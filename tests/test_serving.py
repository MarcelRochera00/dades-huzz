import time
from datetime import UTC, datetime

from dades_huzz.data import State
from dades_huzz.serving import answer, decide_role, repair, validate
from dades_huzz.serving.loop import LiveState
from dades_huzz.serving.versions import Split

AVAILABLE = {f"p_{i:02d}" for i in range(20)}
TEN = [f"p_{i:02d}" for i in range(10)]


def test_ten_distinct_available_products_are_valid():
    assert validate(TEN, AVAILABLE) == []


def test_invalid_answer_reports_every_reason():
    items = ["p_00", "p_00", "p_gone"] + TEN[1:6]
    assert validate(items, AVAILABLE) == ["duplicate", "unavailable", "wrong_size"]


def test_repair_keeps_valid_items_in_order_and_pads_from_fallback():
    items = ["p_05", "p_05", "p_gone", "p_03"]
    fallback = [
        "p_03",
        "p_gone_too",
        "p_11",
        "p_12",
        "p_13",
        "p_14",
        "p_15",
        "p_16",
        "p_17",
        "p_18",
        "p_19",
    ]
    assert repair(items, AVAILABLE, fallback) == [
        "p_05",
        "p_03",
        "p_11",
        "p_12",
        "p_13",
        "p_14",
        "p_15",
        "p_16",
        "p_17",
        "p_18",
    ]


def test_repair_cuts_long_answers_to_ten():
    assert repair(TEN + ["p_15"], AVAILABLE, []) == TEN


ME = "loop_b"


def beat(loop_id, ts_ms, role="active", started_ms=0):
    return {"loop_id": loop_id, "ts_ms": ts_ms, "role": role, "started_ms": started_ms}


def test_a_lone_loop_becomes_active():
    assert (
        decide_role(
            ME,
            "standby",
            started_ms=0,
            last_write_ms=9_000,
            heartbeats=[],
            now_ms=10_000,
        )
        == "active"
    )


def test_a_loop_waits_while_another_is_active_and_alive():
    beats = [beat("loop_a", ts_ms=9_000)]
    assert (
        decide_role(
            ME,
            "standby",
            started_ms=0,
            last_write_ms=9_500,
            heartbeats=beats,
            now_ms=10_000,
        )
        == "standby"
    )


def test_a_waiting_loop_takes_over_when_the_active_one_goes_silent():
    beats = [beat("loop_a", ts_ms=3_000)]
    assert (
        decide_role(
            ME,
            "standby",
            started_ms=0,
            last_write_ms=9_500,
            heartbeats=beats,
            now_ms=10_000,
        )
        == "active"
    )


def test_two_active_loops_leave_only_the_oldest_active():
    beats = [
        beat("loop_a", ts_ms=9_000, started_ms=1_000),
        beat(ME, ts_ms=9_000, started_ms=2_000),
    ]
    assert (
        decide_role(
            ME,
            "active",
            started_ms=2_000,
            last_write_ms=9_000,
            heartbeats=beats,
            now_ms=10_000,
        )
        == "standby"
    )
    assert (
        decide_role(
            "loop_a",
            "active",
            started_ms=1_000,
            last_write_ms=9_000,
            heartbeats=beats,
            now_ms=10_000,
        )
        == "active"
    )


def test_a_loop_that_cannot_write_its_heartbeat_steps_down():
    assert (
        decide_role(
            ME,
            "active",
            started_ms=0,
            last_write_ms=3_000,
            heartbeats=[],
            now_ms=10_000,
        )
        == "standby"
    )


def test_only_the_latest_heartbeat_of_each_loop_counts():
    beats = [
        beat("loop_a", ts_ms=9_000, role="active"),
        beat("loop_a", ts_ms=9_800, role="standby"),
    ]
    assert (
        decide_role(
            ME,
            "standby",
            started_ms=0,
            last_write_ms=9_500,
            heartbeats=beats,
            now_ms=10_000,
        )
        == "active"
    )


def test_a_loop_that_cannot_read_the_heartbeats_keeps_its_role():
    assert (
        decide_role(
            ME,
            "standby",
            started_ms=0,
            last_write_ms=9_500,
            heartbeats=None,
            now_ms=10_000,
        )
        == "standby"
    )
    assert (
        decide_role(
            ME,
            "active",
            started_ms=0,
            last_write_ms=9_500,
            heartbeats=None,
            now_ms=10_000,
        )
        == "active"
    )


def test_answer_replaces_a_product_whose_stock_just_changed_even_if_available():
    fallback = tuple(f"p_{i:02d}" for i in range(12))
    state = State(
        available=frozenset(fallback),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )
    allowed = state.available - {"p_00"}
    split = Split({"v": lambda request, state: list(fallback[:10])}, {"v": 1})
    [result] = answer([{"request_id": "r1"}], split, state, allowed)
    assert result["items"] == [f"p_{i:02d}" for i in range(1, 11)]
    assert result["problems"] == ["unavailable"]


def test_answer_survives_a_model_that_raises():
    fallback = tuple(f"p_{i:02d}" for i in range(10))
    state = State(
        available=frozenset(fallback),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )

    def broken(request, state):
        raise ValueError("bug")

    [result] = answer(
        [{"request_id": "r1"}], Split({"v": broken}, {"v": 1}), state, state.available
    )
    assert result["items"] == list(fallback)
    assert result["problems"] == ["model_error"]
    assert result["model_version"] == "v"


def test_answer_tags_each_request_with_the_version_that_answered_it():
    fallback = tuple(f"p_{i:02d}" for i in range(20))
    state = State(
        available=frozenset(fallback),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )
    split = Split(
        {"a": lambda r, s: list(fallback[:10]), "b": lambda r, s: list(fallback[10:])},
        {"a": 1, "b": 1},
    )
    requests = [{"request_id": f"r_{i}"} for i in range(40)]
    for request, result in zip(
        requests, answer(requests, split, state, state.available)
    ):
        assert result["model_version"] == split.version_for(request["request_id"])
        assert result["items"] == list(
            fallback[:10] if result["model_version"] == "a" else fallback[10:]
        )


class ChangingRawTree:
    """A RawTree whose catalogue can be replaced while the loop runs, as the final round may do."""

    def __init__(self, products: list[str]) -> None:
        self.products = products
        self.updates: list[dict] = []

    def catalog(self):
        return [
            {"product_id": p, "price_eur": 1.0, "is_active": True}
            for p in self.products
        ]

    def catalog_updates_since(self, since_ms):
        return [u for u in self.updates if u["ts_ms"] >= since_ms]

    def best_sellers(self):
        return []

    def recent_events(self):
        return []


def test_live_state_picks_up_a_replaced_catalogue_without_a_restart():
    rawtree = ChangingRawTree([f"p_old_{i}" for i in range(10)])
    live = LiveState(rawtree, reload_s=0.1)
    assert live.state.available == set(rawtree.products)
    rawtree.products = [f"p_new_{i}" for i in range(10)]
    deadline = time.monotonic() + 3
    while live.state.available != set(rawtree.products) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert live.state.available == set(rawtree.products)


def test_live_state_forgets_updates_that_were_removed_from_rawtree():
    rawtree = ChangingRawTree([f"p_{i}" for i in range(10)])
    rawtree.updates = [
        {
            "product_id": "p_0",
            "change": "out_of_stock",
            "ts": "2026-11-14 10:00:00",
            "ts_ms": 1,
            "is_active": False,
        }
    ]
    live = LiveState(rawtree, reload_s=0.1)
    assert "p_0" not in live.state.available
    rawtree.updates = []  # the update table starts again with the new data
    deadline = time.monotonic() + 3
    while "p_0" not in live.state.available and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "p_0" in live.state.available


class SlowEventsRawTree(ChangingRawTree):
    """Events take a while to read, and the trend is counted from them."""

    def __init__(self, products: list[str], read_s: float) -> None:
        super().__init__(products)
        self.read_s = read_s
        self.reads = 0

    def recent_events(self):
        self.reads += 1
        time.sleep(self.read_s)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        return [
            {"ts": now, "event_type": "purchase", "product_id": "p_0", "user_id": "u"}
        ]


def test_the_trend_is_attached_to_the_state_and_read_in_the_background():
    rawtree = SlowEventsRawTree([f"p_{i}" for i in range(10)], read_s=0)
    live = LiveState(rawtree, signals_s=0.2)
    assert live.state.trend == {"p_0": 4}
    assert live.state.recent_purchases == {"u": frozenset({"p_0"})}
    reads = rawtree.reads
    time.sleep(1)
    assert rawtree.reads > reads  # read again in the background


def test_a_slow_events_read_never_holds_up_the_stock_refresh():
    rawtree = SlowEventsRawTree([f"p_{i}" for i in range(10)], read_s=0)
    live = LiveState(rawtree, signals_s=0.1)
    rawtree.read_s = 2  # from now on every events read takes 2 s
    time.sleep(0.3)
    oldest_ms = 0
    for _ in range(10):
        time.sleep(0.15)
        oldest_ms = max(oldest_ms, int(time.time() * 1000) - live.refreshed_ms)
    assert oldest_ms < 1000
