"""An install from before the project was renamed (ForeverCraft) keeps working."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import scan, settings  # noqa: E402

OLD_FILE = """
FCS_DB = {
["Test Realm"] = {
[4358] = { ["name"] = "Rough Dynamite", ["t"] = 1790000000, ["complete"] = true, ["full"] = true, ["total"] = 25,
  ["l"] = { { 79, 20 }, { 80, 5 } } },
["__history"] = { [4358] = { { 1789990000, 90, 40 }, { 1790000000, 79, 25 } } },
},
["__ui"] = { ["lastFull"] = 1790000000 },
}
"""


def _set(**values):
    """Set or clear environment variables; returns what to call to put them back."""
    before = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    return lambda: _set(**before)


def _wow():
    """A World of Warcraft folder as an old install left it: the old addon and its saved scans."""
    base = Path(tempfile.mkdtemp())
    flavour = base / settings.WOW_FLAVOR
    saved = flavour / "WTF" / "Account" / "ME" / "SavedVariables"
    addons = flavour / "Interface" / "AddOns"
    saved.mkdir(parents=True)
    (addons / settings.OLD_ADDON_NAME).mkdir(parents=True)
    (addons / settings.OLD_ADDON_NAME / "ForeverCraftScanner.toc").write_text("## Title: old", encoding="utf-8")
    (saved / f"{settings.OLD_ADDON_NAME}.lua").write_text(OLD_FILE, encoding="utf-8")
    return base, addons, saved


def test_settings_under_the_old_prefix_still_count():
    back = _set(FWC_WOW_FLAVOR=None, FC_WOW_FLAVOR="_old_", FWC_SITE_URL=None, FC_SITE_URL=None)
    try:
        assert settings.env("WOW_FLAVOR") == "_old_" and scan.flavor() == "_old_"
        os.environ["FWC_WOW_FLAVOR"] = "_new_"
        assert scan.flavor() == "_new_"                       # the new name wins
        assert settings.env("SITE_URL") is None and settings.env("SITE_URL", "x") == "x"
    finally:
        back()


def test_scans_saved_by_the_old_addon_are_read():
    base, _, saved = _wow()
    back = _set(FWC_WOW_DIR=str(base), FC_WOW_DIR=None, FWC_WOW_FLAVOR=None, FC_WOW_FLAVOR=None)
    try:
        sd = scan.load_scan()
        assert sd.path.name == "ForeverCraftScanner.lua" and sd.realm == "Test Realm"
        assert sd.items[4358].listings == [(79, 20), (80, 5)] and len(sd.history[4358]) == 2
    finally:
        back()


def test_installing_replaces_the_old_addon_and_carries_its_scans_over():
    base, addons, saved = _wow()
    back = _set(FWC_WOW_DIR=str(base), FC_WOW_DIR=None, FWC_WOW_FLAVOR=None, FC_WOW_FLAVOR=None)
    try:
        dest = scan.install_addon()
        assert dest == addons / scan.ADDON_NAME and (dest / f"{scan.ADDON_NAME}.toc").exists() and (dest / "Queue.lua").exists()
        assert not (addons / settings.OLD_ADDON_NAME).exists()          # two scanners would both run
        new = saved / f"{scan.ADDON_NAME}.lua"
        text = new.read_text(encoding="utf-8")
        assert text.lstrip().startswith("FWCS_DB = {") and "FCS_DB" not in text.replace("FWCS_DB", "")
        assert (saved / f"{settings.OLD_ADDON_NAME}.lua").read_text(encoding="utf-8") == OLD_FILE      # left as it was
        sd = scan.load_scan(new)
        assert sd.items[4358].total == 25 and len(sd.history[4358]) == 2
        # what the new addon has saved since is not overwritten by a second install
        new.write_text(text.replace("Rough Dynamite", "Newer Scan"), encoding="utf-8")
        scan.install_addon()
        assert "Newer Scan" in new.read_text(encoding="utf-8") and scan.carry_over_saved_scans() == []
    finally:
        back()


def test_the_queue_is_read_under_either_name():
    folder = Path(tempfile.mkdtemp())
    (folder / "old.lua").write_text('FCS_QUEUE = {\n  ["FC Alchemy"] = {\n    {4358, "Rough Dynamite"},\n  },\n}\n', encoding="utf-8")
    (folder / "new.lua").write_text('FWCS_QUEUE = {\n  ["FWC Alchemy"] = {\n    {4358, "Rough Dynamite"},\n  },\n}\n', encoding="utf-8")
    assert scan.read_queue(folder / "old.lua") == {"FC Alchemy": [(4358, "Rough Dynamite")]}
    assert scan.read_queue(folder / "new.lua") == {"FWC Alchemy": [(4358, "Rough Dynamite")]}


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
