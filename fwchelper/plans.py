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
             "buy": {"<item>": [copper a unit, "ah" | "vendor"], ...},
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
      ("focus": "profit", where what is made is sold, or "skill", where nothing is); its label
      is the recipes', and "focus" lists the labels of the other. A document without "focus"
      has the profit routes alone. A step is a run of skill points gained with one recipe: "from" is the skill it starts at,
      "to" the skill it ends at. "makes" is absent when the recipe makes no item (an enchant).
      Of what a step uses, "buy" names what the route buys for it and "craft" what it makes on
      the spot ("made" says how: units a craft, what a craft uses, and since 11 Oct 2026 the
      recipe's spell, which the addon's Make button crafts by); the rest comes from what earlier steps made. "learn" is a
      recipe the route buys before this step. "buy" and "sell" of the plan are what the route
      pays and gets for one, on average: an estimate once fewer are bought or sold.

The addon reads Plans.lua, the same data as a Lua table (FWCS_PLANS[<key>]), at the next /reload
or login, with FWCS_PLANS_WRITTEN = when the helper last wrote or touched it (the addon says,
quietly, when the helper is not installed or has not run for days) and FWCS_DEV = true when the
helper runs from a checkout (the addon then shows its scanner's bar by default). It takes from a
route what the character has, in the game: nothing of what a character has is sent anywhere. Which houses are fetched is told from the characters the
addon has seen (FWCS_DB.__chars) and the auction houses it has scanned.

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
CHARS = "__chars"                 # in the addon's saved variable: what each character has
UNASKED_HOUSES = 8                # with no character seen yet, every house is fetched when there are at most this many


class PlansError(Exception):
    """The site could not be read, or what it has is not usable."""


# ---- the document -----------------------------------------------------------------------------
def _pairs(rows, what: str) -> str | None:
    if not isinstance(rows, list) or any(not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], int)
                                              and isinstance(r[1], int) and r[1] > 0) for r in rows):
        return f"{what} is not [[item, units], ...]"
    return None


def check_plans(doc) -> str | None:
    """Why this is not a fwc-plans/1 document, or None when it is one."""
    if not isinstance(doc, dict) or doc.get("format") != PLANS_FORMAT:
        return f"not a {PLANS_FORMAT} document"
    if not isinstance(doc.get("house"), str) or not doc["house"]:
        return "no house"
    if doc.get("faction", "") not in FACTIONS + ("",):
        return f"faction {doc.get('faction')!r} is not one of {', '.join(FACTIONS)}"
    if not isinstance(doc.get("realms"), list) or any(not isinstance(r, str) for r in doc["realms"]):
        return "no realms"
    items = doc.get("items")
    if not isinstance(items, dict) or any(not str(k).isdigit() or not isinstance(v, str) for k, v in items.items()):
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
            if not (str(item).isdigit() and isinstance(how, list) and len(how) in (2, 3) and isinstance(how[0], int) and how[0] > 0
                    and _pairs(how[1], "") is None and (len(how) == 2 or isinstance(how[2], int))):
                return f"plan {key!r}: made[{item}] is not [units, [[item, units], ...], spell]"
        for item, row in (plan.get("buy") or {}).items():
            if not (str(item).isdigit() and isinstance(row, list) and len(row) == 2 and isinstance(row[0], (int, float))):
                return f"plan {key!r}: buy[{item}] is not [copper, source]"
        for item, each in (plan.get("sell") or {}).items():
            if not (str(item).isdigit() and isinstance(each, (int, float))):
                return f"plan {key!r}: sell[{item}] is not copper"
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


_wanted_memo: dict[Path, tuple[tuple, set]] = {}     # path -> ((size, mtime), what it gave): the file is big and read often


def wanted(paths: list[Path] | None = None) -> set[tuple[str, str]]:
    """Whose routes to fetch: {(realm however spelt, faction)} of every character the addon has
    seen and every auction house it has scanned, over every saved-variables file found. A file
    is read again only once it has changed (reading one takes seconds, and `send --watch` asks
    every minute)."""
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
        for c in characters(path):
            found |= {(spelt(r), c["faction"]) for r in (c["realm"], c["house"]) if r}
        try:
            found |= {(spelt(r), f) for r, f, _, _ in scan.datasets(path)}
        except (OSError, SyntaxError):
            pass
        if stamp:
            _wanted_memo[path] = (stamp, found)
        out |= found
    return {(r, f) for r, f in out if r and f in ("Alliance", "Horde")}     # a character's own house, never the shared one


def is_of(house: dict, want: set[tuple[str, str]]) -> bool:
    """Whether a house of houses.json is one of the wanted."""
    names = {spelt(str(r)) for r in [house.get("realm") or "", str(house.get("key") or "").split("--")[0]] + list(house.get("realms") or [])}
    return any((n, house.get("faction", "")) in want for n in names if n)


def choose(houses: list[dict], want: set[tuple[str, str]]) -> list[dict]:
    """The houses to fetch: those of the characters seen; with none seen yet, all of them when
    there are few."""
    listed = [h for h in houses if h.get("ingame")]          # a site from before it had routes for the addon says nothing
    if want:
        return [h for h in listed if is_of(h, want)]
    return listed if len(listed) <= UNASKED_HOUSES else []


# ---- the site -----------------------------------------------------------------------------------
def site_url() -> str:
    return (settings.saved("SITE_URL") or settings.SITE_URL).rstrip("/")


MAX_BYTES = 32 * 1024 * 1024          # of a document, unpacked: a house's routes are about 100 kB


def _no_constant(name: str):
    """JSON's NaN and Infinity, which Python accepts and Lua has no literal for: refused."""
    raise ValueError(f"{name} in the document")


def get(url: str) -> dict:
    """A JSON document from the site, of at most MAX_BYTES; what is read goes into the addon as
    Lua, so only https is followed and nothing the game would take for code is let through
    (see `lua`)."""
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1") and not url.startswith("http://localhost"):
        raise PlansError(f"{url}: only https is read")
    # Cloudflare answers Python's default User-Agent with 403, so name ourselves
    req = urllib.request.Request(url, headers={"User-Agent": f"{settings.NAME}-helper/{__version__}", "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=settings.PIPE_TIMEOUT) as r:
            data = r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise PlansError(f"{url}: {e.code}") from e
    except OSError as e:
        raise PlansError(f"{url} could not be reached ({e})") from e
    try:
        if data[:2] == b"\x1f\x8b":
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_BYTES + 1)      # unpacked only this far
        if len(data) > MAX_BYTES:
            raise PlansError(f"{url} is too large ({len(data) // 1024} kB)")
        return json.loads(data.decode("utf-8"), parse_constant=_no_constant)
    except (OSError, ValueError) as e:
        raise PlansError(f"{url} is not JSON") from e


def houses(site: str | None = None) -> list[dict]:
    """What the site has: its auction houses."""
    doc = get((site or site_url()) + "/data/houses.json")
    listed = doc.get("houses") if isinstance(doc, dict) else None
    if not isinstance(listed, list):
        raise PlansError("the site lists no auction houses")
    return [h for h in listed if isinstance(h, dict) and isinstance(h.get("key"), str) and re.fullmatch(r"[a-z0-9\-]+", h["key"])]


def version_tuple(s) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", str(s))[:3])


def fetch(house: dict, site: str | None = None) -> dict:
    """A house's fwc-plans/1 document. The site says which helper its document takes
    (`needs_helper`, since 1.1.0); one too old is told to update rather than that the
    document is wrong."""
    doc = get(f"{site or site_url()}/data/{house['key']}/ingame.json")
    needs = doc.get("needs_helper") if isinstance(doc, dict) else None
    if isinstance(needs, str) and version_tuple(needs) > version_tuple(__version__):
        raise PlansError(f"{house['key']}: the site's routes need helper {needs} or newer, and this is {__version__}: "
                         "update the helper (the new zip, or git pull), then run this again")
    problem = check_plans(doc)
    if problem:
        raise PlansError(f"{house['key']}: what the site has is not usable: {problem}")
    return doc


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
        clean = "".join(ch for ch in value if ch >= " " or ch == "\n")                    # no control characters
        return '"' + clean.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("|", "||") + '"'
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua(v, indent) for v in value) + "}"
    if isinstance(value, dict):
        pad = " " * (indent + 1)
        rows = []
        for k, v in value.items():
            key = f"[{int(k)}]" if isinstance(k, int) or str(k).isdigit() else f"[{lua(str(k))}]"
            rows.append(f"{pad}{key}={lua(v, indent + 1)},")
        return "{\n" + "\n".join(rows) + "\n" + " " * indent + "}" if rows else "{}"
    raise TypeError(f"no Lua for {type(value).__name__}")


def for_addon(doc: dict) -> dict:
    """A document as the addon holds it: the same, with realms as the addon compares them."""
    out = {k: v for k, v in doc.items() if k != "format"}
    out["realms"] = sorted({spelt(r) for r in doc["realms"] + [doc.get("realm") or ""]} - {""})
    return out


def developing() -> bool:
    """Whether this helper runs from a checkout of the repository (its own, or the core's that
    holds it), rather than from a zip or a store: the addon then shows its scanner's bar by
    default, where an installed one scans in the background."""
    return (settings.ROOT / ".git").exists() or (settings.ROOT.parent / ".git").exists()


def plans_text(docs: list[dict], site: str, written: int | None = None, dev: bool = False) -> str:
    """Plans.lua for these documents: the routes, when they were written (the addon tells from
    it whether the helper runs), and whether this is a developer's install."""
    return "\n".join([
        f"-- Written by `python fwch.py plans` from {site}; do not edit by hand.",
        "-- The routes of your characters' auction houses, for the /fwc window. See fwchelper/plans.py.",
        f"{PLANS_GLOBAL}_WRITTEN = {int(written if written is not None else time.time())}",
        f"{PLANS_GLOBAL} = " + lua({d["house"]: for_addon(d) for d in docs})]
        + (["FWCS_DEV = true"] if dev else []) + [""])


def kept_file() -> Path:
    """The Plans.lua the helper keeps, so that installing the addon again does not lose it."""
    return settings.STATE / "Plans.lua"


def installed_file() -> Path:
    """The second addon's copy (ForeverWowCraftPlans), which the game reads."""
    return scan.plans_addon_dir() / "Plans.lua"


def stamps(path: Path | None = None) -> dict[str, int]:
    """{house: when its routes were made} of a Plans.lua (the kept one by default)."""
    path = path or kept_file()
    try:
        held = luatable.parse(path.read_text(encoding="utf-8")).get(PLANS_GLOBAL) or {}
    except (OSError, SyntaxError):
        return {}
    return {str(k): int(v.get("generated") or 0) for k, v in held.items() if isinstance(v, dict)} if isinstance(held, dict) else {}


def write(docs: list[dict], site: str) -> list[Path]:
    """Write Plans.lua: the helper's own copy, and the installed addon's when it is installed."""
    text = plans_text(docs, site, dev=developing())
    targets = [kept_file()] + ([installed_file()] if installed_file().parent.is_dir() else [])
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(text, encoding="utf-8")
    return targets


_STAMP = re.compile(rf"^{PLANS_GLOBAL}_WRITTEN = \d+$", re.M)


def touch() -> None:
    """Move the written-at stamp of the Plans.lua files to now, leaving the routes as they are:
    the addon tells from it that the helper is running. A file without the stamp (from an
    older helper) is left alone."""
    for t in [kept_file()] + ([installed_file()] if installed_file().is_file() else []):
        try:
            text = t.read_text(encoding="utf-8")
            if _STAMP.search(text):
                t.write_text(_STAMP.sub(f"{PLANS_GLOBAL}_WRITTEN = {int(time.time())}", text, count=1), encoding="utf-8")
        except OSError:
            pass


def refresh(site: str | None = None, force: bool = False) -> tuple[list[dict], list[Path]]:
    """Fetch the routes of the characters' auction houses and write them into the addon, when
    the site has something newer than what was written (or `force`). Returns (the documents
    now written, the files written): no files when nothing was new."""
    site = site or site_url()
    chosen = choose(houses(site), wanted())
    have = stamps()
    current = {h["key"]: int(h.get("generated") or 0) for h in chosen}
    missing = installed_file().parent.is_dir() and not installed_file().exists()
    if not force and not missing and current == have:
        touch()                                         # the addon still sees that the helper runs
        return [], []
    docs = [fetch(h, site) for h in chosen]
    for d, h in zip(docs, chosen):                      # as houses.json has it, so that "nothing new" is told from it alone
        d["generated"] = int(h.get("generated") or d.get("generated") or 0)
    return docs, write(docs, site)


def age(doc: dict) -> str:
    return scan.age_text(int(doc.get("scanned_at") or 0))
