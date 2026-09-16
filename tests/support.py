"""Fakes shared by the test modules.

Nothing here touches a device, a real clock, or a TOML file. Configs are built
from dicts through config.parse_config so the suite runs on 3.10 where
tomllib does not exist.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from shiftd import profiles
from shiftd.config import Config, parse_config
from shiftd.transport import TransportResult


class FakeClock:
    """Wall and monotonic clocks that move independently, which is the point."""

    def __init__(self, wall: float = 1_700_000_000.0, mono: float = 1000.0):
        self._wall = wall
        self._mono = mono

    def wall(self) -> float:
        return self._wall

    def mono(self) -> float:
        return self._mono

    def mono_source(self) -> str:
        return "fake"

    def advance(self, seconds: float) -> None:
        """Time passes normally: both clocks move together."""
        self._wall += seconds
        self._mono += seconds

    def set_wall(self, epoch: float) -> None:
        """Someone ran `date`. Only the wall clock moves."""
        self._wall = epoch

    def jump_wall(self, seconds: float) -> None:
        self._wall += seconds

    def reboot(self, wall_gap: float = 300.0, mono_start: float = 5.0) -> None:
        """Monotonic resets, wall keeps going."""
        self._wall += wall_gap
        self._mono = mono_start

    def set_local(self, text: str) -> None:
        """Set the wall clock from a local 'YYYY-MM-DD HH:MM' string."""
        self._wall = datetime.strptime(text, "%Y-%m-%d %H:%M").timestamp()


class FakeTransport:
    """Stands in for the phone. Records every call."""

    def __init__(self, reachable: bool = True, installed: Optional[Set[str]] = None):
        self.reachable_flag = reachable
        self.installed: Set[str] = set(installed or set())
        self.calls: List[str] = []
        self.installs: List[str] = []
        self.removals: List[str] = []
        self.last_via = "fake"
        self.last_binding = "fake"
        self.dry_run = False
        # Set to force real (non unreachable) failures.
        self.fail_install: Optional[str] = None
        self.fail_list: Optional[str] = None

    # -- helpers used by tests --------------------------------------------

    def drop_profile(self, identifier: str) -> None:
        """Simulate the profile disappearing behind the daemon's back."""
        self.installed.discard(identifier)

    def count_installs(self, identifier: Optional[str] = None) -> int:
        if identifier is None:
            return len(self.installs)
        return sum(1 for entry in self.installs if identifier in entry)

    # -- transport API ----------------------------------------------------

    def _unreachable(self) -> TransportResult:
        return TransportResult(False, "fake", None, "device not found", unreachable=True)

    def device_info(self) -> TransportResult:
        self.calls.append("device_info")
        if not self.reachable_flag:
            return self._unreachable()
        return TransportResult(True, "fake", {"IsSupervised": True, "ProductVersion": "18.2"})

    def list_profiles(self) -> TransportResult:
        self.calls.append("list_profiles")
        if not self.reachable_flag:
            return self._unreachable()
        if self.fail_list:
            return TransportResult(False, "fake", None, self.fail_list)
        return TransportResult(
            True, "fake", [{"PayloadIdentifier": ident} for ident in sorted(self.installed)]
        )

    def install_profile(self, path: Path, keybag: Optional[Path] = None) -> TransportResult:
        self.calls.append("install_profile")
        if not self.reachable_flag:
            return self._unreachable()
        if self.fail_install:
            return TransportResult(False, "fake", None, self.fail_install)
        identifier = _identifier_from_path(path)
        self.installed.add(identifier)
        self.installs.append(identifier)
        return TransportResult(True, "fake", binding="fake.install")

    def remove_profile(self, identifier: str) -> TransportResult:
        self.calls.append("remove_profile")
        if not self.reachable_flag:
            return self._unreachable()
        self.installed.discard(identifier)
        self.removals.append(identifier)
        return TransportResult(True, "fake", binding="fake.remove")

    def is_supervised(self) -> TransportResult:
        return TransportResult(True, "fake", True)


def _identifier_from_path(path: Path) -> str:
    return profiles.identifier_for(Path(path).stem)


def make_config(rules: Optional[List[Dict[str, Any]]] = None, **overrides: Any) -> Config:
    data: Dict[str, Any] = {
        "device": {"udid": "00008130-000A1B2C3D4E001E", "name": "test iPhone"},
        "blocklists": {
            "social": ["com.burbn.instagram", "com.reddit.Reddit"],
            "games": ["com.roblox.robloxmobile"],
        },
        "rules": rules if rules is not None else [],
        "daemon": {},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key].update(value)
        else:
            data[key] = value
    return parse_config(data)


def silence_logging() -> None:
    """Keep the daemon's own logging out of the test output."""
    import logging

    logger = logging.getLogger("shiftd")
    logger.handlers = [logging.NullHandler()]
    logger.propagate = False
    logger.setLevel(logging.CRITICAL + 1)


silence_logging()
