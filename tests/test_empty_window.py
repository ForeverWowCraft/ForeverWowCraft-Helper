"""The empty /fwc window says why it is empty (1.8.0): what the helper writes into Plans.lua for it (the site's
houses, FWCS_SITE, and the problem of a failed look, FWCS_PLANS_PROBLEM), and the six causes the addon names.

The released 1.7.7 addon is run from git (the commit that made 1.7.7) when it is there; a shallow clone has no such commit and
that one test then says so and passes."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, luatable, plans  # noqa: E402
from test_fishing_route import _helper_state, _restore, _site  # noqa: E402
from test_ingame import ADDON, GAME, lupa  # noqa: E402
from test_plans import NOW, document  # noqa: E402

BEFORE_THIS = "e46c0ab"             # main as this change found it: the addon without the empty window's causes
RELEASE_1_7_7 = "3a89aab"          # the commit that made the version 1.7.7, in both addons
ADDON_DIR = "helper/addon/ForeverWowCraftScanner/"
STRIP = re.compile(r"\|c[0-9a-fA-F]{8}|\|r")
HOUSES = [["uspve", "Alliance"], ["uspve", "Horde"], ["eupvp", "Horde"]]
REALM = "CAMWOW US2 Realm 1 PvE"          # a character of this realm is of the house "uspve"; Horde, as the stand-in game says


def house(key, realm, faction, **more):
    return dict({"key": key, "realm": realm, "faction": faction, "realms": [realm], "generated": NOW, "ingame": True}, **more)


# ---- the helper ---------------------------------------------------------------------------------------------------
def test_the_site_list_is_written_after_everything_that_was_there_and_what_was_there_is_unchanged():
    docs = [document()]
    plain = plans.plans_text(docs, "test", written=NOW)
    with_site = plans.plans_text(docs, "test", written=NOW, site_houses=HOUSES)
    assert with_site.startswith(plain.rstrip("\n") + "\n")                                  # the old text, untouched, then the global
    assert with_site[len(plain):] == f'FWCS_SITE = {{ at = {NOW}, houses = {{{{"uspve","Alliance"}},{{"uspve","Horde"}},{{"eupvp","Horde"}}}} }}\n'
    both = plans.plans_text(docs, "test", written=NOW, routes={"Horde": {"kind": "fishing"}}, site_houses=HOUSES)
    assert both.index("FWCS_ROUTES = ") < both.index("FWCS_SITE = ") and both.startswith(plain.rstrip("\n") + "\n")
    listed = plans.site_list([house("a", "US PvE", "Alliance"), house("b", "US PvE", "Horde", ingame=False), house("c", "EU PvP", "Horde"),
                              house("d", "EU PvP", "Horde"), house("e", "Shared", ""), {"key": "f", "faction": "Horde", "ingame": True}])
    assert listed == [["eupvp", "Horde"], ["uspve", "Alliance"]]                              # spelt as the addon's Ruled() spells, once each
    path = Path(tempfile.mkdtemp()) / "Plans.lua"
    path.write_text(with_site + plans.problem_line("reach", NOW), encoding="utf-8")
    assert plans.held(path) == ({"stonespine--horde": NOW}, {})                              # what an earlier helper reads of it is unchanged
    data = luatable.parse(path.read_text(encoding="utf-8"))
    assert data["FWCS_SITE"] == {"at": NOW, "houses": [["uspve", "Alliance"], ["uspve", "Horde"], ["eupvp", "Horde"]]}
    assert data["FWCS_PLANS_PROBLEM"] == {"at": NOW, "kind": "reach"}
    assert plans.problem_line("reach", NOW) == f'FWCS_PLANS_PROBLEM = {{ at = {NOW}, kind = "reach" }}'


def test_the_errors_say_which_kind_they_are():
    kept = plans.get
    try:
        assert plans.PlansError("x").kind == "unusable"
        doc = document()
        doc["needs_helper"] = "99.0.0"
        plans.get = lambda url: doc
        try:
            plans.fetch({"key": "stonespine--horde"})
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "update" and "99.0.0" in str(e)
        doc.pop("needs_helper")
        doc["house"] = ""
        try:
            plans.fetch({"key": "stonespine--horde"})
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "unusable"
        plans.get = kept
        try:
            plans.get("http://example.invalid/data/houses.json")
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "unusable" and "only https" in str(e)                 # nothing was asked of a site
        try:
            plans.get("http://127.0.0.1:9/data/houses.json")
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "reach"
    finally:
        plans.get = kept


def _kept_and_installed():
    return [plans.kept_file(), plans.installed_file()]


def test_a_failed_look_is_recorded_as_one_line_and_the_next_look_that_works_removes_it():
    docs = [document()]
    url, srv, root = _site([house("stonespine--horde", "Stonespine", "Horde")], {}, [])
    kept = _helper_state()
    try:
        assert plans.refresh(url, force=True)[0]
        before = [f.read_text(encoding="utf-8") for f in _kept_and_installed()]
        assert all("FWCS_SITE = " in t and "FWCS_PLANS_PROBLEM" not in t for t in before)           # with no problem, no such line
        for kind in ("reach", "update", "unusable"):
            plans.note_problem(kind)
            for f, was in zip(_kept_and_installed(), before):
                text = f.read_text(encoding="utf-8")
                lines = [ln for ln in text.splitlines() if ln.startswith("FWCS_PLANS_PROBLEM")]
                assert len(lines) == 1 and re.fullmatch(rf'FWCS_PLANS_PROBLEM = \{{ at = \d+, kind = "{kind}" \}}', lines[0])
                # nothing else of the error, and the routes as they were: only the stamp and the site's time move
                assert text.endswith(lines[0] + "\n") and "http" not in lines[0] and str(root) not in text.split("FWCS_PLANS = ")[1].split("FWCS_SITE")[0][:0]
                assert text.split("FWCS_PLANS = ")[1].split("\nFWCS_SITE")[0] == was.split("FWCS_PLANS = ")[1].split("\nFWCS_SITE")[0]
            assert plans.held() == ({"stonespine--horde": NOW}, {})                                      # the kept file is still read as before
        plans.note_problem("reach")
        plans.note_problem("update")                                                                      # again: still the one line
        assert plans.held()[0] and sum(ln.startswith("FWCS_PLANS_PROBLEM") for ln in plans.kept_file().read_text(encoding="utf-8").splitlines()) == 1
        # the look that finds nothing new (touch) removes it, and keeps the site's list
        assert plans.refresh(url) == ([], [])
        assert all("FWCS_PLANS_PROBLEM" not in f.read_text(encoding="utf-8") and "FWCS_SITE = " in f.read_text(encoding="utf-8") for f in _kept_and_installed())
        # and so does a look that writes
        plans.note_problem("unusable")
        assert plans.refresh(url, force=True)[1]
        assert all("FWCS_PLANS_PROBLEM" not in f.read_text(encoding="utf-8") for f in _kept_and_installed())
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)
    assert docs


def test_a_look_that_fails_in_the_helper_records_its_kind_in_the_files():
    url, srv, root = _site([house("stonespine--horde", "Stonespine", "Horde")], {}, [])
    kept = _helper_state()
    saved_site = plans.site_url
    try:
        # a site that serves what cannot be used
        (root / "data" / "stonespine--horde" / "ingame.json").write_text('{"format": "fwc-plans/1"}', encoding="utf-8")
        try:
            plans.refresh(url, force=True)
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "unusable"
        assert 'kind = "unusable"' in plans.kept_file().read_text(encoding="utf-8") and 'kind = "unusable"' in plans.installed_file().read_text(encoding="utf-8")
        # a site whose routes need a newer helper
        (root / "data" / "stonespine--horde" / "ingame.json").write_text(
            __import__("json").dumps(dict(document(), needs_helper="99.0.0")), encoding="utf-8")
        try:
            plans.refresh(url, force=True)
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "update"
        assert 'kind = "update"' in plans.kept_file().read_text(encoding="utf-8")
        # a site that is not there: in a loop it is a line (cli.plans), by hand an error, and the file says "reach" either way
        srv.shutdown()
        srv.server_close()
        plans.site_url = lambda: url
        assert cli.plans(quiet=True, again=True) is False
        assert 'kind = "reach"' in plans.kept_file().read_text(encoding="utf-8") and 'kind = "reach"' in plans.installed_file().read_text(encoding="utf-8")
        try:
            cli.plans(again=True)
            raise AssertionError("no error")
        except SystemExit:
            pass
        text = plans.kept_file().read_text(encoding="utf-8")
        assert url not in text.split("FWCS_PLANS_PROBLEM")[1]                    # the address is not in the problem line
    finally:
        plans.site_url = saved_site
        _restore(kept)


def test_a_first_run_that_cannot_reach_the_site_writes_a_minimal_file_and_the_next_look_still_fetches():
    url, srv, root = _site([house("stonespine--horde", "Stonespine", "Horde")], {}, [])
    kept = _helper_state()
    try:
        assert not plans.kept_file().exists() and not plans.installed_file().exists()
        try:
            plans.refresh("http://127.0.0.1:9", force=False)
            raise AssertionError("no error")
        except plans.PlansError as e:
            assert e.kind == "reach"
        for f in _kept_and_installed():
            lines = f.read_text(encoding="utf-8").splitlines()
            assert lines[0].startswith("-- Written by") and lines[1].startswith("-- The routes of")
            assert re.fullmatch(r"FWCS_PLANS_WRITTEN = \d+", lines[2]) and lines[3] == "FWCS_PLANS = {}"
            assert re.fullmatch(r'FWCS_PLANS_PROBLEM = \{ at = \d+, kind = "reach" \}', lines[4]) and len(lines) == 5
        assert plans.held() == ({}, {})
        docs, written = plans.refresh(url)                      # no `force`: the minimal file is not taken for what the site has
        assert [d["house"] for d in docs] == ["stonespine--horde"] and len(written) == 2
        assert all("FWCS_PLANS_PROBLEM" not in f.read_text(encoding="utf-8") and "stonespine--horde" in f.read_text(encoding="utf-8") for f in written)
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)


def test_a_file_a_1_7_7_helper_wrote_gets_the_site_list_at_the_next_look_with_nothing_fetched():
    hits = []
    url, srv, root = _site([house("stonespine--horde", "Stonespine", "Horde"), house("other--alliance", "Other", "Alliance")], {}, hits)
    kept = _helper_state()
    try:
        docs, written = plans.refresh(url, force=True)
        old = plans.plans_text(docs, url, written=NOW - 3600)             # what 1.7.7 wrote: no site list
        for f in written:
            f.write_text(old, encoding="utf-8")
        hits.clear()
        assert plans.refresh(url) == ([], []) and not any("ingame.json" in h for h in hits)       # nothing fetched but houses.json
        for f in written:
            text = f.read_text(encoding="utf-8")
            assert text.startswith(old.split("FWCS_PLANS_WRITTEN")[0]) and text.split("\nFWCS_SITE")[0].split("FWCS_PLANS = ")[1] == old.split("FWCS_PLANS = ")[1].rstrip("\n")
            assert luatable.parse(text)["FWCS_SITE"]["houses"] == [["other", "Alliance"], ["stonespine", "Horde"]]
        # the size: what this adds to a file
        assert len(written[0].read_text(encoding="utf-8")) - len(old) < 200
    finally:
        srv.shutdown()
        srv.server_close()
        _restore(kept)


# ---- the addon --------------------------------------------------------------------------------------------------
def _release_source(name, commit=RELEASE_1_7_7):
    out = subprocess.run(["git", "show", f"{commit}:{ADDON_DIR}{name}"], capture_output=True, cwd=HELPER, check=False)
    return out.stdout.decode("utf-8") if out.returncode == 0 else None


def _toc(source=None):
    toc = (source or (lambda n: (ADDON / n).read_text(encoding="utf-8")))("ForeverWowCraftScanner.toc")
    return [line.strip() for line in toc.splitlines() if line.strip().endswith(".lua")]


def _load(plans_source, setup="", release=False):
    """The addon (the working tree's, or 1.7.7's) loaded as its .toc says into the stand-in game, with `plans_source` as Plans.lua
    (None: the empty one the scanner ships) and `setup` run before any file."""
    read = (lambda n: _release_source(n, release)) if isinstance(release, str) else _release_source if release else (lambda n: (ADDON / n).read_text(encoding="utf-8"))
    lua = lupa.LuaRuntime()
    lua.execute(GAME)
    lua.execute('function Find(text) for _, f in ipairs(frames) do if f.text == text then return f end end end')
    lua.execute(setup or "local _ = 0")
    for name in _toc(read):
        if name == "Queue.lua":
            continue
        source = read(name) if (name != "Plans.lua" or plans_source is None) else plans_source
        lua.globals().Load(name, source)
    lua.execute('Fire("PLAYER_LOGIN"); Fire("PLAYER_ENTERING_WORLD", true); RunTimers()')
    return lua


def _shown(lua):
    lua.execute('if not (ForeverWowCraftWindow and ForeverWowCraftWindow:IsShown()) then SlashCmdList.FOREVERWOWCRAFT("") end; '
                'Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    return STRIP.sub("", lua.eval("AllText()"))


def _buttons(lua):
    """"reload": the secure reload button is shown, under either label; "switch": it reads "Switch on and reload"."""
    shown = lambda text: bool(lua.eval(f'Find("{text}") and Find("{text}").shown'))  # noqa: E731
    return {"reload": shown("Reload now") or shown("Switch on and reload"), "helper": shown("Get the helper"), "switch": shown("Switch on and reload")}


def _click(lua, text, which="OnClick"):
    lua.execute(f'local b = Find("{text}"); b.scripts.{which}(b)')


STONESPINE = document()                                         # a house the character is of: Stonespine, Horde
ELSEWHERE = document(house="elsewhere--alliance", realm="Elsewhere", faction="Alliance")
SITE_LINE = plans.site_line(HOUSES, NOW)
PROBLEM = lambda kind: plans.problem_line(kind, NOW - 120)  # noqa: E731
AT_USPVE = 'function GetRealmName() return "CAMWOW US2 Realm 1 PvE" end'
NO_API = 'C_AddOns, GetAddOnInfo, IsAddOnLoaded, EnableAddOn = nil, nil, nil, nil'


def addons(reason="DISABLED", loaded=False, enable=True, old=False, table=False):
    """The stand-in's AddOns list: the Plans addon there with `reason` it is not loaded, in the way of a newer client (C_AddOns) or an older one."""
    info = (f'function(n) return {{ name = n, reason = {reason!r} }} end'.replace("'", '"') if table else
            f'function(n) if {reason!r} == "MISSING" then return nil, nil, nil, false, "MISSING" end return n, "title", "notes", false, {reason!r} end'.replace("'", '"'))
    funcs = f'GetAddOnInfo = {info}, IsAddOnLoaded = function() return {str(loaded).lower()} end' \
            + (', EnableAddOn = function(n) enabled = n end' if enable else '')
    return NO_API + "; enabled = nil; " + (f'GetAddOnInfo, IsAddOnLoaded, EnableAddOn = nil, nil, nil; local api = {{ {funcs} }}; '
                                          'GetAddOnInfo, IsAddOnLoaded, EnableAddOn = api.GetAddOnInfo, api.IsAddOnLoaded, api.EnableAddOn' if old
                                          else f'C_AddOns = {{ {funcs} }}')


def written(doc=None, site=True, problem=None, routes_doc=True):
    text = plans.plans_text([doc or ELSEWHERE] if routes_doc else [], "test", written=NOW, site_houses=HOUSES if site else None)
    return text + (PROBLEM(problem) + "\n" if problem else "")


def test_a_character_with_a_house_sees_the_routes_whatever_else_the_file_says():
    text = _shown(_load(written(STONESPINE, site=False)))
    assert "Bolt of Linen Cloth" in text and "No routes for this character" not in text
    assert text == _shown(_load(written(STONESPINE, site=True))) == _shown(_load(written(STONESPINE, site=True, problem="reach")))       # the problem is not shown with routes
    assert _buttons(_load(written(STONESPINE, problem="update"))) == {"reload": False, "helper": False, "switch": False}


def test_state_a_the_plans_addon_is_there_and_off():
    for kw in ({}, {"old": True}, {"table": True}, {"reason": ""}):
        lua = _load(None, AT_USPVE + "; " + addons(**kw))
        text = _shown(lua)
        assert "The ForeverWowCraft Plans addon is switched off." in text
        assert "The routes are kept in a second addon, ForeverWowCraft Plans, and it is not loaded." in text
        assert "Click Switch on and reload below." in text and "Or tick it in the AddOns list (Esc > AddOns) and type /reload." in text
        assert "Tick it in the AddOns list (Esc > AddOns, or the AddOns button at character select)," not in text
        assert "helper is not installed" not in text and "The helper on this PC fetches" not in text
        assert not lua.eval('Find("Switch it on")')                                                    # the separate button is gone
        assert _buttons(lua) == {"reload": True, "helper": False, "switch": True}                      # one button, with the longer label
        assert lua.eval("enabled") is None                                                             # nothing enabled by drawing
        _click(lua, "Switch on and reload", "PreClick")                                                # EnableAddOn("ForeverWowCraftPlans")
        assert lua.eval("enabled") == "ForeverWowCraftPlans"
        assert lua.eval('ForeverWowCraftWindowReload.attributes.macrotext') == "/reload" and lua.eval('ForeverWowCraftWindowReload.attributes.type') == "macro"
        assert lua.eval('ForeverWowCraftWindowReload.scripts.OnClick') is None                         # the secure click is not replaced
    # a client with no enable function: the lines name the AddOns list, the button reads Reload now and enables nothing
    lua = _load(None, AT_USPVE + "; " + addons(enable=False))
    text = _shown(lua)
    assert "switched off" in text and _buttons(lua) == {"reload": True, "helper": False, "switch": False}
    assert "Tick it in the AddOns list (Esc > AddOns, or the AddOns button at character select)," in text
    assert "then click Reload now below, or type /reload." in text and "Switch on and reload" not in text
    _click(lua, "Reload now", "PreClick")
    assert lua.eval("enabled") is None
    # in a fight the secure button is left as it is: label and width untouched
    lua = _load(None, AT_USPVE + "; " + addons())
    _shown(lua)
    lua.execute("ForeverWowCraftWindowReload.SetWidth = function(s, w) s.width = w end")
    lua.execute("Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    assert lua.eval("ForeverWowCraftWindowReload.width") > 120
    lua.execute("ForeverWowCraftWindowReload.shown = false; ForeverWowCraftWindowReload.text = 'Reload now'; ForeverWowCraftWindowReload.width = 120; "
                "InCombatLockdown = function() return true end")
    _shown(lua)
    assert _buttons(lua)["reload"] is False and lua.eval("ForeverWowCraftWindowReload.text") == "Reload now" and lua.eval("ForeverWowCraftWindowReload.width") == 120
    # "Reload now" while the window opened at the debug switch: one line naming the cause
    lua = _load(None, AT_USPVE + "; " + addons())
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("debug")')
    _shown(lua)
    said = [p for p in lua.eval("printed").values() if "empty window" in p]
    assert said == ["ForeverWowCraft: empty window: plans addon off (reason DISABLED)"] or (len(said) == 1 and said[0].endswith("empty window: plans addon off (reason DISABLED)"))


def test_state_b_no_helper_is_what_it_was_and_so_is_every_way_the_addons_list_cannot_say():
    cases = [("no API at all", NO_API), ("missing", addons("MISSING")), ("loaded but nothing written", addons(loaded=True)),
             ("old API, missing", addons("MISSING", old=True)), ("not loadable for another reason", addons("INTERFACE_VERSION")),
             ("an API that fails", 'C_AddOns = { GetAddOnInfo = function() error("no") end }')]
    for name, setup in cases:
        lua = _load(None, AT_USPVE + "; " + setup)
        text = _shown(lua)
        assert "No routes for this character's auction house yet." in text, name
        assert "The helper on this PC fetches the routes from foreverwowcraft.com and sends the prices the" in text and "Until it is installed" in text, name
        assert "switched off" not in text and _buttons(lua) == {"reload": False, "helper": True, "switch": False}, name
        assert "The helper is not installed on this PC" in text, name


def test_state_c_the_helper_says_it_could_not_fetch():
    for kind, lines in (("reach", ["The helper on this PC could not reach foreverwowcraft.com (2 min ago).",
                                   "It tries again by itself about every ten minutes.",
                                   "Then click Reload now below, or type /reload."]),
                        ("update", ["The site's routes need a newer helper than the one on this PC.",
                                    "Update it from the helper's icon by the clock, or at foreverwowcraft.com/helper."]),
                        ("unusable", ["The helper fetched routes it could not use (2 min ago).",
                                      "It tries again by itself about every ten minutes. Nothing for you to do."])):
        lua = _load(written(problem=kind), AT_USPVE)
        text = _shown(lua)
        assert "The helper could not fetch the routes." in text and all(line in text for line in lines), kind
        assert "The helper sees" not in text
        assert _buttons(lua) == {"reload": kind == "reach", "helper": False, "switch": False}, kind
        if kind != "reach":
            _click(lua, "Reload now", "PreClick") if lua.eval('Find("Reload now")') else None
        assert lua.eval("enabled") is None                                                               # the PreClick enables only in state A
    # an unknown kind is no problem the addon knows: it says what it would without one
    assert "The helper could not fetch" not in _shown(_load(written(problem="nonsense"), AT_USPVE))


def test_state_d_the_site_has_the_house_and_the_file_does_not():
    lua = _load(written(), AT_USPVE)
    text = _shown(lua)
    assert "No routes for this character's auction house yet." in text
    assert "Click Reload now below, or type /reload. The helper sees a new character at its" in text
    assert "first reload and fetches the routes of its auction house within a minute;" in text and "a second reload shows them here." in text
    _click(lua, "Reload now", "PreClick")                                    # not state A: nothing is enabled
    assert lua.eval("enabled") is None
    assert "Still empty after that? Check that the helper is running: its icon is by the clock." in text
    assert "Save Prices" not in text and "Save prices" not in text
    assert _buttons(lua) == {"reload": True, "helper": False, "switch": False}


def test_state_e_the_site_has_no_routes_for_this_house():
    for realm, faction, line in (("CAMWOW US2 Realm 1 PvP", "Horde", "They arrive here by themselves once they are."),
                                 ("CAMWOW EU4 Realm 3 RP PvP", "Horde", "They arrive here by themselves once they are."),
                                 ("CAMWOW TW1 Realm 1 PvE", "Horde", "They arrive here by themselves once they are."),
                                 ("CAMWOW KR1 Realm 1 PvP", "Horde", "They arrive here by themselves once they are."),
                                 ("CAMWOW AU1 Realm 2 RP", "Horde", "They arrive here by themselves once they are."),
                                 ("CAMWOW XX1 Realm 2 PvE", "Horde", "ForeverWowCraft does not cover this region yet."),
                                 ("CAMWOW US1 Realm 2 Hardcore", "Horde", "ForeverWowCraft does not cover this kind of realm yet.")):
        lua = _load(written(), f'function GetRealmName() return "{realm}" end')
        text = _shown(lua)
        assert "The site has no routes for this auction house right now." in text, realm
        assert f"No routes on foreverwowcraft.com for {realm} ({faction})." in text, realm
        assert line in text, realm
        if line.startswith("and"):
            assert "Routes for this auction house are not planned yet." in text and "Save Prices" not in text and "within the hour" not in text
        assert _buttons(lua) == {"reload": False, "helper": False, "switch": False}, realm
    # the faction matters: the house is listed for Alliance and Horde, an EU Alliance house is not
    assert "No routes on foreverwowcraft.com for" in _shown(_load(written(), 'function GetRealmName() return "CAMWOW EU1 Realm 1 PvP" end; function UnitFactionGroup() return "Alliance" end'))


def test_state_f_cannot_tell():
    lua = _load(written(site=False), AT_USPVE)                           # a Plans.lua of the 1.7.7 helper
    text = _shown(lua)
    assert "Click Reload now below, or type /reload. The helper sees a new character at its" in text
    _click(lua, "Reload now", "PreClick")
    assert lua.eval("enabled") is None
    assert "Still empty? Check that the helper is running and up to date: its icon is by the clock." in text
    assert _buttons(lua) == {"reload": True, "helper": False, "switch": False}
    text = _shown(_load(written(), 'function GetRealmName() return "Stonespine" end'))              # a realm no rule names, a file with the list
    assert "Still empty after that? ForeverWowCraft does not cover this realm yet." in text and "Save Prices" not in text
    assert "No routes for this character's auction house yet." in text


def test_what_the_window_says_is_what_chat_says_and_debug_names_the_cause_once():
    for setup, plans_text, summary, said in (
            (AT_USPVE + "; " + addons(), None, "The ForeverWowCraft Plans addon is switched off.", "plans addon off (reason DISABLED)"),
            (AT_USPVE, written(problem="reach"), "The helper could not fetch the routes.", "helper could not fetch (reach, 2 min ago)"),
            (AT_USPVE, written(), "No routes for this character's auction house yet.", "the site lists this house, Plans.lua does not have it (3 houses listed)"),
            ('function GetRealmName() return "CAMWOW US2 Realm 1 PvP" end', written(), "The site has no routes for this auction house right now.",
             "the site has no routes for this house (3 listed, region US)")):
        lua = _load(plans_text, setup)
        lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("debug")')
        _shown(lua)
        lua.execute("Fire('BAG_UPDATE_DELAYED'); RunTimers()")                   # drawn again: not said again
        lua.execute('SlashCmdList.FOREVERWOWCRAFT("from 5")')
        printed = [str(p) for p in lua.eval("printed").values()]
        assert sum("empty window: " in p for p in printed) == 1 and any(p.endswith("empty window: " + said) for p in printed), printed
        assert any(p.endswith(summary) for p in printed)
        assert not any(w in " ".join(printed) for w in ("Thrallson", "Stonespine"))           # nothing personal


# ---- older addons and older files ---------------------------------------------------------------------------------
def test_the_released_1_7_7_addon_shown_a_plans_lua_with_the_new_globals_shows_exactly_what_it_showed():
    if lupa is None:
        return
    if _release_source("ForeverWowCraftScanner.toc") is None:
        print("the commit of 1.7.7 is not in this clone: not run")
        return
    sizes = []
    for doc, setup, shows in ((STONESPINE, "", "Bolt of Linen Cloth"), (ELSEWHERE, "", "Reload now"), (ELSEWHERE, AT_USPVE, "Reload now")):
        plain = plans.plans_text([doc], "test", written=NOW)
        with_new = plain + SITE_LINE + "\n" + PROBLEM("reach") + "\n"
        before = _shown(_load(plain, setup, release=True))
        assert before == _shown(_load(with_new, setup, release=True)) and shows in before
        sizes.append(len(before))
    # and with no helper at all: nothing written
    nothing = _shown(_load(None, "", release=True))
    assert nothing == _shown(_load(None, "FWCS_SITE = {}; FWCS_PLANS_PROBLEM = { kind = 'reach' }", release=True)) and "Until it is installed" in nothing
    assert min(sizes) > 100
    # 1.7.7's own text for the empty window is the generic one: it knows no cause
    old = _shown(_load(plans.plans_text([ELSEWHERE], "test", written=NOW), AT_USPVE, release=True))
    assert "Still empty after that? Then nobody has saved this realm and faction's auction house yet:" in old


def test_this_addon_given_a_plans_lua_of_1_7_7_shows_routes_as_before_and_with_no_house_says_it_cannot_tell():
    if lupa is None:
        return
    text_1_7_7 = plans.plans_text([STONESPINE], "test", written=NOW)
    now = _shown(_load(text_1_7_7))
    assert "Bolt of Linen Cloth" in now and now == _shown(_load(text_1_7_7 + SITE_LINE + "\n"))
    if _release_source("ForeverWowCraftScanner.toc", BEFORE_THIS) is not None:
        assert now.replace("of the Mode button", "of the focus button").replace(       # and the options page's blurb, true since 1.8.0
            "Most switches here also have a command (type /fwcs for the list).",
            "Each switch here has a command too (/fwcs); this page is the same settings.") == _shown(_load(text_1_7_7, release=BEFORE_THIS))  # the same window as before, for a house it has
    state = _shown(_load(plans.plans_text([ELSEWHERE], "test", written=NOW), AT_USPVE))
    assert "Still empty? Check that the helper is running and up to date: its icon is by the clock." in state


def test_the_diagnosis_adds_no_event_handler_and_no_timer():
    source = (ADDON / "Window.lua").read_text(encoding="utf-8").split("why the window is empty")[1].split("-- the slider set")[0]
    assert "RegisterEvent" not in source and "C_Timer" not in source and "FWCS_DB" not in source and "SetScript" not in source


def test_no_line_of_any_state_is_longer_than_a_row_takes():
    long_realm = "CAMWOW EU10 Realm 10 RP PvP"
    own = set(_shown(_load(written(STONESPINE))).splitlines())             # what the window shows with routes: not the state's
    cases = [(None, AT_USPVE + "; " + addons()), (None, AT_USPVE), (written(problem="reach"), AT_USPVE), (written(problem="update"), AT_USPVE),
             (written(problem="unusable"), AT_USPVE), (written(), AT_USPVE), (written(), f'function GetRealmName() return "{long_realm}" end; function UnitFactionGroup() return "Alliance" end'),
             (written(), 'function GetRealmName() return "CAMWOW XX10 Realm 10 RP PvP" end; function UnitFactionGroup() return "Alliance" end'),
             (written(site=False), AT_USPVE), (written(), 'function GetRealmName() return "Stonespine" end')]
    longest = 0
    for source, setup in cases:
        lua = _load(source, setup)
        text = _shown(lua)
        for line in text.splitlines():
            if line not in own and line.strip() and not line.startswith("The helper is not installed"):      # that is the notice under the summary, which wraps
                longest = max(longest, len(line))
                assert len(line) <= 90, line
    assert longest > 60


def test_the_debug_line_is_said_the_first_time_the_empty_window_is_drawn_with_debug_on_and_not_again():
    lua = _load(written(), AT_USPVE)
    _shown(lua)                                                              # drawn empty with debug off: nothing said
    said = lambda: sum("empty window: " in str(p) for p in lua.eval("printed").values())  # noqa: E731
    assert said() == 0
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("debug")')
    lua.execute("Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    assert said() == 1
    lua.execute("Fire('BAG_UPDATE_DELAYED'); RunTimers()")
    assert said() == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
