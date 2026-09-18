# Fresh setup checklist

The certain path: Prepare with Supervise, skip the restore, let iCloud
repopulate. Supervision is guaranteed to survive because nothing is restored
over it.

The cost moves from "will supervision hold" to "what does not come back from
iCloud". Work through this **before** you erase. The items in Part 1 are the
ones that are gone permanently if you skip them.

---

## Part 1. Things that do NOT come back. Handle these first.

### Authenticator apps

The highest-stakes item on this page. If you use Google Authenticator, Authy or
similar without cloud sync, erasing destroys the TOTP seeds and you lose access
to every account they protect, including possibly the ones you would need to
recover the others.

- **Google Authenticator**: open it, Menu > Transfer accounts > Export accounts.
  Screenshot the QR codes from a second device, or enable Google account sync.
- **Authy**: confirm multi-device is enabled and the account is registered to
  your phone number.
- **1Password / Bitwarden TOTP**: already synced, nothing to do.
- Whatever you use, verify you can complete a login from a second device before
  erasing.

### Signal

Signal history does not restore from an iCloud or Finder backup. It needs a
device-to-device transfer, which you cannot do to the same phone. Assume the
message history is gone. Export anything you need first.

### WhatsApp

Has its own separate iCloud backup that is off by default.
WhatsApp > Settings > Chats > Chat Backup > Back Up Now. Wait for it to finish.

### Files stored "On My iPhone"

Files app > Browse > On My iPhone. Anything there is local only. Move it to
iCloud Drive or AirDrop it to the Mac.

### Local-only app state

Game saves not backed by Game Center, offline downloads (Spotify, Netflix,
podcasts), draft content in apps that do not sync, custom keyboards and
shortcuts that are not iCloud-backed.

---

## Part 2. Confirm these are actually syncing

Settings > [your name] > iCloud > See All. Each should be on:

| Item | Where it lands |
| --- | --- |
| Photos | iCloud Photos. Open Photos and confirm it does not say "Uploading N items" |
| Messages in iCloud | Settings > [name] > iCloud > Messages in iCloud, on |
| Passwords and Keychain | this is what saves you from re-typing every login |
| Contacts, Calendars, Reminders, Notes, Safari | default on, verify anyway |
| Health | Settings > [name] > iCloud > Health |
| Voice Memos | often overlooked |
| App Store purchase history | automatic, this is how apps come back |

Do not start the erase while Photos still shows an upload in progress.

---

## Part 3. Take a backup anyway

Even though you are not going to restore it. It is your undo button if you
decide supervision is not worth it and you want your old phone back.

Finder > iPhone > Encrypt local backup ticked > Back Up Now.
Backup password into your password manager.

---

## Part 4. The sequence

1. Settings > Face ID & Passcode > **Stolen Device Protection off**. Do it at
   home. The one hour Security Delay is the usual cause of overrun.
2. Settings > [your name] > Find My > **Find My iPhone off**. The restore turned
   this back on, it is not still off from yesterday.
3. Apple Configurator > connect phone > Actions > Prepare:
   Manual Configuration · **Supervise devices ticked** · **Allow pairing with
   other computers ON** · Shared iPad off · **Do not enroll in Device
   Management** · Organization **MichaelHome**
4. Setup Assistant: language, region, Wi-Fi. At **Transfer Your Apps & Data**
   choose **Don't Transfer Apps & Data**. This time that is deliberate.
5. **Sign in to your Apple Account.** Unlike last time, you want this. It is
   what pulls everything back.
6. Set a passcode, enable Face ID, turn iCloud services back on.
7. Verify supervision survived, which it will, because nothing was restored:

   ```sh
   pymobiledevice3 profile cloud-configuration | grep -i supervis
   ```

   Expect `"IsSupervised": true`.

8. Let the App Store re-download your apps. App Store > account > Purchased, or
   they come automatically.

---

## Part 5. Then the daemon

```sh
pymobiledevice3 apps list --userspace > results/artifacts/apps.json
python -m shiftd doctor
```

Build the blocklist from real bundle ids using `docs/BUNDLE-IDS.md`, point
`config.toml` at it, load the launchd agent per `docs/DAEMON.md`.

Keep this findable, it is your only exit once a locked shift is running:

```sh
pymobiledevice3 profile remove com.shiftd.blocklist
```
