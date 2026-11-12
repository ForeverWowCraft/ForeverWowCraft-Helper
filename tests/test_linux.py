"""Linux, without a real Wine prefix: where the game is looked for, where the state goes, and
the systemd user service that starts send --watch at login."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import cli, scan, settings  # noqa: E402


def _wow(prefix: Path, programs: str = "Program Files (x86)", flavor: str = "_forever_") -> Path:
    wow = prefix / "drive_c" / programs / "World of Warcraft"
    (wow / flavor).mkdir(parents=True)
    return wow


def test_prefixes_that_hold_the_game_are_found():
    if sys.platform in ("win32", "darwin"):
        return
    home = Path(tempfile.mkdtemp())
    battlenet = _wow(home / "Games" / "battlenet")
    (home / "Games" / "empty" / "drive_c").mkdir(parents=True)                 # a prefix with no game
    wine = _wow(home / ".wine", flavor="_retail_")
    bottles = _wow(home / ".local" / "share" / "bottles" / "bottles" / "wow", programs="Program Files")
    steam = home / ".steam" / "steam"
    proton = _wow(steam / "steamapps" / "compatdata" / "99" / "pfx")
    library = home / "SteamLibrary"
    extra = _wow(library / "steamapps" / "compatdata" / "100" / "pfx")
    (steam / "steamapps").mkdir(parents=True, exist_ok=True)
    (steam / "steamapps" / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n"0"\n{\n"path"\t\t"%s"\n}\n}\n' % library, encoding="utf-8")
    lutris_root = home / "lutris-games"
    lutris = _wow(lutris_root / "wow")
    (home / ".config" / "lutris").mkdir(parents=True)
    (home / ".config" / "lutris" / "system.yml").write_text("game_path: %s\n" % lutris_root, encoding="utf-8")
    found = scan._search_linux_wow_dirs(home)
    assert found == [wine, battlenet, bottles, lutris, proton, extra]
    assert all("empty" not in str(p) for p in found)


def test_the_prefix_that_holds_the_flavour_wins():
    if sys.platform in ("win32", "darwin"):
        return
    retail = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (retail / "_retail_").mkdir(parents=True)
    forever = Path(tempfile.mkdtemp()) / "World of Warcraft"
    (forever / "_forever_").mkdir(parents=True)
    old = os.environ.get("FWC_WOW_DIR"), os.environ.get("FC_WOW_DIR"), os.environ.get("FWC_WOW_FLAVOR"), settings.stored
    os.environ.pop("FWC_WOW_DIR", None)
    os.environ.pop("FC_WOW_DIR", None)
    os.environ.pop("FWC_WOW_FLAVOR", None)
    settings.stored = lambda: {}
    kept = scan._linux_wow_dirs
    scan._linux_wow_dirs = lambda: [retail, forever]
    try:
        assert scan.wow_dir() == forever
    finally:
        scan._linux_wow_dirs = kept
        settings.stored = old[3]
        for name, value in (("FWC_WOW_DIR", old[0]), ("FC_WOW_DIR", old[1]), ("FWC_WOW_FLAVOR", old[2])):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_linux_state_is_the_data_home():
    if os.name == "nt" or sys.platform == "darwin":
        return
    old = os.environ.get("FWC_STATE"), os.environ.get("FC_STATE"), os.environ.get("XDG_DATA_HOME")
    os.environ.pop("FWC_STATE", None)
    os.environ.pop("FC_STATE", None)
    data = Path(tempfile.mkdtemp())
    os.environ["XDG_DATA_HOME"] = str(data)
    try:
        assert settings._state_dir() == data / "ForeverWowCraft" / "Helper"
    finally:
        for name, value in (("FWC_STATE", old[0]), ("FC_STATE", old[1]), ("XDG_DATA_HOME", old[2])):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_autostart_writes_a_user_service_and_removes_it():
    folder = Path(tempfile.mkdtemp())
    unit = folder / cli.LINUX_UNIT
    calls = []

    def systemctl(*args):
        calls.append(args)

    command = cli.linux_autostart(True, unit=unit, systemctl=systemctl)
    text = unit.read_text(encoding="utf-8")
    assert "send --watch" in command and str(settings.ROOT / "fwch.py") in text
    assert f"ExecStart={command}" in text and "WantedBy=default.target" in text
    assert calls == [("daemon-reload",), ("enable", "--now", cli.LINUX_UNIT)]
    assert cli.linux_autostart(False, unit=unit, systemctl=systemctl) == ""
    assert not unit.exists()
    assert calls[2:] == [("disable", "--now", cli.LINUX_UNIT), ("daemon-reload",)]


def test_a_path_with_spaces_is_quoted_for_systemd():
    assert cli._systemd_arg("/usr/bin/python3") == "/usr/bin/python3"
    assert cli._systemd_arg("/home/me/My Games/fwch.py") == '"/home/me/My Games/fwch.py"'


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
