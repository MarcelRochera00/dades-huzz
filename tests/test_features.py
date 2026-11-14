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
