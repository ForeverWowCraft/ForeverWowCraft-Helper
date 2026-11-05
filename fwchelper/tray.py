"""The tray application's mind, with nothing of Windows in it: what the icon's tooltip and
menu say, which line of the log is worth a balloon, whether the helper starts with Windows,
and the log itself. fwchelper/win.py is the hands (ctypes), fwchelper/app.py drives both."""
from __future__ import annotations
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, settings
from .scan import age_text

LOG_KEEP = 1_000_000                        # bytes, before the log rolls over (the one before is kept as .1)
RUN_VALUE = f"{settings.NAME} Helper"       # the Run key's value, and the Start Menu shortcut's name
HELP_URL = settings.SITE_URL + "/helper"
STATUS, SEND, ROUTES, FOLDER, LOG, STARTUP, HELP, QUIT, UPDATE = range(1, 10)      # the menu's items


@dataclass
class Status:
    """What the icon has to say."""
    name: str | None = None                 # the name this helper sends as, once the pipe gave one
    last_sent: int | None = None            # when a scan was last sent
    houses: list = field(default_factory=list)   # the auction houses whose routes are in the addon
    game: Path | None = None                # the game folder, when found
    problem: str | None = None              # the last trouble, until something goes right
    update: str | None = None               # a newer helper's version, when one is out (fwchelper/update.py)
    started: int = field(default_factory=lambda: int(time.time()))


def _said(s: Status) -> str:
    """One line on how things stand."""
    if s.game is None:
        return "Game not found: choose the game folder"
    if s.problem:
        return s.problem
    sent = f"last sent {age_text(s.last_sent)}" if s.last_sent else "nothing sent yet: open the auction house and click Save Prices"
    routes = f"routes for {len(s.houses)} auction house{'s' if len(s.houses) != 1 else ''}" if s.houses else "no routes yet"
    return f"{sent}; {routes}"


def tooltip(s: Status) -> str:
    """The icon's tooltip: at most 127 characters, as Windows shows it."""
    text = f"{settings.NAME} Helper {__version__}" + (f" ({s.update} is out)" if s.update else "") + (f", as {s.name}" if s.name else "") + "\n" + _said(s)
    return text if len(text) <= 127 else text[:124] + "..."


def menu(s: Status, startup: bool) -> list:
    """The menu's rows: (id, label, enabled, checked), or None for a line between groups. The
    actions alone, short, as other apps' menus are: how things stand is the icon's tooltip."""
    return ([(UPDATE, f"Update to {s.update}...", True, False), None] if s.update else []) + \
           [(SEND, "Send prices now", s.game is not None, False),
            (ROUTES, "Fetch routes now", s.game is not None, False),
            (FOLDER, "Choose the game folder...", True, False),
            (LOG, "Open the log", True, False),
            (STARTUP, "Start with Windows", True, startup),
            (HELP, "Help", True, False), None,
            (QUIT, "Quit", True, False)]


# ---- starting with Windows ----------------------------------------------------------------------
def startup_on(run_value: str | None, approved: bytes | None) -> bool:
    """Whether the helper starts when the user logs on: the Run value is there, and Windows'
    own switch (Settings > Apps > Startup, kept as a StartupApproved record whose first byte is
    even when on and odd, 3, when off) has not turned it off. No record means on."""
    return run_value is not None and (not approved or approved[0] % 2 == 0)


def startup_command(exe: Path, script: Path) -> str:
    return f'"{exe}" "{script}" app'


def app_exe() -> Path:
    """What runs the app without a window: the exe the installer made beside the helper
    (python\\ForeverWowCraft Helper.exe), else the pythonw beside this Python, else this Python."""
    built = settings.ROOT / "python" / f"{settings.NAME} Helper.exe"
    if built.exists():
        return built
    windowless = Path(sys.executable).with_name("pythonw.exe")
    return windowless if windowless.exists() else Path(sys.executable)


# ---- what is worth a balloon --------------------------------------------------------------------
TROUBLE = "Trouble"
UPDATE_OUT = "Update available"
TROUBLE_STARTS = ("not sent", "routes not fetched", "lists not fetched", "the pipe could not", "could not register",
                  "addon not installed", "Game not found", "the helper stopped", "update not downloaded")
# lines that say something went right: the status shows them in place of the last trouble
GOOD_STARTS = ("sent ", f"Installed {settings.NAME} Scanner", "routes for the addon's /fwc window: ", "This helper sends as ")


def balloon(line: str) -> tuple[str, str] | None:
    """(title, text) when a line the helper printed is worth a balloon: only what needs the
    player (since 1.5.2; prices sent, routes arrived and ready were balloons before, and the
    tooltip says those). Trouble, and the game to restart so that it loads the addon."""
    if line.startswith("The game is running: restart it"):
        return "Restart the game", "The addon was installed while the game ran: restart it, so that it loads the addon."
    if line.startswith(TROUBLE_STARTS):
        return TROUBLE, line
    if line.startswith("update available: "):
        return UPDATE_OUT, line[len("update available: "):]
    return None


# ---- the log ------------------------------------------------------------------------------------
class Log:
    """A file in which every line starts with the date and time, rolled over at LOG_KEEP bytes
    (the one before is kept as .1). What print() writes while the app runs: it stands in for
    stdout and stderr. `hook(line)` is told every line as it is complete."""

    encoding = "utf-8"

    def __init__(self, path: Path, hook=None):
        self.path, self.hook, self.partial, self.lock = path, hook, "", threading.Lock()

    def write(self, text: str) -> int:
        with self.lock:
            self.partial += text
            while "\n" in self.partial:
                line, self.partial = self.partial.split("\n", 1)
                self._line(line)
        return len(text)

    def _line(self, line: str) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists() and self.path.stat().st_size > LOG_KEEP:
                self.path.replace(self.path.with_name(self.path.name + ".1"))
            with open(self.path, "a", encoding="utf-8") as f:
                f.write((time.strftime("%Y-%m-%d %H:%M:%S") + "  " + line if line.strip() else "") + "\n")
        except OSError:
            pass
        if self.hook and line.strip():
            try:
                self.hook(line)
            except Exception:  # noqa: BLE001 - a balloon that fails is not worth the loop
                pass

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def reconfigure(self, **kw) -> None:        # stamp_lines() asks stdout for line buffering: every line is written at once here
        pass
