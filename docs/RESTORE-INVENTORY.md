# Restore inventory

Generated from the phone before erasing. 341 user apps.

Tick as you go. The CSV next to this
(`results/artifacts/restore-inventory.csv`) has the same data with blank
`installed` / `logged_in` / `notifications` columns if you would rather work in
a spreadsheet.

## 1. Handle BEFORE you erase (4)

These lose something a reinstall does not give back.

| | App | Bundle id | Why |
| --- | --- | --- | --- |
| [ ] | Authenticator | `com.google.Authenticator` | TOTP seeds are destroyed. Export accounts first. |
| [ ] | Authenticator | `com.microsoft.azureauthenticator` | Back up in-app before erasing. |
| [ ] | Duo Mobile | `com.duosecurity.DuoMobile` | Duo needs re-activation from each provider. |
| [ ] | ‎WhatsApp | `net.whatsapp.WhatsApp` | Has its own iCloud backup, OFF by default. Run it manually. |

## 2. High friction to get back into (18)

Identity verification, card re-adds, support calls. Do these when you have
patience, not at 1am.

| | App | Bundle id | Why |
| --- | --- | --- | --- |
| [ ] | Banking | `com.robinhood.release.Money` | Identity verification likely. Budget time. |
| [ ] | Biocare Health | `com.biotricity.biocare` | Identity verification likely. Budget time. |
| [ ] | Capital One | `com.capitalone.enterprisemobilebanking` | Identity verification likely. Budget time. |
| [ ] | Cash App | `com.squareup.cash` | Identity verification likely. Budget time. |
| [ ] | Chase | `com.chase` | Identity verification likely. Budget time. |
| [ ] | Coinbase | `com.vilcsak.bitcoin2` | Identity verification likely. Budget time. |
| [ ] | CVS Health | `com.cvs.cvspharmacy` | Identity verification likely. Budget time. |
| [ ] | Discover | `com.discoverfinancial.mobile` | Identity verification likely. Budget time. |
| [ ] | Fidelity | `com.fidelity.watchlist` | Identity verification likely. Budget time. |
| [ ] | Fly Delta | `com.delta.iphone.ver1` | Identity verification likely. Budget time. |
| [ ] | Govee Home | `com.ihoment.GoVeeSensor` | Identity verification likely. Budget time. |
| [ ] | M&T Bank | `com.mtb.mbanking10` | Identity verification likely. Budget time. |
| [ ] | PayPal | `com.yourcompany.PPClient` | Identity verification likely. Budget time. |
| [ ] | RENPHO Health | `com.renpho.health` | Identity verification likely. Budget time. |
| [ ] | Robinhood | `com.robinhood.release.Robinhood` | Identity verification likely. Budget time. |
| [ ] | Schwab | `com.schwab.schwabmobile` | Identity verification likely. Budget time. |
| [ ] | United | `com.united.UnitedCustomerFacingIPhone` | Identity verification likely. Budget time. |
| [ ] | Venmo | `net.kortina.labs.Venmo` | Identity verification likely. Budget time. |

## 3. Everything else, alphabetical (319)

`push` marks apps whose Info.plist declares push notifications. Note that is
**capability, not permission**: most apps declare it whether or not you ever
said yes. On this phone 308 of 341 declare it, so the flag is a
weak signal and the Settings > Notifications screenshot below is the real ground
truth for what was actually notifying you.

Still worth knowing per app, because after a reinstall iOS asks once on first
launch. Dismiss that prompt and the app goes silent permanently until you dig
through Settings to fix it.

| | App | Bundle id | Push |
| --- | --- | --- | --- |
| [ ] | ABC | `com.abcdigital.abc.videoplayer` | push |
| [ ] | Abercrombie | `com.abercrombie.anfiphone` | push |
| [ ] | Acorns | `com.acorns.investor` | push |
| [ ] | Action | `com.sportsactioninc.action` | push |
| [ ] | adidas | `com.adidas.app` | push |
| [ ] | Affirm | `com.affirm.recharge` | push |
| [ ] | Airbnb | `com.airbnb.app` | push |
| [ ] | AllTrails | `com.alltrails.AllTrails` | push |
| [ ] | Amazon | `com.amazon.Amazon` | push |
| [ ] | Amazon Alexa | `com.amazon.echo` | push |
| [ ] | American | `com.aa.AmericanAirlines` | push |
| [ ] | Ami | `com.w00w00.ami` | push |
| [ ] | Amtrak | `com.amtrak.rider` | push |
| [ ] | Apollo Lighting | `com.QH.Apollo` |  |
| [ ] | Apple Store | `com.apple.store.Jolly` | push |
| [ ] | ASUS Router | `com.asus.asusrouter` | push |
| [ ] | Audible | `com.audible.iphone` | push |
| [ ] | Ballpark | `com.mlb.AtTheBallpark` | push |
| [ ] | Bangkok Airways | `com.ng.bangkokAirways` | push |
| [ ] | Beli | `beliapp` | push |
| [ ] | Bend | `com.bowery-digital.bend` | push |
| [ ] | Best Buy | `com.bestbuy.buyphone` | push |
| [ ] | bet365 | `com.bet365.bet365NJ` | push |
| [ ] | BetMGM Sports | `com.playmgm.nj.sports2` | push |
| [ ] | Betr | `app.instabet.betr` | push |
| [ ] | BetRivers | `com.rushstreetinteractive.ri` | push |
| [ ] | BetterHelp | `com.ionicframework.betterhelp369708` | push |
| [ ] | Bevel | `com.supersethealth.superset` | push |
| [ ] | Bezel | `com.bezel.bezel` | push |
| [ ] | Bitmoji | `com.bitstrips.imoji` | push |
| [ ] | Bleacher Report | `com.bleacherreport.TeamStream` | push |
| [ ] | Blockchain | `com.rainydayapps.Blockchain` | push |
| [ ] | Bloomberg | `com.bloomberg.Bloomberg` | push |
| [ ] | Bounce | `com.usebounce.app` | push |
| [ ] | Branch | `com.jomaguy.Branch` | push |
| [ ] | Buffalo Wild Wings | `com.blazinrewards` | push |
| [ ] | Calm | `com.calm.calmapp` | push |
| [ ] | Can of Soup | `com.emittance.mimetype` | push |
| [ ] | Canva | `com.canva.canvaeditor` | push |
| [ ] | Canvas | `com.instructure.icanvas` | push |
| [ ] | CBS Sports | `H443NM7F8H.CBSSportsApp` | push |
| [ ] | ChatGPT | `com.openai.chat` | push |
| [ ] | Chess | `com.chess.iphone` | push |
| [ ] | Chick-fil-A | `com.engauge.Chick-fil-A` | push |
| [ ] | Chime | `com.1debit.ChimeProdApp` | push |
| [ ] | Chipotle | `com.chipotle.Chipotle` | push |
| [ ] | Chrome | `com.google.chrome.ios` | push |
| [ ] | Chuck | `com.410labs.AppStore.Chuck` | push |
| [ ] | Cinemark | `com.cinemark.cinemarkapp` | push |
| [ ] | Citi Bike | `com.citibikenyc.citibike` | push |
| [ ] | Citi Mobile | `com.citigroup.citimobile` | push |
| [ ] | Clash of Clans | `com.supercell.magic` | push |
| [ ] | Clash Royale | `com.supercell.scroll` | push |
| [ ] | Claude | `com.anthropic.claude` | push |
| [ ] | CLEAR | `com.clearme.Clear` | push |
| [ ] | Clips | `com.apple.clips` | push |
| [ ] | CNN | `com.cnn.iphone` | push |
| [ ] | Columbia | `com.guidebook.apps.ColumbiaCCSEAS` | push |
| [ ] | Connect | `com.apple.AppStoreConnect` | push |
| [ ] | Connect | `com.garmin.connect.mobile` | push |
| [ ] | Copilot | `com.copilot.production` | push |
| [ ] | Costco | `com.costco.costco` | push |
| [ ] | Credit Karma | `com.creditkarma.mobile` | push |
| [ ] | Crunch | `com.ideawork.icrunch` | push |
| [ ] | Crunchyroll | `com.crunchyroll.iphone` | push |
| [ ] | Curb | `com.ridecharge.TaxiMagic` | push |
| [ ] | Dasher | `com.doordash.dasher` | push |
| [ ] | DataCamp | `com.datacamp` | push |
| [ ] | Deliveroo | `com.deliveroo.orderapp` | push |
| [ ] | Developer | `developer.apple.wwdc-Release` | push |
| [ ] | Devmaxx | `com.mccandless.TheDailyDev` | push |
| [ ] | DICE | `fm.dice.Dice` | push |
| [ ] | Discord | `com.hammerandchisel.discord` | push |
| [ ] | Disney+ | `com.disney.disneyplus` | push |
| [ ] | Dispo | `app.davidsdisposable.davids-disposable-ios` | push |
| [ ] | Docs | `com.google.Docs` |  |
| [ ] | Domino's | `com.dominos.iphone` | push |
| [ ] | DoorDash | `doordash.DoorDashConsumer` | push |
| [ ] | Dos Toros | `com.dostoros.dostoros.ios` | push |
| [ ] | DraftKings | `com.draftkings.sportsbook` | push |
| [ ] | Drive | `com.google.Drive` | push |
| [ ] | Dropbox | `com.getdropbox.Dropbox` | push |
| [ ] | Dunkin' | `com.dunkinbrands.otgo` | push |
| [ ] | Duolingo | `com.duolingo.DuolingoMobile` | push |
| [ ] | Einstein Bros. Bagels | `com.ebb.ebbapp` | push |
| [ ] | Enterprise | `com.enterprise.eracmobile` | push |
| [ ] | ESPN | `com.espn.ScoreCenter` | push |
| [ ] | ESPN TC | `com.espn.tcmen` | push |
| [ ] | Eventbrite | `com.eventbrite.attendee` | push |
| [ ] | Expedia | `com.expedia.booking` | push |
| [ ] | Expo Go | `host.exp.Exponent` | push |
| [ ] | Express Scripts | `com.medco.medcopharmacy` | push |
| [ ] | Facebook | `com.facebook.Facebook` | push |
| [ ] | Fanatics Sports & Casino | `com.fbg.sportsbook` | push |
| [ ] | Fandango | `com.fandango.fandango` | push |
| [ ] | FanDuel | `com.fanduel.sportsbook` | push |
| [ ] | FanDuel Casino | `com.fanduel.casino` | push |
| [ ] | Fantasy | `com.draftkings.dknativermg` | push |
| [ ] | Fantasy | `com.espn.fantasyFootball` | push |
| [ ] | Farfetch | `com.farfetch.discover` | push |
| [ ] | FedEx | `com.fedex.mobile.home` | push |
| [ ] | Fetch | `com.FetchRewards.HopBeta` | push |
| [ ] | Figma | `com.figma.FigmaMirror` | push |
| [ ] | Finimize | `com.finimize.oban` | push |
| [ ] | Fitbod | `com.fitbod` | push |
| [ ] | Five Guys | `com.fiveguys.mobile` | push |
| [ ] | Flappy Dunk | `com.acidcousins.fdunk` |  |
| [ ] | Fliff | `com.fliff.app` | push |
| [ ] | Foot Locker | `com.footlocker.approved` | push |
| [ ] | Forever 21 | `com.forever21.Forever21` | push |
| [ ] | FotMob | `com.mobilefootie.fotmobpro` | push |
| [ ] | FOX One | `com.fox.foxone` | push |
| [ ] | FOX Sports | `com.uie.foxsports` | push |
| [ ] | Frenzy | `com.jadedlabs.frenzy` | push |
| [ ] | G2G | `com.g2g.www` | push |
| [ ] | GarageBand | `com.apple.mobilegarageband` | push |
| [ ] | Gemini | `com.google.gemini` | push |
| [ ] | GetIn | `com.getin.app` | push |
| [ ] | GitHub | `com.github.stormbreaker.prod` | push |
| [ ] | Gmail | `com.google.Gmail` | push |
| [ ] | GNC LiveWell | `com.gnc.GNC` | push |
| [ ] | GO | `com.dena.automotive.taxibell` | push |
| [ ] | GO Raid Party | `net.tinywhale.Remote` | push |
| [ ] | GOAT | `com.airgoat.goat.ios` | push |
| [ ] | Google | `com.google.GoogleMobile` | push |
| [ ] | Google Calendar | `com.google.calendar` | push |
| [ ] | Google Home | `com.google.Chromecast` | push |
| [ ] | Google Maps | `com.google.Maps` | push |
| [ ] | Gopuff | `com.gopuff.gopuff` | push |
| [ ] | Grab | `com.grabtaxi.iphone` | push |
| [ ] | Gradescope | `com.gradescope.student` | push |
| [ ] | Grok Bot | `co.anysphere.sand` | push |
| [ ] | GroupMe | `com.groupme.iphone-app` | push |
| [ ] | Grubhub | `com.grubhub.search` | push |
| [ ] | H&M | `com.hm.goe` | push |
| [ ] | Habitica | `com.habitrpg.ios.Habitica` | push |
| [ ] | Handshake | `com.joinhandshake.Handshake.student` | push |
| [ ] | HBO Max | `com.wbd.stream` | push |
| [ ] | Hello Weather | `hello-weather-app` | push |
| [ ] | Hertz | `com.hertz.HertzDigital` | push |
| [ ] | hims | `com.himshers.ios` | push |
| [ ] | Hollister | `com.abercrombie.hollister` | push |
| [ ] | Home Connect | `com.bshg.homeconnect.na` | push |
| [ ] | Home Depot | `com.thehomedepot.homedepot` | push |
| [ ] | HondaLink | `com.honda.hondalink.connect` | push |
| [ ] | Hotels.com | `com.hotels.HotelsNearMe` | push |
| [ ] | Hotspots | `com.comcast.xwifi` | push |
| [ ] | Hudl | `com.hudl.modi` | push |
| [ ] | Hulu | `com.hulu.plus` | push |
| [ ] | IcyBox | `io.icybox.icybox` | push |
| [ ] | IKEA | `com.ingka.ikea.app` | push |
| [ ] | iMovie | `com.apple.iMovie` | push |
| [ ] | Instacart | `com.instacart` | push |
| [ ] | Instagram | `com.burbn.instagram` | push |
| [ ] | IRONMAN | `me.rtrt.app.irma` | push |
| [ ] | iTunes U | `com.apple.itunesu` | push |
| [ ] | JapanTravel | `com.navitime.inbound.commerce` | push |
| [ ] | JBL Portable | `com.jbl.connect` |  |
| [ ] | JetBlue | `com.jetblue.jetBlueiPhone` | push |
| [ ] | Just Salad | `com.justsalad.justsalad.ios` | push |
| [ ] | Kahoot! | `no.mobitroll.kahoot.controller` | push |
| [ ] | Keepsmile | `com.KS.KSLights` | push |
| [ ] | Keynote | `com.apple.Keynote` | push |
| [ ] | Klarna | `com.klarna.app` | push |
| [ ] | Kohl's | `com.kohls.mcommerce.iphone` | push |
| [ ] | LA Fitness | `com.lafitness.lafitness` | push |
| [ ] | LeanBites | `com.ChorusLabs.LeanBites` | push |
| [ ] | Letterboxd | `com.letterboxd.LetterboxdApp` | push |
| [ ] | Levi's | `com.levistrauss.customer` | push |
| [ ] | Lock In | `com.aclo.lockin` | push |
| [ ] | Lowe's | `com.lowes.mobile.consumer.iphone.lowes` | push |
| [ ] | lululemon | `com.lululemon.shopapp` | push |
| [ ] | Lyft | `com.zimride.instant` | push |
| [ ] | MacroFactor | `com.sbs.diet` | push |
| [ ] | Macy's | `macys.ishop` | push |
| [ ] | Madewell | `com.madewell.madewell` | push |
| [ ] | MC NYC | `com.ezaccessapp.mcnyc` | push |
| [ ] | MEGA | `mega.ios` | push |
| [ ] | MileagePlus X | `com.mileageplus.mpx` | push |
| [ ] | MLB | `com.mlb.AtBatUniversal` | push |
| [ ] | MM Live | `com.turner.mmod2011temp` | push |
| [ ] | Motion | `com.usemotion.motion` | push |
| [ ] | Motivation | `com.MonkeyTaps.Motivation` | push |
| [ ] | mSecure | `com.mseven.msecure5` | push |
| [ ] | My Verizon | `com.vzw.hss.myverizon` | push |
| [ ] | MyFitnessPal | `com.myfitnesspal.mfp` | push |
| [ ] | NBA | `com.nbaimd.gametime.universal` | push |
| [ ] | NBC | `com.nbcuni.nbc.portal` | push |
| [ ] | NBC Sports | `com.nbcuni.com.nbcsports.liveextra` | push |
| [ ] | Netflix | `com.netflix.Netflix` | push |
| [ ] | NFL | `com.nfl.gamecenter` | push |
| [ ] | Nike | `com.nike.omega` | push |
| [ ] | Nordstrom | `com.nordstrom.shopping` | push |
| [ ] | Nordstrom Rack | `com.nordstrom.rack` | push |
| [ ] | NordVPN | `com.nordvpn.NordVPN` | push |
| [ ] | Notability | `com.gingerlabs.Notability` | push |
| [ ] | Notion | `notion.id` | push |
| [ ] | Notion Calendar | `com.cron.calendar` | push |
| [ ] | Numbers | `com.apple.Numbers` | push |
| [ ] | NYCRUNS | `me.rtrt.app.nycra` | push |
| [ ] | NYT Games | `com.magmic.NYTCrosswords09` | push |
| [ ] | NYTimes | `com.nytimes.NYTimes` | push |
| [ ] | NYU Langone | `org.nyulmc.clinical.mychart` | push |
| [ ] | Office Depot | `com.officedepot.OfficeDepotApp` | push |
| [ ] | OneDrive | `com.microsoft.skydrive` | push |
| [ ] | Opal | `com.withopal.opal` | push |
| [ ] | OpenTable | `com.contextoptional.OpenTable` | push |
| [ ] | Organizer | `com.eventbrite.app1` | push |
| [ ] | Outlook | `com.microsoft.Office.Outlook` | push |
| [ ] | Pages | `com.apple.Pages` | push |
| [ ] | Paramount+ | `com.cbsvideo.app` | push |
| [ ] | Partiful | `com.partiful.partiful` | push |
| [ ] | Patreon | `com.patreon.iphone` | push |
| [ ] | Peacock | `com.peacocktv.peacock` | push |
| [ ] | Perplexity | `ai.perplexity.app` | push |
| [ ] | PhotoCircle | `com.circle38.photocircle` | push |
| [ ] | Pick6 | `com.draftkings.picksix` | push |
| [ ] | Pinterest | `pinterest` | push |
| [ ] | PL | `com.premierleague.main` | push |
| [ ] | PlugShare | `com.xatori.plugshare` | push |
| [ ] | Poke Genie | `com.can-jin.pokegenie` | push |
| [ ] | Pokémon GO | `com.nianticlabs.pokemongo` | push |
| [ ] | Pokémon TCGP | `jp.pokemon.pokemontcgp` | push |
| [ ] | Poll Everywhere | `com.polleverywhere.mobile` |  |
| [ ] | Polymarket | `com.polymarket.ios-app` | push |
| [ ] | Posh | `com.poshgroup.POSH` | push |
| [ ] | Postmates | `com.postmates.getitnow` | push |
| [ ] | Pret | `com.pret.mobile.prod` | push |
| [ ] | Prime Video | `com.amazon.aiv.AIVApp` | push |
| [ ] | Privacy | `com.privacy.paybeta` | push |
| [ ] | PrizePicks | `com.myprizepicks.prizepicks` | push |
| [ ] | PS App | `com.playstation.eu.playstationadhoc` | push |
| [ ] | PureGym US | `com.innovatise.blinkholdingsinc` | push |
| [ ] | PurePoker | `com.purepoker.world.app` | push |
| [ ] | Real | `vg.real` | push |
| [ ] | Reddit | `com.reddit.Reddit` | push |
| [ ] | Regal | `com.regalcinemas.regalmovietheatersapp` | push |
| [ ] | Resy | `com.resy.ResyApp` | push |
| [ ] | Rocket Money | `com.truebill.truebillnative` | push |
| [ ] | SeatGeek | `com.seatgeek.SeatGeek` | push |
| [ ] | Shake Shack | `com.halickman.ShackHQ` | push |
| [ ] | Shazam | `com.shazam.Shazam` | push |
| [ ] | Sheets | `com.google.Sheets` |  |
| [ ] | SHEIN | `zzkko.com.ZZKKO` | push |
| [ ] | Shop | `com.jadedlabs.arrive` | push |
| [ ] | Shopper | `com.instacart.shopper` | push |
| [ ] | Shopping | `com.wikibuy.prod.main` | push |
| [ ] | Sidechat | `com.flowerave.sidechat` | push |
| [ ] | Skyscanner | `net.skyscanner.iphone` | push |
| [ ] | Slack | `com.tinyspeck.chatlyio` | push |
| [ ] | Sleeper | `com.blitzstudios.sleeperbot` | push |
| [ ] | Slides | `com.google.Slides` |  |
| [ ] | smartEX App | `jp.co.jr-central.exreserve.overseas` | push |
| [ ] | Snapchat | `com.toyopagroup.picaboo` | push |
| [ ] | Sofascore | `com.SofaScore.iOS` | push |
| [ ] | SoFi | `com.sofi.mobile` | push |
| [ ] | SoundCloud | `com.soundcloud.TouchApp` | push |
| [ ] | Splitwise | `com.Splitwise.SplitwiseMobile` | push |
| [ ] | SpotHero | `com.spothero.spothero` | push |
| [ ] | Spotify | `com.spotify.client` | push |
| [ ] | Stage Timer | `com.msdc.stagetime` |  |
| [ ] | Staples | `com.staplesconnect.retailmobile.StaplesConnectApp` | push |
| [ ] | Starbucks | `com.starbucks.mystarbucks` | push |
| [ ] | stats.fm | `dev.netlob.spotistats` | push |
| [ ] | StockX | `com.Campless.Campless` | push |
| [ ] | Strava | `com.strava.stravaride` | push |
| [ ] | Stripe | `com.stripe.dashboard` | push |
| [ ] | StubHub | `com.stubhub.stubhub` | push |
| [ ] | Support | `com.apple.supportapp` | push |
| [ ] | swipewipe | `com.aoklab.fewerphotos` | push |
| [ ] | Tabelog | `com.kakaku.tabelog.tourists` | push |
| [ ] | Target | `com.target.Target` | push |
| [ ] | Teams | `com.microsoft.skype.teams` | push |
| [ ] | Temu | `com.einnovation.temu` | push |
| [ ] | TestFlight | `com.apple.TestFlight` | push |
| [ ] | theScore | `iphone.thescore.com` | push |
| [ ] | theScore Bet | `com.espn.bet` | push |
| [ ] | Threads | `com.burbn.barcelona` | push |
| [ ] | Ticketmaster | `com.ticketmaster.ios.TicketmasterApp` | push |
| [ ] | TickPick | `com.tickpick.tickpickapp` | push |
| [ ] | TikTok | `com.zhiliaoapp.musically` | push |
| [ ] | TNT | `com.turner.TNT` | push |
| [ ] | TrainTime | `com.mta.mobileapp` | push |
| [ ] | Trello | `com.fogcreek.trello` | push |
| [ ] | Trip.com | `com.ctrip.EBooking` | push |
| [ ] | Turo | `com.relayrides.ios.RelayRides` | push |
| [ ] | Twitch | `tv.twitch` | push |
| [ ] | Uber | `com.ubercab.UberClient` | push |
| [ ] | Uber Eats | `com.ubercab.UberEats` | push |
| [ ] | Under Armour | `com.underarmour.shop` | push |
| [ ] | Underdog | `com.underdogsports.fantasy` | push |
| [ ] | UPS | `com.ups.m.iphone` | push |
| [ ] | USPS Mobile | `com.usps.uspsmobile` |  |
| [ ] | Vinted | `lt.manodrabuziai.fr` | push |
| [ ] | Vrbo | `com.vrbo.traveler` | push |
| [ ] | VSCO | `co.visualsupply.cam` | push |
| [ ] | Walgreens | `com.usablenet.walgreens` | push |
| [ ] | Wallet​ | `org.toshi.distribution` | push |
| [ ] | Walmart | `com.walmart.electronics` | push |
| [ ] | WalterPicks | `com.walterpicks.picksapp` | push |
| [ ] | Waterllama | `com.vitalii.water` | push |
| [ ] | Wawa | `com.wawa.wawaapp` | push |
| [ ] | Waze | `com.waze.iphone` | push |
| [ ] | Wellhub | `com.gympass.gympass` | push |
| [ ] | Wetherspoon | `com.jdwetherspoon.jdwetherspoon` | push |
| [ ] | WHOOP | `com.whoop.iphone` | push |
| [ ] | Wispr Flow | `com.wispr.flowapp` | push |
| [ ] | wordreference | `com.wordreference.WordReferenceDictionary` |  |
| [ ] | WSJ | `com.dowjones.WSJ.ipad` | push |
| [ ] | X | `com.atebits.Tweetie2` | push |
| [ ] | XBOX | `com.microsoft.smartglass` | push |
| [ ] | Xfinity | `com.xfinity.digitalhome` | push |
| [ ] | Yazio | `com.yazio.ios.YAZIO` | push |
| [ ] | YouTube | `com.google.ios.youtube` | push |
| [ ] | YouTube TV | `com.google.ios.youtubeunplugged` | push |
| [ ] | ZARA | `com.inditex.zara.iphone` | push |
| [ ] | ZENGGE | `com.Zhengji.LedBLEAdvanced.BLE` |  |
| [ ] | Zillow | `com.zillow.ZillowMap` | push |
| [ ] | Zoom | `us.zoom.videomeetings` | push |

## Manual captures worth taking before the erase

The app list is data. These are not, and screenshots take two minutes.

- [ ] **Every Home Screen page.** This is your layout, and nothing restores it.
- [ ] **Settings > Notifications.** Shows every app and its current state. This
      is the ground truth for rebuilding your notification setup.
- [ ] **Settings > Focus**, and each Focus's allowed apps and people.
- [ ] **Settings > [your name] > Subscriptions.** What you pay for and when.
- [ ] **Wallet.** Which cards and passes, so you know what to re-add.
- [ ] **Settings > General > VPN & Device Management**, if anything lives there.
- [ ] **Settings > Apps > Default Apps**, browser and mail defaults.
- [ ] **Control Center layout.**
- [ ] **Settings > Privacy & Security > Location Services**, the per-app states.

AirDrop the screenshots to the Mac before erasing, not to iCloud Photos, so they
are readable while the phone is mid-setup.
