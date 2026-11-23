"""The Windows side of the helper (fwchelper/win.py), where it runs: the quiet update's command.
Skipped elsewhere (win.py needs winreg)."""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_the_quiet_update_is_msiexec_itself_with_no_script_host():
    """Up to 1.7.6 a VBScript run by wscript.exe ran msiexec hidden and started the helper
    again; now the helper starts Windows' own msiexec on the installer (by its full path), and
    LAUNCHAPP=1 has the installer start the new helper (installer/helper.wxs)."""
    if sys.platform != "win32":
        return
    import os
    from fwchelper import win
    installer = Path(tempfile.mkdtemp()) / "ForeverWowCraft-Helper-9.9.9.msi"
    installer.write_bytes(b"x")
    log = installer.with_name("install.log")
    command = win.install_command(installer, log)
    msiexec = Path(os.environ["SystemRoot"]) / "System32" / "msiexec.exe"
    assert command == [str(msiexec), "/i", str(installer), "/qn", "/norestart", "/l*v", str(log), "LAUNCHAPP=1"]
    assert msiexec.exists()
    # started as it is, no script and no shell between; the scripts of before cleared
    for old in ("update.vbs", "update.cmd"):
        installer.with_name(old).write_text("old", encoding="utf-8")
    started = []
    kept = subprocess.Popen
    subprocess.Popen = lambda args, **kw: started.append((args, kw))
    try:
        assert win.quiet_update(installer, log) is True
    finally:
        subprocess.Popen = kept
    (args, kw), = started
    assert args == command and not kw.get("shell")
    assert not installer.with_name("update.vbs").exists() and not installer.with_name("update.cmd").exists()
    # msiexec could not be started: False, and the helper opens the installer instead (app.update_now)
    def fail(args, **kw):
        raise OSError("no")
    subprocess.Popen = fail
    try:
        assert win.quiet_update(installer, log) is False
    finally:
        subprocess.Popen = kept


def test_the_installer_starts_the_helper_when_launchapp_is_given():
    """The MSI's execute sequence starts the helper after InstallFinalize when LAUNCHAPP=1 (the
    quiet update's), and never on removal; the finish page's tick box does it for an install
    by hand. An old helper's updater (1.7.6 and before) passes no LAUNCHAPP and starts the
    helper itself, so the two never both start it."""
    text = (Path(__file__).resolve().parent.parent / "installer" / "helper.wxs").read_text(encoding="utf-8")
    assert '<Custom Action="StartHelper" After="InstallFinalize">LAUNCHAPP = "1" AND NOT REMOVE~="ALL"</Custom>' in text
    assert "wscript" not in text.lower() and "vbs" not in text.lower()


def test_the_console_programs_the_helper_runs_open_no_window():
    """tasklist, run from the windowless helper for the game and for another watcher, opened a
    console window for a moment at every start."""
    if sys.platform != "win32":
        return
    from fwchelper import cli, win
    calls = []

    class Done:
        stdout = b'"Wow.exe","1","Console","1","100 K"' + bytes([13, 10])
    kept = subprocess.run
    subprocess.run = lambda args, **kw: calls.append((args, kw)) or Done()
    try:
        assert win.game_running() is True and cli._running(1) is True
    finally:
        subprocess.run = kept
    assert len(calls) == 2 and all(kw["creationflags"] & subprocess.CREATE_NO_WINDOW for _, kw in calls)


def test_tasklist_in_german_code_page_850_neither_stops_the_start_nor_misleads():
    """Players on a German Windows could not start the helper: tasklist answers in the OEM code page 850, and
    text=True raised UnicodeDecodeError on an umlaut. The bytes are decoded leniently now, and the answer is read by
    its CSV fields, not by the localized message."""
    if sys.platform != "win32":
        return
    from fwchelper import cli, win
    umlauts = "Zündung.exe".encode("cp850")                  # 0x81: not valid UTF-8
    try:
        umlauts.decode("utf-8")
        raise AssertionError("the bytes must be invalid UTF-8")
    except UnicodeDecodeError:
        pass
    nothing = "INFORMATION: Es werden keine Aufgaben ausgeführt, die den angegebenen Kriterien entsprechen.".encode("cp850")
    answers, CRLF = {}, bytes([13, 10])

    class Done:
        def __init__(self, out):
            self.stdout = out

    def run(args, **kw):
        assert "text" not in kw and "universal_newlines" not in kw          # bytes, decoded by us
        return Done(answers["out"])
    kept = subprocess.run
    subprocess.run = run
    try:
        answers["out"] = b'"' + umlauts + b'","4242","Console","1","1.000 K"' + CRLF
        assert cli._running(4242) is True and cli._running(42) is False       # a pid is its own field, not a part of another
        answers["out"] = nothing + CRLF
        assert cli._running(4242) is False and win.game_running() is False
        answers["out"] = b'"' + umlauts + b'","1","Console","1","1 K"' + CRLF + b'"Wow.exe","7","Console","1","9 K"' + CRLF
        assert win.game_running() is True
        answers["out"] = b'"' + umlauts + b'","1","Console","1","1 K"' + CRLF
        assert win.game_running() is False
    finally:
        subprocess.run = kept


if __name__ == "__main__":
    test_the_quiet_update_is_msiexec_itself_with_no_script_host()
    test_the_installer_starts_the_helper_when_launchapp_is_given()
    test_the_console_programs_the_helper_runs_open_no_window()
    test_tasklist_in_german_code_page_850_neither_stops_the_start_nor_misleads()
    print("ok")
