"""When each auction house was last scanned, written into the addon as Fresh.lua, so that the
addon offers a scan only when one is wanted:

    FWCS_FRESH = { written = <time>, fresh = <seconds a scan stays fresh>,
                   houses = { ["<realm>"] = { ["<faction>"] = { newest = <time> } } } }

While the house's newest scan is under `fresh` old, the FULL / SCAN box is not offered when the
auction house opens. The addon reads the file at the next /reload, like Plans.lua.

Where it comes from: since 1.8.4, the pipe's answer to a scan the helper sends (learn): a scan
taken (201) is the house's newest, and a scan refused as not needed (409) names the newest the
pipe holds and when a scan is wanted again. Other houses' entries already in the file are kept
until they are no longer fresh. `python fwch.py fresh` still asks the pipe for every house (GET
/v1/fresh) and writes its whole answer; until 1.8.3 the watch asked that every FRESH_EVERY
seconds (or as often as the site's houses.json said), which was most of a helper's requests to
the pipe. The pipe refuses a scan it does not need either way (409): this is what keeps the box
out of the way."""
from __future__ import annotations
import time
from pathlib import Path

from . import luatable, scan, settings
from .plans import _whole, lua

DEFAULT_FRESH = 600            # seconds a scan stays fresh when nothing better is known (the pipe's FRESH_SECONDS as of 2026)
FRESH_RANGE = (60, 86400)      # seconds: a `fresh` outside is no value the pipe would give, and is not used
CLOCK_AHEAD = 600              # seconds a time the pipe gives may be ahead of this computer's clock (a clock drifts): past it, no time

GLOBAL = "FWCS_FRESH"


def for_addon(told: dict) -> dict:
    """The pipe's answer as the addon reads it: houses by realm, then faction ("" when the scan
    did not say), each with its newest scan."""
    houses: dict[str, dict] = {}
    for key, h in (told.get("houses") or {}).items():
        realm, _, faction = str(key).partition("|")
        if not isinstance(h, dict) or not _whole(h.get("newest")):          # a time that is no number is no scan
            continue
        houses.setdefault(realm, {})[faction] = {"newest": _whole(h["newest"])}
    return {"written": int(time.time()), "fresh": _whole(told.get("fresh")) or DEFAULT_FRESH, "houses": houses}


def fresh_text(told: dict) -> str:
    """Fresh.lua's text for the pipe's answer `told`: a header, then the FWCS_FRESH table the addon reads."""
    return "\n".join([
        "-- Written by the helper from the pipe's answers to the scans it sends (and by `python fwch.py fresh`); do not edit by hand.",
        "-- When each auction house was last scanned by anyone. See fwchelper/fresh.py.",
        f"{GLOBAL} = " + lua(for_addon(told)), ""])


def kept_file() -> Path:
    """The Fresh.lua the helper keeps, so that installing the addon again does not lose it."""
    return settings.STATE / "Fresh.lua"


def installed_file() -> Path:
    """The second addon's copy (ForeverWowCraftPlans), which the game reads."""
    return scan.plans_addon_dir() / "Fresh.lua"


def write(told: dict) -> list[Path]:
    """Write Fresh.lua: the helper's own copy, and the installed addon's when it is installed."""
    text = fresh_text(told)
    targets = [kept_file()] + ([installed_file()] if installed_file().parent.is_dir() else [])
    for t in targets:
        scan.write_whole(t, text)
    return targets


def fresh_minutes(told: dict) -> int:
    """How long the pipe last said a scan stays fresh (its own value, `fresh`), in whole minutes, at least one."""
    return max(1, round((_whole(told.get("fresh")) or DEFAULT_FRESH) / 60))


def not_needed(told: dict | None, realm: str, faction: str, scanned_at: int) -> int | None:
    """Whether a scan of this house taken at `scanned_at` is one the pipe would refuse as not
    needed, by what it last said: the newest scan it holds when that is fresh enough, else None.
    The pipe decides for real; this saves sending what it would refuse."""
    if not told:
        return None
    h = (told.get("houses") or {}).get(f"{realm}|{faction}")
    newest = _whole(h.get("newest")) if isinstance(h, dict) else 0
    if newest and scanned_at - newest < (_whole(told.get("fresh")) or DEFAULT_FRESH):
        return newest
    return None


def a_time(x, now: int | None = None) -> bool:
    """Whether `x`, from the pipe's answer, is a time a house's newest scan can have: a whole
    number (not a bool), after 0, and not past this computer's clock by more than CLOCK_AHEAD."""
    now = int(time.time()) if now is None else now
    return isinstance(x, int) and not isinstance(x, bool) and 0 < x <= now + CLOCK_AHEAD


def seconds(x) -> int | None:
    """`x` as the seconds a scan stays fresh when it is a value the pipe could give (FRESH_RANGE), else None."""
    return x if isinstance(x, int) and not isinstance(x, bool) and FRESH_RANGE[0] <= x <= FRESH_RANGE[1] else None


def window(newest, wanted_from) -> int | None:
    """How long a scan stays fresh by a 409's `newest` and `wanted_from` (the pipe wants a scan
    again `fresh` seconds after the newest); None when the two are not numbers that say so."""
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (newest, wanted_from)):
        return None
    return seconds(wanted_from - newest)


def known() -> dict | None:
    """What the helper last learned of the houses, from its own copy of Fresh.lua, in the shape of
    the pipe's answer ({"fresh", "houses": {"<realm>|<faction>": {"newest"}}}); None when there
    is no such file or it cannot be read. Entries whose time is no time are left out."""
    try:
        parsed = luatable.parse(kept_file().read_text(encoding="utf-8")).get(GLOBAL)
    except Exception:  # noqa: BLE001 - a file missing, damaged or edited by hand is nothing known, never a failed send
        return None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("houses"), dict):
        return None
    houses = {}
    for realm, by_faction in parsed["houses"].items():
        if not isinstance(realm, str) or not isinstance(by_faction, dict):
            continue
        for faction, h in by_faction.items():
            if isinstance(faction, str) and isinstance(h, dict) and a_time(h.get("newest")):
                houses[f"{realm}|{faction}"] = {"newest": h["newest"]}
    return {"fresh": seconds(parsed.get("fresh")) or DEFAULT_FRESH, "houses": houses}


def learn(realm: str, faction: str, newest, fresh=None) -> dict | None:
    """Note in Fresh.lua that the house of `realm` and `faction` has a scan from `newest`, as the
    pipe's answer to a sent scan says, keeping the other houses the file holds and dropping those
    no longer fresh. `fresh` is the seconds a scan stays fresh when the answer says it (a 409, by
    window); otherwise the file's last value, else DEFAULT_FRESH. The answer is trusted no more
    than any other: a `newest` that is no time (a_time) writes nothing. Returns what the file now
    holds, in the shape of the pipe's answer, or None when nothing was written."""
    now = int(time.time())
    if not isinstance(realm, str) or not realm.strip() or "|" in realm or faction not in scan.FACTIONS + ("",) or not a_time(newest, now):
        return None
    before = known() or {}
    keeps = seconds(fresh) or seconds(before.get("fresh")) or DEFAULT_FRESH
    houses = dict(before.get("houses") or {})
    key = f"{realm}|{faction}"
    houses[key] = {"newest": max(newest, (houses.get(key) or {}).get("newest") or 0)}      # a house's newest only moves on
    told = {"fresh": keeps, "houses": {k: h for k, h in houses.items() if h["newest"] + keeps > now}}
    write(told)
    return told
