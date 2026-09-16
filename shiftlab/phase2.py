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

    keybag = ask_text("path to your supervision keybag (blank to skip)")
    if not keybag or not Path(keybag).expanduser().exists():
        return r.conclude(SKIPPED, "No keybag provided.")
    ctx["keybag"] = str(Path(keybag).expanduser())

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

    args = PMD3 + ["profile", "install", str(path)]
    if ctx.get("keybag"):
        args += ["--keybag", ctx["keybag"]]
    r.record(run(args))

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
        title="Removal resistance under supervision",
        question=(
            "The commitment device only works if you cannot undo it from the "
            "phone at 2am. Confirm the profile is genuinely stuck."
        ),
    )
    header(r.id, r.title, r.question)

    print("  On the phone: Settings > General > VPN & Device Management")
    pause("open it")

    has_button = ask_yes_no("Is there a Remove Profile button?")
    r.observations["remove_button_present"] = has_button
    if has_button:
        removed = ask_yes_no("Did it actually remove?")
        r.observations["removed_by_user"] = removed
        if removed:
            return r.conclude(
                FAIL,
                "Still removable from the phone even when supervised.",
                "You need an MDM enrollment for real non-removability. Path 02b.",
            )
        return r.conclude(INCONCLUSIVE, "Button present, removal failed.")

    reset = ask_yes_no(
        "Settings > General > Transfer or Reset iPhone: is Erase All Content greyed out?"
    )
    r.observations["erase_blocked"] = reset
    return r.conclude(
        PASS,
        "No removal path from the phone"
        + (", and factory reset is blocked too." if reset else "."),
        "Enforcement confirmed. The only off switch is your Mac, which is the "
        "entire point.",
    )


PHASE2 = [check_08_keybag_silent, check_09_blocked_apps, check_10_locked_down]
