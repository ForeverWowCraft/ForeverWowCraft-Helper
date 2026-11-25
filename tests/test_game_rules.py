"""The game says which kind of realm this is (addon 1.8.9). The client's rules (Enum.GameRule, C_GameRules.IsGameRuleActive:
the PvP and RP rulesets) tell a realm's kind, and Auctionator and Questie read them the same way; on Forever the kind is
all a house needs (every realm of one kind in a region is one auction house). ns.RealmName has a new source for it, how
"rules", after the names the account or the helper knows and before what a player said, and the helper sends the id the
game gave for the kind as evidence (`realm_id_rules`).

"No rule is on" is also what a call made too early, or a client without these rules, looks like, so the kind is trusted
only where every answer is a boolean and RegionalUniqueNamesEnabled() is true (and no hardcore rule is on).

The addon's part needs a Lua (pip install lupa); without one those tests say so and pass."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import pipe, scan  # noqa: E402
from test_no_realm import BROKEN, EU, ROUTES, US, US_ID, _broken, _no_lua  # noqa: E402
from test_ingame import _game  # noqa: E402
from test_realm_kind import _file, _said  # noqa: E402

PVP, RP = 213, 214
NONE = 'FWCS_DB = {}\n'


def rules(pvp=False, rp=False, hardcore=None, enabled="true", region=None):
    """The Lua that defines the rules as the client does (a stand-in that says `pvp`, `rp`, `hardcore` are on)."""
    lua = [f"Enum.GameRule = {{ PvPRuleset = {PVP}, RPRuleset = {RP}{'' if hardcore is None else ', HardcoreRuleset = 215'} }}",
           f"local on = {{ [{PVP}] = {str(pvp).lower()}, [{RP}] = {str(rp).lower()}, [215] = {str(bool(hardcore)).lower()} }}",
           "C_GameRules = { IsGameRuleActive = function(rule) return on[rule] end }",
           f"function RegionalUniqueNamesEnabled() return {enabled} end"]
    if region:
        lua.append(f'function GetCVar(name) return name == "portal" and "{region}" or "" end')
    return "\n".join(lua)


def fresh(extra="", guid_id=US_ID):
    """A new install: nothing saved, the game naming no realm."""
    return _game(ROUTES, saved=BROKEN % guid_id + NONE + extra)


def name(lua):
    return tuple(lua.eval("{ ns.RealmName() }").values())


def test_each_of_the_four_kinds_on_a_new_install_is_the_house_with_nothing_typed():
    if _no_lua():
        return
    for kwargs, house in (({}, "USPvE"), ({"pvp": True}, "USPvP"), ({"rp": True}, "USRP"), ({"pvp": True, "rp": True}, "USRPPvP")):
        lua = fresh(rules(**kwargs))
        assert name(lua) == (house, "rules"), (kwargs, name(lua))
        assert lua.eval("ns.RealmKey()") == house
    lua = fresh(rules(pvp=True, rp=True, region="EU"))
    assert name(lua) == ("EURPPvP", "rules")
    lua = fresh(rules(hardcore=False))                                       # the hardcore rule answering "off" is no reason to doubt
    assert name(lua) == ("USPvE", "rules")
    # the window is not the "R" state, and the player is told nothing to type
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')
    assert "not telling the addon" not in lua.eval("AllText()")


def test_the_kind_the_game_gave_is_kept_by_id_and_nothing_is_written_as_a_realm():
    if _no_lua():
        return
    lua = fresh(rules(pvp=True))
    assert lua.eval(f"FWCS_DB.__realmrules[{US_ID}]") == "PvP"
    for key in ("__realms", "__realmids", "__realmids_inferred", "__realmkinds", "__groups"):
        assert lua.eval(f"FWCS_DB.{key}") is None, key
    # an id the GUID does not give (0) is not kept
    lua = fresh(rules(), guid_id=0)
    assert lua.eval("FWCS_DB.__realmrules") is None
    # the game answering later with another kind (the rules changed, or the early call was wrong): the kept one follows
    lua = fresh(rules())
    lua.execute(f"C_GameRules.IsGameRuleActive = function(rule) return rule == {PVP} end; Fire('GAME_RULES_CHANGED')")
    assert lua.eval(f"FWCS_DB.__realmrules[{US_ID}]") == "PvP" and name(lua) == ("USPvP", "rules")
    lua.execute("Fire('PLAYER_ENTERING_WORLD', false)")
    assert lua.eval(f"FWCS_DB.__realmrules[{US_ID}]") == "PvP"


def test_a_character_on_a_pvp_realm_is_not_taken_for_the_accounts_one_known_pve_realm():
    if _no_lua():
        return
    lua = _broken(extra=rules(pvp=True))                                     # the account knows only a PvE realm
    assert name(lua) == ("USPvP", "rules")
    assert lua.eval("FWCS_DB.__realmids_inferred") is None and lua.eval("FWCS_DB.__realmids") is None
    assert lua.eval('FWCS_DB.__realms["USPvP"]') is None and lua.eval(f"FWCS_DB.__realmrules[{US_ID}]") == "PvP"
    assert lua.eval(f'FWCS_DB.__realms["{US.replace(" ", "")}"]') == US      # the account's own pair is as it was
    # a name remembered for this id, or the helper's, of the other kind, is passed over too
    lua = _broken(realms=(US,), ids={US_ID: US}, extra=rules(pvp=True))
    assert name(lua) == ("USPvP", "rules") and lua.eval(f"FWCS_DB.__realmids[{US_ID}]") == US
    lua = _broken(realms=(US, EU), extra=rules(pvp=True) + f'\nFWCS_REALM_IDS = {{ [{US_ID}] = "USPvE" }}')
    assert name(lua) == ("USPvP", "rules")
    # a name whose kind cannot be read is not passed over
    lua = _broken(realms=("Stonespine",), extra=rules(pvp=True))
    assert name(lua) == ("Stonespine", "inferred")
    for realm, kind, other in ((EU, "PvP", {}), ("CAMWOW US2 Realm 3 RP PvP", "RP PvP", {}), ("CAMWOW US2 Realm 4 RP", "RP", {})):
        lua = _broken(realms=(realm,), extra=rules(pvp=kind in ("PvP", "RP PvP"), rp="RP" in kind))
        assert name(lua) == (realm, "inferred"), (realm, name(lua))


def test_a_remembered_or_tabled_name_of_the_same_kind_is_used_as_before():
    if _no_lua():
        return
    lua = _broken(realms=(US, EU), ids={US_ID: US}, extra=rules())
    assert name(lua) == (US, "id")
    lua = _broken(realms=(US, EU), extra=rules() + f'\nFWCS_REALM_IDS = {{ [{US_ID}] = "{US}" }}')
    assert name(lua) == (US, "helper")
    lua = _broken(realms=(US, EU), extra=rules() + f'\nFWCS_REALM_IDS = {{ [{US_ID}] = "USPvE" }}')
    assert name(lua) == ("USPvE", "helper")
    lua = _broken(realms=(US,), extra=rules())
    assert name(lua) == (US, "inferred") and lua.eval(f"FWCS_DB.__realmids_inferred[{US_ID}]") == US
    lua = _broken(realms=(US,), inferred={US_ID: US}, extra=rules())
    assert name(lua) == (US, "inferred")
    # the game's own name stands over the rules
    lua = _broken(extra=rules(pvp=True) + '\nfunction GetRealmName() return "Stonespine" end')
    assert name(lua) == ("Stonespine", "game")


def test_the_rules_win_over_a_different_said_kind_and_agree_with_the_same_one():
    if _no_lua():
        return
    said = f'FWCS_DB.__realmkinds = {{ [{US_ID}] = "PvP" }}'
    lua = _broken(realms=(US, EU), extra=rules() + "\n" + said)
    assert name(lua) == ("USPvE", "rules")
    lua = _broken(realms=(US, EU), extra=rules(pvp=True) + "\n" + said)
    assert name(lua) == ("USPvP", "rules")
    # what was said is still there, and is the answer once the game cannot say
    lua = _broken(realms=(US, EU), extra=said)
    assert name(lua) == ("USPvP", "said")


def _nil_variants():
    base = rules(pvp=True)
    return {
        "no C_GameRules": base + "\nC_GameRules = nil",
        "C_GameRules not a table": base + "\nC_GameRules = 1",
        "no IsGameRuleActive": base + "\nC_GameRules = {}",
        "no GameRule enum": base + "\nEnum.GameRule = nil",
        "no PvP rule": base + "\nEnum.GameRule.PvPRuleset = nil",
        "no RP rule": base + "\nEnum.GameRule.RPRuleset = nil",
        "rule not a number": base + '\nEnum.GameRule.RPRuleset = "214"',
        "a non-boolean answer": base + "\nC_GameRules.IsGameRuleActive = function() return 1 end",
        "no answer": base + "\nC_GameRules.IsGameRuleActive = function() end",
        "an answer that errors": base + '\nC_GameRules.IsGameRuleActive = function() error("too early") end',
        "no RegionalUniqueNamesEnabled": base + "\nRegionalUniqueNamesEnabled = nil",
        "RegionalUniqueNamesEnabled false": rules(pvp=True, enabled="false"),
        "RegionalUniqueNamesEnabled not a boolean": rules(pvp=True, enabled="1"),
        "RegionalUniqueNamesEnabled errors": base + '\nfunction RegionalUniqueNamesEnabled() error("too early") end',
        "hardcore on": rules(pvp=True, hardcore=True),
        "hardcore not answered": rules(pvp=True, hardcore=False) + "\nlocal f = C_GameRules.IsGameRuleActive; "
                                 "C_GameRules.IsGameRuleActive = function(r) if r == 215 then return nil end return f(r) end",
    }


def test_every_way_the_game_cannot_say_leaves_the_behaviour_of_1_8_8_exactly():
    if _no_lua():
        return
    for label, extra in _nil_variants().items():
        for build in (lambda e: _broken(extra=e), lambda e: _broken(realms=(US, EU), extra=e),
                      lambda e: _broken(realms=(US, EU), extra=e + f'\nFWCS_DB.__realmkinds = {{ [{US_ID}] = "PvP" }}')):
            with_rules = build(extra)
            without = build("")
            assert name(with_rules) == name(without), (label, name(with_rules), name(without))
            assert with_rules.eval("FWCS_DB.__realmrules") is None, label
            assert with_rules.eval("FWCS_DB.__realmids_inferred ~= nil") == without.eval("FWCS_DB.__realmids_inferred ~= nil"), label
    # and the player is asked, as before
    lua = _broken(realms=(US, EU), extra=rules(hardcore=True))
    assert name(lua) == ()
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm")')
    assert "the realm is not known. Say which kind you play on" in _said(lua)
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')
    assert "not telling the addon" in lua.eval("AllText()")


def test_the_player_is_told_how_the_realm_is_known_and_a_kind_the_game_contradicts_is_refused():
    if _no_lua():
        return
    lua = fresh(rules())
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm")')
    assert "this is a US PvE realm (the game says so)." in _said(lua)
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm pvp")')
    assert "the game says this is a US PvE realm, not PvP: nothing kept." in _said(lua)
    assert lua.eval("FWCS_DB.__realmkinds") is None and name(lua) == ("USPvE", "rules")
    lua.execute('SlashCmdList.FOREVERWOWCRAFT("realm pve")')              # agreeing: nothing to say, nothing kept
    assert lua.eval("FWCS_DB.__realmkinds") is None


def test_the_helper_sends_the_id_the_game_gave_as_evidence_and_none_when_it_could_be_two():
    one = pipe.scan_document(scan.load_scan(_rules_file('[4321] = "PvE", [5555] = "PvP"', ""), "USPvE", "Horde"))
    assert one["realm"] == "USPvE" and one["realm_id"] == 4321 and one["realm_id_rules"] is True
    assert "realm_id_said" not in one and "realm_id_inferred" not in one and pipe.check_scan(one) is None
    two = pipe.scan_document(scan.load_scan(_rules_file('[4321] = "PvE", [6666] = "PvE"', ""), "USPvE", "Horde"))
    assert "realm_id" not in two and "realm_id_rules" not in two
    # both tables name one same id: the game's mark; two different ids between them: none
    same = pipe.scan_document(scan.load_scan(_rules_file('[4321] = "PvE"', '[4321] = "PvE"'), "USPvE", "Horde"))
    assert same["realm_id"] == 4321 and same["realm_id_rules"] is True and "realm_id_said" not in same
    apart = pipe.scan_document(scan.load_scan(_rules_file('[4321] = "PvE"', '[6666] = "PvE"'), "USPvE", "Horde"))
    assert "realm_id" not in apart and "realm_id_rules" not in apart
    # a said id alone is still said, an id of 0 or of another kind is none, and a realm that is not a house's name has none of this
    said = pipe.scan_document(scan.load_scan(_rules_file('[5555] = "PvP"', '[4321] = "PvE"'), "USPvE", "Horde"))
    assert said["realm_id"] == 4321 and said["realm_id_said"] is True and "realm_id_rules" not in said
    zero = pipe.scan_document(scan.load_scan(_rules_file('[0] = "PvE"', ""), "USPvE", "Horde"))
    assert "realm_id" not in zero
    assert scan.kind_realm_id({"__realmrules": {1: "RP PvP"}}, "EURPPvP") == (1, True)
    assert scan.kind_realm_id({"__realmrules": {1: "RP PvP"}}, "Stonespine") == (None, False)
    assert scan.kind_realm_id({}, "USPvE") == (None, False)


def _rules_file(rules_ids: str, said_ids: str):
    text = "FWCS_DB = { "
    if rules_ids:
        text += f"__realmrules = {{ {rules_ids} }}, "
    if said_ids:
        text += f"__realmkinds = {{ {said_ids} }}, "
    return _file(text + '__chars = { ["USPvE|Thrallson"] = { name = "Thrallson", realm = "USPvE", house = "USPvE", faction = "Horde", t = 2 } }, '
                 '["USPvE|Horde"] = { [2589] = { t = 1700000000, complete = true, l = { { 5, 1, 2 } } } } }')


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
