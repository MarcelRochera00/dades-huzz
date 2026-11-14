from datetime import UTC, datetime

from dades_huzz.dashboard_jury import read_demand_trends


def test_jury_ranks_subcategories_by_purchase_share_multiplier():
    end = datetime(2026, 11, 14, 20, tzinfo=UTC)
    end_ms = int(end.timestamp() * 1000)

    class RecordedStore:
        def catalog(self):
            return [
                {
                    "product_id": "regular",
                    "subcategory": "Books",
                    "is_active": True,
                    "price_eur": 10,
                },
                {
                    "product_id": "kettle",
                    "subcategory": "Kettles",
                    "is_active": True,
                    "price_eur": 20,
                },
            ]

        def catalog_updates(self):
            return [
                {
                    "product_id": "game",
                    "subcategory": "Game Consoles",
                    "change": "new_product",
                    "ts": "2026-11-14 17:30:00",
                    "ts_ms": end_ms - 9_000_000,
                },
            ]

        def query(self, sql, timeout=None):
            if "AS ts_ms" in sql:
                assert f"< fromUnixTimestamp64Milli(toInt64({end_ms}))" in sql
                return self.catalog_updates()
            if "GROUP BY s" in sql:
                return [
                    {"s": "Books", "n": 850},
                    {"s": "Kettles", "n": 100},
                    {"s": "Game Consoles", "n": 50},
                ]
            return [
                {"p": product, "t": end_ms - 60_000 + i}
                for product, count in [
                    ("regular", 21),
                    ("kettle", 40),
                    ("game", 38),
                    ("unlisted", 1),
                ]
                for i in range(count)
            ]

    assert read_demand_trends(RecordedStore(), end) == [
        ("Game Consoles", 7.68),
        ("Kettles", 4.04),
    ]
