"""The addon keeps an item's price history for 48 hours, 48 points at most (200 points an item until 1.8.0, which
grew the saved file from 6 to 35 MB): trimmed at login, so a player who no longer scans gets a smaller file too,
and at every complete scan of the item. The newest points stay, in their order.

Needs a Lua (pip install lupa); without one this says so and passes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ingame import PLACES_GAME, _game, lupa  # noqa: E402

# a history at the old cap: 200 points, one every half hour for 2589 (the newest 48 all within the 48 hours) and one
# every two hours for 2996 (of the newest 48, only those of the last 48 hours stay); 2320 has nothing recent at all
SAVED = '''
local now = time()
local half, two = {}, {}
for k = 1, 200 do
  half[k] = { now - (200 - k) * 1800, k, k }
  two[k] = { now - (200 - k) * 7200, k, k }
end
FWCS_DB = { ["Stonespine|Horde"] = { __history = { [2589] = half, [2996] = two, [2320] = { { now - 72 * 3600, 5, 5 } } } } }
'''


def _points(lua, item):
    rows = lua.eval(f'FWCS_DB["Stonespine|Horde"].__history[{item}]')
    return None if rows is None else [row[2] for row in rows.values()]


def test_the_history_is_trimmed_at_login():
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        return
    lua = _game(saved=SAVED)
    assert _points(lua, 2589) == list(range(153, 201))                  # the newest 48, oldest first
    assert _points(lua, 2996) == list(range(176, 201))                  # the 25 of the last 48 hours
    assert _points(lua, 2320) is None                                   # nothing recent: the item's history goes


def test_a_complete_scan_keeps_48_points_at_most():
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        return
    lua = _game(saved=SAVED)
    lua.execute(PLACES_GAME)
    lua.execute('''
      FrameUtil = { RegisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:RegisterEvent(e) end end,
                    UnregisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:UnregisterEvent(e) end end }
      C_AuctionHouse.ReplicateItems = function() end
      C_AuctionHouse.GetNumReplicateItems = function() return 3 end
      C_AuctionHouse.GetReplicateItemInfo = function(i)
        return "Linen Cloth", nil, 5, nil, nil, nil, nil, nil, nil, 50 + i * 5, nil, nil, nil, nil, nil, nil, 2589, true
      end
      AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
      FWCS_FRESH = {}
      Fire("AUCTION_HOUSE_SHOW")
      SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
      table.remove(timers); table.remove(timers)
      Fire("REPLICATE_ITEM_LIST_UPDATE")
      RunTimers()
    ''')
    points = _points(lua, 2589)
    assert len(points) == 48 and points[:-1] == list(range(154, 201)) and points[-1] == 10       # the scan's: 50c for 5, 10c a unit
    newest = lua.eval('FWCS_DB["Stonespine|Horde"].__history[2589][48][1]')
    assert newest == lua.eval("time()") or newest == lua.eval("time()") - 1


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
