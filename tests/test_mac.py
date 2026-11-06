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

from fwchelper import __version__, mac, settings, tray, update  # noqa: E402
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
    code = f"import sys; sys.path.insert(0, {str(HELPER)!r}); from fwchelper import mac, settings; settings.STATE = __import__('pathlib').Path({str(folder)!r}); print(mac.one_instance(r'Local\\ForeverWowCraftHelper'))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert out == "False", out                                                        # another process: the lock is held


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
    assert (app / "Contents" / "PkgInfo").read_text() == "APPL????"
    exe = app / "Contents" / "MacOS" / "ForeverWowCraft Helper"
    text = exe.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and 'Resources/python/bin/python3.14" "$here/Resources/helper/fwch.py" app' in text
    if os.name != "nt":
        assert os.access(exe, os.X_OK)
    assert (app / "Contents" / "Resources" / "helper.icns").stat().st_size > 1000
    helper = app / "Contents" / "Resources" / "helper"
    for rel in ("fwch.py", "fwchelper/app.py", "fwchelper/mac.py", "fwchelper/helper-menubar.png", "addon/ForeverWowCraftScanner/ForeverWowCraftScanner.toc",
                "LICENSE", "README.md"):
        assert (helper / rel).is_file(), rel
    assert not (helper / "tests").exists() and not (helper / "installer").exists() and not (helper / "state").exists()
    assert build_mac.PYTHON_URL.endswith("x86_64-apple-darwin-install_only_stripped.tar.gz") and len(build_mac.PYTHON_SHA256) == 64
    assert build_mac.info_plist(__version__)["CFBundleVersion"] == __version__


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
