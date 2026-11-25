"""The player says which kind of realm this is (addon 1.8.8). Since a hotfix of 20 Nov 2026 the game names no realm to an
addon. 1.8.6 works the name out where the account knew one realm and 1.8.7 takes it from the site once enough scanners
have said it; a player on a realm nobody like that scans from was still told the realm is not known. On Forever every
realm of one kind in a region shares one auction house, so the kind is all that is needed: `/fwc realm pve` (pvp, rp,
rppvp), kept by the realm's id, gives the house's own name ("USPvE") as the realm, the last of ns.RealmName's sources.

The addon's part needs a Lua (pip install lupa); without one those tests say so and pass."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import pipe, plans, scan  # noqa: E402
from test_no_realm import EU, ROUTES, US, US_ID, _broken, _keys, _no_lua, _snapshot  # noqa: E402

HOUSE = {"key": "uspve--horde", "realm": "US PvE", "faction": "Horde", "generated": 1, "realms": [], "ingame": True}


def _said(lua):
    return str(lua.eval("printed[#printed]"))


def test_saying_the_kind_gives_the_house_as_the_realm_where_nothing_else_tells():
    if _no_lua():
        return
    lua = _broken(realms=(US, EU))                                           # two realms known and no id: 1.8.6 and 1.8.7 cannot tell
    assert lua.eval("ns.RealmName()") is None
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm")')
    assert "the realm is not known. Say which kind you play on: /fwc realm pve | pvp | rp | rppvp" in _said(lua)
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm PvE")')                 # as typed, any case
    assert "this is a US PvE realm, you said. Type /reload" in _said(lua)
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == ("USPvE", "said") and lua.eval("ns.RealmKey()") == "USPvE"
    assert lua.eval(f"FWCS_DB.__realmkinds[{US_ID}]") == "PvE"               # kept by the realm's id: another realm's character says its own
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm")')
    assert "you said this is a realm of USPvE" in _said(lua)
    for typed, name in (("rp pvp", "USRPPvP"), ("RP-PVP", "USRPPvP"), ("rppvp", "USRPPvP"), ("rp", "USRP"), ("pvp", "USPvP")):
        lua.globals().typed = typed
        lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm " .. typed)')
        assert lua.eval("(ns.RealmName())") == name, (typed, _said(lua))
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm normal")')              # no such kind: said, and nothing changed
    assert "no such kind of realm" in _said(lua) and lua.eval("(ns.RealmName())") == "USPvP"
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm clear")')
    assert "forgotten" in _said(lua) and lua.eval("ns.RealmName()") is None and lua.eval(f"FWCS_DB.__realmkinds[{US_ID}]") is None


def test_after_the_reload_scans_characters_and_routes_are_the_houses():
    if _no_lua():
        return
    lua = _broken(realms=(US, EU), extra=f'FWCS_DB.__realmkinds = {{ [{US_ID}] = "PvE" }}')      # as saved, and read in at the next login
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == ("USPvE", "said")
    assert lua.eval('FWCS_DB.__chars["USPvE|Thrallson"].realm') == "USPvE" and lua.eval('FWCS_DB.__chars["USPvE|Thrallson"].house') == "USPvE"
    said = _snapshot(lua)
    assert lua.eval('FWCS_DB["USPvE|Horde"][2996].full') and not any("not telling the addon" in s for s in said)
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')               # the window has the house's routes (uspve--horde)
    assert "not telling the addon" not in lua.eval("AllText()") and lua.eval("ns.inv.House() ~= nil")
    # nothing of it is a realm's name: no pair of an id and a name is kept, and no name as shown
    assert lua.eval("FWCS_DB.__realmids") is None and lua.eval("FWCS_DB.__realmids_inferred") is None
    assert lua.eval('FWCS_DB.__realms["USPvE"]') is None


def test_what_the_game_the_site_or_the_account_knows_stands_over_what_was_said():
    if _no_lua():
        return
    lua = _broken()                                                          # one realm known: worked out as before
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "inferred")     # the one realm, kept for the id at login
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm pvp")')
    assert f"this realm is already known ({US}): nothing to say." in _said(lua)
    assert lua.eval("FWCS_DB.__realmkinds") is None and lua.eval("(ns.RealmName())") == US
    # said first, and the site names the id later (FWCS_REALM_IDS, 1.8.7): the site's name is the realm
    lua = _broken(realms=(US, EU), extra=f'FWCS_DB.__realmkinds = {{ [{US_ID}] = "PvP" }}; FWCS_REALM_IDS = {{ [{US_ID}] = "{US}" }}')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "helper")


def test_a_house_said_for_one_realm_is_never_worked_out_as_another_characters_realm():
    if _no_lua():
        return
    # the account's only "realm" is the house a character said, on another realm's id: this character's is not known
    saved = ('FWCS_DB = { __realmkinds = { [9999] = "PvE" }, __chars = { ["USPvE|Garosh"] = { name = "Garosh", realm = "USPvE", '
             'house = "USPvE", faction = "Horde", t = 1000 } }, ["USPvE|Horde"] = { [2589] = { t = 1000, complete = true, l = { { 5, 1, 2 } } } } }')
    from test_ingame import _game
    from test_no_realm import BROKEN
    lua = _game(ROUTES, saved=BROKEN % US_ID + saved)
    assert lua.eval("ns.RealmName()") is None
    assert "USPvE|Horde" in _keys(lua) and not any(k.startswith("|") for k in _keys(lua))


HOUSE_ID = 7777         # a second realm's id, which nothing names


def test_a_house_name_in_the_helpers_table_is_the_realm_and_never_a_realms_name():
    if _no_lua():
        return
    table = f'FWCS_REALM_IDS = {{ [{US_ID}] = "USPvE" }}'
    lua = _broken(realms=(US, EU), extra=table)                              # two realms known: only the table can tell
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == ("USPvE", "helper") and lua.eval("ns.RealmKey()") == "USPvE"
    # kept as nothing: no name as shown, no pair of an id and a name (the account's own word), no realm worked out from it
    assert lua.eval('FWCS_DB.__realms["USPvE"]') is None and lua.eval("FWCS_DB.__realmids") is None
    assert lua.eval("FWCS_DB.__realmids_inferred") is None
    # another character, on an id nothing names, does not take the house as its realm
    saved = ('FWCS_DB = { __chars = { ["USPvE|Garosh"] = { name = "Garosh", realm = "USPvE", '
             'house = "USPvE", faction = "Horde", t = 1000 } }, ["USPvE|Horde"] = { [2589] = { t = 1000, complete = true, l = { { 5, 1, 2 } } } } }')
    from test_ingame import _game
    from test_no_realm import BROKEN
    lua = _game(ROUTES, saved=BROKEN % HOUSE_ID + saved + "\n" + table)
    assert lua.eval("ns.RealmName()") is None and lua.eval("FWCS_DB.__realmids_inferred") is None
    # a player who said a kind the table later contradicts follows the table
    lua = _broken(realms=(US, EU), extra=f'FWCS_DB.__realmkinds = {{ [{US_ID}] = "PvP" }}; {table}')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == ("USPvE", "helper")
    assert lua.eval("ns.RealmKey()") == "USPvE" and lua.eval('FWCS_DB.__realms["USPvE"]') is None


def test_a_realm_the_helpers_table_gives_to_another_id_is_not_this_characters_one_known_realm():
    if _no_lua():
        return
    # the account knows one realm, and only because the table names it for another id: a character on an id nothing names
    # may be on any realm, so it is not told it is on that one (and no pair is kept for it)
    lua = _broken(guid_id=HOUSE_ID, realms=(US,), extra=f'FWCS_REALM_IDS = {{ [{US_ID}] = "{US}" }}')
    assert lua.eval("ns.RealmName()") is None and lua.eval("FWCS_DB.__realmids_inferred") is None
    # without the table's word it is worked out, as before
    lua = _broken(guid_id=HOUSE_ID, realms=(US,))
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "inferred") and lua.eval(f"FWCS_DB.__realmids_inferred[{HOUSE_ID}]") == US
    # the table giving the same id as this character's its realm is the table's word, not a guess
    lua = _broken(realms=(US,), extra=f'FWCS_REALM_IDS = {{ [{US_ID}] = "{US}" }}')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "helper")
    # a house's name in the table is no realm: it takes none from the one known
    lua = _broken(guid_id=HOUSE_ID, realms=(US,), extra=f'FWCS_REALM_IDS = {{ [{US_ID}] = "USPvE" }}')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "inferred")


def test_the_region_is_the_clients_portal_then_its_number_then_the_routes():
    if _no_lua():
        return
    kind = f'FWCS_DB.__realmkinds = {{ [{US_ID}] = "PvP" }}'
    lua = _broken(realms=(US, EU), extra=kind)                               # the stand-in names no portal and no number: the routes are US PvE's
    assert lua.eval("(ns.RealmName())") == "USPvP"
    lua = _broken(realms=(US, EU), extra=kind + '; function GetCVar(name) return name == "portal" and "eu" or "" end')
    assert lua.eval("(ns.RealmName())") == "EUPvP"
    lua = _broken(realms=(US, EU), extra=kind + "; function GetCurrentRegion() return 3 end")
    assert lua.eval("(ns.RealmName())") == "EUPvP"
    lua = _broken(realms=(US, EU), extra=kind + '; function GetCVar(name) return name == "portal" and "US" or "" end; function GetCurrentRegion() return 3 end')
    assert lua.eval("(ns.RealmName())") == "USPvP"                           # the portal first: it is what the helper goes by
    # no region at all (no portal, no number, no routes of one region): said so, and nothing kept
    lua = _broken(realms=(US, EU), extra="FWCS_PLANS = {}")
    lua.execute("FWCS_PLANS = {}")
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm pve")')
    assert "cannot tell your region yet" in _said(lua) and lua.eval("FWCS_DB.__realmkinds") is None


# ---- the helper ----------------------------------------------------------------------------------------------------

def _file(text: str) -> Path:
    f = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    f.write_text(text, encoding="utf-8")
    return f


def test_the_helper_fetches_that_houses_routes_and_sends_its_scans_as_the_house():
    p = _file('FWCS_DB = { __realmkinds = { [4321] = "PvE" }, __chars = { ["USPvE|Thrallson"] = { name = "Thrallson", realm = "USPvE", '
              'house = "USPvE", faction = "Horde", t = 2 } }, ["USPvE|Horde"] = { [2589] = { t = 1700000000, complete = true, l = { { 5, 1, 2 } } } } }')
    want = plans.wanted([p])
    assert ("uspve", "Horde") in want
    assert plans.is_of(HOUSE, want) and not plans.is_of(dict(HOUSE, key="uspvp--horde", realm="US PvP"), want)
    assert not plans.is_of(dict(HOUSE, key="uspve--alliance", faction="Alliance"), want)
    found = [(r, f) for r, f, _, _ in scan.datasets(p)]
    assert found == [("USPvE", "Horde")]
    sd = scan.load_scan(p, "USPvE", "Horde")
    doc = pipe.scan_document(sd)
    assert doc["realm"] == "USPvE" and doc["faction"] == "Horde" and doc["realm_id"] == 4321 and doc["realm_id_said"] is True and pipe.check_scan(doc) is None


def _said_file(kinds: str) -> Path:
    return _file('FWCS_DB = { __realmkinds = { ' + kinds + ' }, __chars = { ["USPvE|Thrallson"] = { name = "Thrallson", realm = "USPvE", '
                 'house = "USPvE", faction = "Horde", t = 2 } }, ["USPvE|Horde"] = { [2589] = { t = 1700000000, complete = true, l = { { 5, 1, 2 } } } } }')


def test_a_scan_of_a_said_kind_carries_the_one_id_of_that_kind_and_none_when_it_could_be_two():
    one = pipe.scan_document(scan.load_scan(_said_file('[4321] = "PvE", [5555] = "PvP"'), "USPvE", "Horde"))
    assert one["realm"] == "USPvE" and one["realm_id"] == 4321 and one["realm_id_said"] is True
    assert "realm_id_inferred" not in one and pipe.check_scan(one) is None
    two = pipe.scan_document(scan.load_scan(_said_file('[4321] = "PvE", [6666] = "PvE"'), "USPvE", "Horde"))     # either realm: no guess
    assert "realm_id" not in two and "realm_id_said" not in two
    none = pipe.scan_document(scan.load_scan(_said_file('[5555] = "PvP"'), "USPvE", "Horde"))
    assert "realm_id" not in none and "realm_id_said" not in none
    zero = pipe.scan_document(scan.load_scan(_said_file('[0] = "PvE"'), "USPvE", "Horde"))                    # said where the GUID gave no id
    assert "realm_id" not in zero
    assert scan.said_realm_id({"__realmkinds": {1: "RP PvP"}}, "EURPPvP") == 1 and scan.said_realm_id({"__realmkinds": {1: "RP PvP"}}, "USPvE") is None
    assert scan.said_realm_id({"__realmkinds": {1: "PvE"}}, "Stonespine") is None
    # a pair the file holds for a realm by name is that realm's, not a said one
    named = pipe.scan_document(scan.load_scan(_lua_file_named(), "CAMWOW US2 Realm 1 PvE", "Horde"))
    assert named["realm_id"] == 4321 and "realm_id_said" not in named


def _lua_file_named() -> Path:
    from test_no_realm import _lua_file
    return _lua_file(realms=("CAMWOW US2 Realm 1 PvE",), ids={4321: "CAMWOW US2 Realm 1 PvE"}, broken=False)


def test_the_pipes_check_takes_the_said_mark_and_an_older_helper_drops_a_house_name_from_the_site():
    doc = pipe.scan_document(scan.load_scan(_said_file('[4321] = "PvE"'), "USPvE", "Horde"))
    assert doc["realm_id_said"] is True and pipe.check_scan(doc) is None and pipe.check_scan(dict(doc, something_new=1)) is None
    rules = [[r"^CAMWOW (?:US|AU)\d+ Realm \d+ (PvE|PvP|RP PvP|RP)$", r"US \1"],
             [r"^CAMWOW (EU|TW|KR)\d+ Realm \d+ (PvE|PvP|RP PvP|RP)$", r"\1 \2"]]
    site = {"realm_ids": {"4321": "USPvE", "5555": "EURPPvP", "6666": "CAMWOW US2 Realm 1 PvE"}, "rules": rules,
            "houses": [{"key": "uspve--horde", "realm": "US PvE", "faction": "Horde"}, {"key": "eurppvp--horde", "realm": "EU RP PvP", "faction": "Horde"}]}
    assert plans.realm_ids(site) == {4321: "USPvE", 5555: "EURPPvP", 6666: "CAMWOW US2 Realm 1 PvE"}
    assert plans.realm_ids(dict(site, houses=[site["houses"][0]])) == {4321: "USPvE", 6666: "CAMWOW US2 Realm 1 PvE"}   # a house the site lists
    assert plans.realm_ids(dict(site, houses=[])) == {6666: "CAMWOW US2 Realm 1 PvE"}
    assert plans.realm_ids(dict(site, realm_ids={"1": "uspve", "2": "US PvE", "3": "AUPvE"})) == {}
    # a helper before this took only what the site's rules name: its check (`ruled`) fails on a house's own name
    assert plans.ruled("USPvE", rules) is None and plans.ruled("EURPPvP", rules) is None


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
