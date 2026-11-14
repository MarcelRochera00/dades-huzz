from dades_huzz.data import (
    RequestCursor,
    UpdateLog,
    as_request,
    current_state,
    recently_changed,
)

CATALOG = [
    {"product_id": "p_a", "price_eur": 10.0, "is_active": True},
    {"product_id": "p_b", "price_eur": 20.0, "is_active": True},
    {"product_id": "p_off", "price_eur": 5.0, "is_active": False},
]


def update(product_id, change, ts, price=10.0, active=True):
    return {
        "product_id": product_id,
        "change": change,
        "ts": ts,
        "price_eur": price,
        "is_active": active,
    }


def test_out_of_stock_is_unavailable_until_back_in_stock():
    out = [update("p_a", "out_of_stock", "2026-11-14 10:00:00", active=False)]
    assert current_state(CATALOG, out, []).available == {"p_b"}
    back = out + [update("p_a", "back_in_stock", "2026-11-14 10:05:00")]
    assert current_state(CATALOG, back, []).available == {"p_a", "p_b"}


def test_latest_change_wins_whatever_order_rows_arrive_in():
    rows = [
        update("p_a", "back_in_stock", "2026-11-14 10:05:00"),
        update("p_a", "out_of_stock", "2026-11-14 10:09:00", active=False),
    ]
    assert "p_a" not in current_state(CATALOG, rows, []).available


def test_price_change_does_not_bring_back_an_out_of_stock_product():
    rows = [
        update("p_a", "out_of_stock", "2026-11-14 10:00:00", active=False),
        update("p_a", "price_change", "2026-11-14 10:01:00", price=8.0),
    ]
    state = current_state(CATALOG, rows, [])
    assert "p_a" not in state.available
    assert state.price["p_a"] == 8.0


def test_new_products_are_available_and_marked_new():
    rows = [update("p_new", "new_product", "2026-11-14 10:00:00", price=3.5)]
    state = current_state(CATALOG, rows, [])
    assert state.available == {"p_a", "p_b", "p_new"}
    assert state.new_products == {"p_new"}
    assert state.price["p_new"] == 3.5


def test_every_product_has_its_category_including_products_added_during_the_event():
    catalog = [
        {**CATALOG[0], "category": "Pets", "subcategory": "Pet Beds"},
        {**CATALOG[1], "category": "Beauty", "subcategory": "Shampoo"},
    ]
    rows = [
        {
            **update("p_new", "new_product", "2026-11-14 10:00:00"),
            "category": "Pets",
            "subcategory": "Pet Toys",
        }
    ]
    state = current_state(catalog, rows, [])
    assert state.category == {"p_a": "Pets", "p_b": "Beauty", "p_new": "Pets"}
    assert state.subcategory == {
        "p_a": "Pet Beds",
        "p_b": "Shampoo",
        "p_new": "Pet Toys",
    }


def test_a_row_without_a_category_keeps_the_one_already_known():
    catalog = [{**CATALOG[0], "category": "Pets", "subcategory": "Pet Beds"}]
    rows = [update("p_a", "price_change", "2026-11-14 10:01:00", price=8.0)]
    state = current_state(catalog, rows, [])
    assert state.category == {"p_a": "Pets"}
    assert state.subcategory == {"p_a": "Pet Beds"}


def test_fallback_is_the_best_sellers_that_are_available_in_order():
    out = [update("p_a", "out_of_stock", "2026-11-14 10:00:00", active=False)]
    assert current_state(CATALOG, out, ["p_off", "p_a", "p_b", "p_gone"]).fallback == (
        "p_b",
    )


def test_request_context_is_nested_as_the_contract_says():
    row = {
        "request_id": "r1",
        "ts": "2026-11-14 11:00:00.000",
        "ts_ms": 1,
        "user_id": "u1",
        "is_new_user": True,
        "device": "ios",
        "region": "Catalunya",
        "page": "home",
        "recent_views": None,
    }
    request = as_request(row)
    assert request["context"] == {
        "device": "ios",
        "region": "Catalunya",
        "page": "home",
    }
    assert request["recent_views"] == []


def req(request_id, ts_ms):
    return {"request_id": request_id, "ts_ms": ts_ms}


def test_cursor_returns_each_request_once_across_overlapping_polls():
    cursor = RequestCursor(max_age_ms=2700)
    assert [
        r["request_id"]
        for r in cursor.accept([req("r1", 1000), req("r2", 1300)], now_ms=1500)
    ] == ["r1", "r2"]
    assert [
        r["request_id"]
        for r in cursor.accept([req("r2", 1300), req("r3", 1600)], now_ms=1800)
    ] == ["r3"]


def test_cursor_keeps_a_request_that_shows_up_after_a_newer_one():
    cursor = RequestCursor(max_age_ms=2700)
    cursor.accept([req("r2", 1300)], now_ms=1500)
    assert [
        r["request_id"]
        for r in cursor.accept([req("r1", 1000), req("r2", 1300)], now_ms=1600)
    ] == ["r1"]


def test_cursor_skips_requests_too_old_to_answer_in_time():
    cursor = RequestCursor(max_age_ms=2700)
    fresh = cursor.accept([req("old", 1000), req("new", 3000)], now_ms=3800)
    assert [r["request_id"] for r in fresh] == ["new"]
    assert cursor.skipped == 1


def test_cursor_polls_every_request_still_answerable_in_time():
    cursor = RequestCursor(max_age_ms=2700)
    assert cursor.since_ms(now_ms=10_000) == 7300


def test_cursor_never_returns_a_request_another_loop_already_answered():
    cursor = RequestCursor(max_age_ms=2700)
    cursor.mark_answered(["r1"], now_ms=1100)
    assert [
        r["request_id"]
        for r in cursor.accept([req("r1", 1000), req("r2", 1050)], now_ms=1200)
    ] == ["r2"]


def stock(product_id, change, ts_ms):
    return {
        "product_id": product_id,
        "change": change,
        "ts_ms": ts_ms,
        "ts": str(ts_ms),
    }


def test_products_whose_stock_changed_in_the_window_are_recent_whatever_the_direction():
    rows = [
        stock("p_out", "out_of_stock", 95_000),
        stock("p_back", "back_in_stock", 99_000),
        stock("p_old", "out_of_stock", 80_000),
        stock("p_price", "price_change", 99_500),
    ]
    assert recently_changed(rows, now_ms=100_000, window_ms=10_000) == {
        "p_out",
        "p_back",
    }


def test_update_log_keeps_each_update_once_across_overlapping_reads():
    log = UpdateLog(overlap_ms=10_000)
    first = [stock("p_a", "out_of_stock", 50_000), stock("p_b", "price_change", 60_000)]
    assert log.add(first) == first
    again = [
        stock("p_b", "price_change", 60_000),
        stock("p_c", "back_in_stock", 61_000),
    ]
    assert log.add(again) == [stock("p_c", "back_in_stock", 61_000)]
    assert len(log.rows) == 3


def test_update_log_reads_again_from_a_bit_before_the_newest_update():
    log = UpdateLog(overlap_ms=10_000)
    assert log.since_ms(now_ms=100_000) == 0
    log.add([stock("p_a", "out_of_stock", 50_000)])
    assert log.since_ms(now_ms=100_000) == 40_000


def test_an_update_stamped_in_the_future_does_not_hide_older_ones_landing_late():
    log = UpdateLog(overlap_ms=10_000)
    log.add([stock("p_future", "price_change", 500_000)])
    assert log.since_ms(now_ms=100_000) == 90_000


def test_two_price_changes_in_the_same_millisecond_are_both_kept():
    log = UpdateLog(overlap_ms=10_000)
    first = {**stock("p_a", "price_change", 50_000), "price_eur": 10.0}
    second = {**stock("p_a", "price_change", 50_000), "price_eur": 12.0}
    assert log.add([first, second]) == [first, second]


def test_a_change_stamped_after_our_clock_still_counts_as_recent():
    rows = [stock("p_back", "back_in_stock", 100_400)]
    assert recently_changed(rows, now_ms=100_000, window_ms=10_000) == {"p_back"}


def test_an_update_without_price_keeps_the_last_known_price():
    rows = [
        update("p_a", "out_of_stock", "2026-11-14 10:00:00", price=None, active=False)
    ]
    state = current_state(CATALOG, rows, [])
    assert state.price["p_a"] == 10.0
    assert "p_a" not in state.available
