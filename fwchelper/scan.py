"""Read ForeverWowCraft Scanner data (the addon's FWCS_DB saved variable) and manage its Queue.lua.

Both scan modes (per-item SCAN and the FULL snapshot) write the same record shape, keyed by
dataset and item ID, so whoever reads a ladder need not care which produced it.

A dataset is an auction house: a realm and a faction, Alliance or Horde. The addon keeps each
under the key "<realm>|<faction>". Scans from before it knew the faction are under the realm's
name alone; their faction is "" (unknown). The house both factions share is not scanned (13
Oct 2026); a dataset of it left from before is passed over.

WHAT IS READ HERE, AND WHY (everything the addon gathers: docs/scanner-addon.md, "What the addon
gathers"): of the addon's saved file, the auction ladders and their history (load_scan), the
realm names (FWCS_DB.__realms, __groups), the merchants, trainers and recipe scrolls the player
met (vendors, trainers, recipes). pipe.py says which of it is sent and where. The characters'
own table (FWCS_DB.__chars: what each has) is read by plans.py to know which houses' routes to
fetch, never sent; the addon's settings (__ui) and its places (__places) are not read here.
"""
from __future__ import annotations
import glob
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import luatable, settings as config

ADDON_NAME = "ForeverWowCraftScanner"
PLANS_ADDON = "ForeverWowCraftPlans"                 # the second addon: what the helper writes, kept through an update of the scanner
HELPER_FILES = ("Plans.lua", "Fresh.lua", "Queue.lua")   # what the helper writes into it
SAVED, QUEUE = "FWCS_DB", "FWCS_QUEUE"              # the addon's saved variable and its queue
OLD_SAVED, OLD_QUEUE = "FCS_DB", "FCS_QUEUE"        # ... as the addon called them before it was renamed
FACTIONS = ("Alliance", "Horde")


def split_key(key: str) -> tuple[str, str]:
    """The addon's key of a dataset as (realm, faction)."""
    realm, _, faction = key.partition("|")
    return realm, faction


def dataset_name(realm: str, faction: str = "") -> str:
    """'Stonespine (Horde)', or the realm alone when the faction is not known."""
    return f"{realm} ({faction})" if faction else realm


def faction_named(text: str | None) -> str | None:
    """'horde' -> 'Horde'; None stays None (any faction)."""
    if text is None:
        return None
    for f in FACTIONS:
        if f.lower() == text.strip().lower():
            return f
    if text.strip().lower() in ("", "unknown", "none"):
        return ""
    raise SystemExit(f"unknown faction {text!r}; one of: {', '.join(FACTIONS)}")


@dataclass
class ScanItem:
    """One item's price ladder as recorded by the addon (FWCS_DB[realm][item_id])."""
    item_id: int
    name: str | None
    listings: list[tuple[int, int]]   # (unit price copper, quantity) ascending by price
    complete: bool                     # False when the addon skipped the item (see extra["reason"])
    scanned_at: int
    extra: dict = field(default_factory=dict)   # reason, attempts, assumed, full
    # the time each listing had left, one per listing in the same order: 1 short (under 30 min),
    # 2 medium (under 2 h), 3 long (under 12 h), 4 very long; 0 when the addon did not say.
    # Empty when it never said (addons before 1.0.3).
    left: list[int] = field(default_factory=list)

    @property
    def bands(self) -> list[int]:
        """The time left of each listing (see `left`), 0 for every listing when unknown."""
        return self.left if len(self.left) == len(self.listings) else [0] * len(self.listings)

    @property
    def min_price(self) -> int | None:
        """The lowest unit price listed, in copper; None when nothing is listed."""
        return self.listings[0][0] if self.listings else None

    @property
    def total(self) -> int:
        """Units listed in all."""
        return sum(q for _, q in self.listings)

    def cost_for(self, n: float, scarcity: float = 0.25) -> tuple[float, float]:
        """Cost of buying n units (may be fractional) walking up the ladder. Returns (copper,
        units beyond supply).

        Units past the listed supply are charged the highest listed price times (1 + scarcity).
        """
        remaining, total = n, 0.0
        for price, qty in self.listings:
            take = min(qty, remaining)
            total += take * price
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 0 and self.listings:
            total += remaining * self.listings[-1][0] * (1 + scarcity)
        return total, max(0, remaining)


@dataclass
class ScanData:
    """One auction house's scan as the addon's saved file holds it (load_scan): each item's ladder, the
    lowest prices over time, and the realm, faction and connected realms the house is known by."""
    items: dict[int, ScanItem]
    realm: str
    path: Path
    history: dict[int, list[tuple[int, int, int]]] = field(default_factory=dict)  # item -> [(time, min, units)]
    dropped_stale: list[str] = field(default_factory=list)
    faction: str = ""           # "Alliance" | "Horde", or "" when the scan does not say
    # Connected realms share an auction house, and the addon names it by the group's first realm
    # as the client spells it without spaces. realm_names: {that spelling: the name as shown}, of
    # the realms the account has characters on; connected: the group, when the realm is in one.
    realm_names: dict[str, str] = field(default_factory=dict)
    connected: list[str] = field(default_factory=list)

    @property
    def dataset(self) -> str:
        """The auction house this is a scan of: 'Stonespine (Horde)'."""
        return dataset_name(self.realm, self.faction)

    @property
    def realm_shown(self) -> str:
        """The realm's name as the client shows it, when known; else as the scan names it."""
        return self.realm_names.get(self.realm, self.realm)

    def smoothed_min(self, item_id: int, basis: str, hours: float) -> int | None:
        """Lowest price aggregated over the scans of the last `hours`: 'median', 'min' or 'max'.
        Points where nothing was listed (min 0) are ignored. None when no such points exist."""
        cutoff = time.time() - hours * 3600
        prices = sorted(m for t, m, _ in self.history.get(item_id, []) if t >= cutoff and m > 0)
        if not prices:
            return None
        if basis == "min":
            return prices[0]
        if basis == "max":
            return prices[-1]
        return prices[len(prices) // 2]

    def rescaled_items(self, basis: str, hours: float) -> dict[int, ScanItem]:
        """Copy of `items` with each ladder shifted so its lowest price equals the smoothed value
        (shape preserved). Items without enough history keep their spot ladder."""
        if basis == "spot":
            return self.items
        out = {}
        for iid, it in self.items.items():
            target = self.smoothed_min(iid, basis, hours) if it.listings else None
            if target is None or it.listings[0][0] <= 0:
                out[iid] = it
                continue
            f = target / it.listings[0][0]
            out[iid] = ScanItem(it.item_id, it.name, [(max(1, round(p * f)), q) for p, q in it.listings],
                                it.complete, it.scanned_at, dict(it.extra, rescaled=f), list(it.left))
        return out

    def volatility(self, item_id: int, hours: float) -> float | None:
        """Coefficient of variation of the lowest price over the window, or None if < 3 points."""
        cutoff = time.time() - hours * 3600
        prices = [m for t, m, _ in self.history.get(item_id, []) if t >= cutoff and m > 0]
        if len(prices) < 3:
            return None
        mean = sum(prices) / len(prices)
        var = sum((p - mean) ** 2 for p in prices) / len(prices)
        return (var ** 0.5) / mean if mean else None

    def apply_max_age(self, max_age_hours: float) -> None:
        """Drop records older than the limit. Needed because an item nobody lists is only ever
        refreshed by a scan that includes it; a very old ladder is worse than none."""
        cutoff = time.time() - max_age_hours * 3600
        for iid, it in list(self.items.items()):
            if it.scanned_at < cutoff:
                del self.items[iid]
                self.dropped_stale.append(it.name or str(iid))

    @property
    def newest(self) -> int:
        """When the most recently scanned item was scanned (0 without items)."""
        return max((it.scanned_at for it in self.items.values()), default=0)

    @property
    def oldest(self) -> int:
        """When the least recently scanned item was scanned (0 without items)."""
        return min((it.scanned_at for it in self.items.values()), default=0)

    def age_range(self) -> str:
        """'newest 2 min ago' or, when records come from different scans (a FULL snapshot
        followed by a per-list SCAN), 'newest 2 min ago, oldest 40 min ago'."""
        newest, oldest = age_text(self.newest), age_text(self.oldest)
        return f"newest {newest}" + (f", oldest {oldest}" if oldest != newest else "")


# ---- locating things --------------------------------------------------------------------
COMMON_WOW_DIRS = ("/Applications/World of Warcraft", "~/Applications/World of Warcraft", "/Applications/Games/World of Warcraft") \
    if sys.platform == "darwin" else \
    (r"C:\Program Files (x86)\World of Warcraft", r"C:\World of Warcraft", r"C:\Games\World of Warcraft",
     r"D:\World of Warcraft", r"D:\Games\World of Warcraft", r"D:\WorldOfWarcraft\World of Warcraft")


def _registry_wow_dirs() -> list[Path]:
    r"""Base folders Battle.net registered (InstallPath points at a flavour folder, e.g.
    '...\World of Warcraft\_retail_\'; its parent is the base)."""
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft"),
                      (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Blizzard Entertainment\World of Warcraft")):
        try:
            with winreg.OpenKey(hive, key) as k:
                value, _ = winreg.QueryValueEx(k, "InstallPath")
        except OSError:
            continue
        p = Path(str(value).rstrip("\\/"))
        out.append(p.parent if p.name.startswith("_") and p.name.endswith("_") else p)
    return out


def flavor() -> str:
    """The client folder to use (FWC_WOW_FLAVOR, else settings.WOW_FLAVOR)."""
    return config.env("WOW_FLAVOR", config.WOW_FLAVOR)


def portal() -> str | None:
    """The region this client plays in ("US", "EU", ...), from the game's own Config.wtf (its
    line SET portal): known before the addon has saved anything, so the routes of the region's
    auction houses can be fetched for a player's very first login. None without the file or
    the line."""
    try:
        text = (wow_dir() / flavor() / "WTF" / "Config.wtf").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r'^SET portal "([A-Za-z]{2,4})"', text, re.M)
    return m.group(1).upper() if m else None


def wow_dir() -> Path:
    """The World of Warcraft base folder: FWC_WOW_DIR if set; else settings.WOW_DIR when it exists;
    else what Battle.net registered or a common install folder, preferring one that holds the
    flavour folder. Falls back to settings.WOW_DIR so error messages name a path."""
    env = config.env("WOW_DIR")
    if env:
        return Path(env)
    configured = Path(config.WOW_DIR)
    candidates = [configured] + _registry_wow_dirs() + [Path(c).expanduser() for c in COMMON_WOW_DIRS]
    for c in candidates:
        if (c / flavor()).is_dir():
            return c
    for c in candidates:
        if c.is_dir():
            return c
    return configured


def flavors_present() -> list[str]:
    """Client folders (_retail_, _classic_era_, ...) that exist under the WoW folder."""
    base = wow_dir()
    return sorted(p.name for p in base.glob("_*_") if p.is_dir()) if base.is_dir() else []


def addons_dir() -> Path:
    """The game's AddOns folder: <WoW folder>/<client folder>/Interface/AddOns."""
    return wow_dir() / flavor() / "Interface" / "AddOns"


def plans_addon_dir(dest_root: Path | None = None) -> Path:
    """The second addon's folder: where the helper writes the routes, the lists and the freshness."""
    return (dest_root or addons_dir()) / PLANS_ADDON


def toc_version(folder: Path, name: str) -> tuple[int, ...] | None:
    """The `## Version:` of an addon folder, as numbers, or None when there is no .toc."""
    try:
        for line in (folder / f"{name}.toc").read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("## Version:"):
                return tuple(int(x) for x in re.findall(r"[0-9]+", line.split(":", 1)[1]))
    except OSError:
        pass
    return None


def find_saved_variables() -> list[Path]:
    """All ForeverWowCraftScanner.lua files under the flavour's WTF folder, newest first, along
    with those the addon wrote under its old name."""
    folder = wow_dir() / flavor() / "WTF" / "Account" / "*" / "SavedVariables"
    found = [p for name in (ADDON_NAME, config.OLD_ADDON_NAME) for p in glob.glob(str(folder / f"{name}.lua"))]
    return [Path(p) for p in sorted(found, key=os.path.getmtime, reverse=True)]


# ---- reading scan data ------------------------------------------------------------------
def _datasets(db: dict) -> dict[str, dict]:
    """The auction houses a saved file holds, by the addon's key: a faction's, or one from
    before the faction was recorded. One of the house both factions share (scanned 29 Sep to
    13 Oct 2026) is passed over."""
    return {k: v for k, v in db.items() if isinstance(k, str) and not k.startswith("__") and isinstance(v, dict)
            and split_key(k)[1] in FACTIONS + ("",)}


def _newest(table: dict) -> int:
    return max((int(rec.get("t") or 0) for iid, rec in table.items() if isinstance(iid, int) and isinstance(rec, dict)), default=0)


def vendors(path: Path | None = None) -> dict[int, dict]:
    """The vendors the addon has seen (FWCS_DB.__vendors, since addon 1.6.5): {creature id:
    {"name", "map", "x", "y", "t", "faction", "build", "items": {item id: {"price", "stack",
    "n", "usable", "t", "cost"?}}}}. Empty without the file or the table."""
    if path is None:
        found = find_saved_variables()
        if not found:
            return {}
        path = found[0]
    try:
        data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return {}
    db = data.get(SAVED) or data.get(OLD_SAVED) or {}
    held = db.get("__vendors") if isinstance(db, dict) else None
    out: dict[int, dict] = {}
    for vid, v in (held.items() if isinstance(held, dict) else []):
        if not (isinstance(vid, (int, str)) and isinstance(v, dict) and isinstance(v.get("items"), dict)):     # a name where the client gave no id
            continue
        items = {}
        for iid, row in v["items"].items():
            if isinstance(iid, int) and isinstance(row, dict):
                items[iid] = {"price": int(row.get("price") or 0), "stack": int(row.get("stack") or 1), "n": int(row.get("n", -1) if row.get("n") is not None else -1),
                              "usable": bool(row.get("usable")), "t": int(row.get("t") or 0),
                              **({"cost": {int(k): int(c) for k, c in row["cost"].items() if isinstance(k, int)}} if isinstance(row.get("cost"), dict) else {})}
        out[vid] = {"name": str(v.get("name") or ""), "map": int(v.get("map") or 0), "x": float(v.get("x") or 0), "y": float(v.get("y") or 0),
                    "t": int(v.get("t") or 0), "faction": str(v.get("faction") or ""), "build": v.get("build"), "items": items}
    return out


def trainers(path: Path | None = None) -> dict[int, dict]:
    """The trainers the addon has seen (FWCS_DB.__trainers, since addon 1.6.12): {creature id:
    {"name", "map", "x", "y", "t", "faction", "build", "skill", "teaches": {service name: the
    skill it asks for}}}. Empty without the file or the table."""
    if path is None:
        found = find_saved_variables()
        if not found:
            return {}
        path = found[0]
    try:
        data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return {}
    db = data.get(SAVED) or data.get(OLD_SAVED) or {}
    held = db.get("__trainers") if isinstance(db, dict) else None
    out: dict[int, dict] = {}
    for tid, t in (held.items() if isinstance(held, dict) else []):
        if not (isinstance(tid, (int, str)) and isinstance(t, dict) and isinstance(t.get("teaches"), dict) and t.get("skill")):
            continue
        teaches = {str(n): int(level) for n, level in t["teaches"].items() if isinstance(n, str) and isinstance(level, (int, float))}
        out[tid] = {"name": str(t.get("name") or ""), "map": int(t.get("map") or 0), "x": float(t.get("x") or 0), "y": float(t.get("y") or 0),
                    "t": int(t.get("t") or 0), "faction": str(t.get("faction") or ""), "build": t.get("build"), "skill": str(t["skill"]), "teaches": teaches}
    return out


def recipes(path: Path | None = None) -> dict[int, dict]:
    """The recipe scrolls the addon looked at (FWCS_DB.__recipes, since addon 1.6.22): {item id:
    {"level": the scroll's minimum level from the client's item data, "t", and since addon 1.7.5,
    from a tooltip the player brought up, "tip": [line, level, ...] (each "Requires Level N" line
    of the tooltip and its position), "made": the item the recipe makes, "made_level": that
    item's minimum level from the item data}}. "level" has meant the same in every version, so a
    row of 1.7.4 or before (level alone) reads as it always did. Empty without the file or the
    table."""
    if path is None:
        found = find_saved_variables()
        if not found:
            return {}
        path = found[0]
    try:
        data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, SyntaxError):
        return {}
    db = data.get(SAVED) or data.get(OLD_SAVED) or {}
    held = db.get("__recipes") if isinstance(db, dict) else None
    out: dict[int, dict] = {}
    for iid, row in (held.items() if isinstance(held, dict) else []):
        if isinstance(iid, int) and isinstance(row, dict) and isinstance(row.get("l"), (int, float)) and 1 <= row["l"] <= 100:
            out[iid] = {"level": int(row["l"]), "t": int(row.get("t") or 0)}
            # since addon 1.7.5, from the scroll's tooltip when the player hovered it: each
            # "Requires Level N" line as [line, N, ...], the made item and its item-data level
            tip = row.get("tip")
            if isinstance(tip, list) and 0 < len(tip) <= 2 * MAX_TIP_LINES and len(tip) % 2 == 0 \
                    and all(type(n) is int and 0 < n <= 100 for n in tip):
                out[iid]["tip"] = tip
            if type(row.get("made")) is int and row["made"] > 0:
                out[iid]["made"] = row["made"]
                if type(row.get("madel")) is int and 0 <= row["madel"] <= 100:
                    out[iid]["made_level"] = row["madel"]
    return out


MAX_TIP_LINES = 4                 # "Requires Level" lines kept of one scroll's tooltip (one on every scroll seen)


def datasets(path: Path | None = None) -> list[tuple[str, str, int, int]]:
    """What a saved file holds: [(realm, faction, items, time of the newest scan)], the most
    recently scanned first."""
    if path is None:
        found = find_saved_variables()
        if not found:
            return []
        path = found[0]
    data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
    db = data.get(SAVED) or data.get(OLD_SAVED) or {}
    out = [(*split_key(k), sum(1 for i in v if isinstance(i, int)), _newest(v)) for k, v in _datasets(db).items()]
    return sorted(out, key=lambda d: (-d[3], -d[2]))


def load_scan(path: Path | None = None, realm: str | None = None, faction: str | None = None) -> ScanData:  # noqa: C901 - baseline 9 Nov 2026, to be split
    """Parse the addon's SavedVariables file (newest one found when `path` is None). Of the
    datasets it holds, the one of `realm` and `faction`; left open, the most recently scanned."""
    faction = faction_named(faction)
    if path is None:
        found = find_saved_variables()
        if not found:
            raise SystemExit(f"no {ADDON_NAME}.lua found under {wow_dir() / flavor() / 'WTF'}; "
                             "install the addon, run a scan, then click SAVE in game")
        path = found[0]
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b" or raw.lstrip()[:1] == b"{":      # a scan as it travels through the pipe
        from . import pipe
        sd = pipe.scan_from_document(pipe.unpack(raw), path)
        if (realm is not None and realm != sd.realm) or (faction is not None and faction != sd.faction):
            raise SystemExit(f"{dataset_name(realm or sd.realm, faction or '')} not in scan file; it holds {sd.dataset}")
        return sd
    data = luatable.parse(raw.decode("utf-8", errors="ignore"))
    db = data.get(SAVED) or data.get(OLD_SAVED) or {}
    held = _datasets(db)
    if not held:
        raise SystemExit(f"{path} holds no scan data yet (run a scan, then click SAVE in game)")
    fits = [k for k in held if (realm is None or split_key(k)[0] == realm) and (faction is None or split_key(k)[1] == faction)]
    if not fits:
        raise SystemExit(f"{dataset_name(realm or 'any realm', faction or '')} not in scan file; it holds: "
                         + ", ".join(dataset_name(*split_key(k)) for k in held))
    key = max(fits, key=lambda k: (_newest(held[k]), len(held[k])))
    realm, faction = split_key(key)
    saved, db = db, {realm: held[key]}
    items: dict[int, ScanItem] = {}
    history: dict[int, list[tuple[int, int, int]]] = {}
    for iid, rows in (db[realm].get("__history") or {}).items():
        if isinstance(iid, int) and isinstance(rows, list):
            history[iid] = [(int(r[0]), int(r[1]), int(r[2])) for r in rows if isinstance(r, list) and len(r) >= 3]
    for iid, rec in db[realm].items():
        if not isinstance(iid, int) or not isinstance(rec, dict):
            continue
        rows = sorted((int(r[0]), int(r[1]), int(r[2]) if len(r) >= 3 and isinstance(r[2], int) and 1 <= r[2] <= 4 else 0)
                      for r in (rec.get("l") or []) if isinstance(r, (list, tuple)) and len(r) >= 2)
        items[iid] = ScanItem(
            item_id=iid, name=rec.get("name"), listings=[(p, q) for p, q, _ in rows],
            complete=bool(rec.get("complete")), scanned_at=int(rec.get("t") or 0),
            extra={k: rec[k] for k in ("reason", "attempts", "assumed", "full") if k in rec},
            left=[b for _, _, b in rows] if any(b for _, _, b in rows) else [],
        )
    names = {k: v for k, v in (saved.get("__realms") or {}).items() if isinstance(k, str) and isinstance(v, str)}
    group = (saved.get("__groups") or {}).get(realm)
    return ScanData(items=items, realm=realm, path=path, history=history, faction=faction, realm_names=names,
                    connected=[str(g) for g in group] if isinstance(group, list) else [])


def age_text(scanned_at: int) -> str:
    """Human-readable age of a unix timestamp ('30 min ago', '6 h ago', '3 days ago')."""
    if not scanned_at:
        return "unknown age"
    mins = int((time.time() - scanned_at) // 60)
    if mins < 90:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 48:
        return f"{hours} h ago"
    return f"{hours // 24} days ago"


# ---- the addon's queue + installation ---------------------------------------------------
def read_queue(path: Path) -> dict[str, list[tuple[int, str]]]:
    """Parse an existing Queue.lua into {list name: [(item_id, name), ...]}."""
    if not path.exists():
        return {}
    try:
        data = luatable.parse(path.read_text(encoding="utf-8", errors="ignore"))
        data = data.get(QUEUE) or data.get(OLD_QUEUE) or {}
    except SyntaxError:
        return {}
    return {str(name): [(int(r[0]), str(r[1])) for r in rows if isinstance(r, list) and len(r) >= 2]
            for name, rows in data.items() if isinstance(rows, list)}


def queue_file() -> Path:
    """The queue beside the addon's source: what `install-addon` installs."""
    return config.ADDON_SOURCE / ADDON_NAME / "Queue.lua"


def write_queue(lists: dict[str, list[tuple[int, str]]], replace: bool = False, where: Path | None = None) -> tuple[list[Path], list[str]]:
    """Merge `lists` into `where` (addon/ForeverWowCraftScanner/Queue.lua, the lists the addon
    ships with, unless another is named: the helper keeps what it fetches in its state folder)
    and into the second addon's copy when the addons are installed. Other lists are kept unless
    `replace`. The game reads the file at the next /reload. Returns (paths written, list names
    now queued)."""
    repo = where or queue_file()
    merged = {} if replace else read_queue(repo)
    merged.update(lists)
    lines = ["-- Generated by `python fwc.py shopping-list <profession|all>`; do not edit by hand.",
             '-- FWCS_QUEUE = { ["list name"] = { {itemID, "item name"}, ... }, ... }',
             "FWCS_QUEUE = {"]
    for name, items in merged.items():
        lines.append(f'  ["{name}"] = {{')
        for iid, iname in items:
            safe = iname.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    {{{iid}, "{safe}"}},')
        lines.append("  },")
    lines.append("}")
    text = "\n".join(lines) + "\n"
    targets = [repo]
    installed = plans_addon_dir() / "Queue.lua"
    if installed.parent.is_dir():
        targets.append(installed)
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text(text, encoding="utf-8")
    return targets, list(merged)


def install_addon(dest_root: Path | None = None, force: bool = False) -> Path:
    """Put the two addons into the AddOns folder. The scanner, addon/ForeverWowCraftScanner, replaces
    any previous copy, unless the copy there is newer than this helper's (CurseForge updated it)
    and `force` is not given: then it is left as it is. The second addon, ForeverWowCraftPlans,
    is always brought up to date (install_plans_addon). The addon under its old name is removed
    (two scanners would both run), and the scans it saved are carried over, see
    carry_over_saved_scans. Returns the scanner's folder."""
    src = config.ROOT / "addon" / ADDON_NAME
    root = dest_root or addons_dir()
    dest = root / ADDON_NAME
    if not root.is_dir():
        # a game installed and never started has no Interface\AddOns yet: the game loads addons
        # from the folder all the same, so it is made (a folder given by hand is not: a slip in
        # it would be an addon somewhere nobody looks)
        if dest_root is None and (wow_dir() / flavor()).is_dir():
            root.mkdir(parents=True)
            print(f"Made the AddOns folder, {root}: the game has not been started here yet.")
        else:
            raise SystemExit(f"AddOns folder not found: {root}  (set FWC_WOW_DIR / FWC_WOW_FLAVOR; "
                             f"`where` shows what was detected)")
    old = root / config.OLD_ADDON_NAME
    if old.exists():
        shutil.rmtree(old)
    have, mine = toc_version(dest, ADDON_NAME), toc_version(src, ADDON_NAME)
    if force or not have or not mine or have <= mine:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    install_plans_addon(root)
    if dest_root is None:
        carry_over_saved_scans()
    return dest


def install_plans_addon(root: Path) -> Path:
    """The second addon, ForeverWowCraftPlans, beside the scanner: its .toc from the source, and
    each file the helper writes (HELPER_FILES) from the copy kept in state/ when there is one,
    else the scanner's own (the lists it comes with; no routes, no freshness). It depends on the
    scanner and so loads after it, and its tables are the ones the scanner then has; an update
    of the scanner from CurseForge replaces the scanner's folder and leaves this one alone."""
    folder = root / PLANS_ADDON
    folder.mkdir(exist_ok=True)
    shutil.copyfile(config.ADDON_SOURCE / PLANS_ADDON / f"{PLANS_ADDON}.toc", folder / f"{PLANS_ADDON}.toc")
    for name in HELPER_FILES:
        kept = config.STATE / name
        shutil.copyfile(kept if kept.exists() else config.ADDON_SOURCE / ADDON_NAME / name, folder / name)
    return folder


def carry_over_saved_scans(wtf: Path | None = None) -> list[Path]:
    """Give the renamed addon the scans the old one saved: beside every ForeverCraftScanner.lua
    that has no ForeverWowCraftScanner.lua, write one with the same data under the new variable
    name. The old file is left where it is. Returns the files written. Do this with the game
    closed: at logout the game writes what it has in memory over the file."""
    wtf = wtf or wow_dir() / flavor() / "WTF"
    written = []
    for old in glob.glob(str(wtf / "Account" / "*" / "SavedVariables" / f"{config.OLD_ADDON_NAME}.lua")):
        new = Path(old).with_name(f"{ADDON_NAME}.lua")
        if new.exists():
            continue
        text = Path(old).read_text(encoding="utf-8", errors="ignore")
        new.write_text(re.sub(rf"(?m)^{OLD_SAVED}\b", SAVED, text), encoding="utf-8")
        written.append(new)
    return written
