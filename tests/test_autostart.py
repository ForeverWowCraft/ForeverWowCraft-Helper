"""send.cmd starts with Windows, and only one of it runs at a time."""
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import cli, settings  # noqa: E402


def test_autostart_writes_an_entry_that_opens_send_cmd_and_removes_it_again():
    folder = Path(tempfile.mkdtemp()) / "Startup"                      # not made yet, as a fresh profile's may not be
    entry = cli.autostart(True, folder)
    assert entry.parent == folder and entry.name == "ForeverWowCraft Helper.cmd" and entry.exists()
    text = entry.read_bytes().decode("utf-8")
    assert text.startswith("@echo off\r\n") and "\r\r" not in text and f'/min "{settings.ROOT / "send.cmd"}"' in text
    assert cli.autostart(True, folder) == entry                        # again: the same, not a second one
    assert [p.name for p in folder.iterdir()] == [entry.name]
    assert cli.autostart(False, folder) == entry and not entry.exists()
    cli.autostart(False, folder)                                       # off when already off is fine


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
