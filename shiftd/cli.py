"""Command line. Thin: parse, call the engine, print.

    shiftd status
    shiftd shift social --for 90m
    shiftd shift deep-work --locked
    shiftd unshift
    shiftd schedule list
    shiftd reconcile            what launchd runs every 60s
    shiftd doctor
    shiftd --dry-run reconcile  decide everything, touch nothing

Exit codes: 0 ok, 1 runtime failure, 2 config problem, 3 refused because a
locked shift is active.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, log, profiles
from .config import (
    Config,
    ConfigError,
    DEFAULT_CONFIG_PATH,
    format_duration,
    load as load_config,
    parse_duration,
    toml_backend,
)
from .engine import Engine, EngineError, LockedShiftActive
from .state import StateStore, SystemClock, iso
from .transport import PMD3_CLI, Transport

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2
EXIT_LOCKED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shiftd", description=__doc__.split("\n")[0])
    parser.add_argument("--config", type=Path, default=None, help=f"default {DEFAULT_CONFIG_PATH}")
    parser.add_argument("--state", type=Path, default=None, help="override [daemon].state_file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="decide everything, write nothing to the phone or to state",
    )
    parser.add_argument("--json", action="store_true", help="machine readable output where it exists")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"shiftd {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="what is blocked, until when, and why")

    shift = sub.add_parser("shift", help="start a shift by blocklist or rule name")
    shift.add_argument("name", help="a blocklist from [blocklists] or a rule from [[rules]]")
    shift.add_argument("--for", dest="duration", default=None, help="e.g. 90m, 1h30m")
    shift.add_argument(
        "--locked",
        action="store_true",
        help="cannot be ended early, including from this Mac. Requires --for.",
    )

    sub.add_parser("unshift", help="end the current shift, unless it is locked")

    schedule = sub.add_parser("schedule", help="inspect schedule rules")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    schedule_sub.add_parser("list", help="list rules and the next window")

    sub.add_parser("reconcile", help="one pass: decide, then converge. What launchd calls.")
    sub.add_parser("doctor", help="environment, config and device checks")
    return parser


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------

def _load(args: argparse.Namespace) -> Config:
    config = load_config(args.config)
    for warning in config.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return config


def _engine(args: argparse.Namespace, config: Config) -> Engine:
    log.setup(config.daemon.log_file, verbose=args.verbose)
    state_path = args.state or config.daemon.state_file
    clock = SystemClock()
    store = StateStore(state_path, clock=clock, read_only=bool(args.dry_run))
    store.load()
    transport = Transport(udid=config.udid, keybag=config.keybag, dry_run=bool(args.dry_run))
    return Engine(config, store, transport, clock=clock)


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace, engine: Engine) -> int:
    status = engine.status()
    if args.json:
        print(json.dumps(status, indent=2, default=str))
        return EXIT_OK

    shift = engine.store.current
    if shift is None:
        print("not shifted")
    else:
        lock = "LOCKED" if shift.locked else "unlocked"
        remaining = (
            format_duration(shift.remaining_s) if shift.remaining_s is not None else "open ended"
        )
        print(f"shifted: {shift.blocklist} ({lock}) via rule '{shift.rule}'")
        print(f"  remaining      {remaining}")
        print(f"  ends           {iso(shift.ends_at) or 'no deadline'}")
        print(f"  started        {iso(shift.started_at)}")
        print(f"  profile        {shift.profile_identifier}")
        applied = "yes" if shift.applied else f"no ({shift.last_apply_error or 'not attempted'})"
        print(f"  on device      {applied}")
        if shift.last_seen_on_device_at:
            print(f"  last confirmed {iso(shift.last_seen_on_device_at)}")
        if shift.locked:
            print("  locked shifts cannot be ended early, including by you")

    next_rule, next_at = engine.next_schedule_start()
    if next_rule is not None and next_at is not None:
        print(f"next window: {next_rule.name} at {next_at.isoformat(timespec='minutes')}")
    clock_state = engine.store.state.clock
    if clock_state.jumps or clock_state.reboots:
        print(f"clock: {clock_state.jumps} jumps, {clock_state.reboots} reboots recorded")
    return EXIT_OK


def cmd_shift(args: argparse.Namespace, engine: Engine) -> int:
    duration_s = parse_duration(args.duration, "--for") if args.duration else None
    locked: Optional[bool] = True if args.locked else None
    shift = engine.start(args.name, duration_s=duration_s, locked=locked)
    lock = " LOCKED" if shift.locked else ""
    ends = format_duration(shift.remaining_s) if shift.remaining_s is not None else "open ended"
    print(f"shift started: {shift.blocklist}{lock}, {ends}")
    report = engine.reconcile(dry_run=bool(args.dry_run))
    print(report.render())
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_unshift(args: argparse.Namespace, engine: Engine) -> int:
    shift = engine.unshift()
    if shift is None:
        print("nothing to unshift")
        return EXIT_OK
    print(f"ended {shift.blocklist} (rule '{shift.rule}')")
    report = engine.reconcile(dry_run=bool(args.dry_run))
    print(report.render())
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_schedule_list(args: argparse.Namespace, engine: Engine) -> int:
    config = engine.config
    if args.json:
        print(json.dumps([r.describe() for r in config.rules], indent=2))
        return EXIT_OK
    if not config.rules:
        print("no rules defined")
        return EXIT_OK
    active = engine.active_schedule()
    active_name = active[0].name if active else None
    for rule in config.rules:
        marker = "*" if rule.name == active_name else " "
        disabled = "" if rule.enabled else "  (disabled)"
        print(f" {marker} {rule.describe()}{disabled}")
    next_rule, next_at = engine.next_schedule_start()
    if next_rule is not None and next_at is not None:
        print(f"\nnext: {next_rule.name} at {next_at.isoformat(timespec='minutes')}")
    if active:
        print(f"active now: {active[0].name}, {format_duration(active[1])} left in the window")
    return EXIT_OK


def cmd_reconcile(args: argparse.Namespace, engine: Engine) -> int:
    report = engine.reconcile(dry_run=bool(args.dry_run))
    if args.json:
        print(
            json.dumps(
                {
                    "dry_run": report.dry_run,
                    "target": report.target.blocklist if report.target else None,
                    "rule": report.target.rule if report.target else None,
                    "locked": report.target.locked if report.target else False,
                    "actions": report.actions,
                    "errors": report.errors,
                    "device_reachable": report.device_reachable,
                    "via": report.via,
                    "changed": report.changed,
                },
                indent=2,
            )
        )
    else:
        print(report.render())
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_doctor(args: argparse.Namespace, engine: Engine) -> int:
    config = engine.config
    problems = 0

    def line(label: str, ok: Optional[bool], detail: str = "") -> None:
        mark = {True: "ok  ", False: "FAIL", None: "??  "}[ok]
        print(f"[{mark}] {label}" + (f": {detail}" if detail else ""))

    py_ok = sys.version_info >= (3, 11)
    backend = toml_backend()
    line(
        "python 3.11+",
        py_ok if backend == "none" else (py_ok or None),
        f"{sys.version_info.major}.{sys.version_info.minor} ({sys.executable})",
    )
    if not py_ok and backend == "none":
        problems += 1
    line("toml backend", backend != "none", backend)
    if backend == "none":
        problems += 1
    line("config", True, str(config.source_path))
    for warning in config.warnings:
        line("config warning", None, warning)
    line("keybag", config.keybag is not None, str(config.keybag or "unset, installs will prompt"))

    try:
        import pymobiledevice3  # type: ignore

        version = getattr(pymobiledevice3, "__version__", "unknown")
        line("pymobiledevice3 import", True, f"version {version}")
    except ImportError as exc:
        problems += 1
        line("pymobiledevice3 import", False, str(exc))

    try:
        probe = subprocess.run(
            PMD3_CLI + ["version"], capture_output=True, text=True, timeout=60
        )
        line("pymobiledevice3 cli", probe.returncode == 0, (probe.stdout or probe.stderr).strip()[:80])
    except (OSError, subprocess.SubprocessError) as exc:
        line("pymobiledevice3 cli", False, str(exc))

    state_path = engine.store.path
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        writable = True
    except OSError as exc:
        writable = False
        line("state dir", False, str(exc))
    if writable:
        line("state file", True, f"{state_path} ({'present' if state_path.exists() else 'new'})")

    if args.dry_run:
        line("device", None, "skipped, --dry-run")
        return EXIT_OK if problems == 0 else EXIT_FAIL

    info = engine.transport.device_info()
    if info.ok and isinstance(info.data, dict):
        name = info.data.get("DeviceName", config.device_name)
        version = info.data.get("ProductVersion", "?")
        line("device reachable", True, f"{name}, iOS {version}, via {info.via}")
        supervised = engine.transport.is_supervised()
        if supervised.ok and supervised.data is True:
            line("supervised", True, "blockedAppBundleIDs will be honored")
        elif supervised.ok and supervised.data is False:
            problems += 1
            line("supervised", False, "unsupervised: app blocking payloads get rejected")
        else:
            line("supervised", None, "could not read IsSupervised")
    else:
        # Not a failure. The phone is off the network most of the day.
        line("device reachable", None, info.summary())

    listing = engine.transport.list_profiles()
    if listing.ok:
        ours = [
            identifier
            for identifier in (
                entry.get("PayloadIdentifier", "") for entry in (listing.data or [])
            )
            if identifier.startswith(profiles.BASE_ID)
        ]
        line("shiftd profiles on device", True, ", ".join(ours) if ours else "none")
    else:
        line("profile list", None, listing.summary())

    try:
        loaded = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=30
        )
        agent_loaded = "com.shiftd.agent" in (loaded.stdout or "")
        line("launchd agent", agent_loaded, "loaded" if agent_loaded else "not loaded, see docs/DAEMON.md")
    except (OSError, subprocess.SubprocessError):
        line("launchd agent", None, "launchctl not available")

    return EXIT_OK if problems == 0 else EXIT_FAIL


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = _load(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    engine = _engine(args, config)
    if args.dry_run:
        print("dry run: nothing will be written to the phone or to the state file")

    try:
        if args.command == "status":
            return cmd_status(args, engine)
        if args.command == "shift":
            return cmd_shift(args, engine)
        if args.command == "unshift":
            return cmd_unshift(args, engine)
        if args.command == "schedule":
            return cmd_schedule_list(args, engine)
        if args.command == "reconcile":
            return cmd_reconcile(args, engine)
        if args.command == "doctor":
            return cmd_doctor(args, engine)
    except LockedShiftActive as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_LOCKED
    except (EngineError, ConfigError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except KeyboardInterrupt:
        return EXIT_FAIL

    print(f"unknown command {args.command!r}", file=sys.stderr)
    return EXIT_FAIL
