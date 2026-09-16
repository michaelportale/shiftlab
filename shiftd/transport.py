"""The only module that talks to the phone.

Two paths to the device:

  library   import pymobiledevice3 and call it in process. Preferred: no
            subprocess per minute, real exceptions, real return values.
  cli       shell out to `python -m pymobiledevice3`, the way shiftlab does.
            The CLI surface moves less between releases than the Python API,
            so this is the fallback when an import or an attribute lookup
            fails.

Every call returns a TransportResult. Nothing here raises for a device that is
not there: an iPhone that is off, asleep, off the network, or unplugged is the
normal case, not an error, and the daemon has to keep running through it.
`unreachable=True` says "try again later", `ok=False` with `unreachable=False`
says "this failed for a real reason, look at .error".

UNCERTAIN, and written defensively because of it:
  * the module path and class name of the profile service
  * the method names on it (install/remove/list)
  * the shape of the keybag argument for a silent supervised install: file
    path, raw bytes, or parsed plist
Each of those probes a list of candidates and records which one worked, in
`last_binding`. When the harness (check 08) reports what actually works, delete
the losing candidates.
"""
from __future__ import annotations

import json
import plistlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import log

LIBRARY = "library"
CLI = "cli"
DRY_RUN = "dry-run"

PMD3_CLI: List[str] = [sys.executable, "-m", "pymobiledevice3"]

DEFAULT_TIMEOUT = 120

# Substrings that mean "the phone is not here right now" rather than "this
# broke". Matched case insensitively against stderr and exception text.
_UNREACHABLE_MARKERS: Tuple[str, ...] = (
    "no device",
    "device not found",
    "nodeviceconnected",
    "connectionfailed",
    "muxexception",
    "usbmux",
    "unable to connect",
    "failed to connect",
    "connection refused",
    "no such device",
    "timed out",
    "passwordrequired",
    "device is locked",
    "pairing",
)

_LOG = log.get("transport")


def _looks_unreachable(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _UNREACHABLE_MARKERS)


@dataclass
class TransportResult:
    ok: bool
    via: str
    data: Any = None
    error: str = ""
    unreachable: bool = False
    argv: Optional[List[str]] = None
    binding: str = ""
    elapsed_ms: int = 0

    def __bool__(self) -> bool:
        return self.ok

    def summary(self) -> str:
        if self.ok:
            return f"ok via {self.via}" + (f" ({self.binding})" if self.binding else "")
        if self.unreachable:
            return f"device unreachable via {self.via}: {self.error or 'no detail'}"
        return f"failed via {self.via}: {self.error or 'no detail'}"


@dataclass
class Transport:
    """Device access. Construct once per process."""

    udid: Optional[str] = None
    keybag: Optional[Path] = None
    dry_run: bool = False
    prefer_library: bool = True
    timeout: int = DEFAULT_TIMEOUT
    # Populated as calls run: name of the import/method combination that worked.
    last_binding: str = ""
    last_via: str = ""
    _library_broken: str = field(default="", init=False, repr=False)
    _service_cache: Any = field(default=None, init=False, repr=False)

    # -- public API --------------------------------------------------------

    def device_info(self) -> TransportResult:
        """Lockdown info dict. Cheap reachability probe."""
        if self.dry_run:
            return self._dry("device_info", {})
        return self._attempt(self._lib_device_info, self._cli_device_info, "device_info")

    def install_profile(self, path: Path, keybag: Optional[Path] = None) -> TransportResult:
        """Install or replace a .mobileconfig. Replacement is by
        PayloadIdentifier, so this is an upsert, not an append."""
        path = Path(path)
        bag = keybag if keybag is not None else self.keybag
        if self.dry_run:
            return self._dry("install_profile", {"path": str(path), "keybag": str(bag or "")})
        if not path.exists():
            return TransportResult(False, LIBRARY, error=f"profile not found: {path}")
        return self._attempt(
            lambda: self._lib_install(path, bag),
            lambda: self._cli_install(path, bag),
            "install_profile",
        )

    def remove_profile(self, identifier: str) -> TransportResult:
        if self.dry_run:
            return self._dry("remove_profile", {"identifier": identifier})
        return self._attempt(
            lambda: self._lib_remove(identifier),
            lambda: self._cli_remove(identifier),
            "remove_profile",
        )

    def list_profiles(self) -> TransportResult:
        """data is a list of dicts, each with at least PayloadIdentifier."""
        if self.dry_run:
            return self._dry("list_profiles", [])
        return self._attempt(self._lib_list, self._cli_list, "list_profiles")

    def is_supervised(self) -> TransportResult:
        """data is True/False, or None when the field is absent."""
        info = self.device_info()
        if not info.ok:
            return TransportResult(
                False, info.via, None, info.error, info.unreachable, info.argv, info.binding
            )
        value = None
        if isinstance(info.data, dict):
            for key in ("IsSupervised", "isSupervised", "Supervised"):
                if key in info.data:
                    value = bool(info.data[key])
                    break
        return TransportResult(True, info.via, value, binding=info.binding)

    def reachable(self) -> bool:
        return bool(self.device_info().ok)

    # -- dispatch ----------------------------------------------------------

    def _dry(self, what: str, data: Any) -> TransportResult:
        _LOG.info(log.kv("transport.dry_run", call=what))
        self.last_via = DRY_RUN
        return TransportResult(True, DRY_RUN, data, binding="dry-run")

    def _attempt(
        self,
        library_call: Callable[[], TransportResult],
        cli_call: Callable[[], TransportResult],
        what: str,
    ) -> TransportResult:
        started = time.monotonic()
        result: Optional[TransportResult] = None
        if self.prefer_library and not self._library_broken:
            try:
                result = library_call()
            except _LibraryUnavailable as exc:
                self._library_broken = str(exc)
                _LOG.info(log.kv("transport.library_unavailable", call=what, reason=str(exc)))
            except Exception as exc:  # noqa: BLE001 - library surface is not fully known
                text = f"{type(exc).__name__}: {exc}"
                if _looks_unreachable(text):
                    result = TransportResult(False, LIBRARY, error=text, unreachable=True)
                else:
                    _LOG.warning(log.kv("transport.library_error", call=what, error=text))
                    result = None
        if result is None or (not result.ok and not result.unreachable):
            cli_result = cli_call()
            # Prefer whichever answer is more informative.
            if result is not None and cli_result.error and not result.error:
                cli_result.error = result.error
            result = cli_result
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
        self.last_via = result.via
        self.last_binding = result.binding or self.last_binding
        level = _LOG.debug if result.ok else _LOG.info
        level(
            log.kv(
                f"transport.{what}",
                ok=result.ok,
                via=result.via,
                binding=result.binding or "-",
                unreachable=result.unreachable,
                ms=result.elapsed_ms,
                error=result.error[:200] if result.error else "-",
            )
        )
        return result

    # -- library path ------------------------------------------------------

    def _lockdown(self) -> Any:
        """Create a lockdown client. Tries usbmux first, then a bare client.

        UNCERTAIN: create_using_usbmux's keyword for the device id has been
        `serial` and `udid` in different releases, so both are tried.
        """
        try:
            from pymobiledevice3.lockdown import create_using_usbmux  # type: ignore
        except ImportError as exc:
            raise _LibraryUnavailable(f"pymobiledevice3 not importable: {exc}") from exc

        errors: List[str] = []
        for kwargs in ({"serial": self.udid}, {"udid": self.udid}, {}):
            if self.udid is None and kwargs:
                continue
            try:
                return create_using_usbmux(**kwargs)  # type: ignore[arg-type]
            except TypeError as exc:
                errors.append(f"{kwargs}: {exc}")
                continue
        raise _LibraryUnavailable("create_using_usbmux signature not recognised: " + "; ".join(errors))

    def _profile_service(self) -> Any:
        """Instantiate the profile service.

        UNCERTAIN: module path and class name. Candidates below are ordered
        newest first. Whichever constructs is recorded in last_binding.
        """
        candidates: Tuple[Tuple[str, str], ...] = (
            ("pymobiledevice3.services.mobile_config", "MobileConfigService"),
            ("pymobiledevice3.services.mobileconfig", "MobileConfigService"),
            ("pymobiledevice3.services.mobile_config", "MCInstallService"),
            ("pymobiledevice3.services.profile", "ProfileService"),
        )
        import importlib

        lockdown = self._lockdown()
        errors: List[str] = []
        for module_name, class_name in candidates:
            try:
                module = importlib.import_module(module_name)
            except ImportError as exc:
                errors.append(f"{module_name}: {exc}")
                continue
            service_cls = getattr(module, class_name, None)
            if service_cls is None:
                errors.append(f"{module_name}.{class_name}: missing")
                continue
            for kwargs in ({"lockdown": lockdown}, {}):
                try:
                    service = service_cls(**kwargs) if kwargs else service_cls(lockdown)
                except TypeError as exc:
                    errors.append(f"{class_name}{tuple(kwargs)}: {exc}")
                    continue
                self.last_binding = f"{module_name}.{class_name}"
                return service
        raise _LibraryUnavailable("no usable profile service: " + "; ".join(errors))

    def _lib_device_info(self) -> TransportResult:
        lockdown = self._lockdown()
        info = getattr(lockdown, "all_values", None) or getattr(lockdown, "short_info", None)
        if callable(info):
            info = info()
        if info is None:
            raise _LibraryUnavailable("lockdown client exposes neither all_values nor short_info")
        return TransportResult(True, LIBRARY, dict(info), binding="lockdown.all_values")

    def _lib_install(self, path: Path, keybag: Optional[Path]) -> TransportResult:
        service = self._profile_service()
        payload = path.read_bytes()

        if keybag is not None:
            result = self._lib_install_silent(service, payload, keybag)
            if result is not None:
                return result
            _LOG.info(log.kv("transport.silent_install_unavailable", fallback="plain_install"))

        for method_name in ("install_profile", "install", "install_profile_silent"):
            method = getattr(service, method_name, None)
            if method is None:
                continue
            method(payload)
            return TransportResult(True, LIBRARY, binding=f"{self.last_binding}.{method_name}")
        raise _LibraryUnavailable("profile service has no install method")

    def _lib_install_silent(
        self, service: Any, payload: bytes, keybag: Path
    ) -> Optional[TransportResult]:
        """Supervised silent install.

        UNCERTAIN, and the single most likely thing to need editing: the keybag
        argument has been seen as a path string, as raw file bytes, and as a
        parsed plist. Argument order has been seen both ways too. Every
        combination is tried and the winner is recorded; a TypeError just moves
        on to the next one. Returns None when no combination applies, so the
        caller can fall back to a plain install.
        """
        method = None
        method_name = ""
        for candidate in ("install_profile_silent", "install_silent", "install_profile"):
            found = getattr(service, candidate, None)
            if found is not None and candidate != "install_profile":
                method, method_name = found, candidate
                break
            if found is not None and candidate == "install_profile":
                # Some releases take the keybag as a keyword on the plain call.
                method, method_name = found, candidate
                break
        if method is None:
            return None

        raw = keybag.read_bytes()
        shapes: List[Tuple[str, Sequence[Any], Dict[str, Any]]] = [
            ("keybag_bytes_first", (raw, payload), {}),
            ("payload_first_keybag_bytes", (payload, raw), {}),
            ("keybag_kwarg_bytes", (payload,), {"keybag": raw}),
            ("keybag_kwarg_path", (payload,), {"keybag": str(keybag)}),
            ("keybag_path_first", (str(keybag), payload), {}),
        ]
        try:
            parsed = plistlib.loads(raw)
            shapes.insert(1, ("keybag_plist_first", (parsed, payload), {}))
        except Exception:  # noqa: BLE001 - keybag may not be a plist at all
            pass

        errors: List[str] = []
        for shape_name, args, kwargs in shapes:
            try:
                method(*args, **kwargs)
            except TypeError as exc:
                errors.append(f"{shape_name}: {exc}")
                continue
            binding = f"{self.last_binding}.{method_name}[{shape_name}]"
            _LOG.info(log.kv("transport.silent_install", binding=binding))
            return TransportResult(True, LIBRARY, binding=binding)
        _LOG.info(log.kv("transport.silent_install_shapes_failed", tried=len(shapes)))
        _LOG.debug(log.kv("transport.silent_install_errors", detail="; ".join(errors)[:400]))
        return None

    def _lib_remove(self, identifier: str) -> TransportResult:
        service = self._profile_service()
        for method_name in ("remove_profile", "remove"):
            method = getattr(service, method_name, None)
            if method is None:
                continue
            if self.keybag is not None and method_name == "remove_profile":
                # UNCERTAIN: supervised removal may need the keybag too.
                try:
                    method(identifier, self.keybag.read_bytes())
                    return TransportResult(
                        True, LIBRARY, binding=f"{self.last_binding}.{method_name}[keybag]"
                    )
                except TypeError:
                    pass
            method(identifier)
            return TransportResult(True, LIBRARY, binding=f"{self.last_binding}.{method_name}")
        raise _LibraryUnavailable("profile service has no remove method")

    def _lib_list(self) -> TransportResult:
        service = self._profile_service()
        for method_name in ("get_profile_list", "get_profiles", "list", "profile_list"):
            method = getattr(service, method_name, None)
            if method is None:
                continue
            raw = method()
            return TransportResult(
                True, LIBRARY, _normalise_profile_list(raw), binding=f"{self.last_binding}.{method_name}"
            )
        raise _LibraryUnavailable("profile service has no list method")

    # -- cli path ----------------------------------------------------------

    def _run(self, argv: List[str], timeout: Optional[int] = None) -> Tuple[int, str, str]:
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout or self.timeout
            )
        except FileNotFoundError as exc:
            return 127, "", str(exc)
        except subprocess.TimeoutExpired:
            return -1, "", f"timed out after {timeout or self.timeout}s"
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def _udid_args(self) -> List[str]:
        return ["--udid", self.udid] if self.udid else []

    def _cli_variants(
        self, variants: Sequence[List[str]], parse: Optional[Callable[[str], Any]] = None
    ) -> TransportResult:
        """Run candidate argv forms until one exits 0. Same trick shiftlab uses:
        a renamed subcommand degrades to a clear failure instead of a crash."""
        last_error = ""
        last_argv: List[str] = []
        unreachable = False
        for argv in variants:
            code, out, err = self._run(argv)
            last_argv, last_error = argv, (err or out)
            if code == 0:
                data = parse(out) if parse else out
                return TransportResult(
                    True, CLI, data, argv=argv, binding=" ".join(argv[2:4]) or "cli"
                )
            if _looks_unreachable(err) or _looks_unreachable(out):
                unreachable = True
                break
        return TransportResult(
            False, CLI, None, last_error[:1000], unreachable=unreachable, argv=last_argv
        )

    def _cli_device_info(self) -> TransportResult:
        return self._cli_variants(
            [
                PMD3_CLI + ["lockdown", "info"] + self._udid_args(),
                PMD3_CLI + self._udid_args() + ["lockdown", "info"],
                PMD3_CLI + ["lockdown", "info"],
            ],
            parse=_parse_structured,
        )

    def _cli_install(self, path: Path, keybag: Optional[Path]) -> TransportResult:
        variants: List[List[str]] = []
        if keybag is not None:
            variants += [
                PMD3_CLI + ["profile", "install", str(path), "--keybag", str(keybag)] + self._udid_args(),
                PMD3_CLI + ["profile", "install", "--keybag", str(keybag), str(path)] + self._udid_args(),
            ]
        variants += [
            PMD3_CLI + ["profile", "install", str(path)] + self._udid_args(),
            PMD3_CLI + ["profile", "install", "--path", str(path)] + self._udid_args(),
        ]
        return self._cli_variants(variants)

    def _cli_remove(self, identifier: str) -> TransportResult:
        variants: List[List[str]] = []
        if self.keybag is not None:
            variants.append(
                PMD3_CLI + ["profile", "remove", identifier, "--keybag", str(self.keybag)]
                + self._udid_args()
            )
        variants += [
            PMD3_CLI + ["profile", "remove", identifier] + self._udid_args(),
            PMD3_CLI + ["profile", "remove", "--identifier", identifier] + self._udid_args(),
        ]
        return self._cli_variants(variants)

    def _cli_list(self) -> TransportResult:
        return self._cli_variants(
            [
                PMD3_CLI + ["profile", "list"] + self._udid_args(),
                PMD3_CLI + self._udid_args() + ["profile", "list"],
                PMD3_CLI + ["profile", "list"],
            ],
            parse=lambda out: _normalise_profile_list(_parse_structured(out)),
        )


class _LibraryUnavailable(Exception):
    """The Python API is not shaped the way this module expects. Use the CLI."""


# ---------------------------------------------------------------------------
# output parsing
# ---------------------------------------------------------------------------

def _parse_structured(text: str) -> Any:
    """CLI output is JSON on current releases, a python repr on older ones.

    Falls back to a key scrape so `doctor` still gets something useful rather
    than nothing.
    """
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        pass
    start = text.find("{")
    if start >= 0:
        try:
            return json.loads(text[start:])
        except ValueError:
            pass
    scraped: Dict[str, Any] = {}
    for key in ("IsSupervised", "ProductVersion", "DeviceName", "UniqueDeviceID", "ProductType"):
        match = re.search(rf"{key}['\"]?\s*[:=]\s*['\"]?([^,'\"\n}}]+)", text)
        if match:
            raw = match.group(1).strip()
            scraped[key] = {"true": True, "false": False, "True": True, "False": False}.get(raw, raw)
    return scraped or {"raw": text}


def _normalise_profile_list(raw: Any) -> List[Dict[str, Any]]:
    """Flatten the several shapes a profile list comes back in.

    Seen: a list of dicts, a dict keyed by identifier, and a dict with an
    OrderedIdentifiers / ProfileMetadata pair.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        metadata = raw.get("ProfileMetadata")
        if isinstance(metadata, dict):
            out: List[Dict[str, Any]] = []
            for identifier, meta in metadata.items():
                entry = dict(meta) if isinstance(meta, dict) else {}
                entry.setdefault("PayloadIdentifier", identifier)
                out.append(entry)
            return out
        if all(isinstance(value, dict) for value in raw.values()) and raw:
            out = []
            for identifier, meta in raw.items():
                entry = dict(meta)
                entry.setdefault("PayloadIdentifier", identifier)
                out.append(entry)
            return out
    return []


def installed_identifiers(profiles_data: Any) -> List[str]:
    ids: List[str] = []
    for entry in _normalise_profile_list(profiles_data):
        identifier = entry.get("PayloadIdentifier") or entry.get("PayloadUUID")
        if isinstance(identifier, str):
            ids.append(identifier)
    return ids
