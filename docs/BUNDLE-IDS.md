# Bundle IDs

Reference for `blockedAppBundleIDs`. A wrong id does not error. The profile
installs clean, the app stays on the Home Screen, and you only notice on a bad
day. Treat every id here as a starting point and confirm against the device.

## How to read the confidence column

| Mark | Means |
| --- | --- |
| **V** | Verified 2026-09-15 against Apple's iTunes Lookup API (`itunes.apple.com/lookup?id=<trackId>`), which returns the `bundleId` Apple has on file for the shipping App Store build. |
| **A** | Verified against Apple's own documentation: [Bundle IDs for iPhone and iPad Apple apps](https://support.apple.com/guide/deployment/bundle-ids-for-iphone-and-ipad-apple-apps-depece748c41/web). |
| **I** | Inferred. Not confirmed against a primary source. Test before relying on it. |

The App Store id is included so you can re-verify any row in one call:

```sh
curl -s "https://itunes.apple.com/lookup?id=389801252&country=us" | python3 -m json.tool | grep bundleId
```

## The payload key

`blockedAppBundleIDs` lives in a `com.apple.applicationaccess` payload.
Apple's [machine-readable schema](https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.applicationaccess.yaml)
says, verbatim:

> If present, the system prevents showing or launching apps with bundle IDs in
> the array. Include the value `com.apple.webapp` to restrict all webclips.

Supervised only. Introduced iOS 15.0. The inverse key is spelled
`allowListedAppBundleIDs`, not `allowedAppBundleIDs`, which is an easy hour to
lose.

Apple also warns in the same file:

> Denying system apps may disable other functionality. For example, denying the
> App Store app may prevent users from accepting terms.

And in the [Restrictions payload docs](https://developer.apple.com/documentation/devicemanagement/restrictions):

> The system allows multiple Restrictions payloads. However, don't attempt to
> manage the same restriction in different payloads. Doing so results in
> unexpected behavior.

So keep `blockedAppBundleIDs` in exactly one payload in exactly one profile.
Do not split the blocklist across a "social" profile and a "games" profile.

---

## Social and feed

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| Instagram | `com.burbn.instagram` | V | 389801252 |
| TikTok | `com.zhiliaoapp.musically` | V | 835599320 |
| YouTube | `com.google.ios.youtube` | V | 544007664 |
| X (Twitter) | `com.atebits.Tweetie2` | V | 333903271 |
| Facebook | `com.facebook.Facebook` | V | 284882215 |
| Reddit | `com.reddit.Reddit` | V | 1064216828 |
| Snapchat | `com.toyopagroup.picaboo` | V | 447188370 |
| Threads | `com.burbn.barcelona` | V | 6446901002 |
| LinkedIn | `com.linkedin.LinkedIn` | V | 288429040 |
| Discord | `com.hammerandchisel.discord` | V | 985746746 |
| Pinterest | `pinterest` | V | 429047995 |
| Tumblr | `com.tumblr.tumblr` | V | 305343404 |
| BeReal | `AlexisBarreyat.BeReal` | V | 1459645446 |
| Bluesky | `xyz.blueskyweb.app` | V | 6444370199 |

Five of these are not guessable and are the usual cause of a silently
ineffective blocklist:

- **Pinterest is literally `pinterest`.** No reverse-DNS, no dots. If your
  profile generator validates bundle ids against a reverse-DNS regex, it will
  reject or mangle this one.
- **X is `com.atebits.Tweetie2`.** Atebits was the developer of Tweetie, which
  Twitter bought in 2010. Sixteen years and two renames later the id is
  unchanged. `com.twitter.twitter` and `com.x.x` are both wrong.
- **Snapchat is `com.toyopagroup.picaboo`.** Picaboo was the original name.
- **Threads is `com.burbn.barcelona`.** Burbn was Instagram's predecessor,
  Barcelona was Threads' internal codename. Same prefix as Instagram.
- **BeReal is `AlexisBarreyat.BeReal`.** Capitalised, founder's name, not a
  domain. Bundle ids are case-sensitive; do not normalise this to lowercase.

## Browsers

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| Safari | `com.apple.mobilesafari` | A | built in |
| Chrome | `com.google.chrome.ios` | V | 535886823 |
| Firefox | `org.mozilla.ios.Firefox` | V | 989804926 |
| Edge | `com.microsoft.msedge` | V | 1288723196 |
| Brave | `com.brave.ios.browser` | V | 1052879175 |
| DuckDuckGo | `com.duckduckgo.mobile.ios` | V | 663592361 |
| Arc Search | `company.thebrowser.ArcMobile2` | V | 6472513080 |

Do not block Safari with `blockedAppBundleIDs`. See the Safari section below.

`ArcMobile2` is Arc Search, the current shipping iPhone app. The older Arc
companion app used a different id; if you never installed it, ignore this.

This list is not exhaustive and cannot be. Opera, Opera GX, Vivaldi, Onion
Browser, Aloha, and every "private browser" in the App Store are all separate
bundle ids, and new ones ship weekly. An allowlist
(`allowListedAppBundleIDs`) is the only structurally sound answer to that
problem. A blocklist is a game of whack-a-mole you will eventually lose. The
tradeoff is that an allowlist means enumerating every app you want to keep,
including ones you have not installed yet.

## Games and gambling-adjacent

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| Roblox | `com.roblox.robloxmobile` | V | 431946152 |
| Clash of Clans | `com.supercell.magic` | V | 529479190 |
| Clash Royale | `com.supercell.scroll` | V | 1053012308 |
| DraftKings Sportsbook & Casino | `com.draftkings.sportsbook` | V | 1375031369 |
| DraftKings Fantasy Sports | `com.draftkings.dknativermg` | V | 710535379 |
| FanDuel Sportsbook & Casino | `com.fanduel.sportsbook` | V | 1413721906 |

Supercell's ids are codenames, not product names: Clash of Clans is `magic`,
Clash Royale is `scroll`. Do not guess these.

DraftKings ships at least two separate apps. Blocking the sportsbook leaves
daily fantasy installed and vice versa. Block both.

## Streaming and time sinks

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| Netflix | `com.netflix.Netflix` | V | 363590051 |
| Twitch | `tv.twitch` | V | 460177396 |
| Spotify | `com.spotify.client` | V | 324684580 |
| Prime Video | `com.amazon.aiv.AIVApp` | V | 545519333 |
| Disney+ | `com.disney.disneyplus` | V | 1446075923 |

Twitch is `tv.twitch` with no third component. Prime Video is `aiv`, for Amazon
Instant Video, a brand that has not existed since 2015.

Think before blocking Spotify. If it is your only audio app, blocking it during
a work shift removes focus music rather than a distraction. Blocking Spotify is
usually a mistake unless the problem is specifically podcast-scrolling.

## Shopping

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| Amazon | `com.amazon.Amazon` | V | 297606951 |
| eBay | `com.ebay.iphone` | V | 282614216 |
| Temu | `com.einnovation.temu` | V | 1641486558 |
| SHEIN | `zzkko.com.ZZKKO` | V | 878577184 |

SHEIN's id is `zzkko.com.ZZKKO`: a reversed domain that is itself already
reversed, plus mixed case. Copy it, do not retype it.

## Sports and news

| App | Bundle ID | Conf | App Store id |
| --- | --- | :-: | --- |
| ESPN | `com.espn.ScoreCenter` | V | 317469184 |
| The Athletic | `com.theathletic.news` | V | 1135216317 |
| Apple News | `com.apple.news` | A | built in |
| Bloomberg | `com.bloomberg.Bloomberg` | V | 281941097 |

ESPN is `ScoreCenter`, the app's name a decade ago.

## Apple system apps

All from Apple's published list. These are stable across iOS versions in a way
third-party ids are not.

| App | Bundle ID | Conf | Blockable? |
| --- | --- | :-: | --- |
| Safari | `com.apple.mobilesafari` | A | Use `allowSafari`, see below |
| App Store | `com.apple.AppStore` | A | Yes, with side effects |
| Messages | `com.apple.MobileSMS` | A | Yes |
| Mail | `com.apple.mobilemail` | A | Yes |
| News | `com.apple.news` | A | Yes |
| Podcasts | `com.apple.podcasts` | A | Yes |
| Music | `com.apple.Music` | A | Yes |
| FaceTime | `com.apple.facetime` | A | Yes |
| Photos | `com.apple.mobileslideshow` | A | Yes |
| Camera | `com.apple.camera` | A | Yes |
| **Settings** | `com.apple.Preferences` | A | **No. Never.** |
| **Phone** | `com.apple.mobilephone` | A | **No. Never.** |

Worth knowing about, same source:

| App | Bundle ID | Conf |
| --- | --- | :-: |
| Shortcuts | `com.apple.shortcuts` | A |
| Safari web clips (all) | `com.apple.webapp` | A |
| TV | `com.apple.tv` | A |
| Games | `com.apple.games` | A |
| Sports | `com.apple.sports` | A |
| Stocks | `com.apple.stocks` | A |
| Books | `com.apple.iBooks` | A |
| Files | `com.apple.DocumentsApp` | A |
| Find My | `com.apple.findmy` | A |
| Maps | `com.apple.Maps` | A |
| Contacts | `com.apple.MobileAddressBook` | A |
| Calendar | `com.apple.mobilecal` | A |
| Notes | `com.apple.mobilenotes` | A |
| Reminders | `com.apple.reminders` | A |
| Clock | `com.apple.mobiletimer` | A |
| Wallet | `com.apple.Passbook` | A |
| Health | `com.apple.Health` | A |
| Weather | `com.apple.weather` | A |
| Watch | `com.apple.Bridge` | A |

---

## Caveats that will bite you

### Settings and Phone can never be blocked

Apple, in [Device management restrictions for supervised devices](https://support.apple.com/guide/deployment/restrictions-for-supervised-devices-dep6b5ae23e9/web):

> Any apps other than Settings or Phone (on iPhone) can be placed on either an
> approved list or a disapproved one.

Putting `com.apple.Preferences` or `com.apple.mobilephone` in
`blockedAppBundleIDs` is not an error. It is silently ignored. Do not build a
design that assumes otherwise, and do not spend an evening debugging why
Settings is still there.

This is a feature, not a limitation. Settings staying reachable is what makes
the phone recoverable. See RECOVERY.md.

### Safari has a separate mechanism

Safari is controlled by the boolean `allowSafari`, not by the blocklist. Apple's
schema:

> If `false`, the system disables the Safari web browser app, and the system
> removes its icon from the Home Screen. This setting also prevents users from
> opening web clips.

Supervised only. Note the second sentence: `allowSafari: false` kills web clips
as a side effect, independently of `com.apple.webapp`.

**Unverified:** whether `com.apple.mobilesafari` in `blockedAppBundleIDs` also
works. Apple's own Restrictions example profile literally uses
`com.apple.mobilesafari` as its `blockedAppBundleIDs` sample value, which
suggests it does, but the documented and supported route is `allowSafari`.
Test both in phase 2 check 09 and use whichever is confirmed. Do not set both
in the same profile; per Apple, managing one restriction from two places is
undefined behaviour.

### com.apple.webapp blocks every web clip

`com.apple.webapp` is not an app. It is a wildcard for all Home Screen web
clips. Put it in `blockedAppBundleIDs` and every web clip disappears, including
any you added for legitimate reasons. Put it in `allowListedAppBundleIDs` and
all of them are permitted.

There is no per-clip granularity. It is all or nothing.

This matters because a web clip is the obvious bypass: add `instagram.com` to
the Home Screen and you have a full-screen Instagram that is not
`com.burbn.instagram`. If you block browsers but not `com.apple.webapp`, you
have left the side door open.

### Shortcuts is a bypass vector

Shortcuts can open URLs and launch apps. `com.apple.shortcuts` should be in the
blocklist if you are serious. Apple notes that
`com.apple.ShortcutsActions` must be added to `allowListedAppBundleIDs`
separately if a Shortcut action needs to run, which implies the actions runtime
is a distinct id from the app.

**Unverified:** whether blocking `com.apple.shortcuts` also stops Shortcuts
automations firing in the background, or only hides the app. Test it.

### Blocking the App Store has a cost

Apple's own warning, quoted above. Also: with the App Store blocked you cannot
reinstall an app you deleted, and you cannot accept new terms. Blocking it
prevents "just download a different browser" as a bypass, which is the main
reason to do it, but it is not free.

---

## Getting the truth for your own device

Any published list, including this one, drifts. Apps get acquired, rewritten,
and re-bundled. The only authoritative answer is your phone.

### From the device over USB

```sh
pymobiledevice3 apps list --userspace
```

**Flag warning.** The spelling moves between releases. Verified on
pymobiledevice3 11.12.5 (2026-09-16): the flag is `--userspace`, and `--user`
and `-u` are both rejected. Some releases used `--type {System,User,Hidden,Any}`.
Check `--help` on whatever version you have rather than trusting this line.
The harness probes several spellings for exactly this reason.

```sh
pymobiledevice3 apps list --help   # flag spellings move between releases, check yours
```

Useful spellings once you know which you have:

```sh
pymobiledevice3 apps list --userspace          # apps you installed
pymobiledevice3 apps list --system        # Apple's built-ins (unverified spelling, check --help)
pymobiledevice3 apps list           # everything
pymobiledevice3 apps query com.burbn.instagram # confirm one id exists
```

Pipe to get a clean blocklist-ready list of what is actually installed:

```sh
pymobiledevice3 apps list --userspace 2>/dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(k, "\t", v.get("CFBundleDisplayName","")) for k,v in sorted(d.items())]'
```

ShiftLab check 02 already does this and writes `results/artifacts/apps.json`.
That file, not this document, is the source of truth for your blocklist. Build
the blocklist by selecting from it, so a typo is impossible by construction.

### From an IPA

An `.ipa` is a zip. The id is `CFBundleIdentifier` in the app's `Info.plist`:

```sh
unzip -p App.ipa 'Payload/*.app/Info.plist' > /tmp/i.plist
plutil -extract CFBundleIdentifier raw /tmp/i.plist
```

If `plutil` complains the plist is binary, it still works; `plutil` handles
both. On a non-Mac:

```sh
python3 -c 'import plistlib; print(plistlib.load(open("/tmp/i.plist","rb"))["CFBundleIdentifier"])'
```

### From the App Store without the app

The iTunes Lookup API, which is how every row marked **V** above was checked:

```sh
curl -s "https://itunes.apple.com/lookup?id=<trackId>&country=us" \
  | python3 -c 'import json,sys; [print(r["bundleId"], r["trackName"]) for r in json.load(sys.stdin)["results"]]'
```

Get `<trackId>` from the App Store URL: `apps.apple.com/us/app/name/id389801252`.
The `/search` endpoint is blocked by Apple's robots.txt for automated agents,
but `/lookup` by id is not.

This is the fastest way to verify a new app before adding it, and it does not
require the app to be installed.

---

## The practical trap: the browser is the whole game

Every app in this document has a website. Instagram, TikTok, X, Reddit, and
YouTube all ship full-featured mobile web experiences specifically because they
want to reach people who have not installed the app. YouTube's mobile site is
close to feature-complete. Reddit's is fine. X's is fine.

So a blocklist that hides fourteen social apps and leaves Safari running does
approximately nothing. You will discover this within about four minutes of your
first shift, and the discovery is corrosive: the first time you route around
your own system by typing a URL, the system stops being a constraint and
becomes a suggestion.

A blocklist that does not include the browsers is not a blocker. It is a
Home Screen tidying tool.

### What blocking the browser actually costs

This is the real decision, so be honest about it. With Safari off and Chrome,
Firefox, Edge, Brave, DuckDuckGo, and Arc blocked, you lose, for the whole
shift:

- Looking anything up. Docs, error messages, Stack Overflow, an address, a
  train time, a restaurant menu, a package tracking link.
- Every link anyone sends you. Slack, Messages, and Mail links either fail to
  open or open in an in-app browser, which is a separate question below.
- OAuth and SSO flows that hand off to a browser.
- Captive Wi-Fi portals. Hotels, trains, cafes. The portal needs a browser to
  authenticate. **This is the one that will actually strand you**: you arrive
  somewhere, join the Wi-Fi, and cannot complete the login, so you have no
  network at all beyond cellular.
- Anything that opens a web view for payment or verification.

That is a serious tax on a working day, and it is the reason most people who
build one of these quietly stop using it after a week.

### The in-app browser hole

`SFSafariViewController` and `WKWebView` are how Slack, Messages, and Mail open
links in place. They are part of the host app, not `com.apple.mobilesafari`.

**Unverified, and this is the single most important thing to test in phase 2:**
whether `allowSafari: false` also disables `SFSafariViewController` inside other
apps. Apple's wording says it disables "the Safari web browser app" and its
icon, and separately that it prevents opening web clips. It says nothing about
embedded browsers.

Two possible worlds, and they are very different products:

| If in-app browsers **still work** | If they are **also killed** |
| --- | --- |
| The block is porous. Anything with a web view is a browser. Messages is a browser. You can reach any site by sending yourself a link. | The block is real, but the phone is substantially degraded. Links are dead everywhere and captive portals are unreachable. |

Test it explicitly: with a shift active, tap a link in Messages and record what
happens. Do the same from Mail and Slack. Until you have that answer you do not
know what your own system does, and the answer determines whether this project
is worth finishing.

### The shape that actually works

Rather than all-or-nothing on the browser:

1. **Keep one browser, block the rest.** Leave DuckDuckGo or Firefox reachable
   and block Safari plus the others. Captive portals and lookups survive. This
   is the pragmatic default and it is what most people land on.
2. Accept it is a speed bump, not a wall. The remaining browser can reach
   instagram.com. That is fine if the goal is friction rather than a cage: the
   blocked thing is no longer one thumb-tap from the Home Screen, which is
   where most of the compulsion lives.
3. If you want the wall, pair a full browser block with a DNS or proxy layer so
   the sites are unreachable rather than merely inconvenient, and keep exactly
   one allowlisted browser for captive portals. That is a bigger project than
   this one.

Option 1 plus `com.apple.webapp` in the blocklist plus `com.apple.shortcuts`
gets you most of the benefit at a fraction of the cost. Start there. Tighten
only if you catch yourself routing around it.

---

## Sources

- [Apple, com.apple.applicationaccess payload schema](https://github.com/apple/device-management/blob/release/mdm/profiles/com.apple.applicationaccess.yaml)
- [Apple, Restrictions payload reference](https://developer.apple.com/documentation/devicemanagement/restrictions)
- [Apple, Bundle IDs for iPhone and iPad Apple apps](https://support.apple.com/guide/deployment/bundle-ids-for-iphone-and-ipad-apple-apps-depece748c41/web)
- [Apple, Device management restrictions for supervised devices](https://support.apple.com/guide/deployment/restrictions-for-supervised-devices-dep6b5ae23e9/web)
- [Jamf, Allowing access to Web Clips while restricting app use](https://support.jamf.com/en/articles/11024598-allowing-access-to-web-clips-while-restricting-app-use-with-jamf-pro)
- [pymobiledevice3, apps CLI source](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/cli/apps.py)
- Apple iTunes Lookup API, queried 2026-09-15, for every row marked **V**
