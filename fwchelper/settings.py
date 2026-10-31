"""The helper's settings: where things are and what they are called. Nothing here reads files or
the network."""
from __future__ import annotations
import os
from pathlib import Path

NAME = "ForeverWowCraft"

ROOT = Path(__file__).resolve().parent.parent      # the helper's folder
ADDON_SOURCE = ROOT / "addon"                        # the addon as it is installed from

# Settings are environment variables FWC_<name>. The project was called ForeverCraft until
# 29 Sep 2026; what an install from before that has under the old names still counts: settings
# (FC_<name>), the addon, the scans it saved. OLD_* are those names.
ENV_PREFIX, OLD_ENV_PREFIX = "FWC_", "FC_"
OLD_ADDON_NAME = "ForeverCraftScanner"


def env(name: str, default: str | None = None) -> str | None:
    """The setting FWC_<name>, or the FC_<name> of an older install, or `default`."""
    return os.environ.get(ENV_PREFIX + name) or os.environ.get(OLD_ENV_PREFIX + name) or default


# What the helper keeps of its own: its name and token at the pipe, what it sent, the routes
# and lists it fetched, its log. On Windows that is the user's local application data, so that
# an install under Program Files or a reinstall touches none of it; FWC_STATE names another
# folder. An install from a zip of before 22 Oct 2026 kept it in state/ beside the helper:
# carry_state() moves that over the first time the helper runs.
def _state_dir() -> Path:
    given = env("STATE")
    if given:
        return Path(given)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / NAME / "Helper"
    return ROOT / "state"


STATE = _state_dir()
OLD_STATE = ROOT / "state"
STATE_FILES = ("identity.json", "sent.json", "Plans.lua", "Fresh.lua", "Queue.lua")


def carry_state() -> list[Path]:
    """Bring what an older install kept in state/ beside the helper into STATE, each file
    where STATE has none of that name. Returns what was carried. The old files stay, so that
    the old send.cmd, should it still be run, keeps working."""
    carried = []
    if STATE.resolve() == OLD_STATE.resolve() or not OLD_STATE.is_dir():
        return carried
    for name in STATE_FILES:
        old, new = OLD_STATE / name, STATE / name
        if old.is_file() and not new.exists():
            STATE.mkdir(parents=True, exist_ok=True)
            new.write_bytes(old.read_bytes())
            carried.append(new)
    return carried


def saved(name: str) -> str | None:
    """env(name), or on Windows what `setx` saved for the user: a scheduled task and a terminal
    opened earlier do not see that in their environment."""
    value = env(name)
    if value or os.name != "nt":
        return value
    import winreg
    for prefix in (ENV_PREFIX, OLD_ENV_PREFIX):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                value = winreg.QueryValueEx(k, prefix + name)[0]
        except OSError:
            continue
        if value:
            return value
    return None


# The game. When this folder does not exist the helper looks at what Battle.net registered and at
# common install folders (scan.wow_dir); FWC_WOW_DIR / FWC_WOW_FLAVOR override everything.
# `where` shows what was detected.
WOW_DIR = r"D:\WorldOfWarcraft\World of Warcraft"
WOW_FLAVOR = "_classic_beta_"   # the Forever client folder (the launch client may use another name)

# The pipe: where scans are sent and lists come from. FWC_PIPE_URL names another one. The helper
# registers itself there the first time it sends and keeps the token it is given in STATE;
# FWC_PIPE_TOKEN is for a token that was given by hand instead.
PIPE_URL = "https://pipe.foreverwowcraft.com"
PIPE_TIMEOUT = 60

# The site: where the routes the addon shows in game come from (fwchelper/plans.py). FWC_SITE_URL
# names another one.
SITE_URL = "https://foreverwowcraft.com"
PLANS_EVERY = 60      # seconds between looks at the site for newer routes, while `send --watch` runs: one small fetch of houses.json; the routes follow only when the site has rebuilt
FRESH_EVERY = 300     # seconds between looks at the pipe for when each auction house was last scanned (fwchelper/fresh.py); the addon reads it at /reload
