from dades_huzz.serving import repair, validate

AVAILABLE = {f"p_{i:02d}" for i in range(20)}
TEN = [f"p_{i:02d}" for i in range(10)]


def test_ten_distinct_available_products_are_valid():
    assert validate(TEN, AVAILABLE) == []


def test_invalid_answer_reports_every_reason():
    items = ["p_00", "p_00", "p_gone"] + TEN[1:6]
    assert validate(items, AVAILABLE) == ["duplicate", "unavailable", "wrong_size"]


def test_repair_keeps_valid_items_in_order_and_pads_from_fallback():
    items = ["p_05", "p_05", "p_gone", "p_03"]
    fallback = [
        "p_03",
        "p_gone_too",
        "p_11",
        "p_12",
        "p_13",
        "p_14",
        "p_15",
        "p_16",
        "p_17",
        "p_18",
        "p_19",
    ]
    assert repair(items, AVAILABLE, fallback) == [
        "p_05",
        "p_03",
        "p_11",
        "p_12",
        "p_13",
        "p_14",
        "p_15",
        "p_16",
        "p_17",
        "p_18",
    ]


def test_repair_cuts_long_answers_to_ten():
    assert repair(TEN + ["p_15"], AVAILABLE, []) == TEN
