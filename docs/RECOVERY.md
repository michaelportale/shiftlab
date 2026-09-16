# Recovery

For when the daemon or the profiles go wrong. Supervision setup and the
erase/supervise/restore cycle are covered elsewhere.

Read the pre-commitment checklist at the bottom **before** your first real
shift. Everything above it is easier if you did.

Assume you are reading this annoyed, in a hurry, and possibly locked out of
something you need right now. Commands first, reasoning after.

---

## 0. Fastest path, by situation

| Situation | Go to |
| --- | --- |
| Phone is shifted, Mac works, daemon is wedged | [1](#1-emergency-unshift) |
| Phone is shifted, Mac is dead / lost / at the repair shop | [2](#2-the-mac-is-gone) |
| Supervision identity or keybag is lost | [3](#3-the-supervision-identity-is-gone) |
| Phone will not connect, daemon cannot reach it | [4](#4-the-phone-is-unreachable) |
| Settings shows profiles you do not recognise | [5](#5-profile-stacking-and-strays) |
| Suspect a clock problem | [6](#6-clock-manipulation) |
| Nothing above worked, want a normal phone back | [7](#7-nuclear-option) |

---

## 1. Emergency unshift

The daemon is wedged, uninstalled, mid-refactor, or you just do not trust it.
Remove the profile by hand from the Mac.

### Find the profile

```sh
cd ~/Personal-Projects/shiftlab && source .venv/bin/activate
pymobiledevice3 profile list
```

This returns the installed profiles with their `PayloadIdentifier` values. Find
the one the daemon installs.

### Remove it

```sh
pymobiledevice3 profile remove com.yourdomain.shift.block
```

**The argument is the `PayloadIdentifier`, not a filename and not the
`PayloadDisplayName`.** This is the single most common mistake under pressure.
`profile remove` takes the identifier string exactly as `profile list` printed
it. If you pass a path to the `.mobileconfig` you used to install it, it fails.

Icons come back within a few seconds. No reboot needed.

### If removal is refused

If the profile carries `PayloadRemovalDisallowed`, removal may require the
supervision keybag. The CLI signature for `remove` on current pymobiledevice3
takes only the identifier and has no `--keybag` option, unlike `install`:

```
profile install  <profiles...> [--keybag PATH]
profile remove   <name>
```

**Unverified, and you should test this deliberately rather than discover it on
a bad day:** whether an unkeybagged `profile remove` succeeds against a profile
installed with `PayloadRemovalDisallowed: true` on a supervised device. This is
exactly what ShiftLab check 10 measures. Run it and write the answer here:

```
profile remove against PayloadRemovalDisallowed profile:  [ ] works  [ ] refused
tested on iOS ____  pymobiledevice3 ____  date ________
```

If it is refused, your only Mac-side removal path needs the keybag, and section
3 becomes much more important.

Check your installed CLI before trusting any flag in this document:

```sh
pymobiledevice3 profile --help
pymobiledevice3 profile remove --help
```

The project moved from click to typer and flag spellings shifted. Do not script
against remembered syntax.

### If the Mac cannot see the phone at all

Plug in, unlock, tap Trust. Then:

```sh
pymobiledevice3 usbmux list
```

Empty output means the transport is the problem, not the profile. See section 4.

---

## 2. The Mac is gone

Dead, stolen, or at a repair shop for a week. The phone is shifted and stays
shifted.

**Straight answer: this is the real risk of the architecture, and by default
you are stuck.**

The profile lives on the phone. It has no expiry unless you gave it one. It
resists removal from Settings because that is the entire point. The only thing
that can remove it is a trusted computer with the supervision identity, and
that computer is the one that just died. There is no cloud, no MDM server, no
account recovery, and nobody to call. You built a system whose only off switch
was in your bag.

How bad this is depends entirely on choices you made before it happened.

### If you did nothing in advance

Your options are, in increasing order of pain:

1. **Any Mac plus the supervision identity, if you have the `.p12` in a
   password manager or backup.** Install Apple Configurator and
   pymobiledevice3, import the identity, remove the profile. This is a
   one-hour fix and it is why section 3 and the checklist exist.
2. **Removal password, if you built one in.** See below. Removes the profile
   from the phone itself with no computer at all.
3. **Erase All Content and Settings** on the phone. Wipes it, drops
   supervision, restore from backup. Half a day. See section 7.
4. **Wait.** If the shift schedule has an unblocked window, the phone is only
   partly unusable. If reconcile is not running because the Mac is dead, the
   currently installed profile simply stays as it is forever. A profile
   installed during a shift does not lift itself when the daemon stops. Assume
   permanently shifted.

### What a second trusted Mac buys you

A second Mac with the supervision identity imported is a full second off
switch. It can run `pymobiledevice3 profile remove` against the phone over USB
exactly like the first one. It does not need the daemon, the repo, the
schedule, or any state. It needs the identity and a cable.

This is cheap and it is the single highest-value thing in this document. It can
be an old MacBook in a drawer. It does not need to be online, current, or fast.
It needs to exist and to have the `.p12`.

**Set this up before you first lock yourself out.** The moment you need it is
precisely the moment you cannot create it, because creating a supervision
identity for an already-supervised phone is not a thing you can do without
erasing the phone.

A cheaper variant with most of the benefit: the identity `.p12` plus its
password in 1Password, and a note saying which commands to run. Any Mac you can
borrow becomes the second Mac in twenty minutes. The physical spare machine is
better because borrowing a Mac and installing Homebrew and Python on it is
exactly the kind of friction that turns an annoyance into a crisis.

### The removal password escape hatch

Apple supports a `com.apple.profileRemovalPassword` payload:

> This payload provides a password to allow users to remove a locked
> configuration profile from the device. If this payload is present and has a
> password value set, the device asks for the password when the user taps a
> profile's Remove button.

Requires supervision on iOS. Combined with `PayloadRemovalDisallowed`, per
Apple's reference, this means:

> If present and set to `true`, the user cannot delete the profile (unless the
> profile has a removal password and the user provides it).

So a removal password turns "impossible without a Mac" into "possible with a
password you chose". It is the difference between a locked door and a locked
door with a key hidden somewhere inconvenient.

The honest tradeoff: it is also a bypass. A password you know is a password you
can type at 11pm when you want Instagram. Its value depends entirely on where
you put it.

The pattern that works: generate a long random password, do not memorise it,
store it somewhere with real friction. A sealed envelope. A trusted person. A
password manager on a device you leave at home. You want it retrievable in an
hour of effort, not in ten seconds of weakness.

**Unverified:** removal passwords are documented as incompatible with profiles
that also contain a `com.apple.mdm` payload, where iOS errors with "A profile
containing an MDM payload must be removable." Your profiles carry a
`com.apple.applicationaccess` payload and no MDM payload, so this restriction
should not apply, but confirm it before relying on it. Test: install a profile
with `PayloadRemovalDisallowed: true` plus a `com.apple.profileRemovalPassword`
payload, then try to remove it from Settings and confirm iOS prompts for the
password and accepts it.

### Profile self-expiry, and why you cannot lean on it

`RemovalDate` and `DurationUntilRemoval` look like the obvious deadman switch:

> **RemovalDate:** The date on which the profile will be automatically removed.
>
> **DurationUntilRemoval:** Number of seconds until the profile is automatically
> removed. If the `RemovalDate` key is present, whichever field yields the
> earliest date will be used.

A profile that expires on its own means a dead Mac costs you hours, not weeks.

**But there are credible reports that `DurationUntilRemoval` does not fire on
iOS**, including on supervised devices, with profiles installed both via MDM and
via Apple Configurator. Apple's developer forums carry an unresolved thread on
exactly this with no staff answer.

So: build it in, because if it works it is the best mitigation available. Do
not trust it until you have watched a profile actually disappear on its own.
Test with a five minute `DurationUntilRemoval` on a throwaway profile and watch
Settings. Record the result:

```
DurationUntilRemoval fires on iOS ____ :  [ ] yes  [ ] no
RemovalDate fires on iOS ____ :           [ ] yes  [ ] no
tested ________
```

Also note these are evaluated against the phone's clock, which is section 6.

---

## 3. The supervision identity is gone

The `.p12` and its password are what make your Mac a trusted supervision host.
Lose them and you lose the ability to install profiles with the keybag.

### What is recoverable

**The identity itself: no.** It is a keypair generated by Apple Configurator on
your Mac. There is no escrow. Apple does not have a copy. It is not in iCloud.
If the Mac is wiped and there is no exported `.p12` in a backup, it is gone
permanently. Regenerating produces a different identity, which the phone does
not trust.

**Check before despairing.** It may exist and you have forgotten:

```sh
security find-identity -v ~/Library/Keychains/login.keychain-db | grep -i supervis
ls -la ~/Library/Group\ Containers/*.com.apple.configurator*/ 2>/dev/null
ls -la ~/Library/Application\ Support/com.apple.configurator/ 2>/dev/null
```

Apple Configurator can export it while you still have it: Configurator >
Settings > Organizations > select org > gear menu > Export Supervision
Identity. It writes a `.p12` and asks for a password. Time Machine and any full
disk backup will contain it if it was on disk when the backup ran.

### What is still possible without it

| Capability | Without the identity |
| --- | --- |
| Phone remains supervised | Yes. Supervision is on the phone, not the Mac. |
| Install profiles silently with keybag | No |
| Install profiles with a user tap in Settings | Probably yes, see below |
| `pymobiledevice3 profile list` | Yes. Listing needs no keybag. |
| `pymobiledevice3 profile remove` | Unverified. See section 1. |
| Remove via Settings | Only if no `PayloadRemovalDisallowed`, or you have the removal password |
| Erase All Content and Settings | Yes, unless you blocked it. See the trap below. |
| Full restore to unsupervised | Yes. Section 7. |

You can still push a profile the old way: AirDrop or email the `.mobileconfig`
to the phone and install it from Settings > General > VPN & Device Management.
That gets you an unblocking profile on with the same identifier, which replaces
the blocking one. See section 5.

**The trap you can set for yourself.** Two restriction keys will close this
door, and both are things you might reasonably have enabled:

- `allowUIConfigurationProfileInstallation: false` blocks installing profiles
  by hand from the phone. Apple: "If `false`, the system prohibits the user
  from installing configuration profiles and certificates interactively." If
  this is in your blocking profile and you lose the identity, you cannot
  hand-install the profile that would undo it.
- `allowEraseContentAndSettings: false` removes Erase All Content and Settings.
  That is your section 7 escape hatch.

**Do not set either of these.** They buy you very little against yourself and
they remove two of your three remaining exits. The person you are defending
against is a version of you who wants to scroll, not an attacker.

### The honest summary

Losing the identity is recoverable but expensive. You keep a working, supervised
phone with whatever profile is currently on it. If that profile is a blocking
one you cannot remove, your realistic path is Erase All Content and Settings,
which costs you a restore-from-backup but gets you a clean phone. Nothing is
unrecoverable. Nothing is quick.

---

## 4. The phone is unreachable

The daemon cannot see the phone: cable out, phone off, Trust revoked, usbmuxd
confused.

### Diagnose

```sh
pymobiledevice3 usbmux list                    # is it on the wire at all
pymobiledevice3 lockdown info                  # is lockdown talking
```

Empty `usbmux list` with the cable in: unlock the phone, tap Trust. If no Trust
prompt appears, reset it on the phone at Settings > General > Transfer or Reset
iPhone > Reset > Reset Location & Privacy, then replug.

If `usbmux list` shows the device but lockdown fails, restart the daemon:

```sh
sudo launchctl kickstart -k system/com.apple.usbmuxd
```

### What the daemon should do

The correct behaviour is to treat unreachability as a non-event and keep
reconciling.

| Situation | Behaviour |
| --- | --- |
| Phone unreachable at shift start | Log, retry with backoff, keep the intent. Apply as soon as it connects. |
| Phone unreachable at shift end | Same. The unblock is pending, not cancelled. |
| Phone reconnects mid-shift | Reconcile immediately. Assert desired state regardless of what is installed. |
| Phone unreachable for days | Keep retrying. Do not expire the intent, do not escalate. |

Reconcile against desired state, not against a queue of actions. The daemon
should ask "what should be installed right now given the schedule" and make the
phone match, every time it can reach it. Never "did I already send the install
command". A queue drifts; a reconciler is self-healing and idempotent.

### Why unplugging is not a bypass

Because the profile is already on the phone, and it stays there.

Unplugging mid-shift does not lift the block. It only prevents the daemon from
changing anything, and what it would change next is the unblock at the end of
the shift. **Disconnecting during a shift makes the block last longer, not
shorter.** The phone does not phone home and does not need to; nothing expires
on its own unless you configured `RemovalDate`, which per section 2 you should
not assume works.

This is the property that makes the architecture sound despite the dead-Mac
risk. It fails closed. The failure mode is being blocked too much, never too
little. Design every ambiguous case the same way, and make sure your reconciler
never treats "cannot reach phone" as "assume unblocked and do nothing".

The corollary: the bypass is not unplugging, it is deleting the daemon. Which
is fine. This is a commitment device, not a prison, and a commitment device only
has to beat impulse, not determination.

---

## 5. Profile stacking and strays

### Same identifier versus new identifier

From Apple's profile reference, on `PayloadIdentifier`:

> A reverse-DNS style identifier (com.example.myprofile, for example) that
> identifies the profile. This string is used to determine whether a new profile
> should replace an existing one or should be added.

| You install | Result |
| --- | --- |
| Same `PayloadIdentifier` as an installed profile | **Replaces** it. Old one gone. One profile on the phone. |
| New `PayloadIdentifier` each time | **Stacks.** Both stay installed. Restrictions are cumulative. |

`PayloadUUID` should be regenerated per profile and does not control this.
Identity is the identifier, not the UUID.

**Use one fixed `PayloadIdentifier` for the blocking profile, forever.** Hardcode
it. Never derive it from a timestamp, a shift name, or a uuid. With a stable
identifier, installing an updated blocklist atomically replaces the old one and
"unshift" is a single `profile remove`, which is the design in section 1.

If you generate a fresh identifier per shift, you accumulate one undeletable
profile per shift, each contributing its own restrictions, and after two weeks
you have fourteen overlapping profiles and no idea which is blocking what.
Restrictions union together: an app is blocked if any installed profile blocks
it, so removing one does nothing.

Apple additionally warns in the Restrictions reference:

> The system allows multiple Restrictions payloads. However, don't attempt to
> manage the same restriction in different payloads. Doing so results in
> unexpected behavior.

So stacked profiles managing `blockedAppBundleIDs` are not merely untidy, they
are explicitly undefined behaviour. Keep exactly one.

### Listing and cleaning up

From the Mac:

```sh
pymobiledevice3 profile list
```

From the phone: **Settings > General > VPN & Device Management**. Each profile
is listed with its display name; tap through to see payload contents and the
Remove Profile button. If Remove Profile is greyed out or absent, that profile
carries `PayloadRemovalDisallowed`.

Remove strays one at a time by identifier:

```sh
pymobiledevice3 profile remove com.yourdomain.shift.block.20260914
```

Scripted sweep of everything matching your prefix. Read the list first, then
run it:

```sh
pymobiledevice3 profile list | grep -o 'com\.yourdomain\.shift[^"]*' | sort -u
# eyeball that list, then:
pymobiledevice3 profile list | grep -o 'com\.yourdomain\.shift[^"]*' | sort -u \
  | while read -r id; do echo "removing $id"; pymobiledevice3 profile remove "$id"; done
```

Never sweep without the prefix filter. Blanket-removing every profile takes out
your Wi-Fi, VPN, and mail configuration too.

Make stray detection part of reconcile: if `profile list` shows any profile
matching your prefix other than the one identifier you own, remove it and log
it loudly. That turns a slow accumulation into a visible error on day one.

---

## 6. Clock manipulation

Two clocks matter and they fail differently.

### The Mac's clock

The daemon decides what should be installed by reading local time. Set the Mac's
clock forward past the end of a shift and the next reconcile removes the
profile. This is a complete bypass and it takes about fifteen seconds.

Worth mitigating only in proportion to how much you want to defend against
yourself. The cheap and effective version:

```sh
sudo systemsetup -setusingnetworktime on
sudo systemsetup -getnetworktimeserver
```

Then have the daemon sanity-check on every reconcile:

- Compare `time.time()` against an independent network source. An HTTPS `Date`
  header from any server you do not control is enough and needs no NTP client.
- If local time and network time disagree by more than a small threshold,
  **refuse to unblock** and log. Fail closed, consistent with section 4.
- Track a monotonic clock alongside wall time. A large wall-clock jump with a
  small monotonic delta is a clock change, not elapsed time. This catches the
  manipulation directly.

Do not over-engineer it. Anyone who edits the daemon's source can bypass it
anyway, and you have root on the machine. The check exists to make the bypass a
deliberate act rather than a thoughtless one, which is the whole job of a
commitment device.

### The phone's clock

Matters only if you use `RemovalDate` or `DurationUntilRemoval`, which are
evaluated against the device clock. Set the phone's date forward and an expiring
profile expires. That is a real bypass of the deadman switch, and it is also a
legitimate emergency exit if the Mac is dead, so decide which you want.

`forceAutomaticDateAndTime` is the restriction that pins the phone to network
time. **Unverified:** I could not confirm this key in Apple's published
`com.apple.applicationaccess` schema. Multiple MDM vendors document it as a
supervised iOS restriction, so it very likely exists, but confirm the exact
spelling against Apple's schema before shipping it, and verify on-device that
Settings > General > Date & Time actually greys out the manual toggle.

Note the interaction: if you set `forceAutomaticDateAndTime` in the blocking
profile and rely on `RemovalDate` as your dead-Mac escape, you have closed the
one manual override that would have saved you. Pick one.

---

## 7. Nuclear option

From any state, including a wedged daemon, a lost identity, a dead Mac, and an
unremovable profile, back to a completely normal unsupervised iPhone.

This always works. It is the floor under everything else, and knowing it exists
is most of why the rest of this is a manageable risk rather than a scary one.

### Option A: Erase All Content and Settings

On the phone: Settings > General > Transfer or Reset iPhone > Erase All Content
and Settings.

Per Apple, erasing all content and settings is how you unsupervise a device:

> Unsupervising an iPhone, iPad, or Apple TV erases all content and settings on
> the device, including apps and media. If you want to preserve the data on a
> supervised device, make a backup of it first.

Requires: the device passcode and your Apple ID password for Activation Lock.
Blocked if `allowEraseContentAndSettings: false` is in an installed profile,
which is the trap in section 3.

Cost: full wipe, restore from backup, re-sign-in everywhere. Half a day
including app re-downloads, less if your backup is recent.

### Option B: DFU or Recovery Mode restore

When the phone will not boot, cannot be erased from Settings, or a profile is
blocking erase. Connect to any Mac, put the phone in DFU or Recovery, restore
with Finder or Apple Configurator.

What this does, per a restore behaviour writeup:

> Configuration profiles (incl. MDM) [are] Removed. Profiles cannot survive a
> Restore.

and

> DFU and Recovery Mode both install system firmware cleanly and erase the
> configuration profile payload.

Supervision is local state established by Apple Configurator. Wiping the device
removes it. **Your phone is not in Apple Business Manager**, so there is no
Automated Device Enrollment to re-supervise it at Setup Assistant. That
re-enrollment trap applies to organisationally owned devices, not to yours.

Apple Configurator's **Revive** is the gentler first attempt: it reinstalls
firmware without erasing user data. Try Revive before Restore. It may not clear
profiles, since it preserves data, so treat it as a boot fix rather than a
recovery path.

### What it costs

| | Erase All Content and Settings | DFU restore |
| --- | --- | --- |
| Needs the Mac | No | Yes, any Mac |
| Needs supervision identity | No | No |
| Needs Apple ID password | Yes, Activation Lock | Yes, Activation Lock |
| Needs device passcode | Yes | No |
| Removes supervision | Yes | Yes |
| Removes all profiles | Yes | Yes |
| Wipes data | Yes | Yes |
| Latest iOS forced | No | Yes |
| Time | 1 to 4 hours with restore | 2 to 5 hours with restore |

### The one thing that can actually block you

**Activation Lock.** It survives every local restore as long as Find My is on,
and it is independent of supervision and MDM. After the wipe the phone asks for
the Apple ID it was signed into. Without that password the device is a brick
and no amount of restoring changes that.

So: know your Apple ID password, and keep 2FA recovery working. That is the one
credential with no workaround in this entire document. Everything else has a
path around it.

---

## Pre-commitment checklist

Do all of this before the first shift you cannot cancel. Each item converts a
potential crisis into an inconvenience. None takes long.

**Credentials and keys**

- [ ] Export the supervision identity from Apple Configurator to a `.p12`.
      Configurator > Settings > Organizations > gear > Export Supervision Identity.
- [ ] Store the `.p12` and its password in your password manager, not only on
      the Mac that uses it.
- [ ] Store a second copy somewhere offline: encrypted USB stick, or a printed
      base64 in a drawer. A `.p12` is small.
- [ ] Confirm your Apple ID password is in the password manager and 2FA recovery
      works. This is the one unrecoverable credential. Test it.
- [ ] Verify a current encrypted phone backup exists, and know how old it is.
      Section 7 costs a day or a week depending on this answer.

**Second off switch, pick at least one**

- [ ] A second Mac with the supervision identity imported and pymobiledevice3
      installed. Verify it can run `pymobiledevice3 profile list` against the
      phone. An old laptop in a drawer is enough.
- [ ] A `com.apple.profileRemovalPassword` payload in the blocking profile, with
      a long random password stored behind real friction. Verify the phone
      actually prompts for it and accepts it.
- [ ] A written card with the unshift command and the exact `PayloadIdentifier`,
      kept with the backup identity. You will not remember the identifier under
      stress and the command is useless without it.

**Do not lock these doors**

- [ ] `allowEraseContentAndSettings` is NOT set to false.
- [ ] `allowUIConfigurationProfileInstallation` is NOT set to false.
- [ ] `com.apple.Preferences` and `com.apple.mobilephone` are not relied on
      being blockable. They are not. Settings staying reachable is your escape
      hatch, not an oversight.

**Design invariants**

- [ ] The blocking profile uses ONE fixed `PayloadIdentifier`, hardcoded, never
      generated. Write it down.
- [ ] The daemon reconciles toward desired state and is idempotent. No action
      queue.
- [ ] Unreachable phone fails closed: keep the block, keep retrying, never
      assume unblocked.
- [ ] Clock skew between local and network time fails closed: refuse to unblock.
- [ ] Reconcile detects and removes stray profiles matching your prefix other
      than the one you own.

**Tests to run and record, before trusting any of it**

- [ ] Check 10: does `profile remove` work against a `PayloadRemovalDisallowed`
      profile without a keybag? Record in section 1.
- [ ] Does `DurationUntilRemoval` actually fire? Five minute test profile.
      Record in section 2. Assume no until proven.
- [ ] Does a removal password work alongside `PayloadRemovalDisallowed` in a
      profile with no MDM payload? Record in section 2.
- [ ] Does `allowSafari: false` also kill in-app browsers
      (`SFSafariViewController`) in Messages, Mail, and Slack? This determines
      whether the whole system works. See BUNDLE-IDS.md.
- [ ] Full dry run: shift on, shift off, both by hand, before any schedule
      exists.
- [ ] Rehearse the emergency unshift once, from the written card, without
      looking at this file. If it does not work from the card, fix the card.

---

## Sources

- [pymobiledevice3, profile CLI source](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/cli/profile.py)
- [Apple, ProfileRemovalPassword](https://developer.apple.com/documentation/devicemanagement/profileremovalpassword)
- [Apple, Restrictions payload](https://developer.apple.com/documentation/devicemanagement/restrictions)
- [Apple, com.apple.applicationaccess schema](https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.applicationaccess.yaml)
- [Apple, Unsupervise an iPhone, iPad, or Apple TV in Apple Configurator](https://support.apple.com/guide/apple-configurator-mac/unsupervise-an-iphone-ipad-or-apple-tv-cadbf9b585/mac)
- [Apple, Revive an iPhone, iPad, or Apple TV in Apple Configurator](https://support.apple.com/guide/apple-configurator-mac/revive-an-iphone-ipad-or-apple-tv-cad367dc4593/mac)
- [Apple Developer Forums, DurationUntilRemoval not working](https://developer.apple.com/forums/thread/774996)
- [Apple Developer Forums, com.apple.profileRemovalPassword with MDM payload](https://developer.apple.com/forums/thread/780363)
- [Configuration Profile Reference, payload key definitions](https://github.com/ProfileCreator/Configuration-Profile-Reference/blob/master/markdown/_All.md)
- [Restore a Supervised / MDM iPhone with IPSW](https://www.ipsw.io/blog/restore-mdm-supervised-iphone)
