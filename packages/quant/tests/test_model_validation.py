"""Validate invalid assumptions at the public quantitative model boundaries."""

from dataclasses import replace
from decimal import Decimal

import pandas as pd
import pytest

from analystforge.quant import rolling
from analystforge.quant.backtest.overfitting import (
    check_lookahead_bias,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)
from analystforge.quant.black_litterman import black_litterman
from analystforge.quant.ddm import MultiStageDDMAssumptions, gordon_growth_ddm
from analystforge.quant.factors import fama_french_regression
from analystforge.quant.fcfe import FCFEAssumptions, TerminalValueMethod
from analystforge.quant.optimization import OptimizationError, max_sharpe, min_variance
from analystforge.quant.rebalance import generate_rebalance_trades
from analystforge.quant.residual_income import (
    ResidualIncomeAssumptions,
    ResidualIncomeTerminalMethod,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"base_net_income": Decimal(0)},
        {"base_net_income": Decimal("NaN")},
        {"net_income_growth": ()},
        {"net_income_growth": (Decimal(-1),)},
        {"cost_of_equity": Decimal(-1)},
        {"shares_outstanding": Decimal(0)},
        {"terminal_growth": Decimal("0.2")},
        {"exit_multiple": Decimal(10)},
        {"terminal_method": TerminalValueMethod.EXIT_MULTIPLE},
        {"terminal_method": TerminalValueMethod.EXIT_MULTIPLE, "exit_multiple": Decimal(0)},
    ],
)
def test_fcfe_rejects_invalid_assumptions(changes):
    valid = FCFEAssumptions(
        Decimal(100), (Decimal("0.05"),), Decimal("0.1"), Decimal("0.02"), Decimal(10)
    )
    with pytest.raises(ValueError):
        replace(valid, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"base_book_value": Decimal(0)},
        {"base_book_value": Decimal("Infinity")},
        {"forecast_net_income": ()},
        {"forecast_net_income": (Decimal("NaN"),)},
        {"cost_of_equity": Decimal(-1)},
        {"shares_outstanding": Decimal(0)},
        {"dividend_payout_ratio": Decimal(2)},
        {
            "terminal_method": ResidualIncomeTerminalMethod.GORDON_GROWTH,
            "terminal_growth": Decimal("0.2"),
        },
        {
            "terminal_method": ResidualIncomeTerminalMethod.PERSISTENCE_FACTOR,
            "persistence_factor": Decimal(2),
        },
    ],
)
def test_residual_income_rejects_invalid_assumptions(changes):
    valid = ResidualIncomeAssumptions(Decimal(100), (Decimal(10),), Decimal("0.1"), Decimal(10))
    with pytest.raises(ValueError):
        replace(valid, **changes)


@pytest.mark.parametrize(
    "values", [(0, ".1", ".02"), ("NaN", ".1", ".02"), (1, -1, ".02"), (1, ".1", ".2")]
)
def test_gordon_rejects_invalid_inputs(values):
    with pytest.raises(ValueError):
        gordon_growth_ddm(*values)


@pytest.mark.parametrize(
    "changes",
    [
        {"base_dividend": Decimal(0)},
        {"stage1_growth": ()},
        {"stage1_growth": (Decimal(-1),)},
        {"terminal_growth": Decimal(".2")},
    ],
)
def test_multistage_ddm_rejects_invalid_inputs(changes):
    with pytest.raises(ValueError):
        replace(
            MultiStageDDMAssumptions(Decimal(1), (Decimal(".05"),), Decimal(".1"), Decimal(".02")),
            **changes,
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"covariance": [[1, 2, 3]]},
        {"market_weights": [1]},
        {"covariance": [[float("nan"), 0], [0, 1]]},
        {"risk_aversion": 0},
        {"tau": 0},
        {"views_matrix": [[1]], "views_returns": [0.1]},
        {"views_matrix": [[1, 0]], "views_returns": [0.1, 0.2]},
        {"views_matrix": [[1, 0]], "views_returns": [0.1], "views_uncertainty": [[1, 0], [0, 1]]},
    ],
)
def test_black_litterman_rejects_invalid_shapes_and_parameters(kwargs):
    args = {"covariance": [[0.1, 0], [0, 0.2]], "market_weights": [0.5, 0.5], **kwargs}
    with pytest.raises(ValueError):
        black_litterman(**args)


def test_black_litterman_without_views_returns_market_weights():
    result = black_litterman([[0.1, 0], [0, 0.2]], [0.4, 0.6])
    assert result.optimal_weights == (0.4, 0.6)
    assert result.posterior_returns == pytest.approx((0.1, 0.3))


@pytest.mark.parametrize(
    "fn", [rolling.rolling_volatility, rolling.rolling_sharpe, rolling.rolling_max_drawdown]
)
def test_rolling_requires_sufficient_window_data(fn):
    with pytest.raises(ValueError, match="window"):
        fn(pd.Series([0.01, 0.02]), window=1)
    with pytest.raises(ValueError, match="length"):
        fn(pd.Series([0.01, 0.02]), window=3)


@pytest.mark.parametrize(
    "fn", [rolling.rolling_beta, rolling.rolling_tracking_error, rolling.rolling_information_ratio]
)
def test_rolling_relative_requires_valid_window(fn):
    with pytest.raises(ValueError, match="window"):
        fn(pd.Series([0.01, 0.02]), pd.Series([0.02, 0.03]), window=1)


def test_rolling_beta_requires_matching_series():
    with pytest.raises(ValueError, match="equal length"):
        rolling.rolling_beta(pd.Series([0.01]), pd.Series([0.02, 0.03]), window=3)


@pytest.mark.parametrize("fn", [min_variance, max_sharpe])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_weights": [1]},
        {"initial_weights": [float("nan"), 1]},
        {"asset_sectors": ["tech"], "sector_caps": {"tech": 0.5}},
        {"asset_sectors": ["tech", "bank"], "sector_caps": {"tech": -1}},
        {"asset_sectors": ["tech", "bank"], "sector_caps": {"tech": 2}},
        {"initial_weights": [0.5, 0.5], "turnover_cap": -0.1},
    ],
)
def test_optimizer_rejects_invalid_constraints(fn, kwargs):
    with pytest.raises(OptimizationError):
        fn([0.1, 0.2], [[0.1, 0], [0, 0.2]], **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"current_shares": {"A": 1}, "prices": {}},
        {"prices": {"A": 0}},
        {"current_shares": {"A": -1}},
        {"cash": -1000},
        {"target_weights": {"A": -1}},
        {"target_weights": {"A": 2}},
    ],
)
def test_rebalance_rejects_unavailable_prices_and_invalid_weights(kwargs):
    values = {
        "current_shares": {"A": 1},
        "prices": {"A": 10},
        "target_weights": {"A": 0.5},
        **kwargs,
    }
    with pytest.raises(ValueError):
        generate_rebalance_trades(**values)


def test_rebalance_generates_sell_hold_and_whole_share_orders():
    plan = generate_rebalance_trades(
        {"A": 10, "B": 10}, {"A": 10, "B": 10}, {"A": 0.5, "B": 0}, allow_fractional=False
    )
    assert [o.action.value for o in plan.orders] == ["HOLD", "SELL"]
    assert plan.ending_cash > 0


def test_factor_regression_aligns_pandas_inputs_and_risk_free_series():
    factor = pd.DataFrame({"market": [0.01, -0.01, 0.02, -0.02, 0.03, -0.03]})
    returns = 2 * factor.market + 0.001
    result = fama_french_regression(returns, factor, risk_free=pd.Series([0.001] * 6))
    assert result.betas["market"] == pytest.approx(2)
    assert result.alpha == pytest.approx(0, abs=1e-12)
    assert fama_french_regression(returns, factor, risk_free=0.001).betas[
        "market"
    ] == pytest.approx(2)
    assert fama_french_regression(returns, factor, risk_free=[0.001] * 6).betas[
        "market"
    ] == pytest.approx(2)


def test_factor_regression_constant_returns_and_invalid_inputs():
    factor = pd.DataFrame({"market": [0.01, -0.01, 0.02, -0.02, 0.03, -0.03]})
    assert fama_french_regression([0] * 6, factor).r_squared == 0
    for returns, factors, kwargs in [
        ([0] * 6, factor, {"periods_per_year": 0}),
        ([0], [[0.1]], {}),
        ([float("nan")] * 6, factor, {}),
    ]:
        with pytest.raises(ValueError):
            fama_french_regression(returns, factors, **kwargs)


def test_overfitting_boundaries_are_explicit():
    assert probabilistic_sharpe_ratio(1, 0, 2) == 0.5
    assert probabilistic_sharpe_ratio(1, 0, 100, skewness=10) == 1
    assert probabilistic_sharpe_ratio(1, 2, 100, skewness=10) == 0
    assert expected_max_sharpe(1, 1, 0.2) == 0.2
    check_lookahead_bias(lambda df: [], pd.DataFrame({"close": [1, 2]}))
    with pytest.raises(ValueError, match="signals"):
        check_lookahead_bias(lambda df: [], pd.DataFrame({"close": range(30)}))


@pytest.mark.parametrize(
    ("model", "changes"),
    [
        ("range", {"low": Decimal("NaN")}),
        ("range", {"low": Decimal(4)}),
        ("range", {"base": Decimal(4)}),
        ("segment", {"metric_value": Decimal("NaN")}),
        ("segment", {"ownership_pct": Decimal(0)}),
        ("deal", {"deal_value": Decimal("NaN")}),
        ("deal", {"deal_value": Decimal(0)}),
        ("deal", {"target_metric": Decimal(0)}),
    ],
)
def test_valuation_inputs_reject_nonfinite_or_inconsistent_values(model, changes):
    from analystforge.quant.football_field import ValuationRange
    from analystforge.quant.precedents import PrecedentDeal
    from analystforge.quant.sotp import SegmentValuation

    valid = {
        "range": ValuationRange("a", "A", "Intrinsic", Decimal(1), Decimal(2), Decimal(3)),
        "segment": SegmentValuation("A", "Revenue", Decimal(10), Decimal(2)),
        "deal": PrecedentDeal("A", "2024-01-01", Decimal(10), Decimal(2)),
    }[model]
    with pytest.raises(ValueError):
        replace(valid, **changes)


def test_valuations_require_positive_share_counts_and_observations():
    from analystforge.quant.football_field import ValuationRange, build_football_field
    from analystforge.quant.precedents import PrecedentDeal, precedent_transactions_valuation
    from analystforge.quant.sotp import SegmentValuation, sotp_valuation

    segment = SegmentValuation("A", "Revenue", Decimal(10), Decimal(2))
    deal = PrecedentDeal("A", "2024-01-01", Decimal(10), Decimal(2))
    for fn in [
        lambda: build_football_field([]),
        lambda: build_football_field(
            [ValuationRange("a", "A", "Intrinsic", Decimal(1), Decimal(2), Decimal(3))],
            current_share_price="NaN",
        ),
        lambda: sotp_valuation([], shares_outstanding=1),
        lambda: sotp_valuation([segment], shares_outstanding=0),
        lambda: precedent_transactions_valuation([], target_company_metric=1, shares_outstanding=1),
        lambda: precedent_transactions_valuation(
            [deal], target_company_metric=0, shares_outstanding=1
        ),
        lambda: precedent_transactions_valuation(
            [deal], target_company_metric=1, shares_outstanding=0
        ),
    ]:
        with pytest.raises(ValueError):
            fn()
