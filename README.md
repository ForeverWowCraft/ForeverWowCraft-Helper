# ForeverWowCraft Helper

The addon for World of Warcraft: Forever, and the small program that runs beside the game.
Together they show you, in game, what your professions still need, less what you already have
(`/fwc`), and they record what the auction house lists and send it on, which is where the prices
come from.

It is plain Python 3.10+ with nothing to install, and a WoW addon. MIT licence.

## What it does

| | |
|---|---|
| **The addon** (`addon/ForeverWowCraftScanner`) | `/fwc`: the cheapest route for each profession from your skill on, with what you have (bags, bank, mail, your own auctions) taken off, across your characters if you like. A **Make** button on the game's profession panel crafts that route a step at a time, and says what to buy or learn when it cannot, with an arrow to the nearest trainer, vendor or anvil: the addon comes with the vanilla world's (`Seed.lua`, data from the VMaNGOS database, GPL-2.0, apart from the addon's MIT code) and notes the ones it sees you at. At the auction house a shopping list buys what the step needs, a click and a confirm an item. And it records the auction house's prices, by itself, whenever you open it and it can (once every 15 minutes): a small button on the auction house frame lights up when there is something to save, and that click is all it asks. Nothing of yours is sent: prices only |
| **`fwch.py`** | Finds the game, installs the addon, reads what it saved, sends it through the pipe, and writes the lists and the routes it is given into the addon |

```
python fwch.py where            what was found on this PC
python fwch.py install-addon    copy the addon into the game
python fwch.py status           what the saved scans hold
python fwch.py send --watch     send every scan, after each SAVE in game
python fwch.py autostart        have send.cmd start, minimised, when you log on (--off undoes it)
python fwch.py lists            fetch the lists to scan and write them into the addon
python fwch.py plans            fetch your auction houses' routes and write them into the addon
python fwch.py fresh            when each auction house was last scanned by anyone; the addon shows no scan box while that is fresh
                                ("the site's routes need helper X or newer": unzip the new helper over this one)
```

## Setting up

1. Unzip somewhere permanent, e.g. `C:\ForeverWowCraft-Helper`. Nothing needs installing: the
   zip has Python inside (`python\`, python.org's own build). A zip made without it
   (`--no-python`) uses the PC's Python, 3.10 or newer, and `setup.cmd` says so when there is none.
2. Close the game. In the helper's folder, run `setup.cmd`. It finds the game, installs the
   addon, fetches the lists to scan and the routes, and starts `send.cmd` in a minimised window.
3. Start the game. `/fwc` opens the window. Open the auction house now and then: the prices
   are recorded by themselves, the button on its frame lights up, and clicking it saves them;
   `send.cmd` then sends them. (Interface, AddOns, ForeverWowCraft has the switches, among
   them the scanner's own bar for running scans by hand.)

Every line the window prints starts with the date and time, and each auction house in the
scan file is sent on its own: one the service does not take (`not sent, <house>: ...`) does
not hold the others back, and is tried again. A scan is sent once: the helper remembers what
it sent (`state/sent.json`) by what the scan says, so an update of the helper does not send it
again.

`send.cmd` starts by itself when you log on to Windows from then on, minimised: a
"ForeverWowCraft Helper" window on the taskbar. Close it to stop sending until the next logon;
`python fwch.py autostart --off` stops it from starting at all. Running `send.cmd` while one is
already open does nothing, so it is safe to double-click it to be sure.

Nothing has to be asked for. The first time it talks to the pipe the helper is given a name
and a token of its own, kept in `state/identity.json`. `python fwch.py whoami` shows the name.

If you had the addon under its old name, ForeverCraft Scanner, `setup.cmd` replaces it and
carries its saved scans over.

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
(every minute while `send.cmd` runs, or `python fwch.py plans`) and writes them into the
addon, which reads them at the next `/reload`, SAVE or login. The first time, the helper does
not know your characters yet: log in once, `/reload`, and the routes are there after the next.
An auction house nobody has scanned has no routes; scanning it (below) makes them.

One scan of an auction house in ten minutes is all the site needs, however many play there, so
the pipe takes one and refuses the rest as not needed; the helper sends none it would refuse
("not needed: ... was scanned by someone 4 min ago"), and every five minutes writes into the
addon (`Fresh.lua`) when each house was last scanned, so that the FULL / SCAN box stays away
while a scan is not needed.

## In game: scanning

Open the auction house. A blue **FULL** box appears: click it, and when it turns green, click
**SAVE**. That reloads the interface, which is what makes the game write the scan to disk.
`/fwcs` lists the addon's commands.

A realm has two auction houses that are scanned: your faction's and the other faction's. Scans
are kept and sent by auction house. The one both factions share, in Booty Bay, Gadgetzan and
Everlook, is not scanned (it is thin, and the routes buy to level): the addon tells it by where
you stand, says so in chat when you open it, and FULL and SCAN say so instead of scanning.
`/fwcs house` shows what it takes the open one for; `/fwcs house neutral` (or `alliance`,
`horde`) overrules it, `/fwcs house auto` undoes that.

Connected realms share one auction house, and the addon scans it as one, whichever of the
realms your character is on: it is named by the group's first realm as the client spells it
without spaces (the beta's "Classic Beta PvE" and "Classic Beta PvE 2" are one house, kept as
`ClassicBetaPvE`). The site shows the realm's name as the game does.

The addon does nothing by itself: every scan and every save is a click.

## Settings

Environment variables. On Windows, `setx NAME value` saves one for good.

| Setting | For |
|---|---|
| `FWC_WOW_DIR` | The "World of Warcraft" folder, when it is not found |
| `FWC_WOW_FLAVOR` | The client folder inside it, e.g. `_classic_beta_` |
| `FWC_PIPE_URL` | Another pipe to send to |
| `FWC_SITE_URL` | Another site to fetch the routes from |
| `FWC_PIPE_TOKEN` | A token you were given by hand, used in place of the helper's own |

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

## Tests

```
python tests/test_scan.py
python tests/test_pipe.py
python tests/test_factions.py
python tests/test_old_names.py
python tests/test_independent.py
python tests/test_plans.py
python tests/test_ingame.py
python tests/lua_check.py addon/ForeverWowCraftScanner/ForeverWowCraftScanner.lua
```

`test_ingame.py` runs the addon's Lua against a stand-in for the game, and needs a Lua for
that: `pip install lupa`. Without it, it says so and passes.
