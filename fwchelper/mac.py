"""The Mac, through PyObjC (AppKit): the icon in the menu bar with its menu and notifications,
the lock that keeps the app to one instance, the launch agent that starts it at login, a folder
dialog, opening a file or an address, a user setting. Nothing here decides anything:
fwchelper/tray.py does, and fwchelper/app.py drives, asking the same of this as of
fwchelper/win.py. Imported on the Mac only; AppKit is imported where it is used, so that the
plain parts (the launch agent, the settings file, the lock) are tested anywhere."""
from __future__ import annotations
import os
import plistlib
import queue
import subprocess
import sys
from pathlib import Path

from . import settings

try:
    import fcntl
except ImportError:                                  # Windows, where this module is only read by the tests
    fcntl = None

# how the app's messages speak of the icon on this platform
CLICK = "Click the icon in the menu bar"
WHERE_ICON = "in the menu bar, at the top right"
UPDATE_HOW = "the disk image opens: drag the new helper over the one in Applications, then start it again"

ICON = Path(__file__).with_name("helper-menubar.png")
ICON_POINTS = 18                                     # the menu bar's icons are 18 points tall; the image is 64 px and scaled
POKE = "com.foreverwowcraft.helper.show"             # the word a second start sends the running helper: show your menu (poke())
PLACED_AFTER = 5.0                                   # seconds after the start before the icon's window is looked at (placed())
REOPEN_AFTER = 0.3                                   # seconds between a reopen and the menu: the activation that comes with it closed a menu shown at once
NOT_PLACED = ("Its icon cannot be shown in this Mac's menu bar. "
              "Open the helper again from Applications: its menu appears at the mouse.")
LABEL = "com.foreverwowcraft.helper"                 # the launch agent's, and the application bundle's identifier
_held: list = []                                     # the lock's file, open as long as the app runs


# ---- one instance ---------------------------------------------------------------------------
def one_instance(name: str) -> bool:
    """Take the lock named by `name` (a file in the state folder); False when another process
    of this user holds it already."""
    if fcntl is None:
        return True
    path = settings.STATE / (name.rsplit("\\", 1)[-1] + ".lock")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        f = open(path, "a+")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    _held.append(f)
    return True


# ---- starting at login ----------------------------------------------------------------------
def agents_dir() -> Path:
    """The user's launch agents folder, ~/Library/LaunchAgents."""
    return Path.home() / "Library" / "LaunchAgents"


def agent_path() -> Path:
    """The helper's launch agent there, the one that starts it at login."""
    return agents_dir() / f"{LABEL}.plist"


def poke() -> bool:
    """Tell the helper already running to show its menu at the mouse: what a second start does,
    for a Mac whose menu bar hides the icon (behind the notch, or crowded out). True when the
    word was sent."""
    try:
        from Foundation import NSDistributedNotificationCenter
        NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(POKE, None, None, True)
        return True
    except Exception:  # noqa: BLE001 - no AppKit here (a checkout on another system), or the centre refused
        return False


def shown(path) -> str:
    """A path as the log writes it, the home folder as ~: a log pasted for help names no user."""
    p, home = str(path), str(Path.home())
    return "~" + p[len(home):] if p == home or p.startswith(home + "/") else p


def identity() -> dict:
    """What macOS knows this process as: the main bundle (the .app since 1.7.3, when its own
    executable runs Python; a bare Python's bin folder, with no identifier, before) and the
    running application's identifier."""
    from AppKit import NSRunningApplication
    from Foundation import NSBundle
    bundle = NSBundle.mainBundle()
    return {"path": shown(bundle.bundlePath()), "id": bundle.bundleIdentifier(),
            "running": NSRunningApplication.currentApplication().bundleIdentifier()}


def identity_check() -> int:
    """`fwch.py app --identity` (the bundle's executable with --identity): the identity printed,
    nothing started; 0 when the main bundle is the helper's. The build's test of the bundle."""
    who = identity()
    print(f"main bundle {who['path']}: identifier {who['id']}, running application {who['running']}")
    return 0 if who["id"] == LABEL else 1


def start_lines() -> list[str]:
    """What the log says of this Mac and this process at start: enough to settle a report of a
    missing icon in one round."""
    import platform
    from Foundation import NSProcessInfo
    who = identity()
    return [f"macOS: {NSProcessInfo.processInfo().operatingSystemVersionString()}, processor {platform.machine()}",
            f"executable: {shown(sys.executable)}",
            f"main bundle: {who['path']}, identifier {who['id']}; running application {who['running']}"]


def app_bundle(executable: str | None = None) -> Path | None:
    """The application bundle this Python runs from, or None when it runs from a checkout."""
    p = Path(executable or sys.executable).resolve()
    for parent in p.parents:
        if parent.suffix == ".app" and (parent / "Contents" / "MacOS").is_dir():
            return parent
    return None


def app_command(executable: str | None = None, script: Path | None = None) -> list[str]:
    """What starts the app: the bundle's own executable when installed, else this Python and
    fwch.py."""
    bundle = app_bundle(executable)
    if bundle:
        return [str(bundle / "Contents" / "MacOS" / bundle.stem)]
    return [executable or sys.executable, str(script or settings.ROOT / "fwch.py"), "app"]


def launch_agent(command: list[str]) -> dict:
    """The launch agent, as launchd reads it: run at login, and left alone after (the app keeps
    itself alive; one that quit stays quit until the next login)."""
    return {"Label": LABEL, "ProgramArguments": command, "RunAtLoad": True, "KeepAlive": False, "ProcessType": "Interactive"}


def startup_on() -> bool:
    """Whether the app starts at login: its launch agent is there. (System Settings > General >
    Login Items lists it under "Allow in the Background", with a switch of its own: that switch
    off keeps the agent from running, which this cannot see.)"""
    return agent_path().exists()


def set_startup(on: bool) -> str:
    """Have the app start at login, or not: the launch agent written and loaded, or unloaded
    and removed. Returns the agent's path, or "" when taken out."""
    path = agent_path()
    uid = os.getuid() if hasattr(os, "getuid") else 0
    if not on:
        subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
        path.unlink(missing_ok=True)
        return ""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(launch_agent(app_command()), f)
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)        # an older one, so that the new is read
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)], capture_output=True)
    return str(path)


# ---- the user's setting, the game, files -------------------------------------------------------
def set_user_setting(name: str, value: str) -> None:
    """Keep a setting for the user (settings.json in the state folder), and in this process."""
    settings.store(name[len(settings.ENV_PREFIX):] if name.startswith(settings.ENV_PREFIX) else name, value)


def open_path(what: str | Path) -> None:
    """Open a file with what the Mac opens it with, or an address in the browser."""
    subprocess.Popen(["open", str(what)])


def game_running() -> bool:
    """Whether a World of Warcraft client runs (its process is inside World of Warcraft.app,
    whatever the flavour)."""
    try:
        r = subprocess.run(["pgrep", "-f", "World of Warcraft"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and bool(r.stdout.strip())


def message(title: str, text: str) -> None:
    """A box with the text and an OK button."""
    from AppKit import NSAlert, NSApplication
    NSApplication.sharedApplication()
    alert = NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(text)
    alert.runModal()


def browse_folder(title: str) -> Path | None:
    """A folder the user picks, or None. On the main thread, where the icon runs."""
    from AppKit import NSOpenPanel
    panel = NSOpenPanel.openPanel()
    panel.setCanChooseDirectories_(True)
    panel.setCanChooseFiles_(False)
    panel.setAllowsMultipleSelection_(False)
    panel.setMessage_(title)
    panel.setPrompt_("Choose")
    if panel.runModal() != 1:                       # NSModalResponseOK
        return None
    url = panel.URL()
    return Path(url.path()) if url else None


# ---- the icon ---------------------------------------------------------------------------------
def _delegate_class():  # noqa: C901 - one AppKit delegate class, one small method per message, counted as one
    """The AppKit object the menu and the application talk to, made once AppKit is wanted."""
    import objc
    from AppKit import NSObject

    class Delegate(NSObject):
        def initWithTray_(self, tray):
            self = objc.super(Delegate, self).init()
            if self is None:
                return None
            self.tray = tray
            return self

        def menuNeedsUpdate_(self, menu):
            self.tray._fill(menu)

        def pick_(self, sender):
            self.tray.chosen(sender.tag())

        def applicationWillTerminate_(self, note):
            self.tray.closing()

        def runCall_(self, box):
            self.tray._drain()

        def poke_(self, note):                       # a second start of the helper: the menu, at the mouse
            print("menu asked for by a second start")
            self.tray.pop()

        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
            # opened again from Applications or the Finder while running: macOS sends the running app this,
            # not a second process. The menu at the mouse, once the activation that comes with it has settled
            print("menu asked for by a reopen")
            self.performSelector_withObject_afterDelay_("popLater:", None, REOPEN_AFTER)
            return False

        def popLater_(self, _):
            self.tray.pop()

        def placed_(self, _):
            self.tray.placed()

    return Delegate


class Tray:
    """The icon in the menu bar: its menu is built each time it opens (items()), a row picked
    is chosen(id), and the application quitting is closing(). run() is the main thread's,
    and everything else reaches it through call()."""

    def __init__(self, title: str, icon: Path, items, chosen, closing):
        self.title, self.icon, self.items, self.chosen, self.closing = title, icon, items, chosen, closing
        self.calls: queue.Queue = queue.Queue()
        self.app = self.item = self.delegate = None

    def run(self) -> None:
        """The menu bar on the main thread until the app quits: no Dock icon, the icon (the title FWC when the
        image will not load), its menu built each time it opens, and a second start's word to show the menu."""
        from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSImage, NSMenu, NSSize, NSStatusBar,
                            NSVariableStatusItemLength)
        self.app = NSApplication.sharedApplication()
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)     # no Dock icon, no menu of its own
        self.delegate = _delegate_class().alloc().initWithTray_(self)
        self.app.setDelegate_(self.delegate)
        try:
            for line in start_lines():
                print(line)
        except Exception as e:  # noqa: BLE001 - the log's lines are not worth the icon
            print(f"macOS: not told ({e})")
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        image = NSImage.alloc().initWithContentsOfFile_(str(self.icon))
        if image:
            image.setSize_(NSSize(ICON_POINTS, ICON_POINTS))
            image.setTemplate_(True)                 # the glyph alone: white on a dark bar, black on a light one. The whole icon,
            self.item.button().setImage_(image)      # a navy square, could not be seen on a dark bar (reported 9 Nov 2026)
            size = image.size()
            print(f"menu bar icon made: image {size.width:g}x{size.height:g} points, template {image.isTemplate()}, visible {self.item.isVisible()}")
        else:
            self.item.button().setTitle_("FWC")
            print(f"menu bar icon made: no image (the title FWC), visible {self.item.isVisible()}")
        self.item.button().setToolTip_(self.title)
        try:                                         # a second start asks for the menu (poke()): shown at the mouse, whatever hides the icon
            from Foundation import NSDistributedNotificationCenter
            NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(self.delegate, "poke:", POKE, None)
        except Exception:  # noqa: BLE001
            pass
        menu = NSMenu.alloc().initWithTitle_(self.title)
        menu.setAutoenablesItems_(False)
        menu.setDelegate_(self.delegate)
        self.item.setMenu_(menu)
        self.delegate.performSelector_withObject_afterDelay_("placed:", None, PLACED_AFTER)
        self.app.run()

    def placed(self) -> None:
        """Whether macOS placed the icon: its button has a window, on a screen. Said in the log
        either way; when it was not, the player is told once how to reach the menu (the helper
        is otherwise quiet about its icon). macOS never placed the icon of a process it
        knew by no bundle (9 Nov 2026)."""
        button = self.item.button() if self.item is not None else None
        window = button.window() if button is not None else None
        screen = window.screen() if window is not None else None
        line, ok = placement(window, screen)
        print(line)
        if not ok:
            self.balloon(self.title, NOT_PLACED)

    def pop(self) -> None:
        """The menu at the mouse, as a click on the icon shows it."""
        from AppKit import NSEvent
        menu = self.item.menu()
        self._fill(menu)
        menu.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)

    def _fill(self, menu) -> None:
        from AppKit import NSMenuItem
        menu.removeAllItems()
        for row in self.items():
            if row is None:
                menu.addItem_(NSMenuItem.separatorItem())
                continue
            ident, label, enabled, checked = row
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(label, "pick:", "")
            it.setTarget_(self.delegate)
            it.setTag_(ident)
            it.setEnabled_(enabled)
            it.setState_(1 if checked else 0)
            menu.addItem_(it)

    def _drain(self) -> None:
        while True:
            try:
                fn = self.calls.get_nowait()
            except queue.Empty:
                return
            fn()

    def call(self, fn) -> None:
        """Run fn on the main thread, from any thread."""
        self.calls.put(fn)
        if self.delegate is not None:
            self.delegate.performSelectorOnMainThread_withObject_waitUntilDone_("runCall:", None, False)

    def tooltip(self, text: str) -> None:
        """Set the text shown when the pointer rests on the icon."""
        if self.item is not None:
            self.item.button().setToolTip_(text)

    def balloon(self, title: str, text: str) -> None:
        """A notification. Through the notification center when the app is a bundle it knows
        of; else through the system's script runner, which says it as any script's."""
        try:
            from AppKit import NSUserNotification, NSUserNotificationCenter
            center = NSUserNotificationCenter.defaultUserNotificationCenter()
        except Exception:  # noqa: BLE001 - AppKit without the (old) notification classes
            center = None
        if center is not None:
            note = NSUserNotification.alloc().init()
            note.setTitle_(title)
            note.setInformativeText_(text)
            center.deliverNotification_(note)
            return
        script = f'display notification "{_quoted(text)}" with title "{_quoted(title)}"'
        subprocess.Popen(["osascript", "-e", script])

    def quit(self) -> None:
        """Stop the event loop: run() returns, and app.py closes the rest."""
        from PyObjCTools import AppHelper
        AppHelper.stopEventLoop()


def placement(window, screen) -> tuple[str, bool]:
    """The log's line on the icon's window and screen, and whether the icon was placed."""
    if window is None or screen is None:
        return f"menu bar icon not placed: {'no window' if window is None else 'a window on no screen'}", False
    f, s = window.frame(), screen.frame()
    visible = bool(window.occlusionState() & 2)      # NSWindowOcclusionStateVisible
    return (f"menu bar icon placed: frame {f.origin.x:g},{f.origin.y:g} {f.size.width:g}x{f.size.height:g} "
            f"on a screen {s.size.width:g}x{s.size.height:g}, visible {visible}"), True


def _quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')
