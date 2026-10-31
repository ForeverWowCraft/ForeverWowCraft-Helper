"""What the tray icon says, which lines are balloons, and the log: fwchelper/tray.py, with
nothing of Windows in it."""
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import __version__, settings, tray  # noqa: E402


def test_the_tooltip_says_how_things_stand_in_127_characters():
    s = tray.Status()
    assert tray.tooltip(s) == f"ForeverWowCraft Helper {__version__}\nGame not found: choose the game folder"
    s.game = Path("C:/Games/World of Warcraft")
    assert tray.tooltip(s).endswith("\nnothing sent yet: open the auction house and click Save Prices; no routes yet")
    s.name, s.last_sent, s.houses = "h-abc", int(time.time()) - 120, ["classic-beta-pvp-2--horde"]
    text = tray.tooltip(s)
    assert text.startswith(f"ForeverWowCraft Helper {__version__}, as h-abc\nlast sent 2 min ago; routes for 1 auction house")
    s.houses.append("another")
    assert "routes for 2 auction houses" in tray.tooltip(s)
    s.problem = "not sent: " + "x" * 200
    assert len(tray.tooltip(s)) == 127 and tray.tooltip(s).endswith("...")


def test_the_menu_has_what_the_player_may_want_and_says_whether_it_starts_with_windows():
    s = tray.Status()
    rows = tray.menu(s, startup=True)
    ids = [r[0] for r in rows if r]
    assert ids == [tray.STATUS, tray.SEND, tray.ROUTES, tray.FOLDER, tray.LOG, tray.STARTUP, tray.HELP, tray.QUIT]
    assert rows.count(None) == 3                                       # three groups
    by = {r[0]: r for r in rows if r}
    assert by[tray.STATUS][2] is False and "Game not found" in by[tray.STATUS][1]   # the first row says, and cannot be picked
    assert by[tray.SEND][2] is False and by[tray.ROUTES][2] is False  # nothing to send without the game
    assert by[tray.STARTUP] == (tray.STARTUP, "Start with Windows", True, True)
    s.game = Path("C:/Games")
    by = {r[0]: r for r in tray.menu(s, startup=False) if r}
    assert by[tray.SEND][2] is True and by[tray.STARTUP][3] is False


def test_the_startup_command_runs_the_app_without_a_window():
    assert tray.startup_command(Path(r"C:\x\python\ForeverWowCraft Helper.exe"), Path(r"C:\x\fwch.py")) == \
        r'"C:\x\python\ForeverWowCraft Helper.exe" "C:\x\fwch.py" app'
    exe = tray.app_exe()
    assert exe.suffix == ".exe" or exe == Path(sys.executable)      # pythonw beside this Python, or this Python


def test_which_lines_are_balloons():
    assert tray.balloon("sent Stonespine (Horde): 2324 items, scanned 1 min ago, 34 kB, as h-abc")[0] == "Prices sent"
    title, text = tray.balloon("routes for the addon's /fwc window: Classic Beta PvP 2 (Horde) (32 routes, scanned 5 min ago)")
    assert title == "Routes arrived" and text.startswith("Classic Beta PvP 2 (Horde) (32 routes") and "/reload" in text
    assert tray.balloon(f"Installed {settings.NAME} Scanner to C:/x")[0] == "Addon installed"
    assert tray.balloon("This helper sends as h-abc (public).") == ("Ready", "This helper sends as h-abc (public). Open the auction house in game and click Save Prices.")
    for line in ("not sent: the pipe is down", "routes not fetched: 503", "Game not found: C:/x", "the helper stopped: boom", "addon not installed: no AddOns folder"):
        assert tray.balloon(line) == (tray.TROUBLE, line), line
    for line in ("already sent: Stonespine (Horde), scanned 2 min ago", "In game: /reload", "", "game: C:/x"):
        assert tray.balloon(line) is None, line


def test_the_log_stamps_lines_rolls_over_and_tells_its_hook():
    folder = Path(tempfile.mkdtemp())
    told = []
    log = tray.Log(folder / "helper.log", hook=told.append)
    print("first", file=log)
    log.write("half, ")
    log.write("then the rest\n\nafter a blank\n")
    lines = (folder / "helper.log").read_text(encoding="utf-8").split("\n")
    stamp = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  "
    assert re.fullmatch(stamp + "first", lines[0]) and re.fullmatch(stamp + "half, then the rest", lines[1])
    assert lines[2] == "" and re.fullmatch(stamp + "after a blank", lines[3]) and lines[4] == ""
    assert told == ["first", "half, then the rest", "after a blank"]     # whole lines, no blanks, no stamps
    log.hook = lambda line: 1 / 0                                         # a hook that fails loses nothing
    print("still written", file=log)
    assert "still written" in (folder / "helper.log").read_text(encoding="utf-8")
    kept = tray.LOG_KEEP
    tray.LOG_KEEP = 100
    try:
        for i in range(10):
            print(f"line {i} " + "x" * 40, file=log)
        assert (folder / "helper.log.1").exists() and (folder / "helper.log").stat().st_size < 400
        assert "line 9" in (folder / "helper.log").read_text(encoding="utf-8")
    finally:
        tray.LOG_KEEP = kept
    log.reconfigure(line_buffering=True)                                  # what stamp_lines() asks of stdout
    assert not log.isatty() and log.encoding == "utf-8"


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
