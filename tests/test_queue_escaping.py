"""Queue.lua is written with every list name and item name a quoted Lua string, whatever the pipe sent: the
file loads in Lua to exactly the lists meant and defines nothing else. The lists the addon ships with are
written as they always were, byte for byte."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import pipe, scan  # noqa: E402

try:
    from lupa import lua51 as lupa          # the game's Lua is 5.1
except ImportError:
    try:
        import lupa
    except ImportError:
        lupa = None

ODD = {
    'He said "hi"': [(4358, 'Rough "Dynamite"'), (118, "back\\slash")],
    "a]]b[[c": [(2589, "]]..os.exit()..[["), (2996, "two\nlines")],
    "--[[ not a comment": [(2320, "'single' and [=[level]=]")],
    "x\"] = {} EVIL = 1 --": [(1, "}} EVIL = 2 --")],
}


def _write(lists) -> Path:
    where = Path(tempfile.mkdtemp()) / "Queue.lua"
    kept = scan.plans_addon_dir
    scan.plans_addon_dir = lambda *a: Path(tempfile.mkdtemp()) / "no game" / "here"      # the game's copy is not written here
    try:
        scan.write_queue(lists, replace=True, where=where)
    finally:
        scan.plans_addon_dir = kept
    return where


def test_the_shipped_lists_are_written_byte_for_byte_as_before():
    shipped = scan.read_queue(scan.queue_file())
    written, ships = _write(shipped).read_bytes().split(b"\n", 1), scan.queue_file().read_bytes().split(b"\n", 1)
    assert shipped and written[1] == ships[1]                                          # the lists, byte for byte
    assert written[0] == b"-- Written by the helper from the lists the pipe serves; do not edit by hand."   # the helper's stamp


def test_odd_names_load_to_exactly_the_lists_meant():
    where = _write(ODD)
    assert scan.read_queue(where) == ODD
    if lupa is None:
        print("skipped the Lua half: no Lua here (pip install lupa)")
        return
    lua = lupa.LuaRuntime()
    before = set(lua.globals().keys())
    lua.execute(where.read_text(encoding="utf-8"))
    assert set(lua.globals().keys()) - before == {"FWCS_QUEUE"}                 # nothing else defined
    got = {name: [(row[1], row[2]) for row in rows.values()] for name, rows in lua.globals().FWCS_QUEUE.items()}
    assert got == ODD, got
    # "|" is the game's escape: written "||", which the game shows as "|", as in Plans.lua
    lua.execute(_write({"a|b": [(5, "c|d")]}).read_text(encoding="utf-8"))
    assert {n: [tuple(r.values()) for r in rows.values()] for n, rows in lua.globals().FWCS_QUEUE.items()} == {"a||b": [(5, "c||d")]}


def test_the_pipes_lists_have_names_of_at_most_80_characters():
    ok = pipe.lists_document({"FWC Alchemy": [(4358, "Rough Dynamite")]})
    assert pipe.check_lists(ok) is None
    assert "at most 80" in pipe.check_lists(dict(ok, queue={"x" * 81: [[4358, "Rough Dynamite"]]}))
    assert "at most 80" in pipe.check_lists(dict(ok, queue={"FWC Alchemy": [[4358, "y" * 81]]}))
    assert "at most 80" in pipe.check_lists(dict(ok, queue={"FWC Alchemy": [[4358, 7]]}))
    assert pipe.check_lists(dict(ok, queue={"x" * 80: [[4358, "y" * 80]]})) is None


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
