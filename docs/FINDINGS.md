# Findings

Verified facts accumulated across harness runs. The per-run reports in
`results/` get overwritten; this file does not.

Device: iPhone 16. Mac: Apple Silicon. pymobiledevice3 11.12.5.

## Run 1, 2026-09-16

| # | Result | What it means |
| --- | --- | --- |
| 01 | Confirmed | `lockdown info` opens a session against a stock unsupervised iPhone 16. Transport is fine. |
| 02 | Confirmed | `apps list` enumerates user apps. Flag is `--userspace` on 11.12.5; `--user` and `-u` are rejected. |
| 03 | Invalid | Ran with a display name instead of a bundle id. See the exit-code trap below. Redone, see below. |
| 04 | **Confirmed** | A profile pushed over lockdown to an unsupervised device installs, but **requires a tap in Settings**. No unattended flips without supervision plus a keybag. |
| 05 | Unanswered | Contradicted itself: the web clip appeared, so the profile installed, but the profile was reported as not listed in Settings. Redo. |
| 06 | **Confirmed** | A profile containing `blockedAppBundleIDs` **installs cleanly and is then ignored** on an unsupervised device. Icons do not disappear. The supervision gate is real, and it fails silently rather than rejecting the profile. |
| 07 | Failed, cause unknown | `lockdown info --mobdev2` returned "Device is not connected". Could be Wi-Fi sync never actually enabled, no sync completed since ticking it, or network client isolation. Not yet a verdict on the approach. |

### Traps found the hard way

**`apps uninstall` exits 0 on a bundle id that does not exist.** No error, no
warning. A typo is indistinguishable from success until you look at the phone.
Check 03 now validates against the inventory first and re-lists afterwards
rather than trusting the exit code.

**`profile install` exits 0 for supervised-only keys on an unsupervised
device.** Same shape of problem: the profile is accepted, the key is dropped.
Never treat exit 0 from a profile install as proof the restriction applied.

**`lockdown info --tunnel` is not a wireless test.** It needs a running
`tunneld` and sudo, and it exercises the iOS 17+ RemoteXPC path, which has
nothing to do with mobdev2 Bonjour lockdown. Removed from check 07.

### Useful for RECOVERY.md

Cleanup in run 1 removed both profiles with `pymobiledevice3 profile remove
<identifier>` and no keybag, despite `PayloadRemovalDisallowed: true` being set
on both. So on an **unsupervised** device, Mac-side removal beats
`PayloadRemovalDisallowed`. Whether that still holds once the device is
supervised is check 10 and is the thing your emergency unshift depends on. Check
05 now probes this explicitly and records it.

## Run 2, 2026-09-16 (check 03 redo)

**Confirmed: uninstall over lockdown works on iOS 26, unsupervised, with no
prompt on the device.** `apps uninstall com.linkedin.LinkedIn` removed the app;
verified by re-listing over the wire, not just by looking at the Home Screen.

So **Path 01 is a real fallback.** If supervision turns out to be more trouble
than it is worth, a launchd agent that uninstalls a blocklist on a schedule
works today with no erase, no dev account and no supervision. The cost is app
data and one-tap reinstall from the App Store, so it is friction rather than
enforcement.

## Run 3, 2026-09-16 (checks 05 and 07)

Device confirmed: iPhone17,3, iOS 26.6.2, UDID cached locally, not recorded here,
unsupervised. Cached to `results/artifacts/udid.txt`.

### Major finding: `profile install` only STAGES on an unsupervised device

`pymobiledevice3 profile list` returned an empty manifest both before and after
a successful `profile install`:

```
{"OrderedIdentifiers": [], "ProfileManifest": {}, "ProfileMetadata": {}, "Status": "Acknowledged"}
```

The install exits 0 and logs "installing", but the profile does not exist on the
device until the user taps through Settings > Profile Downloaded > Install. In
run 1 the web clip only appeared after that tap.

Together with check 04, this settles the architecture question:
**unattended profile flips are impossible on an unsupervised device.** Not
awkward, not slow. Impossible. Every schedule change would need a human tapping
Install. Supervision plus a working keybag is the only route to a daemon, and
that means the erase.

### Check 07: closer than it looked

`bonjour mobdev2` exits 0 and finds the phone at 192.168.50.75 as a
`TcpLockdownClient`. The failure was `Choose device: interactive selection
requires a terminal`, because Bonjour returns duplicate candidates and the CLI
cannot prompt. Fixed by passing `--udid`, which the daemon must always do
anyway since a launchd job has no terminal.

Still unresolved: the listing reported `PAIRED:False`, which may mean the pair
record has no Wi-Fi address yet because no full sync completed after ticking
Finder's Wi-Fi box.

### Correction

`lockdown info` reports `"PasswordProtected": false`, but check 05 confirmed iOS
demanded the device passcode before removing the profile. So a passcode IS set
and that field means something else, probably whether the device is locked right
now. Do not use it to reason about passcode state.

## Run 4, 2026-09-16 (check 05, answered)

**FAIL, which is the answer we needed.** With `PayloadRemovalDisallowed: true`
set, on an unsupervised iPhone 16 running iOS 26.6.2:

- The profile IS listed in Settings > General > VPN & Device Management
- A "Remove Profile" button IS present
- Tapping it DID remove the profile
- iOS demanded the device passcode first

So `PayloadRemovalDisallowed` buys exactly one passcode prompt on an
unsupervised device. Nothing more. This matches Apple's documented behavior:
unsupervised, iOS requires configuration profiles to be user-removable.

### Phase 1 verdict

| Question | Answer |
| --- | --- |
| Does the transport work? | Yes |
| Does uninstall-as-blocking work today, no erase? | **Yes, Path 01 is live** |
| Can profiles install unattended, unsupervised? | **No. Staged only, needs a tap** |
| Does `blockedAppBundleIDs` work unsupervised? | No. Accepted then silently ignored |
| Does `PayloadRemovalDisallowed` hold unsupervised? | No. One passcode prompt, then it comes off |
| **Is the erase avoidable for Path 02?** | **No** |

Three independent checks (04, 05, 06) all point the same way. Supervision is
load-bearing, and supervision means the erase.

## Keybag format, resolved from source (not inferred)

Read directly out of the installed `pymobiledevice3` 11.12.5, so this is no
longer an open question.

`MobileConfigService.escalate(keybag_file)`:

```python
keybag_data = Path(keybag_file).read_bytes()
private_key = serialization.load_pem_private_key(keybag_data, password=None)
cer = x509.load_pem_x509_certificate(keybag_data)
escalate_response = await self._send_recv({"RequestType": "Escalate", "SupervisorCertificate": cer.public_bytes(Encoding.DER)})
signed = PKCS7SignatureBuilder().set_data(escalate_response["Challenge"]).add_signer(cer, private_key, hashes.SHA256()).sign(Encoding.DER, [PKCS7Options.Binary])
await self._send_recv({"RequestType": "EscalateResponse", "SignedRequest": signed})
await self._send_recv({"RequestType": "ProceedWithKeybagMigration"})
```

- A keybag is **one PEM file: unencrypted private key + its certificate**
- RSA or EC only, anything else raises `ProfileError`
- `install_profile_silent` is just `escalate()` then `InstallProfileSilent`
- Confirms `create-keybag` is unusable here: it always generates a fresh
  self-signed key and cannot import, so it can never match a device prepared
  with a Configurator identity

`tools/verify_keybag.py` replays all of this offline, including the real PKCS7
signature, against a random challenge. Tested against a synthetic good keybag
(8 passes) and a deliberately mismatched key/cert pair (correctly rejected at
the match check). So the keybag half of check 08 can be proven **before** the
erase, leaving only the device-side handshake, which holds by construction if
the device is prepared with the same organization.

## Trap: openssl cannot extract a Configurator identity

`openssl pkcs12 -in identity.p12 -clcerts -nokeys` fails with:

```
Could not find certificate from <stdin>
```

`-clcerts` filters to certificates openssl considers client certificates, and a
Configurator supervision identity is frequently not flagged that way. The key
extracts fine, the cert silently does not, and you end up with no keybag.

Fixed by doing the conversion in Python with
`pkcs12.load_key_and_certificates`, falling back to matching the private key's
public numbers against the additional-certificates bag when the loader returns
`cert=None`. Tested against both shapes of p12 plus a wrong-passphrase case.

## Keybag verified against a real Configurator identity, 2026-09-16

`verify_keybag.py` returned all eight passes on the actual exported identity:

```
certificate loads: C=US,O=<org>,CN=Apple Configurator: <org> (<uuid>)
certificate public key matches the private key
certificate valid for another 7299 days (until 2046-09-11)
DER encodes for SupervisorCertificate (947 bytes)
PKCS7 challenge signature builds (1634 bytes)
```

RSA 2048, twenty year validity. The signing operation `escalate()` performs
works with this key pair.

### Two warnings, both benign, both silenced

1. `PKCS#12 bundle could not be parsed as DER, falling back to parsing as BER.
   Error details: DEFAULT value was explicitly encoded`. Apple encodes an ASN.1
   DEFAULT explicitly, which is legal BER but not strict DER. The parse
   succeeds. cryptography warns that this **may become an exception in a future
   release**, so pin the cryptography version in the daemon's requirements
   rather than tracking latest.
2. `Attribute's length must be >= 1 and <= 64, but it was 70`. The Configurator
   CN is 70 characters, over the X.500 ub-common-name limit. It only fires when
   stringifying the subject for display. `escalate()` sends
   `cert.public_bytes(Encoding.DER)` and never stringifies, so it cannot affect
   the handshake.

## Supervised, 2026-09-16. Check 08 PASSES.

Apple Configurator Prepare with Supervise completed. `profile cloud-configuration`
reports:

```
IsSupervised: true
AllowPairing: true
IsMDMUnremovable: false
ConfigurationWasApplied: true
OrganizationName: <org>
SupervisorHostCertificates: [ CN=Apple Configurator: <org> (<uuid>) ]
```

The device holds exactly the certificate the local keybag has the private key
for. That is the pairing the whole design rests on.

**`profile install --keybag` then installed a profile with no prompt on the
device.** The escalate handshake works against a real supervised iPhone 16 on
iOS 26.6.2 with an identity converted from a Configurator `.p12`.

That was the last unknown. Unattended, scheduled profile swaps from the Mac are
possible. The daemon is buildable.

### Note on verifying supervision

`pymobiledevice3 lockdown info` does **not** return an `IsSupervised` key on
11.12.5, so grepping it returns nothing on a supervised device and looks like a
failure. Use `pymobiledevice3 profile cloud-configuration` instead, or the
banner at the top of the phone's root Settings screen.

## Downloaded Profile vs Configuration Profile

The trap that produced a false FAIL on check 10, worth knowing permanently.

Settings > General > VPN & Device Management lists two different kinds of thing:

| Heading | What it is | Removable |
| --- | --- | --- |
| DOWNLOADED PROFILE | staged by `profile install` with no keybag, never accepted | always, by design, it was never installed |
| CONFIGURATION PROFILE | actually installed | depends on supervision and payload flags |

A plain `profile install` on a supervised device still only stages. Deleting the
resulting Downloaded Profile proves nothing. Check 10 originally tested one of
these and reported the design as broken.

Ground truth from `profile list` after check 08:

```
OrderedIdentifiers: [com.apple.configurator.usbrestrictedmode, com.shiftlab.marker]
com.shiftlab.marker: IsActive true, PayloadRemovalDisallowed true
```

`com.shiftlab.blocked` from check 09 is absent, confirming it was staged and
never installed. So the profile with no Remove Profile button was the silently
installed marker.

### Bonus: Configurator installs a USB restricted mode profile

Prepare left `com.apple.configurator.usbrestrictedmode`, "USB Accessories while
locked allowed", on the device. That keeps the lockdown channel reachable while
the phone is locked, which is what a daemon firing at 22:30 against a phone
sitting on a charger needs. Do not remove it.

## Phase 2 results, 2026-09-16

### Check 10 PASS. Silent install is genuinely non-removable.

`com.shiftlab.marker`, installed with `profile install --keybag` on the
supervised device, appears under CONFIGURATION PROFILE with **no Remove Profile
button**. Supervision plus silent install is sufficient on its own.
`allowUIConfigurationProfileInstallation=false` is not needed, so Settings stays
usable for everything else. Check 11 is belt and braces, not a requirement.

Erase All Content and Settings was **not** greyed out, as expected: nothing in
the test profile sets `allowEraseContentAndSettings=false`. That remains an exit
and should probably stay one.

### Check 09 effectively passes, with a caveat worth knowing

`blockedAppBundleIDs` with the keybag hid `com.apple.podcasts` from the Home
Screen. Spotlight still surfaces the app's name in results, but tapping it does
not launch: iOS shows a restrictions-enabled prompt instead. So the enforcement
holds, the leak is cosmetic, and the app name remains visible in search.

### Trap: `profile remove` takes no `--keybag`

```
$ pymobiledevice3 profile remove com.shiftlab.marker --keybag ~/.shiftd/keybag.pem
Error: No such option: --keybag        (exit 2)
```

`profile_remove(service_provider, name)` takes only the identifier, and
`remove_profile()` sends an unsigned RemoveProfile request. The harness was
passing `--keybag`, so the command never ran and the emergency-exit probe
reported a false negative that looked like a lockout.

Lesson, the same one as `apps uninstall` and `profile install`: on this CLI a
non-zero exit can mean "you typed it wrong" rather than "the device refused".
Always check the stderr, never the exit code alone.

### Emergency exit confirmed

```
$ pymobiledevice3 profile remove com.shiftlab.blocked
$ pymobiledevice3 profile remove com.shiftlab.marker
$ pymobiledevice3 profile list
OrderedIdentifiers: [com.apple.configurator.usbrestrictedmode]
```

Plain `profile remove`, no keybag, removed a profile carrying
`PayloadRemovalDisallowed: true` that the phone itself offered no way to delete.

**This is the asymmetry the design rests on.** The phone cannot undo a shift.
The Mac can, with one command and no supervision identity needed at the removal
step. Keep it somewhere findable:

```sh
pymobiledevice3 profile remove com.shiftd.blocklist
```

## Verified end to end

| Capability | Status |
| --- | --- |
| Silent, unattended profile install from the Mac | yes, keybag required |
| Apps hidden by `blockedAppBundleIDs` | yes, Spotlight shows the name but will not launch |
| Profile non-removable from the phone | yes, supervision plus silent install is enough |
| Emergency removal from the Mac | yes, plain `profile remove` |
| Wireless control after unplugging | discovery works, session pending a `--udid` retry |

Nothing about the architecture is unproven any more. What is left is product
work: the blocklist, the schedule, and the daemon that was already written.

## RESTORE DROPS SUPERVISION. Confirmed the hard way, 2026-09-16.

After a Finder "Restore Backup..." of the pre-supervision encrypted backup onto
the freshly supervised phone:

```
$ pymobiledevice3 profile cloud-configuration | grep -i supervis
    "IsSupervised": false,
```

All data came back. Supervision did not. The phone is a normal unsupervised
iPhone 16 again.

This is documented behavior, not bad luck:

- Tech Lockdown: "Normally, if you attempt to restore a full backup on to a
  newly supervised iPhone or iPad, the device will revert to being unsupervised."
  ([source](https://www.techlockdown.com/articles/restore-full-backup-supervised-iphone))
- Scalefusion: a normal backup-restore cycle causes "the Supervision settings to
  be lost, and the device becomes unmanaged."
  ([source](https://help.scalefusion.com/docs/supervise-ios-devices-without-data-loss-backup-supervise))

The runbook flagged this as its one unverified assumption and routed the restore
through Finder to dodge Configurator's documented unsupervising behavior. Finder
does the same thing. **Post-setup restore of any kind reverts supervision.**

### The two documented workarounds

**A. Restore during Setup Assistant.** At "Transfer Your Apps & Data" choose
From Mac or PC and restore there, instead of picking "Don't Transfer" and
restoring afterwards. Tech Lockdown describes supervision surviving this path,
but their write-up launders the backup through a second device first, which
implies restoring the device's own pre-supervision backup may still revert it.
Confidence: moderate, not proven.

**B. Skip the restore.** Prepare with Supervise, set up fresh, sign in, let apps
re-download. iCloud-synced data (Photos, Messages, Notes, Contacts, Keychain)
comes back on its own. You lose local-only app state. Confidence: certain.

### What this costs

Nothing irreversible. The encrypted backup is intact, the supervision identity
is exported and verified, and every capability is already proven on hardware.
What it costs is another erase-and-restore cycle.

## Open questions

| Question | Answered by | Status |
| --- | --- | --- |
| Can a `PayloadRemovalDisallowed` profile be deleted from Settings, unsupervised? | check 05 | **yes, after a passcode prompt** |
| Does uninstall over lockdown work on iOS 26? | check 03 | **yes, confirmed, no prompt** |
| Does mobdev2 wireless lockdown work on this network? | check 07 | discovery yes, session pending `--udid` retry |
| Does a Setup Assistant restore preserve supervision? | workaround A | **unproven, the next thing to test** |
| Does `profile install --keybag` install silently once supervised? | check 08 | **YES. Verified end to end on the supervised device.** |
| Does Mac-side `profile remove` still work once supervised? | check 10 | after supervision |
| Does `DurationUntilRemoval` ever actually fire? | manual | unverified, assume no |
