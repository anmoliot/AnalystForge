"""SQLAlchemy ORM models.

Importing this package registers all tables on :class:`analystforge.api.db.Base`
metadata so Alembic and ``create_all`` see the full schema.
"""

from analystforge.api.models.core import AuditLog, Tenant, User
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
from analystforge.api.models.research import Filing, FundamentalFact

__all__ = [
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
    "PriceBar",
    "ProviderHealthRecord",
    "Tenant",
    "User",
]
