from __future__ import annotations

from decimal import Decimal

import pytest

from analystforge.quant.dcf import (
    DCFAssumptions,
    TerminalValueMethod,
    project_fcff,
    run_dcf,
)

D = Decimal

GROWTH_ASSUMPTIONS = DCFAssumptions(
    base_revenue=D("1000"),
    revenue_growth=(D("0.20"), D("0.15"), D("0.10")),
    ebit_margin=(D("0.10"),),
    tax_rate=D("0.25"),
    wacc=D("0.10"),
    terminal_growth=D("0.03"),
    shares_outstanding=D("100"),
    depreciation_pct_revenue=D("0.02"),
    capex_pct_revenue=D("0.04"),
    nwc_pct_incremental_revenue=D("0.10"),
    net_debt=D("200"),
)


def test_projection_derives_revenue_nopat_reinvestment_and_fcff() -> None:
    forecast = project_fcff(GROWTH_ASSUMPTIONS)

    assert [year.year for year in forecast] == [1, 2, 3]
    first, second, third = forecast

    assert first.revenue == D("1200")
    assert first.ebit == D("120")
    assert first.ebitda == D("144")
    assert first.nopat == D("90")
    assert first.depreciation == D("24")
    assert first.capex == D("48")
    assert first.change_in_net_working_capital == D("20")
    assert first.fcff == D("46")
    assert first.discount_factor == pytest.approx(D("1") / D("1.1"))

    assert second.revenue == pytest.approx(D("1380"))
    assert second.fcff == pytest.approx(D("57.9"))
    assert third.revenue == pytest.approx(D("1518"))
    assert third.fcff == pytest.approx(D("69.69"))
    assert third.ebitda == pytest.approx(D("182.16"))


def test_gordon_growth_valuation_matches_an_independent_build_up() -> None:
    result = run_dcf(GROWTH_ASSUMPTIONS)

    expected_enterprise_value = (
        D("46") / D("1.1") + D("57.9") / D("1.21") + D("69.69") / D("1.331")
    ) + (D("69.69") * D("1.03") / D("0.07")) / D("1.331")
    assert float(result.enterprise_value) == pytest.approx(
        float(expected_enterprise_value), abs=0.01
    )
    assert float(result.equity_value) == pytest.approx(
        float(expected_enterprise_value) - 200.0, abs=0.01
    )
    assert float(result.value_per_share) == pytest.approx(
        (float(expected_enterprise_value) - 200.0) / 100.0, abs=1e-4
    )
    assert result.terminal_value_pct_enterprise_value > D("0.75")
    assert any("Terminal value" in warning for warning in result.warnings)


def test_exit_multiple_terminal_value_uses_final_year_ebitda() -> None:
    assumptions = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0.20"), D("0.15"), D("0.10")),
        ebit_margin=(D("0.10"),),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
        depreciation_pct_revenue=D("0.02"),
        capex_pct_revenue=D("0.04"),
        nwc_pct_incremental_revenue=D("0.10"),
        net_debt=D("200"),
        terminal_method=TerminalValueMethod.EXIT_MULTIPLE,
        exit_multiple=D("8"),
    )
    result = run_dcf(assumptions)

    assert result.terminal_value == D("1457.28")
    assert result.terminal_value_pv == D("1094.88")
    assert result.forecast[-1].ebitda == pytest.approx(D("182.16"))


def test_a_no_growth_perpetuity_values_at_fcff_over_wacc() -> None:
    assumptions = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"),) * 5,
        ebit_margin=(D("0.10"),),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
    )
    result = run_dcf(assumptions)

    assert result.enterprise_value == D("750.00")
    assert result.equity_value == D("750.00")
    assert result.value_per_share == D("7.5000")
    assert result.warnings == ()


def test_mid_year_convention_discounts_each_flow_half_a_year_earlier() -> None:
    annual = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"),) * 5,
        ebit_margin=(D("0.10"),),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
    )
    mid_year = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"),) * 5,
        ebit_margin=(D("0.10"),),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
        mid_year_convention=True,
    )
    annual_result = run_dcf(annual)
    mid_year_result = run_dcf(mid_year)

    assert mid_year_result.forecast[0].discount_factor == pytest.approx(
        D("1") / D("1.1") ** D("0.5")
    )
    assert mid_year_result.enterprise_value > annual_result.enterprise_value


def test_negative_equity_produces_a_warning() -> None:
    assumptions = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"),),
        ebit_margin=(D("0.05"),),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
        net_debt=D("10000"),
    )
    result = run_dcf(assumptions)

    assert result.equity_value < 0
    assert any("Equity value is negative" in warning for warning in result.warnings)


def test_assumption_validation() -> None:
    def assumptions(**overrides: object) -> DCFAssumptions:
        values: dict[str, object] = {
            "base_revenue": D("1000"),
            "revenue_growth": (D("0.05"),),
            "ebit_margin": (D("0.10"),),
            "tax_rate": D("0.25"),
            "wacc": D("0.10"),
            "terminal_growth": D("0.02"),
            "shares_outstanding": D("100"),
        }
        values.update(overrides)
        return DCFAssumptions(**values)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="base_revenue must be positive"):
        assumptions(base_revenue=D("0"))
    with pytest.raises(ValueError, match="at least one forecast year"):
        assumptions(revenue_growth=())
    with pytest.raises(ValueError, match="greater than -100%"):
        assumptions(revenue_growth=(D("-1"),))
    with pytest.raises(ValueError, match="one value or one value per forecast year"):
        assumptions(revenue_growth=(D("0.1"), D("0.1")), ebit_margin=(D("0.1"), D("0.1"), D("0.1")))
    with pytest.raises(ValueError, match="tax_rate must be between 0 and 1"):
        assumptions(tax_rate=D("1.5"))
    with pytest.raises(ValueError, match="terminal_growth must be below wacc"):
        assumptions(terminal_growth=D("0.10"))
    with pytest.raises(ValueError, match="exit_multiple requires"):
        assumptions(exit_multiple=D("8"))
    with pytest.raises(ValueError, match="exit_multiple is required"):
        assumptions(terminal_method=TerminalValueMethod.EXIT_MULTIPLE)
    with pytest.raises(ValueError, match="exit_multiple must be positive"):
        assumptions(terminal_method=TerminalValueMethod.EXIT_MULTIPLE, exit_multiple=D("0"))
    with pytest.raises(ValueError, match="shares_outstanding must be positive"):
        assumptions(shares_outstanding=D("0"))
    with pytest.raises(ValueError, match="depreciation_pct_revenue must not be negative"):
        assumptions(depreciation_pct_revenue=D("-0.01"))
    with pytest.raises(ValueError, match="capex_pct_revenue must not be negative"):
        assumptions(capex_pct_revenue=D("-0.01"))
    with pytest.raises(ValueError, match="must be finite"):
        assumptions(base_revenue=D("NaN"))
    with pytest.raises(ValueError, match="wacc must be greater than -100%"):
        assumptions(wacc=D("-1"))


def test_year_specific_margins_override_the_single_margin() -> None:
    assumptions = DCFAssumptions(
        base_revenue=D("1000"),
        revenue_growth=(D("0"), D("0")),
        ebit_margin=(D("0.10"), D("0.20")),
        tax_rate=D("0.25"),
        wacc=D("0.10"),
        terminal_growth=D("0"),
        shares_outstanding=D("100"),
    )
    forecast = project_fcff(assumptions)

    assert forecast[0].ebit == D("100")
    assert forecast[1].ebit == D("200")
    assert forecast[0].fcff == D("75")
    assert forecast[1].fcff == D("150")
