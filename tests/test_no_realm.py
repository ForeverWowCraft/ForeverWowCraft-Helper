"""The game names no realm (a hotfix of 20 Nov 2026 on Forever): GetRealmName() answers "", GetNormalizedRealmName()
nothing, GetAutoCompleteRealms() an empty table, GetRealmID() 0, while UnitGUID("player") still carries the realm's id
("Player-4321-00A1B2C3"). Addons before 1.8.6 then kept scans as "|Horde", characters with realm "", the helper's sends
were refused ("no realm") and tried again for ever, and /fwc was empty. The addon now knows the realm by one function
(ns.RealmName: the game's answer, the character's full name, the name remembered for the id, the helper's table, the one
realm the account knew), scans nothing while it cannot tell, and files what the broken days left; the helper sends a
dataset with no realm only when the file says whose it is.

The addon's part needs a Lua (pip install lupa); without one those tests say so and pass."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import cli, pipe, plans, scan  # noqa: E402
from test_ingame import PLACES_GAME, _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402
from test_snapshot_listed import N, SNAPSHOT, auction  # noqa: E402

US, EU = "CAMWOW US2 Realm 1 PvE", "CAMWOW EU1 Realm 2 PvP"       # made-up realms, spelt as Forever's are
US_ID, EU_ID = 4321, 5555
# the client as it answers since the hotfix; the character's GUID still names the realm's id
BROKEN = '''
  function GetRealmName() return "" end
  function GetNormalizedRealmName() return "" end
  function GetAutoCompleteRealms() return {} end
  function GetRealmID() return 0 end
  function GetCVar() return "" end
  guid = "Player-%d-00A1B2C3"
  function UnitGUID(unit) return unit == "player" and guid or nil end
  fullRealm = ""
  function UnitFullName(unit) return "Thrallson", fullRealm end
'''
ROUTES = document(house="uspve--horde", realm="US PvE", faction="Horde")     # the house a US PvE realm's Horde is of
UNKNOWN = ("the game is not telling the addon which realm this is. Type /fwc realm pve, /fwc realm pvp, /fwc realm rp or "
           "/fwc realm rppvp to say which kind you play on.")


def _saved(realms=(US,), ids=None, inferred=None, broken=True, extra=""):
    """A saved file as the game reads it in: a character and a scan of each realm, and what the broken days left."""
    lines = ["FWCS_DB = { __realms = {"]
    lines += [f'  ["{r.replace(" ", "")}"] = "{r}",' for r in realms] + ["}, __chars = {"]
    lines += [f'  ["{r}|Thrallson{i}"] = {{ name = "Thrallson{i}", realm = "{r}", house = "{r}", faction = "Horde", t = 1000 }},'
              for i, r in enumerate(realms)]
    lines += [f'  ["{realms[0]}|Thrallson"] = {{ name = "Thrallson", realm = "{realms[0]}", house = "{realms[0]}", faction = "Horde", t = 1000,'
              '     picked = "tailoring", from = { tailoring = 20 }, items = { [2589] = { 1, 0, 0, 0 } } },']
    if broken:
        lines += ['  ["|Thrallson"] = { name = "Thrallson", realm = "", house = "", faction = "Horde", t = 2000, from = {},',
                  '     items = { [2589] = { 9, 0, 0, 0 } } },']
    lines += ["},"]
    for r in realms:
        lines += [f'["{r}|Horde"] = {{ [2589] = {{ t = 1000, complete = true, l = {{ {{ 5, 1, 2 }} }} }}, '
                  f'[2996] = {{ t = 1000, complete = true, l = {{}} }} }},']
    if broken:
        lines += ['["|Horde"] = { [2589] = { t = 2000, complete = true, l = { { 7, 1, 2 } } }, [2320] = { t = 2000, complete = true, l = {} } },',
                  '["|Alliance"] = { [2589] = { t = 2000, complete = true, l = {} } },']
    if ids:
        lines += ["__realmids = {" + ", ".join(f'[{i}] = "{n}"' for i, n in ids.items()) + "},"]
    if inferred:
        lines += ["__realmids_inferred = {" + ", ".join(f'[{i}] = "{n}"' for i, n in inferred.items()) + "},"]
    return "\n".join(lines) + "\n}\n" + extra


def _broken(guid_id=US_ID, **saved):
    lua = _game(ROUTES, saved=BROKEN % guid_id + _saved(**saved))
    return lua


def _snapshot(lua):
    """A full snapshot taken at the auction house (test_snapshot_listed's), with the chat said."""
    lua.execute(PLACES_GAME)
    lua.globals().house = lua.table_from([lua.table_from(list(auction(i))) for i in range(N)])
    lua.execute(SNAPSHOT)
    return [str(p) for p in lua.eval("printed").values()]


def _keys(lua, table="FWCS_DB"):
    return {str(k) for k in lua.eval(table).keys()}


def _no_lua():
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        return True
    return False


# ---- the addon ---------------------------------------------------------------------------------------------------
def test_a_healthy_client_is_as_before_and_keeps_the_ids_pair():
    if _no_lua():
        return
    lua = _game(saved='function UnitGUID(unit) return unit == "player" and "Player-77-0A0B0C0D" or nil end')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == ("Stonespine", "game") and lua.eval("ns.RealmKey()") == "Stonespine"
    assert lua.eval("ns.RealmID()") == 77 and lua.eval("FWCS_DB.__realmids[77]") == "Stonespine" and lua.eval("FWCS_DB.__realmids_inferred") is None
    assert lua.eval('FWCS_DB.__chars["Stonespine|Thrallson"].realm') == "Stonespine"
    said = _snapshot(lua)
    assert lua.eval('FWCS_DB["Stonespine|Horde"][2996].full') and not any(UNKNOWN in s for s in said)
    assert not any(k.startswith("|") for k in _keys(lua))


def test_the_realm_id_is_read_from_the_players_guid_alone():
    if _no_lua():
        return
    lua = _game()
    for guid, want in (("Player-4321-00A1B2C3", 4321), ("Creature-0-4170-0-10-3579-000057A14C", None), ("Player-0-1", None), ("", None)):
        lua.execute(f'function UnitGUID() return "{guid}" end')
        assert lua.eval("ns.RealmID()") == want, guid
    lua.execute("UnitGUID = nil")
    assert lua.eval("ns.RealmID()") is None


def test_a_broken_client_with_one_realm_known_finds_it_and_files_the_broken_days():
    if _no_lua():
        return
    lua = _broken(extra='FWCS_DB["|Horde"].__history = { [2589] = { { time() - 60, 7, 1 } } }')     # history older than 48 h goes at login
    # worked out at login from the one realm known, and from then on the name remembered for the id
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "inferred") and lua.eval("ns.RealmKey()") == US
    lua.execute("FWCS_DB.__realmids_inferred = nil")
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "one")
    lua.execute(f'FWCS_DB.__realmids_inferred = {{ [{US_ID}] = "{US}" }}')
    # kept as inferred, apart from the pairs the game gave
    assert lua.eval(f"FWCS_DB.__realmids_inferred[{US_ID}]") == US and lua.eval("FWCS_DB.__realmids") is None
    # the faction's "|Horde" scans are the realm's now; of an item in both, the newer look stays
    db = f'FWCS_DB["{US}|Horde"]'
    assert lua.eval('FWCS_DB["|Horde"]') is None and lua.eval(f"{db}[2589].t") == 2000 and lua.eval(f"{db}[2996].t") == 1000
    assert lua.eval(f"{db}[2320]") is not None and lua.eval(f"{db}.__history[2589][1][2]") == 7
    assert lua.eval('FWCS_DB["|Alliance"]') is not None                     # the other faction's: never this character's to file
    # the character is under its realm again, with what it had and what the broken days counted
    assert lua.eval('FWCS_DB.__chars["|Thrallson"]') is None
    me = f'FWCS_DB.__chars["{US}|Thrallson"]'
    assert lua.eval(f"{me}.realm") == US and lua.eval(f"{me}.house") == US and lua.eval(f"{me}.picked") == "tailoring"
    assert lua.eval(f"{me}.from.tailoring") == 20                           # an empty table of the broken days put over nothing
    said = [str(p) for p in lua.eval("printed").values()]
    assert any(f"scans saved while the game named no realm are now kept as {US} (Horde)." in s for s in said)
    # a scan goes under the realm, and the window has the house's routes
    said = _snapshot(lua)
    assert lua.eval(f"{db}[2996].full") and not any(k.startswith("|H") for k in _keys(lua)) and not any(UNKNOWN in s for s in said)
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')
    assert "not telling the addon" not in lua.eval("AllText()") and lua.eval("ns.inv.House() ~= nil")


def test_a_broken_client_with_two_realms_and_no_id_scans_nothing_and_says_why():
    if _no_lua():
        return
    lua = _broken(realms=(US, EU))
    assert lua.eval("ns.RealmName()") is None and lua.eval("ns.RealmKey()") is None
    before = _keys(lua)
    chars = _keys(lua, "FWCS_DB.__chars")
    said = _snapshot(lua)
    assert sum(UNKNOWN in s for s in said) == 2                     # once at the house (the scan by itself), once at the asked one
    assert _keys(lua) - {"__places"} == before and lua.eval('FWCS_DB["|Horde"][2996]') is None and lua.eval('FWCS_DB["|Horde"][2589].t') == 2000
    lua.execute('Fire("AUCTION_HOUSE_CLOSED"); Fire("AUCTION_HOUSE_SHOW"); Fire("BAG_UPDATE_DELAYED"); RunTimers()')
    assert sum(UNKNOWN in str(p) for p in lua.eval("printed").values()) == 2        # said once a session at the house
    # no character is saved under no realm, and none written over with none
    assert _keys(lua, "FWCS_DB.__chars") == chars and lua.eval('FWCS_DB.__chars["|Thrallson"].t') == 2000
    assert lua.eval(f'FWCS_DB.__chars["{US}|Thrallson"].realm') == US and lua.eval(f'FWCS_DB.__chars["{EU}|Thrallson1"].realm') == EU
    assert lua.eval("FWCS_DB.__realmids") is None and lua.eval("FWCS_DB.__realmids_inferred") is None
    # /fwc says so, in one line, instead of being empty
    lua.execute('SlashCmdList.FOREVERWOWCRAFTSCANNER("plan")')
    assert "The game is not telling the addon which realm this is." in lua.eval("AllText()")


def test_a_broken_client_finds_its_realm_by_the_id_among_two():
    if _no_lua():
        return
    lua = _broken(guid_id=EU_ID, realms=(US, EU), ids={US_ID: US, EU_ID: EU})
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (EU, "id") and lua.eval("ns.RealmKey()") == EU
    lua2 = _broken(guid_id=US_ID, realms=(US, EU), inferred={US_ID: US})
    assert tuple(lua2.eval("{ ns.RealmName() }").values()) == (US, "inferred")
    # this character was the only one saved with no realm in the broken days: the "|Horde" scans were its own
    assert lua.eval('FWCS_DB["|Horde"]') is None and lua.eval(f'FWCS_DB["{EU}|Horde"][2320]') is not None
    _snapshot(lua)
    assert lua.eval(f'FWCS_DB["{EU}|Horde"][2996].full') and lua.eval(f'FWCS_DB["{US}|Horde"][2996].full') is None
    # two characters played with no realm named, on two realms the account knows: the "|Horde" scans could be either's, and stay
    other = 'FWCS_DB.__chars["|Garosh"] = { name = "Garosh", realm = "", house = "", faction = "Horde", t = 2000 }'
    lua = _broken(guid_id=EU_ID, realms=(US, EU), ids={US_ID: US, EU_ID: EU}, extra=other)
    assert lua.eval("(ns.RealmName())") == EU and lua.eval('FWCS_DB["|Horde"]') is not None and lua.eval(f'FWCS_DB["{EU}|Horde"][2320]') is None
    assert lua.eval('FWCS_DB.__chars["|Thrallson"]') is None and lua.eval('FWCS_DB.__chars["|Garosh"].realm') == ""   # each its own character
    # with one realm known, they are that realm's whoever made them
    lua = _broken(extra=other)
    assert lua.eval('FWCS_DB["|Horde"]') is None and lua.eval(f'FWCS_DB["{US}|Horde"][2320]') is not None


def test_a_realm_whose_id_is_another_is_not_inferred():
    if _no_lua():
        return
    lua = _broken(guid_id=US_ID, inferred={EU_ID: US})       # the one realm known is the realm of id 5555, not this one
    assert lua.eval("ns.RealmName()") is None
    assert lua.eval('FWCS_DB["|Horde"]') is not None and lua.eval('FWCS_DB.__chars["|Thrallson"].realm') == ""


def test_the_full_name_and_the_helpers_table_name_the_realm():
    if _no_lua():
        return
    lua = _broken(realms=(US, EU), extra='fullRealm = "CAMWOWUS2Realm1PvE"')      # spelt without spaces, a realm the account knows
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "game") and lua.eval(f"FWCS_DB.__realmids[{US_ID}]") == US
    lua = _broken(realms=(US, EU), extra='fullRealm = "CAMWOWUS9Realm9PvE"')      # spelt so, and unknown: no name for a house
    assert lua.eval("ns.RealmName()") is None
    lua = _broken(realms=(US, EU), extra=f'fullRealm = "{EU}"')
    assert lua.eval("(ns.RealmName())") == EU
    lua = _broken(realms=(US, EU), extra=f'FWCS_REALM_IDS = {{ [{US_ID}] = "{US}" }}')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "helper")
    # the game answering again is all as before: its answer first, whatever was remembered
    lua = _broken(realms=(US, EU), ids={US_ID: EU}, extra=f'function GetRealmName() return "{US}" end')
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "game") and lua.eval(f"FWCS_DB.__realmids[{US_ID}]") == US


def test_a_character_kept_with_no_realm_is_moved_to_its_realm_and_merged_with_what_is_there():
    if _no_lua():
        return
    # nothing at the realm key: the entry moves whole, and so does another character's (the one realm the account knows)
    other = ('FWCS_DB.__chars["|Garosh"] = { name = "Garosh", realm = "", house = "", faction = "Horde", t = 2000,'
             ' items = { [2589] = { 3, 0, 0, 0 } } }; FWCS_DB.__chars["|Thrallson"] = nil')
    lua = _broken(broken=False, extra=other)
    assert lua.eval('FWCS_DB.__chars["|Garosh"]') is None
    moved = f'FWCS_DB.__chars["{US}|Garosh"]'
    assert lua.eval(f"{moved}.realm") == US and lua.eval(f"{moved}.house") == US and lua.eval(f"{moved}.items[2589][1]") == 3
    assert not any(k.startswith("|") for k in _keys(lua, "FWCS_DB.__chars"))
    # one at the realm key as well: the no-realm one is newer and wins for what it has; the old one keeps what only it has
    lua = _broken()
    assert lua.eval('FWCS_DB.__chars["|Thrallson"]') is None
    me = f'FWCS_DB.__chars["{US}|Thrallson"]'
    assert lua.eval(f"{me}.items[2589][1]") == 9 and lua.eval(f"{me}.picked") == "tailoring" and lua.eval(f"{me}.t") == 2000
    mixed = f'''
      local lost, old = FWCS_DB.__chars["|Thrallson"], FWCS_DB.__chars["{US}|Thrallson"]
      lost.bankSeen, lost.mailSeen = 100, 50
      lost.items = {{ [2589] = {{ 9, 4, 1, 0 }}, [2320] = {{ 2, 0, 0, 0 }} }}
      old.bankSeen, old.mailSeen, old.ahSeen = 200, 10, 7
      old.items = {{ [2589] = {{ 1, 8, 5, 6 }}, [2996] = {{ 4, 0, 0, 0 }} }}
      old.skills = {{ [165] = 100 }}; old.upto = {{ tailoring = 150 }}; old.arrow = {{ title = "old" }}
    '''
    lua = _game(ROUTES, saved=BROKEN % US_ID + _saved() + mixed)
    me = f'FWCS_DB.__chars["{US}|Thrallson"]'
    assert [lua.eval(f"{me}.items[2589][{i}]") for i in (1, 2, 3, 4)] == [9, 8, 1, 6]       # bags newer, bank older, mail newer, auctions only the old
    assert lua.eval(f"{me}.items[2320][1]") == 2 and lua.eval(f"{me}.items[2996][1]") == 0     # an item the bags no longer hold
    assert lua.eval(f"{me}.bankSeen") == 200 and lua.eval(f"{me}.mailSeen") == 50 and lua.eval(f"{me}.ahSeen") == 7
    assert lua.eval(f"{me}.skills[165]") == 100 and lua.eval(f"{me}.upto.tailoring") == 150 and lua.eval(f"{me}.arrow.title") == "old"
    # the realm not known: nothing moves
    lua = _broken(realms=(US, EU))
    assert lua.eval('FWCS_DB.__chars["|Thrallson"].t') == 2000 and lua.eval(f'FWCS_DB.__chars["{US}|Thrallson"].t') == 1000
    # two realms known and the id naming one: this character moves, another's entry (maybe of the other realm) stays
    other2 = 'FWCS_DB.__chars["|Garosh"] = { name = "Garosh", realm = "", house = "", faction = "Horde", t = 2000 }'
    lua = _broken(realms=(US, EU), ids={US_ID: US, EU_ID: EU}, extra=other2)
    assert lua.eval('FWCS_DB.__chars["|Thrallson"]') is None and lua.eval('FWCS_DB.__chars["|Garosh"].realm') == ""


def test_an_empty_realm_pair_is_removed_and_never_written():
    if _no_lua():
        return
    junk = 'FWCS_DB.__realms[""] = ""'
    lua = _broken(extra=junk)
    assert lua.eval('FWCS_DB.__realms[""]') is None and lua.eval(f'FWCS_DB.__realms["{US.replace(" ", "")}"]') == US
    # the game answering with nothing, in any way: no empty key comes of it
    lua = _broken(extra='function GetNormalizedRealmName() return "" end')
    assert lua.eval('FWCS_DB.__realms[""]') is None
    lua = _game(saved='function GetRealmName() return "" end function GetNormalizedRealmName() return "" end')
    assert lua.eval('FWCS_DB.__realms == nil or FWCS_DB.__realms[""] == nil')


# ---- the helper --------------------------------------------------------------------------------------------------
def _file(text):
    p = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    p.write_text(text, encoding="utf-8")
    return p


def _lua_file(realms=(US,), ids=None, inferred=None, broken=True):
    """The saved file as the game writes it (the same shape _saved gives the stand-in game), with finished items."""
    text = _saved(realms, ids, inferred, broken).replace("[2589] = { t", '[2589] = { name = "Linen Cloth", t')
    return _file(text.replace("t = 1000, complete", "t = 1790000000, complete").replace("t = 2000, complete", "t = 1790003000, complete"))


class Service:
    url = "test"

    def __init__(self):
        self.sent = []

    def send_scan(self, doc):
        if not doc["realm"].strip():
            raise pipe.PipeError("POST /v1/scans: 400 no realm")         # what the pipe answers it (worker.js, readScan)
        self.sent.append(doc)
        return {"id": len(self.sent), "new": True}


def _sending(fn):
    kept, cli.settings.STATE = cli.settings.STATE, Path(tempfile.mkdtemp())
    cli._no_realm_said.clear()
    try:
        return fn()
    finally:
        cli.settings.STATE = kept


def test_scans_with_no_realm_are_not_sent_and_not_tried_again_when_the_file_cannot_say_whose():
    def run():
        s = Service()
        p = _lua_file(realms=(US, EU))                              # two realms: the "|Horde" scans could be either's
        assert cli.send_once(s, p) is True                          # no Refused: nothing to try again
        assert sorted((d["realm"], d["faction"]) for d in s.sent) == [(EU, "Horde"), (US, "Horde")]
        assert cli.send_once(s, p) is False and len(s.sent) == 2    # the second look: nothing sent, nothing refused
        p1 = _lua_file(realms=(US,))                                 # one realm, but no ids: an addon before 1.8.6, which files them itself
        s1 = Service()
        cli.send_once(s1, p1, again=True)
        assert [(d["realm"], d["faction"]) for d in s1.sent] == [(US, "Horde")]
        # asked for alone (the single-house path), it is not sent either
        assert cli.send_once(Service(), _file('FWCS_DB = { ["|Horde"] = { [2589] = { t = 1790000000, complete = true, l = {} } } }')) is False
    _sending(run)


def test_the_no_realm_line_is_said_once_a_run():
    import contextlib
    import io

    def run():
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            p = _lua_file(realms=(US, EU))
            for _ in range(3):
                cli.send_once(Service(), p, again=True)
        lines = [ln for ln in out.getvalue().splitlines() if "saved while the game named no realm" in ln]
        assert len(lines) == 2 and {ln.split(",")[1].split()[0] for ln in lines} == {"Horde", "Alliance"}, lines
    _sending(run)


def test_scans_with_no_realm_go_under_the_realm_the_file_is_certain_of_with_its_id():
    def run():
        s = Service()
        p = _lua_file(realms=(US,), inferred={US_ID: US})
        assert scan.attributed_realm(scan.saved_db(p)) == US
        cli.send_once(s, p)
        got = sorted((d["realm"], d["faction"], sorted(d["items"])) for d in s.sent)
        assert got == [(US, "Alliance", ["2589"]), (US, "Horde", ["2320", "2589"]), (US, "Horde", ["2589", "2996"])], got
        assert all(d["realm_id"] == US_ID and d["realm_id_inferred"] is True for d in s.sent)
        assert all(pipe.check_scan(d) is None for d in s.sent)
        assert cli.send_once(s, p) is False and len(s.sent) == 3                 # each noted apart: none sent again
        # a pair the game gave is not marked inferred
        doc = pipe.scan_document(scan.load_scan(_lua_file(realms=(US,), ids={US_ID: US}, broken=False), US, "Horde"))
        assert doc["realm_id"] == US_ID and "realm_id_inferred" not in doc
        # no pair: no field (and the mark is the same either way: nothing sent again for it)
        plain = pipe.scan_document(scan.load_scan(_lua_file(realms=(US,), broken=False), US, "Horde"))
        assert "realm_id" not in plain and pipe.mark(plain) == pipe.mark(doc)
    _sending(run)


def test_the_file_is_certain_only_when_nothing_in_it_says_another_realm():
    one = scan.saved_db(_lua_file(realms=(US,), ids={US_ID: US}))
    assert scan.attributed_realm(one) == US
    assert scan.attributed_realm(scan.saved_db(_lua_file(realms=(US,)))) is None                       # no ids: an addon before 1.8.6
    assert scan.attributed_realm(scan.saved_db(_lua_file(realms=(US, EU), ids={US_ID: US}))) is None    # two realms
    assert scan.attributed_realm(scan.saved_db(_lua_file(realms=(US,), ids={US_ID: US}, inferred={EU_ID: US}))) is None   # two ids
    # a character saved with no realm that is nobody's namesake: it may have played on another realm, and scanned there
    stranger = dict(one, __chars=dict(one["__chars"], **{"|Newcomer": {"name": "Newcomer", "realm": "", "faction": "Horde"}}))
    assert scan.attributed_realm(stranger) is None
    assert scan.realm_id_of(one, US) == (US_ID, False) and scan.realm_id_of(one, EU) == (None, False)


def test_a_character_saved_with_no_realm_keeps_its_house_for_the_routes():
    chars = [{"name": "Thrallson", "realm": "", "house": "", "faction": "Horde", "t": 2, "items": {}, "skills": {}}]
    p = _file('FWCS_DB = { __realms = { CAMWOWUS2Realm1PvE = "' + US + '" }, __chars = { ["|Thrallson"] = '
              '{ name = "Thrallson", realm = "", house = "", faction = "Horde", t = 2 } } }')
    assert plans.no_realm_wanted(p, chars) == {(US, "Horde"), (plans.spelt(US), "Horde")}
    assert (US, "Horde") in plans.wanted([p])
    # two realms known and no id: neither is taken for it (its namesake's would be)
    p2 = _file('FWCS_DB = { __realms = { a = "' + US + '", b = "' + EU + '" } }')
    assert plans.no_realm_wanted(p2, chars) == set()
    named = chars + [{"name": "Thrallson", "realm": EU, "house": EU, "faction": "Horde", "t": 1, "items": {}, "skills": {}}]
    assert (EU, "Horde") in plans.no_realm_wanted(p2, named) and (US, "Horde") not in plans.no_realm_wanted(p2, named)
    p3 = _file('FWCS_DB = { __realms = { a = "' + US + '", b = "' + EU + '" }, __realmids = { [' + str(US_ID) + '] = "' + US + '" } }')
    assert (US, "Horde") in plans.no_realm_wanted(p3, chars)


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
