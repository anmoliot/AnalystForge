from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from analystforge.quant.returns import (
    annualize_returns,
    cagr,
    cumulative_return,
    log_returns,
    simple_returns,
    twr,
    wealth_index,
    xirr,
)

D = Decimal


def test_log_and_simple_returns_preserve_the_index() -> None:
    prices = pd.Series([100.0, 110.0, 121.0], index=pd.date_range("2024-01-01", periods=3))
    logged = log_returns(prices)
    simple = simple_returns(prices)

    assert list(logged.index) == list(prices.index[1:])
    assert logged.iloc[0] == pytest.approx(math.log(1.1))
    assert simple.iloc[0] == pytest.approx(0.1)
    assert simple.iloc[1] == pytest.approx(0.1)


def test_wealth_index_and_cumulative_return() -> None:
    prices = pd.Series([50.0, 75.0, 100.0])
    wealth = wealth_index(prices, base=100.0)
    assert list(wealth) == [100.0, 150.0, 200.0]
    assert cumulative_return(prices) == pytest.approx(1.0)


def test_annualize_returns_compounds_geometrically() -> None:
    returns = pd.Series([0.10, -0.05])
    expected = (1.10 * 0.95) ** (252 / 2) - 1.0
    assert annualize_returns(returns) == pytest.approx(expected)
    assert annualize_returns(returns, periods_per_year=2) == pytest.approx(1.045 - 1.0)


def test_cagr_uses_the_number_of_price_intervals() -> None:
    prices = pd.Series([100.0, 110.0, 121.0])
    assert cagr(prices, periods_per_year=1) == pytest.approx(0.10)
    assert cagr(pd.Series([100.0, 121.0]), periods_per_year=2) == pytest.approx(1.21**2 - 1.0)


def test_twr_links_subperiods_around_cash_flows() -> None:
    nav_series = [
        (date(2024, 1, 1), D("100")),
        (date(2024, 2, 1), D("120")),
        (date(2024, 3, 1), D("110")),
    ]
    cashflows = [(date(2024, 1, 1), D("-100")), (date(2024, 2, 1), D("20"))]
    result = twr(cashflows, nav_series)
    assert float(result) == pytest.approx(-1.0 / 12.0)


def test_twr_allows_exactly_minus_one_hundred_percent() -> None:
    nav_series = [(date(2024, 1, 1), D("100")), (date(2024, 1, 2), D("100"))]
    cashflows = [(date(2024, 1, 1), D("-100")), (date(2024, 1, 2), D("100"))]
    assert twr(cashflows, nav_series) == D("-1")


def test_twr_validation() -> None:
    with pytest.raises(ValueError, match="at least two"):
        twr([], [(date(2024, 1, 1), D("100"))])
    with pytest.raises(ValueError, match="duplicate"):
        twr(
            [],
            [(date(2024, 1, 1), D("100")), (date(2024, 1, 1), D("110"))],
        )
    with pytest.raises(ValueError, match="ascending"):
        twr(
            [],
            [(date(2024, 2, 1), D("100")), (date(2024, 1, 1), D("110"))],
        )
    with pytest.raises(ValueError, match="positive"):
        twr([], [(date(2024, 1, 1), D("100")), (date(2024, 2, 1), D("0"))])
    with pytest.raises(ValueError, match="NAV date"):
        twr(
            [(date(2024, 1, 15), D("10"))],
            [(date(2024, 1, 1), D("100")), (date(2024, 2, 1), D("110"))],
        )
    with pytest.raises(ValueError, match="below -100%"):
        twr(
            [(date(2024, 2, 1), D("300"))],
            [(date(2024, 1, 1), D("100")), (date(2024, 2, 1), D("100"))],
        )


def test_xirr_matches_the_excel_example() -> None:
    cashflows = [
        (date(2008, 1, 1), D("-10000")),
        (date(2008, 3, 1), D("2750")),
        (date(2008, 10, 30), D("4250")),
        (date(2009, 2, 15), D("3250")),
        (date(2009, 4, 1), D("2750")),
    ]
    assert xirr(cashflows) == pytest.approx(D("0.373362535"), abs=D("1e-8"))


def test_xirr_finds_a_zero_rate_for_a_simple_return_of_capital() -> None:
    cashflows = [
        (date(2024, 1, 1), D("-1000")),
        (date(2025, 1, 1), D("500")),
        (date(2026, 1, 1), D("500")),
    ]
    assert xirr(cashflows) == pytest.approx(D("0"), abs=D("1e-6"))


def test_xirr_validation() -> None:
    with pytest.raises(ValueError, match="empty"):
        xirr([])
    with pytest.raises(ValueError, match="two distinct dates"):
        xirr([(date(2024, 1, 1), D("-1")), (date(2024, 1, 1), D("1"))])
    with pytest.raises(ValueError, match="positive and negative"):
        xirr([(date(2024, 1, 1), D("1")), (date(2024, 1, 2), D("2"))])
    with pytest.raises(ValueError, match="finite"):
        xirr([(date(2024, 1, 1), D("-1")), (date(2024, 1, 2), D("NaN"))])
    with pytest.raises(ValueError, match="could not find a root"):
        xirr(
            [
                (date(2024, 1, 1), D("-100")),
                (date(2024, 1, 2), D("1")),
                (date(2024, 1, 3), D("-2000")),
            ]
        )


def test_price_validation_is_shared_across_return_functions() -> None:
    with pytest.raises(ValueError, match="at least"):
        simple_returns(pd.Series([], dtype=float))
    with pytest.raises(ValueError, match="finite"):
        log_returns(pd.Series([100.0, float("nan")]))
    with pytest.raises(ValueError, match="strictly positive"):
        cumulative_return(pd.Series([100.0, -1.0]))
    with pytest.raises(ValueError, match="base"):
        wealth_index(pd.Series([100.0, 110.0]), base=0.0)
    with pytest.raises(ValueError, match="periods_per_year"):
        annualize_returns(pd.Series([0.01]), periods_per_year=0)
    with pytest.raises(ValueError, match="empty"):
        annualize_returns(pd.Series([], dtype=float))
    with pytest.raises(ValueError, match="greater than -100%"):
        annualize_returns(pd.Series([-1.0, 0.0]))


def test_returns_of_a_constant_series_are_zero() -> None:
    prices = pd.Series([100.0, 100.0, 100.0])
    assert np.allclose(simple_returns(prices), 0.0)
    assert np.allclose(log_returns(prices), 0.0)
    assert annualize_returns(simple_returns(prices)) == pytest.approx(0.0)
