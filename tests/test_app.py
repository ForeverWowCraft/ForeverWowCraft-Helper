"""The app's first run and its menu, with Windows (fwchelper/win.py) stood in for, against the
test pipe of test_register.py and a game folder made for the occasion."""
import contextlib
import json
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

    CLICK, WHERE_ICON, UPDATE_HOW = "Right-click the icon", "by the clock", "the installer starts it again"

    def startup_on(self):
        return tray.startup_on(self.run_value(tray.RUN_VALUE), self.approved(tray.RUN_VALUE))

    def set_startup(self, on):
        cli.autostart(on, registry=self)

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
    (base / "_forever_" / "Interface" / "AddOns").mkdir(parents=True)
    (base / "_forever_" / "WTF" / "Account" / "ACCOUNT" / "SavedVariables").mkdir(parents=True)
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
        addons = game / "_forever_" / "Interface" / "AddOns"
        assert (addons / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.toc").exists()
        assert (addons / "ForeverWowCraftPlans" / "Fresh.lua").exists()             # the freshness was fetched and written
        assert app.status.game == game and app.status.name == "h-1" and p.name == "h-1"
        assert (settings.STATE / "identity.json").exists()                            # registered, and the token kept
        text = _log()
        assert "started; the state is in" in text and "Installed ForeverWowCraft Scanner" in text
        assert "routes not fetched:" in text                                           # the test pipe serves no site
        assert "This helper sends as h-1 (public)." in text
        titles = [t for t, _ in app.tray.balloons]
        assert titles == ["Trouble"], titles                                          # the routes; nothing else needs the player
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
        assert (game / "_forever_" / "Interface" / "AddOns" / "ForeverWowCraftScanner").is_dir()
    finally:
        cli.startup_dir = kept
        back()
        srv.shutdown()


def test_a_game_never_started_gets_its_addons_folder_and_the_addon_comes_back_when_it_goes():
    # the installer runs before the game's first start: there is no Interface\AddOns yet, and
    # before 1.5.2 the install failed, quietly, once, and nothing tried again
    srv, url = _service()
    back = _fresh_pc()
    game = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (game / "_forever_").mkdir(parents=True)
    os.environ["FWC_PIPE_URL"], os.environ["FWC_WOW_DIR"], os.environ["FWC_SITE_URL"] = url, str(game), url
    kept = cli.startup_dir
    cli.startup_dir = lambda: Path(tempfile.mkdtemp())
    try:
        app = _app(FakeWin())
        with contextlib.redirect_stdout(app.log):
            app.first_run()
        addons = game / "_forever_" / "Interface" / "AddOns"
        assert (addons / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.toc").exists()
        assert "Made the AddOns folder" in _log() and "addon not installed" not in _log()
        assert app.status.problem is None or "routes" in app.status.problem                   # the test pipe serves no site
        # the addon goes missing (the game reinstalled, the folder emptied): the next look puts it back
        import shutil
        shutil.rmtree(addons / "ForeverWowCraftScanner")
        app.looked_addon = 0.0
        with contextlib.redirect_stdout(app.log):
            app.tick()
        assert (addons / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.toc").exists()
        assert "putting it back" in _log() and _log().count("Installed ForeverWowCraft Scanner") == 2
        assert [t for t, _ in app.tray.balloons] == ["Trouble"]                        # the routes, once; the install is no balloon
        # and not every round: within ADDON_AGAIN nothing is looked at
        shutil.rmtree(addons / "ForeverWowCraftScanner")
        with contextlib.redirect_stdout(app.log):
            app.tick()
        assert not (addons / "ForeverWowCraftScanner").exists()
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
        assert app.status.last_sent and app.status.problem is None and app.tray.balloons == []      # the tooltip says it
        assert "last sent" in app.tray.tips[-1]
        app.line("not sent: the pipe is down")
        app.line("not sent: the pipe is down")
        assert app.status.problem == "not sent: the pipe is down"
        assert [t for t, _ in app.tray.balloons] == ["Trouble"]                       # the same trouble twice: one balloon
        app.line("not sent: something else")
        assert [t for t, _ in app.tray.balloons] == ["Trouble", "Trouble"]
        app.line("sent Stonespine (Horde): again")
        assert app.status.problem is None                                              # something went right
        assert "last sent" in app.tray.tips[-1]
        app.line("lists not fetched: 503")
        assert app.status.problem == "lists not fetched: 503" and app.tray.balloons[-1][0] == "Trouble"
        app.line("routes for the addon's /fwc window: Stonespine (Horde) (3 routes)")
        assert app.status.problem is None                                              # any good news clears it
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
        assert app.startup_on() and win.run[tray.RUN_VALUE].endswith('" app') and "starts at login" in _log()
        with contextlib.redirect_stdout(app.log):
            app.chosen(tray.STARTUP)
        assert not app.startup_on() and tray.RUN_VALUE not in win.run
        app.chosen(tray.SEND)
        app.chosen(tray.ROUTES)
        app.chosen(tray.CHECK)
        assert app.asks == {"send": True, "plans": True, "check": True} and app.wake.is_set()
        # the check asked for: GitHub asked at once; the newest already, a newer one installed quietly, or not reachable
        from fwchelper import update
        kept_latest, kept_update_now = update.latest, app.update_now
        installed = []
        app.update_now = lambda quiet=False: installed.append(quiet)
        try:
            update.latest = lambda *a, **k: appmod.__version__
            with contextlib.redirect_stdout(app.log):
                app.check_now()
            assert f"update check: this is the newest, ForeverWowCraft Helper {appmod.__version__}" in _log() and installed == []
            update.latest = lambda *a, **k: "99.0.0"
            with contextlib.redirect_stdout(app.log):
                app.check_now()
            assert installed == [True] and app.status.update == "99.0.0" and "99.0.0 is out" in _log()
            update.latest = lambda *a, **k: None
            with contextlib.redirect_stdout(app.log):
                app.check_now()
            assert "update check: GitHub could not be reached" in _log() and installed == [True]
        finally:
            update.latest, app.update_now = kept_latest, kept_update_now
        app.asks.pop("check")
        app.status.update = None                    # the pretend 99.0.0 is not at the top of the menu below
        app.chosen(tray.LOG)
        app.chosen(tray.HELP)
        assert win.opened == [str(app.log.path), tray.HELP_URL]
        app.chosen(tray.QUIT)
        assert app.stop.is_set() and app.tray.quit_asked
        rows = app.items()
        assert rows[0][0] == tray.SEND and rows[0][2] is False and {r[0] for r in rows if r} >= {tray.SEND, tray.QUIT}
        assert "Game not found" in app.tray.tips[-1] if app.tray.tips else True
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


def test_a_watch_waits_longer_each_time_the_pipe_fails_and_starts_over_when_asked():
    # 5 Nov 2026: the pipe's day of database reads ran out and every helper with a scan asked
    # again every 36 seconds until midnight. A watch waits 30 s after the first failure, then
    # twice as long each time, up to 15 min; a send asked for by hand, or one that goes through, starts over
    assert [cli.retry_wait(n) for n in (1, 2, 3, 4, 5, 6, 7, 20)] == [30, 60, 120, 240, 480, 900, 900, 900]
    assert cli.wait_text(30) == "30 s" and cli.wait_text(120) == "2 min" and cli.wait_text(900) == "15 min"
    from fwchelper import pipe as pipemod
    back = _fresh_pc()
    # a pipe and a site nobody listens on: the watch's freshness and routes fetches must fail here, not
    # register this test's helper with the real pipe (which every run of the suite did, 6 Nov 2026)
    os.environ["FWC_PIPE_URL"], os.environ["FWC_SITE_URL"] = "http://127.0.0.1:9", "http://127.0.0.1:9"
    kept = cli.send_once, cli._pause
    waits, calls = [], []
    stop, wake, asks = threading.Event(), threading.Event(), {}

    def failing(p, path, realm, faction, again=False, fresh=None):
        calls.append(again)
        if len(calls) == 5:
            stop.set()                               # the fifth goes through, and the watch is told to stop
            return True
        raise pipemod.PipeError("POST /v1/scans: 500 the service failed")

    def pause(seconds, stop_=None, wake_=None):
        if seconds > 2:
            waits.append(seconds)
        if len(calls) == 3 and "send" not in asks:
            asks["send"] = True                      # asked for by hand after three failures
    cli.send_once, cli._pause = failing, pause
    try:
        scan_file = settings.STATE / "ForeverWowCraftScanner.lua"
        settings.STATE.mkdir(parents=True, exist_ok=True)
        scan_file.write_text("FWCS_DB = {}", encoding="utf-8")
        out = tray.Log(settings.STATE / "watch.log")
        kept_out = sys.stdout
        sys.stdout = out
        try:
            cli.watch(pipemod.Pipe(), scan_file, None, None, interval=0.01, stop=stop, wake=wake, asks=asks)
        finally:
            sys.stdout = kept_out
        # three failures: 30 s, 1 min, 2 min; asked by hand, 30 s again; the fifth went through
        assert waits == [30, 60, 120, 30] and calls[3] is True and len(calls) == 5
        text = (settings.STATE / "watch.log").read_text(encoding="utf-8")
        assert "not sent: POST /v1/scans: 500 the service failed" in text and "trying again in 2 min" in text
    finally:
        cli.send_once, cli._pause = kept
        back()


def test_the_app_says_once_when_a_newer_helper_is_out_and_installs_it_when_asked():
    from fwchelper import update
    back = _fresh_pc()
    kept = update.latest, update.download, update.digest
    got = []

    def download(version, url=None, into=None, timeout=None):
        path = Path(tempfile.mkdtemp()) / f"ForeverWowCraft-Helper-{version}.msi"
        path.write_bytes(update.MSI_MAGIC)
        got.append(version)
        return path
    update.latest, update.download, update.digest = (lambda url=None, timeout=None: "9.9.9"), download, (lambda *a, **k: None)
    os.environ["FWC_UPDATE_QUIET"] = "0"                                                  # the switch off: the update waits in the menu
    try:
        app = _app(FakeWin())
        app.status.game = Path("C:/x")
        app.looked_addon = time.time()                                                  # not the addon's turn
        with contextlib.redirect_stdout(app.log):
            app.tick()
        assert app.status.update == "9.9.9" and [t for t, _ in app.tray.balloons] == ["Update available"]
        assert "(9.9.9 is out)" in app.tray.tips[-1] and app.items()[0][1] == "Update to 9.9.9..."
        assert "update available: ForeverWowCraft Helper 9.9.9 is out" in _log()
        with contextlib.redirect_stdout(app.log):
            app.tick()                                                                  # not a day later: nothing more said
        assert len(app.tray.balloons) == 1 and got == []
        app.chosen(tray.UPDATE)
        assert app.asks == {"update": True} and app.wake.is_set()
        with contextlib.redirect_stdout(app.log):
            app.tick()
        assert got == ["9.9.9"] and app.win.opened[-1].endswith("ForeverWowCraft-Helper-9.9.9.msi")
        assert app.stop.is_set() and app.tray.quit_asked and "installing ForeverWowCraft Helper 9.9.9" in _log()
        # the download failing is trouble, said as the rest is, and the helper goes on
        update.download = lambda *a, **k: (_ for _ in ()).throw(update.UpdateError("no connection"))
        app2 = _app(FakeWin())
        app2.status.update = "9.9.9"
        app2.asks["update"] = True
        app2.looked_addon = app2.looked_update = time.time()
        with contextlib.redirect_stdout(app2.log):
            app2.tick()
        assert app2.status.problem == "update not downloaded: no connection" and not app2.stop.is_set()
    finally:
        update.latest, update.download, update.digest = kept
        del os.environ["FWC_UPDATE_QUIET"]
        back()


def test_a_newer_helper_installs_by_itself_when_the_download_is_the_one_github_publishes():
    from fwchelper import update
    back = _fresh_pc()
    kept = update.latest, update.download, update.digest
    files = []

    def download(version, url=None, into=None, timeout=None):
        path = Path(tempfile.mkdtemp()) / f"ForeverWowCraft-Helper-{version}.msi"
        path.write_bytes(update.MSI_MAGIC + b"new")
        files.append(path)
        return path
    good = __import__("hashlib").sha256(update.MSI_MAGIC + b"new").hexdigest()
    __version__ = appmod.__version__
    update.latest, update.download, update.digest = (lambda url=None, timeout=None: "9.9.9"), download, (lambda *a, **k: good)

    class QuietWin(FakeWin):
        def __init__(self):
            super().__init__()
            self.quiet = []

        def quiet_update(self, installer, log):
            self.quiet.append((str(installer), str(log)))
            return True
    try:
        # the switch is on by default: the newer helper is downloaded, checked, installed with nothing shown; one line, no balloon
        app = _app(QuietWin())
        app.status.game = Path("C:/x")
        app.looked_addon = time.time()
        with contextlib.redirect_stdout(app.log):
            app.tick()
        assert app.win.quiet and app.win.quiet[0][0] == str(files[0]) and app.win.quiet[0][1].endswith("install.log")
        assert app.stop.is_set() and app.tray.quit_asked and app.tray.balloons == [] and app.win.opened == []
        assert "it installs by itself" in _log() and "updating to ForeverWowCraft Helper 9.9.9 by itself" in _log()
        mark = json.loads((settings.STATE / "updates" / "updated.json").read_text(encoding="utf-8"))
        assert mark["to"] == "9.9.9" and mark["from"] == __version__
        # the new helper starts: it says so once, as a balloon
        app2 = _app(QuietWin())
        kept_version = appmod.__version__
        appmod.__version__ = "9.9.9"
        try:
            with contextlib.redirect_stdout(app2.log):
                app2.after_update()
        finally:
            appmod.__version__ = kept_version
        assert app2.tray.balloons == [("Updated", "Updated to ForeverWowCraft Helper 9.9.9 by itself (from " + __version__ + ")")]
        assert not (settings.STATE / "updates" / "updated.json").exists()
        # the install failed (the old helper is back): trouble, and that version is not tried by itself again
        (settings.STATE / "updates" / "updated.json").write_text(json.dumps({"from": __version__, "to": "9.9.9"}), encoding="utf-8")
        app3 = _app(QuietWin())
        app3.status.game = Path("C:/x")
        app3.looked_addon = time.time()
        with contextlib.redirect_stdout(app3.log):
            app3.after_update()
            app3.tick()
        assert app3.status.problem.startswith("update not installed: the helper is still") and app3.failed() == "9.9.9"
        assert app3.win.quiet == [] and not app3.stop.is_set() and app3.items()[0][1] == "Update to 9.9.9..."       # the menu's Update stays
        assert [t for t, _ in app3.tray.balloons] == ["Trouble", "Update available"]
        # a download that is not what GitHub publishes is deleted, not installed
        update.digest = lambda *a, **k: "0" * 64
        app4 = _app(QuietWin())
        app4.status.game = Path("C:/x")
        app4.status.update = "9.9.9"
        app4.asks["update"] = True
        app4.looked_addon = app4.looked_update = time.time()
        with contextlib.redirect_stdout(app4.log):
            app4.tick()
        assert app4.status.problem.startswith("update not installed: the installer downloaded is not the one GitHub publishes")
        assert not files[-1].exists() and app4.win.quiet == [] and app4.win.opened == [] and not app4.stop.is_set()
        # the menu's switch: off, the update waits in the menu (a platform without a quiet install waits too)
        app5 = _app(QuietWin())
        app5.status.game = Path("C:/x")
        app5.chosen(tray.AUTO)
        assert settings.quiet_update() is False and app5.items()[-5] == (tray.AUTO, "Update by itself", True, False)
        update.digest = lambda *a, **k: good
        app5.looked_addon = time.time()
        with contextlib.redirect_stdout(app5.log):
            app5.tick()
        assert app5.win.quiet == [] and not app5.stop.is_set() and [t for t, _ in app5.tray.balloons] == ["Update available"]
        app5.chosen(tray.AUTO)
        assert settings.quiet_update() is True and app5.wake.is_set()
    finally:
        update.latest, update.download, update.digest = kept
        os.environ.pop("FWC_UPDATE_QUIET", None)
        back()


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
