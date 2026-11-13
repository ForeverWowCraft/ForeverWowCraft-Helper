"""The files the helper writes into the game's folder (Plans.lua, Fresh.lua, Queue.lua) are written whole or
not at all: a write that fails leaves the file the game had, and no temporary file beside it."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import fresh, plans, scan, settings  # noqa: E402
from test_plans import document  # noqa: E402

OLD = "-- the file the game had\nFWCS_PLANS_WRITTEN = 5\nFWCS_PLANS = {}\n"


def _folders():
    """A state folder and an installed Plans addon, each holding OLD in every file the helper writes."""
    state, game = Path(tempfile.mkdtemp()) / "state", Path(tempfile.mkdtemp())
    for folder in (state, game / scan.PLANS_ADDON):
        folder.mkdir(parents=True)
        for name in scan.HELPER_FILES:
            (folder / name).write_text(OLD, encoding="utf-8")
    return state, game


def _left(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name not in scan.HELPER_FILES)


def test_a_write_that_fails_leaves_the_file_as_it_was():
    state, game = _folders()
    kept = settings.STATE, scan.addons_dir, os.replace
    settings.STATE, scan.addons_dir = state, (lambda: game)

    def held(src, dst):                      # Windows, while the game holds the file open
        raise PermissionError(13, "The process cannot access the file because it is being used by another process")
    os.replace = held
    try:
        writes = [lambda: plans.write([document()], "https://example.org"),
                  lambda: fresh.write({"fresh": 600, "houses": {"Stonespine|Horde": {"newest": 1789999000}}}),
                  lambda: scan.write_queue({"Tailoring": [(2589, "Linen Cloth")]}, replace=True, where=state / "Queue.lua")]
        for write in writes:
            try:
                write()
                raise AssertionError("no error")
            except PermissionError:
                pass
        plans.touch()                        # touch and note_problem say nothing of a file they cannot write, as before
        plans.note_problem("reach")
    finally:
        settings.STATE, scan.addons_dir, os.replace = kept
    for folder in (state, game / scan.PLANS_ADDON):
        assert all((folder / name).read_text(encoding="utf-8") == OLD for name in scan.HELPER_FILES)
        assert _left(folder) == [], _left(folder)                                    # no temporary file left


def test_text_that_cannot_be_encoded_writes_nothing():
    state, _ = _folders()
    try:
        scan.write_whole(state / "Plans.lua", "FWCS_PLANS = {'\ud800'}")
        raise AssertionError("no error")
    except UnicodeEncodeError:
        pass
    assert (state / "Plans.lua").read_text(encoding="utf-8") == OLD and _left(state) == []


def test_a_write_that_works_replaces_the_file_whole():
    state, game = _folders()
    kept = settings.STATE, scan.addons_dir
    settings.STATE, scan.addons_dir = state, (lambda: game)
    try:
        written = plans.write([document()], "https://example.org")
        assert written == [state / "Plans.lua", game / scan.PLANS_ADDON / "Plans.lua"]
        assert all("stonespine--horde" in f.read_text(encoding="utf-8") for f in written)
        assert plans.stamps() == {"stonespine--horde": document()["generated"]}
        fresh.write({"fresh": 600, "houses": {}})
        assert "FWCS_FRESH" in (state / "Fresh.lua").read_text(encoding="utf-8")
        assert _left(state) == [] and _left(game / scan.PLANS_ADDON) == []
    finally:
        settings.STATE, scan.addons_dir = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
