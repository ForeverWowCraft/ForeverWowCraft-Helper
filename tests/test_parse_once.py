"""The helper does not parse a file again while it is unchanged: the saved file for the sightings (three parses
of a 6 MB file every ten minutes before 1.8.0) and Plans.lua for the houses it holds (once for every line of the
app's log)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, luatable, pipe, plans, settings  # noqa: E402
from test_plans import document  # noqa: E402
from test_vendors import SAVED, FakePipe, _saved  # noqa: E402


class Counted:
    """luatable.parse, counting its calls."""

    def __init__(self):
        self.calls, self.parse = 0, luatable.parse

    def __call__(self, text):
        self.calls += 1
        return self.parse(text)


def test_an_unchanged_saved_file_is_not_parsed_again_for_the_sightings():
    kept = settings.STATE, luatable.parse
    settings.STATE = Path(tempfile.mkdtemp())
    luatable.parse = counted = Counted()
    try:
        f, p = _saved(), FakePipe()
        assert cli.send_vendors_once(p, f) is True and counted.calls == 3              # vendors, trainers, recipes
        for _ in range(3):
            assert cli.send_vendors_once(p, f) is False
        assert counted.calls == 3 and len(p.sent) == 1                                   # unchanged: not parsed, not sent
        f.write_text(SAVED.replace('["n"] = 1,', '["n"] = 0,'), encoding="utf-8")       # the same size, at once: still a change
        assert cli.send_vendors_once(p, f) is True and counted.calls == 6 and len(p.sent) == 2
        # a send that fails is tried again at the next look, though the file has not changed
        f.write_text(SAVED.replace('["n"] = 1,', '["n"] = 2,'), encoding="utf-8")

        class Down(FakePipe):
            def send_vendors(self, doc):
                raise pipe.PipeError("the pipe could not be reached")
        try:
            cli.send_vendors_once(Down(), f)
            raise AssertionError("no error")
        except pipe.PipeError:
            pass
        assert cli.send_vendors_once(p, f) is True and len(p.sent) == 3 and counted.calls == 12
        assert cli.send_vendors_once(p, f) is False and counted.calls == 12
    finally:
        settings.STATE, luatable.parse = kept


def test_plans_lua_is_parsed_once_for_each_version():
    kept = settings.STATE, luatable.parse
    settings.STATE = Path(tempfile.mkdtemp())
    settings.STATE.mkdir(parents=True, exist_ok=True)
    plans.kept_file().write_text(plans.plans_text([document(generated=100)], "test"), encoding="utf-8")
    luatable.parse = counted = Counted()
    try:
        for _ in range(5):
            assert plans.stamps() == {"stonespine--horde": 100}
        assert counted.calls == 1
        got = plans.stamps()
        got["mine"] = 1                                                                   # what a caller does with it stays its own
        assert plans.stamps() == {"stonespine--horde": 100} and counted.calls == 1
        plans.kept_file().write_text(plans.plans_text([document(generated=200)], "test"), encoding="utf-8")     # the same size, at once
        assert plans.stamps() == {"stonespine--horde": 200} and counted.calls == 2
        plans.kept_file().unlink()
        assert plans.stamps() == {}
    finally:
        settings.STATE, luatable.parse = kept


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
