"""Reference calculation tests for complete valuation suite (WP2).

Exit criteria: each method matches an independent reference calculation within 0.01%.
"""

from __future__ import annotations

from decimal import Decimal

from analystforge.quant.ddm import (
    MultiStageDDMAssumptions,
    gordon_growth_ddm,
    multi_stage_ddm,
)
from analystforge.quant.fcfe import (
    FCFEAssumptions,
    fcfe_valuation,
)
from analystforge.quant.fcfe import (
    TerminalValueMethod as FCFETerminalValueMethod,
)
from analystforge.quant.football_field import (
    ValuationRange,
    build_football_field,
)
from analystforge.quant.precedents import (
    PrecedentDeal,
    precedent_transactions_valuation,
)
from analystforge.quant.residual_income import (
    ResidualIncomeAssumptions,
    ResidualIncomeTerminalMethod,
    residual_income_valuation,
)
from analystforge.quant.sotp import (
    SegmentValuation,
    sotp_valuation,
)
from analystforge.quant.wacc import (
    blume_adjusted_beta,
)


def assert_within_tolerance(
    actual: Decimal, expected: Decimal, tolerance: Decimal = Decimal("0.0001")
) -> None:
    """Verify relative difference |actual - expected| / |expected| <= 0.01%."""
    diff = abs(actual - expected)
    rel_diff = diff / abs(expected)
    assert rel_diff <= tolerance, (
        f"Actual {actual} differs from reference {expected} by {rel_diff:.6%} (> {tolerance:.4%})"
    )


def test_blume_adjusted_beta_reference() -> None:
    # Raw beta = 1.6
    # Blume adjusted = (2/3) * 1.6 + (1/3) * 1.0 = 1.066666667 + 0.333333333 = 1.40
    raw = Decimal("1.60")
    expected = (Decimal("2") / Decimal("3")) * raw + (Decimal("1") / Decimal("3"))
    actual = blume_adjusted_beta(raw)
    assert_within_tolerance(actual, expected)
    assert round(float(actual), 2) == 1.40


def test_fcfe_reference_calculation() -> None:
    # 5-year forecast FCFE model
    # Base NI = 1000
    # Growth = 10% each year
    # D&A = 15% of NI, Capex = 20% of NI, NWC = 5% of NI, Borrowing = 10% of NI
    # Net multiplier = 1 + 0.15 - 0.20 - 0.05 + 0.10 = 1.00 => FCFE = Net Income
    # Cost of equity = 10%, Terminal growth = 3%, Shares = 100
    assumptions = FCFEAssumptions(
        base_net_income=Decimal("1000"),
        net_income_growth=(
            Decimal("0.10"),
            Decimal("0.10"),
            Decimal("0.10"),
            Decimal("0.10"),
            Decimal("0.10"),
        ),
        cost_of_equity=Decimal("0.10"),
        terminal_growth=Decimal("0.03"),
        shares_outstanding=Decimal("100"),
        depreciation_pct_ni=Decimal("0.15"),
        capex_pct_ni=Decimal("0.20"),
        nwc_pct_ni=Decimal("0.05"),
        net_borrowing_pct_ni=Decimal("0.10"),
        terminal_method=FCFETerminalValueMethod.GORDON_GROWTH,
    )
    result = fcfe_valuation(assumptions)

    # Independent hand calculation:
    # NI_t:
    # Y1 = 1100, FCFE1 = 1100, PV1 = 1100 / 1.10 = 1000
    # Y2 = 1210, FCFE2 = 1210, PV2 = 1210 / 1.21 = 1000
    # Y3 = 1331, FCFE3 = 1331, PV3 = 1331 / 1.331 = 1000
    # Y4 = 1464.10, FCFE4 = 1464.10, PV4 = 1464.10 / 1.4641 = 1000
    # Y5 = 1610.51, FCFE5 = 1610.51, PV5 = 1610.51 / 1.61051 = 1000
    # Sum explicit PV = 5000.00
    expected_pv_explicit = Decimal("5000.00")
    assert_within_tolerance(result.pv_explicit_fcfe, expected_pv_explicit)

    # TV_5 = (1610.51 * 1.03) / (0.10 - 0.03) = 1658.8253 / 0.07 = 23697.5042857
    # PV(TV) = 23697.5042857 / 1.1^5 = 14714.2857
    expected_pv_tv = (Decimal("1610.51") * Decimal("1.03") / Decimal("0.07")) / (
        Decimal("1.10") ** 5
    )
    assert_within_tolerance(result.pv_terminal_value, expected_pv_tv)

    expected_equity_val = expected_pv_explicit + expected_pv_tv
    assert_within_tolerance(result.equity_value, expected_equity_val)

    expected_share_price = expected_equity_val / Decimal("100")
    assert_within_tolerance(result.implied_share_price, expected_share_price)


def test_gordon_growth_ddm_reference() -> None:
    # D0 = $4.00, r_e = 9%, g = 4%
    # D1 = 4.00 * 1.04 = $4.16
    # P0 = 4.16 / (0.09 - 0.04) = 4.16 / 0.05 = $83.20
    res = gordon_growth_ddm(
        dividend_t0=Decimal("4.00"), cost_of_equity=Decimal("0.09"), growth_rate=Decimal("0.04")
    )
    expected_p0 = Decimal("83.20")
    assert_within_tolerance(res.implied_share_price, expected_p0)
    assert res.dividend_yield == Decimal("0.05")  # 4.16 / 83.20 = 5%


def test_multi_stage_ddm_reference() -> None:
    # Base dividend D0 = 2.00
    # 3-year high growth: 15%, 15%, 15%
    # Cost of equity = 10%, terminal growth = 4%
    # D1 = 2.30, PV(D1) = 2.30 / 1.10 = 2.090909
    # D2 = 2.645, PV(D2) = 2.645 / 1.21 = 2.185950
    # D3 = 3.04175, PV(D3) = 3.04175 / 1.331 = 2.285312
    # TV3 = 3.04175 * 1.04 / (0.10 - 0.04) = 3.16342 / 0.06 = 52.723667
    # PV(TV3) = 52.723667 / 1.331 = 39.612071
    # Total Price = 2.090909 + 2.185950 + 2.285312 + 39.612071 = 46.174242
    assumptions = MultiStageDDMAssumptions(
        base_dividend=Decimal("2.00"),
        stage1_growth=(Decimal("0.15"), Decimal("0.15"), Decimal("0.15")),
        cost_of_equity=Decimal("0.10"),
        terminal_growth=Decimal("0.04"),
    )
    res = multi_stage_ddm(assumptions)
    expected_price = Decimal("46.1742")
    assert_within_tolerance(res.implied_share_price, expected_price, tolerance=Decimal("0.0005"))


def test_residual_income_reference_calculation() -> None:
    # BV0 = $50.00
    # 2 years forecast NI: Y1 = $10.00, Y2 = $12.00
    # Payout ratio = 20% (dividends Y1 = 2.00, Y2 = 2.40)
    # Cost of equity = 10%, terminal growth = 2% (Gordon terminal method)
    # Shares = 1
    # Y1:
    # Beg BV = 50.00, Equity charge = 50 * 0.10 = 5.00
    # RI_1 = 10.00 - 5.00 = 5.00, PV(RI_1) = 5.00 / 1.10 = 4.545455
    # End BV1 = 50 + 10 - 2 = 58.00
    # Y2:
    # Beg BV = 58.00, Equity charge = 58 * 0.10 = 5.80
    # RI_2 = 12.00 - 5.80 = 6.20, PV(RI_2) = 6.20 / 1.21 = 5.123967
    # TV_2 = (6.20 * 1.02) / (0.10 - 0.02) = 6.324 / 0.08 = 79.05
    # PV(TV_2) = 79.05 / 1.21 = 65.330578
    # Total Equity = 50.00 + 4.545455 + 5.123967 + 65.330578 = 125.00
    assumptions = ResidualIncomeAssumptions(
        base_book_value=Decimal("50.00"),
        forecast_net_income=(Decimal("10.00"), Decimal("12.00")),
        cost_of_equity=Decimal("0.10"),
        shares_outstanding=Decimal("1.00"),
        dividend_payout_ratio=Decimal("0.20"),
        terminal_method=ResidualIncomeTerminalMethod.GORDON_GROWTH,
        terminal_growth=Decimal("0.02"),
    )
    res = residual_income_valuation(assumptions)
    expected_equity = Decimal("125.00")
    assert_within_tolerance(res.equity_value, expected_equity, tolerance=Decimal("0.0005"))
    assert_within_tolerance(res.implied_share_price, expected_equity, tolerance=Decimal("0.0005"))


def test_sotp_reference_calculation() -> None:
    # 3 business units:
    # Segment 1: Cloud - EBITDA $500M @ 20x EV/EBITDA = $10,000M
    # Segment 2: Hardware - Revenue $2000M @ 2x EV/Sales = $4,000M
    # Segment 3: Services (80% owned) - EBITDA $200M @ 15x * 0.8 = $2,400M
    # Total EV = 10,000 + 4,000 + 2,400 = $16,400M
    # Net Debt = $2,000M
    # Non-controlling interest = $400M
    # Investments = $500M
    # Corp overhead PV = $500M
    # Equity value = 16,400 - 2,000 - 400 + 500 - 500 = $14,000M
    # Shares = 100M -> Share price = $140.00
    segments = [
        SegmentValuation("Cloud", "EBITDA", Decimal("500"), Decimal("20")),
        SegmentValuation("Hardware", "Revenue", Decimal("2000"), Decimal("2")),
        SegmentValuation(
            "Services", "EBITDA", Decimal("200"), Decimal("15"), ownership_pct=Decimal("0.80")
        ),
    ]
    res = sotp_valuation(
        segments,
        net_debt=Decimal("2000"),
        non_controlling_interest=Decimal("400"),
        investments_associates=Decimal("500"),
        corporate_overhead_pv=Decimal("500"),
        shares_outstanding=Decimal("100"),
    )
    assert res.total_enterprise_value == Decimal("16400.00")
    assert res.equity_value == Decimal("14000.00")
    assert res.implied_share_price == Decimal("140.0000")


def test_precedent_transactions_reference() -> None:
    # 4 precedent M&A deals in cybersecurity:
    # Deal 1: EV $1,000M, EBITDA $100M -> 10.0x
    # Deal 2: EV $1,800M, EBITDA $150M -> 12.0x
    # Deal 3: EV $2,800M, EBITDA $200M -> 14.0x
    # Deal 4: EV $4,800M, EBITDA $300M -> 16.0x
    # Median multiple = 13.0x, Mean = 13.0x
    # Target company EBITDA = $120M, Net Debt = $200M, Shares = 50M
    # Implied median EV = 120 * 13 = $1560M
    # Implied median equity value = 1560 - 200 = $1360M
    # Implied median share price = 1360 / 50 = $27.20
    deals = [
        PrecedentDeal("Deal A", "2024-01-15", Decimal("1000"), Decimal("100")),
        PrecedentDeal("Deal B", "2024-05-20", Decimal("1800"), Decimal("150")),
        PrecedentDeal("Deal C", "2024-08-10", Decimal("2800"), Decimal("200")),
        PrecedentDeal("Deal D", "2024-11-01", Decimal("4800"), Decimal("300")),
    ]
    res = precedent_transactions_valuation(
        deals,
        target_company_metric=Decimal("120"),
        net_debt=Decimal("200"),
        shares_outstanding=Decimal("50"),
    )
    assert res.count == 4
    assert res.median_multiple == Decimal("13.0000")
    assert res.mean_multiple == Decimal("13.0000")
    assert res.implied_ev_median == Decimal("1560.00")
    assert res.implied_share_price_median == Decimal("27.2000")


def test_football_field_consolidation() -> None:
    ranges = [
        ValuationRange(
            "dcf_fcff",
            "DCF (FCFF)",
            "Intrinsic",
            Decimal("140.00"),
            Decimal("160.00"),
            Decimal("185.00"),
        ),
        ValuationRange(
            "dcf_fcfe",
            "DCF (FCFE)",
            "Intrinsic",
            Decimal("135.00"),
            Decimal("155.00"),
            Decimal("180.00"),
        ),
        ValuationRange(
            "comps_ebitda",
            "Comps EV/EBITDA",
            "Comps",
            Decimal("130.00"),
            Decimal("150.00"),
            Decimal("170.00"),
        ),
        ValuationRange(
            "comps_pe",
            "Comps P/E",
            "Comps",
            Decimal("125.00"),
            Decimal("148.00"),
            Decimal("175.00"),
        ),
        ValuationRange(
            "sotp", "SOTP", "Asset-Based", Decimal("150.00"), Decimal("165.00"), Decimal("190.00")
        ),
        ValuationRange(
            "market_52w",
            "52-Week Range",
            "Market",
            Decimal("120.00"),
            Decimal("152.00"),
            Decimal("178.00"),
        ),
    ]
    ff = build_football_field(ranges, current_share_price=Decimal("152.50"))
    assert len(ff.ranges) == 6
    assert ff.composite_low == Decimal("120.00")
    assert ff.composite_high == Decimal("190.00")
    assert ff.current_share_price == Decimal("152.50")
