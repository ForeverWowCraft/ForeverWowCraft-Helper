"""The helper as an application: an icon in the notification area (Windows) or the menu bar
(the Mac), and behind it everything setup.cmd and send.cmd did, with no window to read and
nothing to answer.

    python fwch.py app            or the installed "ForeverWowCraft Helper" (python\\ForeverWowCraft Helper.exe fwch.py app;
                                  on the Mac, ForeverWowCraft Helper.app)

At start it finds the game (and asks for the folder, through the icon's menu, when it cannot),
installs the addon, fetches the lists and the routes, and then sends every scan the addon
saves, as `send --watch` does. What it prints goes to the log in the state folder
(settings.STATE). The icon's tooltip says how things stand; a balloon comes only for what
needs the player (tray.balloon), each once a day at most. One instance runs at a time.

fwchelper/tray.py is what the icon says (tested on any OS); fwchelper/win.py is Windows and
fwchelper/mac.py the Mac, the same hands: `win` below is whichever runs."""
from __future__ import annotations
import json
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__, cli, pipe as pipemod, plans as plansmod, scan, settings, tray, update

MUTEX = r"Local\ForeverWowCraftHelper"
ICON = Path(__file__).with_name("helper.ico")
TROUBLE_AGAIN = 86400         # seconds before the same trouble is a balloon again (the tooltip shows it meanwhile)
GAME_AGAIN = 60               # seconds between two looks for the game while it is not found
ADDON_AGAIN = 600             # seconds between two looks at whether the addon is still in the game


class App:
    """The app: the icon on one thread (win.Tray.run), the work on another (work)."""

    def __init__(self, win, log: tray.Log):
        self.win, self.log = win, log
        log.hook = self.line
        self.status = tray.Status()
        self.stop, self.wake, self.folder_chosen = threading.Event(), threading.Event(), threading.Event()
        self.asks: dict = {}                         # what the menu asked for: "send", "plans"
        self.tried: set = set()                      # the versions tried by themselves this run (once each)
        self.told: dict[str, float] = {}             # trouble balloons: when each text was last shown
        self.tray = None

    # ---- what the icon shows ----------------------------------------------------------------
    def line(self, line: str) -> None:
        """Every line printed, as the log sees it: the status follows, and some are balloons."""
        if line.startswith(tray.GOOD_STARTS):
            self.status.problem = None                   # something went right: the status says so, not the last trouble
        if line.startswith("sent "):
            self.status.last_sent = int(time.time())
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
            elif title == tray.UPDATE_OUT:                   # once a version: the tooltip and the menu say it meanwhile
                if text in self.told:
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
        return tray.menu(self.status, self.startup_on(), settings.quiet_update())

    def startup_on(self) -> bool:
        return self.win.startup_on()

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
            self.win.set_startup(on)
            print("starts at login from now on" if on else "no longer starts at login")
        elif ident == tray.HELP:
            self.win.open_path(tray.HELP_URL)
        elif ident == tray.UPDATE:
            self.asks["update"] = True
            self.wake.set()
        elif ident == tray.AUTO:
            on = not settings.quiet_update()
            settings.store("UPDATE_QUIET", "1" if on else "0")
            print("a newer helper installs by itself from now on" if on else "a newer helper waits in the menu from now on")
            if on and self.status.update:
                self.wake.set()
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
                cli.watch(p, None, None, None, stop=self.stop, wake=self.wake, asks=self.asks, tick=self.tick)
        except Exception as e:  # noqa: BLE001 - the icon stays, and says
            print(f"the helper stopped: {e}")
            print(traceback.format_exc())
        finally:
            cli.release_watch()

    def first_run(self) -> pipemod.Pipe:
        """What setup.cmd did, with nothing asked: the game, the addon, the lists, the routes."""
        print(f"{settings.NAME} Helper {__version__} started; the state is in {settings.STATE}")
        self.after_update()
        for carried in settings.carry_state():
            print(f"carried {carried.name} over from the old state folder")
        if cli.retire_startup_entry():
            print("removed the old Startup entry (send.cmd); the app starts with Windows instead")
        said = 0.0
        while not self.stop.is_set():
            base, flavour = scan.wow_dir(), scan.flavor()
            if (base / flavour).is_dir():
                self.status.game = base
                break
            self.status.game = None
            if time.time() - said >= TROUBLE_AGAIN:          # said once an hour; looked for every minute, in case it is installed meanwhile
                said = time.time()
                print(f"Game not found: {base / flavour}. {self.win.CLICK} and choose the game folder.")
            self.folder_chosen.clear()
            if self.folder_chosen.wait(GAME_AGAIN):
                said = 0.0                                   # the folder was chosen: say at once whether it is the one
        print(f"game: {self.status.game}")
        self.install()
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

    def install(self) -> bool:
        """The addon into the game; False, and the trouble said, when it could not be."""
        was = (scan.addons_dir() / scan.ADDON_NAME / f"{scan.ADDON_NAME}.toc").exists()      # there already: a reload is enough
        try:
            cli.install_addon()
            if self.win.game_running():
                print("The game is running: type /reload in the chat, so that it loads the new addon." if was
                      else "The game is running: log out to the character screen and back in (or restart it), so that it finds the new addon.")
            self.looked_addon = time.time()
            return True
        except SystemExit as e:
            print(f"addon not installed: {e}")
            self.looked_addon = time.time()
            return False

    looked_addon = 0.0
    looked_update = 0.0

    def tick(self) -> None:
        """Every round of the watch: now and then, is the addon still in the game? A game
        reinstalled, a folder emptied by hand, or an install that failed the first time (the
        game not there yet) is put right without a restart of the helper. Once a day, is a
        newer helper out? And the update: by itself when the switch is on and it has not
        failed on this version, or when the menu asked for it."""
        if self.asks.pop("update", False):
            self.update_now()
        if time.time() - self.looked_update >= settings.UPDATE_EVERY:
            self.looked_update = time.time()
            self.look_for_update()
        if self.status.update and settings.quiet_update() and self.status.update not in self.tried and self.status.update != self.failed():
            self.tried.add(self.status.update)
            self.update_now(quiet=True)
        if time.time() - self.looked_addon < ADDON_AGAIN:
            return
        self.looked_addon = time.time()
        toc = scan.addons_dir() / scan.ADDON_NAME / f"{scan.ADDON_NAME}.toc"
        if not toc.exists():
            print("the addon is not in the game any more: putting it back")
            self.install()

    def look_for_update(self) -> None:
        """Whether a newer helper is out (fwchelper/update.py): the tooltip and the menu say so,
        and a balloon once, unless it installs by itself (then the balloon is the one after).
        Nothing said when it cannot be told."""
        found = update.check()
        if found and found != self.status.update:
            self.status.update = found
            if settings.quiet_update() and found != self.failed():
                print(f"a newer helper is out: {settings.NAME} Helper {found} (this one is {__version__}); it installs by itself")
            else:
                print(f"update available: {settings.NAME} Helper {found} is out (this one is {__version__}). {self.win.CLICK} and choose Update.")
            self.refresh()

    # ---- the update itself ----------------------------------------------------------------------
    # By itself (since 1.6.0): the installer downloaded, its SHA-256 checked against the one
    # GitHub publishes for the release, then installed with nothing shown (win.quiet_update) and
    # the helper started again; the new one says "updated to" once. A note of what was begun
    # (updates/updated.json) tells the new helper to say so, or the old one, started again by
    # the script because the install failed, to say that and not try that version by itself
    # again (updates/failed.json): the menu's Update stays. Without a published digest, or on a
    # platform without a quiet install (the Mac's disk image), the update waits in the menu.
    def updates_dir(self) -> Path:
        return settings.STATE / "updates"

    def failed(self) -> str | None:
        """The version a quiet install failed on, not to be tried by itself again."""
        try:
            return str(json.loads((self.updates_dir() / "failed.json").read_text(encoding="utf-8")).get("to") or "") or None
        except (OSError, ValueError, AttributeError):
            return None

    def after_update(self) -> None:
        """At the start: what a quiet install begun by the helper before came to."""
        mark = self.updates_dir() / "updated.json"
        if not mark.exists():
            return
        try:
            begun = json.loads(mark.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            begun = {}
        mark.unlink(missing_ok=True)
        to = str(begun.get("to") or "") if isinstance(begun, dict) else ""
        if to and update.version_tuple(to) == update.version_tuple(__version__):
            print(f"updated to {settings.NAME} Helper {__version__} by itself" + (f" (from {begun.get('from')})" if begun.get("from") else ""))
            (self.updates_dir() / "failed.json").unlink(missing_ok=True)
        else:
            (self.updates_dir() / "failed.json").write_text(json.dumps({"to": to, "at": int(time.time())}), encoding="utf-8")
            print(f"update not installed: the helper is still {__version__} after installing {to or 'a newer one'} by itself "
                  f"(the installer's log is {self.updates_dir() / 'install.log'}). {self.win.CLICK} and choose Update.")

    def update_now(self, quiet: bool = False) -> None:
        """The newer helper, downloaded and installed: by itself when `quiet` and the download is
        the one GitHub publishes, else opened, so that its installer closes this one, puts the new
        one in its place and starts it again (installer/helper.wxs)."""
        version = self.status.update
        if not version:
            print("no update to install")
            return
        print(f"downloading {settings.NAME} Helper {version} ...")
        try:
            path = update.download(version)
        except update.UpdateError as e:
            print(f"update not downloaded: {e}")
            return
        expected = update.digest(version)
        if expected and not update.verified(path, expected):
            path.unlink(missing_ok=True)
            print(f"update not installed: the installer downloaded is not the one GitHub publishes for {version} (its SHA-256 differs); "
                  "it was deleted. Try again later from the menu.")
            return
        quietly = getattr(self.win, "quiet_update", None)
        if quiet:
            if not expected or not quietly:
                print(f"update available: {settings.NAME} Helper {version} is out (this one is {__version__}); "
                      + ("GitHub publishes no checksum for it, so it is not installed by itself" if not quietly is None else "it is not installed by itself here")
                      + f". {self.win.CLICK} and choose Update.")
                return
            self.updates_dir().mkdir(parents=True, exist_ok=True)
            (self.updates_dir() / "updated.json").write_text(json.dumps({"from": __version__, "to": version, "at": int(time.time())}), encoding="utf-8")
            print(f"updating to {settings.NAME} Helper {version} by itself: the helper closes now and is back in a moment")
            if quietly(path, self.updates_dir() / "install.log"):
                self.closing()
                if self.tray:
                    self.tray.call(self.tray.quit)
                return
            (self.updates_dir() / "updated.json").unlink(missing_ok=True)
            print("the quiet install could not be started; the installer opens instead")
        print(f"installing {settings.NAME} Helper {version}: {self.win.UPDATE_HOW}")
        self.win.open_path(path)
        self.closing()
        if self.tray:
            self.tray.call(self.tray.quit)


def hands():
    """The platform's module: fwchelper/win.py on Windows, fwchelper/mac.py on the Mac."""
    if sys.platform == "win32":
        from . import win
        return win
    if sys.platform == "darwin":
        from . import mac
        return mac
    raise SystemExit("the app is for Windows and the Mac: elsewhere, `python fwch.py send --watch` does the sending")


def run() -> None:
    win = hands()
    if not win.one_instance(MUTEX):
        win.message(f"{settings.NAME} Helper", f"The helper is running already: its icon is {win.WHERE_ICON}.")
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
