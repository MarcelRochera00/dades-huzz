from dades_huzz.features import category_signals


class FakeRawTree:
    """Answers the catalogue query with a known product and a new one, and the ranking with nothing."""

    def __init__(self):
        self.queries = []

    def query(self, sql, timeout=10):
        self.queries.append(sql)
        if "catalog_updates" in sql:
            return [
                {"product_id": "p_old", "category": "Toys"},
                {"product_id": "p_new", "category": "Fashion"},
            ]
        return []


def test_category_signals_know_the_category_of_products_added_during_the_event():
    # a cold request is one whose last view is a new product: Destroyer needs its category
    signals = category_signals(FakeRawTree(), until="2026-11-14 12:00:00")
    assert signals.category_of == {"p_old": "Toys", "p_new": "Fashion"}


class ProfileRawTree:
    """Answers the profile query with per-category weights for two shoppers."""

    def query(self, sql, timeout=10):
        assert "history_events" in sql and "2026-11-07 07:00:00" in sql
        return [
            {"user_id": "u_1", "category": "Toys", "weight": 30},
            {"user_id": "u_1", "category": "Books", "weight": 10},
            {"user_id": "u_2", "category": "Pets", "weight": 5},
        ]


def test_shopper_profiles_are_each_shoppers_share_of_weight_per_category():
    from dades_huzz.features import shopper_profiles

    profiles = shopper_profiles(ProfileRawTree(), until="2026-11-07 07:00:00")
    assert profiles == {"u_1": {"Toys": 0.75, "Books": 0.25}, "u_2": {"Pets": 1.0}}


class PurchasesRawTree:
    def query(self, sql, timeout=10):
        assert "purchase" in sql and "history_events" in sql
        return [{"user_id": "u_1", "products": ["p_a", "p_b"]}]


def test_shopper_purchases_are_each_shoppers_bought_products():
    from dades_huzz.features import shopper_purchases

    assert shopper_purchases(PurchasesRawTree(), until="2026-11-14 12:00:00") == {
        "u_1": frozenset({"p_a", "p_b"})
    }
