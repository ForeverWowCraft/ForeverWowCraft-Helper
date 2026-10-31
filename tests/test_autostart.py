"""The app starts with Windows through the user's Run key, and only one helper sends at a time."""
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import cli, settings, tray  # noqa: E402


class Registry:
    """What fwchelper/win.py reads and writes of the registry, as a dict."""

    def __init__(self):
        self.run, self.records = {}, {}

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


def test_autostart_puts_the_app_under_the_run_key_and_takes_it_out_again():
    reg = Registry()
    reg.records[tray.RUN_VALUE] = bytes([3]) + bytes(11)               # Windows' own switch had been turned off
    folder = Path(tempfile.mkdtemp()) / "Startup"
    folder.mkdir()
    old = folder / "ForeverWowCraft Helper.cmd"                        # what helpers before 1.5.0 wrote there
    old.write_text("start send.cmd", encoding="utf-8")
    kept = cli.startup_dir
    cli.startup_dir = lambda: folder
    try:
        command = cli.autostart(True, reg)
        assert command == f'"{tray.app_exe()}" "{settings.ROOT / "fwch.py"}" app' and reg.run[tray.RUN_VALUE] == command
        assert reg.records[tray.RUN_VALUE][0] == 2 and not old.exists()  # the switch is on again, the old entry is gone
        assert tray.startup_on(reg.run_value(tray.RUN_VALUE), reg.approved(tray.RUN_VALUE))
        assert cli.autostart(True, reg) == command                     # again: the same, not a second one
        assert cli.autostart(False, reg) == "" and tray.RUN_VALUE not in reg.run
        assert not tray.startup_on(reg.run_value(tray.RUN_VALUE), reg.approved(tray.RUN_VALUE))
        cli.autostart(False, reg)                                      # off when already off is fine
    finally:
        cli.startup_dir = kept


def test_windows_own_switch_counts():
    assert not tray.startup_on(None, None)                             # no entry: not starting
    assert tray.startup_on("cmd", None)                                # an entry Windows has no record of: on
    assert tray.startup_on("cmd", bytes([2]) + bytes(11)) and tray.startup_on("cmd", bytes([6]) + bytes(11))
    assert not tray.startup_on("cmd", bytes([3]) + bytes(11))          # turned off in Settings > Apps > Startup


def test_a_second_watcher_sees_the_first_and_a_dead_one_is_not_counted():
    kept = settings.STATE
    settings.STATE = Path(tempfile.mkdtemp())
    try:
        assert cli.other_watcher() is None                             # nobody: the watch is ours
        assert (settings.STATE / "watching.pid").read_text(encoding="utf-8") == str(os.getpid())
        assert cli.other_watcher() is None                             # ours already: still ours
        gone = subprocess.Popen([sys.executable, "-c", "pass"])        # a process that has ended
        gone.wait()
        (settings.STATE / "watching.pid").write_text(str(gone.pid), encoding="utf-8")
        assert cli.other_watcher() is None                             # a watcher that ended is no watcher
        (settings.STATE / "watching.pid").write_text("garbage", encoding="utf-8")
        assert cli.other_watcher() is None                             # nor is an unreadable note
        alive = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            (settings.STATE / "watching.pid").write_text(str(alive.pid), encoding="utf-8")
            assert cli.other_watcher() == alive.pid                    # another one is running: not ours
            assert (settings.STATE / "watching.pid").read_text(encoding="utf-8") == str(alive.pid)
        finally:
            alive.kill()
            alive.wait()
        assert cli.other_watcher() is None                             # it ended: the watch is ours again
        cli.release_watch()
        assert not (settings.STATE / "watching.pid").exists()
    finally:
        settings.STATE = kept


def test_a_watching_window_says_when_each_line_was_written():
    out = io.StringIO()
    window = cli.Stamped(out)
    print("sent Stonespine (Horde): 12 items", file=window)
    print("\nfirst\nsecond", file=window)
    window.write("half, ")
    window.write("then the rest\n")
    lines = out.getvalue().split("\n")
    stamp = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}  "                   # year first, then the time of day
    assert re.fullmatch(stamp + r"sent Stonespine \(Horde\): 12 items", lines[0])
    assert lines[1] == "" and re.fullmatch(stamp + "first", lines[2]) and re.fullmatch(stamp + "second", lines[3])
    assert re.fullmatch(stamp + "half, then the rest", lines[4])       # once a line, not once a write
    # send --watch stamps every line it prints, so no message carries a time of its own
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert "stamp_lines()\n    other = other_watcher()" in source and "%H:%M:%S')}" not in source


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
