"""Backtesting API (Phase 7).

The Phase 7 build agent owns this module; it is registered centrally in
``analystforge.api.routers.__init__`` so the shared registry never changes.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/backtests", tags=["backtesting"])
