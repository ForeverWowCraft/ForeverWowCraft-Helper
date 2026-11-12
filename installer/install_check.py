"""The helper's .msi installed, upgraded, started and removed for real, on a Windows PC with no
helper on it (CI's hosted runner): per-user installs, no administrator, as a player has them.

    python installer/install_check.py --old-url URL --old-sha256 HEX --new A.msi --newer B.msi --logs DIR

1. the old release (downloaded, its SHA-256 checked) installed quietly: its files and the Run
   entry there, and no helper started (a quiet install by hand starts none)
2. A over it as the old release's own quiet update ran msiexec (up to 1.7.6: a VBScript ran
   `msiexec /i <msi> /qn /norestart /l*v <log>`, no LAUNCHAPP, and started the helper itself):
   the log says it succeeded, the files are A's, the zip-only scripts are not there, and the
   installer started no helper (the old script does that)
3. B over A as this helper's quiet update does (fwchelper/win.py install_command: LAUNCHAPP=1):
   the installer starts the helper, exactly one, and it is still running moments later, the new
   helper's log saying it started
4. B removed quietly: the running helper closed, none started again, the Run entry and every
   file the install put in gone

The helper started in 3 is pointed at nowhere first (the pipe, the site and the update check at
127.0.0.1:9, as user settings), so a test never registers at the real pipe. msiexec's logs go
to DIR. It refuses to run where a helper is installed already, or outside CI: it would replace
that helper and then remove it.
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
import time
import winreg
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import embed  # noqa: E402
import exeicon  # noqa: E402
from fwchelper import win  # noqa: E402

NAME = "ForeverWowCraft Helper"
INSTALLED = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / NAME
EXE = INSTALLED / "python" / f"{NAME}.exe"
RUN_KEY, RUN_VALUE = r"Software\Microsoft\Windows\CurrentVersion\Run", NAME
OWN_KEY = r"Software\ForeverWowCraft\Helper"
NOWHERE = {"FWC_PIPE_URL": "http://127.0.0.1:9", "FWC_SITE_URL": "http://127.0.0.1:9", "FWC_UPDATE_URL": "http://127.0.0.1:9/latest",
           "FWC_UPDATE_API": "http://127.0.0.1:9/api", "FWC_UPDATE_QUIET": "0"}


class Failed(Exception):
    """A step did not do what it should."""


def check(ok: bool, what: str) -> None:
    """Say what was checked; stop the test when it is not so."""
    print(("  ok    " if ok else "  FAIL  ") + what, flush=True)
    if not ok:
        raise Failed(what)


def run_value() -> str | None:
    """The helper's Run entry, or None."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            return str(winreg.QueryValueEx(k, RUN_VALUE)[0])
    except OSError:
        return None


def installed_before() -> bool:
    """Whether a helper is installed for this user already."""
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, OWN_KEY).Close()
        return True
    except OSError:
        return INSTALLED.exists()


def helpers() -> list[int]:
    """The process ids of the helpers running (the installed exe's image name)."""
    out = subprocess.run(["tasklist", "/fi", f"IMAGENAME eq {NAME}.exe", "/fo", "csv", "/nh"], capture_output=True, text=True,
                         creationflags=subprocess.CREATE_NO_WINDOW).stdout
    return [int(line.split('","')[1]) for line in out.splitlines() if line.startswith(f'"{NAME}.exe"')]


def msiexec(args: list[str]) -> int:
    """Run msiexec as given and wait; its exit code. 0 is done, 3010 done with a restart asked for."""
    started = time.time()
    code = subprocess.run(args).returncode
    print(f"  msiexec {' '.join(a for a in args[1:] if not a.endswith(('.msi', '.log')))}: exit {code} in {time.time() - started:.0f} s", flush=True)
    return code


def log_says_done(log: Path) -> bool:
    """Whether msiexec's log ends in success (it is UTF-16 when it starts with the mark, else ANSI)."""
    data = log.read_bytes()
    text = data.decode("utf-16") if data[:2] == b"\xff\xfe" else data.decode("mbcs", errors="replace")
    return "success or error status: 0" in text


def files_now() -> set[Path]:
    """The files under the install folder, but Python's own byte code (written while the helper runs)."""
    return {p for p in INSTALLED.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def wait_for(cond, seconds: float) -> bool:
    """Whether `cond()` came true within `seconds`."""
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(1)
    return bool(cond())


def nowhere(on: bool) -> None:
    """Point the helper's pipe, site and update check at 127.0.0.1:9 as user settings, or take that off."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
        for name, value in NOWHERE.items():
            if on:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(k, name)
                except OSError:
                    pass


def steps(old: Path, new: Path, newer: Path, logs: Path) -> None:  # noqa: C901 - one story, step by step
    """The four steps of the module's docstring; raises Failed at the first that does not hold."""
    command = f'"{EXE}" "{INSTALLED / "fwch.py"}" app'

    print("1. the old release, installed quietly", flush=True)
    log = logs / "1-old-install.log"
    check(msiexec(["msiexec", "/i", str(old), "/qn", "/norestart", "/l*v", str(log)]) == 0 and log_says_done(log), "installed")
    check(EXE.exists() and (INSTALLED / "fwch.py").exists(), "its exe and fwch.py are there")
    check(run_value() == command, "its Run entry starts the exe on fwch.py app")
    time.sleep(5)
    check(helpers() == [], "no helper started")

    print("2. A over it, as the old helper's quiet update ran msiexec (no LAUNCHAPP)", flush=True)
    log = logs / "2-old-updater.log"
    check(msiexec(["msiexec", "/i", str(new), "/qn", "/norestart", "/l*v", str(log)]) == 0 and log_says_done(log), "installed, the log says so")
    check("def install_command(" in (INSTALLED / "fwchelper" / "win.py").read_text(encoding="utf-8"), "the helper's files are A's")
    check(not (INSTALLED / "send.cmd").exists() and not (INSTALLED / "setup.cmd").exists(), "send.cmd and setup.cmd are not installed")
    data = EXE.read_bytes()
    check(exeicon.signature_entry(data) == (0, 0), "A's exe has no stale signature pointer")
    check(exeicon.file_version(EXE).get("FileVersion") == product_version(new), f"the exe is A's ({product_version(new)})")
    check(run_value() == command, "the Run entry is the same command, the one the old script starts")
    time.sleep(5)
    check(helpers() == [], "the installer started no helper (the old script starts it)")

    print("3. B over A, as this helper's quiet update does (LAUNCHAPP=1)", flush=True)
    nowhere(True)
    log = logs / "3-new-updater.log"
    args = win.install_command(newer, log)
    check(args[0].lower().endswith(r"\system32\msiexec.exe") and args[-1] == "LAUNCHAPP=1", "the command is msiexec itself with LAUNCHAPP=1")
    check(msiexec(args) == 0 and log_says_done(log), "installed, the log says so")
    check(exeicon.file_version(EXE).get("FileVersion") == product_version(newer), f"the exe is B's ({product_version(newer)})")
    check(wait_for(lambda: len(helpers()) >= 1, 30), "the installer started the helper")
    time.sleep(10)
    running = helpers()
    check(len(running) == 1, f"exactly one helper is running 10 s later ({len(running)})")
    state_log = Path(os.environ["LOCALAPPDATA"]) / "ForeverWowCraft" / "Helper" / "helper.log"      # the state folder (settings.STATE)
    def said() -> str:
        return state_log.read_text(encoding="utf-8", errors="replace") if state_log.exists() else ""
    wait_for(lambda: " started; the state is in " in said(), 20)
    for line in said().splitlines()[:6]:
        print("    helper.log: " + line[:160])
    check(f"{NAME} " in said() and " started; the state is in " in said(), "the helper's log says it started")
    files = files_now()

    print("4. B removed quietly", flush=True)
    log = logs / "4-uninstall.log"
    check(msiexec(["msiexec", "/x", str(newer), "/qn", "/norestart", "/l*v", str(log)]) == 0 and log_says_done(log), "removed, the log says so")
    check(wait_for(lambda: helpers() == [], 20), "the running helper closed")
    time.sleep(5)
    check(helpers() == [], "no helper started again")
    check(run_value() is None, "the Run entry is gone")
    left = sorted(str(p.relative_to(INSTALLED)) for p in files if p.exists())
    check(not left, f"every file the install put in is gone ({len(files)} files; left: {left[:5]})")
    extra = sorted(str(p.relative_to(INSTALLED)) for p in INSTALLED.rglob("*")) if INSTALLED.exists() else []
    print(f"  note  the install folder {'is gone' if not extra else 'still holds what the running helper wrote: ' + ', '.join(extra[:6])}")


def product_version(msi: Path) -> str:
    """The .msi's ProductVersion, read from its Property table."""
    import msilib                       # Python 3.12's own (the CI's): read-only, a query
    db = msilib.OpenDatabase(str(msi), msilib.MSIDBOPEN_READONLY)
    view = db.OpenView("SELECT `Value` FROM `Property` WHERE `Property` = 'ProductVersion'")
    view.Execute(None)
    value = view.Fetch().GetString(1)
    view.Close()
    return value


def main(argv=None) -> int:
    """The command line: the test, 0 when every step held."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--old-url", required=True, help="the old release's .msi")
    ap.add_argument("--old-sha256", required=True, help="its SHA-256: the test stops when the download is not that")
    ap.add_argument("--new", type=Path, required=True, help="A: this helper's .msi, installed the old updater's way")
    ap.add_argument("--newer", type=Path, required=True, help="B: this helper's .msi under a higher version, installed this updater's way")
    ap.add_argument("--logs", type=Path, required=True, help="where msiexec's logs go")
    ap.add_argument("--cache", type=Path, help="where the old .msi is downloaded (default: the logs' folder)")
    a = ap.parse_args(argv)
    if not os.environ.get("GITHUB_ACTIONS") and not os.environ.get("CI"):
        raise SystemExit("this installs, replaces and removes the helper for this user: CI only")
    if installed_before():
        raise SystemExit("a helper is installed for this user already: not touched")
    a.logs.mkdir(parents=True, exist_ok=True)
    cache = a.cache or a.logs
    data = embed.fetch(a.old_url, a.old_sha256.lower(), cache)      # downloaded once, its SHA-256 checked, or the test stops
    old = cache / a.old_url.rsplit("/", 1)[1]
    print(f"the old release: {old.name}, {len(data)} bytes, SHA-256 as pinned")
    try:
        steps(old, a.new.resolve(), a.newer.resolve(), a.logs.resolve())
    except Failed:
        return 1
    finally:
        nowhere(False)
    print("every step held")
    return 0


if __name__ == "__main__":
    sys.exit(main())
