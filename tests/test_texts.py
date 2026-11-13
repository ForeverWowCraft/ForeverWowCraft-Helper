"""What the addon says of itself is true (1.8.0): the /fwcs help names the player commands that exist, no line
asks a player with the tray helper to run fwch.py, the finish alert says no "pulsing bar" (hidden unless switched
on), the options page does not say every switch has a command, and the .toc names the Make button."""
import re
from pathlib import Path

ADDON = Path(__file__).resolve().parent.parent / "addon" / "ForeverWowCraftScanner"
LUA = (ADDON / "ForeverWowCraftScanner.lua").read_text(encoding="utf-8")


def test_the_help_names_the_commands_that_exist():
    help_line = next(line for line in LUA.splitlines() if "Commands: /fwcs full" in line)
    named = set(re.findall(r"\| (\w+)", help_line.split("Commands: /fwcs", 1)[1].split(".", 1)[0]))
    handled = set(re.findall(r'cmd == "(\w+)"', LUA))
    assert named <= handled, named - handled
    assert {"remind", "offer", "plan"} <= named


def test_no_text_asks_for_fwch_py_or_promises_what_is_not_so():
    shown = re.findall(r'"[^"\n]*"', LUA)
    assert not [s for s in shown if "fwch.py" in s]
    assert "pulsing bar" not in LUA
    assert "Each switch here has a command" not in (ADDON / "Background.lua").read_text(encoding="utf-8")
    toc = (ADDON / "ForeverWowCraftScanner.toc").read_text(encoding="utf-8")
    assert "The Make button" in toc and "FWC button" not in toc


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
