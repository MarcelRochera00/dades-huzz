from dades_huzz.serving.trends import SubcategoryHeat

MIN = 60_000


def steady_day(heat, minutes=120):
    """Two hours of an even day: Kettles 1 purchase a minute, Books 9."""
    for m in range(minutes):
        heat.add(
            [(m * MIN, "Kettles")] + [(m * MIN + i, "Books") for i in range(1, 10)]
        )


def test_an_even_day_has_no_hot_subcategory():
    heat = SubcategoryHeat()
    steady_day(heat)
    assert heat.hot(now_ms=120 * MIN) == {}


def test_a_subcategory_selling_far_above_its_normal_is_hot_with_its_ratio():
    heat = SubcategoryHeat()
    steady_day(heat)
    burst = [
        (120 * MIN + i * 20_000, "Kettles") for i in range(45)
    ]  # 45 extra in 15 min
    heat.add(burst)
    hot = heat.hot(now_ms=135 * MIN)
    assert set(hot) == {"Kettles"}
    assert hot["Kettles"] >= 2.0


def test_a_small_spike_is_not_hot_however_large_the_ratio():
    heat = SubcategoryHeat()
    steady_day(heat)
    heat.add(
        [(125 * MIN, "Aquariums")] * 1 + [(126 * MIN, "Aquariums")]
    )  # 2 of a rare one
    assert "Aquariums" not in heat.hot(now_ms=130 * MIN)


def test_a_burst_cools_down_once_it_leaves_the_window():
    heat = SubcategoryHeat()
    steady_day(heat)
    heat.add([(120 * MIN + i * 20_000, "Kettles") for i in range(45)])
    assert "Kettles" in heat.hot(now_ms=135 * MIN)
    assert "Kettles" not in heat.hot(now_ms=160 * MIN)


def test_the_backfilled_window_is_not_counted_twice_in_the_day():
    heat = SubcategoryHeat()
    heat.add_day(
        {"Books": 900, "Kettles": 100}
    )  # the day before the cut, window included
    heat.add([(i * 1000, "Kettles") for i in range(10)], count_in_day=False)
    assert heat.day == {"Books": 900, "Kettles": 100}
    assert len(heat.window) == 10


def test_a_subcategory_new_today_is_hot_once_it_sells_enough():
    heat = SubcategoryHeat()
    steady_day(heat)
    heat.add([(120 * MIN + i * 20_000, "Smart Rings") for i in range(30)])
    assert "Smart Rings" in heat.hot(now_ms=135 * MIN)
