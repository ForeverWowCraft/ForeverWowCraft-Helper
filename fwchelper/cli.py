"""The helper's commands: `python fwch.py <command>`.

  where          the game folder, the client, the AddOns folder and the scan files that were found
  install-addon  copy the two addons into the game
  status         what the addon's saved scans hold
  send           send the latest scan through the pipe; with --watch, after every SAVE in game
  app            the same, as a Windows application: an icon by the clock, no window (fwchelper/app.py)
  autostart      have the app start when you log in (--off undoes it)
  lists          fetch the lists from the pipe and write them into the addon
  plans          fetch the routes of your characters' auction houses from the site and write them
                 into the addon, for its /fwc window; `send --watch` does it by itself
  whoami         the name this helper sends under, and whether it is trusted

The first `send` or `lists` registers the helper with the pipe: it is given a token of its own,
kept in the state folder (settings.STATE: identity.json). Nothing has to be set or asked for.

WHAT IS SENT, WHEN (everything the addon gathers: docs/scanner-addon.md, "What the addon
gathers"): `send` (and the app, which runs `send --watch`) sends a scan after the player saved
one in game, and the merchants, trainers and recipe scrolls the player met when they changed
(send_vendors_once), to the project's pipe, pooled with other players' to price the routes and
to know Forever's vendors, trainers and recipes. pipe.py says what each document holds and what is
never in one. Besides, the helper only reads: the lists and the freshness from the pipe, the
routes from the site (asked for by the auction house, nothing else), and new versions of itself.
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

from . import __version__, pipe as pipemod, plans as plansmod, scan, settings, tray
from . import fresh as freshmod


def where() -> None:
    """Print what was found on this machine: the game folder, the client, the AddOns folder, the addon, the scan files, the state folder and what starts at login."""
    base, flav = scan.wow_dir(), scan.flavor()
    present = scan.flavors_present()
    print(f"WoW folder:     {base}  ({'found' if base.is_dir() else 'NOT FOUND'}"
          + (", from FWC_WOW_DIR" if settings.env("WOW_DIR") else "") + ")")
    print(f"Client flavour: {flav}  ({'found' if (base / flav).is_dir() else 'NOT FOUND'}"
          + (", from FWC_WOW_FLAVOR" if settings.env("WOW_FLAVOR") else "")
          + (f"; present: {', '.join(present)}" if present else "") + ")")
    print(f"AddOns folder:  {scan.addons_dir()}  ({'found' if scan.addons_dir().is_dir() else 'NOT FOUND'})")
    installed = scan.addons_dir() / scan.ADDON_NAME
    print(f"Addon:          {'installed' if installed.is_dir() else 'not installed'}  ({installed})")
    found = scan.find_saved_variables()
    print("Scan files:     " + (", ".join(f"{p} ({scan.age_text(int(p.stat().st_mtime))})" for p in found[:3]) if found
                                else "none yet (open the auction house in game and click Save Prices)"))
    print(f"State folder:   {settings.STATE}")
    if os.name == "nt" or sys.platform == "darwin":
        from .app import hands
        on = hands().startup_on()
        old = os.name == "nt" and (startup_dir() / f"{settings.NAME} Helper.cmd").exists()
        print("At login:       " + ("the app starts" if on else "nothing (python fwch.py autostart, or the icon's menu)")
              + (" (and the old send.cmd entry is still there; the app removes it)" if old else ""))
    if not (base / flav).is_dir():
        print("\nSet FWC_WOW_DIR to the World of Warcraft folder and FWC_WOW_FLAVOR to the client folder "
              "(_forever_), or start the app and choose the game folder from the icon's menu.")


def install_addon(addons_dir: Path | None = None, force: bool = False) -> Path:
    """Copy the scanner and the plans addon into the AddOns folder (`addons_dir`, else the game's) and say
    what was done; a newer scanner already there is left as it is unless `force`. Returns where the scanner is."""
    root = addons_dir or scan.addons_dir()
    had_old = addons_dir is None and (root / settings.OLD_ADDON_NAME).is_dir()
    have, mine = scan.toc_version(root / scan.ADDON_NAME, scan.ADDON_NAME), scan.toc_version(settings.ADDON_SOURCE / scan.ADDON_NAME, scan.ADDON_NAME)
    dest = scan.install_addon(addons_dir, force)
    if had_old:
        print(f"Removed the addon under its old name ({settings.OLD_ADDON_NAME}); its saved scans were carried over.")
        print("The game has to be restarted, not only reloaded, to see an addon under a new name.")
    dotted = lambda v: ".".join(str(x) for x in v)   # noqa: E731
    if have and mine and have > mine and not force:
        print(f"Left {settings.NAME} Scanner as it is in {dest}: the one installed ({dotted(have)}) is newer than this helper's "
              f"({dotted(mine)}). --force puts this helper's in anyway.")
    else:
        print(f"Installed {settings.NAME} Scanner to {dest}")
    print(f"Installed {settings.NAME} Plans beside it, {scan.plans_addon_dir(root)}: what the helper fetches goes there, "
          "and stays through an update of the scanner.")
    print("Restart the game or /reload so they load.")
    return dest


def status(path: Path | None = None, realm: str | None = None, faction: str | None = None) -> None:
    """Print what the addon's saved scans hold: the auction houses, items and auctions, and the characters seen."""
    sd = scan.load_scan(path, realm, faction)
    done = [it for it in sd.items.values() if it.complete]
    listed = [it for it in done if it.listings]
    held = scan.datasets(sd.path) if sd.path.suffix == ".lua" else []
    if len(held) > 1:
        print("the file holds: " + ", ".join(f"{scan.dataset_name(r, f)} ({n} items, {scan.age_text(t)})" for r, f, n, t in held))
    print(f"{sd.path}\n{sd.dataset}   items: {len(done)} scanned, {len(listed)} with auctions, "
          f"{sum(len(it.listings) for it in listed):,} auctions   records: {sd.age_range()}")
    skipped = len(sd.items) - len(done)
    if skipped:
        print(f"skipped by the addon: {skipped}")
    chars = plansmod.characters(sd.path) if sd.path.suffix == ".lua" else []
    if chars:
        print("characters: " + ", ".join(f"{c['name']} ({c['realm']}, {len(c['items'])} kinds of item, seen {scan.age_text(c['t'])})"
                                         for c in chars))


# ---- a window that stays open -----------------------------------------------------------------
class Stamped:
    """Standard output with the time at the start of every line, `2026-09-30 14:05:09  text`,
    for a loop whose window is looked at now and then: the last line says how old it is. Empty
    lines are left empty. What another program writes to the window (a deploy) is not stamped."""

    def __init__(self, out):
        self.out, self.at_start = out, True

    def write(self, text: str) -> int:
        """Write the text, the time first at the start of each line that is not empty, the game account's folder name redacted."""
        from . import tray
        for line in text.splitlines(keepends=True):
            if self.at_start and line.strip():
                self.out.write(now() + "  ")
            self.out.write(tray.redact(line))
            self.at_start = line.endswith("\n")
        return len(text)

    def __getattr__(self, name):
        return getattr(self.out, name)


def now() -> str:
    """The local date and time, year first: 2026-09-30 14:05:09."""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def stamp_lines() -> None:
    """From here on, every line this process prints starts with the time it was printed at."""
    sys.stdout.reconfigure(line_buffering=True)      # each line as soon as it is written, even when piped
    if not isinstance(sys.stdout, Stamped):
        sys.stdout = Stamped(sys.stdout)


# ---- the pipe ---------------------------------------------------------------------------------
def _sent_file() -> Path:
    return settings.STATE / "sent.json"


class Refused(pipemod.PipeError):
    """Some auction houses of a file were not sent; each was reported as it happened. Raised
    after the rest were sent, so a watch tries again the way it does for any refusal."""

    def __init__(self, errors: list):
        super().__init__(f"{len(errors)} auction house{'s' if len(errors) > 1 else ''} not sent")
        self.errors = errors


def send_once(p: pipemod.Pipe, path: Path | None = None, realm: str | None = None, faction: str | None = None,  # noqa: C901 - baseline 9 Nov 2026, to be split
              again: bool = False, fresh: dict | None = None) -> bool:
    """Send what the scan file holds and was not sent already: every auction house in it, or
    the one of `realm` and `faction`. `fresh` is what the pipe last said of the houses
    (fwchelper/fresh.py): a scan it would refuse as not needed is not sent. Returns whether
    anything was sent."""
    if realm is None and faction is None:
        file = path or (scan.find_saved_variables() or [None])[0]
        held = scan.datasets(file) if file and file.suffix == ".lua" else []
        if len(held) > 1:               # each on its own: one the service refuses does not hold the others back
            done, refused = False, []
            for r, f, _, _ in held:
                try:
                    done = send_once(p, file, r, f or "unknown", again, fresh) or done
                except pipemod.PipeError as e:
                    print(f"not sent, {scan.dataset_name(r, f)}: {e}")
                    refused.append(e)
            if refused:
                raise Refused(refused)
            return done
    sd = scan.load_scan(path, realm, faction)
    doc = pipemod.scan_document(sd)
    if not doc["items"]:
        print("nothing to send: the scan file holds no finished items")
        return False
    packed = pipemod.pack(doc)
    mark = pipemod.mark(doc)
    sent = json.loads(_sent_file().read_text(encoding="utf-8")) if _sent_file().exists() else {}
    if sent.get(sd.dataset) == mark and not again:
        print(f"already sent: {sd.dataset}, scanned {scan.age_text(doc['scanned_at'])}")
        return False

    def noted() -> None:
        settings.STATE.mkdir(parents=True, exist_ok=True)
        sent[sd.dataset] = mark
        _sent_file().write_text(json.dumps(sent), encoding="utf-8")

    # the freshness gate: the value of a scan is the auction house's, so one the pipe holds a
    # fresh scan of already is not sent (and is not asked for again: the next SAVE is new)
    newest = None if again else freshmod.not_needed(fresh, doc["realm"], doc.get("faction", ""), doc["scanned_at"])
    if newest:
        print(f"not needed: {sd.dataset} was scanned by someone {scan.age_text(newest)}; nothing sent, and nothing needs doing "
              f"(the pipe says a scan stays fresh for {freshmod.fresh_minutes(fresh)} minutes).")
        noted()
        return False
    try:
        answer = p.send_scan(doc)
    except pipemod.TooSoon as e:
        print(f"{sd.dataset}: not taken yet ({e}). It goes with the next scan.")
        return False
    except pipemod.NotNeeded as e:
        print(f"not needed: {sd.dataset} was scanned by someone {scan.age_text(e.newest) if e.newest else 'a moment ago'}; nothing sent, "
              "and nothing needs doing.")
        noted()
        return False
    noted()
    print(f"sent {sd.dataset}: {len(doc['items'])} items, scanned {scan.age_text(doc['scanned_at'])}, "
          f"{len(packed) / 1000:.0f} kB" + ("" if answer.get("new", True) else " (the service had it already)")
          + (f", as {p.name}" if getattr(p, "name", None) else ""))
    return True


def _watch_lock() -> Path:
    return settings.STATE / "watching.pid"


def _running(pid: int) -> bool:
    """Whether a process with this id is alive."""
    if os.name == "nt":                                   # os.kill(pid, 0) would end it on Windows
        # CREATE_NO_WINDOW: run from the windowless helper, a console program opens a black window of its own
        # otherwise, seen for a moment at every start
        out = subprocess.run(["tasklist", "/fi", f"PID eq {pid}", "/nh", "/fo", "csv"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def other_watcher() -> int | None:
    """The process id of another helper that is already watching, or None: then the watch is
    this process's, and noted in the state folder so the next one to start sees it."""
    lock = _watch_lock()
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = None
    if pid and pid != os.getpid() and _running(pid):
        return pid
    settings.STATE.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return None


def release_watch() -> None:
    """Remove the note that this process is the one watching, so that the next helper to start may watch."""
    _watch_lock().unlink(missing_ok=True)


def _pause(seconds: float, stop: threading.Event | None, wake: threading.Event | None = None) -> None:
    """Sleep, unless told to stop, or woken: `wake` is set by whoever wants a round now."""
    if stop is None and wake is None:
        time.sleep(seconds)
        return
    event = wake or stop
    if event.wait(seconds) and wake is not None:
        wake.clear()


def retry_wait(failures: int) -> float:
    """How long a watch waits before sending again after `failures` refusals or failures in a
    row: RETRY_FIRST (30 s), then twice that each time, up to RETRY_MAX (15 min). On 5 Nov
    2026 the pipe's day of database reads ran out at 16:30 UTC, and until midnight every
    helper with a scan asked again every 36 seconds: the pipe's own day of requests is
    not endless either."""
    return float(min(settings.RETRY_FIRST * 2 ** max(0, failures - 1), settings.RETRY_MAX))


def wait_text(seconds: float) -> str:
    """A wait in seconds as text: "2 min", or "30 s" under a minute."""
    return f"{seconds / 60:g} min" if seconds >= 60 else f"{seconds:g} s"


def failed(what: str, e: BaseException) -> None:
    """A step of the watch that failed for a reason nobody foresaw (a document the site or the pipe should never
    serve): one line with what it was, the traceback after it for the log, and the watch goes on to try again at
    its next interval. Before 1.8.0 such an error ended the watch, and with it the look for a newer helper."""
    print(f"{what} failed: {type(e).__name__}: {e}")
    print(traceback.format_exc())


def survive(what: str, do, *args, **kw):
    """`do(*args, **kw)`, or None when it raises anything but an ending (Ctrl+C, SystemExit): said by `failed`."""
    try:
        return do(*args, **kw)
    except Exception as e:  # noqa: BLE001 - whatever it was, the watch and the update check must go on
        failed(what, e)
        return None


_vendors_done: tuple | None = None      # the saved file's version (scan.file_version) whose sightings were last sent, or found sent


def send_vendors_once(p, path: Path | None = None) -> bool:
    """Send the vendors and trainers the addon has seen (scan.vendors, scan.trainers) and the
    levels the recipe scrolls asked for (scan.recipes), when they changed since they were last
    sent: one document, the union of every sighting, kept at the pipe per helper. Returns
    whether anything was sent. A saved file unchanged since its sightings were last dealt with
    is not read again (three reads of a 6 MB file took 5 s and 200 MB, every ten minutes); a
    send that failed is tried again."""
    global _vendors_done
    file = path or (scan.find_saved_variables() or [None])[0]
    version = scan.file_version(file) if file else None
    if version is not None and version == _vendors_done:
        return False
    seen = scan.vendors(file) if file and file.suffix == ".lua" else {}
    met = scan.trainers(file) if file and file.suffix == ".lua" else {}
    asked = scan.recipes(file) if file and file.suffix == ".lua" else {}
    if not seen and not met and not asked:
        _vendors_done = version
        return False
    doc = pipemod.vendors_document(seen, met, asked)
    mark = pipemod.mark_vendors(doc)
    sent = json.loads(_sent_file().read_text(encoding="utf-8")) if _sent_file().exists() else {}
    if sent.get("__vendors") == mark:
        _vendors_done = version
        return False
    answer = p.send_vendors(doc)
    settings.STATE.mkdir(parents=True, exist_ok=True)
    sent["__vendors"] = mark
    _sent_file().write_text(json.dumps(sent), encoding="utf-8")
    _vendors_done = version
    print(f"vendors sent: {len(doc['vendors'])} seen, {sum(len(v['items']) for v in doc['vendors'].values())} wares"
          + (f"; {len(met)} trainer(s), {sum(len(t['teaches']) for t in met.values())} services" if met else "")
          + (f"; {len(asked)} recipe scroll(s) with the level each asks for" if asked else "")
          + ("" if answer.get("new", True) else " (the pipe had them)"))
    return True


def send_vendors_step(p, path: Path | None) -> None:
    """The watch's send of the vendors met: a refusal or a pipe out of reach is one line, and tried again later."""
    try:
        send_vendors_once(p, path)
    except (SystemExit, pipemod.PipeError) as e:
        print(f"vendors not sent: {e}")


def watch(p: pipemod.Pipe, path: Path | None, realm: str | None, faction: str | None, interval: float = 2.0,  # noqa: C901, PLR0912 - baseline 9 Nov 2026, to be split
          stop: threading.Event | None = None, wake: threading.Event | None = None, asks: dict | None = None,
          tick=None) -> None:
    """Send after every save in game, fetch the routes and the freshness now and then, until
    `stop` is set (or, without one, Ctrl+C). `wake` cuts a pause short, and `asks` is what the
    app's menu wants done at once: {"send": True} sends the scan file as it is, {"plans": True}
    fetches the routes whether or not the site says they are new. `tick()`, when given, is
    called every round: the app's own chores (the addon put back when it is missing). The
    watch's lock is the caller's to take (other_watcher) and release (release_watch)."""
    asks = asks if asks is not None else {}
    last, looked, freshened, told, vendored = None, 0.0, 0.0, None, 0.0
    try:
        failures = 0                                 # refusals or failures in a row, for retry_wait
        while stop is None or not stop.is_set():
            if tick is not None:
                tick()
            wanted = asks.pop("plans", False)
            if wanted or time.time() - looked >= plansmod.plans_every():      # the routes the addon shows: newer ones, now and then
                looked = time.time()
                survive("routes", plans, quiet=True, again=wanted)
            if time.time() - freshened >= plansmod.fresh_every():   # when each house was last scanned, for the addon's box
                freshened = time.time()
                told = survive("freshness", freshen, p, quiet=True) or told
            if time.time() - vendored >= settings.VENDORS_EVERY:  # the vendors met, when they changed
                vendored = time.time()
                survive("vendors", send_vendors_step, p, path)
            found = [path] if path else scan.find_saved_variables()
            try:
                stamp = (found[0], found[0].stat().st_mtime, found[0].stat().st_size) if found else None
            except OSError:
                stamp = None
            asked = asks.pop("send", False)
            if asked:
                failures = 0                         # asked for by hand: now, whatever came before
            if stamp and (stamp != last or asked):
                _pause(1.5, stop)                    # let the game finish writing
                last = stamp
                try:
                    send_once(p, path, realm, faction, again=asked, fresh=told)
                    failures = 0
                except (SystemExit, Exception) as e:  # noqa: BLE001 - a scan file nobody foresaw is tried again like a refusal
                    failures += 1
                    wait = retry_wait(failures)
                    if not isinstance(e, (SystemExit, pipemod.PipeError)):
                        failed("the send", e)
                    elif not isinstance(e, Refused):           # those were reported one by one
                        print(f"not sent: {e}")
                    print(f"trying again in {wait_text(wait)}")
                    last = None                      # try again at the look after the wait
                    _pause(wait, stop, wake)
            elif asked:
                print("nothing to send: no scan file yet (open the auction house in game and click Save Prices)")
            _pause(interval, stop, wake)
    except KeyboardInterrupt:
        print("\nstopped.")


def send(path: Path | None, realm: str | None, faction: str | None, watch_it: bool, interval: float, again: bool) -> None:
    """Send the latest scan through the pipe once, or with `watch_it` after every save in game until stopped (one watching helper at a time)."""
    p = pipemod.Pipe()
    if not watch_it:
        send_once(p, path, realm, faction, again)
        return
    stamp_lines()
    other = other_watcher()
    if other:
        print(f"Another helper window is already sending (process {other}); this one is not needed.")
        return
    print(f"Sending to {p.url} after every SAVE in game. Ctrl+C to stop.")
    try:
        watch(p, path, realm, faction, interval)
    finally:
        release_watch()


# ---- starting with Windows ----------------------------------------------------------------------
def startup_dir() -> Path:
    """The folder whose contents Windows runs when the user logs on."""
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def retire_startup_entry(folder: Path | None = None) -> bool:
    """Remove the Startup-folder script that helpers before 1.5.0 wrote to start send.cmd at
    logon (the app's Run entry takes its place). Returns whether there was one."""
    entry = (folder or startup_dir()) / f"{settings.NAME} Helper.cmd"
    if not entry.exists():
        return False
    entry.unlink()
    return True


def autostart(on: bool = True, registry=None) -> str:
    """Have the app start when the user logs on to Windows: a value under the user's Run key,
    which Windows' Settings > Apps > Startup lists with a switch of its own; or, with `on`
    false, take it out. Returns the command written, or "" when taken out. `registry` is
    fwchelper/win.py, or in tests anything with its run_value, set_run_value and approve."""
    if registry is None:
        if sys.platform == "darwin":
            from . import mac
            return mac.set_startup(on)
        if os.name != "nt":
            raise SystemExit("autostart is for Windows and the Mac: elsewhere, have your session start `python fwch.py send --watch`")
        from . import win as registry
    retire_startup_entry()
    if not on:
        registry.set_run_value(tray.RUN_VALUE, None)
        return ""
    command = tray.startup_command(tray.app_exe(), settings.ROOT / "fwch.py")
    registry.set_run_value(tray.RUN_VALUE, command)
    registry.approve(tray.RUN_VALUE)                 # on, even where Windows' switch had been turned off
    return command


def whoami() -> None:
    """Print the pipe's address, the name this helper sends under and whether it is trusted."""
    p = pipemod.Pipe()
    me = p.me()
    print(f"{p.url}\nThis helper sends as {me['name']} ({me['trust']}).")
    if me["trust"] == "public":
        print("What a public sender sends is used where it agrees with what others saw of the same auction house.")


def lists(p: pipemod.Pipe | None = None) -> None:
    """Fetch the lists of items to scan from the pipe and write them as Queue.lua, in the state folder and the installed addon, in place of those there."""
    doc = (p or pipemod.Pipe()).lists()
    if doc is None:
        print("the service has no lists yet")
        return
    problem = pipemod.check_lists(doc)
    if problem:
        raise SystemExit(f"what the service sent is not usable: {problem}")
    queue = {name: [(int(i), str(n)) for i, n in rows] for name, rows in doc["queue"].items()}
    written, names = scan.write_queue(queue, replace=True, where=settings.STATE / "Queue.lua")     # kept with the helper's state, not in its source
    print(f"{len(names)} lists, {sum(len(v) for v in queue.values()):,} items, made {scan.age_text(doc['generated'])}: "
          + ", ".join(names[:4]) + (" ..." if len(names) > 4 else ""))
    for w in written:
        print(f"Wrote {w}")
    print("In game: /reload")


def freshen(p: pipemod.Pipe | None = None, quiet: bool = False) -> dict | None:
    """Ask the pipe when each auction house was last scanned by anyone and write that into
    the addon (Fresh.lua). Returns what the pipe said, or None when it could not be asked or
    is from before the gate."""
    p = p or pipemod.Pipe()
    try:
        told = p.fresh()
    except pipemod.PipeError as e:
        if not quiet:
            raise SystemExit(str(e)) from None
        print(f"the pipe could not be asked when the houses were scanned: {e}")
        return None
    if told is None:
        if not quiet:
            print(f"{p.url} does not say when the houses were scanned (a pipe from before the freshness gate): the box shows every time")
        return None
    written = freshmod.write(told)
    if not quiet:
        now = int(time.time())
        houses = told.get("houses") or {}
        for key in sorted(houses):
            h = houses[key]
            realm, _, faction = key.partition("|")
            print(f"{scan.dataset_name(realm, faction):36} scanned {scan.age_text(h['newest']) if h.get('newest') else 'never'}")
        print(f"A scan is fresh for {told.get('fresh', 600) // 60} minutes: the box is not shown while one is, and the pipe takes none it does not need. "
              f"Now {time.strftime('%H:%M', time.localtime(now))}.")
        for w in written:
            print(f"Wrote {w}")
        print("In game: /reload")
    return told


def plans(quiet: bool = False, again: bool = False) -> bool:
    """Fetch the routes of the characters' auction houses and write them into the addon.
    `quiet` is for a loop: nothing is said when nothing is new, and a site that cannot be read
    is a line, not the end. Returns whether anything was written."""
    try:
        docs, written = plansmod.refresh(force=again)
    except plansmod.PlansError as e:
        if not quiet:
            raise SystemExit(str(e)) from None
        print(f"routes not fetched: {e}")
        return False
    if not written:
        if not quiet:
            print(f"nothing new at {plansmod.site_url()}: the addon has the routes of "
                  + (", ".join(sorted(plansmod.stamps())) or "no auction house (none of your characters' is on the site yet)"))
        return False
    def told(d: dict) -> str:
        also = f", {len(d['also'])} with a second profession" if d.get("also") else ""
        return f"{scan.dataset_name(d.get('realm') or d['house'], d.get('faction', ''))} ({len(d['plans'])} routes{also}, scanned {plansmod.age(d)})"
    print("routes for the addon's /fwc window: " + (", ".join(told(d) for d in docs)
                                                    or "none: no auction house of your characters is on the site yet"))
    if not quiet:
        for w in written:
            print(f"Wrote {w}")
    print("In game: /reload, then /fwc" if not quiet else "They show after the next SAVE, /reload or login.")
    return True


def main(argv=None) -> None:  # noqa: C901, PLR0912, PLR0915 - command dispatch: one branch per subcommand, after its parser
    """The helper's command line: parse `argv` (the process's arguments when None) and run the command it names."""
    ap = argparse.ArgumentParser(prog="fwch", description=f"{settings.NAME} Helper {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("where", help="show the detected WoW folder, client flavour, AddOns folder and scan files")
    p = sub.add_parser("install-addon", help="copy the two addons into the WoW AddOns folder")
    p.add_argument("--addons-dir", help="another AddOns folder")
    p.add_argument("--force", action="store_true", help="put this helper's scanner in even over a newer one (CurseForge's)")
    p = sub.add_parser("status", help="what the addon's saved scans hold")
    p.add_argument("--path", help="a scan file (default: the newest found)")
    p.add_argument("--realm")
    p.add_argument("--faction", help="Alliance or Horde (default: every auction house the file holds)")
    p = sub.add_parser("send", help="send the latest scan through the pipe")
    p.add_argument("--watch", action="store_true", help="send after every SAVE in game (Ctrl+C to stop)")
    p.add_argument("--interval", type=float, default=2.0, metavar="SEC", help="how often --watch looks at the file")
    p.add_argument("--again", action="store_true", help="send even what was sent already")
    p.add_argument("--path", help="a scan file (default: the newest found)")
    p.add_argument("--realm")
    p.add_argument("--faction", help="Alliance or Horde (default: every auction house the file holds)")
    p = sub.add_parser("app", help="run as an application: an icon by the clock (Windows) or in the menu bar (Mac), no window; sends, fetches, installs the addon")
    p.add_argument("--identity", action="store_true", help="(Mac) print the bundle macOS knows this process by and start nothing; fails unless it is the helper's")
    p = sub.add_parser("autostart", help="have the app start when you log in")
    p.add_argument("--off", action="store_true", help="undo that")
    sub.add_parser("lists", help="fetch the lists from the pipe and write them into the addon")
    p = sub.add_parser("plans", help="fetch the routes of your characters' auction houses and write them into the addon")
    p.add_argument("--again", action="store_true", help="write them even when the site has nothing newer")
    sub.add_parser("whoami", help="the name this helper sends under, and whether it is trusted")
    sub.add_parser("fresh", help="when each auction house was last scanned by anyone; written into the addon, which shows no scan box while that is fresh")
    a = ap.parse_args(argv)
    settings.carry_state()                           # an install from before 1.5.0 kept its state beside the helper
    try:
        if a.cmd == "where":
            where()
        elif a.cmd == "install-addon":
            install_addon(Path(a.addons_dir) if a.addons_dir else None, a.force)
        elif a.cmd == "status":
            status(Path(a.path) if a.path else None, a.realm, a.faction)
        elif a.cmd == "send":
            send(Path(a.path) if a.path else None, a.realm, a.faction, a.watch, a.interval, a.again)
        elif a.cmd == "app" and a.identity:
            if sys.platform != "darwin":
                raise SystemExit("--identity is the Mac's: the bundle macOS knows the helper by")
            from . import mac
            sys.exit(mac.identity_check())
        elif a.cmd == "app":
            from . import app
            app.run()
        elif a.cmd == "autostart":
            command = autostart(not a.off)
            switch = "System Settings > General > Login Items" if sys.platform == "darwin" else "Settings > Apps > Startup"
            print("The app no longer starts when you log in." if a.off
                  else f"The app starts when you log in ({switch} has a switch for it):\n  {command}")
        elif a.cmd == "lists":
            lists()
        elif a.cmd == "plans":
            plans(again=a.again)
        elif a.cmd == "whoami":
            whoami()
        elif a.cmd == "fresh":
            freshen()
    except pipemod.PipeError as e:
        raise SystemExit(str(e)) from None
