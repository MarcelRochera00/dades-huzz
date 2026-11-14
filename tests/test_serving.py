from dades_huzz.serving import decide_role, repair, validate

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
