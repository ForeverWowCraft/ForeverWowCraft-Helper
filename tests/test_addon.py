"""What the addon's code says of the full snapshot's cooldown and its sound. The addon runs in
the game only, so this reads the Lua: that the pieces are there and tied together."""
import re
import sys
from pathlib import Path

HELPER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPER))

LUA = (HELPER / "addon" / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.lua").read_text(encoding="utf-8")


def _function(name: str) -> str:
    """The body of `local function <name>` up to the next line that starts a top-level statement."""
    m = re.search(r"^local function %s\(.*?\n(.*?)^end$" % re.escape(name), LUA, re.S | re.M)
    assert m, name
    return m.group(1)


def test_the_ready_sound_is_one_sound_whenever_it_plays():
    ring = _function("RingReady")
    assert "PlaySound(" in ring and "UIErrorsFrame:AddMessage" in ring and "UpdateStatus()" in ring
    assert LUA.count("PlaySound(SOUNDKIT.ALARM_CLOCK_WARNING_3") == 1          # nowhere else: both callers go through RingReady
    assert "RingReady(true)" in _function("ArmReadyAlert")                     # when the cooldown ends in the world
    assert "RingReady(false)" in _function("RingAtLogin")                      # and at a login with the snapshot ready


def test_it_plays_at_a_login_with_the_snapshot_ready_and_not_at_a_reload():
    at_login = _function("RingAtLogin")
    # only with the alert on, lists to scan, and no cooldown left; a little after the loading screen
    assert "not ReadyAlertEnabled() or #QueueNames() == 0 or FullCooldownLeft() > 0 then return end" in at_login
    assert "C_Timer.After(LOGIN_RING_DELAY" in at_login and re.search(r"^local LOGIN_RING_DELAY = \d+", LUA, re.M)
    # a login is the character entering the world from the character list: a SAVE reloads the UI, and must not ring
    assert 'loader:RegisterEvent("PLAYER_ENTERING_WORLD")' in LUA
    assert 'if event == "PLAYER_ENTERING_WORLD" then\n    if isInitialLogin and' in LUA and "RingAtLogin() end\n    return" in LUA
    # wherever the character is: nothing here asks whether the auction house is open
    assert "ahOpen" not in at_login and "AuctionHouseFrame" not in at_login


def test_the_cooldown_is_kept_for_the_account_and_started_by_any_list_that_arrives():
    assert "## SavedVariables: FWCS_DB" in (HELPER / "addon" / "ForeverWowCraftScanner" / "ForeverWowCraftScanner.toc").read_text(encoding="utf-8")
    assert 'loader:RegisterEvent("REPLICATE_ITEM_LIST_UPDATE")' in LUA and "s.lastFull, s.lastFullRefused = time(), nil" in _function("NoteFullArrived")
    assert "Settings().lastFullRefused = time()" in LUA                        # a FULL nothing came of


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
