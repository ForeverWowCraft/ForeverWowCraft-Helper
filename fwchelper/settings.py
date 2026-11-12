"""The helper's settings: where things are and what they are called. Nothing here reads the
network, and the one file read is the settings the icon's menu saved (stored())."""
from __future__ import annotations
import json
import os
import sys
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
    """The setting FWC_<name>, or the FC_<name> of an older install, or what the icon's menu
    saved (stored()), or `default`."""
    value = os.environ.get(ENV_PREFIX + name) or os.environ.get(OLD_ENV_PREFIX + name)
    if not value and name != "STATE":                 # the saved settings live in STATE: it is named by the environment alone
        value = stored().get(ENV_PREFIX + name)
    return value or default


# The settings the icon's menu saves ("Choose the game folder") where there is no registry to
# keep them in, the Mac: settings.json in STATE, {"FWC_WOW_DIR": "..."}. Windows keeps them as
# user environment variables (fwchelper/win.py), which env() sees as any other.
SETTINGS_FILE = "settings.json"
_stored: tuple[float | None, dict] = (None, {})


def stored() -> dict:
    """What settings.json holds, read again when it changed."""
    global _stored
    path = STATE / SETTINGS_FILE
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {}
    if stamp != _stored[0]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        _stored = (stamp, data if isinstance(data, dict) else {})
    return _stored[1]


def store(name: str, value: str) -> Path:
    """Keep FWC_<name> in settings.json, for every helper run from now on, and in this process."""
    data = dict(stored())
    data[ENV_PREFIX + name] = value
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / SETTINGS_FILE
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.environ[ENV_PREFIX + name] = value
    return path


# What the helper keeps of its own: its name and token at the pipe, what it sent, the routes
# and lists it fetched, its log. On Windows that is the user's local application data, on the
# Mac the user's Application Support, on Linux the user's data home (~/.local/share, or
# XDG_DATA_HOME), so that an install under Program Files or Applications or a reinstall touches
# none of it; FWC_STATE names another folder. An install from a zip of before 22 Oct 2026, and a
# Linux install that kept it in state/ beside the helper, has it carried over the first time the
# helper runs (carry_state()).
def _state_dir() -> Path:
    given = env("STATE")
    if given:
        return Path(given)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / NAME / "Helper"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / NAME / "Helper"
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / NAME / "Helper"


STATE = _state_dir()
OLD_STATE = ROOT / "state"
STATE_FILES = ("identity.json", "sent.json", "Plans.lua", "Fresh.lua", "Queue.lua")


def carry_state() -> list[Path]:
    """Bring what an older install kept in state/ beside the helper into STATE, each file
    where STATE has none of that name. Returns what was carried. The old files stay, so that
    the old send.cmd, should it still be run, keeps working. On Linux the state lived beside
    the helper until it moved under the data home, so the first run after that carries it too."""
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
WOW_DIR = "/Applications/World of Warcraft" if sys.platform == "darwin" else r"D:\WorldOfWarcraft\World of Warcraft"
WOW_FLAVOR = "_forever_"        # the Forever client folder (the beta's _classic_beta_ until 31 Oct 2026)

# The pipe: where scans are sent and lists come from. FWC_PIPE_URL names another one. The helper
# registers itself there the first time it sends and keeps the token it is given in STATE;
# FWC_PIPE_TOKEN is for a token that was given by hand instead.
PIPE_URL = "https://pipe.foreverwowcraft.com"
PIPE_TIMEOUT = 60

# The site: where the routes the addon shows in game come from (fwchelper/plans.py). FWC_SITE_URL
# names another one.
SITE_URL = "https://foreverwowcraft.com"
# Both were far more often until 1.7.2 (60 s and 300 s): every helper's looks add up, the pipe's are counted against a daily
# allowance (a few hundred helpers took nearly half of it, 9 Nov 2026), and the site replans a house every half hour at most.
# "Fetch routes now" in the menu still looks at once.
PLANS_EVERY = 600     # seconds between looks at the site for newer routes, while `send --watch` runs: one small fetch of houses.json; the routes follow only when the site has rebuilt
FRESH_EVERY = 1800    # seconds between looks at the pipe for when each auction house was last scanned (fwchelper/fresh.py); the addon reads it at /reload
VENDORS_EVERY = 600   # seconds between looks at the saved file for vendors met (sent when they changed: cli.send_vendors_once)
RETRY_FIRST = 30      # seconds a watch waits before sending again after the pipe refused or failed; doubled each time it fails again ...
RETRY_MAX = 900       # ... up to this (15 min): a pipe that is down is not asked twice a minute by every helper (5 Nov 2026)

# Updates (fwchelper/update.py): where the helper's releases are, asked once a day whether a newer
# one is out (the newest release's address redirects to its tag: no API, no key), and the installer
# of the newest, by its fixed name, for the tray's "Update to ..." row: the .msi on Windows, the
# .dmg on the Mac. FWC_UPDATE_URL names another place to ask (a test).
HELPER_REPO = "https://github.com/ForeverWowCraft/ForeverWowCraft-Helper"
UPDATE_CHECK_URL = HELPER_REPO + "/releases/latest"
UPDATE_KIND = "dmg" if sys.platform == "darwin" else "msi"
UPDATE_FILE = f"{NAME}-Helper.{UPDATE_KIND}"
UPDATE_URL = HELPER_REPO + "/releases/latest/download/" + UPDATE_FILE
UPDATE_EVERY = 86400  # seconds between two looks for a newer helper
# The release's page on GitHub's API, for the SHA-256 GitHub publishes for the installer: a
# newer helper installs by itself only when the download matches it (FWC_UPDATE_API: a test).
UPDATE_API = "https://api.github.com/repos/ForeverWowCraft/ForeverWowCraft-Helper/releases/latest"
UPDATE_QUIET = True   # a newer helper installs by itself; the menu's "Update by itself" keeps FWC_UPDATE_QUIET


def quiet_update() -> bool:
    """Whether a newer helper installs by itself (the menu's "Update by itself", kept in the
    saved settings as FWC_UPDATE_QUIET), or waits in the menu."""
    return env("UPDATE_QUIET", "1" if UPDATE_QUIET else "0") != "0"
