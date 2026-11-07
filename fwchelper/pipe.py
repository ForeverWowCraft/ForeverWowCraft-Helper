"""The pipe: scans go to a service, lists come back from it.

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


def check_scan(doc) -> str | None:
    """Why this is not a fwc-scan/1 document, or None when it is one."""
    if not isinstance(doc, dict) or doc.get("format") != SCAN_FORMAT:
        return f"not a {SCAN_FORMAT} document"
    if not isinstance(doc.get("realm"), str) or not doc["realm"].strip():
        return "no realm"
    if doc.get("faction", "") not in FACTIONS + ("",):
        return f"faction {doc.get('faction')!r} is not one of {', '.join(FACTIONS)}"
    if not isinstance(doc.get("items"), dict) or not doc["items"]:
        return "no items"
    for key, row in doc["items"].items():
        if not str(key).isdigit() or not isinstance(row, dict) or not isinstance(row.get("t"), int) or not isinstance(row.get("l"), list):
            return f"item {key!r} is not an item"
        for rung in row["l"]:       # a unit price of 0 is a stack listed for under a copper a unit (addons before 0.6.1 sent it)
            if not (isinstance(rung, list) and len(rung) in (3, 4) and all(isinstance(x, int) for x in rung) and rung[0] >= 0
                    and rung[1] > 0 and rung[2] > 0 and (len(rung) == 3 or 1 <= rung[3] <= 4)):
                return f"item {key}: {rung!r} is not [unit price, stack size, auctions, time left]"
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


def vendors_document(vendors: dict[int, dict], trainers: dict[int, dict] | None = None) -> dict:
    """The vendors a helper's player has met, for the pipe (POST /v1/vendors): {"format",
    "helper", "vendors": {creature id: {name, map, x, y, t, faction, build, items: {item id:
    {price, stack, n, usable, t, cost?}}}}, "trainers": {creature id: {name, map, x, y, t,
    faction, build, skill, teaches: {service: the skill it asks for}}}} (the trainers since
    helper 1.6.12). Nothing of the player: the vendor's name and where it stood, its wares and
    their prices, the trainer's and what it teaches at which skill, when each was seen."""
    return {"format": VENDORS_FORMAT, "helper": __version__,
            "vendors": {str(k): {**v, "items": {str(i): r for i, r in v["items"].items()}} for k, v in vendors.items()},
            "trainers": {str(k): {**t, "teaches": {str(n): int(level) for n, level in t["teaches"].items()}} for k, t in (trainers or {}).items()}}


def check_vendors(doc) -> str | None:
    """Why this is not a fwc-vendors/1 document, or None when it is one."""
    if not isinstance(doc, dict) or doc.get("format") != VENDORS_FORMAT:
        return f"not a {VENDORS_FORMAT} document"
    trainers = doc.get("trainers", {})
    if not isinstance(trainers, dict):
        return "trainers is not a table"
    if not isinstance(doc.get("vendors"), dict) or not (doc["vendors"] or trainers):
        return "no vendors"
    if len(doc["vendors"]) > 2000:
        return "too many vendors"
    if len(trainers) > 500:
        return "too many trainers"
    for tid, t in trainers.items():
        if not (isinstance(tid, str) and 0 < len(tid) <= 80) or not isinstance(t, dict) or not isinstance(t.get("name"), str) or len(t["name"]) > 80:
            return f"trainer {tid!r} is not a trainer"
        if not (isinstance(t.get("map"), int) and isinstance(t.get("t"), int) and t.get("faction", "") in FACTIONS + ("",)):
            return f"trainer {tid}: no map, time or faction"
        if not all(isinstance(t.get(k), (int, float)) and 0 <= t[k] <= 1 for k in ("x", "y")):
            return f"trainer {tid}: not on its map"
        if not isinstance(t.get("skill"), str) or not t["skill"] or len(t["skill"]) > 40:
            return f"trainer {tid}: no skill"
        if not isinstance(t.get("teaches"), dict) or len(t["teaches"]) > 400:
            return f"trainer {tid}: no services, or too many"
        for name, level in t["teaches"].items():
            if not isinstance(name, str) or len(name) > 80 or not isinstance(level, int) or level < 0:
                return f"trainer {tid}: {str(name)[:40]!r} is not a service"
    for vid, v in doc["vendors"].items():
        if not (isinstance(vid, str) and 0 < len(vid) <= 80) or not isinstance(v, dict) or not isinstance(v.get("name"), str) or len(v["name"]) > 80:
            return f"vendor {vid!r} is not a vendor"
        if not (isinstance(v.get("map"), int) and isinstance(v.get("t"), int) and v.get("faction", "") in FACTIONS + ("",)):
            return f"vendor {vid}: no map, time or faction"
        if not all(isinstance(v.get(k), (int, float)) and 0 <= v[k] <= 1 for k in ("x", "y")):
            return f"vendor {vid}: not on its map"
        if not isinstance(v.get("items"), dict) or len(v["items"]) > 400:
            return f"vendor {vid}: no items, or too many"
        for iid, row in v["items"].items():
            if not str(iid).isdigit() or not isinstance(row, dict) or not all(isinstance(row.get(k), int) for k in ("price", "stack", "n", "t")):
                return f"vendor {vid}: item {iid!r} is not a ware"
    return None


def mark_vendors(doc: dict) -> str:
    """What the sightings say, less the helper's version: "already sent" goes by it."""
    return hashlib.sha256(json.dumps([doc["vendors"], doc.get("trainers", {})], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:32]


def lists_document(queue: dict[str, list[tuple[int, str]]]) -> dict:
    return {"format": LISTS_FORMAT, "generated": int(time.time()),
            "queue": {name: [[int(i), str(n)] for i, n in rows] for name, rows in queue.items()}}


def check_lists(doc) -> str | None:
    if not isinstance(doc, dict) or doc.get("format") != LISTS_FORMAT:
        return f"not a {LISTS_FORMAT} document"
    if not isinstance(doc.get("queue"), dict):
        return "no queue"
    for name, rows in doc["queue"].items():
        if not isinstance(rows, list) or any(not (isinstance(r, list) and len(r) == 2 and isinstance(r[0], int)) for r in rows):
            return f"list {name!r} is not [[item id, name], ...]"
    return None


def pack(doc: dict) -> bytes:
    """The document as it is sent: compact JSON, gzipped. The same document packs to the same
    bytes, so its digest says whether it was seen before."""
    text = json.dumps(doc, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return gzip.compress(text.encode("utf-8"), compresslevel=9, mtime=0)


def unpack(data: bytes) -> dict:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return json.loads(data.decode("utf-8"))


def digest(data: bytes) -> str:
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
class Pipe:
    """The service at `url`, spoken to with `token`."""

    def __init__(self, url: str | None = None, token: str | None = None, register: bool = True):
        self.url = (url or settings.saved("PIPE_URL") or settings.PIPE_URL or "").rstrip("/")
        if not self.url:
            raise PipeError("no pipe to talk to: set FWC_PIPE_URL")
        self.name = None
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
        return self.ask("GET", "/v1/health")

    def me(self) -> dict:
        return self.ask("GET", "/v1/me")

    def senders(self) -> list[dict]:
        return self.ask("GET", "/v1/senders")["senders"]

    def set_sender(self, name: str, trust: str, note: str = "") -> dict:
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
        return self.ask("GET", "/v1/lists", missing_ok=True)

    def fresh(self) -> dict | None:
        """Each auction house's newest scan; None from a pipe from before the gate (12 Oct 2026)."""
        return self.ask("GET", "/v1/fresh", missing_ok=True, packed=False)

    def set_lists(self, doc: dict) -> dict:
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
        return self.ask("PUT", "/v1/state", blob, packed=False, content_type="application/zip")

    def move_blobs(self, after: str = "", limit: int = 50) -> dict:
        """Copies a page of what the service's database still holds into its bucket; the answer says
        `moved`, `had` (already there), `last` (the key to go on from) and `left`."""
        return self.ask("POST", f"/v1/blobs/move?limit={int(limit)}&after={urllib.request.quote(after, safe='')}")
