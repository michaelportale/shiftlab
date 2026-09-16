"""Build the .mobileconfig that hides apps.

Same shape as shiftlab/profiles.py, with one difference that matters for a
daemon rather than a harness: every identifier and UUID is derived
deterministically from the blocklist name. iOS replaces a profile when the
incoming PayloadIdentifier matches an installed one, so a stable identifier
means "install" is an upsert. A random UUID per build would stack duplicate
profiles in Settings every reconcile.

The bundle list can change between builds while the identifier stays put. A
short content hash rides along in PayloadDescription and in a private key so
`shiftd status` can tell "installed profile matches config" from "installed
profile is stale" without re-reading the payload off the phone.
"""
from __future__ import annotations

import hashlib
import plistlib
import uuid
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

BASE_ID = "com.shiftd"

# Fixed namespace so uuid5 output is stable across machines and runs.
_NS = uuid.UUID("6f5e6b2e-9f37-5f61-9d6c-7f2a1c0b4d11")


def identifier_for(blocklist: str) -> str:
    """Top level PayloadIdentifier for a blocklist. Stable by design."""
    return f"{BASE_ID}.block.{blocklist}"


def payload_identifier_for(blocklist: str) -> str:
    return f"{identifier_for(blocklist)}.restrictions"


def _uuid_for(identifier: str) -> str:
    return str(uuid.uuid5(_NS, identifier)).upper()


def content_hash(bundle_ids: Iterable[str]) -> str:
    """Short digest of the blocked set. Order independent."""
    joined = "\n".join(sorted(set(bundle_ids)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def build(
    blocklist: str,
    bundle_ids: Sequence[str],
    *,
    removal_disallowed: bool = True,
    organization: str = "shiftd",
    display_name: Optional[str] = None,
) -> Tuple[bytes, str]:
    """Return (plist bytes, content hash) for one blocklist."""
    if not bundle_ids:
        raise ValueError(f"blocklist {blocklist!r} is empty, refusing to build an empty block")
    ordered: List[str] = sorted(set(bundle_ids))
    digest = content_hash(ordered)
    top_id = identifier_for(blocklist)
    payload_id = payload_identifier_for(blocklist)

    payload = {
        "PayloadType": "com.apple.applicationaccess",
        "PayloadVersion": 1,
        "PayloadIdentifier": payload_id,
        "PayloadUUID": _uuid_for(payload_id),
        "PayloadDisplayName": display_name or f"shiftd {blocklist}",
        # Supervised devices only. Unsupervised, iOS rejects the payload, which
        # is check 06 in the harness.
        "blockedAppBundleIDs": ordered,
    }
    doc = {
        "PayloadType": "Configuration",
        "PayloadVersion": 1,
        "PayloadIdentifier": top_id,
        "PayloadUUID": _uuid_for(top_id),
        "PayloadDisplayName": display_name or f"shiftd: {blocklist}",
        "PayloadDescription": f"{len(ordered)} apps hidden by shiftd. content={digest}",
        "PayloadOrganization": organization,
        "PayloadScope": "System",
        "PayloadRemovalDisallowed": bool(removal_disallowed),
        # Private key, ignored by iOS, read back by `profile list` for drift checks.
        "ShiftdContentHash": digest,
        "PayloadContent": [payload],
    }
    return plistlib.dumps(doc), digest


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def build_to(
    directory: Path,
    blocklist: str,
    bundle_ids: Sequence[str],
    *,
    removal_disallowed: bool = True,
    organization: str = "shiftd",
) -> Tuple[Path, str]:
    """Build and write. Filename is stable so the directory does not grow."""
    data, digest = build(
        blocklist,
        bundle_ids,
        removal_disallowed=removal_disallowed,
        organization=organization,
    )
    path = write(directory / f"{blocklist}.mobileconfig", data)
    return path, digest


def parse_hash(profile_dict: dict) -> Optional[str]:
    """Pull the content hash back out of a profile dict from the device."""
    value = profile_dict.get("ShiftdContentHash")
    if isinstance(value, str):
        return value
    description = profile_dict.get("PayloadDescription", "")
    if isinstance(description, str) and "content=" in description:
        return description.rsplit("content=", 1)[1].strip() or None
    return None
