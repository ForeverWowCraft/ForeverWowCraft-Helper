"""The realms' ids from the site (helper 1.8.7). Since a hotfix of 20 Nov 2026 the game names no realm to an addon, and
the addon of 1.8.6 works the name out only where the account knew exactly one realm: a new install, or an account with
characters on two realms, was told "the game is not telling the addon which realm this is" and could scan nothing. The
site's houses.json now says which realm an id is (`realm_ids`, once enough scanners agree), and the helper writes that
into Plans.lua as FWCS_REALM_IDS, which the addon has read since 1.8.6 (ns.RealmName, source d).

The addon's part needs a Lua (pip install lupa); without one that test says so and passes."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fwchelper import luatable, plans, settings  # noqa: E402
from test_ingame import _game, lupa  # noqa: E402
from test_plans import document  # noqa: E402

NOW = 1_795_000_000
US, EU = "CAMWOW US2 Realm 1 PvE", "CAMWOW EU1 Realm 2 PvP"       # made-up realms, spelt as Forever's are
US_ID, EU_ID = 4321, 5555
RULES = [[r"^CAMWOW (?:US|AU)\d+ Realm \d+ (PvE|PvP|RP PvP|RP)$", r"US \1"],
         [r"^CAMWOW (EU|TW|KR)\d+ Realm \d+ (PvE|PvP|RP PvP|RP)$", r"\1 \2"]]      # as the site says them (config.HOUSE_PATTERNS)
SITE = "https://example.test"


def test_only_pairs_the_addon_can_use_are_taken_from_the_site():
    doc = {"houses": [], "rules": RULES, "realm_ids": {str(US_ID): US, str(EU_ID): EU}}
    assert plans.realm_ids(doc) == {US_ID: US, EU_ID: EU}
    bad = {"0": US, "-1": US, "12345678901": US, "x": US, "²": US, "1.5": US, " 7": US,          # no id
           "11": "Stonespine", "12": "US PvE", "13": "", "14": None, "15": 7, "16": [US], "17": US + "\n", "18": "x" * 81,    # no realm the rules know
           str(US_ID): US}
    assert plans.realm_ids(dict(doc, realm_ids=bad)) == {US_ID: US}
    assert plans.realm_ids(dict(doc, realm_ids={US_ID: US})) == {}                # a key that is a number is no JSON, and not taken
    for given in (None, [], "text", 7, [[US_ID, US]]):
        assert plans.realm_ids(dict(doc, realm_ids=given)) == {}
    assert plans.realm_ids({"houses": [], "realm_ids": {str(US_ID): US}}) == {}  # no rules: nothing says the name is a realm's
    assert plans.realm_ids(dict(doc, rules="text")) == {} and plans.realm_ids(None) == {} and plans.realm_ids([]) == {}
    many = {str(n): US for n in range(1, plans.MAX_REALM_IDS + 2)}
    assert plans.realm_ids(dict(doc, realm_ids=many)) == {}                      # no list of realms is this long
    assert len(plans.realm_ids(dict(doc, realm_ids=dict(list(many.items())[:-1])))) == plans.MAX_REALM_IDS


def test_the_line_is_one_line_the_game_and_the_helper_both_read():
    text = plans.plans_text([document()], SITE, written=NOW, site_houses=[["uspve", "Horde"]], realm_ids={EU_ID: EU, US_ID: US})
    line = f'FWCS_REALM_IDS = {{ [{US_ID}]="{US}", [{EU_ID}]="{EU}" }}'
    lines = text.split("\n")
    assert line in lines and lines.index(line) == len(lines) - 3 and lines[-2].startswith("FWCS_SITE = ")     # before FWCS_SITE, which stays last
    assert luatable.parse(text)["FWCS_REALM_IDS"] == {US_ID: US, EU_ID: EU}
    # without pairs the text is what it was before 1.8.7, byte for byte
    plain = plans.plans_text([document()], SITE, written=NOW, site_houses=[["uspve", "Horde"]])
    assert plans.plans_text([document()], SITE, written=NOW, site_houses=[["uspve", "Horde"]], realm_ids={}) == plain
    assert "FWCS_REALM_IDS" not in plain and text.replace(line + "\n", "") == plain
    # a name is a quoted literal whatever is in it: nothing of it becomes code, and "|" does not start a colour
    odd = plans.realm_ids_line({7: 'a"b\\c|d\n] = os.exit() --'})
    assert odd == 'FWCS_REALM_IDS = { [7]="a\\"b\\\\c||d\\n] = os.exit() --" }' and "\n" not in odd


def _state():
    kept = settings.STATE
    settings.STATE = Path(tempfile.mkdtemp())
    return kept


def test_a_look_with_nothing_new_still_brings_the_pairs_and_a_failed_look_keeps_them():
    kept = _state()
    try:
        plans.write([document()], SITE, site_houses=[["uspve", "Horde"]])
        before = plans.kept_file().read_text(encoding="utf-8")
        assert "FWCS_REALM_IDS" not in before
        plans.touch([["uspve", "Horde"]], {US_ID: US})                           # the site learnt an id since: no new routes, the pair all the same
        text = plans.kept_file().read_text(encoding="utf-8")
        data = luatable.parse(text)
        assert data["FWCS_REALM_IDS"] == {US_ID: US} and data["FWCS_PLANS"] == luatable.parse(before)["FWCS_PLANS"]
        assert [line.split(" = ")[0] for line in text.strip().split("\n")[-2:]] == ["FWCS_REALM_IDS", "FWCS_SITE"]
        plans.touch([["uspve", "Horde"]], {US_ID: US, EU_ID: EU})                # replaced as a line, never added twice
        text = plans.kept_file().read_text(encoding="utf-8")
        assert text.count("FWCS_REALM_IDS") == 1 and luatable.parse(text)["FWCS_REALM_IDS"] == {US_ID: US, EU_ID: EU}
        plans.note_problem("reach")                                              # the site could not be reached: what was known stays
        text = plans.kept_file().read_text(encoding="utf-8")
        data = luatable.parse(text)
        assert data["FWCS_REALM_IDS"] == {US_ID: US, EU_ID: EU} and data["FWCS_PLANS_PROBLEM"]["kind"] == "reach"
        assert [line.split(" = ")[0] for line in text.strip().split("\n")[-3:]] == ["FWCS_REALM_IDS", "FWCS_SITE", "FWCS_PLANS_PROBLEM"]
        plans.touch([["uspve", "Horde"]])                                        # a caller that says nothing of them leaves them
        assert luatable.parse(plans.kept_file().read_text(encoding="utf-8"))["FWCS_REALM_IDS"] == {US_ID: US, EU_ID: EU}
        plans.touch([["uspve", "Horde"]], {})                                    # the site says none any more: none
        text = plans.kept_file().read_text(encoding="utf-8")
        assert "FWCS_REALM_IDS" not in text and luatable.parse(text)["FWCS_PLANS"] == luatable.parse(before)["FWCS_PLANS"]
    finally:
        settings.STATE = kept


def test_a_refresh_writes_what_houses_json_says_with_new_routes_and_without():
    kept, get, wanted, portal = _state(), plans.get, plans.wanted, plans.scan.portal
    house = {"key": "uspve--horde", "realm": "US PvE", "faction": "Horde", "generated": NOW, "realms": [], "ingame": True}
    site = {"houses": [house], "rules": RULES, "realm_ids": {str(US_ID): US}}
    plans.get = lambda url, limit=None: site if url.endswith("/data/houses.json") else document(house="uspve--horde", realm="US PvE", faction="Horde")
    plans.wanted = lambda paths=None: set()                                      # a first install: no character saved yet
    plans.scan.portal = lambda: "US"
    try:
        docs, files = plans.refresh(SITE)
        assert len(docs) == 1 and files and plans.REALM_IDS == {US_ID: US}
        assert luatable.parse(plans.kept_file().read_text(encoding="utf-8"))["FWCS_REALM_IDS"] == {US_ID: US}
        site["realm_ids"][str(EU_ID)] = EU                                       # the routes are as they were; the site names one more id
        assert plans.refresh(SITE) == ([], [])
        assert luatable.parse(plans.kept_file().read_text(encoding="utf-8"))["FWCS_REALM_IDS"] == {US_ID: US, EU_ID: EU}
        del site["realm_ids"]                                                    # a site from before, or one that knows none
        assert plans.refresh(SITE) == ([], []) and plans.REALM_IDS == {}
        assert "FWCS_REALM_IDS" not in plans.kept_file().read_text(encoding="utf-8")
    finally:
        settings.STATE, plans.get, plans.wanted, plans.scan.portal = kept, get, wanted, portal
        plans.REALM_IDS.clear()


def test_the_addon_knows_its_realm_from_the_line_the_helper_writes():
    if lupa is None:
        print("   (no Lua here: pip install lupa to run the addon's part)")
        return
    broken = '''
      function GetRealmName() return "" end
      function GetNormalizedRealmName() return "" end
      function GetAutoCompleteRealms() return {} end
      function GetRealmID() return 0 end
      function GetCVar() return "" end
      function UnitGUID(unit) return unit == "player" and "Player-%d-00A1B2C3" or nil end
      function UnitFullName(unit) return "Newcomer", "" end
    ''' % US_ID
    # a new install: nothing saved, the game names no realm, and the line the helper writes is all there is to go by
    lua = _game(saved=broken + plans.realm_ids_line({US_ID: US, EU_ID: EU}))
    assert tuple(lua.eval("{ ns.RealmName() }").values()) == (US, "helper")
    # and without the line the same player is told the realm is not known, as with 1.8.6
    lua = _game(saved=broken)
    assert lua.eval("ns.RealmName()") is None


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
