"""Generate the .mobileconfig files the checks install.

Two profiles matter:

  marker      Harmless. A single web clip, plus PayloadRemovalDisallowed.
              Used to answer: does a lockdown-installed profile need a tap on
              the phone, and can it be removed from Settings anyway?

  blocked     A com.apple.applicationaccess payload carrying
              blockedAppBundleIDs. Expected to be REJECTED on an unsupervised
              device. If it installs, the supervision gate is not what the
              documentation says it is, and the whole erase step goes away.
"""
from __future__ import annotations

import plistlib
import uuid
from pathlib import Path

BASE_ID = "com.shiftlab"


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def _wrap(
    *,
    name: str,
    display_name: str,
    description: str,
    payloads: list,
    removal_disallowed: bool,
) -> bytes:
    doc = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{BASE_ID}.{name}",
        "PayloadUUID": _uuid(),
        "PayloadDisplayName": display_name,
        "PayloadDescription": description,
        "PayloadOrganization": "ShiftLab",
        "PayloadScope": "System",
        "PayloadRemovalDisallowed": bool(removal_disallowed),
        "PayloadContent": payloads,
    }
    return plistlib.dumps(doc)


def marker_profile(removal_disallowed: bool = True) -> bytes:
    payload = {
        "PayloadType": "com.apple.webClip.managed",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{BASE_ID}.marker.webclip",
        "PayloadUUID": _uuid(),
        "PayloadDisplayName": "ShiftLab Marker",
        "URL": "https://example.com/shiftlab",
        "Label": "ShiftLab",
        "IsRemovable": False,
        "FullScreen": False,
    }
    return _wrap(
        name="marker",
        display_name="ShiftLab Marker",
        description=(
            "Harmless test profile. Adds one web clip so you can see at a "
            "glance whether it installed. Delete it when the check is done."
        ),
        payloads=[payload],
        removal_disallowed=removal_disallowed,
    )


def blocked_apps_profile(bundle_ids: list, removal_disallowed: bool = True) -> bytes:
    payload = {
        "PayloadType": "com.apple.applicationaccess",
        "PayloadVersion": 1,
        "PayloadIdentifier": f"{BASE_ID}.blocked.restrictions",
        "PayloadUUID": _uuid(),
        "PayloadDisplayName": "ShiftLab App Block",
        "blockedAppBundleIDs": list(bundle_ids),
    }
    return _wrap(
        name="blocked",
        display_name="ShiftLab App Block",
        description="Hides the listed apps. Supervised devices only.",
        payloads=[payload],
        removal_disallowed=removal_disallowed,
    )


def identifier_for(name: str) -> str:
    return f"{BASE_ID}.{name}"


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
