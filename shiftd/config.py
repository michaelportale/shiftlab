"""Config loading and validation.

TOML via stdlib tomllib (3.11+). The import is guarded so the rest of the
package, and the test suite, still work on 3.10 where tomllib does not exist.
On 3.10 the loader raises ConfigError with a fix, rather than ImportError at
import time.

Everything is validated up front and loudly. A daemon that silently runs with
half a config is worse than one that refuses to start: the failure mode is
"the phone was never blocked and you did not notice for a week".
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # 3.11+
    import tomllib as _toml  # type: ignore[import-not-found]

    _TOML_SOURCE = "tomllib"
except ImportError:  # pragma: no cover - depends on interpreter
    try:
        import tomli as _toml  # type: ignore[import-not-found,no-redef]

        _TOML_SOURCE = "tomli"
    except ImportError:
        _toml = None  # type: ignore[assignment]
        _TOML_SOURCE = "none"

RULE_KINDS = ("schedule", "session", "manual")

DAYS: Tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY_INDEX: Dict[str, int] = {day: i for i, day in enumerate(DAYS)}
_DAY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "daily": DAYS,
    "everyday": DAYS,
    "all": DAYS,
    "weekdays": DAYS[0:5],
    "weekends": DAYS[5:7],
}

_BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")
_DURATION_RE = re.compile(r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?$", re.IGNORECASE)

DEFAULT_CONFIG_PATH = Path("~/.config/shiftd/config.toml")
DEFAULT_STATE_PATH = Path("~/.local/state/shiftd/state.json")
DEFAULT_LOG_PATH = Path("~/Library/Logs/shiftd/shiftd.log")


class ConfigError(Exception):
    """Config is unusable. The message names the offending key."""


# ---------------------------------------------------------------------------
# scalar parsers
# ---------------------------------------------------------------------------

def parse_hhmm(value: Any, where: str) -> int:
    """'22:30' -> minutes since local midnight."""
    if not isinstance(value, str):
        raise ConfigError(f"{where}: expected a time string like \"22:30\", got {value!r}")
    match = _TIME_RE.match(value.strip())
    if not match:
        raise ConfigError(f"{where}: {value!r} is not HH:MM (24 hour, e.g. \"07:00\")")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ConfigError(f"{where}: {value!r} is not a real time of day")
    return hour * 60 + minute


def format_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_duration(value: Any, where: str) -> int:
    """'90m', '1h30m', '2h', 90 -> seconds. Bare numbers are minutes."""
    if isinstance(value, bool):
        raise ConfigError(f"{where}: expected a duration, got a boolean")
    if isinstance(value, int):
        if value <= 0:
            raise ConfigError(f"{where}: duration must be positive, got {value}")
        return value * 60
    if not isinstance(value, str):
        raise ConfigError(f"{where}: expected a duration like \"90m\" or \"1h30m\", got {value!r}")
    text = value.strip().lower()
    if text.isdigit():
        minutes = int(text)
        if minutes <= 0:
            raise ConfigError(f"{where}: duration must be positive, got {value!r}")
        return minutes * 60
    match = _DURATION_RE.match(text)
    if not match or not any(match.groups()):
        raise ConfigError(
            f"{where}: {value!r} is not a duration. Use \"90m\", \"1h30m\", \"2h\", or a plain "
            "number of minutes."
        )
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = hours * 3600 + minutes * 60
    if seconds <= 0:
        raise ConfigError(f"{where}: duration must be positive, got {value!r}")
    return seconds


def format_duration(seconds: float) -> str:
    total = int(max(0, round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s" if secs else f"{minutes}m"
    return f"{secs}s"


def parse_days(value: Any, where: str) -> Tuple[str, ...]:
    if isinstance(value, str):
        items: List[str] = [value]
    elif isinstance(value, list):
        items = list(value)
    else:
        raise ConfigError(f"{where}: expected a list of weekdays or a keyword like \"daily\"")
    out: List[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ConfigError(f"{where}: {item!r} is not a weekday name")
        token = item.strip().lower()[:9]
        if token in _DAY_ALIASES:
            out.extend(_DAY_ALIASES[token])
            continue
        short = token[:3]
        if short not in _DAY_INDEX:
            raise ConfigError(
                f"{where}: {item!r} is not a weekday. Use {', '.join(DAYS)}, or "
                f"{', '.join(sorted(_DAY_ALIASES))}."
            )
        out.append(short)
    if not out:
        raise ConfigError(f"{where}: no weekdays given")
    return tuple(sorted(set(out), key=lambda d: _DAY_INDEX[d]))


def day_index(name: str) -> int:
    return _DAY_INDEX[name]


def expand_path(value: Any, where: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: expected a filesystem path, got {value!r}")
    return Path(os.path.expandvars(value)).expanduser()


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    """One way a shift can start.

    schedule  recurring window, weekday + start + end, may cross midnight
    session   named preset with a fixed duration, started by hand
    manual    started by hand, duration supplied on the command line
    """

    name: str
    kind: str
    blocklist: str
    locked: bool = False
    enabled: bool = True
    days: Tuple[str, ...] = ()
    start_min: int = 0
    end_min: int = 0
    duration_s: Optional[int] = None

    @property
    def crosses_midnight(self) -> bool:
        return self.kind == "schedule" and self.end_min <= self.start_min

    @property
    def window_seconds(self) -> int:
        """Length of a schedule window, handling the midnight wrap."""
        if self.kind != "schedule":
            return int(self.duration_s or 0)
        span = self.end_min - self.start_min
        if span <= 0:
            span += 24 * 60
        return span * 60

    def describe(self) -> str:
        lock = " [locked]" if self.locked else ""
        if self.kind == "schedule":
            days = "daily" if len(self.days) == 7 else ",".join(self.days)
            return (
                f"{self.name}: schedule {days} "
                f"{format_hhmm(self.start_min)}-{format_hhmm(self.end_min)} "
                f"-> {self.blocklist}{lock}"
            )
        if self.kind == "session":
            return (
                f"{self.name}: session {format_duration(self.duration_s or 0)} "
                f"-> {self.blocklist}{lock}"
            )
        return f"{self.name}: manual -> {self.blocklist}{lock}"


@dataclass(frozen=True)
class DaemonSettings:
    state_file: Path = DEFAULT_STATE_PATH
    log_file: Path = DEFAULT_LOG_PATH
    # Re-push the profile when the phone reappears with it missing. Turning this
    # off makes unplugging the phone a bypass, so it defaults on.
    reassert: bool = True
    # Seconds of wall-clock drift against the monotonic clock before a tick is
    # logged as a clock jump. Normal NTP correction is well under this.
    clock_jump_tolerance_s: int = 120
    # A locked shift refuses to end early. This is the only escape hatch and it
    # is deliberately awkward: the phrase has to be typed exactly.
    override_phrase: str = "break the commitment"
    profile_removal_disallowed: bool = True
    organization: str = "shiftd"


@dataclass(frozen=True)
class Config:
    udid: str
    keybag: Optional[Path]
    device_name: str
    blocklists: Dict[str, Tuple[str, ...]]
    rules: Tuple[Rule, ...]
    daemon: DaemonSettings
    source_path: Optional[Path] = None
    warnings: Tuple[str, ...] = field(default=())

    def rule(self, name: str) -> Optional[Rule]:
        for rule in self.rules:
            if rule.name == name:
                return rule
        return None

    def schedules(self) -> Tuple[Rule, ...]:
        return tuple(r for r in self.rules if r.kind == "schedule")

    def bundle_ids(self, blocklist: str) -> Tuple[str, ...]:
        try:
            return self.blocklists[blocklist]
        except KeyError:
            raise ConfigError(
                f"unknown blocklist {blocklist!r}. Known: {', '.join(sorted(self.blocklists))}"
            ) from None


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _require_table(data: Any, key: str) -> Dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _bool(table: Dict[str, Any], key: str, where: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{where}.{key}: expected true or false, got {value!r}")
    return value


def parse_config(data: Dict[str, Any], source_path: Optional[Path] = None) -> Config:
    """Validate a parsed TOML document. Separated from file IO so tests can
    build configs from dicts."""
    if not isinstance(data, dict):
        raise ConfigError("config root must be a table")

    warnings: List[str] = []

    device = _require_table(data, "device")
    udid = device.get("udid")
    if not isinstance(udid, str) or not udid.strip():
        raise ConfigError(
            "[device].udid is required. Get it with `pymobiledevice3 usbmux list` "
            "or `system_profiler SPUSBDataType`."
        )
    udid = udid.strip()
    if not re.match(r"^[0-9A-Fa-f\-]{8,64}$", udid):
        warnings.append(
            f"[device].udid {udid!r} does not look like a UDID; proceeding, but check it"
        )

    keybag: Optional[Path] = None
    raw_keybag = device.get("keybag", device.get("supervision_identity"))
    if raw_keybag not in (None, ""):
        keybag = expand_path(raw_keybag, "[device].keybag")
        if not keybag.exists():
            raise ConfigError(
                f"[device].keybag: {keybag} does not exist. Export the supervision "
                "identity from Apple Configurator (File > Export > Supervision Identity)."
            )
    else:
        warnings.append(
            "[device].keybag is unset. Installs will be attempted unsupervised, which "
            "means iOS will park the profile in Settings waiting for a tap."
        )

    device_name = device.get("name", "iPhone")
    if not isinstance(device_name, str):
        raise ConfigError("[device].name must be a string")

    raw_lists = _require_table(data, "blocklists")
    if not raw_lists:
        raise ConfigError("[blocklists] is empty. Define at least one, e.g. social = [...]")
    blocklists: Dict[str, Tuple[str, ...]] = {}
    for name, ids in raw_lists.items():
        where = f"[blocklists].{name}"
        if not _NAME_RE.match(name):
            raise ConfigError(f"{where}: blocklist names must be alphanumeric, got {name!r}")
        if not isinstance(ids, list) or not ids:
            raise ConfigError(f"{where}: expected a non-empty list of bundle ids")
        seen: List[str] = []
        for entry in ids:
            if not isinstance(entry, str) or not _BUNDLE_RE.match(entry.strip()):
                raise ConfigError(f"{where}: {entry!r} is not a bundle id (e.g. com.burbn.instagram)")
            bundle = entry.strip()
            if "." not in bundle:
                # Pinterest really does ship as the bare id "pinterest", so this
                # is a warning rather than a rejection.
                warnings.append(f"{where}: {bundle!r} has no dot; unusual for a bundle id, check it")
            if bundle in seen:
                warnings.append(f"{where}: {bundle} listed twice")
                continue
            seen.append(bundle)
        blocklists[name] = tuple(seen)

    raw_rules = data.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ConfigError("[[rules]] must be an array of tables")
    rules: List[Rule] = []
    names: List[str] = []
    for index, raw in enumerate(raw_rules):
        rules.append(_parse_rule(raw, index, blocklists, names, warnings))
    if not rules:
        warnings.append("no [[rules]] defined; only ad hoc `shiftd shift` will do anything")

    daemon_table = _require_table(data, "daemon")
    defaults = DaemonSettings()
    daemon = DaemonSettings(
        state_file=expand_path(
            daemon_table.get("state_file", str(defaults.state_file)), "[daemon].state_file"
        ),
        log_file=expand_path(
            daemon_table.get("log_file", str(defaults.log_file)), "[daemon].log_file"
        ),
        reassert=_bool(daemon_table, "reassert", "[daemon]", defaults.reassert),
        clock_jump_tolerance_s=_positive_int(
            daemon_table.get("clock_jump_tolerance_s", defaults.clock_jump_tolerance_s),
            "[daemon].clock_jump_tolerance_s",
        ),
        override_phrase=_string(
            daemon_table.get("override_phrase", defaults.override_phrase),
            "[daemon].override_phrase",
        ),
        profile_removal_disallowed=_bool(
            daemon_table,
            "profile_removal_disallowed",
            "[daemon]",
            defaults.profile_removal_disallowed,
        ),
        organization=_string(
            daemon_table.get("organization", defaults.organization), "[daemon].organization"
        ),
    )

    unused = set(data) - {"device", "blocklists", "rules", "daemon"}
    for key in sorted(unused):
        warnings.append(f"[{key}] is not a section shiftd knows about; ignored")

    return Config(
        udid=udid,
        keybag=keybag,
        device_name=device_name,
        blocklists=blocklists,
        rules=tuple(rules),
        daemon=daemon,
        source_path=source_path,
        warnings=tuple(warnings),
    )


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{where}: expected a positive integer, got {value!r}")
    return value


def _parse_rule(
    raw: Any,
    index: int,
    blocklists: Dict[str, Tuple[str, ...]],
    seen_names: List[str],
    warnings: List[str],
) -> Rule:
    where = f"[[rules]] #{index + 1}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a table")

    name = raw.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ConfigError(f"{where}: needs a name like \"sleep\" (alphanumeric, dash, dot)")
    where = f"[[rules]] {name!r}"
    if name in seen_names:
        raise ConfigError(f"{where}: duplicate rule name")
    seen_names.append(name)

    kind = raw.get("kind", "schedule")
    if kind not in RULE_KINDS:
        raise ConfigError(f"{where}.kind: expected one of {', '.join(RULE_KINDS)}, got {kind!r}")

    blocklist = raw.get("blocklist")
    if not isinstance(blocklist, str):
        raise ConfigError(f"{where}.blocklist: required, a name from [blocklists]")
    if blocklist not in blocklists:
        raise ConfigError(
            f"{where}.blocklist: unknown blocklist {blocklist!r}. "
            f"Known: {', '.join(sorted(blocklists))}"
        )

    locked = raw.get("locked", False)
    if not isinstance(locked, bool):
        raise ConfigError(f"{where}.locked: expected true or false, got {locked!r}")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{where}.enabled: expected true or false, got {enabled!r}")

    known = {"name", "kind", "blocklist", "locked", "enabled", "days", "start", "end", "duration"}
    for key in sorted(set(raw) - known):
        warnings.append(f"{where}: unknown key {key!r}, ignored")

    if kind == "schedule":
        if "start" not in raw or "end" not in raw:
            raise ConfigError(f"{where}: a schedule rule needs start and end, e.g. \"22:30\"")
        start_min = parse_hhmm(raw["start"], f"{where}.start")
        end_min = parse_hhmm(raw["end"], f"{where}.end")
        if start_min == end_min:
            raise ConfigError(
                f"{where}: start and end are both {raw['start']!r}. A zero length window "
                "is almost certainly not what you meant; for all day use 00:00 to 23:59."
            )
        days = parse_days(raw.get("days", "daily"), f"{where}.days")
        if "duration" in raw:
            warnings.append(f"{where}: duration ignored for a schedule rule")
        return Rule(
            name=name,
            kind=kind,
            blocklist=blocklist,
            locked=locked,
            enabled=enabled,
            days=days,
            start_min=start_min,
            end_min=end_min,
        )

    if kind == "session":
        if "duration" not in raw:
            raise ConfigError(f"{where}: a session rule needs a duration, e.g. \"90m\"")
        duration_s = parse_duration(raw["duration"], f"{where}.duration")
        return Rule(
            name=name,
            kind=kind,
            blocklist=blocklist,
            locked=locked,
            enabled=enabled,
            duration_s=duration_s,
        )

    duration_s = parse_duration(raw["duration"], f"{where}.duration") if "duration" in raw else None
    return Rule(
        name=name,
        kind=kind,
        blocklist=blocklist,
        locked=locked,
        enabled=enabled,
        duration_s=duration_s,
    )


def load(path: Optional[Path] = None) -> Config:
    """Read and validate a config file."""
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH.expanduser()
    if not config_path.exists():
        raise ConfigError(
            f"no config at {config_path}. Copy shiftd/config.example.toml there and edit it."
        )
    if _toml is None:
        raise ConfigError(
            "no TOML parser available. shiftd wants Python 3.11+ for stdlib tomllib; "
            "on 3.10 either `pip install tomli` or run shiftd under a newer interpreter."
        )
    try:
        raw = _toml.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"cannot read {config_path}: {exc}") from exc
    except Exception as exc:  # tomllib.TOMLDecodeError, name differs across backends
        raise ConfigError(f"{config_path} is not valid TOML: {exc}") from exc
    return parse_config(raw, source_path=config_path)


def toml_backend() -> str:
    """Which TOML parser is in play. Used by `doctor`."""
    return _TOML_SOURCE
