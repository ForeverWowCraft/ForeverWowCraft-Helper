"""The full snapshot builds ladders only for the listed items (the queue) and records exactly what it did when it
built one for every auction on the house; its figures (auctions read, distinct items on the house) still count
every auction. Before 1.8.0 a table and a ladder row were made for each of the house's 172,000 auctions, though
only the listed items were recorded.

Needs a Lua (pip install lupa); without one this says so and passes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_ingame import PLACES_GAME, _game, lupa  # noqa: E402

LISTED = (2996, 2589, 2320)            # the stand-in game's queue (test_ingame.GAME); 2320 has no auction here
ITEMS = (2589, 9999, 2996, 8888, 7777)  # two listed, three not
N = 1200


def auction(i):
    """(item, count, buyout, band) of auction i of the synthetic house; every 37th is one a ladder skips."""
    item, count = ITEMS[i % len(ITEMS)], 1 + i % 3
    if i % 37 == 0:
        return (False if i % 2 else item), 0, 0, 0
    return item, count, count * (100 + i), 1 + i % 4      # a unit price of its own for each auction: no ties to sort


def expected():
    ladders = {item: [] for item in LISTED}
    for i in range(N):
        item, count, buyout, band = auction(i)
        if item in ladders and count > 0 and buyout > 0:
            ladders[item].append([buyout // count, count, band])
    return {item: sorted(rows) for item, rows in ladders.items()}


SNAPSHOT = '''
  FrameUtil = { RegisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:RegisterEvent(e) end end,
                UnregisterFrameForEvents = function(f, evs) for _, e in ipairs(evs) do f:UnregisterEvent(e) end end }
  C_AuctionHouse.ReplicateItems = function() end
  C_AuctionHouse.GetNumReplicateItems = function() return #house end
  C_AuctionHouse.GetReplicateItemInfo = function(i)
    local a = house[i + 1]
    return "name", nil, a[2], nil, nil, nil, nil, nil, nil, a[3], nil, nil, nil, nil, nil, nil, a[1], true
  end
  timeAsked = {}
  C_AuctionHouse.GetReplicateItemTimeLeft = function(i) timeAsked[#timeAsked + 1] = i; return house[i + 1][4] end
  AuctionHouseFrame = CreateFrame("Frame"); AuctionHouseFrame.shown = true
  FWCS_FRESH = {}
  SlashCmdList.FOREVERWOWCRAFTSCANNER("debug")          -- the log lines in chat too
  Fire("AUCTION_HOUSE_SHOW")
  SlashCmdList.FOREVERWOWCRAFTSCANNER("full force")
  table.remove(timers); table.remove(timers)
  Fire("REPLICATE_ITEM_LIST_UPDATE")
  for _ = 1, 5 do RunTimers() end                       -- 500 auctions a frame
'''


def test_the_snapshot_records_the_listed_items_as_before_and_counts_every_auction():
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        return
    lua = _game()
    lua.execute(PLACES_GAME)
    lua.globals().house = lua.table_from([lua.table_from(list(auction(i))) for i in range(N)])
    lua.execute(SNAPSHOT)
    db = lua.eval('FWCS_DB["Stonespine|Horde"]')
    got = {item: [list(r.values()) for r in db[item]["l"].values()] for item in LISTED}
    assert got == expected(), {k: (len(got[k]), len(expected()[k])) for k in LISTED}
    assert all(db[item]["complete"] and db[item]["full"] for item in LISTED)
    assert db[9999] is None and db[8888] is None and db[7777] is None                     # nothing of an unlisted item, as before
    valid = [auction(i) for i in range(N) if auction(i)[0] and auction(i)[1] > 0]
    said = [str(p) for p in lua.eval("printed").values()]
    assert any(f"snapshot: {len(valid)} auctions, {len({a[0] for a in valid})} distinct items on the AH; 2 queued items priced, 1 with no auctions"
               in p for p in said), said
    assert any(f"{len(valid)} auctions read, 2 of 3 route items priced." in p for p in said)
    # the time left is asked of the listed items' auctions alone
    asked = list(lua.eval("timeAsked").values())
    assert asked and all(auction(i)[0] in LISTED for i in asked) and len(asked) == sum(len(r) for r in expected().values())


if __name__ == "__main__":
    if lupa is None:
        print("skipped: no Lua here (pip install lupa)")
        sys.exit(0)
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
