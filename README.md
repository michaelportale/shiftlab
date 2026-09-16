# ShiftLab

A self-hosted replacement for Shift (shiftyourphone.com), for one iPhone and
one Mac.

Shift does not use Apple's Screen Time API. It enrolls the phone in supervised
MDM over USB and drives it from a desktop. The useful consequence: with
supervision you do not need an MDM server at all. Apple Configurator gives you
a supervision identity, and `pymobiledevice3` pushes profiles with it straight
from your Mac.

Two packages here. `shiftlab` proves the assumptions. `shiftd` is the thing
that runs.

## Read this before you erase anything

Two findings from the research that are easy to get wrong and expensive to
undo:

1. **Do not restore with Apple Configurator.** Apple's own Configurator docs:
   "If the devices are supervised, they become unsupervised after the restore."
   Route the restore through Finder instead. `docs/SUPERVISION-RUNBOOK.md`
   Phase 6.
2. **The supervision identity decision happens before you hit Prepare, not
   after.** `pymobiledevice3 profile create-keybag` always generates a fresh
   self-signed key and cannot import one, so a keybag it makes will be rejected
   by a phone prepared with a different identity. You either convert
   Configurator's exported `.p12` into a keybag afterwards (the documented-
   nowhere path, recipe in Phase 5) or generate the identity first and import
   it into Configurator before preparing. Pick one while reading, not while
   the phone sits at the Hello screen.

## Order of operations

| Step | What | Where |
| --- | --- | --- |
| 1 | Run phase 1 of the harness | `python -m shiftlab` |
| 2 | Encrypted local backup | runbook Phase 2 |
| 3 | Create the supervision identity and verify the keybag, before erasing | runbook Phase 0.5 |
| 4 | Erase, Prepare with Supervise, export the identity, restore | runbook Phases 3-7 |
| 5 | Run phase 2 of the harness | `python -m shiftlab --phase 2` |
| 6 | Configure and load the daemon | `docs/DAEMON.md` |

Step 1 can change everything. Check 05 asks whether a profile carrying
`PayloadRemovalDisallowed` can still be deleted from Settings on an
unsupervised phone. If it cannot, steps 2 through 4 are unnecessary.

## shiftlab, the verification harness

Interactive. Each check runs a command, then asks what the phone did, because
half the answers only exist on the screen. Nothing in phase 1 is irreversible;
check 03 deletes one app you name and is gated behind typing `delete`.

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m shiftlab
python -m shiftlab --only 05
python -m shiftlab --phase 2
```

Phase 1: transport, app inventory, uninstall round trip, profile install,
**removability**, the supervision gate, wireless control.
Phase 2: keybag silent install, blocked apps actually hidden, removal
resistance.

Output lands in `results/REPORT-<phase>.md` with a verdict and a "so what" per
check, plus a full command transcript in the run json.

## shiftd, the daemon

Holds the schedule, reconciles the phone toward it once a minute under launchd.

```sh
python -m shiftd doctor
python -m shiftd status
python -m shiftd shift social --for 90m --locked
python -m shiftd unshift
python -m shiftd reconcile --dry-run
```

`unshift` refuses while a locked shift is active and tells you when it ends.

Design notes in `docs/DAEMON.md`. The parts worth knowing:

- **Locked shifts cannot be ended early, including from the Mac.** That is the
  commitment device. Countdowns run off a monotonic budget so changing the
  system clock does not end one.
- **Reconcile is idempotent** and re-asserts the profile when the phone comes
  back, so unplugging is not a bypass.
- **Phone unreachable is a normal condition**, not an error that kills the
  daemon.
- `transport.py` is the only module that touches the phone. Library first, CLI
  fallback.

50 tests, transport mocked, no phone needed: `python3 -m unittest discover -s tests`.

## Docs

| File | What |
| --- | --- |
| `docs/SUPERVISION-RUNBOOK.md` | Backup, erase, supervise, export identity, restore. Every step with expected result and failure note. |
| `docs/DAEMON.md` | State machine, idempotency argument, failure modes, launchctl. |
| `docs/BUNDLE-IDS.md` | Verified bundle ids for the blocklist, with the non-guessable ones flagged. |
| `docs/RECOVERY.md` | When it goes wrong. Emergency unshift, dead Mac, lost identity, profile stacking. |

## The one real risk

There is exactly one off switch and it is the Mac. The profile lives on the
phone, has no expiry unless configured, and resists removal from Settings by
design. A Mac that dies or goes to a repair shop leaves the phone shifted with
no cloud, no MDM server and no account recovery. The obvious safety net,
`DurationUntilRemoval`, has credible reports of never firing and is unverified
here.

Two mitigations, both of which must exist **before** the first lockout because
neither can be added afterwards without erasing the phone:

- Export the supervision identity `.p12` to a password manager and a second
  machine.
- Add a `com.apple.profileRemovalPassword` payload and store that password
  behind real friction.

`docs/RECOVERY.md` has the pre-commitment checklist.
