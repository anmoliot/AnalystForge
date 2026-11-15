"""Valuation services: DCF execution, WACC derivation, sensitivity tables, Monte Carlo, and Excel formula export."""

from __future__ import annotations

import io
import math
import uuid
from decimal import Decimal
from typing import Any

import numpy as np
import xlsxwriter
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.research import FundamentalFact
from analystforge.api.models.valuation import ValuationModel, ValuationVersion
from analystforge.quant.dcf import DCFAssumptions, DCFResult, TerminalValueMethod, run_dcf
from analystforge.quant.money import to_decimal
from analystforge.quant.wacc import (
    after_tax_cost_of_debt,
    capm_cost_of_equity,
    compute_wacc,
    wacc_from_capm,
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
        depreciation_pct_revenue=to_decimal(params.get("depreciation_pct_revenue", Decimal("0.04"))),
        capex_pct_revenue=to_decimal(params.get("capex_pct_revenue", Decimal("0.05"))),
        nwc_pct_incremental_revenue=to_decimal(params.get("nwc_pct_incremental_revenue", Decimal("0.10"))),
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
            except Exception:
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
    """Run Monte Carlo simulation on growth and margin drivers using an explicit RNG."""
    rng = np.random.default_rng(seed)
    base_growth = [float(g) for g in params["revenue_growth"]]
    base_margin = [float(m) for m in params["ebit_margin"]]
    if len(base_margin) == 1:
        base_margin = base_margin * len(base_growth)

    values: list[float] = []
    for _ in range(iterations):
        # Sample normal variation around growth (+/- 2% vol) and margin (+/- 1.5% vol)
        sim_growth = [g + float(rng.normal(0, 0.015)) for g in base_growth]
        sim_margin = [max(0.01, m + float(rng.normal(0, 0.01))) for m in base_margin]

        p = dict(params)
        p["revenue_growth"] = sim_growth
        p["ebit_margin"] = sim_margin
        try:
            res = execute_dcf(p)
            values.append(res["value_per_share"])
        except Exception:
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

    # Formats
    fmt_title = wb.add_format({"bold": True, "font_size": 14, "font_color": "#1e293b"})
    fmt_header = wb.add_format({
        "bold": True,
        "bg_color": "#0f172a",
        "font_color": "#ffffff",
        "border": 1,
        "align": "center",
    })
    fmt_currency = wb.add_format({"num_format": "$#,##0.00", "border": 1})
    fmt_pct = wb.add_format({"num_format": "0.0%", "border": 1})
    fmt_bold_curr = wb.add_format({"bold": True, "num_format": "$#,##0.00", "border": 1, "bg_color": "#f1f5f9"})
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
        ("NWC % Incremental Revenue", float(params.get("nwc_pct_incremental_revenue", 0.10)), fmt_pct),
    ]

    for idx, (lbl, val, fmt) in enumerate(assumptions_rows, start=3):
        ws_assump.write(f"A{idx}", lbl, fmt_label)
        ws_assump.write(f"B{idx}", val, fmt)

    # Sheet 2: DCF Forecast Model (WITH LIVE FORMULAS!)
    ws_dcf = wb.add_worksheet("DCF Model")
    ws_dcf.set_column("A:A", 28)

    forecast_years = len(params["revenue_growth"])
    for col_idx in range(forecast_years):
        ws_dcf.set_column(col_idx + 1, col_idx + 1, 16)

    ws_dcf.write("A1", "Forecast Year", fmt_header)
    for col_idx in range(forecast_years):
        ws_dcf.write(0, col_idx + 1, f"Year {col_idx + 1}", fmt_header)

    # Growth rate row
    ws_dcf.write("A2", "Revenue Growth Rate", fmt_label)
    for col_idx, g in enumerate(params["revenue_growth"]):
        ws_dcf.write(1, col_idx + 1, float(g), fmt_pct)

    # Revenue row (live formulas referencing prior column and growth)
    ws_dcf.write("A3", "Revenue ($)", fmt_label)
    ws_dcf.write_formula(2, 1, "=Assumptions!B3*(1+B2)", fmt_currency)
    for col_idx in range(1, forecast_years):
        col_letter = chr(ord("B") + col_idx)
        prev_letter = chr(ord("B") + col_idx - 1)
        ws_dcf.write_formula(2, col_idx + 1, f"={prev_letter}3*(1+{col_letter}2)", fmt_currency)

    # EBIT Margin row
    ws_dcf.write("A4", "EBIT Margin", fmt_label)
    margins = params["ebit_margin"]
    if len(margins) == 1:
        margins = margins * forecast_years
    for col_idx, m in enumerate(margins):
        ws_dcf.write(3, col_idx + 1, float(m), fmt_pct)

    # EBIT row = Revenue * Margin
    ws_dcf.write("A5", "EBIT ($)", fmt_label)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(4, col_idx + 1, f"={col_letter}3*{col_letter}4", fmt_currency)

    # NOPAT = EBIT * (1 - Tax Rate)
    ws_dcf.write("A6", "NOPAT ($)", fmt_label)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(5, col_idx + 1, f"={col_letter}5*(1-Assumptions!$B$4)", fmt_currency)

    # Free Cash Flow to Firm (FCFF)
    ws_dcf.write("A7", "FCFF ($)", fmt_bold_curr)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        # Simplified FCFF formula for model sheet
        ws_dcf.write_formula(6, col_idx + 1, f"={col_letter}6+{col_letter}3*Assumptions!$B$9-{col_letter}3*Assumptions!$B$10", fmt_bold_curr)

    # Present Value of FCFF = FCFF / (1 + WACC)^Year
    ws_dcf.write("A8", "Present Value ($)", fmt_currency)
    for col_idx in range(forecast_years):
        col_letter = chr(ord("B") + col_idx)
        ws_dcf.write_formula(7, col_idx + 1, f"={col_letter}7/((1+Assumptions!$B$5)^{col_idx + 1})", fmt_currency)

    # Sheet 3: Valuation Summary (with live formulas referencing DCF sheet)
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
