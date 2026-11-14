from __future__ import annotations

from decimal import Decimal

import pytest

from analystforge.quant.wacc import (
    after_tax_cost_of_debt,
    capm_cost_of_equity,
    compute_wacc,
    relever_beta,
    unlever_beta,
    wacc_from_capm,
)

D = Decimal


def test_capm_cost_of_equity_reference_value() -> None:
    assert capm_cost_of_equity("0.04", "1.2", "0.05") == D("0.10")


def test_after_tax_cost_of_debt_reference_value() -> None:
    assert after_tax_cost_of_debt("0.06", "0.25") == D("0.045")


def test_hamada_beta_unlevers_and_relevers_back() -> None:
    unlevered = unlever_beta("1.2", "0.25", "0.5")
    assert unlevered == pytest.approx(D("1.2") / D("1.375"))
    assert relever_beta(unlevered, "0.25", "0.5") == pytest.approx(D("1.2"))


def test_compute_wacc_uses_market_value_weights() -> None:
    result = compute_wacc(
        market_value_equity="600",
        market_value_debt="400",
        cost_of_equity="0.10",
        pre_tax_cost_of_debt="0.05",
        tax_rate="0.25",
    )

    assert result.equity_weight == D("0.6")
    assert result.debt_weight == D("0.4")
    assert result.after_tax_cost_of_debt == D("0.0375")
    assert result.wacc == D("0.075")
    assert result.market_value_equity == D("600")
    assert result.market_value_debt == D("400")
    assert "WACC" in result.formula


def test_wacc_from_capm_matches_the_component_build_up() -> None:
    result = wacc_from_capm(
        risk_free_rate="0.04",
        beta="1.2",
        equity_risk_premium="0.05",
        market_value_equity="600",
        market_value_debt="400",
        pre_tax_cost_of_debt="0.05",
        tax_rate="0.25",
    )

    assert result.cost_of_equity == D("0.10")
    assert result.wacc == D("0.075")


def test_a_debt_free_company_costs_equity_only() -> None:
    result = compute_wacc(
        market_value_equity="1000",
        market_value_debt="0",
        cost_of_equity="0.09",
        pre_tax_cost_of_debt="0.06",
        tax_rate="0.30",
    )

    assert result.debt_weight == D("0")
    assert result.wacc == D("0.09")


def test_wacc_validation() -> None:
    with pytest.raises(ValueError, match="greater than -100%"):
        capm_cost_of_equity("-1", "1", "0.05")
    with pytest.raises(ValueError, match="greater than -100%"):
        after_tax_cost_of_debt("-1", "0.2")
    with pytest.raises(ValueError, match="between 0 and 1"):
        after_tax_cost_of_debt("0.05", "1.2")
    with pytest.raises(ValueError, match="between 0 and 1"):
        unlever_beta("1.2", "-0.1", "0.5")
    with pytest.raises(ValueError, match="must not be negative"):
        unlever_beta("1.2", "0.25", "-0.1")
    with pytest.raises(ValueError, match="must not be negative"):
        compute_wacc("100", "-1", "0.10", "0.05", "0.25")
    with pytest.raises(ValueError, match="must be positive"):
        compute_wacc("0", "0", "0.10", "0.05", "0.25")
    with pytest.raises(ValueError, match="finite"):
        compute_wacc("100", "0", D("NaN"), "0.05", "0.25")
    with pytest.raises(ValueError, match="greater than -100%"):
        compute_wacc("100", "0", "-1", "0.05", "0.25")
