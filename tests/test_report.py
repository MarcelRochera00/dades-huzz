from dades_huzz.serving.report import conversion_interval_pct


def test_conversion_interval_matches_a_worked_example():
    low, high = conversion_interval_pct(purchases=10, requests=1000)
    assert round(low, 2) == 0.54
    assert round(high, 2) == 1.83
