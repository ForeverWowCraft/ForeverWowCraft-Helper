"""What the pipe says of each auction house's scans (GET /v1/fresh), written into the addon as
Fresh.lua, so that the addon offers a scan only when one is wanted:

    FWCS_FRESH = { written = <time>, fresh = <seconds a scan stays fresh>,
                   houses = { ["<realm>"] = { ["<faction>"] = { newest = <time> } } } }

While the house's newest scan is under `fresh` old, the FULL / SCAN box is not offered when the
auction house opens. The addon reads the file at the next /reload, like Plans.lua, and the
helper writes it every FRESH_EVERY seconds while `send --watch` runs. The pipe refuses a scan
it does not need either way (409): this is what keeps the box out of the way."""
from __future__ import annotations
import time
from pathlib import Path

from . import scan, settings
from .plans import _whole, lua

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
    return {"written": int(time.time()), "fresh": _whole(told.get("fresh")) or 600, "houses": houses}


def fresh_text(told: dict) -> str:
    """Fresh.lua's text for the pipe's answer `told`: a header, then the FWCS_FRESH table the addon reads."""
    return "\n".join([
        "-- Written by `python fwch.py fresh` (and the helper's send window, by itself) from the pipe; do not edit by hand.",
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
    return max(1, round((_whole(told.get("fresh")) or 600) / 60))


def not_needed(told: dict | None, realm: str, faction: str, scanned_at: int) -> int | None:
    """Whether a scan of this house taken at `scanned_at` is one the pipe would refuse as not
    needed, by what it last said: the newest scan it holds when that is fresh enough, else None.
    The pipe decides for real; this saves sending what it would refuse."""
    if not told:
        return None
    h = (told.get("houses") or {}).get(f"{realm}|{faction}")
    newest = _whole(h.get("newest")) if isinstance(h, dict) else 0
    if newest and scanned_at - newest < (_whole(told.get("fresh")) or 600):
        return newest
    return None
