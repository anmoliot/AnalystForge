"""Decimal money and ratio-boundary helpers.

Accounting and valuation values stay in :class:`~decimal.Decimal` here; statistical
functions convert to ``float`` explicitly at their own boundary. All quantisation is
explicit and uses banker's rounding unless a caller asks otherwise.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Final

ZERO: Final[Decimal] = Decimal("0")
ONE: Final[Decimal] = Decimal("1")
HUNDRED: Final[Decimal] = Decimal("100")


def to_decimal(value: Decimal | int | str | float) -> Decimal:
    """Convert a finite numeric value to ``Decimal`` without binary-float noise."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid decimal value: {value!r}") from exc
    else:
        result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"Decimal value must be finite, got {value!r}")
    return result


def quantize(
    value: Decimal | int | str | float,
    places: int = 2,
    *,
    rounding: str = ROUND_HALF_EVEN,
) -> Decimal:
    """Quantise a value to a fixed number of decimal places.

    ``rounding`` accepts the decimal module constants, which are strings.
    """
    if places < 0:
        raise ValueError("places must be non-negative")
    quantum = Decimal(1).scaleb(-places)
    return to_decimal(value).quantize(quantum, rounding=rounding)


def money(value: Decimal | int | str | float, places: int = 2) -> Decimal:
    """Quantise a currency amount for display or reporting."""
    return quantize(value, places)


def safe_div(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> Decimal | None:
    """Divide two decimals, returning ``None`` for missing inputs or a zero denominator."""
    if numerator is None or denominator is None or denominator == ZERO:
        return None
    return numerator / denominator


def safe_ratio(
    numerator: Decimal | None,
    denominator: Decimal | None,
) -> float | None:
    """Divide two decimals as a statistical ratio, returning ``None`` when undefined."""
    result = safe_div(numerator, denominator)
    return None if result is None else float(result)


def rate_to_decimal(rate: float, *, name: str = "rate") -> Decimal:
    """Convert a finite rate to Decimal, rejecting non-finite values and rates below -100%."""
    decimal_rate = to_decimal(rate)
    if decimal_rate <= Decimal("-1"):
        raise ValueError(f"{name} must be greater than -100%")
    return decimal_rate


def discount_factor(
    rate: Decimal,
    exponent: Decimal | int,
) -> Decimal:
    """Discount factor ``1 / (1 + rate) ** exponent`` for a rate above -100%."""
    if rate <= Decimal("-1"):
        raise ValueError("rate must be greater than -100%")
    decimal_exponent = to_decimal(exponent)
    if decimal_exponent < ZERO:
        raise ValueError("exponent must be non-negative")
    return ONE / ((ONE + rate) ** decimal_exponent)
