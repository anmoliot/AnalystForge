"""Macro dashboard and economic indicator APIs.

Real FRED data only:
- Yield curve points (1M, 3M, 6M, 1Y, 2Y, 5Y, 10Y, 30Y) with current vs historical comparison (1M ago, 1Y ago)
- Key macro indicators: CPI, Real GDP, Civilian Unemployment Rate, Fed Funds Policy Rate, Credit Spreads (High Yield OAS)
- Real as-of observation dates and timestamps
- Transparent data-unavailable feedback when FRED keys or series are uningested
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import desc, select

from analystforge.api.deps import SessionDep
from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries

router = APIRouter(prefix="/macro", tags=["macro"])

_YIELD_CURVE_TENORS: list[tuple[str, str]] = [
    ("1M", "DGS1MO"),
    ("3M", "DGS3MO"),
    ("6M", "DGS6MO"),
    ("1Y", "DGS1"),
    ("2Y", "DGS2"),
    ("5Y", "DGS5"),
    ("10Y", "DGS10"),
    ("30Y", "DGS30"),
]


@router.get("/series", summary="Get key economic indicators and historical series")
async def get_macro_indicators(session: SessionDep, request: Request) -> list[dict[str, Any]]:
    settings = getattr(request.app.state, "settings", None)
    demo_mode = getattr(settings, "demo_mode", False) if settings else False

    series_stmt = select(MacroSeries).order_by(MacroSeries.code)
    series_list = (await session.execute(series_stmt)).scalars().all()

    results: list[dict[str, Any]] = []

    for s in series_list:
        obs_stmt = (
            select(MacroObservation.day, MacroObservation.value)
            .where(MacroObservation.series_code == s.code)
            .order_by(desc(MacroObservation.day))
            .limit(60)
        )
        obs_rows = (await session.execute(obs_stmt)).fetchall()

        latest_val = float(obs_rows[0][1]) if obs_rows and obs_rows[0][1] is not None else None
        latest_date = obs_rows[0][0].isoformat() if obs_rows else None
        prior_val = float(obs_rows[1][1]) if len(obs_rows) > 1 and obs_rows[1][1] is not None else latest_val
        change = latest_val - prior_val if latest_val is not None and prior_val is not None else 0.0

        results.append({
            "code": s.code,
            "id": s.code,
            "title": s.title,
            "units": s.units,
            "frequency": s.frequency,
            "provider": s.provider or "FRED",
            "latest_value": latest_val,
            "latest_date": latest_date,
            "as_of": latest_date,
            "change": round(change, 4),
            "history": [
                {"date": r[0].isoformat(), "value": float(r[1]) if r[1] is not None else None}
                for r in reversed(obs_rows)
            ],
        })

    # Return empty list if no series ingested, unless explicit DEMO mode is enabled
    if not results and demo_mode:
        today = date.today()
        standard_demo = [
            ("DGS10", "10-Year Treasury Constant Maturity Rate [DEMO]", "%", "Daily", 4.35, -0.04),
            ("DGS2", "2-Year Treasury Constant Maturity Rate [DEMO]", "%", "Daily", 4.22, -0.06),
            ("FEDFUNDS", "Federal Funds Effective Rate [DEMO]", "%", "Monthly", 4.83, 0.0),
            ("CPIAUCSL", "Consumer Price Index (CPI All Urban) [DEMO]", "Index", "Monthly", 315.2, 0.8),
            ("UNRATE", "Civilian Unemployment Rate [DEMO]", "%", "Monthly", 4.1, 0.0),
            ("GDPC1", "Real Gross Domestic Product [DEMO]", "Bil. Chn. 2017 $", "Quarterly", 22850.0, 70.0),
        ]
        for s_id, title, units, freq, val, chg in standard_demo:
            results.append({
                "code": s_id,
                "id": s_id,
                "title": title,
                "units": units,
                "frequency": freq,
                "provider": "DEMO",
                "latest_value": val,
                "latest_date": today.isoformat(),
                "as_of": today.isoformat(),
                "change": chg,
                "history": [
                    {"date": (today - timedelta(days=i * 7)).isoformat(), "value": round(val - (i * chg * 0.2), 3)}
                    for i in reversed(range(12))
                ],
            })

    return results


@router.get("/series/{code}", summary="Get detailed observations for a macroeconomic series")
async def get_series_detail(code: str, session: SessionDep) -> dict[str, Any]:
    series = await session.get(MacroSeries, code)
    if not series:
        raise HTTPException(status_code=404, detail=f"Macro series '{code}' not found.")

    obs_stmt = (
        select(MacroObservation.day, MacroObservation.value)
        .where(MacroObservation.series_code == code)
        .order_by(MacroObservation.day.asc())
        .limit(365)
    )
    obs_rows = (await session.execute(obs_stmt)).fetchall()
    latest_date = obs_rows[-1][0].isoformat() if obs_rows else None
    return {
        "code": series.code,
        "title": series.title,
        "units": series.units,
        "frequency": series.frequency,
        "as_of": latest_date,
        "observations": [
            {"day": r[0].isoformat(), "value": float(r[1]) if r[1] is not None else None}
            for r in obs_rows
            if r[1] is not None
        ],
    }


@router.get("/yield-curve", summary="US Treasury yield curve structure, historical comparisons, and slope")
async def get_yield_curve(session: SessionDep, request: Request) -> dict[str, Any]:
    settings = getattr(request.app.state, "settings", None)
    fred_configured = bool(settings.provider_key("fred")) if settings else False
    demo_mode = getattr(settings, "demo_mode", False) if settings else False

    curve_tenors: list[dict[str, Any]] = []
    curve_1m_ago: list[dict[str, Any]] = []
    curve_1y_ago: list[dict[str, Any]] = []

    latest_days: list[date] = []
    rate_map: dict[str, float] = {}

    for tenor, code in _YIELD_CURVE_TENORS:
        # Latest observation
        stmt_latest = (
            select(MacroObservation.day, MacroObservation.value)
            .where(MacroObservation.series_code == code)
            .order_by(desc(MacroObservation.day))
            .limit(1)
        )
        row = (await session.execute(stmt_latest)).first()
        if row and row[1] is not None:
            rate_val = float(row[1])
            rate_map[code] = rate_val
            obs_day: date = row[0]
            latest_days.append(obs_day)
            curve_tenors.append({"tenor": tenor, "rate": rate_val, "as_of": obs_day.isoformat()})

            # Historical 1 Month Ago (~30 days prior)
            target_1m = obs_day - timedelta(days=30)
            stmt_1m = (
                select(MacroObservation.day, MacroObservation.value)
                .where(MacroObservation.series_code == code, MacroObservation.day <= target_1m)
                .order_by(desc(MacroObservation.day))
                .limit(1)
            )
            row_1m = (await session.execute(stmt_1m)).first()
            if row_1m and row_1m[1] is not None:
                curve_1m_ago.append({"tenor": tenor, "rate": float(row_1m[1]), "as_of": row_1m[0].isoformat()})

            # Historical 1 Year Ago (~365 days prior)
            target_1y = obs_day - timedelta(days=365)
            stmt_1y = (
                select(MacroObservation.day, MacroObservation.value)
                .where(MacroObservation.series_code == code, MacroObservation.day <= target_1y)
                .order_by(desc(MacroObservation.day))
                .limit(1)
            )
            row_1y = (await session.execute(stmt_1y)).first()
            if row_1y and row_1y[1] is not None:
                curve_1y_ago.append({"tenor": tenor, "rate": float(row_1y[1]), "as_of": row_1y[0].isoformat()})

    if curve_tenors:
        rate_10y = rate_map.get("DGS10")
        rate_2y = rate_map.get("DGS2")
        spread_10_2: float | None = None
        is_inverted = False
        if rate_10y is not None and rate_2y is not None:
            spread_10_2 = round(rate_10y - rate_2y, 4)
            is_inverted = spread_10_2 < 0
        as_of = max(latest_days).isoformat() if latest_days else None
        return {
            "configured": fred_configured,
            "message": None,
            "as_of": as_of,
            "spread_10y_2y": spread_10_2,
            "is_inverted": is_inverted,
            "curve": curve_tenors,
            "curve_1m_ago": curve_1m_ago,
            "curve_1y_ago": curve_1y_ago,
        }

    # If demo mode is explicitly enabled, return labeled demo data
    if demo_mode:
        today = date.today()
        demo_curve = [
            {"tenor": "1M", "rate": 4.60, "as_of": today.isoformat()},
            {"tenor": "3M", "rate": 4.55, "as_of": today.isoformat()},
            {"tenor": "6M", "rate": 4.45, "as_of": today.isoformat()},
            {"tenor": "1Y", "rate": 4.30, "as_of": today.isoformat()},
            {"tenor": "2Y", "rate": 4.22, "as_of": today.isoformat()},
            {"tenor": "5Y", "rate": 4.18, "as_of": today.isoformat()},
            {"tenor": "10Y", "rate": 4.35, "as_of": today.isoformat()},
            {"tenor": "30Y", "rate": 4.55, "as_of": today.isoformat()},
        ]
        spread = round(4.35 - 4.22, 4)
        return {
            "configured": False,
            "message": "DEMO MODE: Showing illustrative yield curve",
            "as_of": today.isoformat(),
            "spread_10y_2y": spread,
            "is_inverted": spread < 0,
            "curve": demo_curve,
            "curve_1m_ago": [],
            "curve_1y_ago": [],
        }

    # Honest empty state: no fabricated numbers!
    msg = "FRED key not configured" if not fred_configured else "FRED yield curve data not yet ingested"
    return {
        "configured": fred_configured,
        "message": msg,
        "as_of": None,
        "spread_10y_2y": None,
        "is_inverted": False,
        "curve": [],
        "curve_1m_ago": [],
        "curve_1y_ago": [],
    }


@router.get("/fx", summary="Latest foreign exchange rates")
async def get_fx_rates(session: SessionDep, request: Request) -> list[dict[str, Any]]:
    settings = getattr(request.app.state, "settings", None)
    demo_mode = getattr(settings, "demo_mode", False) if settings else False

    fx_stmt = (
        select(FxRate)
        .order_by(desc(FxRate.day))
        .limit(100)
    )
    fx_rows = (await session.execute(fx_stmt)).scalars().all()

    rates: dict[str, Any] = {}
    for r in fx_rows:
        pair = f"{r.base}/{r.quote}"
        if pair not in rates:
            rates[pair] = {
                "pair": pair,
                "base": r.base,
                "quote": r.quote,
                "rate": float(r.rate),
                "date": r.day.isoformat(),
            }

    if not rates and demo_mode:
        default_pairs = [
            ("EUR", "USD", 1.085),
            ("GBP", "USD", 1.295),
            ("USD", "JPY", 154.2),
            ("USD", "CHF", 0.885),
            ("EUR", "GBP", 0.838),
        ]
        for base, quote, rate in default_pairs:
            pair = f"{base}/{quote}"
            rates[pair] = {
                "pair": pair,
                "base": base,
                "quote": quote,
                "rate": rate,
                "date": date.today().isoformat(),
            }

    return list(rates.values())
