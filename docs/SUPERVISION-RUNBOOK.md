# Supervising a personal iPhone 16 from a Mac

Runbook for putting your own iPhone 16 into supervised mode via Apple Configurator, keeping your data,
and retaining the supervision identity so `pymobiledevice3` can silently install configuration profiles.

Written September 2026. Apple Configurator 2.20.

**Read Phase 0 and the two headline findings before you touch anything.**

---

## Headline findings that shape this plan

**1. The erase is unavoidable.** Apple states it plainly for the Configurator path: supervising a device
this way means "the device is erased and all data is lost"
([Apple Platform Deployment, About Apple device supervision](https://support.apple.com/guide/deployment/about-device-supervision-dep1d89f0bff/web)).
Supervision is applied before activation, "before the Setup Assistant first appears on a new or fully
erased device". There is no in-place, non-destructive supervise path in 2.20. The only non-Configurator
route is Automated Device Enrollment via Apple Business Manager, which still supervises during Setup
Assistant on a fresh device and is not available for a retail personal phone. Plan for the wipe.

**2. Do NOT use Apple Configurator's "Restore from Back Up".** It unsupervises the phone. Apple's own
Configurator docs say, for both restore actions: "Apple Configurator erases all device contents. If the
devices are supervised, they become unsupervised after the restore"
([Back up and restore devices](https://support.apple.com/guide/apple-configurator-mac/back-up-and-restore-devices-cadbf9b61c/mac)).
Restore through **Finder** instead. See Phase 6 for the conflicting Apple statements and how to verify.

---

## Phase 0. Before you start

Checklist. All of it, before the phone gets wiped.

- [ ] Mac on macOS 15.7 or later. Required by Apple Configurator 2.20 ([Requirements](https://support.apple.com/guide/apple-configurator-mac/requirements-cadbf9a73b/mac)).
- [ ] Apple Configurator 2.20 installed from the Mac App Store.
- [ ] Free space on the Mac: at least 1.5x the phone's used storage. Check `Settings > General > iPhone Storage` on the phone, then `df -h /` on the Mac. Backups land in `~/Library/Application Support/MobileSync/Backup/`.
- [ ] A known-good USB-C cable. Use a direct port, not a hub. A flaky cable during Prepare is the top cause of a bricked-looking restore loop.
- [ ] Apple Account password to hand. You need it to turn off Find My, and again to sign back in.
- [ ] A password manager entry created *in advance* for the backup encryption password. If you lose it the backup is unrecoverable, and there is no reset that preserves it ([About encrypted backups](https://support.apple.com/en-us/108353)).
- [ ] Two-factor codes reachable from something other than the phone being wiped (another Apple device, or SMS to a number you can read elsewhere). This is the classic lockout.
- [ ] 4 to 6 hours of wall clock. See the time budget at the end.
- [ ] `pymobiledevice3` installed and working: `pymobiledevice3 lockdown info` against the phone returns output today, before any of this.
- [ ] Decide your Organization name now. It appears verbatim on the phone's supervision banner forever, and changing it later means erasing again.
- [ ] Somewhere safe and off-device to store a `.p12`. Not the phone.

Capture the pre-state for later comparison:

```sh
pymobiledevice3 lockdown info > ~/Desktop/pre-supervision-lockdown-info.txt
grep -iE 'IsSupervised|ProductVersion|UniqueDeviceID|SerialNumber' ~/Desktop/pre-supervision-lockdown-info.txt
```

Expected: `IsSupervised` is `false` or absent.

---

## Phase 0.5. Create and verify the supervision identity FIRST

Added after reading pymobiledevice3 11.12.5's source. This phase did not exist
in the original plan and it removes most of the risk from the erase.

**Why this goes before the wipe.** Apple Configurator can create an Organization
and its supervision identity with no device attached. The identity is just an
X.509 certificate and its RSA key. So you can generate it, convert it to the
keybag format, and prove the keybag works, all while your phone is still
untouched. Then Prepare with that same organization.

**What a keybag actually is.** No longer inferred. From
`pymobiledevice3/services/mobile_config.py`:

```python
keybag_data = Path(keybag_file).read_bytes()
private_key = serialization.load_pem_private_key(keybag_data, password=None)
cer = x509.load_pem_x509_certificate(keybag_data)
```

One PEM file holding an **unencrypted private key concatenated with its
certificate**. RSA or EC only; anything else raises `ProfileError`. `escalate()`
then sends the cert DER as `SupervisorCertificate`, signs the device's
`Challenge` with `PKCS7SignatureBuilder`, and sends `EscalateResponse` followed
by `ProceedWithKeybagMigration`.

This also confirms the earlier warning: `profile create-keybag` generates a
fresh self-signed key and **cannot import one**, so a keybag it makes will never
escalate against a device prepared with a different identity. Convert from
Configurator's export instead.

### 0.5.1 Create the organization

1. Open Apple Configurator with no device connected.
2. Menu bar: **Apple Configurator > Settings > Organizations > +**
3. Sign in with your Apple Account when prompted, or choose **Skip** to generate
   a local-only supervision identity. Either produces a usable identity.
4. Name it something you will recognize on the phone's lock screen banner, since
   iOS displays it. "Michael" reads better than "Org1".
5. Choose **Generate a new supervision identity**.

Expected: the organization appears in the list with a supervision identity.

### 0.5.2 Export the identity

1. Select the organization > gear or right-click > **Export Supervision
   Identity**.
2. Choose **Encrypted PKCS12 (.p12)**, set a passphrase, save it.
3. Put the `.p12` and its passphrase in your password manager **now**, and on a
   second machine. This file cannot be regenerated for an already-prepared
   device. Losing it means erasing the phone to recover.

If the export menu item is missing, fall back to Keychain Access: find the
certificate whose name matches the organization, expand it to confirm a private
key is attached, select both, right-click > Export 2 items, save as .p12.

### 0.5.3 Convert and verify

```sh
mkdir -p ~/.shiftd && chmod 700 ~/.shiftd
python tools/make_keybag.py ~/.shiftd/<identity>.p12 ~/.shiftd/keybag.pem
python tools/verify_keybag.py ~/.shiftd/keybag.pem
```

Do not use the openssl CLI for this. `openssl pkcs12 -clcerts` returns nothing
when the identity certificate is not flagged as a client cert, which is common
in Configurator exports, and it fails with the unhelpful "Could not find
certificate from <stdin>". Confirmed on a real export. `make_keybag.py` reads
the p12 with the same cryptography library that later consumes the keybag and
recovers the certificate from the additional-certificates bag.

`verify_keybag.py` runs the exact calls `escalate()` makes, including building
the real PKCS7 challenge signature against a random challenge. Eight checks. All
offline.

Expected: eight passes and "This keybag will work with
install_profile_silent."

**Do not proceed to Phase 1 until this passes.** If it fails:

| Failure | Cause | Fix |
| --- | --- | --- |
| private key is encrypted | converter wrote an encrypted key | re-run `make_keybag.py`, it always writes NoEncryption |
| no loadable PEM private key | p12 exported without the key | re-export, confirm the key is attached in Keychain Access |
| certificate does not match the private key | the p12 held more than one identity | re-export with only the supervision identity selected |
| unsupported key type | not RSA or EC | regenerate the organization |
| PKCS7 challenge signing failed | broken cert/key pair | regenerate the organization |

**What this still does not prove.** That the device accepts the certificate.
That holds by construction as long as you Prepare in Phase 3 with this same
organization, since `escalate()` checks the supervisor cert against the one the
device was prepared with. Everything up to that handshake is now verified.

## Phase 1. Clear the blockers on the phone

Order matters. Stolen Device Protection gates turning Find My off, so it goes first.

### 1.1 Turn off Stolen Device Protection

`Settings > Face ID & Passcode` (enter passcode) `> Stolen Device Protection > off`.

Expected: toggle goes off immediately.

**If this goes wrong:** if you are not at a Familiar Location, iOS imposes a Security Delay. You wait
one hour, then re-authenticate with Face ID to complete the change. Turning off SDP is itself a
delay-gated action, as is signing out of your Apple Account and changing the passcode
([About Stolen Device Protection](https://support.apple.com/en-us/120340)).
Do this step at home, where the phone already treats the location as familiar, or start the delay an
hour before you intend to begin. This is the single most common reason this runbook overruns.

### 1.2 Turn off Find My iPhone

`Settings > [your name] > Find My > Find My iPhone > off`. Enter your Apple Account password.

Expected: toggle off, and the Activation Lock association is released.

**If this goes wrong:** Configurator's Prepare will fail outright with the phone still Activation Locked.
Supervision requires the full erase, and an Activation Locked device will not come back up unattended.
If you skip this and only notice after the wipe, you can still recover by signing in with the same Apple
Account at Setup Assistant, but do not rely on it. Verify the toggle is genuinely off before continuing.

### 1.3 Note your passcode state

You do not need to remove the passcode. Setup Assistant will ask you to set one after the erase, and the
restore brings your settings back. Just know the current one.

---

## Phase 2. Back up. Encrypted, or you lose things silently.

### 2.1 The trap

An unencrypted local backup **silently omits** a large amount of state. It does not warn you. Apple's
list of what only an encrypted backup carries:

- Your saved passwords
- Wi-Fi settings
- Website history
- Health data
- Call history

([About encrypted backups on your iPhone](https://support.apple.com/en-us/108353); Apple Platform
Deployment states an unencrypted backup "never contains" these,
[Back up and restore managed devices](https://support.apple.com/guide/deployment/back-up-and-restore-managed-devices-depd44f04xc5/web)).

In practice that also means Keychain items and most app login tokens are gone, so you re-authenticate
every app on the other side, and years of Health and fitness history is unrecoverable if you had no
other copy. Finder and Configurator backups are **unencrypted by default**. This is the step people get
wrong.

### 2.2 Make the encrypted local backup

1. Connect the phone by cable. Trust the Mac if prompted.
2. Finder sidebar, click the iPhone.
3. `General` tab, `Backups` section.
4. Select **Back up all of the data on your iPhone to this Mac**.
5. Tick **Encrypt local backup**. Set the password. Store it in your password manager now, not later.
6. Click **Back Up Now**.

Expected: progress bar, then a fresh timestamp under "Latest backup to this Mac". Once encryption is on
it stays on and the phone remembers it.

**If this goes wrong:** if the encryption checkbox will not stick, or Finder claims a password is
already set that you do not know, reset it on the phone with `Settings > General > Transfer or Reset
iPhone > Reset > Reset All Settings`. This clears the backup password but also clears Wi-Fi networks and
other settings. Old encrypted backups become unreadable. Do this *before* the real backup, never after.

### 2.3 Verify the backup is actually encrypted

```sh
ls -lt ~/Library/Application\ Support/MobileSync/Backup/
# newest dir, then:
plutil -p ~/Library/Application\ Support/MobileSync/Backup/<UDID>/Manifest.plist | grep -i isencrypted
```

Expected: `"IsEncrypted" => 1`.

**Do not proceed to the erase until you have seen this print 1.** This is the gate for the whole
operation.

### 2.4 Belt and braces: also take an iCloud backup

Worth it. It is an independent copy in case the local backup is corrupt, and it covers you if the Mac
dies mid-process. It is not a substitute: iCloud backup plus iCloud sync restores most things but app
data fidelity is worse than a local encrypted restore.

`Settings > [your name] > iCloud > iCloud Backup > Back Up Now`, on Wi-Fi and power.

Note on a claim you may hit elsewhere: Apple's deployment guide lists "iCloud Backup: Turns off iCloud
Backup on supervised devices" under backup *restrictions*. That is describing the `allowCloudBackup`
restriction key that an administrator can apply, not an automatic consequence of supervision. The key's
own schema in [apple/device-management](https://github.com/apple/device-management) defines it as
defaulting to `true` with support on unsupervised devices deprecated, so it is a restriction you choose
to set, not something supervision does to you. Supervising the phone will not by itself kill your iCloud
backups. Do not set that restriction in your own blocker profile unless you mean it.

### 2.5 Rough durations

| Backup | Typical |
|---|---|
| First encrypted local backup, ~60 GB used | 25 to 60 min over USB-C |
| Subsequent local backups | 5 to 15 min |
| iCloud backup, first full | 1 to 6 hours, depends on uplink |

---

## Phase 3. Prepare with Supervise

### 3.1 Create the Organization first

Do this before touching the phone so the identity exists and you understand what it is.

Apple Configurator > `Apple Configurator` menu > `Settings` > `Organizations` > `+`.

You will be asked to sign in with an Apple Account (optional for a manual, non-MDM setup, and you can
skip it), then supply the Organization name, phone, email, address. Then Configurator offers to
**Generate a new supervision identity** or **Choose an existing supervision identity**.

Choose **Generate a new supervision identity** unless you are doing the plan B in Phase 5.3.

### 3.2 What the supervision identity actually is

An X.509 certificate plus its RSA private key. Configurator puts both into your login keychain: Apple's
docs note that after setup "the certificates and private keys for the identity are still in the login
and system keychain files"
([Organization settings in Apple Configurator](https://support.apple.com/guide/apple-configurator-mac/organization-settings-cade65abdcd/mac)).

During Prepare, the certificate is written into the phone's escrow keybag. Afterwards, anything holding
the matching private key can prove it is the supervisor over USB, escalate privileges on the
`com.apple.mobile.MCInstall` lockdown service, and install or remove configuration profiles **without a
user prompt**. That is the whole point of this exercise and the reason the profile blocker can be made
non-trivial for you to undo on impulse.

It is also why losing the private key is permanent: see Phase 8.

### 3.3 Run Prepare

1. Connect the phone. It should show in Configurator's All Devices view.
2. Select it. `Actions > Prepare`, or the Prepare button.
3. **Prepare with:** `Manual Configuration`.
4. Tick **Supervise devices**.
5. Decide **Allow devices to pair with other computers** (see 3.4).
6. Leave **Enable Shared iPad** unticked.
7. **Enrollment:** choose `Do not enroll in Device Management`.
8. **Organization:** pick the one from 3.1.
9. **Setup Assistant:** choose which panes to show. `Show all steps` is fine. You are about to restore anyway.
10. Click **Prepare**.

Expected: the phone erases, reboots to the Hello screen, and Configurator reports the prepare completed.
5 to 10 minutes.

**If this goes wrong:**
- Do not disconnect, sleep, or shut down the Mac mid-Prepare. Apple warns this "could damage the devices" ([Prepare an iPhone manually](https://support.apple.com/guide/apple-configurator-mac/prepare-an-iphone-ipad-or-apple-tv-manually-cad99bc2a859/mac)).
- Failure citing Activation Lock means Find My was still on. Recover by signing in with the same Apple Account, then redo Phase 1.2.
- If it hangs, a different cable and a direct port fixes it more often than anything else.

### 3.4 About "Allow devices to pair with other computers"

This controls whether the phone will establish a trust pairing with *any* Mac or PC, or only with hosts
possessing the supervision identity. Leaving it **on** is what you want here: `pymobiledevice3` talks
over a normal lockdown pairing, and you may want Finder to see the phone from another machine later.

Turning it **off** hardens the phone against being plugged into an arbitrary computer, but it also
restricts your own tooling to hosts carrying the identity, and Apple notes that "changing this
restriction later requires you to erase, prepare, and supervise the devices again". Given you are
building your own blocker and will be iterating on profiles, do not paint yourself into that corner on
the first pass. Leave it on.

---

## Phase 4. Minimal Setup Assistant

You are going to overwrite this in Phase 6, so do the least possible.

1. Language, region, Wi-Fi.
2. At **Apps & Data** / **Transfer Your Apps & Data**, choose **Don't Transfer Apps & Data**. Do not restore here. You want the controlled Finder restore.
3. Skip Apple Account sign-in if offered. Skip Face ID, Siri, Screen Time.
4. Set a passcode if forced. It gets replaced by the restore.

Expected: you reach the home screen on a bare, supervised phone.

### 4.1 Confirm supervision took, before restoring

Do this now. If supervision failed, you want to know before you spend an hour restoring.

`Settings > General > About`, and the banner at the top of the main Settings screen.

```sh
pymobiledevice3 profile cloud-configuration
```

Expected: `"IsSupervised": true`, plus `OrganizationName` and a
`SupervisorHostCertificates` entry whose CN matches your Configurator identity.

Do **not** use `pymobiledevice3 lockdown info | grep -i supervised`. Verified on
11.12.5: that command returns no `IsSupervised` key at all, on supervised and
unsupervised devices alike, so it prints nothing and reads as a failure.

**If this goes wrong:** if it is false, redo Phase 3. Your data is still in the encrypted backup, so
this is cheap. Do not continue with an unsupervised phone.

---

## Phase 5. Export and back up the supervision identity

**This is the step people lose, and it is unrecoverable.** Do it now, while the identity is fresh and
before anything else can go wrong.

### 5.1 Export the .p12 from Configurator

`Apple Configurator` menu > `Settings` > `Organizations` > select your Organization > the action / gear
menu > **Export Supervision Identity**.

Set format to **Encrypted PKCS12 (.p12)**, supply a passphrase, save. Apple's guidance: "Make sure the
format is 'Encrypted PKCS12 (.p12)'", and it lands as a `.p12` on your desktop
([Organization settings](https://support.apple.com/guide/apple-configurator-mac/organization-settings-cade65abdcd/mac)).

Fallback via Keychain Access if the menu item is missing: open Keychain Access, `login` keychain, search
your Organization name. You want the certificate **and** its nested private key. Select both, right
click, `Export 2 items`, format `Personal Information Exchange (.p12)`.

Verify it actually contains a key:

```sh
openssl pkcs12 -in supervision-identity.p12 -info -nokeys -legacy 2>&1 | head
openssl pkcs12 -in supervision-identity.p12 -nocerts -nodes -legacy 2>/dev/null | grep -c 'PRIVATE KEY'
```

Expected: the second command prints `1` or more. A `.p12` with no private key is useless and is the
usual silent failure when exporting from Keychain Access with only the cert row selected.

Store the `.p12` and its passphrase in at least two places, neither of them the iPhone.

### 5.2 Converting to a pymobiledevice3 keybag

`pymobiledevice3 profile install --keybag` and `profile create-keybag` want a **different container** to
Configurator's `.p12`, though the underlying material is the same kind of thing.

What the code does, from [pymobiledevice3](https://github.com/doronz88/pymobiledevice3):

- `profile create-keybag <keybag> <organization>` always **generates a brand new** self-signed RSA-2048 certificate and key. It cannot import an existing identity. It sets only the Common Name.
- The keybag file it writes is a **plain PEM file: an unencrypted private key concatenated with the certificate**. Not PKCS#12, not password protected.
- `profile install --keybag` reads that PEM, loads the key with `load_pem_private_key(..., password=None)` and the cert with `load_pem_x509_certificate`, then performs an `Escalate` / `EscalateResponse` handshake (PKCS7 SHA-256 signature over a device challenge) before sending `InstallProfileSilent`.

The consequence, and it is the important part: **a freshly generated keybag will not work on your phone.**
The device only honours the escalation if the certificate presented is the supervision identity it was
prepared with. So you must convert the Configurator identity into pymobiledevice3's PEM shape rather
than generating a new one.

```sh
# key first, in TraditionalOpenSSL form, matching what pymobiledevice3 writes
openssl pkcs12 -in supervision-identity.p12 -nocerts -nodes -legacy \
  | openssl rsa > supervision-keybag.pem

# then the certificate appended
openssl pkcs12 -in supervision-identity.p12 -clcerts -nokeys -legacy \
  | openssl x509 >> supervision-keybag.pem

chmod 600 supervision-keybag.pem
grep -c 'BEGIN' supervision-keybag.pem   # expect 2
```

`-legacy` is needed because OpenSSL 3 will not read Configurator's RC2-encrypted PKCS#12 without it. If
your `openssl` is LibreSSL (the macOS default at `/usr/bin/openssl`), drop `-legacy` or use Homebrew's
OpenSSL 3 at `/opt/homebrew/opt/openssl@3/bin/openssl`.

**Stated uncertainty.** The mapping between Configurator's exported supervision identity and
pymobiledevice3's keybag is **not documented by either project**. I am inferring it from the
pymobiledevice3 source (PEM key + cert, `password=None`) and from what the escrow keybag mechanism must
be doing. It is consistent, but unverified end to end. What to test, on the real phone, before you build
anything on top of it:

1. Write a trivial, harmless profile. A configuration profile that only sets a wallpaper or a single
   benign restriction. Something you would not mind removing by hand.
2. `pymobiledevice3 profile install --keybag supervision-keybag.pem trivial.mobileconfig`
3. Expected on success: no prompt on the phone, and the profile appears under
   `Settings > General > VPN & Device Management`.
4. Expected on failure: an escalation error from the `Escalate` / `EscalateResponse` exchange, or an
   `MCInstall` authentication error. That means the cert is not being accepted as supervisor.
5. If it fails, check in this order: (a) the PEM really has both blocks and the key is unencrypted;
   (b) the key is the one matching that cert, compare `openssl rsa -noout -modulus` and
   `openssl x509 -noout -modulus` and confirm the hashes match; (c) whether openssl's bag-attribute
   preamble text is confusing the parser, strip everything before the first `-----BEGIN`;
   (d) whether pymobiledevice3 expects the cert before the key rather than after, swap the order and retry.

If none of that works, fall back to 5.3.

### 5.3 Plan B: generate the keybag first, import it into Configurator

Cleaner if the conversion fights you, but it must be decided **before** Phase 3 because it changes the
Organization setup. Cost of switching later is another full erase.

```sh
pymobiledevice3 profile create-keybag supervision-keybag.pem "ShiftLab"
openssl pkcs12 -export -inkey supervision-keybag.pem -in supervision-keybag.pem \
  -out supervision-identity.p12
```

Then in Phase 3.1 choose **Choose an existing supervision identity** and point it at that `.p12`. Now
the keybag is native to pymobiledevice3 by construction and only Configurator has to accept the import,
which is the better-documented direction.

---

## Phase 6. Restore your data

> **CORRECTED 2026-09-16, after this went wrong in practice.**
> A post-setup restore reverts the device to unsupervised. Finder's "Restore
> Backup..." does it just as surely as Apple Configurator's restore does. Do
> **not** pick "Don't Transfer Apps & Data" in Setup Assistant and restore
> afterwards, which is what the original version of this phase said.
>
> Restore **during** Setup Assistant at "Transfer Your Apps & Data" > "From Mac
> or PC", or skip the restore entirely and let iCloud repopulate. Verify with
> `pymobiledevice3 profile cloud-configuration` before doing anything else.

### 6.1 Use Finder. Not Configurator.

1. Connect the phone. Trust the Mac.
2. Finder sidebar, click the iPhone.
3. `General` tab > **Restore Backup**.
4. Pick the encrypted backup from Phase 2. Enter the backup password.
5. Wait. Do not disconnect.

Expected: the phone reboots, restores, then spends a further while re-downloading apps and media in the
background over Wi-Fi.

### 6.2 The crux: does supervision survive this?

Apple's documentation is inconsistent here and you should know that going in.

- The Configurator unsupervise page says a supervised device's backup, "When restored to the original device, that device is still supervised", and "When restored to any other device, that device is unsupervised but available for supervision" ([Unsupervise a device](https://support.apple.com/guide/apple-configurator-mac/unsupervise-an-iphone-ipad-or-apple-tv-cadbf9b585/mac)).
- The Configurator backup page says of its own restore actions: "Apple Configurator erases all device contents. If the devices are supervised, they become unsupervised after the restore" ([Back up and restore devices](https://support.apple.com/guide/apple-configurator-mac/back-up-and-restore-devices-cadbf9b61c/mac)).

These are reconcilable: Configurator's Restore action re-images the device, which drops supervision,
while a Finder restore writes user data onto the existing activation state. Supervision lives in the
activation record and escrow keybag, not in the user-data backup. That is why the Finder path is the one
in this runbook.

**But I have not verified this against a primary Apple statement that addresses exactly our case**, which
is restoring an *unsupervised-era* backup onto a *freshly supervised* phone. Apple's statements both
concern backups taken *from* supervised devices. Treat it as high confidence, not certainty.

**So verify immediately after the restore, before you reconfigure anything:**

```sh
pymobiledevice3 profile cloud-configuration
```

Expected: `"IsSupervised": true`, plus `OrganizationName` and a
`SupervisorHostCertificates` entry whose CN matches your Configurator identity.

Do **not** use `pymobiledevice3 lockdown info | grep -i supervised`. Verified on
11.12.5: that command returns no `IsSupervised` key at all, on supervised and
unsupervised devices alike, so it prints nothing and reads as a failure.

**If this goes wrong:** if it came back false, nothing is lost. Your encrypted backup is still on the
Mac and still valid. Redo Phase 3 to re-supervise, then redo Phase 6. The cost is time, not data. This
is precisely why Phase 2.3 insisted you confirm the backup before wiping.

### 6.3 Re-enable what you turned off

Only after supervision is confirmed.

1. Sign back into your Apple Account: `Settings > [your name]`.
2. `Settings > [your name] > Find My > Find My iPhone > on`.
3. `Settings > Face ID & Passcode > Stolen Device Protection > on`.

Expected: both on, Activation Lock re-armed.

Note the interaction for later: with SDP on, disabling Find My or changing your passcode is
delay-gated again. That is useful friction for a self-imposed blocker, but it also means *you* eat the
one-hour delay the next time you need to erase and re-supervise. Factor it into any future iteration.

---

## Phase 7. Verification

Run all four.

**1. Settings banner.** Top of the main `Settings` screen, and `Settings > General > About`.

The iPhone wording is: "This iPhone is supervised. [Organization name] can monitor your internet traffic
and locate this device." Note that the "supervised **and managed by**" phrasing is Apple's Mac and Apple
Watch text, not iPhone. Do not go hunting for a string that will not appear
([About Apple device supervision](https://support.apple.com/guide/deployment/about-device-supervision-dep1d89f0bff/web)).

**2. Lockdown.**

```sh
pymobiledevice3 lockdown info | grep -iE 'IsSupervised|ActivationState'
```

Expected: `IsSupervised: True`, `ActivationState: Activated`.

**3. Profile list.**

```sh
pymobiledevice3 profile list
```

Expected: runs cleanly. Shows any profile from your 5.2 test.

**4. Silent install actually works.** The real test of the identity, not just of supervision:

```sh
pymobiledevice3 profile install --keybag supervision-keybag.pem trivial.mobileconfig
```

Expected: completes with no prompt on the phone. If it prompts, the keybag path is not working and your
blocker will be removable by hand. Go back to 5.2.

**5. Data spot-check.** Confirm the encrypted restore did its job: open Health and check history is
present, check `Settings > Apps > Passwords` has your entries, check Wi-Fi joined known networks
automatically, check call history. If any of these are empty, the backup was not encrypted and you have
a problem this runbook was designed to prevent.

---

## Phase 8. Rollback, and what is irreversible

### 8.1 Removing supervision

There is no in-place unsupervise. Apple: "Unsupervising an iPhone, iPad, or Apple TV erases all content
and settings on the device, including apps and media"
([Unsupervise a device](https://support.apple.com/guide/apple-configurator-mac/unsupervise-an-iphone-ipad-or-apple-tv-cadbf9b585/mac)).

Procedure, and it is Phases 1 through 6 again:

1. Fresh encrypted Finder backup.
2. Turn off SDP, then Find My.
3. Configurator `Actions > Prepare`, **Supervise devices unticked**. Or `Actions > Erase`.
4. Setup Assistant, minimal.
5. Finder restore from the backup.
6. Re-enable Find My and SDP.

Budget the same 4 to 6 hours. Supervision is not a toggle in either direction.

### 8.2 If you lose the supervision identity

Plainly:

- Profiles already installed under that identity **stay installed** and keep working.
- You can no longer install or remove profiles silently. `--keybag` escalation fails permanently, because you cannot prove you are the supervisor.
- Profiles marked non-removable, or installed with a removal password you also lost, cannot be removed by hand from the phone.
- The **only** remedy is a full erase and re-supervise, which is the full Phase 1 to 6 cycle with a fresh identity.
- A new supervision identity does **not** inherit authority over the old one. Apple: "After you prepare supervised devices with a supervision identity, changing that identity later requires that you erase, prepare, and supervise the devices again" ([Prepare manually](https://support.apple.com/guide/apple-configurator-mac/prepare-an-iphone-ipad-or-apple-tv-manually-cad99bc2a859/mac)).

There is a real design tension here for a self-blocker. A locked-down, non-removable profile plus a
safely stored identity means you can undo it in minutes. A locked-down profile plus a *deliberately*
hard-to-reach identity means the escape hatch is a 4-hour erase-and-restore, which is exactly the
friction you may want. Choose consciously. Do not end up in the second state by accident.

### 8.3 Genuinely irreversible

- **Data not in the backup at wipe time.** Gone. The wipe is real.
- **A forgotten backup encryption password.** The backup is unrecoverable. Apple offers a reset, but it invalidates every existing encrypted backup ([About encrypted backups](https://support.apple.com/en-us/108353)).
- **A lost supervision identity private key.** Not regenerable, not derivable from the certificate, not recoverable from the phone.
- **The Organization name on the banner.** Changing it means erase and re-supervise.
- **The "Allow devices to pair with other computers" setting.** Changing it means erase and re-supervise.

---

## Time budget

| Phase | Hands-on | Wall clock |
|---|---|---|
| 0. Prep and checks | 20 min | 20 min |
| 1. SDP and Find My off | 5 min | 5 min, **or 65 min if the Security Delay fires** |
| 2. Encrypted local backup | 5 min | 25 to 60 min |
| 2.4 iCloud backup (parallel, optional) | 2 min | 1 to 6 h, run it overnight beforehand |
| 3. Prepare with Supervise | 10 min | 10 min |
| 4. Minimal Setup Assistant | 5 min | 5 min |
| 5. Export identity, build keybag, test | 20 min | 20 min |
| 6. Finder restore | 5 min | 30 to 90 min |
| 6.x App and media re-download | 0 | 1 to 3 h background |
| 7. Verification | 10 min | 10 min |
| **Total** | **~1.5 h** | **4 to 6 h**, plus background sync |

Do it on a day you do not need the phone. Run the iCloud backup the night before.

---

## What can go wrong

| Symptom | Cause | Fix |
|---|---|---|
| Cannot turn off SDP, told to wait | Not at a Familiar Location | Wait out the one-hour Security Delay, or do it at home. Start early. |
| Prepare fails, Activation Lock | Find My still on | Sign in with the same Apple Account, turn Find My off, redo Phase 3. |
| Prepare hangs or phone stuck on Hello | Cable, hub, or Mac slept mid-Prepare | New cable, direct port, disable sleep. Never shut the Mac down during Prepare. |
| Health, passwords, Wi-Fi all missing after restore | Backup was not encrypted | Prevented by Phase 2.3. If it already happened, only an older encrypted backup or iCloud sync helps. |
| `IsSupervised: False` after restore | Restore path dropped supervision, or Configurator's Restore was used instead of Finder | Re-supervise (Phase 3), restore again (Phase 6). Data is safe in the backup. |
| Profile install prompts instead of installing silently | Keybag not accepted as supervisor | Phase 5.2 troubleshooting list. Check modulus match first. |
| `openssl` cannot read the .p12 | OpenSSL 3 refusing legacy RC2 | Add `-legacy`, or use Homebrew OpenSSL 3. |
| .p12 exports but has no private key | Only the cert row selected in Keychain Access | Re-export selecting both cert and nested key. Verify with the grep in 5.1. |
| Locked out by 2FA mid-setup | Only trusted device was the phone being wiped | Prevented in Phase 0. Recover via account recovery, which takes days. |
| Cannot remove a profile, identity lost | No supervisor key | Full erase and re-supervise. See 8.2. |

---

## Sources

- [Apple Platform Deployment: About Apple device supervision](https://support.apple.com/guide/deployment/about-device-supervision-dep1d89f0bff/web)
- [Apple Platform Deployment: Back up and restore managed devices](https://support.apple.com/guide/deployment/back-up-and-restore-managed-devices-depd44f04xc5/web)
- [Apple Configurator: Prepare an iPhone, iPad, or Apple TV manually](https://support.apple.com/guide/apple-configurator-mac/prepare-an-iphone-ipad-or-apple-tv-manually-cad99bc2a859/mac)
- [Apple Configurator: Supervise devices](https://support.apple.com/guide/apple-configurator-mac/supervise-devices-apd9e4f64088/mac)
- [Apple Configurator: Organization settings](https://support.apple.com/guide/apple-configurator-mac/organization-settings-cade65abdcd/mac)
- [Apple Configurator: Unsupervise an iPhone, iPad, or Apple TV](https://support.apple.com/guide/apple-configurator-mac/unsupervise-an-iphone-ipad-or-apple-tv-cadbf9b585/mac)
- [Apple Configurator: Back up and restore devices](https://support.apple.com/guide/apple-configurator-mac/back-up-and-restore-devices-cadbf9b61c/mac)
- [Apple Configurator: Requirements](https://support.apple.com/guide/apple-configurator-mac/requirements-cadbf9a73b/mac)
- [Apple Support: About encrypted backups on your iPhone, iPad, or iPod touch](https://support.apple.com/en-us/108353)
- [Apple Support: About Stolen Device Protection for iPhone](https://support.apple.com/en-us/120340)
- [apple/device-management](https://github.com/apple/device-management)
- [doronz88/pymobiledevice3](https://github.com/doronz88/pymobiledevice3)
