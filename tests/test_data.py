from dades_huzz.data import RequestCursor, as_request, current_state

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
