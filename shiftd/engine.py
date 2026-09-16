"""Scheduler and reconciler.

One function matters: reconcile(). It reads config, state and the clock,
decides what the phone should look like right now, and moves it one step
toward that. It is safe to run every 60 seconds forever, and safe to run twice
in the same second.

Idempotency comes from three properties:

  * installing a profile is an upsert, because PayloadIdentifier is stable per
    blocklist (see profiles.py)
  * a device write only happens when the observed device state differs from the
    desired one: right profile present, right content hash, nothing stale
  * all lifecycle transitions are derived from state plus clock, never from
    "what happened last time this ran"

Rules of the engine:

  * A locked shift is never ended early. Not by a schedule change, not by
    `shiftd unshift`, not by editing the config, not by moving the clock.
  * The phone being unreachable is a retry, not a failure. When it comes back
    the profile is re-asserted, so unplugging is not a bypass, only a delay.
  * Exactly one shift is active at a time. Overlapping schedule windows resolve
    by precedence, locked first.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import log, profiles
from .config import DAYS, Config, Rule, format_duration
from .state import Shift, StateStore, SystemClock
from .transport import Transport, installed_identifiers

_LOG = log.get("engine")

PROFILE_PREFIX = f"{profiles.BASE_ID}.block."


class EngineError(Exception):
    """Operator error. The message is meant to be printed as is."""


class LockedShiftActive(EngineError):
    def __init__(self, shift: Shift, remaining_s: Optional[float]):
        self.shift = shift
        self.remaining_s = remaining_s
        when = (
            f"ends in {format_duration(remaining_s)}"
            if remaining_s is not None
            else "has no end time, it was started open ended"
        )
        super().__init__(
            f"'{shift.rule}' is locked and {when}. That is the point of locking it. "
            "The only way out is deleting the state file and the profile by hand, "
            "which you will remember doing."
        )


@dataclass
class Target:
    """What should be on the phone right now."""

    blocklist: str
    rule: str
    kind: str
    locked: bool
    duration_s: Optional[float]

    @property
    def identifier(self) -> str:
        return profiles.identifier_for(self.blocklist)


@dataclass
class ReconcileReport:
    dry_run: bool = False
    target: Optional[Target] = None
    actions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    device_reachable: Optional[bool] = None
    via: str = ""
    clock_jumped: bool = False
    changed: bool = False

    def act(self, message: str) -> None:
        self.actions.append(message)
        self.changed = True

    def observe(self, message: str) -> None:
        self.actions.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines: List[str] = []
        head = "would do" if self.dry_run else "did"
        if self.target:
            lock = " locked" if self.target.locked else ""
            lines.append(f"target: {self.target.blocklist} via {self.target.rule}{lock}")
        else:
            lines.append("target: nothing blocked")
        if not self.actions:
            lines.append(f"{head}: nothing, already converged")
        for action in self.actions:
            lines.append(f"{head}: {action}")
        for error in self.errors:
            lines.append(f"error: {error}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# schedule maths
# ---------------------------------------------------------------------------

def schedule_remaining(rule: Rule, now: datetime) -> Optional[float]:
    """Seconds left in this rule's window, or None when it is not active.

    A window that crosses midnight belongs to the day it STARTS on: a
    22:30-07:00 rule with days=["fri"] runs Friday night into Saturday morning.
    """
    if rule.kind != "schedule" or not rule.enabled:
        return None
    length = timedelta(seconds=rule.window_seconds)
    for days_back in (0, 1):
        start_day = (now - timedelta(days=days_back)).date()
        if DAYS[start_day.weekday()] not in rule.days:
            continue
        start = datetime.combine(start_day, datetime.min.time()) + timedelta(minutes=rule.start_min)
        end = start + length
        if start <= now < end:
            return (end - now).total_seconds()
    return None


def _precedence(item: Tuple[Rule, float]) -> Tuple[int, float]:
    rule, remaining = item
    # Locked wins. Then the one that lasts longest, so a short unlocked window
    # cannot truncate a long one.
    return (0 if rule.locked else 1, -remaining)


class Engine:
    def __init__(
        self,
        config: Config,
        store: StateStore,
        transport: Transport,
        clock: Optional[SystemClock] = None,
        profile_dir: Optional[Path] = None,
    ):
        self.config = config
        self.store = store
        self.transport = transport
        self.clock = clock or store.clock
        self.profile_dir = Path(profile_dir or (store.path.parent / "profiles"))

    # -- decision ----------------------------------------------------------

    def now_local(self) -> datetime:
        return datetime.fromtimestamp(self.clock.wall())

    def active_schedule(self) -> Optional[Tuple[Rule, float]]:
        """Highest precedence schedule window covering now."""
        now = self.now_local()
        candidates: List[Tuple[Rule, float]] = []
        for rule in self.config.schedules():
            remaining = schedule_remaining(rule, now)
            if remaining is not None and remaining > 0:
                candidates.append((rule, remaining))
        if not candidates:
            return None
        candidates.sort(key=_precedence)
        return candidates[0]

    def desired(self) -> Optional[Target]:
        """What should be blocked right now, given state and config.

        An active shift holds until its budget runs out. A schedule window only
        gets to start a shift when nothing is already running.
        """
        shift = self.store.current
        if shift is not None and not shift.expired:
            return Target(
                blocklist=shift.blocklist,
                rule=shift.rule,
                kind=shift.kind,
                locked=shift.locked,
                duration_s=shift.remaining_s,
            )
        scheduled = self.active_schedule()
        if scheduled is None:
            return None
        rule, remaining = scheduled
        return Target(
            blocklist=rule.blocklist,
            rule=rule.name,
            kind=rule.kind,
            locked=rule.locked,
            duration_s=remaining,
        )

    # -- operator commands -------------------------------------------------

    def start(
        self,
        name: str,
        duration_s: Optional[float] = None,
        locked: Optional[bool] = None,
    ) -> Shift:
        """Start a shift by blocklist name or by rule name.

        `shiftd shift deep-work` uses the rule's blocklist, duration and locked
        flag as defaults. `shiftd shift social --for 90m` works straight off a
        blocklist.
        """
        held = self.store.locked_hold()
        if held is not None:
            raise LockedShiftActive(held, held.remaining_s)

        rule = self.config.rule(name)
        if rule is not None:
            blocklist = rule.blocklist
            kind = rule.kind
            rule_name = rule.name
            if duration_s is None:
                duration_s = rule.duration_s
            if locked is None:
                locked = rule.locked
        elif name in self.config.blocklists:
            blocklist = name
            kind = "manual"
            rule_name = "ad-hoc"
        else:
            known_rules = ", ".join(r.name for r in self.config.rules) or "none"
            raise EngineError(
                f"no blocklist or rule named {name!r}. "
                f"Blocklists: {', '.join(sorted(self.config.blocklists))}. Rules: {known_rules}."
            )

        if duration_s is not None and duration_s <= 0:
            raise EngineError("duration must be positive")
        if locked and duration_s is None:
            raise EngineError(
                "refusing to start an open ended locked shift. A locked shift with no end "
                "is a factory reset waiting to happen. Pass --for."
            )

        self.config.bundle_ids(blocklist)  # raises with a useful message if unknown
        if self.store.current is not None:
            self.store.end_shift("superseded")
        shift = self.store.start_shift(
            blocklist=blocklist,
            rule=rule_name,
            kind=kind,
            locked=bool(locked),
            profile_identifier=profiles.identifier_for(blocklist),
            duration_s=duration_s,
        )
        return shift

    def unshift(self) -> Optional[Shift]:
        """End the current shift. Refuses while it is locked."""
        held = self.store.locked_hold()
        if held is not None:
            raise LockedShiftActive(held, held.remaining_s)
        shift = self.store.current
        if shift is None:
            return None
        return self.store.end_shift("unshift")

    # -- reconcile ---------------------------------------------------------

    def reconcile(self, dry_run: bool = False) -> ReconcileReport:
        report = ReconcileReport(dry_run=dry_run)

        tick = self.store.tick(self.config.daemon.clock_jump_tolerance_s)
        report.clock_jumped = tick.jumped
        if tick.jumped:
            report.observe(
                f"clock jump {int(tick.jump_s)}s detected, credited {int(tick.elapsed_s)}s "
                "from the monotonic clock instead"
            )

        shift = self.store.current
        if shift is not None and shift.expired:
            # Locked or not, an exhausted budget is over. Locked only ever means
            # "cannot end EARLY".
            self.store.end_shift("expired")
            report.act(f"ended {shift.rule} ({shift.blocklist}), time served")
            shift = None

        target = self.desired()
        report.target = target

        if target is not None and self.store.current is None:
            self.store.start_shift(
                blocklist=target.blocklist,
                rule=target.rule,
                kind=target.kind,
                locked=target.locked,
                profile_identifier=target.identifier,
                duration_s=target.duration_s,
            )
            report.act(
                f"started {target.rule} ({target.blocklist})"
                + (f" for {format_duration(target.duration_s)}" if target.duration_s else "")
            )

        self._converge(target, report)
        self.store.save()
        return report

    def _converge(self, target: Optional[Target], report: ReconcileReport) -> None:
        """Make the device match `target`. Only writes when something differs."""
        listing = self.transport.list_profiles()
        report.via = self.transport.last_via
        if not listing.ok:
            report.device_reachable = False if listing.unreachable else None
            if listing.unreachable:
                if target is not None:
                    self.store.mark_apply_failed("device unreachable")
                    report.observe("device unreachable, will re-assert when it is back")
                    _LOG.info(log.kv("reconcile.unreachable", blocklist=target.blocklist))
                else:
                    report.observe("device unreachable, nothing to do anyway")
                return
            # A listing that failed for a real reason is not proof the profile is
            # absent, so fall through and let the upsert sort it out.
            report.errors.append(f"profile list failed: {listing.error[:200]}")

        present = set(installed_identifiers(listing.data)) if listing.ok else set()
        if listing.ok:
            report.device_reachable = True
            self.store.mark_seen_on_device()

        ours = {ident for ident in present if ident.startswith(PROFILE_PREFIX)}
        wanted = target.identifier if target else None

        for identifier in sorted(ours - ({wanted} if wanted else set())):
            self._remove(identifier, report, reason="stale")

        if target is None:
            return

        bundle_ids = self.config.bundle_ids(target.blocklist)
        path, digest = profiles.build_to(
            self.profile_dir,
            target.blocklist,
            bundle_ids,
            removal_disallowed=self.config.daemon.profile_removal_disallowed,
            organization=self.config.daemon.organization,
        )

        shift = self.store.current
        installed = wanted in present if listing.ok else False
        content_matches = bool(shift and shift.content_hash == digest)
        if installed and content_matches and shift is not None and shift.applied:
            report.observe(f"{target.blocklist} already enforced ({len(bundle_ids)} apps)")
            self.store.mark_applied(digest)
            return

        if not self.config.daemon.reassert and installed and shift is not None and shift.applied:
            return

        why = "missing from device" if not installed else ("content changed" if not content_matches else "unconfirmed")
        result = self.transport.install_profile(path, keybag=self.config.keybag)
        report.via = self.transport.last_via
        if result.ok:
            self.store.mark_applied(digest)
            report.act(
                f"installed {target.blocklist} ({len(bundle_ids)} apps, {why}) via {result.via}"
            )
            _LOG.info(
                log.kv(
                    "reconcile.installed",
                    blocklist=target.blocklist,
                    apps=len(bundle_ids),
                    reason=why,
                    via=result.via,
                    binding=result.binding or "-",
                )
            )
        else:
            self.store.mark_apply_failed(result.error or result.summary())
            if result.unreachable:
                report.device_reachable = False
                report.observe("device went away mid install, will retry next pass")
            else:
                report.errors.append(f"install failed: {result.summary()}")
            _LOG.warning(
                log.kv(
                    "reconcile.install_failed",
                    blocklist=target.blocklist,
                    unreachable=result.unreachable,
                    error=(result.error or "")[:200],
                )
            )

    def _remove(self, identifier: str, report: ReconcileReport, reason: str) -> None:
        result = self.transport.remove_profile(identifier)
        report.via = self.transport.last_via
        if result.ok:
            report.act(f"removed {identifier} ({reason})")
            _LOG.info(log.kv("reconcile.removed", identifier=identifier, reason=reason, via=result.via))
        elif result.unreachable:
            report.device_reachable = False
            report.observe(f"could not remove {identifier}, device unreachable")
        else:
            report.errors.append(f"remove {identifier} failed: {result.summary()}")

    # -- reporting ---------------------------------------------------------

    def status(self) -> Dict[str, object]:
        shift = self.store.current
        scheduled = self.active_schedule()
        next_rule, next_start = self.next_schedule_start()
        return {
            "shift": shift.to_dict() if shift else None,
            "locked": bool(shift and shift.locked and not shift.expired),
            "remaining_s": shift.remaining_s if shift else None,
            "active_schedule": scheduled[0].name if scheduled else None,
            "next_schedule": next_rule.name if next_rule else None,
            "next_schedule_at": next_start.isoformat(timespec="minutes") if next_start else None,
            "device_udid": self.config.udid,
            "state_file": str(self.store.path),
            "clock_jumps": self.store.state.clock.jumps,
            "reboots": self.store.state.clock.reboots,
        }

    def next_schedule_start(self, horizon_days: int = 8) -> Tuple[Optional[Rule], Optional[datetime]]:
        """Soonest upcoming schedule window start. Used by `status` and `schedule list`."""
        now = self.now_local()
        best: Optional[Tuple[datetime, Rule]] = None
        for rule in self.config.schedules():
            if not rule.enabled:
                continue
            for offset in range(horizon_days):
                day = (now + timedelta(days=offset)).date()
                if DAYS[day.weekday()] not in rule.days:
                    continue
                start = datetime.combine(day, datetime.min.time()) + timedelta(minutes=rule.start_min)
                if start <= now:
                    continue
                if best is None or start < best[0]:
                    best = (start, rule)
                break
        if best is None:
            return None, None
        return best[1], best[0]
