"""Comprehensive test suite for WP6: News analytics, Filings diff/navigation, Hybrid retrieval, and Research Assistant."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.db import Database
from analystforge.api.models.market import Exchange, Instrument, PriceBar
from analystforge.api.models.news import NewsArticle, NewsArticleInstrument
from analystforge.api.models.rag import DocumentChunk, ResearchCallLog, ResearchSession
from analystforge.api.models.research import Filing, FundamentalFact
from analystforge.api.services.filings_analytics import (
    diff_filing_sections,
    extract_key_metrics,
    parse_filing_sections,
)
from analystforge.api.services.llm import set_llm_provider
from analystforge.api.services.news_analytics import (
    analyze_sentiment,
    classify_topics,
    cluster_articles,
    deduplicate_articles,
    extract_article_content,
    get_sentiment_price_overlay,
    normalize_url,
    tag_instruments_in_text,
)
from analystforge.api.services.research_assistant import (
    REFUSAL_MESSAGE,
    execute_research_assistant_query,
    execute_tool,
    generate_research_note_draft,
)
from analystforge.api.services.retrieval import (
    chunk_text,
    compute_bm25_lexical_scores,
    compute_semantic_scores,
    hybrid_fuse_rankings,
    retrieve_relevant_passages,
)
from analystforge.providers.llm import (
    ChatMessage,
    DeterministicFakeLLMProvider,
    LLMRateLimitError,
    LLMResponse,
    ToolCall,
)
import sys
from pathlib import Path

# Ensure apps/api/tests directory is importable
_TESTS_DIR = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from eval_dataset import EVALUATION_QUESTIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded_research_data(db: Database) -> dict[str, Any]:
    """Seed test database with all 5 eval instruments, bars, filings, facts, and news."""
    async with db.session() as session:
        # Ensure exchanges exist
        for code, name, country, tz, ccy in [
            ("NASDAQ", "Nasdaq", "US", "America/New_York", "USD"),
            ("LSE", "London Stock Exchange", "GB", "Europe/London", "GBP"),
        ]:
            existing = (
                await session.execute(select(Exchange).where(Exchange.code == code))
            ).scalar_one_or_none()
            if not existing:
                session.add(
                    Exchange(code=code, name=name, country=country, timezone=tz, currency=ccy)
                )
        await session.flush()

        instrument_acc = 0
        instruments = {}
        for ticker, name, sector, currency, exch_code in [
            ("AAPL", "Apple Inc.", "Technology", "USD", "NASDAQ"),
            ("NVDA", "Nvidia Corp.", "Technology", "USD", "NASDAQ"),
            ("MSFT", "Microsoft Corp.", "Technology", "USD", "NASDAQ"),
            ("SHEL.L", "Shell plc", "Energy", "GBP", "LSE"),
            ("AZN.L", "AstraZeneca plc", "Health Care", "GBP", "LSE"),
        ]:
            instrument_acc += 1
            inst = Instrument(
                id=uuid.uuid4(),
                exchange_code=exch_code,
                ticker=ticker,
                name=name,
                asset_type="equity",
                sector=sector,
                currency=currency,
            )
            session.add(inst)
            await session.flush()

            # Price bars
            for i in range(10):
                bar = PriceBar(
                    instrument_id=inst.id,
                    ts=datetime(2025, 1, 10 + i, 0, 0, 0, tzinfo=UTC),
                    open=Decimal("180.00"),
                    high=Decimal("185.00"),
                    low=Decimal("179.00"),
                    close=Decimal(str(180.00 + i * 1.5)),
                    volume=50_000_000,
                    provider="yahoo",
                )
                session.add(bar)

            # SEC Filing
            accession = f"0000320193-24-0001{instrument_acc:02d}"
            filing = Filing(
                id=uuid.uuid4(),
                instrument_id=inst.id,
                accession=accession,
                form="10-K",
                filed_date=date(2024, 11, 1),
                period_of_report=date(2024, 9, 28),
                primary_document=f"{ticker.lower().replace('.', '')}-20240928.htm",
                document_url=f"https://www.sec.gov/Archives/edgar/data/320193/{accession}/{ticker.lower().replace('.', '')}-20240928.htm",
                provider="sec_edgar",
            )
            session.add(filing)

            # Fundamental Facts (Revenue, Net Income, Diluted EPS)
            session.add_all(
                [
                    FundamentalFact(
                        instrument_id=inst.id,
                        taxonomy="us-gaap",
                        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
                        unit="USD",
                        value=Decimal("391035000000"),
                        period_start=date(2023, 10, 1),
                        period_end=date(2024, 9, 28),
                        fiscal_year=2024,
                        fiscal_period="FY",
                        form="10-K",
                        filed=date(2024, 11, 1),
                        accession=accession,
                        provider="sec_edgar",
                    ),
                    FundamentalFact(
                        instrument_id=inst.id,
                        taxonomy="us-gaap",
                        concept="NetIncomeLoss",
                        unit="USD",
                        value=Decimal("93736000000"),
                        period_start=date(2023, 10, 1),
                        period_end=date(2024, 9, 28),
                        fiscal_year=2024,
                        fiscal_period="FY",
                        form="10-K",
                        filed=date(2024, 11, 1),
                        accession=accession,
                        provider="sec_edgar",
                    ),
                    FundamentalFact(
                        instrument_id=inst.id,
                        taxonomy="us-gaap",
                        concept="EarningsPerShareDiluted",
                        unit="USD/shares",
                        value=Decimal("6.08"),
                        period_start=date(2023, 10, 1),
                        period_end=date(2024, 9, 28),
                        fiscal_year=2024,
                        fiscal_period="FY",
                        form="10-K",
                        filed=date(2024, 11, 1),
                        accession=accession,
                        provider="sec_edgar",
                    ),
                ]
            )

            # News article with sentiment
            art = NewsArticle(
                id=uuid.uuid4(),
                url=f"https://finance.yahoo.com/news/{ticker.lower().replace('.', '')}-record-quarter-2025.html",
                source="Yahoo Finance",
                title=f"{name} Posts Record Revenue Driven by Strong Growth",
                summary=f"{name} reported quarterly revenue growth beating analyst estimates, surging to new all-time records.",
                content=(
                    f"{name} reported quarterly revenue growth beating analyst estimates, surging to new all-time records. "
                    f"{sector} segment expanded rapidly across all major geographies."
                ),
                published_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
                sentiment_score=0.85,
                sentiment_label="positive",
                sentiment_confidence=0.92,
                sentiment_backend="lexical-fallback",
                topics=["Earnings & Financial Results"],
            )
            session.add(art)
            await session.flush()
            session.add(NewsArticleInstrument(article_id=art.id, instrument_id=inst.id))

            # Document chunk with risk-factor / business-content text relevant to grounded questions
            chunk_content = {
                "AAPL": (
                    "Apple designs and sells iPhone, Mac, iPad, wearables, and Services. "
                    "Revenue from iPhone and Services growth. Supply chain risks in China. "
                    "Customer concentration in carrier partnerships. Gross margin expansion from Services mix."
                ),
                "NVDA": (
                    "Nvidia designs GPUs and AI data center chips. Data center revenue growth. "
                    "Segment performance in gaming and professional visualization. "
                    "Customer concentration in cloud providers. Export controls and semiconductor supply constraints. "
                    "R&D investment in AI hardware."
                ),
                "MSFT": (
                    "Microsoft cloud infrastructure and AI data centers. Commercial cloud revenue. "
                    "Operating margins in Intelligent Cloud and Productivity. Customer concentration in enterprise. "
                    "Supply chain for data center hardware."
                ),
                "SHEL.L": (
                    "Shell LNG cargoes and upstream oil production. Operating cash flow. "
                    "Capital allocation and dividend. Climate transition risks. Commodity price volatility. "
                    "Customer concentration in energy trading."
                ),
                "AZN.L": (
                    "AstraZeneca oncology pipeline and clinical trials. Product revenue from cancer drugs. "
                    "Patent expiry risks. Pricing regulation. R&D expenditure. Gross margin on pharmaceutical products."
                ),
            }[ticker]
            chunk = DocumentChunk(
                instrument_id=inst.id,
                source_type="FILING",
                source_id=accession,
                title=f"{name} FY2024 10-K Item 1A Risk Factors",
                section="Item 1A. Risk Factors",
                content=chunk_content,
                chunk_index=0,
            )
            session.add(chunk)
            instruments[ticker] = inst

        await session.commit()
        return {"instrument": instruments["AAPL"], "instruments": instruments}


# ---------------------------------------------------------------------------
# Unit Tests: News Analytics & Ingestion
# ---------------------------------------------------------------------------


def test_news_full_text_extraction():
    html_sample = (
        "<html><body>"
        "<script>var x = 1;</script>"
        "<div class='article-content'>"
        "<p>Nvidia reported surging demand for Hopper and Blackwell AI accelerator chips across cloud hyperscalers.</p>"
        "</div>"
        "</body></html>"
    )
    extracted = extract_article_content(html_sample)
    assert extracted is not None
    assert "Blackwell AI accelerator" in extracted
    assert "<script>" not in extracted


def test_news_deduplication():
    u1 = "https://example.com/news/article-1?utm_source=twitter&utm_medium=social"
    u2 = "https://example.com/news/article-1"
    assert normalize_url(u1) == normalize_url(u2)

    arts = [
        {"url": u1, "title": "Fed Holds Policy Rates Steady at 5.25%", "summary": "Fed decision summary."},
        {"url": u2, "title": "Fed Holds Policy Rates Steady at 5.25%", "summary": "Fed decision summary duplicate."},
        {"url": "https://example.com/news/different", "title": "Tech Stocks Surge on AI Guidance", "summary": "Tech rally."},
    ]
    deduped = deduplicate_articles(arts)
    assert len(deduped) == 2


def test_news_sentiment_analysis():
    bullish_text = "Company reported record quarterly revenue, surging profits, beating estimates with strong dividend growth."
    bearish_text = "The firm posted massive quarterly losses, suffering severe revenue declines, debt defaults, and an SEC investigation."
    neutral_text = "The company filed its standard administrative form with regulatory bodies for the period ending Tuesday."

    sent_pos = analyze_sentiment(bullish_text)
    assert sent_pos["label"] == "positive"
    assert sent_pos["score"] > 0.2

    sent_neg = analyze_sentiment(bearish_text)
    assert sent_neg["label"] == "negative"
    assert sent_neg["score"] < -0.2

    sent_neu = analyze_sentiment(neutral_text)
    assert sent_neu["label"] == "neutral"


def test_news_topic_classification():
    text1 = "Quarterly revenue and earnings per share exceeded consensus guidance with expanding profit margins."
    text2 = "Semiconductor manufacturer launches next-generation artificial intelligence GPU chip platform with software stack."
    topics1 = classify_topics(text1)
    topics2 = classify_topics(text2)
    assert "Earnings & Financial Results" in topics1
    assert "Product, Technology & AI" in topics2


# ---------------------------------------------------------------------------
# Unit Tests: Filings Navigation & Diff
# ---------------------------------------------------------------------------


def test_filing_sections_navigation():
    text = (
        "ITEM 1. BUSINESS\nApple designs and sells smartphones and personal computing platforms.\n\n"
        "ITEM 1A. RISK FACTORS\nWe face risks regarding global supply chains and trade tariffs.\n\n"
        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS\nRevenue grew 8%.\n\n"
        "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\nConsolidated balance sheets."
    )
    parsed = parse_filing_sections(text, form="10-K")
    assert "item_1" in parsed["sections"]
    assert "item_1a" in parsed["sections"]
    assert "item_7" in parsed["sections"]
    assert "item_8" in parsed["sections"]
    assert "supply chains" in parsed["sections"]["item_1a"]["content"]


def test_filings_section_diff():
    prior = "We depend on international manufacturing partners. We face semiconductor supply constraints."
    current = (
        "We depend on international manufacturing partners. We face semiconductor supply constraints.\n\n"
        "Rapid adoption of generative artificial intelligence introduces new cybersecurity vulnerabilities and regulatory scrutiny."
    )
    diff = diff_filing_sections(prior, current)
    assert diff["similarity_ratio"] < 1.0
    assert diff["added_paragraph_count"] >= 1
    assert any("artificial intelligence" in r or "cybersecurity" in r for r in diff["emerging_risk_factors"])


# ---------------------------------------------------------------------------
# Unit Tests: Retrieval (Lexical, Semantic & Hybrid RRF)
# ---------------------------------------------------------------------------


def test_chunking_and_hybrid_scoring():
    text = "Sentence one is about Apple revenue growth. Sentence two discusses operating margins. Sentence three addresses iPhone market share."
    chunks = chunk_text(text, chunk_size=50, overlap=10)
    assert len(chunks) >= 2

    docs = [
        "Apple posted strong quarterly revenue and net income.",
        "Nvidia designs GPUs and artificial intelligence data centers.",
        "Shell produces liquefied natural gas and crude oil.",
    ]
    bm25 = compute_bm25_lexical_scores("Apple revenue", docs)
    assert bm25[0] > bm25[1]
    assert bm25[0] > bm25[2]

    sem, backend = compute_semantic_scores("Apple revenue", docs)
    assert sem[0] > sem[1]

    fused = hybrid_fuse_rankings(bm25, sem)
    assert fused[0] > fused[1]
    assert fused[0] > fused[2]


# ---------------------------------------------------------------------------
# API Integration Tests (Research Assistant, Groundedness, Tools & Refusal)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_assistant_query_grounded_answer(
    client: AsyncClient,
    seeded_research_data: dict[str, Any],
):
    # Set deterministic fake provider with grounded response containing citations
    fake_provider = DeterministicFakeLLMProvider({
        "Apple": "[citation:1] Apple Inc. reported record revenue driven by Services growth. [citation:2] Diluted EPS reached $6.08 in FY2024 disclosures.",
    })
    set_llm_provider(fake_provider)

    res = await client.post(
        "/api/v1/research/query",
        json={"query": "What are Apple's revenue and EPS figures?", "ticker": "AAPL"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["citations"]) >= 1
    assert not data["refusal"]
    assert data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_research_assistant_strict_refusal_on_unsupported_query(
    client: AsyncClient,
    seeded_research_data: dict[str, Any],
):
    # Query with non-existent entity and ungrounded topic
    fake_provider = DeterministicFakeLLMProvider()
    set_llm_provider(fake_provider)

    res = await client.post(
        "/api/v1/research/query",
        json={"query": "What was the profit of Hogwarts Magic Academy in 2024?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["refusal"] is True
    assert REFUSAL_MESSAGE in data["answer"]
    assert len(data["citations"]) == 0


@pytest.mark.asyncio
async def test_research_tool_execution(
    client: AsyncClient,
    seeded_research_data: dict[str, Any],
):
    # Test get_ratios tool
    res_ratios = await client.post(
        "/api/v1/research/tools/execute",
        json={"name": "get_ratios", "arguments": {"ticker": "AAPL"}},
    )
    assert res_ratios.status_code == 200
    data_ratios = res_ratios.json()
    assert data_ratios["ticker"] == "AAPL"
    assert "trailing_pe" in data_ratios
    assert "roe_pct" in data_ratios

    # Test quick_dcf tool
    res_dcf = await client.post(
        "/api/v1/research/tools/execute",
        json={"name": "quick_dcf", "arguments": {"ticker": "AAPL", "wacc": 0.085, "terminal_growth": 0.02}},
    )
    assert res_dcf.status_code == 200
    data_dcf = res_dcf.json()
    assert "implied_fair_share_price" in data_dcf


@pytest.mark.asyncio
async def test_research_filings_and_news_endpoints(
    client: AsyncClient,
    seeded_research_data: dict[str, Any],
):
    # Filings sections
    res_sec = await client.get("/api/v1/research/filings/AAPL/sections")
    assert res_sec.status_code == 200
    assert "sections" in res_sec.json()

    # Filings diff
    res_diff = await client.get("/api/v1/research/filings/AAPL/diff?section=item_1a")
    assert res_diff.status_code == 200
    diff_data = res_diff.json()
    assert "similarity_ratio" in diff_data

    # News sentiment overlay
    res_sent = await client.get("/api/v1/research/news/AAPL/sentiment?days=30")
    assert res_sent.status_code == 200
    sent_data = res_sent.json()
    assert sent_data["ticker"] == "AAPL"
    assert "points" in sent_data


@pytest.mark.asyncio
async def test_research_note_draft_generation(
    client: AsyncClient,
    seeded_research_data: dict[str, Any],
):
    res = await client.post(
        "/api/v1/research/notes/draft",
        json={"ticker": "AAPL"},
    )
    assert res.status_code == 200
    note = res.json()
    assert "snapshot" in note
    assert "thesis" in note
    assert "risks" in note
    assert "valuation_summary" in note


# ---------------------------------------------------------------------------
# 50-Question Benchmark Evaluation Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_50_question_eval_benchmark(
    db: Database,
    seeded_research_data: dict[str, Any],
):
    """Run full 50-question evaluation suite verifying grounding and 100% refusal on trap questions."""
    assert len(EVALUATION_QUESTIONS) == 50

    fake_provider = DeterministicFakeLLMProvider({
        "Apple": "[citation:1] Apple revenue and EPS trajectory demonstrated in audited filings.",
        "Nvidia": "[citation:1] Nvidia data center hardware segment shows strong revenue momentum.",
        "Microsoft": "[citation:1] Microsoft intelligent cloud and commercial subscriptions expanded.",
        "Shell": "[citation:1] Shell operating cash flow and upstream LNG performance.",
        "AstraZeneca": "[citation:1] AstraZeneca pharmaceutical oncology pipeline.",
    })

    refusal_count = 0
    grounded_count = 0

    async with db.session() as session:
        for item in EVALUATION_QUESTIONS:
            query = item["question"]
            ticker = item.get("ticker")
            expected_refusal = item["expected_refusal"]

            result = await execute_research_assistant_query(
                query=query,
                session=session,
                ticker=ticker,
                provider=fake_provider,
            )

            if expected_refusal:
                assert result["refusal"] is True, f"Failed refusal on question {item['id']}: {query}"
                assert REFUSAL_MESSAGE in result["answer"]
                refusal_count += 1
            else:
                assert result["refusal"] is False, f"Unexpected refusal on question {item['id']}: {query}"
                assert len(result["citations"]) >= 1
                grounded_count += 1

    assert refusal_count == 20
    assert grounded_count == 30
