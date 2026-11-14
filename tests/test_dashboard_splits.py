from datetime import UTC, datetime

from dades_huzz.dashboard_splits import (
    HISTORICAL_SPLITS,
    SplitPeriod,
    read_split_stats,
    version_style,
)
from dades_huzz.serving.versions import VERSIONS, parse_split


class FakeRawTree:
    team = "team_test"

    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def query(self, sql, timeout=None):
        self.sql = sql
        return self.rows


def test_every_live_and_historical_version_has_its_own_colour_and_description():
    names = set(VERSIONS) | {
        name for _, split in HISTORICAL_SPLITS for name in parse_split(split)
    }
    styles = {name: version_style(name) for name in names}
    for name, (colour, description) in styles.items():
        assert colour.startswith("#"), name
        assert description and description != version_style("not-a-version")[1], name
    live = [styles[name][0] for name in VERSIONS if not name.startswith("tati-0")]
    assert len(set(live)) == len(live), "two live versions share a colour"


def test_an_unknown_version_gets_a_neutral_style_instead_of_failing():
    colour, description = version_style("some-new-version")
    assert colour.startswith("#")
    assert description


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
