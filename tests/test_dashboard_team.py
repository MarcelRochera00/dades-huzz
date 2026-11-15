from datetime import UTC, datetime, timedelta

from dades_huzz.dashboard_jury import JuryBucket
from dades_huzz.dashboard_splits import SplitPeriod
from dades_huzz.dashboard_team import confirmed_practice_series, read_active_split


def test_practice_history_uses_confirmed_displays_and_preserves_traffic_gaps():
    end = datetime(2026, 11, 15, 9, tzinfo=UTC)
    start = end - timedelta(hours=6)
    start_ms = int(start.timestamp() * 1000)
    rows = [
        JuryBucket("a", start_ms, 100, 1, 0),
        JuryBucket("a", start_ms + 600_000, 300, 9, 0),
        JuryBucket("b", start_ms + 1_200_000, 40, 0, 0),
        JuryBucket("b", start_ms + 1_800_000, 20, 1, 0),
        JuryBucket("final-only", int(end.timestamp() * 1000), 100, 20, 0),
    ]
    splits = [
        SplitPeriod(start, start + timedelta(minutes=20), "a=50,b=50", (), "heartbeat"),
        SplitPeriod(
            start + timedelta(minutes=30),
            start + timedelta(minutes=40),
            "a=50,b=50",
            ("a",),
            "heartbeat",
        ),
    ]
    points = confirmed_practice_series(rows, start, end, splits)
    assert len(points) == 24
    assert {point["model_version"] for point in points} == {"a", "b"}
    assert points[0] == {
        "bucket_start": start,
        "bucket_end": start + timedelta(minutes=30),
        "model_version": "a",
        "purchases_per_100": 2.5,
        "requests": 400,
        "overlap": True,
    }
    assert points[1]["purchases_per_100"] == 0
    assert points[2]["purchases_per_100"] is None
    assert points[2]["requests"] is None
    assert not points[2]["overlap"]
    assert points[3]["purchases_per_100"] == 5.0
    assert points[-1]["bucket_end"] == end


class ServingRecords:
    team = "team_02"

    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, timeout):
        return self.rows


def heartbeat(at, loop_id, role, configuration, paused="", started_ms=1):
    return {
        "loop_id": loop_id,
        "started_ms": started_ms,
        "role": role,
        "configuration": configuration,
        "paused": paused,
        "heartbeat_ms": int(at.timestamp() * 1000),
    }


def test_active_split_reports_the_planned_shares_and_paused_versions():
    now = datetime(2026, 11, 15, 9, 20, tzinfo=UTC)
    heartbeat_at = now - timedelta(seconds=2)
    records = ServingRecords(
        [
            heartbeat(
                heartbeat_at,
                "first",
                "active",
                "pair:lauri-omni-plain+lauri-titan-plus-als=3,lauri-titan-plus=1",
                paused="lauri-titan-plus",
            )
        ]
    )
    active = read_active_split(records, now)
    assert active is not None
    assert active.heartbeat_at == heartbeat_at
    assert list(active.shares.items()) == [
        ("pair:lauri-omni-plain+lauri-titan-plus-als", 3),
        ("lauri-titan-plus", 1),
    ]
    assert active.paused == ("lauri-titan-plus",)


def test_active_split_does_not_report_an_old_heartbeat_as_current():
    now = datetime(2026, 11, 15, 9, 20, tzinfo=UTC)
    records = ServingRecords(
        [
            heartbeat(
                now - timedelta(seconds=7), "first", "active", "lauri-titan-plus=100"
            )
        ]
    )
    assert read_active_split(records, now) is None


def test_active_split_uses_each_loops_latest_role_and_prefers_the_oldest_active_loop():
    now = datetime(2026, 11, 15, 9, 20, tzinfo=UTC)
    records = ServingRecords(
        [
            heartbeat(now - timedelta(seconds=1), "demoted", "standby", "a=100"),
            heartbeat(
                now - timedelta(seconds=2), "newer", "active", "b=100", started_ms=3
            ),
            heartbeat(now - timedelta(seconds=3), "demoted", "active", "a=100"),
            heartbeat(
                now - timedelta(seconds=4), "older", "active", "c=100", started_ms=2
            ),
        ]
    )
    active = read_active_split(records, now)
    assert active is not None
    assert active.shares == {"c": 100}
