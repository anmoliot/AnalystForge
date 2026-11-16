"""News full-text extraction, deduplication, ticker tagging, sentiment analysis, and topic clustering."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import structlog
from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.market import Instrument, PriceBar
from analystforge.api.models.news import NewsArticle, NewsArticleInstrument

logger = structlog.get_logger("services.news_analytics")

# ---------------------------------------------------------------------------
# 1. Full-Text Extraction (trafilatura with HTML fallback)
# ---------------------------------------------------------------------------


def extract_article_content(html_or_text: str) -> str | None:
    """Extract clean main body article text using trafilatura."""
    if not html_or_text or not html_or_text.strip():
        return None

    # Check if looks like HTML
    if "<" in html_or_text and ">" in html_or_text:
        try:
            import trafilatura

            extracted = trafilatura.extract(
                html_or_text,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_links=False,
                output_format="txt",
            )
            if extracted and len(extracted.strip()) > 40:
                return extracted.strip()
        except Exception as exc:
            logger.debug("trafilatura.failed", error=str(exc))

        # Basic HTML strip fallback
        clean = re.sub(r"<script[^>]*>.*?</script>", "", html_or_text, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean if len(clean) > 20 else None

    return html_or_text.strip()


# ---------------------------------------------------------------------------
# 2. Deduplication (URL normalization + content hash + title similarity)
# ---------------------------------------------------------------------------


def normalize_url(url: str) -> str:
    """Normalize article URL by stripping tracking parameters, hashes, and default ports."""
    parsed = urlparse(url)
    # Strip tracking parameters
    qs = parse_qs(parsed.query)
    filtered_qs = {
        k: v
        for k, v in qs.items()
        if not (k.startswith("utm_") or k in {"ref", "fbclid", "gclid", "src", "source"})
    }
    normalized_query = urlencode(filtered_qs, doseq=True)
    clean_path = parsed.path.rstrip("/")
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        clean_path,
        parsed.params,
        normalized_query,
        "",  # Strip fragment
    ))


def content_hash(text: str) -> str:
    """Compute sha256 hash over normalized alphanumeric tokens."""
    tokens = re.findall(r"\w+", text.lower())
    norm = " ".join(tokens)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def title_similarity(t1: str, t2: str) -> float:
    """Compute token Jaccard similarity between two titles."""
    s1 = set(re.findall(r"\w+", t1.lower()))
    s2 = set(re.findall(r"\w+", t2.lower()))
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate a list of article dicts by normalized URL, content hash, and title similarity."""
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    unique: list[dict[str, Any]] = []

    for item in articles:
        url = normalize_url(str(item.get("url", "")))
        if url in seen_urls:
            continue

        body = str(item.get("content") or item.get("summary") or item.get("title") or "")
        h = content_hash(body)
        if h in seen_hashes and len(body) > 60:
            continue

        title = str(item.get("title", ""))
        # Check against recent titles in unique
        is_dup_title = False
        for u in unique[-15:]:
            if title_similarity(title, str(u.get("title", ""))) > 0.85:
                is_dup_title = True
                break
        if is_dup_title:
            continue

        seen_urls.add(url)
        seen_hashes.add(h)
        unique.append(item)

    return unique


# ---------------------------------------------------------------------------
# 3. Ticker Tagging
# ---------------------------------------------------------------------------


def tag_instruments_in_text(text: str, instruments: list[Instrument]) -> list[uuid.UUID]:
    """Tag instruments referenced in text using ticker boundaries and company name matching."""
    if not text or not instruments:
        return []

    matched_ids: set[uuid.UUID] = set()
    upper_text = text.upper()
    words = set(re.findall(r"[A-Z0-9\.]+", upper_text))

    for inst in instruments:
        ticker = inst.ticker.upper()
        # Direct word match (e.g. AAPL, MSFT, SHEL.L)
        if ticker in words or re.search(rf"\b{re.escape(ticker)}\b", upper_text):
            matched_ids.add(inst.id)
            continue

        # Also match unadorned ticker if exchange suffix present (e.g. SHEL for SHEL.L)
        base_sym = ticker.split(".")[0]
        if len(base_sym) >= 3 and re.search(rf"\b{re.escape(base_sym)}\b", upper_text):
            matched_ids.add(inst.id)
            continue

        # Company name match (excluding generic terms like 'Inc', 'Corp', 'Plc', 'Ltd')
        clean_name = re.sub(
            r"\b(Inc|Corp|Corporation|Plc|Ltd|Co|LLC|Group|Holdings|SA|AG|NV)\b\.?",
            "",
            inst.name,
            flags=re.IGNORECASE,
        ).strip()
        if len(clean_name) >= 4 and re.search(rf"\b{re.escape(clean_name)}\b", text, re.IGNORECASE):
            matched_ids.add(inst.id)

    return list(matched_ids)


# ---------------------------------------------------------------------------
# 4. Sentiment Analysis (FinBERT with Lexical Financial Fallback)
# ---------------------------------------------------------------------------

# Loughran-McDonald inspired financial dictionary
_FINANCIAL_POSITIVE = {
    "gain", "gains", "profit", "profits", "profitable", "beat", "beats", "beating",
    "surge", "surges", "surging", "growth", "growing", "outperform", "outperformed",
    "dividend", "dividends", "upgrade", "upgrades", "upgraded", "rally", "rallies",
    "expansion", "bullish", "record", "strong", "stronger", "upside", "upswing",
    "rebound", "recovery", "positive", "exceeded", "exceeds", "solid", "milestone",
    "breakthrough", "momentum", "soar", "soared", "soaring", "gainers", "top-line",
}

_FINANCIAL_NEGATIVE = {
    "loss", "losses", "decline", "declines", "declining", "plunge", "plunges", "plunging",
    "deficit", "downgrade", "downgrades", "downgraded", "litigation", "lawsuit", "lawsuits",
    "impairment", "risk", "risks", "fall", "falls", "falling", "miss", "misses", "missing",
    "slump", "slumps", "drop", "drops", "dropping", "bankruptcy", "warning", "warnings",
    "debt", "default", "defaults", "fraud", "weak", "weaker", "headwinds", "pressure",
    "probe", "investigation", "recession", "contraction", "subpoena", "penalty", "penalties",
    "bearish", "layoffs", "downside", "insolvency", "writedown", "fell",
}

_NEGATION_WORDS = {"not", "no", "never", "without", "failed", "fails", "failing", "hardly", "barely"}


def analyze_sentiment(text: str) -> dict[str, Any]:
    """Analyze financial sentiment using local FinBERT if available, otherwise lexical financial fallback."""
    if not text or not text.strip():
        return {
            "score": 0.0,
            "label": "neutral",
            "confidence": 0.5,
            "backend": "lexical-fallback",
            "probabilities": {"positive": 0.33, "neutral": 0.34, "negative": 0.33},
        }

    # Attempt FinBERT via transformers
    try:
        from transformers import pipeline  # type: ignore

        finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert", top_k=None)
        res = finbert(text[:512])[0]
        # Map labels to scores
        probs = {item["label"].lower(): float(item["score"]) for item in res}
        pos = probs.get("positive", 0.0)
        neg = probs.get("negative", 0.0)
        neu = probs.get("neutral", 0.0)
        compound = pos - neg
        label = "positive" if compound > 0.15 else ("negative" if compound < -0.15 else "neutral")
        conf = max(pos, neg, neu)
        return {
            "score": round(compound, 4),
            "label": label,
            "confidence": round(conf, 4),
            "backend": "finbert",
            "probabilities": {"positive": round(pos, 4), "neutral": round(neu, 4), "negative": round(neg, 4)},
        }
    except Exception:
        # Lexical financial fallback (Loughran-McDonald rules)
        pass

    words = re.findall(r"\b[a-zA-Z-]+\b", text.lower())
    if not words:
        return {
            "score": 0.0,
            "label": "neutral",
            "confidence": 0.5,
            "backend": "lexical-fallback",
            "probabilities": {"positive": 0.33, "neutral": 0.34, "negative": 0.33},
        }

    pos_count = 0
    neg_count = 0
    for idx, w in enumerate(words):
        is_negated = any(
            words[max(0, idx - k)] in _NEGATION_WORDS
            for k in range(1, min(4, idx + 1))
        )
        if w in _FINANCIAL_POSITIVE:
            if is_negated:
                neg_count += 1
            else:
                pos_count += 1
        elif w in _FINANCIAL_NEGATIVE:
            if is_negated:
                pos_count += 1
            else:
                neg_count += 1

    total = pos_count + neg_count
    if total == 0:
        return {
            "score": 0.0,
            "label": "neutral",
            "confidence": 0.8,
            "backend": "lexical-fallback",
            "probabilities": {"positive": 0.15, "neutral": 0.70, "negative": 0.15},
        }

    compound = (pos_count - neg_count) / max(1, total)
    pos_prob = pos_count / (total + 1.0)
    neg_prob = neg_count / (total + 1.0)
    neu_prob = 1.0 / (total + 1.0)
    label = "positive" if compound > 0.15 else ("negative" if compound < -0.15 else "neutral")
    conf = max(pos_prob, neg_prob, neu_prob)

    return {
        "score": round(float(compound), 4),
        "label": label,
        "confidence": round(float(conf), 4),
        "backend": "lexical-fallback",
        "probabilities": {
            "positive": round(pos_prob, 4),
            "neutral": round(neu_prob, 4),
            "negative": round(neg_prob, 4),
        },
    }


# ---------------------------------------------------------------------------
# 5. Topic Clustering
# ---------------------------------------------------------------------------

TOPIC_RULES = {
    "Earnings & Financial Results": {
        "earnings", "revenue", "profit", "eps", "quarter", "quarterly", "fiscal", "guidance",
        "ebitda", "net income", "sales", "margins", "operating profit", "cash flow",
    },
    "Mergers & Acquisitions": {
        "merger", "acquisition", "takeover", "acquire", "acquired", "buyout", "deal",
        "transaction", "tender offer", "spin-off", "divestiture", "purchase",
    },
    "Macroeconomics & Monetary Policy": {
        "inflation", "interest rate", "rates", "federal reserve", "fed", "ecb", "yield",
        "treasury", "central bank", "monetary policy", "gdp", "cpi", "unemployment", "recession",
    },
    "Regulatory, Legal & Governance": {
        "sec", "lawsuit", "antitrust", "regulator", "regulatory", "doj", "investigation",
        "compliance", "court", "probe", "fine", "penalty", "ruling", "whistleblower",
    },
    "Product, Technology & AI": {
        "ai", "artificial intelligence", "chips", "gpu", "semiconductor", "software",
        "cloud", "patent", "launch", "product", "platform", "model", "hardware", "device",
    },
    "Capital Structure & Buybacks": {
        "buyback", "share repurchase", "dividend", "dividends", "offering", "bonds",
        "notes", "debt offering", "equity financing", "convertible", "refinancing",
    },
}


def classify_topics(text: str) -> list[str]:
    """Classify text into dominant financial topics using signature keyword matching."""
    lower = text.lower()
    scores: dict[str, int] = {}
    for topic, keywords in TOPIC_RULES.items():
        hits = sum(1 for kw in keywords if re.search(rf"\b{re.escape(kw)}\b", lower))
        if hits > 0:
            scores[topic] = hits

    if not scores:
        return ["General Corporate"]

    sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [t[0] for t in sorted_topics[:3]]


def cluster_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group articles into topic clusters with metadata."""
    clusters: dict[str, list[dict[str, Any]]] = {}
    for a in articles:
        text = f"{a.get('title', '')} {a.get('summary', '')} {a.get('content', '')}"
        topics = classify_topics(text)
        primary_topic = topics[0]
        clusters.setdefault(primary_topic, []).append(a)

    return [
        {
            "topic": topic,
            "article_count": len(arts),
            "articles": arts[:10],
        }
        for topic, arts in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
    ]


# ---------------------------------------------------------------------------
# 6. Database Aggregation & Sentiment-Price Overlay
# ---------------------------------------------------------------------------


async def aggregate_ticker_sentiment(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Aggregate daily news sentiment scores for an instrument."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            func.date(NewsArticle.published_at).label("day"),
            func.avg(NewsArticle.sentiment_score).label("avg_sentiment"),
            func.count(NewsArticle.id).label("total_articles"),
            func.sum(case((NewsArticle.sentiment_label == "positive", 1), else_=0)).label("pos_count"),
            func.sum(case((NewsArticle.sentiment_label == "negative", 1), else_=0)).label("neg_count"),
            func.sum(case((NewsArticle.sentiment_label == "neutral", 1), else_=0)).label("neu_count"),
        )
        .join(NewsArticleInstrument, NewsArticle.id == NewsArticleInstrument.article_id)
        .where(
            NewsArticleInstrument.instrument_id == instrument_id,
            NewsArticle.published_at >= cutoff,
        )
        .group_by(func.date(NewsArticle.published_at))
        .order_by(func.date(NewsArticle.published_at))
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "date": str(r.day),
            "avg_sentiment": round(float(r.avg_sentiment), 4) if r.avg_sentiment is not None else 0.0,
            "total_articles": int(r.total_articles),
            "positive": int(r.pos_count or 0),
            "negative": int(r.neg_count or 0),
            "neutral": int(r.neu_count or 0),
        }
        for r in rows
    ]


async def get_sentiment_price_overlay(
    session: AsyncSession,
    ticker: str,
    days: int = 60,
) -> dict[str, Any]:
    """Align daily closing prices with daily average sentiment for charting."""
    ticker_clean = ticker.upper().strip()
    inst_stmt = select(Instrument).where(Instrument.ticker == ticker_clean)
    instrument = (await session.execute(inst_stmt)).scalar_one_or_none()
    if not instrument:
        return {"ticker": ticker_clean, "points": [], "error": f"Instrument '{ticker_clean}' not found"}

    cutoff_date = (datetime.now(UTC) - timedelta(days=days)).date()

    # 1. Fetch prices
    price_stmt = (
        select(PriceBar)
        .where(PriceBar.instrument_id == instrument.id, PriceBar.ts >= cutoff_date)
        .order_by(PriceBar.ts)
    )
    bars = (await session.execute(price_stmt)).scalars().all()

    # 2. Fetch sentiment aggregates
    sent_items = await aggregate_ticker_sentiment(session, instrument.id, days=days)
    sent_by_date = {s["date"]: s for s in sent_items}

    # 3. Merge overlay
    points = []
    for b in bars:
        d_str = b.ts.strftime("%Y-%m-%d")
        s_data = sent_by_date.get(d_str)
        points.append({
            "date": d_str,
            "close": float(b.close),
            "volume": b.volume,
            "sentiment": s_data["avg_sentiment"] if s_data else None,
            "articles_count": s_data["total_articles"] if s_data else 0,
        })

    return {
        "ticker": ticker_clean,
        "instrument_name": instrument.name,
        "points": points,
    }
