"""Grounded research assistant, RAG, SEC filings, and news analytics API (Phase 9 & WP6)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from analystforge.api.deps import CurrentUser, CurrentUserOptional, SessionDep
from analystforge.api.models.core import User
from analystforge.api.models.market import Instrument
from analystforge.api.models.news import NewsArticle, NewsArticleInstrument
from analystforge.api.models.rag import DocumentChunk, ResearchMessage, ResearchSession
from analystforge.api.models.research import Filing, FundamentalFact
from analystforge.api.services.filings_analytics import (
    diff_filing_sections,
    extract_key_metrics,
    parse_filing_sections,
)
from analystforge.api.services.news_analytics import (
    analyze_sentiment,
    cluster_articles,
    get_sentiment_price_overlay,
)
from analystforge.api.services.research_assistant import (
    execute_research_assistant_query,
    execute_tool,
    generate_research_note_draft,
    stream_research_assistant_query,
)

router = APIRouter(prefix="/research", tags=["research"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    ticker: str | None = None
    session_id: uuid.UUID | None = None


class SessionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    ticker: str | None = None


class ToolExecuteRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class NoteDraftRequest(BaseModel):
    ticker: str


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post("/sessions", summary="Create a new research session")
async def create_research_session(
    payload: SessionCreateRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    res_session = ResearchSession(
        user_id=current_user.id,
        title=payload.title,
        ticker=payload.ticker.upper() if payload.ticker else None,
    )
    session.add(res_session)
    await session.commit()
    await session.refresh(res_session)

    return {
        "id": str(res_session.id),
        "title": res_session.title,
        "ticker": res_session.ticker,
        "created_at": res_session.created_at.isoformat(),
    }


@router.get("/sessions", summary="List user research sessions")
async def list_research_sessions(
    session: SessionDep,
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    stmt = (
        select(ResearchSession)
        .where(ResearchSession.user_id == current_user.id)
        .order_by(desc(ResearchSession.updated_at))
        .limit(50)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "title": r.title,
            "ticker": r.ticker,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/sessions/{session_id}", summary="Get research session messages and citations")
async def get_research_session(
    session_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    stmt = (
        select(ResearchSession)
        .where(
            ResearchSession.id == session_id,
            ResearchSession.user_id == current_user.id,
        )
        .options(selectinload(ResearchSession.messages))
    )
    res = (await session.execute(stmt)).scalar_one_or_none()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research session not found",
        )

    return {
        "id": str(res.id),
        "title": res.title,
        "ticker": res.ticker,
        "created_at": res.created_at.isoformat(),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "citations": m.citations or [],
                "created_at": m.created_at.isoformat(),
            }
            for m in res.messages
        ],
    }


# ---------------------------------------------------------------------------
# Grounded Research Query & SSE Streaming
# ---------------------------------------------------------------------------


@router.post("/query", summary="Grounded RAG query over filings, facts, and news")
async def query_research_assistant(
    payload: QueryRequest,
    session: SessionDep,
    current_user: CurrentUserOptional,
) -> dict[str, Any]:
    user_id = current_user.id if current_user else None
    return await execute_research_assistant_query(
        query=payload.query,
        session=session,
        ticker=payload.ticker,
        user_id=user_id,
        session_id=payload.session_id,
    )


@router.post("/stream", summary="SSE Streaming grounded research response")
async def stream_research_assistant(
    payload: QueryRequest,
    session: SessionDep,
    current_user: CurrentUserOptional,
) -> StreamingResponse:
    gen = stream_research_assistant_query(
        query=payload.query,
        session=session,
        ticker=payload.ticker,
        session_id=payload.session_id,
    )
    return StreamingResponse(gen, media_type="text/event-stream")


@router.post("/tools/execute", summary="Explicit audited tool call execution")
async def execute_research_tool(
    payload: ToolExecuteRequest,
    session: SessionDep,
    current_user: CurrentUserOptional,
) -> dict[str, Any]:
    return await execute_tool(payload.name, payload.arguments, session)


@router.post("/notes/draft", summary="Generate structured institutional research note draft")
async def create_research_note_draft(
    payload: NoteDraftRequest,
    session: SessionDep,
    current_user: CurrentUserOptional,
) -> dict[str, Any]:
    user_id = current_user.id if current_user else None
    return await generate_research_note_draft(payload.ticker, session, user_id=user_id)


# ---------------------------------------------------------------------------
# SEC Filings Endpoints (Navigation, Diff, Metrics)
# ---------------------------------------------------------------------------


@router.get("/filings/{ticker}", summary="Get recent SEC filings for ticker")
async def get_instrument_filings(
    ticker: str,
    session: SessionDep,
) -> list[dict[str, Any]]:
    ticker_clean = ticker.upper().strip()
    inst_stmt = select(Instrument).where(Instrument.ticker == ticker_clean)
    instrument = (await session.execute(inst_stmt)).scalar_one_or_none()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument '{ticker_clean}' not found",
        )

    filing_stmt = (
        select(Filing)
        .where(Filing.instrument_id == instrument.id)
        .order_by(desc(Filing.filed_date))
        .limit(20)
    )
    filings = (await session.execute(filing_stmt)).scalars().all()
    return [
        {
            "id": str(f.id),
            "accession": f.accession,
            "form": f.form,
            "filed_date": f.filed_date.isoformat(),
            "period_of_report": f.period_of_report.isoformat() if f.period_of_report else None,
            "primary_document": f.primary_document,
            "document_url": f.document_url,
            "provider": f.provider,
        }
        for f in filings
    ]


@router.get("/filings/{ticker}/sections", summary="Get standard Item sections for a filing")
async def get_filing_sections(
    ticker: str,
    session: SessionDep,
    accession: str | None = None,
) -> dict[str, Any]:
    ticker_clean = ticker.upper().strip()
    inst = (
        await session.execute(select(Instrument).where(Instrument.ticker == ticker_clean))
    ).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument '{ticker_clean}' not found")

    stmt = select(Filing).where(Filing.instrument_id == inst.id)
    if accession:
        stmt = stmt.where(Filing.accession == accession)
    stmt = stmt.order_by(desc(Filing.filed_date)).limit(1)
    filing = (await session.execute(stmt)).scalar_one_or_none()

    if not filing:
        raise HTTPException(status_code=404, detail=f"No filing found for '{ticker_clean}'")

    # Sample standard 10-K sections for navigation demonstration
    sample_text = (
        f"UNITED STATES SECURITIES AND EXCHANGE COMMISSION\n"
        f"FORM {filing.form} ANNUAL REPORT\n"
        f"ITEM 1. BUSINESS\n"
        f"{inst.name} is a global leader in {inst.sector}. The company designs, develops, and delivers high-performance solutions.\n\n"
        f"ITEM 1A. RISK FACTORS\n"
        f"Our business faces risks regarding supply chain bottlenecks, semiconductor availability, geopolitical trade tariffs, and foreign exchange fluctuations.\n\n"
        f"ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS\n"
        f"Total revenue increased 14% year-over-year driven by high enterprise customer demand and cloud software expansion.\n\n"
        f"ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n"
        f"Audited consolidated balance sheets and statements of operations filed herewith."
    )
    return parse_filing_sections(sample_text, form=filing.form)


@router.get("/filings/{ticker}/diff", summary="Period-over-period diff for Risk Factors or MD&A")
async def get_filings_section_diff(
    ticker: str,
    session: SessionDep,
    section: str = Query("item_1a", description="item_1a or item_7"),
) -> dict[str, Any]:
    ticker_clean = ticker.upper().strip()
    inst = (
        await session.execute(select(Instrument).where(Instrument.ticker == ticker_clean))
    ).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument '{ticker_clean}' not found")

    # Sample prior vs current section text for institutional comparison
    if section == "item_1a":
        prior = (
            "We face intense global market competition and cyclical demand.\n\n"
            "Fluctuations in interest rates and foreign exchange rates may negatively impact our financial performance.\n\n"
            "We depend on key third-party manufacturing partners for critical components."
        )
        current = (
            "We face intense global market competition and cyclical demand.\n\n"
            "Fluctuations in interest rates and foreign exchange rates may negatively impact our financial performance.\n\n"
            "We depend on key third-party manufacturing partners for critical components.\n\n"
            "Geopolitical trade restrictions and tariffs may limit access to raw materials and international markets.\n\n"
            "Rapid deployment of generative artificial intelligence and machine learning models exposes us to cybersecurity vulnerabilities and regulatory scrutiny."
        )
    else:
        prior = (
            "Consolidated revenue increased 8% due to steady enterprise software subscriptions.\n\n"
            "Operating margin contracted 50 bps reflecting increased research and development personnel expenses."
        )
        current = (
            "Consolidated revenue increased 14% due to accelerated cloud adoption and enterprise contract expansions.\n\n"
            "Operating margin expanded 120 bps reflecting operating leverage and disciplined capital expenditure."
        )

    return diff_filing_sections(prior, current)


@router.get("/filings/{ticker}/metrics", summary="Extract key financial metrics from fundamental facts")
async def get_filings_key_metrics(
    ticker: str,
    session: SessionDep,
) -> list[dict[str, Any]]:
    ticker_clean = ticker.upper().strip()
    inst = (
        await session.execute(select(Instrument).where(Instrument.ticker == ticker_clean))
    ).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument '{ticker_clean}' not found")

    facts = (
        await session.execute(
            select(FundamentalFact)
            .where(FundamentalFact.instrument_id == inst.id)
            .order_by(desc(FundamentalFact.period_end))
            .limit(50)
        )
    ).scalars().all()

    return extract_key_metrics(facts)


# ---------------------------------------------------------------------------
# News Analytics Endpoints (Sentiment, Topics, Overlay)
# ---------------------------------------------------------------------------


@router.get("/news/{ticker}", summary="Get recent news articles for ticker")
async def get_instrument_news(
    ticker: str,
    session: SessionDep,
) -> list[dict[str, Any]]:
    ticker_clean = ticker.upper().strip()
    inst_stmt = select(Instrument).where(Instrument.ticker == ticker_clean)
    instrument = (await session.execute(inst_stmt)).scalar_one_or_none()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument '{ticker_clean}' not found",
        )

    news_stmt = (
        select(NewsArticle)
        .join(NewsArticleInstrument, NewsArticle.id == NewsArticleInstrument.article_id)
        .where(NewsArticleInstrument.instrument_id == instrument.id)
        .order_by(desc(NewsArticle.published_at))
        .limit(20)
    )
    articles = (await session.execute(news_stmt)).scalars().all()
    return [
        {
            "id": str(a.id),
            "title": a.title,
            "source": a.source,
            "url": a.url,
            "summary": a.summary,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "sentiment_score": a.sentiment_score,
            "sentiment_label": a.sentiment_label,
            "sentiment_backend": a.sentiment_backend,
            "topics": a.topics or [],
        }
        for a in articles
    ]


@router.get("/news/{ticker}/sentiment", summary="Get daily sentiment breakdown and price overlay")
async def get_instrument_sentiment_overlay(
    ticker: str,
    session: SessionDep,
    days: int = Query(60, ge=7, le=365),
) -> dict[str, Any]:
    return await get_sentiment_price_overlay(session, ticker, days=days)


@router.get("/news/{ticker}/topics", summary="Topic clustering for instrument news")
async def get_instrument_news_topics(
    ticker: str,
    session: SessionDep,
) -> list[dict[str, Any]]:
    ticker_clean = ticker.upper().strip()
    inst = (
        await session.execute(select(Instrument).where(Instrument.ticker == ticker_clean))
    ).scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail=f"Instrument '{ticker_clean}' not found")

    news_stmt = (
        select(NewsArticle)
        .join(NewsArticleInstrument, NewsArticle.id == NewsArticleInstrument.article_id)
        .where(NewsArticleInstrument.instrument_id == inst.id)
        .order_by(desc(NewsArticle.published_at))
        .limit(30)
    )
    articles = (await session.execute(news_stmt)).scalars().all()
    items = [
        {
            "id": str(a.id),
            "title": a.title,
            "source": a.source,
            "summary": a.summary,
            "content": a.content,
            "published_at": a.published_at.isoformat() if a.published_at else None,
        }
        for a in articles
    ]
    return cluster_articles(items)
