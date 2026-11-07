"""The Windows side of the helper (fwchelper/win.py), where it runs: the quiet update's script.
Skipped elsewhere (win.py needs winreg)."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_the_quiet_update_runs_through_the_script_host_with_no_window():
    if sys.platform != "win32":
        return
    from fwchelper import win
    installer = Path(tempfile.mkdtemp()) / "ForeverWowCraft-Helper-9.9.9.msi"
    installer.write_bytes(b"x")
    exe = Path("C:/Program Files/FWC Helper/python/ForeverWowCraft Helper.exe")
    fwch = Path("C:/Program Files/FWC Helper/fwch.py")
    log = installer.with_name("install.log")
    text = win.update_script(installer, log, exe, fwch)
    lines = text.splitlines()
    assert lines[0] == 'Set sh = CreateObject("WScript.Shell")' and lines[1] == "WScript.Sleep 3000"
    assert lines[2] == f'sh.Run "msiexec /i ""{installer}"" /qn /norestart /l*v ""{log}""", 0, True'
    assert lines[3] == f'sh.Run """{exe}"" ""{fwch}"" app", 1, False'
    assert "ping" not in text and "cmd" not in text
    # started by wscript (no console of its own), the old cmd script cleared
    installer.with_name("update.cmd").write_text("old", encoding="utf-8")
    started = []
    kept = subprocess.Popen
    subprocess.Popen = lambda args, **kw: started.append((args, kw))
    try:
        assert win.quiet_update(installer, log) is True
    finally:
        subprocess.Popen = kept
    (args, kw), = started
    assert args[0] == "wscript.exe" and "//B" in args and args[-1].endswith("update.vbs")
    assert kw["creationflags"] & subprocess.CREATE_NO_WINDOW and not kw["creationflags"] & subprocess.DETACHED_PROCESS
    assert not installer.with_name("update.cmd").exists()
    assert installer.with_name("update.vbs").read_text(encoding="utf-16").startswith("Set sh")


def test_the_console_programs_the_helper_runs_open_no_window():
    """tasklist, run from the windowless helper for the game and for another watcher, opened a
    console window for a moment at every start (the user, 7 Nov 2026)."""
    if sys.platform != "win32":
        return
    from fwchelper import cli, win
    calls = []

    class Done:
        stdout = '"Wow.exe","1","Console","1","100 K"' + chr(10)
    kept = subprocess.run
    subprocess.run = lambda args, **kw: calls.append((args, kw)) or Done()
    try:
        assert win.game_running() is True and cli._running(1) is True
    finally:
        subprocess.run = kept
    assert len(calls) == 2 and all(kw["creationflags"] & subprocess.CREATE_NO_WINDOW for _, kw in calls)


if __name__ == "__main__":
    test_the_quiet_update_runs_through_the_script_host_with_no_window()
    test_the_console_programs_the_helper_runs_open_no_window()
    print("ok")
