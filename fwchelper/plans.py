"""The routes, in game: fetch what the site publishes for the addon and write it into the addon.

The site has, beside each auction house's pages, one document for the addon:

    <site>/data/houses.json           {"houses": [{"key", "realm", "faction", "realms", "scan_newest", "generated", ...}]}
    <site>/data/<key>/ingame.json     a fwc-plans/1 document

    fwc-plans/1   the routes of one auction house, with the item ids the game goes by
        {"format": "fwc-plans/1", "house": "<key>", "realm": "<as shown>", "faction": "Alliance" | "Horde" | "",
         "realms": ["<every realm that shares the house, in any spelling>", ...],
         "scanned_at": <time>, "generated": <time>,
         "items": {"<item id>": "name", ...},
         "variants": [["<key>", "<label>", "<recipes>", "<focus>"], ...],
         "focus": [["<key>", "<label>"], ...],
         "plans": {"<profession>-<variant>": {
             "profession": "tailoring", "skill_line": 197, "variant": "trainer", "start": 1, "target": 300,
             "net": <copper>, "spent": <copper>, "sold": <copper>, "gaps": [[from, to], ...],
             "steps": [{"from": 1, "to": 50, "recipe": "Bolt of Linen Cloth", "spell": 2963, "crafts": 92,
                        "uses": [[item, units a craft], ...], "makes": [item, units a craft],
                        "per": [crafts expected for each skill point, from "from" on],
                        "buy": [item, ...], "craft": [item, ...],
                        "learn": [recipe item, copper]}, ...],
             "made": {"<item>": [units a craft, [[item, units a craft], ...], spell], ...},
             "buy": {"<item>": [copper a unit, "ah" | "vendor", a vendor's price when one sells it too (since 7 Nov 2026)], ...},
             "camp": [[item, the skill it is first needed at, "Tanning Rack"], ...],
             "sell": {"<item>": copper a unit, ...}, "disenchant": [item, ...]}},
         "also": {"<profession>-<variant>+<companion>": {... the same, "companions": ["<companion>"]}, ...},
         "recipes": {"<spell id>": [reagents' cost, what it makes is worth as the route counts it,
                                    what it sells for if it does sell, the chance that it sells (0 to 1),
                                    what a vendor pays] | false, ...}}

      "recipes" (since 7 Oct 2026; may be absent) is what making one of each recipe of every
      profession comes to, in copper, at the prices of the profit route: the reagents at the
      auction house or the vendor, or made where that is cheaper, and what it makes valued as
      the route sells it: the auction price after the cut, weighted by the chance that it
      sells, the vendor's price otherwise. Since 12 Oct 2026 three more: the plain sale (the
      auction price after the cut, or the vendor's where nothing is listed), the chance, and
      the vendor's price; a document from before has the first two. The addon shows the plain
      sale less the reagents beside each recipe in the game's profession panel, and the rest
      in the tooltip. `false` is a recipe with a reagent nothing prices.

      "also" (since 6 Oct 2026; may be absent) holds the routes that a second profession the
      character has changes: an enchanter's tailoring route disenchants, say. Only a route that
      differs from the plain one is there. A variant (since 7 Oct 2026 with four parts; two
      before) is the recipes a route may use ("trainer", "plans") times what it is for
      ("focus": "profit", where what is made is sold, or "skill", where nothing is), and
      "focus" lists the labels of the latter. Since 2 Nov 2026 every route may buy recipes:
      the recipes part is "plans" throughout and the label is the focus's. A document without
      "focus" has the profit routes alone. A step is a run of skill points gained with one recipe: "from" is the skill it starts at,
      "to" the skill it ends at. "makes" is absent when the recipe makes no item (an enchant).
      Of what a step uses, "buy" names what the route buys for it and "craft" what it makes on
      the spot ("made" says how: units a craft, what a craft uses, and since 11 Oct 2026 the
      recipe's spell, which the addon's Make button crafts by); the rest comes from what earlier steps made. "learn" is a
      recipe the route buys before this step. "buy" and "sell" of the plan are what the route
      pays and gets for one, on average: an estimate once fewer are bought or sold.

      "convert" (since 1.8.4; an enchanting plan's, may be absent) is {"<item made>": [item used, units used,
      units made, spell]}: an essence of one kind made from the other by using the item, both ways for every
      essence the route uses (three Lesser Magic Essence into one Greater, one Greater into three Lesser). A
      conversion the route makes is in "made" too, without a spell: it is no recipe of the profession's window.
      The addon counts what is held of either kind against what a step needs and says when to split or combine.
      One that is not usable is left out of the document (check_plans), the route kept.

The addon reads Plans.lua, the same data as a Lua table (FWCS_PLANS[<key>]), at the next /reload
or login, with FWCS_PLANS_WRITTEN = when the helper last wrote or touched it (the addon says,
quietly, when the helper is not installed or has not run for days). It takes from a
route what the character has, in the game: nothing of what a character has is sent anywhere. Which houses are fetched is told from the characters the
addon has seen (FWCS_DB.__chars) and the auction houses it has scanned.

The fishing route (since 1.8.0). Cooking has one more route, "Fishing only", which levels with fish the
player catches, a vendor's goods and a vendor's recipe scrolls and nothing from the auction house. It is the
same for every house of a faction, so the site keeps one copy in each Alliance or Horde house's folder,
`extra/cooking-fishing.ingame.json` (the house's entry in houses.json says `"fishing": true`), and it is NOT
in ingame.json: a helper or an addon from before reads any buy source but "vendor" as the auction house.
The helper fetches it once for a faction and writes it into Plans.lua as a second global,

    FWCS_ROUTES = {["Alliance"] = <a plan as above, with the names of its items>, ...}

which no earlier addon reads. The plan has "kind": "fishing", buy rows with the source "catch" (the fish; the
price is a weight, not copper), "catch" {fish: [[zone, chance], ...]} (the Classic-era world's zones),
"sold_by" {scroll: where}, "names" {item: name} and "notes" [[skill, text, kind], ...].

What the window says when it is empty (since 1.8.0). Two more globals, written after everything above, so that
the text before them is what it was, and which no earlier addon reads:

    FWCS_SITE = { at = <time>, houses = { {"uspve", "Alliance"}, {"uspve", "Horde"}, ... } }

the auction houses the site lists with routes for the addon (houses.json, `"ingame": true`) as the addon compares
them (`spelt` of the house's "realm" field, so Inventory.lua's Ruled() finds its house in it) and the faction, and
when the helper looked. With it the window tells a house the site has but this file lacks (reload) from one the site
has no routes for. A file an earlier helper wrote has none: the next look adds it (`touch` does, with no fetch).

    FWCS_PLANS_PROBLEM = { at = <time>, kind = "reach" | "update" | "unusable" }

there only while the last look for routes failed: "reach" (the site could not be read), "update" (its routes need a
newer helper), "unusable" (it served what could not be used). Nothing else of the error is written (no address, no
text, no path). The next look that works (`write` or `touch`) removes it. With no kept Plans.lua yet, a failed first
look writes a minimal one (the comment lines, the stamp, `FWCS_PLANS = {}` and the problem), and the next look
fetches all the same.

The house's lowest prices (since 1.8.4). Beside ingame.json each house's folder has

    <site>/data/<key>/prices.json     a fwc-prices/1 document (its entry in houses.json says "prices": true)

    fwc-prices/1   {"format": "fwc-prices/1", "house": "<key>", "at": <time>, "generated": <time>,
                    "prices": {"<item id>": the lowest unit price listed, ...},
                    "seen": {"<item id>": when it was scanned, for an item scanned well before "at"}}

the lowest single listing of every item the house's scans saw listed, for the addon's item tooltips. A file of its own, so that
the routes do not hang on it: one that is not usable (larger than MAX_PRICE_BYTES, more than MAX_PRICE_ITEMS items, an id or a
price that is not a whole number in bounds, another house's) is left out, said once in the log (`DROPPED`), and the routes
are written all the same. It is written into Plans.lua as one more global, after FWCS_ROUTES and before FWCS_SITE,

    FWCS_PRICES = {["<key>"] = {at = <time>, prices = {[item] = copper, ...}, seen = {[item] = <time>, ...}}, ...}

which no earlier addon reads; with no price list the text is what it was before.

Times are unix seconds, money is copper.
"""
from __future__ import annotations
import gzip
import io
import json
import math
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__, luatable, scan, settings
from .scan import FACTIONS

PLANS_FORMAT = "fwc-plans/1"
PLANS_GLOBAL = "FWCS_PLANS"
SITE_GLOBAL = "FWCS_SITE"         # the houses the site lists with routes for the addon (since 1.8.0)
PROBLEM_GLOBAL = "FWCS_PLANS_PROBLEM"      # there only while the last look failed (since 1.8.0)
ROUTES_GLOBAL = "FWCS_ROUTES"     # the routes that are one for a whole faction, beside FWCS_PLANS (since 1.8.0): {"Alliance": a plan, ...}
FISHING_FILE = "extra/cooking-fishing.ingame.json"      # in a house's folder on the site; its entry in houses.json says "fishing": true
PRICES_FORMAT = "fwc-prices/1"
PRICES_GLOBAL = "FWCS_PRICES"     # the houses' lowest prices, for the addon's item tooltips (since 1.8.4)
PRICES_FILE = "prices.json"       # in a house's folder on the site; its entry in houses.json says "prices": true
MAX_PRICE_BYTES = 2 * 1024 * 1024          # of a price list, unpacked: a house's is about 22 kB (15 Nov 2026)
MAX_PRICE_ITEMS = 20000                    # items of a price list: a house lists under 2,000
MAX_COPPER = 99_999_999_999                # a price: the most gold the game holds, 9,999,999g 99s 99c
CHARS = "__chars"                 # in the addon's saved variable: what each character has
UNASKED_HOUSES = 8                # with no character seen yet, every house is fetched when there are at most this many


class PlansError(Exception):
    """The site could not be read, or what it has is not usable. `kind` says which, for the addon's window
    (FWCS_PLANS_PROBLEM): "reach" (not reachable, an HTTP error, too large, not JSON), "update" (the site's routes
    need a newer helper), "unusable" (anything else)."""

    def __init__(self, message: str, kind: str = "unusable"):
        super().__init__(message)
        self.kind = kind


# ---- the document -----------------------------------------------------------------------------
def _digits(key) -> bool:
    """Whether a key is an id: one to ten ASCII digits. "²" passes str.isdigit and int() refuses it, and so does a
    number of thousands of digits."""
    s = str(key)
    return 0 < len(s) <= 10 and s.isascii() and s.isdigit()


def _whole(x) -> int:
    """A time from a document: the number when it is one, else 0 (a string or a list there must not stop the look)."""
    return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else 0


def _pairs(rows, what: str) -> str | None:
    if not isinstance(rows, list) or any(not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], int)
                                              and isinstance(r[1], int) and r[1] > 0) for r in rows):
        return f"{what} is not [[item, units], ...]"
    return None


MAX_CONVERT_ROWS = 64             # a plan's "convert": ten essences make ten rows (15 Nov 2026)
MAX_CONVERT_UNITS = 20            # units used or made by one conversion: a stack of essences is 20; the game's are 1 and 3


def _convert_ok(convert, known) -> bool:
    """Whether a plan's "convert" (since 1.8.4) is {item made: [item used, units used, units made, spell]} with ids the
    document names, whole counts from 1 to MAX_CONVERT_UNITS, a spell id, and at most MAX_CONVERT_ROWS rows."""
    if not isinstance(convert, dict) or len(convert) > MAX_CONVERT_ROWS:
        return False
    for made, row in convert.items():
        if not (_digits(made) and known(int(made)) and isinstance(row, list) and len(row) == 4
                and all(isinstance(x, int) and not isinstance(x, bool) for x in row) and known(row[0]) and row[0] != int(made)
                and 1 <= row[1] <= MAX_CONVERT_UNITS and 1 <= row[2] <= MAX_CONVERT_UNITS and _digits(row[3])):
            return False
    return True


def check_plans(doc) -> str | None:  # noqa: C901, PLR0912 - validator: one guard per field of the site's document, which goes into the game as Lua, read top to bottom
    """Why this is not a fwc-plans/1 document, or None when it is one. A plan's "convert" that is not usable is
    taken out of the document (_convert_ok), the routes kept."""
    if not isinstance(doc, dict) or doc.get("format") != PLANS_FORMAT:
        return f"not a {PLANS_FORMAT} document"
    if not isinstance(doc.get("house"), str) or not doc["house"]:
        return "no house"
    if doc.get("faction", "") not in FACTIONS + ("",):
        return f"faction {doc.get('faction')!r} is not one of {', '.join(FACTIONS)}"
    if not isinstance(doc.get("realms"), list) or any(not isinstance(r, str) for r in doc["realms"]):
        return "no realms"
    items = doc.get("items")
    if not isinstance(items, dict) or any(not _digits(k) or not isinstance(v, str) for k, v in items.items()):
        return "items is not {item id: name}"
    if not isinstance(doc.get("plans"), dict):
        return "no plans"
    if not isinstance(doc.get("also", {}), dict):
        return "also is not {key: plan}"

    def known(item) -> bool:
        return isinstance(item, int) and str(item) in items
    for key, plan in list(doc["plans"].items()) + list(doc.get("also", {}).items()):
        if not isinstance(plan, dict) or not isinstance(plan.get("profession"), str) or not isinstance(plan.get("steps"), list):
            return f"plan {key!r} is not a plan"
        if "companions" in plan and (not isinstance(plan["companions"], list) or any(not isinstance(c, str) for c in plan["companions"])):
            return f"plan {key!r}: companions is not a list of professions"
        for step in plan["steps"]:
            name = f"plan {key!r}, step {step.get('recipe') if isinstance(step, dict) else step!r}"
            if not isinstance(step, dict) or not all(isinstance(step.get(k), int) for k in ("from", "to", "crafts")) \
                    or not isinstance(step.get("recipe"), str) or step["to"] <= step["from"]:
                return f"{name} is not a step"
            problem = _pairs(step.get("uses"), f"{name}: uses")
            if problem:
                return problem
            if "makes" in step and _pairs([step["makes"]], "makes"):
                return f"{name}: makes is not [item, units]"
            per = step.get("per")
            if not isinstance(per, list) or len(per) != step["to"] - step["from"] or any(not isinstance(x, (int, float)) or x < 0 for x in per):
                return f"{name}: per is not a number for each skill point"
            used = [i for i, _ in step["uses"]] + ([step["makes"][0]] if "makes" in step else []) \
                + list(step.get("buy") or []) + list(step.get("craft") or [])
            if not all(known(i) for i in used):
                return f"{name} names an item that items does not"
        for item, how in (plan.get("made") or {}).items():
            if not (_digits(item) and isinstance(how, list) and len(how) in (2, 3) and isinstance(how[0], int) and how[0] > 0
                    and _pairs(how[1], "") is None and (len(how) == 2 or isinstance(how[2], int))):
                return f"plan {key!r}: made[{item}] is not [units, [[item, units], ...], spell]"
        for item, row in (plan.get("buy") or {}).items():
            if not (_digits(item) and isinstance(row, list) and len(row) in (2, 3) and isinstance(row[0], (int, float))
                    and (len(row) == 2 or isinstance(row[2], (int, float)))):
                return f"plan {key!r}: buy[{item}] is not [copper, source]"
        for item, each in (plan.get("sell") or {}).items():
            if not (_digits(item) and isinstance(each, (int, float))):
                return f"plan {key!r}: sell[{item}] is not copper"
        # an enchanter's essence conversions: one that is not usable is left out, and the route with it, which
        # stands without (the addon then counts each essence as it is, as before 1.8.4)
        if "convert" in plan and not _convert_ok(plan["convert"], known):
            del plan["convert"]
    return None


def check_route(plan) -> str | None:
    """Why this is not the fishing route's plan (extra/cooking-fishing.ingame.json), or None when it is: a plan as
    check_plans reads it, kind "fishing", with the names of its items and what the addon reads besides."""
    if not isinstance(plan, dict) or plan.get("kind") != "fishing":
        return "not a fishing route"
    names = plan.get("names")
    if not isinstance(names, dict) or any(not _digits(k) or not isinstance(v, str) for k, v in names.items()):
        return "names is not {item id: name}"
    problem = check_plans({"format": PLANS_FORMAT, "house": "fishing", "realms": [], "items": names, "plans": {"cooking-fishing": plan}})
    if problem:
        return problem
    catch, sold, notes = plan.get("catch"), plan.get("sold_by"), plan.get("notes")
    if not isinstance(catch, dict) or any(not _digits(k) or not isinstance(v, list) or any(
            not (isinstance(z, list) and len(z) == 2 and isinstance(z[0], str) and isinstance(z[1], (int, float))) for z in v)
            for k, v in catch.items()):
        return "catch is not {fish: [[zone, chance], ...]}"
    if not isinstance(sold, dict) or any(not _digits(k) or not isinstance(v, str) for k, v in sold.items()):
        return "sold_by is not {scroll: where}"
    if not isinstance(notes, list) or any(not (isinstance(n, list) and len(n) in (2, 3) and isinstance(n[0], int) and isinstance(n[1], str)
                                                         and (len(n) == 2 or isinstance(n[2], str))) for n in notes):
        return "notes is not [[skill, text, kind], ...]"
    return None


def _int_in(x, low: int, high: int) -> bool:
    """Whether x is a whole number (not a bool, not a float) from low to high."""
    return isinstance(x, int) and not isinstance(x, bool) and low <= x <= high


def check_prices(doc, key: str) -> str | None:
    """Why this is not the fwc-prices/1 document of the house `key`, or None when it is: every id one to ten digits, every price a
    whole number of copper from 1 to MAX_COPPER, at most MAX_PRICE_ITEMS of them, every time whole and not after "at"."""
    if not isinstance(doc, dict) or doc.get("format") != PRICES_FORMAT:
        return f"not a {PRICES_FORMAT} document"
    if doc.get("house") != key:
        return "another house's prices"
    at, prices, seen = doc.get("at"), doc.get("prices"), doc.get("seen", {})
    if not _int_in(at, 0, 2**32):
        return "at is not a time"
    if not isinstance(prices, dict) or len(prices) > MAX_PRICE_ITEMS:
        return f"prices is not {{item id: copper}} of at most {MAX_PRICE_ITEMS} items"
    if any(not _digits(k) or not _int_in(v, 1, MAX_COPPER) for k, v in prices.items()):
        return f"prices is not {{item id: copper from 1 to {MAX_COPPER}}}"
    if not isinstance(seen, dict) or any(k not in prices or not _int_in(v, 0, at) for k, v in seen.items()):
        return "seen is not {item id of prices: a time not after at}"
    return None


# ---- which houses -------------------------------------------------------------------------------
def spelt(realm: str) -> str:
    """A realm's name however it is spelt: 'Classic Beta PvE 2' and 'ClassicBetaPvE2' are 'classicbetapve2'."""
    return re.sub(r"[^a-z0-9]+", "", realm.lower())


def characters(path: Path | None = None) -> list[dict]:
    """The characters the addon has seen, from a saved-variables file (the newest found when
    `path` is None): [{"name", "realm", "house", "faction", "t", "items": {item: [in bags, in the bank]},
    "skills": {skill line: rank}}]. Empty when there is no file, or an addon from before 0.7."""
    if path is None:
        found = scan.find_saved_variables()
        if not found:
            return []
        path = found[0]
    try:
        data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return []
    db = data.get(scan.SAVED) or data.get(scan.OLD_SAVED) or {}
    held = db.get(CHARS) if isinstance(db, dict) else None
    out = []
    for key, c in (held.items() if isinstance(held, dict) else []):
        if not isinstance(c, dict):
            continue
        items = c.get("items") if isinstance(c.get("items"), dict) else {}
        skills = c.get("skills") if isinstance(c.get("skills"), dict) else {}
        out.append({"key": str(key), "name": str(c.get("name") or key), "realm": str(c.get("realm") or ""),
                    "house": str(c.get("house") or ""), "faction": str(c.get("faction") or ""), "t": int(c.get("t") or 0),
                    "items": {int(i): [int((n or [0, 0])[0] or 0), int((n or [0, 0])[1] or 0)] if isinstance(n, list) else [int(n), 0]
                              for i, n in items.items() if isinstance(i, int)},
                    "skills": {int(k): int(v) for k, v in skills.items() if isinstance(k, int) and isinstance(v, (int, float))}})
    return sorted(out, key=lambda c: -c["t"])


def no_realm_wanted(path: Path, chars: list[dict]) -> set[tuple[str, str]]:
    """The realms a character saved with no realm (the game named none, 20 Nov 2026, and an addon
    before 1.8.6 kept it so) may be on, by what the file still knows: its namesakes' (the same name
    and faction, saved under a realm), the one realm the file knows when it knows one, and the
    realms the addon paired with ids. Fetching a house too many costs a fetch; forgetting the
    player's house left /fwc empty. {(realm, faction)}, the realm both spelt and as shown."""
    lost = [c for c in chars if not c["realm"] and c["faction"] in ("Alliance", "Horde")]
    if not lost:
        return set()
    db = scan.saved_db(path)
    real, inferred = scan.realm_ids(db)
    known = scan.known_realms(db)
    out = set()
    for c in lost:
        realms = {o["realm"] for o in chars if o["realm"] and o["name"] == c["name"] and o["faction"] == c["faction"]}
        realms |= set(real.values()) | set(inferred.values()) | (set(known.values()) if len(known) == 1 else set())
        out |= {(r, c["faction"]) for r in realms} | {(spelt(r), c["faction"]) for r in realms}
    return out


_wanted_memo: dict[Path, tuple[tuple, set]] = {}     # path -> ((size, mtime), what it gave): the file is big and read often


def wanted(paths: list[Path] | None = None) -> set[tuple[str, str]]:
    """Whose routes to fetch: {(realm, faction)} of every character the addon has seen and
    every auction house it has scanned, over every saved-variables file found; each realm both
    as spelt (`spelt`, which the houses' lists are matched by) and as the game shows it (which
    the site's name rules are matched by: `by_rule`). A file is read again only once it has
    changed (reading one takes seconds, and `send --watch` asks every minute)."""
    out = set()
    for path in (paths if paths is not None else scan.find_saved_variables()):
        try:
            st = path.stat()
            stamp = (st.st_size, st.st_mtime)
        except OSError:
            stamp = None
        held = _wanted_memo.get(path)
        if held and held[0] == stamp:
            out |= held[1]
            continue
        found = set()
        chars = characters(path)
        for c in chars:
            found |= {(spelt(r), c["faction"]) for r in (c["realm"], c["house"]) if r}
            found |= {(c["realm"], c["faction"])} if c["realm"] else set()
        found |= no_realm_wanted(path, chars)
        try:
            found |= {(s, f) for r, f, _, _ in scan.datasets(path) for s in (spelt(r), r)}
        except (OSError, SyntaxError):
            pass
        if stamp:
            _wanted_memo[path] = (stamp, found)
        out |= found
    return {(r, f) for r, f in out if r and f in ("Alliance", "Horde")}     # a character's own house, never the shared one


def ruled(realm: str, rules: list) -> str | None:
    """The auction house a realm's name is of by the site's rules (`rules` of houses.json:
    [pattern, name] pairs, the core's config.HOUSE_PATTERNS), or None. A rule that is not a
    pattern and a replacement is skipped."""
    for rule in rules or []:
        if not (isinstance(rule, list) and len(rule) == 2 and all(isinstance(x, str) for x in rule)):
            continue
        try:
            if re.fullmatch(rule[0], realm):
                return re.sub(rule[0], rule[1], realm)
        except re.error:
            continue
    return None


def by_rule(house: dict, want: set[tuple[str, str]]) -> list[str]:
    """The wanted realms that are of this house by the site's rules though the house's list
    does not have them: nobody has scanned from them yet. A character there gets the house's
    routes all the same (6 Nov 2026: on Forever every realm of a ruleset in a region is one
    house, and a list of the realms scanned from is not the house)."""
    rules, name, faction = house.get("rules"), house.get("realm"), house.get("faction", "")
    if not rules or not name:
        return []
    return sorted(r for r, f in want if f == faction and ruled(r, rules) == name)


def is_of(house: dict, want: set[tuple[str, str]]) -> bool:
    """Whether a house of houses.json is one of the wanted: a wanted realm is in its list, or
    is of it by the site's name rules."""
    names = {spelt(str(r)) for r in [house.get("realm") or "", str(house.get("key") or "").split("--")[0]] + list(house.get("realms") or [])}
    return any((n, house.get("faction", "")) in want for n in names if n) or bool(by_rule(house, want))


def choose(houses: list[dict], want: set[tuple[str, str]], region: str | None = None) -> list[dict]:
    """The houses to fetch: those of the characters seen. With none seen yet (a first install:
    the addon saves a character at its first /reload or logout), the houses of the client's
    `region` (scan.portal: "US" has US PvE, US PvP, ...), so that /fwc has routes at the very
    first login instead of an empty window and two reloads (players kept reporting the blank
    window, 9 Nov 2026); or all of them when there are few. More than UNASKED_HOUSES, none."""
    listed = [h for h in houses if h.get("ingame")]          # the houses with routes for the addon (`ingame` is absent on a site from before them)
    if want:
        return [h for h in listed if is_of(h, want)]
    if region:
        mine = [h for h in listed if str(h.get("realm") or "").upper().startswith(region.upper() + " ")]
        if 0 < len(mine) <= UNASKED_HOUSES:
            return mine
    return listed if len(listed) <= UNASKED_HOUSES else []


# ---- the site -----------------------------------------------------------------------------------
def site_url() -> str:
    """The site the routes come from: the saved FWC_SITE_URL, else settings.SITE_URL, without a trailing slash."""
    return (settings.saved("SITE_URL") or settings.SITE_URL).rstrip("/")


MAX_BYTES = 32 * 1024 * 1024          # of a document, unpacked: a house's routes are about 100 kB


def _no_constant(name: str):
    """JSON's NaN and Infinity, which Python accepts and Lua has no literal for: refused."""
    raise ValueError(f"{name} in the document")


def get(url: str, limit: int = MAX_BYTES) -> dict:
    """A JSON document from the site, of at most `limit` bytes unpacked; what is read goes into the
    addon as Lua, so only https is followed and nothing the game would take for code is let through
    (see `lua`)."""
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        raise PlansError(f"{url}: only https is read")
    # Cloudflare answers Python's default User-Agent with 403, so name ourselves
    req = urllib.request.Request(url, headers={"User-Agent": f"{settings.NAME}-helper/{__version__}", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=settings.PIPE_TIMEOUT) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise PlansError(f"{url}: {e.code}", "reach") from e
    except OSError as e:
        raise PlansError(f"{url} could not be reached ({e})", "reach") from e
    try:
        if data[:2] == b"\x1f\x8b":
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read(limit + 1)      # unpacked only this far
        if len(data) > limit:
            raise PlansError(f"{url} is too large ({len(data) // 1024} kB)", "reach")
        return json.loads(data.decode("utf-8"), parse_constant=_no_constant)
    except (OSError, ValueError, RecursionError) as e:          # RecursionError: JSON nested deeper than Python follows
        raise PlansError(f"{url} is not JSON", "reach") from e


# How often the watch looks, as the site last said (houses.json "helper", since 1.7.2), so that
# it can be changed for every helper at once without a release. Empty until houses.json has been
# fetched; settings.PLANS_EVERY and FRESH_EVERY stand in for whatever the site does not say.
INTERVALS: dict = {}
INTERVAL_RANGE = (60, 86400)       # seconds: a site value outside is held to the nearer end


def hints(doc) -> dict:
    """The site's intervals from a houses.json document: whole seconds only, held to INTERVAL_RANGE."""
    given = doc.get("helper") if isinstance(doc, dict) else None
    out = {}
    for name in ("plans_every", "fresh_every"):
        value = given.get(name) if isinstance(given, dict) else None
        if isinstance(value, int) and not isinstance(value, bool):
            out[name] = min(max(value, INTERVAL_RANGE[0]), INTERVAL_RANGE[1])
    return out


def plans_every() -> int:
    """Seconds between the watch's looks at the site for newer routes."""
    return INTERVALS.get("plans_every", settings.PLANS_EVERY)


def fresh_every() -> int:
    """Seconds between the watch's looks at the pipe for when each house was last scanned, as
    helpers 1.7.2 to 1.8.3 use it. Still read (the site keeps saying it for them), but from
    1.8.4 the watch makes no such look: it learns the same from the answer to each scan it
    sends (fresh.learn)."""
    return INTERVALS.get("fresh_every", settings.FRESH_EVERY)


def houses(site: str | None = None) -> list[dict]:
    """What the site has: its auction houses. What it says of how often to look is kept (INTERVALS)."""
    doc = get((site or site_url()) + "/data/houses.json")
    listed = doc.get("houses") if isinstance(doc, dict) else None
    if not isinstance(listed, list):
        raise PlansError("the site lists no auction houses")
    INTERVALS.clear()
    INTERVALS.update(hints(doc))
    rules = doc.get("rules") if isinstance(doc.get("rules"), list) else []      # the name rules, on every house for by_rule
    return [dict(h, rules=rules) for h in listed if isinstance(h, dict) and isinstance(h.get("key"), str) and re.fullmatch(r"[a-z0-9\-]+", h["key"])
            and isinstance(h.get("faction", ""), str)]


def version_tuple(s) -> tuple[int, ...]:
    """A version as numbers to compare, at most three: "1.7.6" -> (1, 7, 6)."""
    return tuple(int(x) for x in re.findall(r"\d+", str(s))[:3])


def fetch(house: dict, site: str | None = None) -> dict:
    """A house's fwc-plans/1 document. The site says which helper its document takes
    (`needs_helper`, since 1.1.0); one too old is told to update rather than that the
    document is wrong."""
    doc = get(f"{site or site_url()}/data/{house['key']}/ingame.json")
    needs = doc.get("needs_helper") if isinstance(doc, dict) else None
    if isinstance(needs, str) and version_tuple(needs) > version_tuple(__version__):
        raise PlansError(f"{house['key']}: the site's routes need helper {needs} or newer, and this is {__version__}: "
                         "update the helper (the new zip, or git pull), then run this again", "update")
    problem = check_plans(doc)
    if problem:
        raise PlansError(f"{house['key']}: what the site has is not usable: {problem}")
    return doc


def fetch_route(house: dict, site: str | None = None) -> dict:
    """The fishing route a house's folder holds (its houses.json entry says "fishing": true), as the addon takes it."""
    plan = get(f"{site or site_url()}/data/{house['key']}/{FISHING_FILE}")
    problem = check_route(plan)
    if problem:
        raise PlansError(f"{house['key']}: the fishing route is not usable: {problem}")
    return plan


def routes_for(chosen: list[dict], site: str | None = None, have: dict | None = None) -> dict:
    """{faction: the fishing route} for the chosen houses that have one: fetched once a faction, from the first house of it
    that lists one. A route that cannot be read is left out (the houses' routes are still written): `have`, the routes
    the kept file holds, stands in for it."""
    out = {}
    for h in chosen:
        faction = h.get("faction", "")
        if h.get("fishing") is True and faction in FACTIONS and faction not in out:
            try:
                out[faction] = fetch_route(h, site)
            except PlansError:
                if faction in (have or {}):
                    out[faction] = have[faction]
    return out


DROPPED: list[str] = []            # the price lists the last look left out, and why: said once in the log (cli.plans)
_refused: set[tuple[str, int]] = set()      # (house, when its data was made) of a price list left out: not asked for again until it changes


def fetch_prices(house: dict, site: str | None = None) -> dict:
    """A house's price list as the addon takes it: {"at", "prices", "seen"}, ids as numbers."""
    doc = get(f"{site or site_url()}/data/{house['key']}/{PRICES_FILE}", MAX_PRICE_BYTES)
    problem = check_prices(doc, house["key"])
    if problem:
        raise PlansError(f"{house['key']}: the prices are not usable: {problem}")
    return {"at": doc["at"], "prices": {int(k): v for k, v in doc["prices"].items()},
            "seen": {int(k): v for k, v in (doc.get("seen") or {}).items()}}


def prices_for(chosen: list[dict], site: str | None = None) -> dict:
    """{house: its price list} for the chosen houses whose entry in houses.json says "prices": true. One that cannot be read or
    is not usable is left out, and said in DROPPED; the rest, and the routes, are written all the same."""
    out = {}
    for h in chosen:
        if h.get("prices") is True:
            try:
                out[h["key"]] = fetch_prices(h, site)
            except PlansError as e:
                DROPPED.append(str(e))
                _refused.add((h["key"], _whole(h.get("generated"))))
    return out


# ---- Plans.lua ------------------------------------------------------------------------------------
def lua(value, indent: int = 0) -> str:
    """A JSON-like value as a Lua literal, for the game to load: every string is a quoted
    literal whatever is in it (so nothing in a document can become code), a number is finite,
    and "|", which the game's UI reads as the start of a colour or link, is written as "||",
    which it shows as "|". A dict whose keys are all digits gets number keys."""
    if value is None:
        return "nil"
    if value is True or value is False:
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a number that is not finite")
        return repr(round(value, 4)) if value != int(value) else str(int(value))
    if isinstance(value, str):
        clean = "".join(ch for ch in value if (ch >= " " or ch == "\n") and not "\ud800" <= ch <= "\udfff")     # no control characters, no lone surrogates
        return '"' + clean.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("|", "||") + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua(v, indent) for v in value) + "}"
    if isinstance(value, dict):
        pad = " " * (indent + 1)
        rows = []
        for k, v in value.items():
            key = f"[{int(k)}]" if isinstance(k, int) or _digits(k) else f"[{lua(str(k))}]"
            rows.append(f"{pad}{key}={lua(v, indent + 1)},")
        return "{\n" + "\n".join(rows) + "\n" + " " * indent + "}" if rows else "{}"
    raise TypeError(f"no Lua for {type(value).__name__}")


def for_addon(doc: dict) -> dict:
    """A document as the addon holds it: the same, with realms as the addon compares them."""
    out = {k: v for k, v in doc.items() if k != "format"}
    out["realms"] = sorted({spelt(r) for r in doc["realms"] + [doc.get("realm") or ""]} - {""})
    return out


def site_list(listed: list[dict]) -> list[list[str]]:
    """The auction houses the site lists with routes for the addon, as the addon compares them: [[spelt realm, faction], ...],
    from houses.json (`ingame` true). A house of no faction is left out: no character is of it."""
    found = {(spelt(str(h.get("realm") or "")), h["faction"]) for h in listed if h.get("ingame") and h.get("faction") in FACTIONS}
    return [list(x) for x in sorted(found) if x[0]]


def site_line(houses: list[list[str]], at: int | None = None) -> str:
    """The FWCS_SITE line (one line: `touch` replaces it as a line)."""
    return f"{SITE_GLOBAL} = {{ at = {int(at if at is not None else time.time())}, houses = {lua(houses)} }}"


def problem_line(kind: str, at: int | None = None) -> str:
    """The FWCS_PLANS_PROBLEM line: when, and which of "reach", "update", "unusable"; nothing else of the error."""
    return f"{PROBLEM_GLOBAL} = {{ at = {int(at if at is not None else time.time())}, kind = {lua(kind)} }}"


def plans_text(docs: list[dict], site: str, written: int | None = None, routes: dict | None = None,  # noqa: PLR0913 - one argument a global of the file
               site_houses: list[list[str]] | None = None, prices: dict | None = None) -> str:
    """Plans.lua for these documents: the routes, and when they were written (the addon tells
    from it whether the helper runs). Nothing else: until 1.5.6 a helper run from a checkout
    of the repository added FWCS_DEV = true, which showed the addon's scanner bar, and a copy
    of that file in front of a player showed it to them (6 Nov 2026). The bar is a switch in
    the game now, nothing a file says. `routes` ({faction: the fishing route}) is written as a second global
    after the first, and `site_houses` (`site_list`) as FWCS_SITE after that; with neither the text is what it
    was before 1.8.0, byte for byte, and with either everything up to the new global is that text. `prices`
    ({house: its price list}, `prices_for`) is FWCS_PRICES, after FWCS_ROUTES and before FWCS_SITE, and only
    when there is one: the text before it is unchanged."""
    now = int(written if written is not None else time.time())
    return "\n".join([
        f"-- Written by `python fwch.py plans` from {site}; do not edit by hand.",
        "-- The routes of your characters' auction houses, for the /fwc window. See fwchelper/plans.py.",
        f"{PLANS_GLOBAL}_WRITTEN = {now}",
        f"{PLANS_GLOBAL} = " + lua({d["house"]: for_addon(d) for d in docs}),
        *([f"{ROUTES_GLOBAL} = " + lua(routes)] if routes else []),
        *([f"{PRICES_GLOBAL} = " + lua(prices)] if prices else []),
        *([site_line(site_houses, now)] if site_houses is not None else []), ""])


def kept_file() -> Path:
    """The Plans.lua the helper keeps, so that installing the addon again does not lose it."""
    return settings.STATE / "Plans.lua"


def installed_file() -> Path:
    """The second addon's copy (ForeverWowCraftPlans), which the game reads."""
    return scan.plans_addon_dir() / "Plans.lua"


_held_memo: dict[str, tuple] = {}     # path -> (scan.file_version, what held gave): one entry a file


def held(path: Path | None = None) -> tuple[dict[str, int], dict]:
    """({house: when its routes were made}, {faction: the fishing route}) of a Plans.lua (the kept one by default).
    A file is read again only once it has changed: every line of the app's log asks (the tooltip), and a read
    of a large Plans.lua took half a second."""
    found = _read_held(path or kept_file())
    return dict(found[0]), dict(found[1])


def priced(path: Path | None = None) -> set[str]:
    """The houses a Plans.lua (the kept one by default) holds a price list of (FWCS_PRICES, since 1.8.4)."""
    return set(_read_held(path or kept_file())[2])


def _read_held(path: Path) -> tuple[dict, dict, set]:
    """(stamps, fishing routes, houses with a price list) of a Plans.lua, read again only once it has changed."""
    version = scan.file_version(path)
    memo = _held_memo.get(str(path))
    if version is not None and memo and memo[0] == version:
        return memo[1]
    try:
        data = luatable.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}, {}, set()
    plans, routes, prices = data.get(PLANS_GLOBAL) or {}, data.get(ROUTES_GLOBAL) or {}, data.get(PRICES_GLOBAL) or {}
    found = ({str(k): int(v.get("generated") or 0) for k, v in plans.items() if isinstance(v, dict)} if isinstance(plans, dict) else {},
             {str(k): v for k, v in routes.items() if isinstance(v, dict)} if isinstance(routes, dict) else {},
             {str(k) for k, v in prices.items() if isinstance(v, dict)} if isinstance(prices, dict) else set())
    if version is not None:
        _held_memo[str(path)] = (version, found)
    return found


def stamps(path: Path | None = None) -> dict[str, int]:
    """{house: when its routes were made} of a Plans.lua (the kept one by default)."""
    return held(path)[0]


def write(docs: list[dict], site: str, routes: dict | None = None, site_houses: list[list[str]] | None = None,
          prices: dict | None = None) -> list[Path]:
    """Write Plans.lua: the helper's own copy, and the installed addon's when it is installed."""
    text = plans_text(docs, site, routes=routes, site_houses=site_houses, prices=prices)
    targets = [kept_file()] + ([installed_file()] if installed_file().parent.is_dir() else [])
    for t in targets:
        scan.write_whole(t, text)
    return targets


_STAMP = re.compile(rf"^{PLANS_GLOBAL}_WRITTEN = \d+$", re.M)
_SITE_LINE = re.compile(rf"^{SITE_GLOBAL} = .*\n?", re.M)
_PROBLEM_LINE = re.compile(rf"^{PROBLEM_GLOBAL} = .*\n?", re.M)


def _retouch(text: str, site_houses: list[list[str]] | None, kind: str | None) -> str:
    """The text with the stamp at now, the problem line as `kind` says (None: none) and FWCS_SITE as `site_houses` says (None:
    as it is, or none). Both one-line globals come last, the site's first; the routes are left as they are."""
    now = int(time.time())
    kept = _SITE_LINE.search(text)
    body = _PROBLEM_LINE.sub("", _SITE_LINE.sub("", _STAMP.sub(f"{PLANS_GLOBAL}_WRITTEN = {now}", text, count=1)))
    body = body if body.endswith("\n") else body + "\n"
    tail = [site_line(site_houses, now)] if site_houses is not None else [kept.group(0).rstrip("\n")] if kept else []
    return body + "".join(line + "\n" for line in tail + ([problem_line(kind, now)] if kind else []))


def touch(site_houses: list[list[str]] | None = None) -> None:
    """Move the written-at stamp of the Plans.lua files to now, leaving the routes as they are:
    the addon tells from it that the helper is running. A look that worked also clears the problem line, and
    `site_houses` (`site_list`) sets FWCS_SITE, added when the file (an earlier helper's) has none. A file without
    the stamp (from an older helper) is left alone."""
    for t in [kept_file()] + ([installed_file()] if installed_file().is_file() else []):
        try:
            text = t.read_text(encoding="utf-8")
            if _STAMP.search(text):
                scan.write_whole(t, _retouch(text, site_houses, None))
        except OSError:
            pass


def note_problem(kind: str) -> None:
    """Record that the last look for routes failed (`kind`, as PlansError has it): one line in the kept Plans.lua and the
    installed one, the stamp moved (the helper ran), the routes as they are. With no Plans.lua yet, a minimal one."""
    for t in [kept_file()] + ([installed_file()] if installed_file().parent.is_dir() else []):
        try:
            try:
                text = t.read_text(encoding="utf-8")
            except FileNotFoundError:
                text = plans_text([], site_url())
            if _STAMP.search(text):                          # a file with no stamp is not one of ours to edit
                scan.write_whole(t, _retouch(text, None, kind))
        except OSError:
            pass


def refresh(site: str | None = None, force: bool = False) -> tuple[list[dict], list[Path]]:
    """Fetch the routes of the characters' auction houses and write them into the addon, when
    the site has something newer than what was written (or `force`). Returns (the documents
    now written, the files written): no files when nothing was new. A look that fails with a
    PlansError is recorded in the addon's files (`note_problem`) and raised."""
    try:
        return _refresh(site or site_url(), force)
    except PlansError as e:
        note_problem(e.kind)
        raise


def _refresh(site: str, force: bool) -> tuple[list[dict], list[Path]]:
    want = wanted()
    listed = houses(site)
    chosen = choose(listed, want, None if want else scan.portal())
    have, kept_routes = held()
    current = {h["key"]: _whole(h.get("generated")) for h in chosen}
    missing = installed_file().parent.is_dir() and not installed_file().exists()
    wants = {h.get("faction") for h in chosen if h.get("fishing") is True} & set(FACTIONS)      # a faction's fishing route the kept file lacks (written by an older helper)
    # a house's price list the kept file lacks (written by an older helper), unless this one left it out of the same data
    lacks = {h["key"] for h in chosen if h.get("prices") is True and (h["key"], current[h["key"]]) not in _refused} - priced()
    seen = site_list(listed)
    DROPPED.clear()
    if not force and not missing and current == have and wants <= set(kept_routes) and not lacks:
        touch(seen)                                     # the addon still sees that the helper runs, and which houses the site lists
        return [], []
    docs = [fetch(h, site) for h in chosen]
    for d, h in zip(docs, chosen):                      # as houses.json has it, so that "nothing new" is told from it alone
        d["generated"] = _whole(h.get("generated")) or _whole(d.get("generated"))
        mine = by_rule(h, want)                         # a realm of the house by its name: into the list the addon finds its house by
        if mine:
            d["realms"] = sorted({*(d.get("realms") or []), *mine})
    return docs, write(docs, site, routes_for(chosen, site, kept_routes), seen, prices_for(chosen, site))


def age(doc: dict) -> str:
    """How old the scan a house's routes were planned from is, as text ("3 h ago")."""
    return scan.age_text(int(doc.get("scanned_at") or 0))
