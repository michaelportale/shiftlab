"""Checks that only make sense once the device is supervised.

Run these after the backup / erase / Prepare-with-Supervise / restore cycle,
with the supervision identity exported from Apple Configurator.
"""
from __future__ import annotations

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
    header,
    pause,
    run,
    try_variants,
)


KEYBAG_CACHE = ARTIFACTS / "keybag-path.txt"


def resolve_keybag(ctx: dict) -> str:
    """Keybag path, cached to disk so any --only run can find it.

    Only the path is cached, never the key material. Without this, running a
    single phase 2 check starts with an empty ctx and silently falls back to a
    non-silent install, which tests nothing.
    """
    if ctx.get("keybag"):
        return ctx["keybag"]
    if KEYBAG_CACHE.exists():
        cached = KEYBAG_CACHE.read_text().strip()
        if cached and Path(cached).exists():
            ctx["keybag"] = cached
            print(C.dim(f"  using keybag {cached}"))
            return cached
    raw = ask_text("path to your supervision keybag", "~/.shiftd/keybag.pem")
    path = Path(raw).expanduser()
    if not path.exists():
        print(C.red(f"  ! {path} does not exist"))
        return ""
    ctx["keybag"] = str(path)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    KEYBAG_CACHE.write_text(str(path) + "\n")
    return str(path)


def check_08_keybag_silent(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="08",
        title="Silent install with the supervision keybag",
        question=(
            "With a supervision identity in hand, does `profile install --keybag` "
            "land a profile with no tap on the phone? This is the single feature "
            "that makes the daemon usable."
        ),
    )
    header(r.id, r.title, r.question)

    keybag = resolve_keybag(ctx)
    if not keybag:
        return r.conclude(SKIPPED, "No usable keybag provided.")

    path = profiles.write(
        ARTIFACTS / "marker.mobileconfig", profiles.marker_profile(removal_disallowed=True)
    )

    win, attempts = try_variants(
        [
            PMD3 + ["profile", "install", str(path), "--keybag", ctx["keybag"]],
            PMD3 + ["profile", "install", "--keybag", ctx["keybag"], str(path)],
        ]
    )
    for a in attempts:
        r.record(a)

    if not win:
        return r.conclude(
            FAIL,
            "Keybag install failed. Error text in the run json.",
            "Check the keybag was exported for THIS supervision identity. If it "
            "is right and this still fails, Path 02b (NanoMDM) is the way to get "
            "unattended delivery.",
        )

    tapped = ask_yes_no("Did the phone ask you to accept anything?")
    r.observations["required_tap"] = tapped
    ctx["marker_installed"] = True

    if tapped is False:
        return r.conclude(
            PASS,
            "Silent install confirmed.",
            "Path 02 is fully viable with no MDM server. Build the daemon.",
        )
    return r.conclude(
        INCONCLUSIVE,
        "Install worked but still prompted.",
        "Something about the supervision identity is not being accepted. Compare "
        "against `cfgutil` doing the same install.",
    )


def check_09_blocked_apps(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="09",
        title="blockedAppBundleIDs under supervision",
        question=(
            "Do the icons actually disappear, and can the app still be reached "
            "some other way? URL schemes have historically been an escape hatch."
        ),
    )
    header(r.id, r.title, r.question)

    target = ask_text("bundle id to block", "com.burbn.instagram")
    path = profiles.write(
        ARTIFACTS / "blocked.mobileconfig",
        profiles.blocked_apps_profile([target], removal_disallowed=True),
    )

    keybag = resolve_keybag(ctx)
    if not keybag:
        return r.conclude(SKIPPED, "No keybag, so this would test a staged install.")
    r.record(run(PMD3 + ["profile", "install", str(path), "--keybag", keybag]))

    listing = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    landed = profiles.identifier_for("blocked") in listing.stdout
    r.observations["profile_on_device"] = landed
    if not landed:
        return r.conclude(
            FAIL,
            "Profile is not in `profile list`, so nothing was tested.",
            "The silent install did not land. Re-check the keybag.",
        )
    print(C.green("  profile confirmed on device"))

    hidden = ask_yes_no(f"Is {target} gone from the Home Screen?")
    r.observations["icon_hidden"] = hidden
    spotlight = ask_yes_no("Can you still launch it from Spotlight search?")
    r.observations["spotlight_launch"] = spotlight
    print()
    print(C.dim("  Now open Notes and tap a link with the app's URL scheme,"))
    print(C.dim("  e.g. instagram://app, to test the classic escape hatch."))
    scheme = ask_yes_no("Did the URL scheme launch it?")
    r.observations["url_scheme_launch"] = scheme

    if hidden and not spotlight and not scheme:
        return r.conclude(
            PASS,
            "Fully hidden, no launch path found.",
            "This is the behavior Shift sells. You now have it.",
        )
    if hidden:
        return r.conclude(
            INCONCLUSIVE,
            "Icon hidden but a launch path survives "
            f"(spotlight={spotlight}, url_scheme={scheme}).",
            "Close it by also blocking the scheme's handler, or accept it as "
            "friction. Worth knowing Shift may have the same hole.",
        )
    return r.conclude(FAIL, "Icons did not disappear under supervision.", "Re-check IsSupervised.")


def check_10_locked_down(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="10",
        title="Removal resistance of a silently installed profile",
        question=(
            "The commitment device only works if you cannot undo it from the "
            "phone at 2am. Does a profile installed silently with the keybag "
            "resist removal from Settings?"
        ),
    )
    header(r.id, r.title, r.question)

    keybag = resolve_keybag(ctx)
    if not keybag:
        return r.conclude(SKIPPED, "No keybag.")

    ident = profiles.identifier_for("marker")

    # iOS lists staged-but-unaccepted profiles as "Downloaded Profile" and they
    # are always deletable, because they were never installed. Testing one of
    # those tells you nothing. Clear the decks, then install ours silently.
    print(C.yellow("  On the phone first: Settings > General > VPN & Device Management."))
    print(C.yellow("  Delete anything listed as a DOWNLOADED PROFILE. Those are"))
    print(C.yellow("  staged leftovers and they are removable by design."))
    pause("cleared?")

    r.record(run(PMD3 + ["profile", "remove", ident], echo=False))
    path = profiles.write(
        ARTIFACTS / "marker.mobileconfig",
        profiles.marker_profile(removal_disallowed=True),
    )
    r.record(run(PMD3 + ["profile", "install", str(path), "--keybag", keybag]))

    listing = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    if ident not in listing.stdout:
        return r.conclude(
            FAIL, f"{ident} did not land, so nothing was tested.",
            "Re-run check 08.",
        )
    print(C.green(f"  {ident} confirmed installed silently"))

    print()
    print("  Settings > General > VPN & Device Management. Find the entry named")
    print("  'ShiftLab Marker' under CONFIGURATION PROFILE, not under")
    print("  DOWNLOADED PROFILE. Those are different things.")
    pause("looking at the right one?")

    has_button = ask_yes_no("Does 'ShiftLab Marker' have a Remove Profile button?")
    r.observations["remove_button_present"] = has_button

    removed = None
    if has_button:
        removed = ask_yes_no("Tap it. Did it actually remove?")
        r.observations["removed_by_user"] = removed

    after = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    still_there = ident in after.stdout
    r.observations["still_on_device_after"] = still_there

    reset = ask_yes_no(
        "Settings > General > Transfer or Reset iPhone: is Erase All Content greyed out?"
    )
    r.observations["erase_blocked"] = reset

    # the emergency exit, proven and then used as cleanup
    rm = r.record(run(PMD3 + ["profile", "remove", ident], echo=False))
    final = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    mac_exit = rm.ok and ident not in final.stdout
    r.observations["mac_side_keybag_remove_works"] = mac_exit
    print(C.dim(f"  emergency exit: Mac-side keybag remove worked = {mac_exit}"))

    if still_there and not removed:
        return r.conclude(
            PASS,
            "Silently installed profile survives the Settings UI"
            + (" (no Remove button)." if not has_button else " (Remove did nothing)."),
            "Supervision plus silent install is sufficient on its own. You do not "
            "need allowUIConfigurationProfileInstallation. Mac-side keybag remove "
            f"is your exit and it works = {mac_exit}.",
        )
    return r.conclude(
        FAIL,
        "Removed from Settings despite supervision and PayloadRemovalDisallowed.",
        "Run check 11: adding allowUIConfigurationProfileInstallation=false is "
        "the next lever before considering an MDM enrollment.",
    )


def check_11_ui_lockdown(ctx: dict) -> CheckResult:
    r = CheckResult(
        id="11",
        title="Removal resistance with the profile UI locked",
        question=(
            "Check 10 showed that supervision plus PayloadRemovalDisallowed is "
            "not enough on its own. Does adding "
            "allowUIConfigurationProfileInstallation=false actually close the "
            "Settings escape hatch?"
        ),
    )
    header(r.id, r.title, r.question)

    keybag = resolve_keybag(ctx)
    if not keybag:
        return r.conclude(SKIPPED, "No keybag.")

    target = ask_text("bundle id to block while we test this", "com.apple.podcasts")
    path = profiles.write(
        ARTIFACTS / "enforce.mobileconfig",
        profiles.enforce_profile([target], lock_profile_ui=True),
    )
    ident = profiles.identifier_for("enforce")

    print()
    print(C.yellow("  Heads up: this profile locks the Settings profile UI."))
    print(C.yellow("  Your way out is from this Mac, with:"))
    print(C.yellow(f"    pymobiledevice3 profile remove {ident}"))
    if not ask_yes_no("Understood, install it?"):
        return r.conclude(SKIPPED, "Not installed.")

    r.record(run(PMD3 + ["profile", "install", str(path), "--keybag", keybag]))
    listing = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    if ident not in listing.stdout:
        return r.conclude(FAIL, "Profile did not land.", "Nothing was tested.")
    print(C.green("  profile confirmed on device"))

    hidden = ask_yes_no(f"Is {target} gone from the Home Screen?")
    r.observations["icon_hidden"] = hidden
    spotlight = ask_yes_no("Can you still launch it from Spotlight?")
    r.observations["spotlight_launch"] = spotlight

    print()
    print("  Settings > General > VPN & Device Management")
    pause("looking?")
    listed = ask_yes_no("Is the profile even listed?")
    r.observations["listed_in_settings"] = listed
    has_button = ask_yes_no("Is there a Remove Profile button?") if listed else False
    r.observations["remove_button_present"] = has_button
    removed = ask_yes_no("If there is one, tap it. Did it remove?") if has_button else False
    r.observations["removed_by_user"] = removed

    after = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    still_there = ident in after.stdout
    r.observations["still_on_device"] = still_there

    # Always prove the Mac-side exit works before leaving the phone locked.
    rm = r.record(run(PMD3 + ["profile", "remove", ident], echo=False))
    final = r.record(run(PMD3 + ["profile", "list"], timeout=60, echo=False))
    mac_exit = rm.ok and ident not in final.stdout
    r.observations["mac_side_remove_works"] = mac_exit
    print(C.dim(f"  cleanup: Mac-side keybag remove worked = {mac_exit}"))
    if not mac_exit:
        print(C.red("  ! the profile is still installed. Remove it before you walk away:"))
        print(C.red(f"    pymobiledevice3 profile remove {ident}"))

    if hidden and not removed:
        return r.conclude(
            PASS,
            "Apps hidden, and the profile could not be removed from Settings"
            + ("." if listed else " because it is not even listed there."),
            "This is the enforcement configuration. Ship the daemon with "
            "allowUIConfigurationProfileInstallation=false in the blocking "
            f"profile, and keep the Mac-side keybag remove as the only exit "
            f"(verified working = {mac_exit}).",
        )
    if not hidden:
        return r.conclude(
            FAIL,
            "Profile landed but the app did not disappear.",
            "Check the bundle id. Settings and Phone can never be blocked.",
        )
    return r.conclude(
        FAIL,
        "Still removable from Settings even with the profile UI locked.",
        "Supervision alone cannot make a profile stick. You need an MDM "
        "enrollment (Path 02b) or a com.apple.profileRemovalPassword payload.",
    )


PHASE2 = [check_08_keybag_silent, check_09_blocked_apps, check_10_locked_down, check_11_ui_lockdown]
