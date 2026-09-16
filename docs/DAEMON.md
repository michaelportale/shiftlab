# shiftd

The daemon ShiftLab feeds into. It keeps one `com.apple.applicationaccess`
profile on the phone whenever a rule says apps should be hidden, and takes it
off when no rule does. It is driven by launchd, one pass a minute, and it holds
no long running process.

```
cli        argument parsing, human output
engine     decides the desired state, reconciles toward it
state      what is shifted, on disk, restart safe
profiles   builds the .mobileconfig
transport  the only module that talks to the phone
config     TOML, validated hard at load
```

No network calls, no server, no cloud. The phone is reached over USB lockdown
or Wi-Fi lockdown with the existing pair record, both local.

## State machine

There are two states and the transitions between them.

```
                start / schedule window opens
        IDLE  ----------------------------------->  SHIFTED
          ^                                          |  |
          |  budget exhausted (expired)              |  |
          +------------------------------------------+  |
          |                                             |
          |  unshift, only when unlocked                |
          +---------------------------------------------+
```

`SHIFTED` carries: blocklist, the rule that started it, `locked`, and
`remaining_s`, a budget in seconds. It also carries what the device looks like:
`applied`, `apply_attempts`, `last_apply_error`, `last_seen_on_device_at`.
Those are device facts, not lifecycle, and they never affect whether the shift
is over.

Transitions:

| From | Event | To | Notes |
| --- | --- | --- | --- |
| IDLE | schedule window covers now | SHIFTED | budget = seconds left in the window |
| IDLE | `shiftd shift <name> --for 90m` | SHIFTED | `--locked` requires `--for` |
| SHIFTED | budget reaches 0 | IDLE | the only way a locked shift ends |
| SHIFTED | `shiftd unshift`, unlocked | IDLE | refused while locked |
| SHIFTED | `shiftd shift`, unlocked | SHIFTED | the old shift is superseded |

One shift at a time. Overlapping schedule windows resolve by precedence:
locked first, then whichever runs longest.

## Why reconcile is idempotent

`shiftd reconcile` runs every 60 seconds forever. Three properties keep that
from doing damage:

1. **Stable identity.** `PayloadIdentifier` is derived from the blocklist name
   and never changes, so iOS treats a second install as a replacement, not an
   addition. Random UUIDs per build would stack a new profile in Settings every
   minute.
2. **Compare before write.** Every pass lists the profiles on the device. A
   write happens only when the target profile is missing, its content hash does
   not match the config, or the last apply is unconfirmed. Steady state does
   zero writes.
3. **Derived, not remembered.** Desired state is a function of config, state
   and the clock. Nothing depends on what the previous pass did, so a skipped
   pass, a crash mid pass, or two passes in the same second all converge to the
   same place.

A consequence worth naming: a profile deleted out of band is reinstalled on the
next pass. Unplugging the phone delays enforcement, it does not end it.

## The locked shift guarantee

While a shift is locked and its budget is above zero:

* `shiftd unshift` refuses and prints when it ends
* `shiftd shift <other>` refuses
* deleting the rule from the config does not release it
* moving the Mac clock forward does not release it
* rebooting the Mac does not release it, the state file is on disk
* the phone cannot release it, `PayloadRemovalDisallowed` plus supervision

The budget is counted against the monotonic clock
(`clock_gettime(CLOCK_MONOTONIC)`, which on macOS keeps counting through sleep
and ignores `date`), not against a wall clock deadline. A jump between the two
clocks larger than `clock_jump_tolerance_s` is logged as `clock.jump` and the
monotonic figure is used. Setting the clock forward six hours during a locked
22:30 to 07:00 block credits the 60 seconds that really passed.

Across a reboot the monotonic clock resets, so the wall clock is the only
measure left. It is clamped to non-negative, so a backwards clock cannot hand
back time already served. This is the one place a determined operator gets
leverage: reboot, set the clock forward, and the next tick credits the gap.

### Honest limits

This is a commitment device, not a prison.

* He owns the Mac, the config, the state file and the keybag. `rm state.json`
  plus one profile removal ends any lock in under a minute.
* Nothing here is tamper evident beyond the history log, which lives in the
  same file it would be tampered with.
* Enforcement stops at the edge of reachability. If the phone is off the
  network for the whole window, the profile was installed before the window
  started or it was not installed at all.
* The value is the friction and the record, not impossibility. The 2am version
  of you has to open a terminal, remember the paths, and see the history entry
  in the morning.

If that is not enough, the next step up is a real MDM enrollment
(Path 02b, NanoMDM) where removal requires the server, not the laptop.

## Failure modes

| Failure | What happens | What to do |
| --- | --- | --- |
| Phone off, asleep, unplugged, off the network | `unreachable`, logged, budget keeps counting, profile re-asserted when it returns | nothing |
| pymobiledevice3 Python API moved | transport falls back to the CLI, `via=cli` in the logs | nothing, then fix the binding |
| pymobiledevice3 CLI also fails | reconcile exits 1, `error: install failed` | `shiftd doctor` |
| Keybag wrong or expired | install fails or the phone prompts for a tap | re-export from Apple Configurator |
| Device not supervised | iOS rejects the payload | `shiftd doctor` says so, this is harness check 06 |
| Corrupt state file | moved to `state.json.corrupt-<ts>`, fresh state, logged `state.corrupt` | any active lock is released, restart the shift |
| Mac asleep through a whole window | no passes run, profile installed at window start stays on | nothing |
| Mac rebooted mid window | budget credited from the wall clock gap, enforcement resumes at login | nothing |
| launchd agent not loaded | nothing is enforced, silently | `shiftd doctor` checks for it |
| Clock moved | `clock.jump` in the log and in history, monotonic wins | look at why |

Logs go to stderr and to `[daemon].log_file`, rotated at 2MB, three back.
Every line is `event=<name> key=value`, so `grep 'event=reconcile.install'` and
`grep 'event=clock.jump'` do what you expect.

## Install

```sh
cd ~/Personal-Projects/shiftlab
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

mkdir -p ~/.config/shiftd
cp shiftd/config.example.toml ~/.config/shiftd/config.toml
# edit: udid, keybag path, blocklists, rules
$EDITOR ~/.config/shiftd/config.toml

python -m shiftd doctor
python -m shiftd --dry-run reconcile
```

`doctor` checks the interpreter, the TOML backend, the config, the keybag, both
transport paths, the state file, device reachability, supervision, which shiftd
profiles are on the phone, and whether the LaunchAgent is loaded.

## launchd

Edit the three absolute paths in `launchd/com.shiftd.agent.plist` first.
launchd does not expand `~` and does not read your shell profile.

```sh
cp launchd/com.shiftd.agent.plist ~/Library/LaunchAgents/
mkdir -p ~/Library/Logs/shiftd

# load (modern form)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.shiftd.agent.plist

# run one pass right now
launchctl kickstart -k gui/$(id -u)/com.shiftd.agent

# is it there, and what did it exit with
launchctl print gui/$(id -u)/com.shiftd.agent | head -20

# unload
launchctl bootout gui/$(id -u)/com.shiftd.agent
```

Older form, still works: `launchctl load -w` and `launchctl unload -w` with the
plist path.

It runs in the GUI session on purpose. usbmuxd is reachable from there, and a
LaunchDaemon in the system context would need extra work to see the phone.
`RunAtLoad` is on so enforcement resumes at login without waiting 60 seconds.
There is no `KeepAlive`: `reconcile` is a one shot pass that exits, and
KeepAlive would restart it in a loop.

Watch it:

```sh
tail -f ~/Library/Logs/shiftd/shiftd.log
tail -f ~/Library/Logs/shiftd/agent.err.log
```

## Emergency recovery

In rough order of how much you should have to mean it.

1. **Unlocked shift, done early.**
   `python -m shiftd unshift`

2. **Locked shift, and you genuinely need out.** Two steps, both deliberate:

   ```sh
   launchctl bootout gui/$(id -u)/com.shiftd.agent     # stop it re-asserting
   rm ~/.local/state/shiftd/state.json                 # release the lock
   python -m shiftd doctor                             # confirm what is still installed
   pymobiledevice3 profile remove com.shiftd.block.<blocklist>
   ```

   Removing the profile without booting out the agent achieves nothing: the
   next pass puts it straight back.

3. **Phone stuck with a profile and the Mac gone.** With supervision and
   `PayloadRemovalDisallowed`, Settings has no Remove button. Recovery is
   Apple Configurator on any Mac with the same supervision identity, or a
   restore. Keep a copy of the keybag somewhere that is not only this laptop.

4. **Config is broken and nothing runs.** `shiftd` refuses to start on an
   invalid config, which means no enforcement, which is a fail open. The error
   names the key. Fix it, then `launchctl kickstart -k`.

## Open questions, waiting on the harness

Two things in the code are written to be replaced once ShiftLab phase 2
reports:

* **Keybag silent install (check 08).** `transport._lib_install_silent` tries
  five argument shapes for the keybag, path, raw bytes, parsed plist, keyword
  and positional, and logs which one worked as `transport.silent_install`.
  When the answer is known, delete the losers and keep one call.
* **Whether silent install works at all.** If check 08 says the phone still
  prompts, unattended schedule flips are not possible over lockdown and the
  daemon has to either install every profile up front and toggle by other means
  or move to a local MDM server (Path 02b). The reconcile loop and the state
  machine survive that change, the transport does not.
