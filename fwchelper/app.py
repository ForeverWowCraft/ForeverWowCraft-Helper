"""The helper as a Windows application: an icon in the notification area, and behind it
everything setup.cmd and send.cmd did, with no window to read and nothing to answer.

    python fwch.py app            or the installed "ForeverWowCraft Helper" (python\\ForeverWowCraft Helper.exe fwch.py app)

At start it finds the game (and asks for the folder, through the icon's menu, when it cannot),
installs the addon, fetches the lists and the routes, and then sends every scan the addon
saves, as `send --watch` does. What it prints goes to the log in the state folder
(settings.STATE), and the lines that matter to the player come up as balloons: ready, prices
sent, routes arrived, trouble. The icon's menu has the rest. One instance runs at a time.

fwchelper/tray.py is what the icon says (tested on any OS); fwchelper/win.py is Windows."""
from __future__ import annotations
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__, cli, pipe as pipemod, plans as plansmod, scan, settings, tray

MUTEX = r"Local\ForeverWowCraftHelper"
ICON = Path(__file__).with_name("helper.ico")
TROUBLE_AGAIN = 3600          # seconds before the same trouble is a balloon again


class App:
    """The app: the icon on one thread (win.Tray.run), the work on another (work)."""

    def __init__(self, win, log: tray.Log):
        self.win, self.log = win, log
        log.hook = self.line
        self.status = tray.Status()
        self.stop, self.wake, self.folder_chosen = threading.Event(), threading.Event(), threading.Event()
        self.asks: dict = {}                         # what the menu asked for: "send", "plans"
        self.told: dict[str, float] = {}             # trouble balloons: when each text was last shown
        self.tray = None

    # ---- what the icon shows ----------------------------------------------------------------
    def line(self, line: str) -> None:
        """Every line printed, as the log sees it: the status follows, and some are balloons."""
        if line.startswith("sent "):
            self.status.last_sent, self.status.problem = int(time.time()), None
        elif line.startswith("This helper sends as "):
            self.status.name = line.split("as ", 1)[1].split(" ", 1)[0]
        said = tray.balloon(line)
        if said:
            title, text = said
            if title == tray.TROUBLE:
                self.status.problem = text
                if self.told.get(text, 0) > time.time() - TROUBLE_AGAIN:
                    said = None
                self.told[text] = time.time()
            if said and self.tray:
                self.tray.call(lambda: self.tray.balloon(title, text))
        self.refresh()

    def refresh(self) -> None:
        self.status.houses = sorted(plansmod.stamps())
        if self.tray:
            text = tray.tooltip(self.status)
            self.tray.call(lambda: self.tray.tooltip(text))

    def items(self) -> list:
        return tray.menu(self.status, self.startup_on())

    def startup_on(self) -> bool:
        return tray.startup_on(self.win.run_value(tray.RUN_VALUE), self.win.approved(tray.RUN_VALUE))

    def chosen(self, ident: int) -> None:
        """A menu row was picked (on the icon's thread)."""
        if ident == tray.SEND:
            self.asks["send"] = True
            self.wake.set()
        elif ident == tray.ROUTES:
            self.asks["plans"] = True
            self.wake.set()
        elif ident == tray.FOLDER:
            folder = self.win.browse_folder("The World of Warcraft folder: the one that holds the client folder (_forever_)")
            if folder:
                self.win.set_user_setting("FWC_WOW_DIR", str(folder))
                print(f"game folder set to {folder}")
                self.folder_chosen.set()
                self.wake.set()
        elif ident == tray.LOG:
            self.win.open_path(self.log.path)
        elif ident == tray.STARTUP:
            on = not self.startup_on()
            cli.autostart(on, registry=self.win)
            print("starts with Windows from now on" if on else "no longer starts with Windows")
        elif ident == tray.HELP:
            self.win.open_path(tray.HELP_URL)
        elif ident == tray.QUIT:
            self.closing()
            self.tray.quit()

    def closing(self) -> None:
        self.stop.set()
        self.wake.set()
        self.folder_chosen.set()

    # ---- the work -----------------------------------------------------------------------------
    def work(self) -> None:
        try:
            p = self.first_run()
            if not self.stop.is_set():
                cli.watch(p, None, None, None, stop=self.stop, wake=self.wake, asks=self.asks)
        except Exception as e:  # noqa: BLE001 - the icon stays, and says
            print(f"the helper stopped: {e}")
            print(traceback.format_exc())
        finally:
            cli.release_watch()

    def first_run(self) -> pipemod.Pipe:
        """What setup.cmd did, with nothing asked: the game, the addon, the lists, the routes."""
        print(f"{settings.NAME} Helper {__version__} started; the state is in {settings.STATE}")
        for carried in settings.carry_state():
            print(f"carried {carried.name} over from the old state folder")
        if cli.retire_startup_entry():
            print("removed the old Startup entry (send.cmd); the app starts with Windows instead")
        while not self.stop.is_set():
            base, flavour = scan.wow_dir(), scan.flavor()
            if (base / flavour).is_dir():
                self.status.game = base
                break
            self.status.game = None
            print(f"Game not found: {base / flavour}. Right-click the icon and choose the game folder.")
            self.folder_chosen.clear()
            self.folder_chosen.wait(3600)
        print(f"game: {self.status.game}")
        try:
            cli.install_addon()
            if self.win.game_running():
                print("The game is running: restart it, so that it loads the addon.")
        except SystemExit as e:
            print(f"addon not installed: {e}")
        p = pipemod.Pipe()                               # the one pipe for the run: it registers once, at its first word
        for what, step in (("lists", lambda: cli.lists(p)), ("routes", lambda: cli.plans(quiet=True)), ("freshness", lambda: cli.freshen(p, quiet=True))):
            if self.stop.is_set():
                break
            try:
                step()
            except (SystemExit, pipemod.PipeError, plansmod.PlansError) as e:
                print(f"{what} not fetched: {e}")
        try:
            me = p.me()
            print(f"This helper sends as {me['name']} ({me['trust']}).")
        except pipemod.PipeError as e:
            print(f"the pipe could not be reached: {e}")
        self.refresh()
        return p


def run() -> None:
    if sys.platform != "win32":
        raise SystemExit("the app is for Windows: elsewhere, `python fwch.py send --watch` does the sending")
    from . import win
    if not win.one_instance(MUTEX):
        win.message(f"{settings.NAME} Helper", "The helper is running already: its icon is in the notification area, by the clock.")
        return
    log = tray.Log(settings.STATE / "helper.log")
    sys.stdout = sys.stderr = log
    app = App(win, log)
    other = cli.other_watcher()
    if other:
        win.message(f"{settings.NAME} Helper", f"A helper window (send.cmd, process {other}) is sending already. Close it, then start the app again.")
        return
    app.tray = win.Tray(f"{settings.NAME} Helper", ICON, app.items, app.chosen, app.closing)
    worker = threading.Thread(target=app.work, name="helper", daemon=True)
    worker.start()
    try:
        app.tray.run()
    finally:
        app.closing()
        worker.join(10)
        cli.release_watch()
        print("stopped")
