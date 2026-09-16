"""Persistent state: what is shifted, until when, whether it is locked.

Survives daemon restarts and Mac reboots because everything lives in one JSON
file written atomically.

Clock design, which is the part worth reading:

A locked shift counts down a budget of seconds, not a wall-clock deadline. The
budget is decremented by the monotonic clock, which no `date` command can move.
Setting the Mac clock forward to 07:30 during a locked 22:30-07:00 block
therefore buys nothing: wall time says the window is over, the budget says
four hours left, and the budget wins.

Source of elapsed time, in order:

  1. time.clock_gettime(CLOCK_MONOTONIC). On macOS this keeps counting while
     the machine is asleep and ignores clock changes. Exactly what is wanted.
  2. time.monotonic(). On macOS this excludes sleep, so a Mac that slept all
     night under-credits the budget and the shift runs long. Conservative in
     the right direction for a commitment device, but it is a fallback.

Both reset at boot. A negative delta means the machine rebooted, in which case
the only available measure is the wall clock, clamped to non-negative and
logged. Disagreement between wall and monotonic beyond a tolerance is recorded
as a clock jump in the history whether or not it changes the outcome.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import log

STATE_VERSION = 1
HISTORY_LIMIT = 400

_LOG = log.get("state")

SOURCE_MONOTONIC = "monotonic"
SOURCE_WALL_AFTER_REBOOT = "wall-after-reboot"
SOURCE_FIRST_TICK = "first-tick"


def iso(epoch: Optional[float]) -> str:
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch, timezone.utc).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# clocks
# ---------------------------------------------------------------------------

class SystemClock:
    """Real clocks. Tests substitute their own object with the same methods."""

    def wall(self) -> float:
        return time.time()

    def mono(self) -> float:
        try:
            # macOS CLOCK_MONOTONIC advances across sleep; time.monotonic() does not.
            return time.clock_gettime(time.CLOCK_MONOTONIC)
        except (AttributeError, OSError):  # pragma: no cover - platform dependent
            return time.monotonic()

    def mono_source(self) -> str:
        try:
            time.clock_gettime(time.CLOCK_MONOTONIC)
            return "CLOCK_MONOTONIC"
        except (AttributeError, OSError):  # pragma: no cover - platform dependent
            return "time.monotonic"


@dataclass
class ClockTick:
    elapsed_s: float
    source: str
    wall_delta_s: float
    mono_delta_s: float
    jump_s: float = 0.0
    jumped: bool = False
    rebooted: bool = False


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------

@dataclass
class Shift:
    """One active block. `remaining_s` is authoritative, `ends_at` is a hint."""

    blocklist: str
    rule: str
    kind: str
    locked: bool
    profile_identifier: str
    content_hash: str = ""
    started_at: float = 0.0
    ends_at: Optional[float] = None
    remaining_s: Optional[float] = None
    # Profile confirmed present on the device at the last successful check.
    applied: bool = False
    apply_attempts: int = 0
    last_apply_error: str = ""
    last_applied_at: Optional[float] = None
    last_seen_on_device_at: Optional[float] = None

    @property
    def open_ended(self) -> bool:
        return self.remaining_s is None

    @property
    def expired(self) -> bool:
        return self.remaining_s is not None and self.remaining_s <= 0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["started_at_iso"] = iso(self.started_at)
        data["ends_at_iso"] = iso(self.ends_at)
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Shift":
        fields = {f for f in Shift.__dataclass_fields__}  # type: ignore[attr-defined]
        return Shift(**{k: v for k, v in data.items() if k in fields})


@dataclass
class ClockState:
    last_wall: Optional[float] = None
    last_mono: Optional[float] = None
    jumps: int = 0
    reboots: int = 0
    last_jump_at: Optional[float] = None


@dataclass
class State:
    version: int = STATE_VERSION
    current: Optional[Shift] = None
    clock: ClockState = field(default_factory=ClockState)
    history: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "current": self.current.to_dict() if self.current else None,
            "clock": asdict(self.clock),
            "history": self.history[-HISTORY_LIMIT:],
            "updated_at": self.updated_at,
            "updated_at_iso": iso(self.updated_at),
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "State":
        current = data.get("current")
        clock_raw = data.get("clock") or {}
        clock_fields = {f for f in ClockState.__dataclass_fields__}  # type: ignore[attr-defined]
        return State(
            version=int(data.get("version", STATE_VERSION)),
            current=Shift.from_dict(current) if isinstance(current, dict) else None,
            clock=ClockState(**{k: v for k, v in clock_raw.items() if k in clock_fields}),
            history=list(data.get("history") or []),
            updated_at=float(data.get("updated_at") or 0.0),
        )


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

class StateStore:
    """Load, mutate, save. Every mutation goes through here."""

    def __init__(self, path: Path, clock: Optional[SystemClock] = None, read_only: bool = False):
        self.path = Path(path).expanduser()
        self.clock = clock or SystemClock()
        self.read_only = read_only
        self.state = State()
        self.loaded_from_disk = False

    # -- persistence -------------------------------------------------------

    def load(self) -> State:
        if not self.path.exists():
            self.state = State()
            self.loaded_from_disk = False
            return self.state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.state = State.from_dict(raw)
            self.loaded_from_disk = True
        except (OSError, ValueError, TypeError) as exc:
            # Corrupt state ends any active shift, including a locked one. That is
            # a real hole and it is documented in docs/DAEMON.md. Keep the file so
            # it can be inspected rather than overwriting the evidence.
            backup = self.path.with_suffix(self.path.suffix + f".corrupt-{int(time.time())}")
            try:
                self.path.replace(backup)
            except OSError:
                backup = self.path
            _LOG.error(log.kv("state.corrupt", path=str(self.path), backup=str(backup), error=str(exc)))
            self.state = State()
            self.loaded_from_disk = False
            self.note("state.corrupt", backup=str(backup), error=str(exc)[:200])
        if self.state.version != STATE_VERSION:
            _LOG.warning(log.kv("state.version_mismatch", found=self.state.version, expected=STATE_VERSION))
            self.state.version = STATE_VERSION
        return self.state

    def save(self) -> None:
        if self.read_only:
            _LOG.debug(log.kv("state.save_skipped", reason="read_only"))
            return
        self.state.updated_at = self.clock.wall()
        self.state.history = self.state.history[-HISTORY_LIMIT:]
        payload = json.dumps(self.state.to_dict(), indent=2, sort_keys=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    # -- history -----------------------------------------------------------

    def note(self, event: str, **fields: Any) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"at": self.clock.wall(), "at_iso": iso(self.clock.wall()), "event": event}
        entry.update(fields)
        self.state.history.append(entry)
        return entry

    def history_tail(self, count: int = 20) -> List[Dict[str, Any]]:
        return self.state.history[-count:]

    # -- clock -------------------------------------------------------------

    def tick(self, tolerance_s: float = 120.0) -> ClockTick:
        """Advance the clock accounting and decrement any active budget.

        Call once per reconcile, before deciding anything.
        """
        now_wall = self.clock.wall()
        now_mono = self.clock.mono()
        prev = self.state.clock

        if prev.last_wall is None or prev.last_mono is None:
            tick = ClockTick(0.0, SOURCE_FIRST_TICK, 0.0, 0.0)
        else:
            wall_delta = now_wall - prev.last_wall
            mono_delta = now_mono - prev.last_mono
            if mono_delta < 0:
                # Monotonic went backwards: the Mac rebooted. Wall clock is the
                # only measure left, and it is clamped so a backwards clock
                # cannot hand back time already served.
                prev.reboots += 1
                elapsed = max(0.0, wall_delta)
                tick = ClockTick(
                    elapsed, SOURCE_WALL_AFTER_REBOOT, wall_delta, mono_delta, rebooted=True
                )
                _LOG.info(
                    log.kv("clock.reboot", wall_delta=round(wall_delta, 1), credited=round(elapsed, 1))
                )
                self.note("clock.reboot", wall_delta=round(wall_delta, 1), credited=round(elapsed, 1))
            else:
                jump = wall_delta - mono_delta
                tick = ClockTick(mono_delta, SOURCE_MONOTONIC, wall_delta, mono_delta, jump_s=jump)
                if abs(jump) > tolerance_s:
                    tick.jumped = True
                    prev.jumps += 1
                    prev.last_jump_at = now_wall
                    _LOG.warning(
                        log.kv(
                            "clock.jump",
                            delta_s=round(jump, 1),
                            direction="forward" if jump > 0 else "backward",
                            credited=round(mono_delta, 1),
                        )
                    )
                    self.note(
                        "clock.jump",
                        delta_s=round(jump, 1),
                        wall_delta=round(wall_delta, 1),
                        mono_delta=round(mono_delta, 1),
                    )

        prev.last_wall = now_wall
        prev.last_mono = now_mono

        shift = self.state.current
        if shift is not None and shift.remaining_s is not None and tick.elapsed_s > 0:
            shift.remaining_s = max(0.0, shift.remaining_s - tick.elapsed_s)
            if shift.ends_at is not None:
                # Keep the display deadline honest against the real budget.
                shift.ends_at = now_wall + shift.remaining_s
        return tick

    # -- shifts ------------------------------------------------------------

    def start_shift(
        self,
        *,
        blocklist: str,
        rule: str,
        kind: str,
        locked: bool,
        profile_identifier: str,
        duration_s: Optional[float],
        content_hash: str = "",
    ) -> Shift:
        now = self.clock.wall()
        shift = Shift(
            blocklist=blocklist,
            rule=rule,
            kind=kind,
            locked=locked,
            profile_identifier=profile_identifier,
            content_hash=content_hash,
            started_at=now,
            ends_at=(now + duration_s) if duration_s is not None else None,
            remaining_s=float(duration_s) if duration_s is not None else None,
        )
        self.state.current = shift
        _LOG.info(
            log.kv(
                "shift.start",
                blocklist=blocklist,
                rule=rule,
                kind=kind,
                locked=locked,
                duration_s=int(duration_s) if duration_s is not None else "open",
            )
        )
        self.note(
            "shift.start",
            blocklist=blocklist,
            rule=rule,
            kind=kind,
            locked=locked,
            ends_at_iso=iso(shift.ends_at),
        )
        return shift

    def end_shift(self, reason: str) -> Optional[Shift]:
        shift = self.state.current
        if shift is None:
            return None
        self.state.current = None
        _LOG.info(log.kv("shift.end", blocklist=shift.blocklist, rule=shift.rule, reason=reason))
        self.note(
            "shift.end",
            blocklist=shift.blocklist,
            rule=shift.rule,
            reason=reason,
            served_s=int(self.clock.wall() - shift.started_at),
        )
        return shift

    def mark_applied(self, content_hash: str = "") -> None:
        shift = self.state.current
        if shift is None:
            return
        now = self.clock.wall()
        shift.applied = True
        shift.last_applied_at = now
        shift.last_seen_on_device_at = now
        shift.last_apply_error = ""
        shift.apply_attempts = 0
        if content_hash:
            shift.content_hash = content_hash

    def mark_apply_failed(self, error: str) -> None:
        shift = self.state.current
        if shift is None:
            return
        shift.applied = False
        shift.apply_attempts += 1
        shift.last_apply_error = error[:500]

    def mark_seen_on_device(self) -> None:
        shift = self.state.current
        if shift is not None:
            shift.last_seen_on_device_at = self.clock.wall()

    # -- queries -----------------------------------------------------------

    @property
    def current(self) -> Optional[Shift]:
        return self.state.current

    def locked_hold(self) -> Optional[Shift]:
        """The active shift if it is locked and its budget is not exhausted."""
        shift = self.state.current
        if shift is None or not shift.locked:
            return None
        if shift.remaining_s is not None and shift.remaining_s <= 0:
            return None
        return shift
