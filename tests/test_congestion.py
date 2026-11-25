from pipeline import congestion


def test_level_boundaries():
    assert congestion.level(0.0) == "Low"
    assert congestion.level(0.399) == "Low"
    assert congestion.level(0.40) == "Moderate"
    assert congestion.level(0.699) == "Moderate"
    assert congestion.level(0.70) == "High"
    assert congestion.level(0.899) == "High"
    assert congestion.level(0.90) == "Severe"
    assert congestion.level(1.5) == "Severe"


def test_capacity_is_95th_percentile_and_never_zero():
    assert congestion.capacity(range(101)) == 95
    assert congestion.capacity([0, 0, 0]) == 1
