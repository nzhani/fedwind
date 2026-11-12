import pytest

from power_curve import PowerCurve

C = PowerCurve(rated_kw=2000, cut_in=3, rated_speed=12, cut_out=25)


@pytest.mark.parametrize("v,expected", [(0, 0), (2.9, 0), (12, 2000), (20, 2000), (25, 0), (30, 0)])
def test_regions(v, expected):
    assert C.power_kw(v) == expected


def test_monotonic_between_cut_in_and_rated():
    values = [C.power_kw(3 + i * 0.5) for i in range(19)]
    assert values == sorted(values) and 0 <= values[0] < values[-1] <= 2000


def test_never_negative():
    assert all(C.power_kw(v / 10) >= 0 for v in range(-50, 400))


def test_invalid_curve():
    with pytest.raises(ValueError):
        PowerCurve(cut_in=12, rated_speed=3)
