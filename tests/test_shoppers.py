from dades_huzz.serving.shoppers import SHARDS, ShopperDay, read_backfill

CATEGORY = {"p_toy1": "Toys", "p_toy2": "Toys", "p_tv": "Electronics"}.get


def event(user, product, kind, t):
    return {"u": user, "p": product, "e": kind, "t": t}


def test_categories_count_views_and_weigh_carts_more():
    day = ShopperDay()
    day.add(
        [
            event("u1", "p_toy1", "view", 1),
            event("u1", "p_toy2", "view", 2),
            event("u1", "p_tv", "add_to_cart", 3),
        ],
        CATEGORY,
    )
    categories, _, _ = day.snapshot()
    assert categories == {"u1": {"Toys": 2, "Electronics": 3}}


def test_carted_products_leave_once_bought():
    day = ShopperDay()
    day.add(
        [
            event("u1", "p_toy1", "add_to_cart", 1),
            event("u1", "p_tv", "add_to_cart", 2),
            event("u1", "p_tv", "purchase", 3),
        ],
        CATEGORY,
    )
    _, carted, _ = day.snapshot()
    assert carted == {"u1": frozenset({"p_toy1"})}


def test_viewed_products_are_the_latest_first_without_repeats_and_capped():
    day = ShopperDay(viewed_max=3)
    views = ["p_a", "p_b", "p_c", "p_a", "p_d"]
    day.add([event("u1", p, "view", t) for t, p in enumerate(views)], CATEGORY)
    _, _, viewed = day.snapshot()
    assert viewed == {"u1": ("p_d", "p_a", "p_c")}


def test_a_row_read_twice_counts_once():
    day = ShopperDay()
    rows = [event("u1", "p_toy1", "view", 5)]
    day.add(rows, CATEGORY)
    day.add(rows + [event("u1", "p_toy2", "view", 6)], CATEGORY)
    categories, _, _ = day.snapshot()
    assert categories == {"u1": {"Toys": 2}}


def test_a_snapshot_does_not_change_when_more_events_arrive():
    day = ShopperDay()
    day.add([event("u1", "p_toy1", "view", 1)], CATEGORY)
    before = day.snapshot()
    day.add(
        [event("u1", "p_toy2", "view", 2), event("u2", "p_tv", "view", 3)], CATEGORY
    )
    assert before == ({"u1": {"Toys": 1}}, {}, {"u1": ("p_toy1",)})


def test_the_backfill_sits_under_newer_live_events():
    day = ShopperDay()
    day.add(
        [event("u1", "p_tv", "view", 100), event("u1", "p_toy1", "purchase", 101)],
        CATEGORY,
    )
    day.add_backfill(
        categories=[{"u": "u1", "c": "Toys", "n": 4}],
        carted=[{"u": "u1", "p": "p_toy1"}, {"u": "u1", "p": "p_toy2"}],
        viewed=[{"u": "u1", "v": ["p_toy1", "p_tv"]}],
    )
    categories, carted, viewed = day.snapshot()
    assert categories == {"u1": {"Toys": 4, "Electronics": 1}}
    assert carted == {
        "u1": frozenset({"p_toy2"})
    }  # p_toy1 was bought after the backfill's cut
    assert viewed == {"u1": ("p_tv", "p_toy1")}


def test_an_event_of_an_unknown_product_still_counts_as_viewed():
    day = ShopperDay()
    day.add([event("u1", "p_new", "view", 1)], CATEGORY)
    categories, _, viewed = day.snapshot()
    assert categories == {}
    assert viewed == {"u1": ("p_new",)}


class CountingRawTree:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, sql, timeout=10):
        self.queries.append(sql)
        return []


def test_the_backfill_reads_every_kind_in_slices_and_freezes_after_each():
    rawtree, freezes = CountingRawTree(), []
    read_backfill(rawtree, until_ms=1_000, after_each=lambda: freezes.append(1))
    # categories, carts and views, each in SHARDS slices
    assert len(rawtree.queries) == 3 * SHARDS
    assert all(f"% {SHARDS} = " in sql for sql in rawtree.queries)
    assert len(freezes) == 3 * SHARDS


def test_add_returns_only_the_rows_it_had_not_counted_yet():
    day = ShopperDay()
    rows = [event("u1", "p_toy1", "view", 5)]
    assert day.add(rows, CATEGORY) == rows
    assert day.add(rows + [event("u1", "p_toy2", "purchase", 6)], CATEGORY) == [
        event("u1", "p_toy2", "purchase", 6)
    ]
