# ForeverWowCraft Helper

The addon for World of Warcraft: Forever, and the small program that runs beside the game.
Together they show you, in game, what your professions still need, less what you already have
(`/fwc`), and they record what the auction house lists and send it on, which is where the prices
come from.

It is plain Python 3.10+ with nothing to install, and a WoW addon. MIT licence. Questions and
help: the Discord, <https://discord.gg/XPt2JUCxAg>. What is sent and what is not: [The pipe](#the-pipe)
below, and <https://www.foreverwowcraft.com/privacy>.

## What it does

| | |
|---|---|
| **The addon** (`addon/ForeverWowCraftScanner`) | `/fwc`: the cheapest route for each profession from your skill on, with what you have (bags, bank, mail, your own auctions) taken off, across your characters if you like. A **Make** button on the game's profession panel crafts that route a step at a time, and says what to buy or learn when it cannot, with an arrow to the nearest trainer, vendor or anvil: the addon comes with the vanilla world's (`Seed.lua`, data from the VMaNGOS database, GPL-2.0, apart from the addon's MIT code) and notes the ones it sees you at. At the auction house a shopping list buys what the step needs, a click and a confirm an item. And it records the auction house's prices, by itself, whenever you open it and it can (once every 15 minutes): a small button on the auction house frame lights up when there is something to save, and that click is all it asks. Nothing of yours is sent: prices only |
| **`fwch.py`** | Finds the game, installs the addon, reads what it saved, sends it through the pipe, and writes the lists and the routes it is given into the addon. On Windows and on the Mac |

```
python fwch.py where            what was found on this PC
python fwch.py install-addon    copy the two addons into the game (--force: over a newer scanner)
python fwch.py status           what the saved scans hold
python fwch.py app              the application: an icon by the clock (Windows) or in the menu bar (Mac) that does all of the below by itself
python fwch.py send --watch     the same sending, in a window (send.cmd)
python fwch.py autostart        have the app start when you log in (--off undoes it)
python fwch.py lists            fetch the lists to scan and write them into the addon
python fwch.py plans            fetch your auction houses' routes and write them into the addon
python fwch.py fresh            when each auction house was last scanned by anyone; the addon waits while that is fresh
                                ("the site's routes need helper X or newer": unzip the new helper over this one)
```

## Setting up

1. Download `ForeverWowCraft-Helper-<version>.msi` and run it. Nothing else needs installing:
   Python is inside (`python\`, python.org's own build). It installs for your own user, under
   `%LOCALAPPDATA%\Programs\ForeverWowCraft Helper`, so Windows asks for no administrator; it
   may warn that the installer is not signed (SmartScreen: "More info", then "Run anyway").
2. The helper starts when the installer is done, and when you log on to Windows from then on:
   an icon by the clock, in the notification area. It finds the game, installs the addon,
   fetches the lists to scan and the routes, and waits. If it cannot find the game, right-click
   the icon and **Choose the game folder**: the "World of Warcraft" folder, the one that holds
   the client folder (`_forever_`).
3. Start the game (if it was running, log out to the character screen and back in: the game finds a new addon there; an updated one needs only `/reload`).
   `/fwc` opens the window. Open the auction house now and then: the prices are recorded by
   themselves, the **Save Prices** button on its frame lights up when there is something to
   save, and that click is all it asks; the helper sends them within seconds. (Interface,
   AddOns, ForeverWowCraft has the switches, among them the scanner's own bar for running
   scans by hand.)

Point at the icon for how things stand: what was last sent, how many auction houses have
routes, or what is wrong. Its menu: **Send prices now**; **Fetch routes now**; **Choose the
game folder**; **Open the log**; **Start with Windows**, ticked when it does (Windows' own
Settings > Apps > Startup has the same switch); **Help**; **Quit**. A balloon comes only when
something needs you: the game not found, the addon not installed, prices that could not be
sent, a `/reload` or a log-out the addon needs. Everything the helper does is in its log, with the date and time at the start of
every line: `%LOCALAPPDATA%\ForeverWowCraft\Helper\helper.log`. The same folder holds the
helper's name and token at the pipe (`identity.json`), what it sent (`sent.json`), and the
routes, lists and freshness it fetched; an uninstall leaves it, so a reinstall is the same
sender. `FWC_STATE` names another folder. One instance runs at a time: starting the helper
again while it runs only says so.

Each auction house in the scan file is sent on its own: one the service does not take
(`not sent, <house>: ...`) does not hold the others back, and is tried again. A scan is sent
once: the helper remembers what it sent by what the scan says, so an update of the helper
does not send it again.

Nothing has to be asked for. The first time it talks to the pipe the helper is given a name
and a token of its own. `python\python.exe fwch.py whoami`, from the install folder, shows
the name.

**Without the installer:** the zip (`ForeverWowCraft-Helper-<date>.zip`, Python inside),
unzipped somewhere permanent, e.g. `C:\ForeverWowCraft-Helper`. `setup.cmd` in it does what
the installer's first run does and starts the same app (`python fwch.py app`), which starts
with Windows from then on (`python fwch.py autostart --off` undoes that). `send.cmd` is the
sending alone, in a window whose every line starts with the date and time. A zip made without
Python (`--no-python`) uses the PC's own, 3.10 or newer, and `setup.cmd` says so when there is
none. A helper from before 1.5.0 kept its state in `state\` beside itself: the first run of
1.5.0 carries that over, so it stays the same sender.

If you had the addon under its old name, ForeverCraft Scanner, the helper replaces it and
carries its saved scans over.

**On a Mac:** download `ForeverWowCraft-Helper-<version>.dmg`, open it, and drag
**ForeverWowCraft Helper** into Applications. Python is inside the application: nothing else to
install. The application is not signed yet (the project's business signs it once it has its
Apple Developer membership), so the first time, macOS says it cannot check it for malware:
System Settings > Privacy & Security, scroll down, **Open Anyway**. Then it is an icon in the
menu bar, at the top right, with the same menu: **Start at login** puts a launch agent in your
Library (System Settings > General > Login Items lists it under "Allow in the Background"). It
looks for the game in `/Applications/World of Warcraft`; **Choose the game folder...** in the
menu is for anywhere else. What the helper keeps is in `~/Library/Application Support/ForeverWowCraft/Helper`:
its log, its name and token at the pipe, and `settings.json` with the folder you chose. The
game is the same client and the same addon folder as on Windows. (Since 1.6.0.)

## In game: what you still need

`/fwc` opens a window with the route for one of your professions, as the site has it for your
realm and faction, from your own skill on:

* **Shopping list**: what the route buys, how many you have, how many are left to buy and
  what that costs. What you have enough of is greyed out.
* **From what you have**: what is taken from what you have, also where it is something
  the route would have made (bolts, bars) rather than bought.
* **Route**, **Make on the way**, **Left to sell**: the crafts from your skill to the top,
  what to make for them, and what is left over at the end.

The row of buttons at the top is the professions, as on the site: the one shown is blue, the
ones you do not have are grey (their whole route shows, from the trainer on). **Also** under
them is a second profession to count, as the site's "also have": your other profession by
itself, or the one you pick. Then the recipes a route may use (a trainer's only, or also
recipes bought from the auction house when they pay off), what the route is **for** (profit:
what you make is sold, and the route is the cheapest once it is; skill-up: nothing is counted
as sold, so it takes the cheapest reagents per skill point and leaves less to list), and
whether your **other characters** of the
same auction house and faction count too: their things as they were when each last played
with the addon. Point at a row to see who has how many, and where. **Auctionator** gives the
shopping list as an Auctionator import string to copy: what is left to buy, or everything
from nothing. The skill slider plans a part of the route, from one end to the other, as the
site's slider does: drag an end or type the number; the list, the costs and the Auctionator
list follow, and **Reset** is your own skill to the route's end. `/fwc from 150`,
`/fwc to 225` and `/fwc also enchanting` do the same by hand; `auto` in place of the value
undoes each. Under the slider, **Gold** is what you have to spend: the gold in your bags, or
an amount you type (`12g 40s`, or `12` for gold) and Enter; the summary says how far up the
route it goes, at the route's prices for what is still to buy, and with the box beside it
ticked the list and the Auctionator import stop there. Selling what you make on the way gets
some of it back, so you will get a little further than it says.

**In the profession panel**, beside every recipe, what making one comes to: what it sells for
at the auction house after the house's cut, less what its reagents cost, at the prices of the
site's last scan of your auction house. Green with a plus when it pays, red when it costs, a
grey `?` when a reagent has never been listed. Point at the number for what is behind it: the
reagents, the sale, the chance that the item sells at all, what a vendor pays otherwise, and
what the route counts it at (the sale weighted by that chance). An enchant makes nothing to
sell, so it shows what its reagents cost.

Bags are counted as they change. The bank, the mail and your own auctions still up are
counted while each is open (the game has no other way to them), so visit each once on each
character; the window says what has not been counted yet and when each last was. Costs are
the route's average prices: when you need fewer, the cheapest auctions go first, so the real
cost is a little lower.

On a game in another language, the items and recipes are named as your game names them, and
so is the Auctionator list (Auctionator finds items by those names). The game only has an
item's name once it has met the item since you logged in: the window asks it for the rest and
they come in a moment, English until then, and the Auctionator box says when some still are.
The window's own words stay English.

The routes come from the site: the helper fetches those of your characters' auction houses
(every minute while the helper runs, or `python fwch.py plans`) and writes them into the
addon, which reads them at the next `/reload` or login (saving prices reloads too). The first
time, the helper does not know your characters yet: log in once, `/reload`, and the routes are
there after the next. An auction house nobody has saved has no routes; saving it (below) makes them.

One scan of an auction house in ten minutes is all the site needs, however many play there, so
the pipe takes one and refuses the rest as not needed; the helper sends none it would refuse
("not needed: ... was scanned by someone 4 min ago"), and every five minutes writes into the
addon (`Fresh.lua`) when each house was last scanned, so that the addon records nothing while
a scan is not needed.

Everything the helper writes into the game (the routes, the lists, the freshness) goes into a
second, tiny addon, **ForeverWowCraft Plans**, which `install-addon` puts beside the scanner and
which loads after it. An update of the scanner from CurseForge replaces the scanner's whole
folder and touches none of it. `install-addon` leaves a scanner newer than its own (CurseForge's)
in place, and `--force` puts its own in anyway.

## In game: recording prices

Open the auction house. A small button at its top right says where things stand: **Scanning...**
while the addon reads the house (it does so by itself when the house opens and it can, once
every 15 minutes, and not while someone else saved the house in the last ten minutes), **Prices
in m:ss** while it waits, and a lit **Save Prices** when there is something to save, with a short
sound once. Click it: the interface reloads, which is what makes the game write the prices to
disk, and the helper sends them within seconds. Nothing leaves the PC
without that click. Point at the button for what it is doing; Interface, AddOns, ForeverWowCraft
has the switches (the scan by itself, the sound, and the scanner's own bar with FULL, SCAN and
SAVE for running scans by hand; `/fwcs` lists the commands).

A realm has two auction houses that are recorded: your faction's and the other faction's.
Prices are kept and sent by auction house. The one both factions share, in Booty Bay, Gadgetzan
and Everlook, is not recorded (it is thin, and the routes buy to level): the addon tells it by
where you stand and says so in chat when you open it. `/fwcs house` shows what it takes the open
one for; `/fwcs house neutral` (or `alliance`, `horde`) overrules it, `/fwcs house auto` undoes
that.

Connected realms share one auction house, and the addon records it as one, whichever of the
realms your character is on: it is kept under the group's first realm as the client spells it
without spaces. The site shows the realm's name as the game does.

## Updating

The helper looks once a day whether a newer release is out (where the newest release's address
on GitHub redirects to; nothing of yours is sent). When one is, it updates by itself: the
installer is downloaded into the helper's state folder, its SHA-256 checked against the one
GitHub publishes for the release (a download that does not match is deleted, not installed),
and installed with nothing shown (a per-user install: no administrator); the helper closes and
is back in a moment, settings and all, and a balloon says once that it was updated. Untick
**Update by itself** in the menu and the update waits instead: the tooltip says a newer one is
out, a balloon says it once, and **Update to 1.6.0...** at the top of the menu installs it (the
installer opens, closes the helper and starts it again). The quiet install's log is
`updates\install.log` in the state folder; one that failed is said once, and that version then
waits in the menu. **Check for an update now** in the menu asks GitHub at once instead of
waiting for the day's look: a balloon says the answer, and a newer helper is installed quietly
right away, whether or not it updates by itself as a rule (since 1.6.8). On the Mac the update
always waits in the menu: it is a disk image to drag.
(By itself since 1.6.0; from the menu since 1.5.5. A helper from before has to be updated by
hand once: the installer from the site's helper page.)
On the Mac the download is the new release's disk image: it opens, the helper quits, and you
drag the new one over the old in Applications and start it again.

## Settings

Environment variables. On Windows, `setx NAME value` saves one for good; on the Mac, the
application reads them from `settings.json` in its state folder too, which is where its menu
saves the game folder.

| Setting | For |
|---|---|
| `FWC_WOW_DIR` | The "World of Warcraft" folder, when it is not found |
| `FWC_WOW_FLAVOR` | The client folder inside it, `_forever_` |
| `FWC_PIPE_URL` | Another pipe to send to |
| `FWC_SITE_URL` | Another site to fetch the routes from |
| `FWC_PIPE_TOKEN` | A token you were given by hand, used in place of the helper's own |
| `FWC_STATE` | Another folder for what the helper keeps (its name and token, what it sent, the routes it fetched, the log) |

## The pipe

Scans go out and lists come back as two small JSON documents, `fwc-scan/1` and `fwc-lists/1`,
over HTTP. `fwchelper/pipe.py` describes both and the requests. Anything that speaks them can
be at the other end.

What is sent: the realm's name and your character's faction, and for each item its name, when
it was scanned, and the prices and quantities listed. Nothing about you, your characters or
who listed what. The name the helper sends under is random, and says nothing about you.

What is not sent: what your characters have. Their bags, banks and skills are counted in the
game, kept in the addon's saved file on your PC, and used there. The helper reads from that
file only which realms and factions your characters are of, to know whose routes to fetch
from the site, and fetching them tells the site nothing but which auction houses.

The pipe holds every sender to a pace: a scan of an auction house every five minutes, which is
more often than the game lets anyone scan. What a new sender sends is used where it agrees
with what others saw of the same auction house.

When the pipe refuses a scan or is down, the helper keeps the scan and tries again: after half
a minute the first time, then twice as long each time, up to every quarter hour, until it goes
through (since 1.5.4). Send now from the tray menu asks at once.

## Tests

```
for t in tests/test_*.py; do python "$t" || exit 1; done
python tests/lua_check.py addon/ForeverWowCraftScanner/*.lua
```

Each test file runs on its own, with nothing installed (`test_ingame.py` runs the addon's Lua
when `lupa` is there, and passes without it). `test_app.py` and `test_tray.py` are the app with
Windows stood in for; `test_installer.py` is what the installer puts in, without building it;
`test_mac.py` is the Mac's side without a Mac: the launch agent, the settings file, the lock,
and what the application bundle holds.

## The installer

`python installer/build.py` makes `ForeverWowCraft-Helper-<version>.msi` (on Windows: it
fetches python.org's embeddable Python and WiX 3.14, checks both against their hashes, gives a
copy of `pythonw.exe` the helper's name and icon, and builds). `installer/helper.wxs` says what
the installer does: a per-user install, a Start Menu entry, the Run entry that starts the app
at logon, "Start the helper now" at the end, and the running app closed before an upgrade or a
removal. A release (a `v<version>` tag) builds it on a Windows runner and puts it on the
GitHub release beside the zips.

`python3 installer/build_mac.py` makes `ForeverWowCraft-Helper-<version>.dmg` on a Mac: the
application bundle (`ForeverWowCraft Helper.app`: the helper's files, a standalone Python from
python-build-standalone fetched and checked against its hash, PyObjC installed into it for the
menu bar, the icon, and a launcher script; `LSUIElement`, so no Dock icon) and a disk image
with a link to Applications beside it. A release builds it on the project's own Mac, a
self-hosted runner, and puts it on the release too. The application is unsigned until the
project's business has an Apple Developer membership (`docs/signing.md` in the core).

`test_ingame.py` runs the addon's Lua against a stand-in for the game, and needs a Lua for
that: `pip install lupa`. Without it, it says so and passes.

## About

A fan project, by players, for the game's players: not affiliated with or endorsed by Blizzard
Entertainment. World of Warcraft is a trademark of Blizzard Entertainment, Inc. The code is MIT
(`LICENSE`), apart from `Seed.lua`, data from the VMaNGOS database under the GPL-2.0, as its
header says. The site, the privacy page and the Discord: <https://www.foreverwowcraft.com>.
