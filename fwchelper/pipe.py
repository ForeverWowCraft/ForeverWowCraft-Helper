"""The pipe: scans go to a service, lists come back from it.

WHAT IS SENT, AND WHY (everything the addon gathers: docs/scanner-addon.md, "What the addon
gathers"). Two documents leave this computer, both built here from the addon's saved file:
  a scan (fwc-scan/1): the auction house's realm and faction, each listed item's id, name and
    auctions (unit price, stack, how many, time left), when; the names of the realms the
    account's characters logged in on with the addon, and the house's connected realms, so that
    the site names the house. Sent after the player saved a scan in game. For the routes' prices.
  the sightings (fwc-vendors/1): the merchants, trainers and recipe scrolls the player met
    (fields in vendors_document below), sent when they changed. For who sells what on Forever,
    the skill a trainer teaches a recipe at, and the level a recipe is gated at.
Both go to the project's pipe under this helper's own token (a random name the pipe gave it),
pooled with other players' to price the routes and to know Forever's vendors, trainers and recipes.
NEVER sent: no character name, gold, bags, bank or mail, chat, guild, account name or password,
and no position but the spot of a merchant's or trainer's window the player opened. What each
character has (FWCS_DB.__chars) stays on this computer.

Two documents, both JSON, sent gzipped:

    fwc-scan/1   what one scanner saw: for each item, when, and its ladder
        {"format": "fwc-scan/1", "realm": "...", "faction": "Alliance" | "Horde" | "",
         "scanned_at": <newest item's time>, "helper": "<version>", "items": {"<item id>": {"t": <time>, "name": "...", "full": 1,
         "l": [[unit price, stack size, auctions of that price and size, time left], ...]}, ...}}
      Only items the addon finished are in it. An item nobody lists has "l": []. A realm and a
      faction are one auction house; "" is a scan that does not say which faction's. The time
      left is the auction house's band, 1 short (under 30 min), 2 medium (under 2 h), 3 long
      (under 12 h), 4 very long; a rung without it (helpers before 1.0.3) is of three parts.

    fwc-lists/1  what the scanners should do: the lists the addon scans
        {"format": "fwc-lists/1", "generated": <time>, "queue": {"<list name>": [[item id, "name"], ...]}}

and a service that speaks HTTP. Anyone may send: a helper asks for a token once and is given one
of its own. After that every request carries "Authorization: Bearer <token>".

    POST /v1/register       {"helper": "<version>"}      -> {"name", "token", "trust": "public"}   (no token)
    POST /v1/scans          a fwc-scan/1 document        -> {"id", "new": true|false, "trust"}
                            429 with Retry-After when the sender sends faster than it may;
                            409 {"fresh": true, "newest", "wanted_from"} when the auction house
                            has a scan fresh enough already: not needed, and nothing is kept;
                            403 when the pipe takes scans from the core alone (ACCEPT_SCANS).
                            The core's token may add ?sender=NAME: the scan is kept as that
                            trusted sender's, at no pace and past the gate (what it read from
                            Blizzard's API)
    GET  /v1/fresh          -> {"fresh": seconds, "houses": {"<realm>|<faction>": {"newest"}}}
                            (no token; a minute old at most)
    GET  /v1/lists          -> the fwc-lists/1 document, 404 when none was set
    GET  /v1/me             -> {"name", "trust"}
    GET  /v1/scans?after=N  -> {"scans": [{"id", "realm", "faction", "scanned_at", "received_at", "sender", "items", ...}]}
    GET  /v1/scans/<id>     -> the document
    PUT  /v1/lists          a fwc-lists/1 document
    GET  /v1/senders        -> {"senders": [{"name", "trust", "scans", "houses", "last_seen", ...}]}
    PUT  /v1/senders/<name> {"trust": "trusted" | "public" | "blocked", "note"}
    GET  /v1/health         -> {"ok": true}   (no token)

A scanner's token may send scans and read lists. Reading scans, setting lists and saying who is
trusted takes the token of whoever runs the service. A sender is `public` until made `trusted`;
what is done with a public sender's scans is for whoever reads them to decide. Times are unix
seconds, money is copper.

The freshness gate: the value of a scan is the auction house's, not the sender's, so the pipe
takes one scan of a house in `fresh` seconds and says "not needed" to the rest (NotNeeded here),
however many play; the addon hides its scan box while the house's newest scan is fresh.
"""
from __future__ import annotations
import gzip
import hashlib
import json
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from . import __version__, settings
from .scan import FACTIONS, ScanData, ScanItem

SCAN_FORMAT, LISTS_FORMAT, VENDORS_FORMAT = "fwc-scan/1", "fwc-lists/1", "fwc-vendors/1"


class PipeError(Exception):
    """The service refused a request, or could not be reached."""


class TooSoon(PipeError):
    """The service holds senders to a pace, and this came too soon. `wait` is in seconds."""

    def __init__(self, message: str, wait: int):
        super().__init__(message)
        self.wait = wait


# ---- documents --------------------------------------------------------------------------------
class NotNeeded(PipeError):
    """The auction house has a scan fresh enough already: this one is not wanted (409)."""
    def __init__(self, message: str, newest: int | None, wanted_from: int | None):
        super().__init__(message)
        self.newest, self.wanted_from = newest, wanted_from


def scan_document(sd: ScanData) -> dict:
    """What a scan file holds for its realm, as a fwc-scan/1 document."""
    items = {}
    for iid, it in sorted(sd.items.items()):
        if not it.complete:
            continue
        kinds = Counter((max(1, price), stack, band) for (price, stack), band in zip(it.listings, it.bands))   # under a copper a unit: a copper
        row = {"t": it.scanned_at, "l": [[price, stack, n] + ([band] if band else []) for (price, stack, band), n in sorted(kinds.items())]}
        if it.name:
            row["name"] = it.name
        if it.extra.get("full"):
            row["full"] = 1
        items[str(iid)] = row
    doc = {"format": SCAN_FORMAT, "realm": sd.realm, "faction": sd.faction, "scanned_at": max((r["t"] for r in items.values()), default=0),
           "helper": __version__, "items": items}
    if sd.realm_names:
        doc["realm_names"] = dict(sd.realm_names)
    if sd.connected:
        doc["connected"] = list(sd.connected)
    return doc


MAX_ITEMS, MAX_RUNGS = 20000, 400000      # in a scan, as the pipe has them (pipe/src/worker.js)
MAX_TIME = 2 ** 32 - 1                    # a time is unix seconds: past this it is not one
MAX_NAMES = 1000                          # realms in realm_names, or in connected
MAX_TEXT = 200                            # characters of an item's name, the helper's version
MAX_LIST_NAME = 80                        # characters of a list's name or a row's name in fwc-lists/1 (the longest shipped is 50)
# a rung's bounds, as the pipe has them. A bound here must be one no honest scan can reach: a
# single auction past it would have every honest scan of that house refused. They refuse numbers
# no client could have read (an integer past JavaScript's safe range), not prices nobody would
# pay: measured 9 Nov 2026, Forever's houses list units at up to 99,999,999,999 copper, stacks
# of 10000 and 5,937 auctions alike
MAX_PRICE, MAX_STACK, MAX_AUCTIONS = 2 ** 53 - 1, 1000000, 1000000


def _whole(x, lo: int = 0, hi: int = MAX_TIME) -> bool:
    """An integer (not a bool: JSON's true is not a number) from lo to hi."""
    return isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi


def _text(x, most: int = MAX_TEXT) -> bool:
    return isinstance(x, str) and len(x) <= most


def _id(key) -> bool:
    """An item id as a document's key: ASCII digits, ten at most (int() refuses other digits, and very long ones)."""
    return isinstance(key, str) and 0 < len(key) <= 10 and key.isascii() and key.isdigit()


def check_scan(doc) -> str | None:  # noqa: C901, PLR0912 - validator: one guard per field of a document anyone can send, read top to bottom
    """Why this is not a fwc-scan/1 document, or None when it is one. Everything the core
    reads of a scan is checked here, its type and its size, so that a document sent by anyone
    cannot fail where it is read (9 Nov 2026: one without scanned_at stopped the core's pull).
    What it names of the document is cut short: the text is the sender's."""
    if not isinstance(doc, dict) or doc.get("format") != SCAN_FORMAT:
        return f"not a {SCAN_FORMAT} document"
    if not isinstance(doc.get("realm"), str) or not doc["realm"].strip() or len(doc["realm"]) > 80:
        return "no realm"
    if doc.get("faction", "") not in FACTIONS + ("",):
        return f"faction {str(doc.get('faction'))[:20]!r} is not one of {', '.join(FACTIONS)}"
    if not _whole(doc.get("scanned_at")):
        return "scanned_at is not a time"
    if doc.get("helper") is not None and not _text(doc["helper"]):      # None: a house the core kept from scans that did not say
        return "helper is not a version"
    names, group = doc.get("realm_names", {}), doc.get("connected", [])
    if not isinstance(names, dict) or len(names) > MAX_NAMES or not all(_text(k, 80) and _text(v, 80) for k, v in names.items()):
        return "realm_names is not {realm: name}"
    if not isinstance(group, list) or len(group) > MAX_NAMES or not all(_text(g, 80) for g in group):
        return "connected is not a list of realms"
    if not isinstance(doc.get("items"), dict) or not doc["items"]:
        return "no items"
    if len(doc["items"]) > MAX_ITEMS:
        return "too many items"
    rungs = 0
    for key, row in doc["items"].items():
        if not _id(key) or not isinstance(row, dict) or not _whole(row.get("t")) or not isinstance(row.get("l"), list):
            return f"item {str(key)[:20]!r} is not an item"
        # what else a row may carry: its name, whether it was a full scan, and in a house as the
        # core keeps it, who it is from and whether it is unverified (inbox.merge)
        if not _text(row.get("name", "")) or row.get("full", 0) not in (0, 1) or row.get("u", 0) not in (0, 1) or not _text(row.get("by", ""), 80):
            return f"item {key}: its name, full, u or by is not what it should be"
        for rung in row["l"]:       # a unit price of 0 is a stack listed for under a copper a unit (addons before 0.6.1 sent it)
            if not (isinstance(rung, list) and len(rung) in (3, 4) and _whole(rung[0], 0, MAX_PRICE) and _whole(rung[1], 1, MAX_STACK)
                    and _whole(rung[2], 1, MAX_AUCTIONS) and (len(rung) == 3 or _whole(rung[3], 1, 4))):
                return f"item {key}: {repr(rung)[:60]} is not [unit price, stack size, auctions, time left]"
        rungs += len(row["l"])
        if rungs > MAX_RUNGS:
            return "too many auctions"
    return None


def scan_from_document(doc: dict, source: Path | None = None) -> ScanData:
    """A fwc-scan/1 document as the scan it was made from (without the addon's summary of
    earlier scans: a document holds one scan)."""
    problem = check_scan(doc)
    if problem:
        raise PipeError(problem)
    items = {}
    for key, row in doc["items"].items():
        rungs = sorted((max(1, r[0]), r[1], r[3] if len(r) > 3 else 0) for r in row["l"] for _ in range(r[2]))
        items[int(key)] = ScanItem(int(key), row.get("name"), [(p, q) for p, q, _ in rungs], True, row["t"],
                                   {"full": True} if row.get("full") else {}, [b for _, _, b in rungs] if any(b for _, _, b in rungs) else [])
    names, group = doc.get("realm_names"), doc.get("connected")
    return ScanData(items=items, realm=doc["realm"], path=source or Path("pipe"), faction=doc.get("faction", ""),
                    realm_names={str(k): str(v) for k, v in names.items()} if isinstance(names, dict) else {},
                    connected=[str(g) for g in group] if isinstance(group, list) else [])


def vendors_document(vendors: dict[int, dict], trainers: dict[int, dict] | None = None, recipes: dict[int, dict] | None = None) -> dict:
    """The vendors a helper's player has met, for the pipe (POST /v1/vendors): {"format",
    "helper", "vendors": {creature id: {name, map, x, y, t, faction, build, items: {item id:
    {price, stack, n, usable, t, cost?}}}}, "trainers": {creature id: {name, map, x, y, t,
    faction, build, skill, teaches: {service: the skill it asks for}}}} (the trainers since
    helper 1.6.12), "recipes": {recipe item id: {level: the scroll's minimum level from the
    client's item data, t, and since 1.7.5, from a tooltip the player brought up, tip: [line,
    level, ...], made: the made item, made_level: its item-data level}} (since 1.6.22). The
    pipe as deployed checks level and t and keeps a row whole, so the fields of 1.7.5 travel
    without a change to it. Nothing of the player: the vendor's name and where it stood, its
    wares and their prices, the trainer's and what it teaches at which skill, a scroll's
    levels, when each was seen."""
    return {"format": VENDORS_FORMAT, "helper": __version__,
            "vendors": {str(k): {**v, "items": {str(i): r for i, r in v["items"].items()}} for k, v in vendors.items()},
            "trainers": {str(k): {**t, "teaches": {str(n): int(level) for n, level in t["teaches"].items()}} for k, t in (trainers or {}).items()},
            "recipes": {str(k): {"level": int(r["level"]), "t": int(r.get("t") or 0), **{f: r[f] for f in RECIPE_EXTRAS if f in r}}
                        for k, r in (recipes or {}).items()}}


RECIPE_EXTRAS = ("tip", "made", "made_level")      # a recipe row's fields since 1.7.5, each there only when known


def _recipe_extras(row: dict) -> bool:
    """Whether a recipe row's fields of 1.7.5, those it has, are what they should be."""
    tip = row.get("tip", [2, 2])
    if not (isinstance(tip, list) and 0 < len(tip) <= 8 and len(tip) % 2 == 0 and all(_whole(n, 1, 100) for n in tip)):
        return False
    if "made" in row and not _whole(row["made"], 1, 10 ** 10):
        return False
    return "made_level" not in row or ("made" in row and _whole(row["made_level"], 0, 100))


def check_vendors(doc) -> str | None:  # noqa: C901, PLR0912 - validator: one guard per field of a document anyone can send, read top to bottom
    """Why this is not a fwc-vendors/1 document, or None when it is one."""
    if not isinstance(doc, dict) or doc.get("format") != VENDORS_FORMAT:
        return f"not a {VENDORS_FORMAT} document"
    trainers = doc.get("trainers", {})
    if not isinstance(trainers, dict):
        return "trainers is not a table"
    recipes = doc.get("recipes", {})
    if not isinstance(recipes, dict):
        return "recipes is not a table"
    if not isinstance(doc.get("vendors"), dict) or not (doc["vendors"] or trainers or recipes):
        return "no vendors"
    if len(doc["vendors"]) > 2000:
        return "too many vendors"
    if len(trainers) > 500:
        return "too many trainers"
    if len(recipes) > 3000:
        return "too many recipes"
    for iid, row in recipes.items():
        if not _id(iid) or not isinstance(row, dict) or not isinstance(row.get("level"), int) \
                or not 1 <= row["level"] <= 100 or not isinstance(row.get("t"), int):
            return f"recipe {str(iid)[:20]!r}: not a level"
        if not _recipe_extras(row):
            return f"recipe {str(iid)[:20]!r}: its tip, made or made_level is not what it should be"
    for tid, t in trainers.items():
        if not (isinstance(tid, str) and 0 < len(tid) <= 80) or not isinstance(t, dict) or not isinstance(t.get("name"), str) or len(t["name"]) > 80:
            return f"trainer {str(tid)[:40]!r} is not a trainer"
        if not (isinstance(t.get("map"), int) and isinstance(t.get("t"), int) and t.get("faction", "") in FACTIONS + ("",)):
            return f"trainer {str(tid)[:40]}: no map, time or faction"
        if not all(isinstance(t.get(k), (int, float)) and 0 <= t[k] <= 1 for k in ("x", "y")):
            return f"trainer {str(tid)[:40]}: not on its map"
        if not isinstance(t.get("skill"), str) or not t["skill"] or len(t["skill"]) > 40:
            return f"trainer {str(tid)[:40]}: no skill"
        if not isinstance(t.get("teaches"), dict) or len(t["teaches"]) > 400:
            return f"trainer {str(tid)[:40]}: no services, or too many"
        for name, level in t["teaches"].items():
            if not isinstance(name, str) or len(name) > 80 or not isinstance(level, int) or level < 0:
                return f"trainer {str(tid)[:40]}: {str(name)[:40]!r} is not a service"
    for vid, v in doc["vendors"].items():
        if not (isinstance(vid, str) and 0 < len(vid) <= 80) or not isinstance(v, dict) or not isinstance(v.get("name"), str) or len(v["name"]) > 80:
            return f"vendor {str(vid)[:40]!r} is not a vendor"
        if not (isinstance(v.get("map"), int) and isinstance(v.get("t"), int) and v.get("faction", "") in FACTIONS + ("",)):
            return f"vendor {str(vid)[:40]}: no map, time or faction"
        if not all(isinstance(v.get(k), (int, float)) and 0 <= v[k] <= 1 for k in ("x", "y")):
            return f"vendor {str(vid)[:40]}: not on its map"
        if not isinstance(v.get("items"), dict) or len(v["items"]) > 400:
            return f"vendor {str(vid)[:40]}: no items, or too many"
        for iid, row in v["items"].items():
            if not _id(iid) or not isinstance(row, dict) or not all(isinstance(row.get(k), int) for k in ("price", "stack", "n", "t")):
                return f"vendor {str(vid)[:40]}: item {str(iid)[:20]!r} is not a ware"
    return None


def mark_vendors(doc: dict) -> str:
    """What the sightings say, less the helper's version: "already sent" goes by it."""
    return hashlib.sha256(json.dumps([doc["vendors"], doc.get("trainers", {}), doc.get("recipes", {})], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]


def lists_document(queue: dict[str, list[tuple[int, str]]]) -> dict:
    """A fwc-lists/1 document of the lists, {list name: [(item id, name)]}, stamped now."""
    return {"format": LISTS_FORMAT, "generated": int(time.time()),
            "queue": {name: [[int(i), str(n)] for i, n in rows] for name, rows in queue.items()}}


def check_lists(doc) -> str | None:
    """What is wrong with a fwc-lists/1 document, or None when it is usable."""
    if not isinstance(doc, dict) or doc.get("format") != LISTS_FORMAT:
        return f"not a {LISTS_FORMAT} document"
    if not isinstance(doc.get("queue"), dict):
        return "no queue"
    for name, rows in doc["queue"].items():
        if not _text(name, MAX_LIST_NAME):
            return f"list {str(name)[:40]!r}: its name is not text of at most {MAX_LIST_NAME} characters"
        if not isinstance(rows, list) or any(not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], int) and _text(r[1], MAX_LIST_NAME))
                                             for r in rows):
            return f"list {name!r} is not [[item id, name], ...] with names of at most {MAX_LIST_NAME} characters"
    return None


def pack(doc: dict) -> bytes:
    """The document as it is sent: compact JSON, gzipped. The same document packs to the same
    bytes, so its digest says whether it was seen before."""
    text = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)


def unpack(data: bytes) -> dict:
    """A JSON document from the service's bytes, gunzipped first when they are gzipped."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        return json.loads(data.decode("utf-8"))
    except RecursionError:                          # JSON nested deeper than Python follows: no document of ours
        raise PipeError("the service's answer is nested too deep to read") from None


def digest(data: bytes) -> str:
    """The SHA-256 of the bytes, in hex."""
    return hashlib.sha256(data).hexdigest()


def _why(data: bytes) -> str:
    """What the service said was wrong, from its answer."""
    try:
        return json.loads(data.decode("utf-8")).get("error", "")
    except (ValueError, AttributeError):
        return data[:120].decode("utf-8", errors="replace")


def mark(doc: dict) -> str:
    """What a scan says, whichever helper sends it: the digest of its auction house and its
    items alone. "Already sent" goes by it, so that an update of the helper, which changes the
    document's `helper` and may add to what it says besides, does not send every scan again."""
    said = {"realm": doc["realm"], "faction": doc.get("faction", ""), "items": doc["items"]}
    return digest(json.dumps(said, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode("utf-8"))


# ---- the service ------------------------------------------------------------------------------
# The core's pace. The core fetches documents one by one (every new scan, every changed vendors
# document), and as fast as the pipe answers that would be a flood; so a Pipe speaking with the
# core's token keeps a steady pace, a request no sooner than CORE_PACE after the last, and never
# floods the pipe. A helper is not paced: it asks a handful of times when it starts and once or
# twice a save. A 429 the core gets anyway is waited out a few times, then given to the caller:
# the pull stops there and goes on from its cursor at the next pass. The numbers behind the
# pace: see docs/security.md in the core.
CORE_PACE = 1.25            # seconds from the start of one of the core's requests to the next
RULE_TRIES = 3              # 429s waited out in a row, at most, before the 429 is the answer
RULE_WAIT, RULE_WAIT_MOST = 11, 60     # seconds a 429 is waited out: this, or the Retry-After, up to a minute
_sleep, _clock = time.sleep, time.monotonic      # the tests fake these


class Pipe:
    """The service at `url`, spoken to with `token`. `pace` is the least time in seconds from
    the start of one request to the next; by default CORE_PACE when the token is the core's
    (FWC_PIPE_CORE_TOKEN), and none for a helper."""

    def __init__(self, url: str | None = None, token: str | None = None, register: bool = True, pace: float | None = None):
        self.url = (url or settings.saved("PIPE_URL") or settings.PIPE_URL or "").rstrip("/")
        if not self.url:
            raise PipeError("no pipe to talk to: set FWC_PIPE_URL")
        self.name = None
        if pace is None:            # a helper gives no token, and so is never paced; the core gives its own
            pace = CORE_PACE if token and token == settings.saved("PIPE_CORE_TOKEN") else 0.0
        self.pace = float(pace)
        self.token = token if token is not None else settings.saved("PIPE_TOKEN")
        self.registers = register and token is None and not self.token       # no token given: get one of our own
        if self.registers:
            mine = self._identity().get(self.url)
            if mine:
                self.name, self.token = mine["name"], mine["token"]

    # ---- a token of our own ---------------------------------------------------------------
    @staticmethod
    def _identity_file() -> Path:
        return settings.STATE / "identity.json"

    def _identity(self) -> dict:
        f = self._identity_file()
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except ValueError:
            return {}

    def register(self) -> str:
        """Ask the service for a token, keep it, and return the name that came with it."""
        status, data = self.request("POST", "/v1/register", json.dumps({"helper": __version__}).encode(), packed=False)
        if status == 429:
            raise TooSoon("the service is not registering anyone right now; try later", 3600)
        if status >= 400:
            raise PipeError(f"could not register with {self.url}: {status} {data[:120].decode('utf-8', errors='replace')}")
        answer = json.loads(data.decode("utf-8"))
        self.name, self.token = answer["name"], answer["token"]
        known = self._identity()
        known[self.url] = {"name": self.name, "token": self.token, "since": int(time.time())}
        settings.STATE.mkdir(parents=True, exist_ok=True)
        self._identity_file().write_text(json.dumps(known, indent=1), encoding="utf-8")
        return self.name

    def request(self, method: str, path: str, body: bytes | None = None, packed: bool = True,
                content_type: str = "application/json") -> tuple[int, bytes]:
        """One request, as (status, body). A paced Pipe (the core's) keeps its pace, and waits
        out a 429 up to RULE_TRIES times before answering with it; a helper's is answered at once."""
        pace = getattr(self, "pace", 0.0)
        tries = 0
        while True:
            if pace:
                wait = getattr(self, "_last", float("-inf")) + pace - _clock()
                if wait > 0:
                    _sleep(wait)
                self._last = _clock()
            status, data = self._request(method, path, body, packed, content_type)
            if status != 429 or not pace or tries >= RULE_TRIES:
                return status, data
            tries += 1
            _sleep(min(max(self.retry_after, RULE_WAIT), RULE_WAIT_MOST))

    def _request(self, method: str, path: str, body: bytes | None, packed: bool, content_type: str) -> tuple[int, bytes]:
        headers = {"User-Agent": f"{settings.NAME}-helper/{__version__}"}
        if self.token and path != "/v1/register":
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            headers["Content-Type"] = content_type
            if packed:
                headers["Content-Encoding"] = "gzip"
        req = urllib.request.Request(self.url + path, data=body, method=method, headers=headers)
        self.retry_after = 0
        try:
            with urllib.request.urlopen(req, timeout=settings.PIPE_TIMEOUT) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            self.retry_after = int(e.headers.get("Retry-After") or 0) if e.headers else 0
            return e.code, e.read()
        except OSError as e:
            raise PipeError(f"{self.url} could not be reached ({e})") from e

    def ask(self, method: str, path: str, body: bytes | None = None, missing_ok: bool = False, packed: bool = True,
            content_type: str = "application/json"):
        """One request to the service, its answer unpacked ({} when empty). A helper without a token registers
        first, and again when the service no longer knows its token. A 404 is None when `missing_ok`; a 429
        raises TooSoon, a 409 for a house with a fresh scan NotNeeded, any other error PipeError."""
        if self.registers and not self.token and path not in ("/v1/health", "/v1/register"):
            self.register()
        status, data = self.request(method, path, body, packed, content_type)
        if status == 401 and self.registers and self.token and path != "/v1/health":
            self.token = None                       # the service does not know our token (any more): ask for another
            self.register()
            status, data = self.request(method, path, body, packed, content_type)
        if status == 404 and missing_ok:
            return None
        if status == 429:
            try:
                why = json.loads(data.decode("utf-8")).get("error", "")
            except (ValueError, AttributeError):
                why = ""
            raise TooSoon(why or "sent too soon", self.retry_after or 60)
        if status == 409:
            try:
                told = json.loads(data.decode("utf-8"))
            except (ValueError, AttributeError):
                told = {}
            if told.get("fresh"):
                raise NotNeeded(told.get("error") or "not needed: the auction house has a fresh scan", told.get("newest"), told.get("wanted_from"))
        if status >= 400:
            raise PipeError(f"{method} {path}: {status} {_why(data)}".strip())
        return unpack(data) if data else {}

    def health(self) -> dict:
        """GET /v1/health: {"ok": true} when the service is up (no token needed)."""
        return self.ask("GET", "/v1/health")

    def me(self) -> dict:
        """GET /v1/me: {"name", "trust"} of the sender this token is."""
        return self.ask("GET", "/v1/me")

    def senders(self) -> list[dict]:
        """GET /v1/senders: every sender, its trust, scans, houses and when last seen (the core's token)."""
        return self.ask("GET", "/v1/senders")["senders"]

    def set_sender(self, name: str, trust: str, note: str = "") -> dict:
        """PUT /v1/senders/<name>: make a sender "trusted", "public" or "blocked", with a note (the core's token)."""
        return self.ask("PUT", f"/v1/senders/{name}", json.dumps({"trust": trust, "note": note}).encode(), packed=False)

    def send_vendors(self, doc: dict) -> dict:
        """POST /v1/vendors: the vendors seen. {"vendors": n, "new": true|false}."""
        problem = check_vendors(doc)
        if problem:
            raise PipeError(problem)
        return self.ask("POST", "/v1/vendors", pack(doc))

    def send_scan(self, doc: dict, sender: str | None = None) -> dict:
        """Send a scan. `sender` is for the core's token alone: the name the pipe keeps the scan
        under (what the core read from Blizzard's API is from "blizzard-api", not "core")."""
        return self.ask("POST", "/v1/scans" + (f"?sender={urllib.request.quote(sender)}" if sender else ""), pack(doc))

    def lists(self) -> dict | None:
        """GET /v1/lists: the fwc-lists/1 document of what the scanners should scan, None when none was set."""
        return self.ask("GET", "/v1/lists", missing_ok=True)

    def fresh(self) -> dict | None:
        """Each auction house's newest scan; None from a pipe from before the gate (12 Oct 2026)."""
        return self.ask("GET", "/v1/fresh", missing_ok=True, packed=False)

    def set_lists(self, doc: dict) -> dict:
        """PUT /v1/lists: set the lists the scanners scan (the core's token)."""
        return self.ask("PUT", "/v1/lists", pack(doc))

    PAGE = 500          # the most the service lists in one answer

    def scans(self, after: int = 0, realm: str | None = None, faction: str | None = None) -> list[dict]:
        """Every scan listed after id `after`, oldest first. The service answers a page at a
        time, so the pages are asked for until one comes short."""
        out: list[dict] = []
        after = int(after)
        while True:
            query = f"?after={after}&limit={self.PAGE}" + (f"&realm={urllib.request.quote(realm)}" if realm else "") \
                + (f"&faction={urllib.request.quote(faction)}" if faction is not None else "")
            page = self.ask("GET", "/v1/scans" + query)["scans"]
            out.extend(page)
            last = int(page[-1].get("id") or 0) if page else 0
            if len(page) < self.PAGE or last <= after:
                return out
            after = last

    def scan(self, scan_id: int) -> dict:
        """GET /v1/scans/<id>: one scan's fwc-scan/1 document (the core's token)."""
        return self.ask("GET", f"/v1/scans/{int(scan_id)}")

    def vendors(self, after: int = 0) -> list[dict]:
        """The vendors documents the helpers sent (the core's: GET /v1/vendors): [{sender,
        received_at, helper, vendors, wares, bytes}], those received after `after`."""
        return self.ask("GET", f"/v1/vendors?after={int(after)}")["vendors"]

    def vendor_doc(self, sender: str) -> dict:
        """One sender's vendors document, the newest (the core's: GET /v1/vendors/<sender>)."""
        return self.ask("GET", f"/v1/vendors/{urllib.request.quote(sender)}")

    # ---- the core's state, so that the core can run anywhere -------------------------------
    def state(self) -> bytes | None:
        """The core's inbox (data/pipe) as the zip the last run put; None when none was put yet."""
        status, data = self.request("GET", "/v1/state")
        if status == 404:
            return None
        if status >= 400:
            raise PipeError(f"GET /v1/state: {status} {_why(data)}".strip())
        return data

    def set_state(self, blob: bytes) -> dict:
        """PUT /v1/state: put the core's inbox, zipped, for the next run wherever it runs (the core's token)."""
        return self.ask("PUT", "/v1/state", blob, packed=False, content_type="application/zip")

    def site_state(self) -> bytes | None:
        """The site the core last built, as the zip the last run put; None when none was put yet.
        Apart from the inbox since 10 Nov 2026: the two in one request grew past what Cloudflare lets through."""
        status, data = self.request("GET", "/v1/state/site")
        if status == 404:
            return None
        if status >= 400:
            raise PipeError(f"GET /v1/state/site: {status} {_why(data)}".strip())
        return data

    def set_site_state(self, blob: bytes) -> dict:
        """PUT /v1/state/site: put the site the core built, zipped, beside its inbox (the core's token)."""
        return self.ask("PUT", "/v1/state/site", blob, packed=False, content_type="application/zip")

    def sell(self) -> dict | None:
        """The archivist's fwc-sell/1 document (what sold, per auction house and item); None when none was put yet."""
        status, data = self.request("GET", "/v1/sell")
        if status == 404:
            return None
        if status >= 400:
            raise PipeError(f"GET /v1/sell: {status} {_why(data)}".strip())
        return json.loads(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)

    def set_sell(self, doc: dict) -> dict:
        """PUT /v1/sell: put the archivist's fwc-sell/1 document for the cloud's pass (the core's token)."""
        return self.ask("PUT", "/v1/sell", pack(doc))

    def report(self) -> str | None:
        """The archivist's quality report (one HTML page); None when none was put yet."""
        status, data = self.request("GET", "/v1/report")
        if status == 404:
            return None
        if status >= 400:
            raise PipeError(f"GET /v1/report: {status} {_why(data)}".strip())
        return data.decode("utf-8", "replace")

    def set_report(self, html_text: str) -> dict:
        """PUT /v1/report: put the archivist's quality report, one HTML page (the core's token)."""
        return self.ask("PUT", "/v1/report", html_text.encode("utf-8"), packed=False, content_type="text/html; charset=utf-8")

    def move_blobs(self, after: str = "", limit: int = 50) -> dict:
        """Copies a page of what the service's database still holds into its bucket; the answer says
        `moved`, `had` (already there), `last` (the key to go on from) and `left`."""
        return self.ask("POST", f"/v1/blobs/move?limit={int(limit)}&after={urllib.request.quote(after, safe='')}")
