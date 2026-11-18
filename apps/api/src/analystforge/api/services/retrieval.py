"""Hybrid document retrieval combining semantic embeddings with lexical search (RAG)."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from typing import Any

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.models.news import NewsArticle, NewsArticleInstrument
from analystforge.api.models.rag import DocumentChunk
from analystforge.api.models.research import Filing, FundamentalFact

logger = structlog.get_logger("services.retrieval")

# Global model cache for sentence-transformers
_EMBEDDING_MODEL = None
_EMBEDDING_BACKEND = "lexical-fallback"


def get_embedding_backend() -> str:
    global _EMBEDDING_MODEL, _EMBEDDING_BACKEND
    if _EMBEDDING_MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            _EMBEDDING_BACKEND = "sentence-transformers"
        except Exception:
            _EMBEDDING_BACKEND = "lexical-fallback"
    return _EMBEDDING_BACKEND


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """Split text into overlapping semantic passages respecting sentence boundaries."""
    if not text or not text.strip():
        return []

    # Clean text
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= chunk_size:
        return [clean]

    # Split by sentence boundaries (.!? followed by space)
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for s in sentences:
        s_len = len(s)
        if current_len + s_len > chunk_size and current_chunk:
            chunk_str = " ".join(current_chunk)
            chunks.append(chunk_str)
            # Maintain overlap by keeping tail sentences
            overlap_len = 0
            new_chunk: list[str] = []
            for prev_s in reversed(current_chunk):
                if overlap_len + len(prev_s) <= overlap:
                    new_chunk.insert(0, prev_s)
                    overlap_len += len(prev_s)
                else:
                    break
            current_chunk = new_chunk
            current_len = overlap_len

        current_chunk.append(s)
        current_len += s_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


# ---------------------------------------------------------------------------
# Lexical & Semantic Vector Scoring
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"\b[a-zA-Z0-9_\.]+\b", text.lower()) if len(w) > 1]


def compute_bm25_lexical_scores(query: str, documents: list[str]) -> list[float]:
    """Compute BM25-style lexical relevance scores."""
    if not documents or not query.strip():
        return [0.0] * len(documents)

    q_tokens = tokenize(query)
    if not q_tokens:
        return [0.0] * len(documents)

    doc_tokens = [tokenize(d) for d in documents]
    doc_lens = [len(dt) for dt in doc_tokens]
    avg_dl = sum(doc_lens) / max(1, len(doc_lens))
    num_docs = len(documents)

    # Document frequencies
    df: Counter[str] = Counter()
    for dt in doc_tokens:
        df.update(set(dt))

    # BM25 parameters
    k1 = 1.5
    b = 0.75

    scores = []
    for dt, dl in zip(doc_tokens, doc_lens, strict=False):
        tf = Counter(dt)
        score = 0.0
        for q in q_tokens:
            if q in tf:
                doc_freq = df[q]
                idf = math.log(1.0 + (num_docs - doc_freq + 0.5) / (doc_freq + 0.5))
                term_tf = tf[q]
                norm_tf = (term_tf * (k1 + 1)) / (
                    term_tf + k1 * (1 - b + b * (dl / max(1.0, avg_dl)))
                )
                score += idf * norm_tf
        # Boost exact phrase match
        if query.lower() in " ".join(dt):
            score += 2.0
        scores.append(round(max(0.0, score), 4))

    return scores


def compute_semantic_scores(query: str, documents: list[str]) -> tuple[list[float], str]:
    """Compute semantic similarity scores using sentence-transformers or TF-IDF vector cosine fallback."""
    backend = get_embedding_backend()
    global _EMBEDDING_MODEL

    if backend == "sentence-transformers" and _EMBEDDING_MODEL is not None:
        try:
            import numpy as np

            q_emb = _EMBEDDING_MODEL.encode(query, convert_to_numpy=True)
            doc_embs = _EMBEDDING_MODEL.encode(documents, convert_to_numpy=True)
            # Cosine similarity
            q_norm = np.linalg.norm(q_emb)
            d_norms = np.linalg.norm(doc_embs, axis=1)
            dot_prods = np.dot(doc_embs, q_emb)
            sims = dot_prods / (d_norms * q_norm + 1e-9)
            return [round(float(s), 4) for s in sims], "sentence-transformers"
        except Exception as exc:
            logger.warning("sentence_transformers.inference_failed", error=str(exc))

    # Deterministic lexical vector fallback (TF-IDF cosine similarity)
    all_docs = [query, *documents]
    doc_tokens = [tokenize(d) for d in all_docs]
    vocab = sorted({w for dt in doc_tokens for w in dt})
    if not vocab:
        return [0.0] * len(documents), "lexical-fallback"

    vocab_idx = {w: i for i, w in enumerate(vocab)}
    df: Counter[str] = Counter()
    for dt in doc_tokens:
        df.update(set(dt))

    num_docs = len(all_docs)
    idf = {w: math.log((1.0 + num_docs) / (1.0 + df[w])) + 1.0 for w in vocab}

    # Vectors
    vectors = []
    for dt in doc_tokens:
        tf = Counter(dt)
        vec = [0.0] * len(vocab)
        for w, count in tf.items():
            if w in vocab_idx:
                vec[vocab_idx[w]] = (1.0 + math.log(count)) * idf[w]
        norm = math.sqrt(sum(v * v for v in vec))
        vectors.append([v / norm if norm > 0 else 0.0 for v in vec])

    q_vec = vectors[0]
    doc_vecs = vectors[1:]
    scores = []
    for d_vec in doc_vecs:
        sim = sum(q * d for q, d in zip(q_vec, d_vec, strict=False))
        scores.append(round(max(0.0, sim), 4))

    return scores, "lexical-fallback"


def hybrid_fuse_rankings(
    lexical_scores: list[float],
    semantic_scores: list[float],
    k: int = 60,
    weight_semantic: float = 0.6,
    weight_lexical: float = 0.4,
) -> list[float]:
    """Reciprocal Rank Fusion (RRF) of lexical and semantic rankings."""
    n = len(lexical_scores)
    # Sort indices by score descending
    lex_ranked = sorted(range(n), key=lambda i: lexical_scores[i], reverse=True)
    sem_ranked = sorted(range(n), key=lambda i: semantic_scores[i], reverse=True)

    lex_rank_map = {idx: rank + 1 for rank, idx in enumerate(lex_ranked)}
    sem_rank_map = {idx: rank + 1 for rank, idx in enumerate(sem_ranked)}

    fused_scores = []
    for i in range(n):
        rrf = (weight_lexical / (k + lex_rank_map[i])) + (weight_semantic / (k + sem_rank_map[i]))
        fused_scores.append(round(rrf, 6))

    return fused_scores


# ---------------------------------------------------------------------------
# Database Hybrid Retrieval
# ---------------------------------------------------------------------------


async def retrieve_relevant_passages(
    session: AsyncSession,
    query: str,
    instrument_id: uuid.UUID | None = None,
    limit: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    """Retrieve top relevant passages across DocumentChunk, Filing, FundamentalFact, and News."""
    passages: list[dict[str, Any]] = []

    # 1. First, search DocumentChunk table
    chunk_stmt = select(DocumentChunk)
    if instrument_id:
        chunk_stmt = chunk_stmt.where(DocumentChunk.instrument_id == instrument_id)
    chunk_stmt = chunk_stmt.order_by(desc(DocumentChunk.created_at)).limit(30)
    db_chunks = (await session.execute(chunk_stmt)).scalars().all()

    for c in db_chunks:
        passages.append(
            {
                "source_type": c.source_type,
                "source_id": c.source_id,
                "title": c.title,
                "section": c.section,
                "content": c.content,
                "snippet": c.content[:300] + ("..." if len(c.content) > 300 else ""),
                "chunk_index": c.chunk_index,
            }
        )

    # 2. If instrument specified and passages sparse, extract from Filing, Facts, and News
    if instrument_id and len(passages) < 5:
        # A. Filings
        filing_stmt = (
            select(Filing)
            .where(Filing.instrument_id == instrument_id)
            .order_by(desc(Filing.filed_date))
            .limit(3)
        )
        filings = (await session.execute(filing_stmt)).scalars().all()
        for f in filings:
            passages.append(
                {
                    "source_type": "FILING",
                    "source_id": f.accession,
                    "title": f"{f.form} Regulatory Filing (Accession {f.accession})",
                    "section": f"Filing Date {f.filed_date.isoformat()}",
                    "content": f"Filing {f.form} filed on {f.filed_date} for period {f.period_of_report}. Primary document: {f.primary_document}. Document URL: {f.document_url}.",
                    "snippet": f"SEC {f.form} filing for period {f.period_of_report} filed on {f.filed_date}.",
                    "chunk_index": 0,
                }
            )

        # B. Facts
        fact_stmt = (
            select(FundamentalFact)
            .where(FundamentalFact.instrument_id == instrument_id)
            .order_by(desc(FundamentalFact.period_end))
            .limit(10)
        )
        facts = (await session.execute(fact_stmt)).scalars().all()
        for fact in facts:
            passages.append(
                {
                    "source_type": "FACT",
                    "source_id": f"{fact.concept}_{fact.period_end}",
                    "title": f"XBRL Fact: {fact.concept}",
                    "section": f"Period Ending {fact.period_end}",
                    "content": f"XBRL concept {fact.concept} value {fact.value} {fact.unit} for period {fact.period_start} to {fact.period_end} (Form {fact.form}).",
                    "snippet": f"{fact.concept}: {fact.value} {fact.unit} (ending {fact.period_end})",
                    "chunk_index": 0,
                }
            )

        # C. News
        news_stmt = (
            select(NewsArticle)
            .join(NewsArticleInstrument, NewsArticle.id == NewsArticleInstrument.article_id)
            .where(NewsArticleInstrument.instrument_id == instrument_id)
            .order_by(desc(NewsArticle.published_at))
            .limit(5)
        )
        articles = (await session.execute(news_stmt)).scalars().all()
        for a in articles:
            passages.append(
                {
                    "source_type": "NEWS",
                    "source_id": str(a.id),
                    "title": a.title,
                    "section": "Market News",
                    "content": f"{a.title}. {a.summary or ''} {a.content or ''}".strip(),
                    "snippet": a.summary or a.title,
                    "chunk_index": 0,
                }
            )

    if not passages:
        return [], get_embedding_backend()

    # 3. Hybrid ranking over collected passages
    doc_texts = [p["content"] for p in passages]
    lex_scores = compute_bm25_lexical_scores(query, doc_texts)
    sem_scores, backend = compute_semantic_scores(query, doc_texts)
    fused_scores = hybrid_fuse_rankings(lex_scores, sem_scores)

    ranked_indices = sorted(range(len(passages)), key=lambda i: fused_scores[i], reverse=True)

    results = []
    for rank, idx in enumerate(ranked_indices[:limit]):
        item = dict(passages[idx])
        item["score"] = fused_scores[idx]
        item["lexical_score"] = lex_scores[idx]
        item["semantic_score"] = sem_scores[idx]
        item["rank"] = rank + 1
        item["backend"] = backend
        results.append(item)

    return results, backend
