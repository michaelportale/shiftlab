"""Build a restoration checklist from the phone, before you erase it.

Reads the installed-app list over lockdown and writes:

  docs/RESTORE-INVENTORY.md          tick-through checklist, priority ordered
  results/artifacts/restore-inventory.csv   same data for a spreadsheet

The useful trick: each app's Info.plist says whether it uses push
notifications (UIBackgroundModes contains remote-notification, or the
aps-environment entitlement). So "which apps will silently stop notifying me"
is answerable from data instead of memory.

    python tools/inventory.py              # read the phone
    python tools/inventory.py --from results/artifacts/apps.json
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ARTIFACTS = ROOT / "results" / "artifacts"

# Apps where erasing costs you something a reinstall does not give back.
# Handle these BEFORE the wipe.
CRITICAL = {
    "com.google.Authenticator": "TOTP seeds are destroyed. Export accounts first.",
    "com.authy.Authy": "Confirm multi-device is enabled before erasing.",
    "com.microsoft.azureauthenticator": "Back up in-app before erasing.",
    "com.duosecurity.DuoMobile": "Duo needs re-activation from each provider.",
    "org.whispersystems.signal": "History does not restore from any backup. It is gone.",
    "net.whatsapp.WhatsApp": "Has its own iCloud backup, OFF by default. Run it manually.",
    "ph.telegra.Telegraph": "Cloud chats restore. Secret chats do not.",
    "com.apple.Passbook": "Wallet cards must be re-added. Transit cards need care.",
}
CRITICAL_KEYWORDS = {
    "authenticator": "TOTP seeds may be destroyed. Check for an export or cloud sync.",
    "2fa": "TOTP seeds may be destroyed. Check for an export or cloud sync.",
    "otp": "TOTP seeds may be destroyed. Check for an export or cloud sync.",
}

# Rough signal for "you will have to prove who you are again, and it is a faff".
HIGH_FRICTION = (
    "bank", "chase", "wells", "fidelity", "schwab", "vanguard", "robinhood",
    "coinbase", "venmo", "paypal", "cash", "amex", "capital one", "discover",
    "irs", "insurance", "health", "aetna", "cigna", "united", "delta",
    "american airlines", "gov", "id.me",
)


def load_apps(source: str | None) -> dict:
    if source:
        return json.loads(Path(source).read_text())
    out = subprocess.run(
        [sys.executable, "-m", "pymobiledevice3", "apps", "list", "--userspace"],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        sys.exit(f"could not read apps from the device:\n{out.stderr[:400]}")
    return json.loads(out.stdout)


def uses_push(info: dict) -> bool:
    modes = info.get("UIBackgroundModes") or []
    if "remote-notification" in modes:
        return True
    ent = info.get("Entitlements") or {}
    return "aps-environment" in ent


def classify(name: str, bundle_id: str, info: dict) -> tuple[str, str]:
    lower = name.lower()
    if bundle_id in CRITICAL:
        return "critical", CRITICAL[bundle_id]
    for kw, note in CRITICAL_KEYWORDS.items():
        if kw in lower:
            return "critical", note
    for kw in HIGH_FRICTION:
        if kw in lower:
            return "high-friction", "Identity verification likely. Budget time."
    return "normal", ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="source", help="read a saved apps.json instead of the device")
    args = ap.parse_args()

    raw = load_apps(args.source)
    rows = []
    for bundle_id, info in raw.items():
        if info.get("ApplicationType") != "User":
            continue
        name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle_id
        tier, note = classify(name, bundle_id, info)
        rows.append({
            "name": name,
            "bundle_id": bundle_id,
            "version": info.get("CFBundleShortVersionString", ""),
            "push": "yes" if uses_push(info) else "",
            "tier": tier,
            "note": note,
        })
    rows.sort(key=lambda r: r["name"].lower())

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path = ARTIFACTS / "restore-inventory.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "bundle_id", "version", "push", "tier", "note",
                                          "installed", "logged_in", "notifications"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "installed": "", "logged_in": "", "notifications": ""})

    critical = [r for r in rows if r["tier"] == "critical"]
    friction = [r for r in rows if r["tier"] == "high-friction"]
    push = [r for r in rows if r["push"] and r["tier"] == "normal"]
    quiet = [r for r in rows if not r["push"] and r["tier"] == "normal"]

    def table(items, with_note=False, mark_push=False):
        head = "| | App | Bundle id |" + (" Push |" if mark_push else "") + (" Why |" if with_note else "")
        sep = "| --- | --- | --- |" + (" --- |" if mark_push else "") + (" --- |" if with_note else "")
        lines = [head, sep]
        for r in items:
            row = f"| [ ] | {r['name']} | `{r['bundle_id']}` |"
            if mark_push:
                row += f" {'push' if r['push'] else ''} |"
            if with_note:
                row += f" {r['note']} |"
            lines.append(row)
        return "\n".join(lines)

    table_all = table(sorted(push + quiet, key=lambda r: r["name"].lower()), mark_push=True)

    md = f"""# Restore inventory

Generated from the phone before erasing. {len(rows)} user apps.

Tick as you go. The CSV next to this
(`results/artifacts/restore-inventory.csv`) has the same data with blank
`installed` / `logged_in` / `notifications` columns if you would rather work in
a spreadsheet.

## 1. Handle BEFORE you erase ({len(critical)})

These lose something a reinstall does not give back.

{table(critical, with_note=True) if critical else "_none detected, but read the list in docs/FRESH-SETUP-CHECKLIST.md anyway_"}

## 2. High friction to get back into ({len(friction)})

Identity verification, card re-adds, support calls. Do these when you have
patience, not at 1am.

{table(friction, with_note=True) if friction else "_none detected_"}

## 3. Everything else, alphabetical ({len(push) + len(quiet)})

`push` marks apps whose Info.plist declares push notifications. Note that is
**capability, not permission**: most apps declare it whether or not you ever
said yes. On this phone {len(push)} of {len(rows)} declare it, so the flag is a
weak signal and the Settings > Notifications screenshot below is the real ground
truth for what was actually notifying you.

Still worth knowing per app, because after a reinstall iOS asks once on first
launch. Dismiss that prompt and the app goes silent permanently until you dig
through Settings to fix it.

{table_all}

## Manual captures worth taking before the erase

The app list is data. These are not, and screenshots take two minutes.

- [ ] **Every Home Screen page.** This is your layout, and nothing restores it.
- [ ] **Settings > Notifications.** Shows every app and its current state. This
      is the ground truth for rebuilding your notification setup.
- [ ] **Settings > Focus**, and each Focus's allowed apps and people.
- [ ] **Settings > [your name] > Subscriptions.** What you pay for and when.
- [ ] **Wallet.** Which cards and passes, so you know what to re-add.
- [ ] **Settings > General > VPN & Device Management**, if anything lives there.
- [ ] **Settings > Apps > Default Apps**, browser and mail defaults.
- [ ] **Control Center layout.**
- [ ] **Settings > Privacy & Security > Location Services**, the per-app states.

AirDrop the screenshots to the Mac before erasing, not to iCloud Photos, so they
are readable while the phone is mid-setup.
"""
    DOCS.mkdir(exist_ok=True)
    (DOCS / "RESTORE-INVENTORY.md").write_text(md)

    print(f"  {len(rows)} user apps")
    print(f"  {len(critical)} critical, {len(friction)} high-friction, {len(push)} use push")
    print(f"\n  docs/RESTORE-INVENTORY.md")
    print(f"  {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
