import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fwchelper import luatable, scan  # noqa: E402

SAMPLE = r'''
FWCS_DB = {
	["__ui"] = {
		["lastFull"] = 1790000000,
	},
	["Classic Beta PvE 2"] = {
		[2840] = {
			["name"] = "Copper Bar",
			["t"] = 1790000000,
			["commodity"] = true,
			["complete"] = true,
			["full"] = true,
			["l"] = {
				{
					12, -- [1]
					20, -- [2]
				}, -- [1]
				{
					15, -- [1]
					100, -- [2]
				}, -- [2]
			},
		},
		[4358] = {
			["name"] = "Rough Dynamite",
			["t"] = 1790000000,
			["complete"] = true,
			["full"] = true,
			["l"] = {
				{
					80, -- [1]
					5, -- [2]
					4, -- [3]
				}, -- [1]
				{
					79, -- [1]
					20, -- [2]
					1, -- [3]
				}, -- [2]
				{
					99, -- [1]
					1, -- [2]
				}, -- [3]
			},
		},
		[3490] = {
			["name"] = "Deadly \"Bronze\" Poniard",
			["complete"] = false,
			["reason"] = "timeout",
			["l"] = {
			},
		},
	},
}
'''


def _write_sample() -> Path:
    p = Path(tempfile.mkdtemp()) / "ForeverWowCraftScanner.lua"
    p.write_text(SAMPLE, encoding="utf-8")
    return p


def test_parse_saved_variables():
    data = luatable.parse(SAMPLE)
    realm = data["FWCS_DB"]["Classic Beta PvE 2"]
    assert realm[2840]["name"] == "Copper Bar"
    assert realm[2840]["l"] == [[12, 20], [15, 100]]
    assert realm[2840]["commodity"] is True
    assert realm[3490]["name"] == 'Deadly "Bronze" Poniard'
    assert realm[3490]["l"] == {}   # empty table stays a dict


def test_parse_escapes_and_nested():
    v = luatable.parse_value(r'{ ["a"] = "x\ny\124cff", [1] = -3.5, b = nil, c = false }')
    assert v["a"] == "x\ny|cff" and v[1] == -3.5 and v["b"] is None and v["c"] is False


def test_load_scan_skips_settings_and_keeps_extras():
    sd = scan.load_scan(_write_sample())
    assert sd.realm == "Classic Beta PvE 2" and set(sd.items) == {2840, 3490, 4358}
    assert sd.items[2840].listings == [(12, 20), (15, 100)] and sd.items[2840].extra["full"] is True
    assert not sd.items[3490].complete and sd.items[3490].extra["reason"] == "timeout"
    # the time each auction has left rides along in the ladder's order; a row without it is 0
    assert sd.items[4358].listings == [(79, 20), (80, 5), (99, 1)] and sd.items[4358].left == [1, 4, 0]
    assert sd.items[2840].left == [] and sd.items[2840].bands == [0, 0]       # a ladder from before the addon said


def test_max_age_drops_old_records():
    sd = scan.load_scan(_write_sample())
    sd.apply_max_age(0.0001)
    assert not sd.items and len(sd.dropped_stale) == 3


def test_history_smoothing_and_volatility():
    import time as _t
    sd = scan.load_scan(_write_sample())
    now = int(_t.time())
    sd.history[2840] = [(now - 3600, 10, 100), (now - 2400, 14, 90), (now - 1200, 30, 50), (now - 10, 0, 0)]
    assert sd.smoothed_min(2840, "median", 24) == 14      # the 0 (nothing listed) point is ignored
    assert sd.smoothed_min(2840, "min", 24) == 10 and sd.smoothed_min(2840, "max", 24) == 30
    assert sd.smoothed_min(2840, "median", 0.1) is None    # window too short
    scaled = sd.rescaled_items("median", 24)[2840]
    assert scaled.listings[0][0] == 14 and scaled.listings[1][0] == round(15 * 14 / 12)  # shape kept
    assert sd.rescaled_items("spot", 24)[2840].listings[0][0] == 12
    sd.history[4358] = [(now - 3600, 70, 10), (now - 10, 90, 10)]
    assert sd.rescaled_items("min", 24)[4358].left == [1, 4, 0]           # the time left goes along with the shifted ladder
    assert 0.4 < sd.volatility(2840, 24) < 0.6


def test_queue_round_trip():
    repo_queue = scan.config.ROOT / "addon" / scan.ADDON_NAME / "Queue.lua"
    if repo_queue.exists():
        parsed = scan.read_queue(repo_queue)
        assert all(isinstance(k, str) and rows for k, rows in parsed.items())


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok", k)
