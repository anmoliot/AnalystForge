"""SQLAlchemy ORM models.

Importing this package registers all tables on :class:`analystforge.api.db.Base`
metadata so Alembic and ``create_all`` see the full schema.
"""

from analystforge.api.models import backtest, rag, reporting, screener  # noqa: F401
from analystforge.api.models.core import ApiKey, AuditLog, RefreshToken, TOTPSecret, Tenant, User
from analystforge.api.models.macro import FxRate, MacroObservation, MacroSeries
from analystforge.api.models.market import (
    CorporateAction,
    Exchange,
    Instrument,
    InstrumentProviderSymbol,
    PriceBar,
)
from analystforge.api.models.news import NewsArticle, NewsArticleInstrument
from analystforge.api.models.ops import JobRun, ProviderHealthRecord
from analystforge.api.models.portfolio import Portfolio, PortfolioTransaction
from analystforge.api.models.research import Filing, FundamentalFact
from analystforge.api.models.valuation import ValuationModel, ValuationVersion

__all__ = [
    "ApiKey",
    "AuditLog",
    "CorporateAction",
    "Exchange",
    "Filing",
    "FundamentalFact",
    "FxRate",
    "Instrument",
    "InstrumentProviderSymbol",
    "JobRun",
    "MacroObservation",
    "MacroSeries",
    "NewsArticle",
    "NewsArticleInstrument",
    "Portfolio",
    "PortfolioTransaction",
    "PriceBar",
    "ProviderHealthRecord",
    "RefreshToken",
    "TOTPSecret",
    "Tenant",
    "User",
    "ValuationModel",
    "ValuationVersion",
]

