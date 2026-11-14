import time

from dades_huzz.serving.handover import Handover, decide_role

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


class HeartbeatRawTree:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    def server_now_ms(self):
        return int(time.time() * 1000)

    def insert(self, table, rows):
        self.inserted.extend(rows)

    def heartbeats_since(self, since_ms):
        return []


def test_the_heartbeat_carries_the_split_in_force_and_the_versions_left_out():
    rawtree = HeartbeatRawTree()
    Handover(
        rawtree,
        details=lambda: {"versions": "a=50,b=50", "out": "b"},
    )
    beat = rawtree.inserted[0]
    assert beat["kind"] == "heartbeat"
    assert (beat["versions"], beat["out"]) == ("a=50,b=50", "b")
