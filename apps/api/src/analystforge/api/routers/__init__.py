"""Versioned API router assembly."""

from fastapi import APIRouter

from analystforge.api.routers import (
    alerts,
    auth,
    backtest,
    company,
    data,
    macro,
    meta,
    portfolio,
    reports,
    research,
    screener,
    valuation,
)

api_router = APIRouter()
api_router.include_router(meta.router)
api_router.include_router(auth.router)
api_router.include_router(company.router)
api_router.include_router(valuation.router)
api_router.include_router(portfolio.router)
api_router.include_router(backtest.router)
api_router.include_router(screener.router)
api_router.include_router(macro.router)
api_router.include_router(alerts.router)
api_router.include_router(research.router)
api_router.include_router(reports.router)
api_router.include_router(data.router)
