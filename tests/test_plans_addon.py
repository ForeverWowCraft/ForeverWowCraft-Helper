"""The helper's files in the game (the routes, the lists, the freshness) live in a second addon,
ForeverWowCraftPlans, beside the scanner: an update of the scanner from CurseForge replaces the
scanner's whole folder and touches none of them. install-addon puts both in, keeps a scanner
newer than its own (CurseForge's) unless forced, and the scanner's own copies are plain defaults."""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fwchelper  # noqa: E402
from fwchelper import cli, fresh, plans, scan, settings  # noqa: E402

SOURCE = settings.ADDON_SOURCE


def _addons() -> Path:
    addons = Path(tempfile.mkdtemp()) / "Interface" / "AddOns"
    addons.mkdir(parents=True)
    return addons


def _state(**files) -> Path:
    state = Path(tempfile.mkdtemp()) / "state"
    state.mkdir()
    for name, text in files.items():
        (state / name).write_text(text, encoding="utf-8")
    return state


def _version(text: str) -> str:
    return next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("## Version:"))


def test_both_addons_are_installed_and_the_helpers_files_go_to_the_second():
    addons = _addons()
    kept_state = settings.STATE
    settings.STATE = _state(**{"Plans.lua": "FWCS_PLANS = { kept = true }", "Fresh.lua": "FWCS_FRESH = { kept = true }"})
    try:
        dest = scan.install_addon(addons)
        second = addons / scan.PLANS_ADDON
        assert dest == addons / scan.ADDON_NAME and (dest / f"{scan.ADDON_NAME}.toc").exists()
        toc = (second / f"{scan.PLANS_ADDON}.toc").read_text(encoding="utf-8")
        assert "## Dependencies: ForeverWowCraftScanner" in toc              # so it loads after the scanner, and its tables win
        assert [line for line in toc.splitlines() if line.endswith(".lua")] == ["Plans.lua", "Fresh.lua", "Queue.lua"]
        assert (second / "Plans.lua").read_text(encoding="utf-8") == "FWCS_PLANS = { kept = true }"
        assert (second / "Fresh.lua").read_text(encoding="utf-8") == "FWCS_FRESH = { kept = true }"
        assert (second / "Queue.lua").read_bytes() == (SOURCE / scan.ADDON_NAME / "Queue.lua").read_bytes()   # the lists the helper has
        # the scanner's own copies are the plain defaults, untouched by what the helper keeps
        assert "kept" not in (dest / "Plans.lua").read_text(encoding="utf-8") and "FWCS_PLANS = {}" in (dest / "Plans.lua").read_text(encoding="utf-8")
        assert "FWCS_FRESH = {}" in (dest / "Fresh.lua").read_text(encoding="utf-8")
        assert "## Dependencies" not in (dest / f"{scan.ADDON_NAME}.toc").read_text(encoding="utf-8")   # the scanner stands alone
        # the writers aim at the second addon
        kept_dir = scan.addons_dir
        scan.addons_dir = lambda: addons
        try:
            assert plans.installed_file() == second / "Plans.lua" and fresh.installed_file() == second / "Fresh.lua"
            kept_queue = scan.queue_file
            repo = Path(tempfile.mkdtemp()) / "Queue.lua"
            scan.queue_file = lambda: repo
            try:
                targets, names = scan.write_queue({"FWC Test": [(4358, "Rough Dynamite")]})
                assert targets == [repo, second / "Queue.lua"] and names == ["FWC Test"]
                assert scan.read_queue(second / "Queue.lua") == {"FWC Test": [(4358, "Rough Dynamite")]}
            finally:
                scan.queue_file = kept_queue
        finally:
            scan.addons_dir = kept_dir
    finally:
        settings.STATE = kept_state


def test_a_newer_scanner_from_curseforge_is_left_alone_unless_forced():
    addons = _addons()
    kept_state = settings.STATE
    settings.STATE = _state()
    try:
        dest = scan.install_addon(addons)
        mine = scan.toc_version(SOURCE / scan.ADDON_NAME, scan.ADDON_NAME)
        assert mine == scan.toc_version(dest, scan.ADDON_NAME) and len(mine) == 3
        toc = (dest / f"{scan.ADDON_NAME}.toc").read_text(encoding="utf-8")
        newer = toc.replace("## Version: " + ".".join(map(str, mine)), "## Version: 99.0.0")
        assert newer != toc
        (dest / f"{scan.ADDON_NAME}.toc").write_text(newer, encoding="utf-8")
        (dest / "newer.lua").write_text("-- from CurseForge", encoding="utf-8")
        assert scan.toc_version(dest, scan.ADDON_NAME) == (99, 0, 0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.install_addon(addons)
        assert (dest / "newer.lua").exists() and scan.toc_version(dest, scan.ADDON_NAME) == (99, 0, 0)       # left as it is
        assert "Left ForeverWowCraft Scanner as it is" in out.getvalue() and "99.0.0" in out.getvalue() and "--force" in out.getvalue()
        assert (addons / scan.PLANS_ADDON / f"{scan.PLANS_ADDON}.toc").exists()                               # the second addon still brought up to date
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["install-addon", "--addons-dir", str(addons), "--force"])
        assert not (dest / "newer.lua").exists() and scan.toc_version(dest, scan.ADDON_NAME) == mine
        assert "Installed ForeverWowCraft Scanner" in out.getvalue() and "ForeverWowCraft Plans beside it" in out.getvalue()
        # an older one, or the same, is replaced
        (dest / f"{scan.ADDON_NAME}.toc").write_text(toc.replace("## Version: " + ".".join(map(str, mine)), "## Version: 0.1.0"), encoding="utf-8")
        (dest / "older.lua").write_text("", encoding="utf-8")
        scan.install_addon(addons)
        assert not (dest / "older.lua").exists() and scan.toc_version(dest, scan.ADDON_NAME) == mine
        assert scan.toc_version(addons / "nothing", scan.ADDON_NAME) is None
    finally:
        settings.STATE = kept_state


def test_the_versions_agree_and_the_addon_points_at_the_helper():
    scanner = (SOURCE / scan.ADDON_NAME / f"{scan.ADDON_NAME}.toc").read_text(encoding="utf-8")
    second = (SOURCE / scan.PLANS_ADDON / f"{scan.PLANS_ADDON}.toc").read_text(encoding="utf-8")
    assert _version(scanner) == _version(second) == fwchelper.__version__
    window = (SOURCE / scan.ADDON_NAME / "Window.lua").read_text(encoding="utf-8")
    main = (SOURCE / scan.ADDON_NAME / f"{scan.ADDON_NAME}.lua").read_text(encoding="utf-8")
    assert 'ns.HELPER_URL = "https://www.foreverwowcraft.com/helper"' in main
    assert 'Button(win, 110, "Get the helper")' in window and "function ns.ShowHelper()" in window and "ns.HELPER_URL)" in window
    assert "not FWCS_PLANS_WRITTEN" in main                                 # the login line for an install without a helper


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
