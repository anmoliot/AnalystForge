from __future__ import annotations

from decimal import Decimal

import pytest

from analystforge.quant.money import (
    discount_factor,
    money,
    quantize,
    rate_to_decimal,
    safe_div,
    safe_ratio,
    to_decimal,
)

D = Decimal


def test_to_decimal_uses_the_shortest_float_representation() -> None:
    assert to_decimal(0.1) == D("0.1")
    assert to_decimal(3) == D("3")
    assert to_decimal("2.50") == D("2.50")
    assert to_decimal(D("4.25")) == D("4.25")


@pytest.mark.parametrize("value", ["not-a-number", float("nan"), float("inf")])
def test_to_decimal_rejects_non_finite_input(value: object) -> None:
    with pytest.raises(ValueError):
        to_decimal(value)  # type: ignore[arg-type]


def test_quantize_uses_bankers_rounding_at_the_half() -> None:
    assert quantize("2.675", 2) == D("2.68")
    assert quantize("2.665", 2) == D("2.66")
    assert quantize("1.005", 2) == D("1.00")
    assert money("10.555") == D("10.56")


def test_quantize_rejects_negative_places() -> None:
    with pytest.raises(ValueError, match="places"):
        quantize("1", -1)


def test_safe_division_returns_none_instead_of_fabricating_zero() -> None:
    assert safe_div(D("10"), D("4")) == D("2.5")
    assert safe_div(None, D("4")) is None
    assert safe_div(D("10"), None) is None
    assert safe_div(D("10"), D("0")) is None
    assert safe_ratio(D("10"), D("4")) == 2.5
    assert safe_ratio(D("10"), D("0")) is None


def test_rate_to_decimal_validates_the_boundary() -> None:
    assert rate_to_decimal(0.08) == D("0.08")
    assert rate_to_decimal(-0.5, name="discount") == D("-0.5")
    with pytest.raises(ValueError, match="discount"):
        rate_to_decimal(-1.0, name="discount")


def test_discount_factor_matches_the_compound_identity() -> None:
    factor = discount_factor(D("0.10"), 2)
    assert factor == D(1) / (D("1.10") ** 2)
    assert discount_factor(D("0.10"), 0) == D(1)
    with pytest.raises(ValueError, match="rate"):
        discount_factor(D("-1"), 1)
    with pytest.raises(ValueError, match="exponent"):
        discount_factor(D("0.10"), -1)
