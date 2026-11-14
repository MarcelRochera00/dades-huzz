from datetime import UTC, datetime

from dades_huzz.dashboard_splits import SplitPeriod, read_split_stats
from dades_huzz.dashboard_team import read_cold_groups


class FakeRawTree:
    team = "team_test"

    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def query(self, sql, timeout=None):
        self.sql = sql
        return self.rows


def test_cold_requests_and_purchases_are_counted_per_assigned_version():
    period = SplitPeriod(
        datetime(2026, 11, 14, 17, tzinfo=UTC),
        datetime(2026, 11, 14, 18, tzinfo=UTC),
        "a=50,b=50",
        (),
        "heartbeat",
    )
    row = {"actual": "a", "shown_by": "team", "revenue_eur": 0.0}
    rawtree = FakeRawTree(
        [
            {
                **row,
                "assigned_index": 1,
                "finished": 1,
                "requests": 10,
                "purchases": 2,
                "cold_requests": 4,
                "cold_purchases": 1,
            },
            {
                **row,
                "assigned_index": 1,
                "finished": 0,
                "requests": 3,
                "purchases": 0,
                "cold_requests": 2,
                "cold_purchases": 0,
            },
            {
                **row,
                "actual": "b",
                "assigned_index": 2,
                "finished": 1,
                "requests": 8,
                "purchases": 1,
                "cold_requests": 5,
                "cold_purchases": 1,
            },
        ]
    )

    a, b = read_split_stats(rawtree, period).rows

    assert (a.cold_completed, a.cold_purchases) == (4, 1)
    assert (b.cold_completed, b.cold_purchases) == (5, 1)
    assert "new_product" in rawtree.sql and "is_new_user" in rawtree.sql


def test_the_cold_groups_query_is_built_from_the_shared_cold_definition():
    rawtree = FakeRawTree(
        [
            {
                "group_name": "Both",
                "requests": 3,
                "completed": 2,
                "pending": 1,
                "purchases": 1,
            }
        ]
    )

    groups = read_cold_groups(rawtree, datetime(2026, 11, 14, 18, tzinfo=UTC))

    assert "{" not in rawtree.sql.replace("{team}", "")
    assert "new_shopper" in rawtree.sql and "viewed_new_product" in rawtree.sql
    assert next(g for g in groups if g["group"] == "Both")["purchases"] == 1
