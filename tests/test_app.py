"""The app's first run and its menu, with Windows (fwchelper/win.py) stood in for, against the
test pipe of test_register.py and a game folder made for the occasion."""
import contextlib
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import app as appmod, cli, settings, tray  # noqa: E402
from test_register import _fresh_pc, _service  # noqa: E402


class FakeTray:
    def __init__(self):
        self.balloons, self.tips, self.quit_asked = [], [], False

    def call(self, fn):
        fn()

    def balloon(self, title, text):
        self.balloons.append((title, text))

    def tooltip(self, text):
        self.tips.append(text)

    def quit(self):
        self.quit_asked = True


class FakeWin:
    """fwchelper/win.py as the app sees it, with a registry of its own."""

    def __init__(self, folder=None):
        self.run, self.records, self.opened, self.settings, self.folder, self.game_runs = {}, {}, [], {}, folder, False

    def run_value(self, name):
        return self.run.get(name)

    def set_run_value(self, name, command):
        if command is None:
            self.run.pop(name, None)
        else:
            self.run[name] = command

    def approved(self, name):
        return self.records.get(name)

    def approve(self, name):
        self.records[name] = bytes([2]) + bytes(11)

    def browse_folder(self, title):
        return self.folder

    def set_user_setting(self, name, value):
        self.settings[name] = value
        os.environ[name] = value

    def open_path(self, what):
        self.opened.append(str(what))

    def game_running(self):
        return self.game_runs


def _game():
    """A World of Warcraft folder with the client folder, its AddOns and WTF."""
    base = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (base / "_classic_beta_" / "Interface" / "AddOns").mkdir(parents=True)
    (base / "_classic_beta_" / "WTF" / "Account" / "ACCOUNT" / "SavedVariables").mkdir(parents=True)
    return base


def _app(win):
    settings.OLD_STATE = Path(tempfile.mkdtemp()) / "state"        # no older install's state to carry over (this checkout's stays out)
    log = tray.Log(settings.STATE / "helper.log")
    app = appmod.App(win, log)
    app.tray = FakeTray()
    return app


def _log():
    path = settings.STATE / "helper.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_the_first_run_finds_the_game_installs_the_addon_and_registers():
    srv, url = _service()
    back = _fresh_pc()
    game = _game()
    os.environ["FWC_PIPE_URL"], os.environ["FWC_WOW_DIR"], os.environ["FWC_SITE_URL"] = url, str(game), url
    kept = cli.startup_dir
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        app = _app(FakeWin())
        with contextlib.redirect_stdout(app.log):                                      # as run() has it: print() goes to the log
            p = app.first_run()
        addons = game / "_classic_beta_" / "Interface" / "AddOns"
        assert (addons / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.toc").exists()
        assert (addons / "ForeverWowCraftPlans" / "Fresh.lua").exists()             # the freshness was fetched and written
        assert app.status.game == game and app.status.name == "h-1" and p.name == "h-1"
        assert (settings.STATE / "identity.json").exists()                            # registered, and the token kept
        text = _log()
        assert "started; the state is in" in text and "Installed ForeverWowCraft Scanner" in text
        assert "routes not fetched:" in text                                           # the test pipe serves no site
        assert "This helper sends as h-1 (public)." in text
        titles = [t for t, _ in app.tray.balloons]
        assert titles == ["Addon installed", "Trouble", "Ready"], titles              # the trouble is the routes
        assert app.tray.tips[-1].startswith("ForeverWowCraft Helper") and "as h-1" in app.tray.tips[-1]
    finally:
        cli.startup_dir = kept
        back()
        srv.shutdown()


def test_without_the_game_the_app_waits_for_the_folder_from_the_menu():
    srv, url = _service()
    back = _fresh_pc()
    game = _game()
    os.environ["FWC_PIPE_URL"], os.environ["FWC_SITE_URL"] = url, url
    os.environ["FWC_WOW_DIR"] = str(game.parent / "nowhere")
    kept = cli.startup_dir
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        win = FakeWin(folder=game)
        app = _app(win)
        done = []
        with contextlib.redirect_stdout(app.log):
            worker = threading.Thread(target=lambda: done.append(app.first_run()), daemon=True)
            worker.start()
            for _ in range(100):
                if "Game not found" in _log():
                    break
                time.sleep(0.05)
            assert "Game not found" in _log() and app.status.game is None and not done
            assert app.tray.balloons[-1][0] == tray.TROUBLE and "choose the game folder" in app.tray.tips[-1]
            app.chosen(tray.FOLDER)                                                   # the user picks the folder
            worker.join(30)
        assert done and app.status.game == game and win.settings == {"FWC_WOW_DIR": str(game)}
        assert (game / "_classic_beta_" / "Interface" / "AddOns" / "ForeverWowCraftScanner").is_dir()
    finally:
        cli.startup_dir = kept
        back()
        srv.shutdown()


def test_lines_move_the_status_and_trouble_is_a_balloon_once():
    back = _fresh_pc()
    try:
        app = _app(FakeWin())
        app.status.game = Path("C:/x")
        app.line("sent Stonespine (Horde): 2324 items, scanned 1 min ago, 34 kB, as h-1")
        assert app.status.last_sent and app.status.problem is None and app.tray.balloons[-1][0] == "Prices sent"
        app.line("not sent: the pipe is down")
        app.line("not sent: the pipe is down")
        assert app.status.problem == "not sent: the pipe is down"
        assert [t for t, _ in app.tray.balloons] == ["Prices sent", "Trouble"]       # the same trouble twice: one balloon
        app.line("not sent: something else")
        assert [t for t, _ in app.tray.balloons] == ["Prices sent", "Trouble", "Trouble"]
        app.line("sent Stonespine (Horde): again")
        assert app.status.problem is None                                              # something went right
        assert "last sent" in app.tray.tips[-1]
    finally:
        back()


def test_the_menu_does_what_it_says():
    back = _fresh_pc()
    kept = cli.startup_dir
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        win = FakeWin()
        app = _app(win)
        assert not app.startup_on()
        with contextlib.redirect_stdout(app.log):
            app.chosen(tray.STARTUP)
        assert app.startup_on() and win.run[tray.RUN_VALUE].endswith('" app') and "starts with Windows" in _log()
        with contextlib.redirect_stdout(app.log):
            app.chosen(tray.STARTUP)
        assert not app.startup_on() and tray.RUN_VALUE not in win.run
        app.chosen(tray.SEND)
        app.chosen(tray.ROUTES)
        assert app.asks == {"send": True, "plans": True} and app.wake.is_set()
        app.chosen(tray.LOG)
        app.chosen(tray.HELP)
        assert win.opened == [str(app.log.path), tray.HELP_URL]
        app.chosen(tray.QUIT)
        assert app.stop.is_set() and app.tray.quit_asked
        rows = app.items()
        assert rows[0][1].startswith("Game not found") and {r[0] for r in rows if r} >= {tray.SEND, tray.QUIT}
    finally:
        cli.startup_dir = kept
        back()


def test_the_watch_stops_when_told_and_does_what_the_menu_asked():
    srv, url = _service()
    back = _fresh_pc()
    game = _game()
    os.environ["FWC_PIPE_URL"], os.environ["FWC_WOW_DIR"], os.environ["FWC_SITE_URL"] = url, str(game), url
    try:
        from fwchelper import pipe as pipemod
        p = pipemod.Pipe()
        stop, wake, asks = threading.Event(), threading.Event(), {"send": True}
        out = tray.Log(settings.STATE / "watch.log")
        kept_out = sys.stdout
        sys.stdout = out
        try:
            t = threading.Thread(target=lambda: cli.watch(p, None, None, None, interval=0.1, stop=stop, wake=wake, asks=asks), daemon=True)
            t.start()
            time.sleep(1)
            stop.set()
            wake.set()
            t.join(10)
        finally:
            sys.stdout = kept_out
        assert not t.is_alive()
        text = (settings.STATE / "watch.log").read_text(encoding="utf-8")
        assert "nothing to send: no scan file yet" in text and asks == {}
    finally:
        back()
        srv.shutdown()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
