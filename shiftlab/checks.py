"""The checks themselves.

Phase 1 runs against your phone as it is today. Nothing here erases the
device. Check 03 is the only destructive one and it is gated behind a typed
confirmation.

Phase 2 only makes sense after the device is supervised.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import profiles
from .runner import (
    ARTIFACTS,
    FAIL,
    INCONCLUSIVE,
    PASS,
    PMD3,
    SKIPPED,
    C,
    CheckResult,
    ask_text,
    ask_yes_no,
    confirm_typed,
    device_udid,
    header,
    pause,
    run,
    try_variants,
)

# Apps worth knowing the bundle id of, for the eventual blocklist.
USUAL_SUSPECTS = {
    "com.burbn.instagram": "Instagram",
    "com.zhiliaoapp.musically": "TikTok",
    "com.google.ios.youtube": "YouTube",
    "com.atebits.Tweetie2": "X",
    "com.facebook.Facebook": "Facebook",
    "com.reddit.Reddit": "Reddit",
    "com.toyopagroup.picaboo": "Snapchat",
    "com.hammerandchisel.discord": "Discord",
    "com.linkedin.LinkedIn": "LinkedIn",
    "com.apple.mobilesafari": "Safari",
    "com.google.chrome.ios": "Chrome",
}


# ---------------------------------------------------------------------------
# 01 - transport
# ---------------------------------------------------------------------------

def check_01_transport(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="01",
        title="USB lockdown transport",
        question=(
            "Can pymobiledevice3 still open a lockdown session against a stock, "
            "unsupervised iPhone on current iOS? Everything else depends on this."
        ),
    )
    header(r.id, r.title, r.question)
    print("  Plug the phone in, unlock it, and tap Trust if asked.")
    pause("ready?")

    win, attempts = try_variants(
        [
            PMD3 + ["lockdown", "info"],
            PMD3 + ["usbmux", "list"],
            PMD3 + ["lockdown", "device-list"],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        return r.conclude(
            FAIL,
            "No lockdown command succeeded. Either the device is not paired, "
            "usbmuxd is not running, or the CLI surface moved.",
            "Fix this before anything else. Try `idevice_id -l` to confirm the "
            "device is visible at all, and re-pair by unplugging, replugging "
            "and tapping Trust.",
        )

    ctx["transport_cmd"] = win.argv
    blob = win.stdout
    (ARTIFACTS).mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "device-info.txt").write_text(blob)

    for key in ("ProductVersion", "ProductType", "UniqueDeviceID", "IsSupervised"):
        for line in blob.splitlines():
            if key in line:
                r.observations[key] = line.strip()[:160]
                break

    supervised = "true" in r.observations.get("IsSupervised", "").lower()
    ctx["supervised"] = supervised
    return r.conclude(
        PASS,
        f"Lockdown reachable via `{' '.join(win.argv[2:])}`. "
        f"IsSupervised reported as {supervised}.",
        "Transport works. Device info written to results/artifacts/device-info.txt.",
    )


# ---------------------------------------------------------------------------
# 02 - app inventory
# ---------------------------------------------------------------------------

def check_02_inventory(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="02",
        title="App inventory over installation_proxy",
        question=(
            "Can you enumerate installed user apps and their bundle ids? You need "
            "this list to build any blocklist, and it is the same channel uninstall "
            "runs over."
        ),
    )
    header(r.id, r.title, r.question)

    win, attempts = try_variants(
        [
            # --userspace since the click -> typer migration; --user before that.
            PMD3 + ["apps", "list", "--userspace"],
            PMD3 + ["apps", "list", "--user"],
            PMD3 + ["apps", "list"],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        return r.conclude(
            FAIL,
            "Could not list apps. installation_proxy is unreachable or the "
            "subcommand moved.",
            "Path 01 (uninstall as the blocking primitive) is dead if this does "
            "not work.",
        )

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "apps.json").write_text(win.stdout)

    found = {}
    try:
        data = json.loads(win.stdout)
        keys = list(data.keys()) if isinstance(data, dict) else []
        ctx["bundle_ids"] = keys
        for bid, label in USUAL_SUSPECTS.items():
            if bid in keys:
                found[label] = bid
    except json.JSONDecodeError:
        for bid, label in USUAL_SUSPECTS.items():
            if bid in win.stdout:
                found[label] = bid
        ctx["bundle_ids"] = []

    ctx["found_suspects"] = found
    if found:
        print()
        print(C.bold("  Blocklist candidates present on this device:"))
        for label, bid in found.items():
            print(f"    {label:<12} {C.dim(bid)}")

    return r.conclude(
        PASS,
        f"Listed apps successfully. Matched {len(found)} known blocklist candidates.",
        "Full inventory in results/artifacts/apps.json. These bundle ids are "
        "what go into blockedAppBundleIDs later.",
    )


# ---------------------------------------------------------------------------
# 03 - uninstall round trip  (DESTRUCTIVE)
# ---------------------------------------------------------------------------

def check_03_uninstall(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="03",
        title="Uninstall round trip",
        question=(
            "Does uninstalling a user app over lockdown still work on current iOS? "
            "This is the whole of Path 01, and it is the same-day fallback if "
            "supervision turns out to be more trouble than it is worth."
        ),
    )
    header(r.id, r.title, r.question)

    known = ctx.get("bundle_ids") or []
    suspects = ctx.get("found_suspects") or {}
    if suspects:
        print("  Safe-ish picks from your device (cloud-backed, nothing stored locally):")
        for label in ("LinkedIn", "Chrome"):
            if label in suspects:
                print(f"    {label:<12} {C.dim(suspects[label])}")
        print()

    print(C.yellow("  This deletes an app and its local data. Pick something you"))
    print(C.yellow("  do not care about. Do not pick a messaging app."))
    print(C.yellow("  Use the FULL bundle id, not the app's display name."))
    print()

    target = ask_text("bundle id to uninstall (blank to skip)")
    if not target:
        return r.conclude(SKIPPED, "No target given.")

    # pymobiledevice3 exits 0 on a bundle id that does not exist, so a typo
    # looks exactly like a successful uninstall. Validate first.
    if known and target not in known:
        near = [b for b in known if target.lower() in b.lower()]
        print(C.red(f"  ! {target!r} is not installed on this device."))
        if near:
            print("    did you mean:")
            for b in near[:5]:
                print(f"      {b}")
        return r.conclude(
            SKIPPED,
            f"{target!r} is not in the device inventory, so nothing was attempted.",
            "Rerun with the full bundle id. The uninstall command exits 0 on an "
            "unknown id, which is why this guard exists.",
        )
    if not known:
        print(C.yellow("  ! inventory unavailable, cannot validate the id first"))

    if not confirm_typed(
        "delete",
        f"{target} and its local data will be removed from the phone.",
    ):
        return r.conclude(SKIPPED, "Not confirmed.")

    win, attempts = try_variants(
        [
            PMD3 + ["apps", "uninstall", target],
            PMD3 + ["apps", "uninstall", "--bundle-id", target],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        return r.conclude(
            FAIL,
            "Uninstall command failed. Error text is in the run json.",
            "Path 01 is off the table.",
        )

    # Verify over the wire rather than trusting the exit code or your eyes.
    recheck = r.record(run(PMD3 + ["apps", "list", "--userspace"], echo=False))
    still_there = target in recheck.stdout if recheck.ok else None
    r.observations["present_after_uninstall"] = still_there

    gone_visually = ask_yes_no("Is the icon actually gone from the Home Screen?")
    r.observations["icon_removed"] = gone_visually
    prompted = ask_yes_no("Did the phone show any confirmation prompt?")
    r.observations["phone_prompted"] = prompted

    if still_there is False:
        return r.conclude(
            PASS,
            "App removed over lockdown with no supervision, confirmed by re-listing"
            + (" and with no prompt on the device." if prompted is False else "."),
            "Path 01 is viable as a weekend build. Reinstall from the App Store is "
            "still one tap, so this is friction, not enforcement.",
        )
    if still_there is True:
        return r.conclude(
            FAIL,
            "Command exited 0 but the app is still in the inventory.",
            "Exit code 0 from this command means nothing. Check the bundle id.",
        )
    return r.conclude(INCONCLUSIVE, "Could not re-list apps to verify.")

# ---------------------------------------------------------------------------
# 04 - profile install over lockdown, unsupervised
# ---------------------------------------------------------------------------

def check_04_profile_install(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="04",
        title="Profile install over MCInstall",
        question=(
            "Does a profile pushed over lockdown install silently, or does iOS "
            "park it in Settings and wait for a tap? This decides whether the "
            "daemon can flip a schedule without you touching the phone."
        ),
    )
    header(r.id, r.title, r.question)

    path = profiles.write(
        ARTIFACTS / "marker.mobileconfig", profiles.marker_profile(removal_disallowed=True)
    )
    print(C.dim(f"  wrote {path}"))

    win, attempts = try_variants(
        [
            PMD3 + ["profile", "install", str(path)],
            PMD3 + ["profile", "install", "--path", str(path)],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        return r.conclude(
            FAIL,
            "Profile install over lockdown was rejected outright.",
            "Path 02 needs a different delivery channel. Fall back to hosting "
            "the mobileconfig and installing it by hand, or go to 02b (NanoMDM).",
        )

    print()
    print("  Now look at the phone.")
    tapped = ask_yes_no("Did you have to open Settings and tap Install to accept it?")
    r.observations["required_tap"] = tapped
    visible = ask_yes_no("Is a 'ShiftLab' web clip now on the Home Screen?")
    r.observations["webclip_visible"] = visible
    ctx["marker_installed"] = bool(visible) or win.ok

    if tapped is False:
        return r.conclude(
            PASS,
            "Profile installed silently with no interaction on the device.",
            "Big result. The daemon can swap profiles on a schedule unattended, "
            "even before supervision.",
        )
    if tapped is True:
        return r.conclude(
            PASS,
            "Profile installed, but iOS required manual acceptance on the device.",
            "Expected for unsupervised. Supervision plus a keybag is what buys "
            "silent install, which is check 08. A daemon that needs a tap every "
            "time is not a product.",
        )
    return r.conclude(INCONCLUSIVE, "Install exited 0 but device behavior unrecorded.")


# ---------------------------------------------------------------------------
# 05 - removability
# ---------------------------------------------------------------------------

def check_05_removability(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="05",
        title="PayloadRemovalDisallowed, unsupervised",
        question=(
            "THE question for Path 02. A profile carrying PayloadRemovalDisallowed "
            "is installed. Can you still delete it from Settings? If yes, "
            "supervision is doing the real work and the erase is unavoidable."
        ),
    )
    header(r.id, r.title, r.question)

    ident = profiles.identifier_for("marker")

    def installed() -> bool:
        listing = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
        return ident in listing.stdout

    if not installed():
        path = profiles.write(
            ARTIFACTS / "marker.mobileconfig",
            profiles.marker_profile(removal_disallowed=True),
        )
        r.record(run(PMD3 + ["profile", "install", str(path)]))
        print()
        print(C.yellow("  `profile install` only STAGES the profile on an unsupervised"))
        print(C.yellow("  device. Nothing is installed until you accept it. Do this:"))
        print()
        print("    Settings (root screen) > 'Profile Downloaded' near the top")
        print("    or Settings > General > VPN & Device Management")
        print("    Tap it > Install (top right) > passcode > Install > Install")
        print()
        for attempt in range(3):
            pause("accepted it on the phone?")
            if installed():
                break
            print(C.red("  still not showing over the wire."))
            if attempt < 2:
                print(C.dim("  the banner is easy to miss. Look under both paths above."))
        else:
            return r.conclude(
                INCONCLUSIVE,
                f"{ident} never appeared in `profile list` after three tries.",
                "Either the acceptance sheet was not completed, or staged profiles "
                "expire fast. Rerun and go straight to Settings.",
            )

    print()
    print(C.green(f"  Confirmed over the wire: {ident} is installed."))
    print()
    print("  Now, in Settings > General > VPN & Device Management, open it.")
    pause("looking at 'ShiftLab Marker'?")

    has_button = ask_yes_no("Is there a 'Remove Profile' button?")
    r.observations["remove_button_present"] = has_button

    if has_button is False:
        r.conclude(
            PASS,
            "No Remove Profile button. PayloadRemovalDisallowed honored unsupervised.",
            "Best possible outcome: Path 02 may work with no erase. Verify it "
            "survives a reboot before believing it.",
        )
    else:
        removed = ask_yes_no("Tap it. Did the profile actually come off?")
        r.observations["removed_by_user"] = removed
        passcode = ask_yes_no("Did it demand your device passcode first?")
        r.observations["passcode_required"] = passcode
        if removed:
            r.conclude(
                FAIL,
                "Profile removable from Settings"
                + (" after a passcode prompt." if passcode else " with no challenge."),
                "Confirms the documented behavior: unsupervised, iOS requires "
                "profiles to be removable. Path 02 needs supervision, which means "
                "the backup/erase/supervise/restore cycle.",
            )
        else:
            r.conclude(INCONCLUSIVE, "Remove button present but removal did not complete.")

    # Separate question, and the one your emergency unshift depends on: does an
    # unkeybagged remove from the Mac beat PayloadRemovalDisallowed?
    if installed():
        rm = r.record(run(PMD3 + ["profile", "remove", ident], timeout=60, echo=False))
        beat = rm.ok and not installed()
        r.observations["mac_side_remove_beats_removal_disallowed"] = beat
        print(C.dim(f"  emergency-unshift probe: Mac-side remove worked = {beat}"))
    return r

# ---------------------------------------------------------------------------
# 06 - the supervision gate
# ---------------------------------------------------------------------------

def check_06_supervision_gate(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="06",
        title="blockedAppBundleIDs without supervision",
        question=(
            "Apple documents blockedAppBundleIDs as supervised-only. Confirm it "
            "rather than trust it. If this installs, the entire erase step "
            "disappears and the project becomes trivial."
        ),
    )
    header(r.id, r.title, r.question)

    found = ctx.get("found_suspects") or {}
    default = next(iter(found.values()), "com.burbn.instagram")
    target = ask_text("bundle id to attempt to block", default)

    path = profiles.write(
        ARTIFACTS / "blocked.mobileconfig",
        profiles.blocked_apps_profile([target], removal_disallowed=True),
    )
    print(C.dim(f"  wrote {path}"))

    win, attempts = try_variants(
        [
            PMD3 + ["profile", "install", str(path)],
            PMD3 + ["profile", "install", "--path", str(path)],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        err = "\n".join((attempts[-1].stderr or attempts[-1].stdout).splitlines()[:4])
        r.observations["rejection"] = err[:400]
        return r.conclude(
            PASS,
            "Rejected, as documented. The supervision gate is real.",
            "Path 02 requires supervision. Budget the erase. Save this rejection "
            "text, it is the baseline you compare against after supervising.",
        )

    hidden = ask_yes_no(f"Unexpected: it installed. Did {target} vanish from the Home Screen?")
    r.observations["icon_hidden"] = hidden
    if hidden:
        return r.conclude(
            FAIL,
            "blockedAppBundleIDs took effect on an UNSUPERVISED device.",
            "This contradicts Apple's own schema. Re-verify after a reboot, then "
            "check whether the device is already supervised (check 01 reported "
            f"IsSupervised={ctx.get('supervised')}). If it really works, skip the "
            "erase entirely.",
        )
    return r.conclude(
        INCONCLUSIVE,
        "Profile installed but apps were not hidden.",
        "Accepted and ignored is the common unsupervised behavior for supervised-"
        "only keys. Treat as 'gate is real'.",
    )


# ---------------------------------------------------------------------------
# 07 - wireless control
# ---------------------------------------------------------------------------

def check_07_wireless(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="07",
        title="Control over Wi-Fi after unplugging",
        question=(
            "Shift's pitch is that it works wirelessly after a one-time cable "
            "setup. That is lockdown over Bonjour using the existing pair record. "
            "Does it hold on your network?"
        ),
    )
    header(r.id, r.title, r.question)

    udid = device_udid(ctx)
    r.observations["udid_known"] = bool(udid)
    if not udid:
        print(C.yellow("  ! no cached UDID. Plug in once and run --only 01 first."))
        return r.conclude(SKIPPED, "UDID unknown, cannot select a device non-interactively.")

    print("  Wi-Fi sync is easy to think you enabled and not have. Do this exactly:")
    print("    1. Cable still IN. Finder > sidebar > your iPhone > General tab")
    print("    2. Tick 'Show this iPhone when on Wi-Fi'")
    print("    3. Click Apply, then Sync once. The pair record only gets the")
    print("       Wi-Fi address after a sync completes.")
    print("    4. Same network both ends, no VPN on either, not a guest network")
    print("       and not one with client isolation")
    print("    5. NOW unplug")
    ready = ask_yes_no("All five done?")
    if not ready:
        return r.conclude(SKIPPED, "Not attempted.")

    disc = r.record(run(PMD3 + ["bonjour", "mobdev2"], timeout=60))
    r.observations["discovered_on_network"] = bool(disc.ok and disc.stdout.strip())

    # Bonjour normally turns up the same phone more than once, so --udid is
    # required rather than optional.
    win, attempts = try_variants(
        [
            PMD3 + ["lockdown", "info", "--mobdev2", "--udid", udid],
            PMD3 + ["lockdown", "info", "--udid", udid, "--mobdev2"],
        ],
        timeout=90,
    )
    for a in attempts:
        r.record(a)

    if win:
        return r.conclude(
            PASS,
            f"Wireless lockdown works with --udid {udid[:12]}...",
            "The daemon can run headless and reach the phone whenever you are "
            "home. Always pass --udid; Bonjour returns duplicate candidates and "
            "the CLI cannot prompt from a launchd job.",
        )

    blob = " ".join((a.stderr or a.stdout) for a in attempts).lower()
    if "pair" in blob or "trust" in blob:
        return r.conclude(
            FAIL,
            "Discovered on the network but the TCP session is not paired.",
            "The Bonjour listing showed PAIRED:False. Finder's Wi-Fi tick needs a "
            "completed sync before the pair record carries the Wi-Fi address. "
            "Plug in, sync fully, unplug, retry.",
        )
    if not r.observations["discovered_on_network"]:
        return r.conclude(
            FAIL,
            "Not discoverable over Bonjour, so this is a network problem rather "
            "than a verdict on the approach.",
            "Try a phone hotspot to rule out client isolation on your Wi-Fi.",
        )
    return r.conclude(
        FAIL,
        "Discoverable but no wireless lockdown session.",
        "Not fatal. A launchd agent that acts while the phone charges overnight "
        "still enforces a sleep schedule. You lose midday flips.",
    )

# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cleanup(ctx: dict) -> None:
    print()
    print(C.bold("cleanup"))
    for name in ("marker", "blocked"):
        ident = profiles.identifier_for(name)
        run(PMD3 + ["profile", "remove", ident], timeout=60)
    print(C.dim("  if anything is left over, remove it by hand in"))
    print(C.dim("  Settings > General > VPN & Device Management"))


PHASE1 = [
    check_01_transport,
    check_02_inventory,
    check_03_uninstall,
    check_04_profile_install,
    check_05_removability,
    check_06_supervision_gate,
    check_07_wireless,
]
