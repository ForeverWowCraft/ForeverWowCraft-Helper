"""The helper's Mac side without a Mac: the launch agent, the settings file the menu saves
where there is no registry, the lock, the .dmg check, and what the application bundle holds
(installer/build_mac.py), laid out without Python. AppKit itself is not touched here."""
import json
import os
import plistlib
import sys
import tempfile
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))
sys.path.insert(0, str(HELPER / "installer"))

from fwchelper import __version__, mac, settings, update  # noqa: E402
import build_mac  # noqa: E402


def _state():
    """A state folder of this test's own."""
    folder = Path(tempfile.mkdtemp()) / "state"
    settings.STATE = folder
    settings._stored = (None, {})
    return folder


def test_the_launch_agent_runs_the_app_at_login():
    cmd = mac.app_command("/usr/local/bin/python3", Path("/Users/me/helper/fwch.py"))
    assert cmd == ["/usr/local/bin/python3", str(Path("/Users/me/helper/fwch.py")), "app"]     # the path as this OS writes it
    agent = mac.launch_agent(cmd)
    assert agent["Label"] == "com.foreverwowcraft.helper" and agent["RunAtLoad"] is True and agent["KeepAlive"] is False
    assert agent["ProgramArguments"] == cmd
    text = plistlib.dumps(agent)                                                    # what launchd reads: a plist
    assert b"<string>com.foreverwowcraft.helper</string>" in text and plistlib.loads(text) == agent
    assert mac.agent_path().name == "com.foreverwowcraft.helper.plist" and mac.agent_path().parent.name == "LaunchAgents"


def test_inside_the_application_bundle_the_agent_starts_the_bundle_itself():
    root = Path(tempfile.mkdtemp())
    app = root / "Applications" / "ForeverWowCraft Helper.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    python = app / "Contents" / "Resources" / "python" / "bin" / "python3.14"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    assert mac.app_bundle(str(python)) == app.resolve()                                # resolved: a Mac's temp folder is a link
    assert mac.app_command(str(python)) == [str(app.resolve() / "Contents" / "MacOS" / "ForeverWowCraft Helper")]
    assert mac.app_bundle(str(root / "checkout" / "python3")) is None


def test_the_menu_saves_the_game_folder_in_the_state_folder_and_env_sees_it():
    folder = _state()
    for name in ("FWC_WOW_DIR", "FC_WOW_DIR"):
        os.environ.pop(name, None)
    assert settings.env("WOW_DIR") is None and settings.stored() == {}
    mac.set_user_setting("FWC_WOW_DIR", "/Applications/World of Warcraft")
    assert json.loads((folder / "settings.json").read_text(encoding="utf-8")) == {"FWC_WOW_DIR": "/Applications/World of Warcraft"}
    assert os.environ["FWC_WOW_DIR"] == "/Applications/World of Warcraft"            # this process sees it at once
    del os.environ["FWC_WOW_DIR"]
    assert settings.env("WOW_DIR") == "/Applications/World of Warcraft"              # and every run from now on, from the file
    os.environ["FWC_WOW_DIR"] = "/elsewhere"
    assert settings.env("WOW_DIR") == "/elsewhere"                                    # the environment comes first
    del os.environ["FWC_WOW_DIR"]
    (folder / "settings.json").write_text("not json", encoding="utf-8")
    settings._stored = (None, {})
    assert settings.env("WOW_DIR", "default") == "default"                           # a broken file is no setting
    assert settings.env("STATE") is None                                              # STATE itself never comes from the file


def test_one_instance_at_a_time_through_the_lock():
    folder = _state()
    if mac.fcntl is None:
        assert mac.one_instance(r"Local\ForeverWowCraftHelper") is True              # Windows: the mutex is win.py's, this cannot tell
        return
    assert mac.one_instance(r"Local\ForeverWowCraftHelper") is True
    assert (folder / "ForeverWowCraftHelper.lock").exists()
    import subprocess
    code = f"import sys; sys.path.insert(0, {str(HELPER)!r}); from fwchelper import mac, settings; settings.STATE = __import__('pathlib').Path({str(folder)!r}); print(mac.one_instance(r'Local\\ForeverWowCraftHelper'))"  # noqa: E501 - the program run in a child Python, kept on one line
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert out == "False", out                                                        # another process: the lock is held


def test_the_menu_bar_image_is_a_template_and_a_second_start_asks_for_the_menu():
    """The menu bar's image is the glyph on a clear ground (the Mac colours it for a dark or a
    light bar); the whole icon, a navy square, could not be seen on a dark bar, and players
    reported the helper running with no icon (9 Nov 2026). A second start sends the running
    helper the word to show its menu at the mouse."""
    text = (HELPER / "fwchelper" / "mac.py").read_text(encoding="utf-8")
    assert "image.setTemplate_(True)" in text and 'addObserver_selector_name_object_(self.delegate, "poke:", POKE, None)' in text
    assert "popUpMenuPositioningItem_atLocation_inView_" in text and mac.POKE == "com.foreverwowcraft.helper.show"
    assert isinstance(mac.poke(), bool)                                              # False without AppKit, never an error
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(mac.ICON).convert("RGBA")
    alpha = im.getchannel("A")
    corners = [alpha.getpixel(p) for p in ((0, 0), (63, 0), (0, 63), (63, 63))]
    opaque = sum(1 for v in alpha.tobytes() if v > 128) / (im.size[0] * im.size[1])
    assert im.size == (64, 64) and corners == [0, 0, 0, 0] and 0.15 < opaque < 0.5       # a glyph, not a filled square
    assert all(px[:3] == (0, 0, 0) for px in im.getdata() if px[3] > 0)                # black: the Mac does the colouring


def test_a_disk_image_is_known_by_its_trailer_and_an_msi_by_its_head():
    folder = Path(tempfile.mkdtemp())
    dmg = folder / "a.dmg"
    dmg.write_bytes(b"\0" * 1000 + update.DMG_TRAILER + b"\0" * 508)
    assert update.is_installer(dmg, "dmg") and not update.is_installer(dmg, "msi")
    msi = folder / "a.msi"
    msi.write_bytes(update.MSI_MAGIC + b"\0" * 500)
    assert update.is_installer(msi, "msi") and not update.is_installer(msi, "dmg")
    short = folder / "short.dmg"
    short.write_bytes(b"koly")
    assert not update.is_installer(short, "dmg") and not update.is_installer(folder / "missing.dmg", "dmg")
    assert settings.UPDATE_FILE.endswith(".dmg" if sys.platform == "darwin" else ".msi")


def test_the_application_bundle_holds_the_helper_its_icon_and_a_launcher():
    out = Path(tempfile.mkdtemp())
    app = build_mac.stage(out, out / "cache", "1.5.9", python=False)
    assert app.name == "ForeverWowCraft Helper.app"
    with open(app / "Contents" / "Info.plist", "rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleIdentifier"] == "com.foreverwowcraft.helper" and info["CFBundleShortVersionString"] == "1.5.9"
    assert info["LSUIElement"] is True and info["CFBundleExecutable"] == "ForeverWowCraft Helper" and info["CFBundleIconFile"] == "helper"
    assert info["LSMinimumSystemVersion"] == build_mac.MACOS_MIN
    assert (app / "Contents" / "PkgInfo").read_text() == "APPL????"
    # the executable is compiled against the Pythons, so a layout without them has none: never a script that starts Python
    assert (app / "Contents" / "MacOS").is_dir() and list((app / "Contents" / "MacOS").iterdir()) == []
    assert (app / "Contents" / "Resources" / "helper.icns").stat().st_size > 1000
    helper = app / "Contents" / "Resources" / "helper"
    for rel in ("fwch.py", "fwchelper/app.py", "fwchelper/mac.py", "fwchelper/helper-menubar.png", "addon/ForeverWowCraftScanner/ForeverWowCraftScanner.toc",
                "LICENSE", "README.md"):
        assert (helper / rel).is_file(), rel
    assert not (helper / "tests").exists() and not (helper / "installer").exists() and not (helper / "state").exists()
    assert build_mac.PYTHON_URL.endswith("x86_64-apple-darwin-install_only_stripped.tar.gz") and len(build_mac.PYTHON_SHA256) == 64
    assert build_mac.PYTHONS["arm64"][0].endswith("aarch64-apple-darwin-install_only_stripped.tar.gz") and len(build_mac.PYTHONS["arm64"][1]) == 64
    assert build_mac.native_arch() in ("x86_64", "arm64")
    assert build_mac.info_plist(__version__)["CFBundleVersion"] == __version__


def test_the_launcher_is_compiled_for_both_processors_and_runs_python_in_its_own_process():
    """A script that started the bundle's Python left the process with no bundle, and a newer
    macOS never placed its menu bar icon (9 Nov 2026): the main executable is compiled from
    installer/launcher.c, one slice for each processor against that processor's Python, joined
    with lipo, and the bundle is then signed ad hoc under its identifier."""
    res, exe, work = Path("/b/Resources"), Path("/b/MacOS/ForeverWowCraft Helper"), Path("/w")
    cmds = build_mac.launcher_commands(res, exe, work)
    assert [c[0] for c in cmds] == ["clang", "clang", "lipo"]
    for cmd, arch in zip(cmds, ("x86_64", "arm64")):
        assert cmd[1:3] == ["-arch", arch] and "-mmacosx-version-min=11.0" in cmd and str(build_mac.LAUNCHER) in cmd
        assert cmd[cmd.index("-I") + 1] == str(res / f"python-{arch}" / "include" / "python3.14")
        assert cmd[cmd.index("-L") + 1] == str(res / f"python-{arch}" / "lib") and "-lpython3.14" in cmd
        assert f"-Wl,-rpath,@executable_path/../Resources/python-{arch}/lib" in cmd      # libpython found inside the bundle, wherever it is
        assert cmd[-2:] == ["-o", str(work / f"launcher-{arch}")]
    assert cmds[2] == ["lipo", "-create", str(work / "launcher-x86_64"), str(work / "launcher-arm64"), "-output", str(exe)]
    assert build_mac.sign_command(Path("/o/ForeverWowCraft Helper.app")) == [
        "codesign", "--force", "--sign", "-", "--identifier", "com.foreverwowcraft.helper", str(Path("/o/ForeverWowCraft Helper.app"))]
    src = build_mac.LAUNCHER.read_text(encoding="utf-8")
    for part in ("Py_InitializeFromConfig", "Py_RunMain", "config.home", "config.write_bytecode = 0", "_NSGetExecutablePath",
                 '"%s/Resources/python-" ARCH', '"%s/Resources/helper/fwch.py"', 'args[n++] = "app";', '#define ARCH "arm64"', '#define ARCH "x86_64"'):
        assert part in src, part
    assert "execv" not in src and "posix_spawn" not in src and "#!/bin/sh" not in (HELPER / "installer" / "build_mac.py").read_text(encoding="utf-8")
    assert "launcher.c" not in [p.name for p in build_mac.build.helper_files()]       # the source stays out of the bundle's helper/


def test_no_clang_is_said_plainly():
    which = build_mac.shutil.which
    build_mac.shutil.which = lambda name: None
    try:
        build_mac.compile_launcher(Path("/b/Resources"), Path("/b/MacOS/x"))
    except SystemExit as e:
        assert "clang" in str(e) and "xcode-select --install" in str(e)
    else:
        raise AssertionError("no SystemExit without clang")
    finally:
        build_mac.shutil.which = which


class _Rect:
    def __init__(self, x, y, w, h):
        self.origin = type("P", (), {"x": x, "y": y})()
        self.size = type("S", (), {"width": w, "height": h})()


class _Window:
    def __init__(self, screen, occlusion=2):
        self._screen, self._occlusion = screen, occlusion

    def screen(self):
        return self._screen

    def frame(self):
        return _Rect(2206, 1416, 34, 24)

    def occlusionState(self):
        return self._occlusion


class _Screen:
    def frame(self):
        return _Rect(0, 0, 2560, 1440)


def _tray_with(window):
    """A Tray whose status item's button has `window`, its notifications kept in a list."""
    t = mac.Tray("ForeverWowCraft Helper", mac.ICON, list, print, print)
    button = type("B", (), {"window": lambda self: window})()
    t.item = type("I", (), {"button": lambda self: button})()
    t.said = []
    t.balloon = lambda title, text: t.said.append((title, text))
    return t


def test_an_icon_the_menu_bar_did_not_place_is_said_once_and_a_placed_one_only_in_the_log():
    import contextlib
    import io
    screen = _Screen()
    assert mac.placement(None, None) == ("menu bar icon not placed: no window", False)
    assert mac.placement(_Window(None), None) == ("menu bar icon not placed: a window on no screen", False)
    line, ok = mac.placement(_Window(screen), screen)
    assert ok and line == "menu bar icon placed: frame 2206,1416 34x24 on a screen 2560x1440, visible True"
    assert mac.placement(_Window(screen, occlusion=0), screen)[0].endswith("visible False")
    for window, told in ((None, True), (_Window(None), True), (_Window(screen), False)):
        t = _tray_with(window)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            t.placed()
        assert printed.getvalue().startswith("menu bar icon ")
        assert t.said == ([("ForeverWowCraft Helper", mac.NOT_PLACED)] if told else [])          # quiet when the icon is there
    assert "Open the helper again from Applications" in mac.NOT_PLACED
    text = (HELPER / "fwchelper" / "mac.py").read_text(encoding="utf-8")
    assert 'performSelector_withObject_afterDelay_("placed:", None, PLACED_AFTER)' in text          # once a start, a few seconds in
    assert text.count("def placed(") == 1 and mac.PLACED_AFTER >= 1


def test_opening_the_running_helper_again_shows_its_menu_after_the_activation():
    """Opened again from Applications or the Finder, a running app is sent a reopen, not
    started twice: the menu at the mouse, a moment later (the activation that comes with the
    reopen closed a menu shown at once), and False to AppKit."""
    text = (HELPER / "fwchelper" / "mac.py").read_text(encoding="utf-8")
    body = text.split("def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):", 1)[1].split("def popLater_", 1)[0]
    assert 'print("menu asked for by a reopen")' in body and "return False" in body
    assert 'self.performSelector_withObject_afterDelay_("popLater:", None, REOPEN_AFTER)' in body
    assert "def popLater_(self, _):\n            self.tray.pop()" in text and 0 < mac.REOPEN_AFTER < 1
    assert 'print("menu asked for by a second start")' in text


def test_the_log_writes_the_home_folder_as_a_tilde_and_identity_is_the_macs_alone():
    home = str(Path.home())
    assert mac.shown(home + "/Downloads/ForeverWowCraft Helper.app") == "~/Downloads/ForeverWowCraft Helper.app"
    assert mac.shown("/Applications/ForeverWowCraft Helper.app") == "/Applications/ForeverWowCraft Helper.app"
    assert mac.shown(home + "x/y") == home + "x/y"                                    # another user's folder beside it is left
    if sys.platform != "darwin":
        from fwchelper import cli
        try:
            cli.main(["app", "--identity"])
        except SystemExit as e:
            assert "Mac" in str(e)
        else:
            raise AssertionError("--identity ran off a Mac")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
