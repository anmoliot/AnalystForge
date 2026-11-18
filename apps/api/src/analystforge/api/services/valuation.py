"""Valuation services: DCF (FCFF & FCFE), DDM, Residual Income, Comps, SOTP, Precedents, WACC builder, and Excel export."""

from __future__ import annotations

import io
import logging
from decimal import Decimal
from typing import Any

import numpy as np
import xlsxwriter
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.macro import MacroObservation
from analystforge.quant.dcf import DCFAssumptions, DCFResult, TerminalValueMethod, run_dcf
from analystforge.quant.ddm import (
    MultiStageDDMAssumptions,
    gordon_growth_ddm,
    multi_stage_ddm,
)
from analystforge.quant.fcfe import (
    FCFEAssumptions,
    FCFEResult,
    fcfe_valuation,
)
from analystforge.quant.fcfe import (
    TerminalValueMethod as FCFETerminalValueMethod,
)
from analystforge.quant.football_field import (
    FootballFieldResult,
    ValuationRange,
    build_football_field,
)
from analystforge.quant.money import to_decimal
from analystforge.quant.multiples import (
    peer_statistics,
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
    after_tax_cost_of_debt,
    blume_adjusted_beta,
    capm_cost_of_equity,
)


def execute_dcf(params: dict[str, Any]) -> dict[str, Any]:
    """Execute pure DCF calculations from user assumptions."""
    assumptions = DCFAssumptions(
        base_revenue=to_decimal(params["base_revenue"]),
        revenue_growth=tuple(to_decimal(g) for g in params["revenue_growth"]),
        ebit_margin=tuple(to_decimal(m) for m in params["ebit_margin"]),
        tax_rate=to_decimal(params["tax_rate"]),
        wacc=to_decimal(params["wacc"]),
        terminal_growth=to_decimal(params.get("terminal_growth", Decimal("0.025"))),
        shares_outstanding=to_decimal(params["shares_outstanding"]),
        depreciation_pct_revenue=to_decimal(
            params.get("depreciation_pct_revenue", Decimal("0.04"))
        ),
        capex_pct_revenue=to_decimal(params.get("capex_pct_revenue", Decimal("0.05"))),
        nwc_pct_incremental_revenue=to_decimal(
            params.get("nwc_pct_incremental_revenue", Decimal("0.10"))
        ),
        net_debt=to_decimal(params.get("net_debt", Decimal("0"))),
        mid_year_convention=bool(params.get("mid_year_convention", True)),
        terminal_method=TerminalValueMethod(params.get("terminal_method", "gordon_growth")),
        exit_multiple=to_decimal(params["exit_multiple"]) if params.get("exit_multiple") else None,
    )
    res: DCFResult = run_dcf(assumptions)

    forecast_items = [
        {
            "year": f.year,
            "revenue": float(f.revenue),
            "ebit": float(f.ebit),
            "ebitda": float(f.ebitda),
            "nopat": float(f.nopat),
            "depreciation": float(f.depreciation),
            "capex": float(f.capex),
            "nwc_change": float(f.change_in_net_working_capital),
            "fcff": float(f.fcff),
            "discount_factor": float(f.discount_factor),
            "present_value": float(f.present_value),
        }
        for f in res.forecast
    ]

    return {
        "enterprise_value": float(res.enterprise_value),
        "equity_value": float(res.equity_value),
        "value_per_share": float(res.value_per_share),
        "terminal_value": float(res.terminal_value),
        "terminal_value_pv": float(res.terminal_value_pv),
        "terminal_value_pct": float(res.terminal_value_pct_enterprise_value),
        "sum_pv_fcff": float(res.sum_present_value_fcff),
        "net_debt": float(res.net_debt),
        "shares_outstanding": float(res.shares_outstanding),
        "warnings": list(res.warnings),
        "forecast": forecast_items,
        "formula": res.formula,
    }


def execute_fcfe(params: dict[str, Any]) -> dict[str, Any]:
    """Execute Free Cash Flow to Equity (FCFE) valuation."""
    assumptions = FCFEAssumptions(
        base_net_income=to_decimal(params["base_net_income"]),
        net_income_growth=tuple(to_decimal(g) for g in params["net_income_growth"]),
        cost_of_equity=to_decimal(params["cost_of_equity"]),
        terminal_growth=to_decimal(params.get("terminal_growth", Decimal("0.025"))),
        shares_outstanding=to_decimal(params["shares_outstanding"]),
        depreciation_pct_ni=to_decimal(params.get("depreciation_pct_ni", Decimal("0.10"))),
        capex_pct_ni=to_decimal(params.get("capex_pct_ni", Decimal("0.15"))),
        nwc_pct_ni=to_decimal(params.get("nwc_pct_ni", Decimal("0.05"))),
        net_borrowing_pct_ni=to_decimal(params.get("net_borrowing_pct_ni", Decimal("0.05"))),
        terminal_method=FCFETerminalValueMethod(params.get("terminal_method", "gordon_growth")),
        exit_multiple=to_decimal(params["exit_multiple"]) if params.get("exit_multiple") else None,
        mid_year_convention=bool(params.get("mid_year_convention", False)),
    )
    res: FCFEResult = fcfe_valuation(assumptions)

    forecast_items = [
        {
            "year": f.year,
            "net_income": float(f.net_income),
            "depreciation": float(f.depreciation),
            "capex": float(f.capex),
            "nwc_change": float(f.nwc_change),
            "net_borrowing": float(f.net_borrowing),
            "fcfe": float(f.fcfe),
            "discount_factor": float(f.discount_factor),
            "present_value": float(f.present_value),
        }
        for f in res.forecast_years
    ]

    return {
        "pv_explicit_fcfe": float(res.pv_explicit_fcfe),
        "terminal_value": float(res.terminal_value),
        "terminal_value_pv": float(res.pv_terminal_value),
        "equity_value": float(res.equity_value),
        "value_per_share": float(res.implied_share_price),
        "forecast": forecast_items,
    }


def execute_ddm(params: dict[str, Any]) -> dict[str, Any]:
    """Execute Dividend Discount Model (single-stage Gordon or multi-stage)."""
    model_type = params.get("model_type", "gordon")
    if model_type == "gordon":
        gordon_res = gordon_growth_ddm(
            dividend_t0=to_decimal(params["dividend_t0"]),
            cost_of_equity=to_decimal(params["cost_of_equity"]),
            growth_rate=to_decimal(params["growth_rate"]),
        )
        return {
            "model_type": "gordon",
            "dividend_t0": float(gordon_res.dividend_t0),
            "dividend_t1": float(gordon_res.dividend_t1),
            "cost_of_equity": float(gordon_res.cost_of_equity),
            "growth_rate": float(gordon_res.growth_rate),
            "implied_share_price": float(gordon_res.implied_share_price),
            "dividend_yield": float(gordon_res.dividend_yield),
        }

    # Multi-stage
    assumptions = MultiStageDDMAssumptions(
        base_dividend=to_decimal(params["base_dividend"]),
        stage1_growth=tuple(to_decimal(g) for g in params["stage1_growth"]),
        cost_of_equity=to_decimal(params["cost_of_equity"]),
        terminal_growth=to_decimal(params["terminal_growth"]),
    )
    multi_res = multi_stage_ddm(assumptions)
    return {
        "model_type": "multi_stage",
        "pv_explicit_dividends": float(multi_res.pv_explicit_dividends),
        "terminal_value": float(multi_res.terminal_value),
        "pv_terminal_value": float(multi_res.pv_terminal_value),
        "implied_share_price": float(multi_res.implied_share_price),
        "forecast": [
            {
                "year": y.year,
                "dividend": float(y.dividend),
                "discount_factor": float(y.discount_factor),
                "present_value": float(y.present_value),
            }
            for y in multi_res.forecast_years
        ],
    }


def execute_residual_income(params: dict[str, Any]) -> dict[str, Any]:
    """Execute Edwards-Bell-Ohlson Residual Income model."""
    assumptions = ResidualIncomeAssumptions(
        base_book_value=to_decimal(params["base_book_value"]),
        forecast_net_income=tuple(to_decimal(ni) for ni in params["forecast_net_income"]),
        cost_of_equity=to_decimal(params["cost_of_equity"]),
        shares_outstanding=to_decimal(params["shares_outstanding"]),
        dividend_payout_ratio=to_decimal(params.get("dividend_payout_ratio", Decimal("0"))),
        terminal_method=ResidualIncomeTerminalMethod(params.get("terminal_method", "zero_growth")),
        terminal_growth=to_decimal(params.get("terminal_growth", Decimal("0"))),
        persistence_factor=to_decimal(params.get("persistence_factor", Decimal("1"))),
    )
    res = residual_income_valuation(assumptions)
    return {
        "base_book_value": float(res.base_book_value),
        "pv_explicit_residual_income": float(res.pv_explicit_residual_income),
        "terminal_value": float(res.terminal_value),
        "pv_terminal_value": float(res.pv_terminal_value),
        "equity_value": float(res.equity_value),
        "implied_share_price": float(res.implied_share_price),
        "forecast": [
            {
                "year": y.year,
                "beginning_book_value": float(y.beginning_book_value),
                "net_income": float(y.net_income),
                "dividends": float(y.dividends),
                "ending_book_value": float(y.ending_book_value),
                "equity_charge": float(y.equity_charge),
                "residual_income": float(y.residual_income),
                "discount_factor": float(y.discount_factor),
                "present_value_ri": float(y.present_value_ri),
            }
            for y in res.forecast_years
        ],
    }


def execute_comps(params: dict[str, Any]) -> dict[str, Any]:
    """Comparable companies valuation: peer multiples, distribution statistics, and implied ranges."""
    peer_multiples_raw = params.get("peer_multiples", [])
    if not peer_multiples_raw:
        raise ValueError("peer_multiples list cannot be empty")

    multiples_dec = [to_decimal(m) for m in peer_multiples_raw]
    stats = peer_statistics(multiples_dec)

    ordered = sorted(multiples_dec)
    n = len(ordered)
    p25 = ordered[int(0.25 * (n - 1))]
    p75 = ordered[int(0.75 * (n - 1))]

    target_metric = to_decimal(params["target_metric"])
    net_debt = to_decimal(params.get("net_debt", 0))
    shares = to_decimal(params["shares_outstanding"])
    is_equity_multiple = bool(params.get("is_equity_multiple", False))  # P/E or P/B vs EV/EBITDA

    def get_price(mult: Decimal) -> float:
        if is_equity_multiple:
            eq_val = target_metric * mult
        else:
            eq_val = target_metric * mult - net_debt
        return float(eq_val / shares)

    return {
        "count": stats.count,
        "mean_multiple": float(stats.mean) if stats.mean else None,
        "median_multiple": float(stats.median) if stats.median else None,
        "min_multiple": float(stats.minimum) if stats.minimum else None,
        "max_multiple": float(stats.maximum) if stats.maximum else None,
        "p25_multiple": float(p25),
        "p75_multiple": float(p75),
        "implied_share_price_min": get_price(stats.minimum) if stats.minimum else None,
        "implied_share_price_p25": get_price(p25),
        "implied_share_price_median": get_price(stats.median) if stats.median else None,
        "implied_share_price_p75": get_price(p75),
        "implied_share_price_max": get_price(stats.maximum) if stats.maximum else None,
    }


def execute_sotp(params: dict[str, Any]) -> dict[str, Any]:
    """Execute Sum of the Parts (SOTP) conglomerate valuation."""
    segments = [
        SegmentValuation(
            name=s["name"],
            metric_name=s["metric_name"],
            metric_value=to_decimal(s["metric_value"]),
            multiple=to_decimal(s["multiple"]),
            ownership_pct=to_decimal(s.get("ownership_pct", 1.0)),
        )
        for s in params["segments"]
    ]
    res = sotp_valuation(
        segments,
        net_debt=to_decimal(params.get("net_debt", 0)),
        non_controlling_interest=to_decimal(params.get("non_controlling_interest", 0)),
        investments_associates=to_decimal(params.get("investments_associates", 0)),
        corporate_overhead_pv=to_decimal(params.get("corporate_overhead_pv", 0)),
        shares_outstanding=to_decimal(params["shares_outstanding"]),
    )
    return {
        "total_enterprise_value": float(res.total_enterprise_value),
        "net_debt": float(res.net_debt),
        "non_controlling_interest": float(res.non_controlling_interest),
        "investments_associates": float(res.investments_associates),
        "corporate_overhead_pv": float(res.corporate_overhead_pv),
        "equity_value": float(res.equity_value),
        "implied_share_price": float(res.implied_share_price),
        "segments": [
            {
                "name": s.name,
                "metric_name": s.metric_name,
                "metric_value": float(s.metric_value),
                "multiple": float(s.multiple),
                "ownership_pct": float(s.ownership_pct),
                "enterprise_value": float(s.enterprise_value),
            }
            for s in res.segments
        ],
    }


def execute_precedents(params: dict[str, Any]) -> dict[str, Any]:
    """Execute Precedent M&A transactions valuation."""
    deals = [
        PrecedentDeal(
            target=d["target"],
            announced_date=d.get("announced_date", ""),
            deal_value=to_decimal(d["deal_value"]),
            target_metric=to_decimal(d["target_metric"]),
        )
        for d in params["deals"]
    ]
    res = precedent_transactions_valuation(
        deals,
        target_company_metric=to_decimal(params["target_metric"]),
        net_debt=to_decimal(params.get("net_debt", 0)),
        shares_outstanding=to_decimal(params["shares_outstanding"]),
    )
    return {
        "count": res.count,
        "min_multiple": float(res.min_multiple),
        "p25_multiple": float(res.p25_multiple),
        "median_multiple": float(res.median_multiple),
        "mean_multiple": float(res.mean_multiple),
        "p75_multiple": float(res.p75_multiple),
        "max_multiple": float(res.max_multiple),
        "implied_ev_p25": float(res.implied_ev_p25),
        "implied_ev_median": float(res.implied_ev_median),
        "implied_ev_p75": float(res.implied_ev_p75),
        "implied_share_price_p25": float(res.implied_share_price_p25),
        "implied_share_price_median": float(res.implied_share_price_median),
        "implied_share_price_p75": float(res.implied_share_price_p75),
        "deals": [
            {
                "target": d.target,
                "announced_date": d.announced_date,
                "deal_value": float(d.deal_value),
                "target_metric": float(d.target_metric),
                "implied_multiple": float(d.implied_multiple),
            }
            for d in res.deals
        ],
    }


async def execute_wacc_builder(session: AsyncSession, params: dict[str, Any]) -> dict[str, Any]:
    """Derive WACC with CAPM, Blume-adjusted regression beta, and real-time FRED risk-free rate."""
    # 1. Risk-free rate: query latest DGS10 from FRED if not manually specified
    rf_rate = params.get("risk_free_rate")
    if rf_rate is None:
        stmt = (
            select(MacroObservation.value)
            .where(MacroObservation.series_code == "DGS10")
            .order_by(desc(MacroObservation.day))
            .limit(1)
        )
        val = (await session.execute(stmt)).scalar_one_or_none()
        rf_rate = float(val) / 100.0 if val is not None else 0.0435

    # 2. Beta handling: raw regression beta with Blume adjustment
    raw_beta = float(params.get("raw_beta", 1.0))
    apply_blume = bool(params.get("apply_blume", True))
    beta = float(blume_adjusted_beta(to_decimal(raw_beta))) if apply_blume else raw_beta

    erp = float(params.get("equity_risk_premium", 0.055))
    cost_of_equity = float(
        capm_cost_of_equity(to_decimal(rf_rate), to_decimal(beta), to_decimal(erp))
    )

    pre_tax_cost_of_debt = float(params.get("pre_tax_cost_of_debt", 0.055))
    tax_rate = float(params.get("tax_rate", 0.21))
    after_tax_debt = float(
        after_tax_cost_of_debt(to_decimal(pre_tax_cost_of_debt), to_decimal(tax_rate))
    )

    mv_equity = float(params.get("market_value_equity", 1000000))
    mv_debt = float(params.get("market_value_debt", 250000))
    total_val = mv_equity + mv_debt
    w_e = mv_equity / total_val
    w_d = mv_debt / total_val

    wacc_val = w_e * cost_of_equity + w_d * after_tax_debt

    return {
        "wacc": round(wacc_val, 4),
        "cost_of_equity": round(cost_of_equity, 4),
        "after_tax_cost_of_debt": round(after_tax_debt, 4),
        "risk_free_rate": round(rf_rate, 4),
        "raw_beta": round(raw_beta, 4),
        "adjusted_beta": round(beta, 4),
        "equity_risk_premium": round(erp, 4),
        "equity_weight": round(w_e, 4),
        "debt_weight": round(w_d, 4),
        "market_value_equity": mv_equity,
        "market_value_debt": mv_debt,
        "source_risk_free": "FRED 10-Year Treasury Constant Maturity (DGS10)",
    }


def execute_football_field(params: dict[str, Any]) -> dict[str, Any]:
    """Aggregate valuation ranges across all methods into a unified Football Field."""
    ranges = [
        ValuationRange(
            method_id=r["method_id"],
            label=r["label"],
            category=r.get("category", "Intrinsic"),
            low=to_decimal(r["low"]),
            base=to_decimal(r["base"]),
            high=to_decimal(r["high"]),
            notes=r.get("notes"),
        )
        for r in params["ranges"]
    ]
    curr_p = params.get("current_share_price")
    res: FootballFieldResult = build_football_field(
        ranges, current_share_price=to_decimal(curr_p) if curr_p is not None else None
    )
    return {
        "current_share_price": float(res.current_share_price) if res.current_share_price else None,
        "composite_low": float(res.composite_low),
        "composite_median": float(res.composite_median),
        "composite_high": float(res.composite_high),
        "ranges": [
            {
                "method_id": r.method_id,
                "label": r.label,
                "category": r.category,
                "low": float(r.low),
                "base": float(r.base),
                "high": float(r.high),
                "notes": r.notes,
            }
            for r in res.ranges
        ],
    }


def compute_sensitivity_grid(
    params: dict[str, Any],
    wacc_steps: list[float] | None = None,
    g_steps: list[float] | None = None,
) -> dict[str, Any]:
    """Generate 2D sensitivity grid for implied value per share (WACC vs Terminal Growth)."""
    base_wacc = float(params["wacc"])
    base_g = float(params.get("terminal_growth", 0.025))

    if not wacc_steps:
        wacc_steps = [round(base_wacc + delta, 4) for delta in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    if not g_steps:
        g_steps = [round(base_g + delta, 4) for delta in (-0.01, -0.005, 0.0, 0.005, 0.01)]

    matrix: list[list[float | None]] = []
    for w in wacc_steps:
        row: list[float | None] = []
        for g in g_steps:
            if g >= w:
                row.append(None)
                continue
            p = dict(params)
            p["wacc"] = w
            p["terminal_growth"] = g
            try:
                res = execute_dcf(p)
                row.append(round(res["value_per_share"], 2))
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "operation unavailable (%s)", type(exc).__name__
                )
                row.append(None)
        matrix.append(row)

    return {
        "wacc_axis": wacc_steps,
        "g_axis": g_steps,
        "matrix": matrix,
    }


def compute_monte_carlo(
    params: dict[str, Any], iterations: int = 1000, seed: int = 42
) -> dict[str, Any]:
    """Run Monte Carlo simulation on growth and margin drivers using an explicit scoped RNG."""
    rng = np.random.default_rng(seed)
    base_growth = [float(g) for g in params["revenue_growth"]]
    base_margin = [float(m) for m in params["ebit_margin"]]
    if len(base_margin) == 1:
        base_margin = base_margin * len(base_growth)

    values: list[float] = []
    for _ in range(iterations):
        sim_growth = [g + float(rng.normal(0, 0.015)) for g in base_growth]
        sim_margin = [max(0.01, m + float(rng.normal(0, 0.01))) for m in base_margin]

        p = dict(params)
        p["revenue_growth"] = sim_growth
        p["ebit_margin"] = sim_margin
        try:
            res = execute_dcf(p)
            values.append(res["value_per_share"])
        except Exception as exc:
            logging.getLogger(__name__).warning("operation unavailable (%s)", type(exc).__name__)
            continue

    if not values:
        return {"mean": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0, "std": 0.0, "seed": seed}

    arr = np.array(values)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p90": float(np.percentile(arr, 90)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "seed": seed,
    }


def generate_dcf_excel_workbook(
    params: dict[str, Any], result: dict[str, Any], company_name: str = "Company"
) -> bytes:
    """Generate professional DCF Excel workbook with LIVE formulas."""
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True})

    fmt_title = wb.add_format({"bold": True, "font_size": 14, "font_color": "#1e293b"})
    fmt_header = wb.add_format(
        {
            "bold": True,
            "bg_color": "#0f172a",
            "font_color": "#ffffff",
            "border": 1,
            "align": "center",
        }
    )
    fmt_currency = wb.add_format({"num_format": "$#,##0.00", "border": 1})
    fmt_pct = wb.add_format({"num_format": "0.0%", "border": 1})
    fmt_bold_curr = wb.add_format(
        {"bold": True, "num_format": "$#,##0.00", "border": 1, "bg_color": "#f1f5f9"}
    )
    fmt_label = wb.add_format({"bold": True, "border": 1})
    fmt_regular = wb.add_format({"border": 1})

    # Sheet 1: Assumptions
    ws_assump = wb.add_worksheet("Assumptions")
    ws_assump.set_column("A:A", 30)
    ws_assump.set_column("B:B", 18)

    ws_assump.write("A1", f"{company_name} - DCF Model Assumptions", fmt_title)
    assumptions_rows = [
        ("Base Revenue ($)", float(params["base_revenue"]), fmt_currency),
        ("Tax Rate", float(params["tax_rate"]), fmt_pct),
        ("WACC (Discount Rate)", float(params["wacc"]), fmt_pct),
        ("Terminal Growth Rate", float(params.get("terminal_growth", 0.025)), fmt_pct),
        ("Shares Outstanding", float(params["shares_outstanding"]), fmt_regular),
        ("Net Debt ($)", float(params.get("net_debt", 0)), fmt_currency),
        ("Depreciation % Revenue", float(params.get("depreciation_pct_revenue", 0.04)), fmt_pct),
        ("CapEx % Revenue", float(params.get("capex_pct_revenue", 0.05)), fmt_pct),
        (
            "NWC % Incremental Revenue",
            float(params.get("nwc_pct_incremental_revenue", 0.10)),
            fmt_pct,
        ),
    ]

    for idx, (lbl, val, fmt) in enumerate(assumptions_rows, start=3):
        ws_assump.write(f"A{idx}", lbl, fmt_label)
        ws_assump.write(f"B{idx}", val, fmt)

    # Sheet 2: DCF Forecast Model (WITH LIVE FORMULAS)
    ws_dcf = wb.add_worksheet("DCF Model")
    ws_dcf.set_column("A:A", 28)

    forecast_years = len(params["revenue_growth"])
    for col_idx in range(forecast_years):
        ws_dcf.set_column(col_idx + 1, col_idx + 1, 16)

    ws_dcf.write("A1", "Forecast Year", fmt_header)
    for col_idx in range(forecast_years):
        ws_dcf.write(0, col_idx + 1, f"Year {col_idx + 1}", fmt_header)

    ws_dcf.write("A2", "Revenue Growth Rate", fmt_label)
    for col_idx, g in enumerate(params["revenue_growth"]):
        ws_dcf.write(1, col_idx + 1, float(g), fmt_pct)

    ws_dcf.write("A3", "Revenue ($)", fmt_label)
    ws_dcf.write_formula(2, 1, "=Assumptions!B3*(1+B2)", fmt_currency)
    for col_idx in range(1, forecast_years):
        col_letter = chr(ord("B") + col_idx)
        prev_letter = chr(ord("B") + col_idx - 1)
        ws_dcf.write_formula(2, col_idx + 1, f"={prev_letter}3*(1+{col_letter}2)", fmt_currency)

    ws_dcf.write("A4", "EBIT Margin", fmt_label)
    margins = params["ebit_margin"]
    if len(margins) == 1:
        margins = margins * forecast_years
    for col_idx, m in enumerate(margins):
        ws_dcf.write(3, col_idx + 1, float(m), fmt_pct)

    ws_dcf.write("A5", "EBIT ($)", fmt_label)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(4, col_idx + 1, f"={col_letter}3*{col_letter}4", fmt_currency)

    ws_dcf.write("A6", "NOPAT ($)", fmt_label)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(5, col_idx + 1, f"={col_letter}5*(1-Assumptions!$B$4)", fmt_currency)

    ws_dcf.write("A7", "FCFF ($)", fmt_bold_curr)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(
            6,
            col_idx + 1,
            f"={col_letter}6+{col_letter}3*Assumptions!$B$9-{col_letter}3*Assumptions!$B$10",
            fmt_bold_curr,
        )

    ws_dcf.write("A8", "Present Value ($)", fmt_currency)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(
            7, col_idx + 1, f"={col_letter}7/((1+Assumptions!$B$5)^{col_idx + 1})", fmt_currency
        )

    # Sheet 3: Valuation Summary
    ws_sum = wb.add_worksheet("Valuation Summary")
    ws_sum.set_column("A:A", 32)
    ws_sum.set_column("B:B", 20)

    ws_sum.write("A1", "Valuation Summary & Bridge", fmt_title)
    last_col = chr(ord("B") + forecast_years - 1)

    ws_sum.write("A3", "Sum of PV of Explicit FCFF", fmt_label)
    ws_sum.write_formula("B3", f"=SUM('DCF Model'!B8:{last_col}8)", fmt_currency)

    ws_sum.write("A4", "Terminal Value (PV)", fmt_label)
    ws_sum.write("B4", result["terminal_value_pv"], fmt_currency)

    ws_sum.write("A5", "Enterprise Value ($)", fmt_header)
    ws_sum.write_formula("B5", "=B3+B4", fmt_bold_curr)

    ws_sum.write("A6", "Less: Net Debt", fmt_label)
    ws_sum.write_formula("B6", "=Assumptions!B8", fmt_currency)

    ws_sum.write("A7", "Implied Equity Value ($)", fmt_header)
    ws_sum.write_formula("B7", "=B5-B6", fmt_bold_curr)

    ws_sum.write("A8", "Shares Outstanding", fmt_label)
    ws_sum.write_formula("B8", "=Assumptions!B7", fmt_regular)

    ws_sum.write("A9", "Implied Value Per Share ($)", fmt_header)
    ws_sum.write_formula("B9", "=B7/B8", fmt_bold_curr)

    wb.close()
    return output.getvalue()
