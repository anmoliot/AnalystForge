"""SEC Filing section navigation, period-over-period section diffing, and key metric extraction."""

from __future__ import annotations

import difflib
import re
from decimal import Decimal
from typing import Any

from analystforge.api.models.research import FundamentalFact

# Standard SEC 10-K / 10-Q Item regex patterns
SECTION_PATTERNS = [
    ("item_1", "Item 1", "Business", re.compile(r"(?:ITEM\s+1\b[\.\:\s\-]+(?:BUSINESS|DESCRIPTION\s+OF\s+BUSINESS))", re.IGNORECASE)),
    ("item_1a", "Item 1A", "Risk Factors", re.compile(r"(?:ITEM\s+1A\b[\.\:\s\-]+RISK\s+FACTORS)", re.IGNORECASE)),
    ("item_1b", "Item 1B", "Unresolved Staff Comments", re.compile(r"(?:ITEM\s+1B\b[\.\:\s\-]+UNRESOLVED\s+STAFF\s+COMMENTS)", re.IGNORECASE)),
    ("item_2", "Item 2", "Properties", re.compile(r"(?:ITEM\s+2\b[\.\:\s\-]+PROPERTIES)", re.IGNORECASE)),
    ("item_3", "Item 3", "Legal Proceedings", re.compile(r"(?:ITEM\s+3\b[\.\:\s\-]+LEGAL\s+PROCEEDINGS)", re.IGNORECASE)),
    ("item_7", "Item 7", "Management's Discussion and Analysis (MD&A)", re.compile(r"(?:ITEM\s+7\b[\.\:\s\-]+MANAGEMENT(?:\'S|\s+S)?\s+DISCUSSION\s+AND\s+ANALYSIS)", re.IGNORECASE)),
    ("item_7a", "Item 7A", "Quantitative and Qualitative Disclosures About Market Risk", re.compile(r"(?:ITEM\s+7A\b[\.\:\s\-]+QUANTITATIVE\s+AND\s+QUALITATIVE\s+DISCLOSURES)", re.IGNORECASE)),
    ("item_8", "Item 8", "Financial Statements and Supplementary Data", re.compile(r"(?:ITEM\s+8\b[\.\:\s\-]+FINANCIAL\s+STATEMENTS)", re.IGNORECASE)),
]

RISK_KEYWORDS = [
    "artificial intelligence", "generative ai", "tariffs", "trade restrictions",
    "supply chain", "geopolitical", "inflation", "interest rates", "liquidity",
    "cybersecurity", "data privacy", "sanctions", "climate change", "competition",
    "antitrust", "regulatory scrutiny", "foreign exchange", "credit risk",
]


def clean_filing_text(text: str) -> str:
    """Normalize whitespace and strip HTML markup from SEC filings."""
    if "<" in text and ">" in text:
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
    # Normalize unicode spaces & linebreaks
    text = re.sub(r"[\r\t\f\v ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_filing_sections(text: str, form: str = "10-K") -> dict[str, Any]:
    """Parse a 10-K or 10-Q filing into its standard Item sections."""
    cleaned = clean_filing_text(text)
    matches: list[tuple[int, str, str, str]] = []

    for key, item_no, title, pattern in SECTION_PATTERNS:
        for m in pattern.finditer(cleaned):
            matches.append((m.start(), key, item_no, title))

    # Sort matches by position in document
    matches.sort(key=lambda x: x[0])

    # De-duplicate table of contents mentions (often at first 10% of doc)
    # Keep the latter occurrences if multiple matches occur
    filtered_matches: list[tuple[int, str, str, str]] = []
    seen_keys: set[str] = set()
    for pos, key, item_no, title in reversed(matches):
        if key not in seen_keys:
            seen_keys.add(key)
            filtered_matches.append((pos, key, item_no, title))
    filtered_matches.sort(key=lambda x: x[0])

    sections: dict[str, Any] = {}
    total_len = len(cleaned)

    for i, (pos, key, item_no, title) in enumerate(filtered_matches):
        end_pos = filtered_matches[i + 1][0] if i + 1 < len(filtered_matches) else total_len
        content = cleaned[pos:end_pos].strip()
        sections[key] = {
            "key": key,
            "item": item_no,
            "title": title,
            "start_char": pos,
            "end_char": end_pos,
            "char_count": len(content),
            "snippet": content[:300] + ("..." if len(content) > 300 else ""),
            "content": content,
        }

    # If no standard items could be segmented, return the full document under general section
    if not sections:
        sections["full_document"] = {
            "key": "full_document",
            "item": form,
            "title": f"{form} Full Text",
            "start_char": 0,
            "end_char": total_len,
            "char_count": total_len,
            "snippet": cleaned[:300] + ("..." if total_len > 300 else ""),
            "content": cleaned,
        }

    return {
        "form": form,
        "total_characters": total_len,
        "sections_found": list(sections.keys()),
        "sections": sections,
    }


def diff_filing_sections(prior_text: str, current_text: str) -> dict[str, Any]:
    """Calculate period-over-period diff for Risk Factors or MD&A sections."""
    norm_prior = clean_filing_text(prior_text)
    norm_current = clean_filing_text(current_text)

    # Compute similarity ratio
    matcher = difflib.SequenceMatcher(None, norm_prior, norm_current)
    similarity = matcher.ratio()

    # Split into paragraphs
    p_prior = [p.strip() for p in norm_prior.split("\n\n") if len(p.strip()) > 30]
    p_current = [p.strip() for p in norm_current.split("\n\n") if len(p.strip()) > 30]

    set_prior = set(p_prior)
    set_current = set(p_current)

    added_paragraphs = [p for p in p_current if p not in set_prior]
    removed_paragraphs = [p for p in p_prior if p not in set_current]

    # Detect emerging risk keywords in added paragraphs
    added_text = " ".join(added_paragraphs).lower()
    prior_text_lower = norm_prior.lower()
    emerging_risks = []
    for kw in RISK_KEYWORDS:
        if kw in added_text and kw not in prior_text_lower:
            emerging_risks.append(kw)

    return {
        "similarity_ratio": round(similarity, 4),
        "prior_paragraph_count": len(p_prior),
        "current_paragraph_count": len(p_current),
        "added_paragraph_count": len(added_paragraphs),
        "removed_paragraph_count": len(removed_paragraphs),
        "emerging_risk_factors": emerging_risks,
        "added_highlights": added_paragraphs[:5],
        "removed_highlights": removed_paragraphs[:5],
    }


def extract_key_metrics(facts: list[FundamentalFact]) -> list[dict[str, Any]]:
    """Extract and structure key comparative metrics across reporting periods from XBRL facts."""
    if not facts:
        return []

    # Filter to annual/quarterly facts of interest
    target_concepts = {
        "Revenues": "Revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax": "Revenue",
        "SalesRevenueNet": "Revenue",
        "GrossProfit": "Gross Profit",
        "OperatingIncomeLoss": "Operating Income",
        "NetIncomeLoss": "Net Income",
        "EarningsPerShareDiluted": "Diluted EPS",
        "NetCashProvidedByUsedInOperatingActivities": "Operating Cash Flow",
        "PaymentsToAcquirePropertyPlantAndEquipment": "CapEx",
    }

    # Group by period_end date
    by_period: dict[str, dict[str, Any]] = {}
    for f in facts:
        if f.concept in target_concepts:
            metric_name = target_concepts[f.concept]
            period_str = f.period_end.isoformat()
            if period_str not in by_period:
                by_period[period_str] = {
                    "period_end": period_str,
                    "fiscal_year": f.fiscal_year,
                    "fiscal_period": f.fiscal_period,
                    "form": f.form,
                    "metrics": {},
                }
            # Keep fact if not yet recorded or if higher precision
            if metric_name not in by_period[period_str]["metrics"]:
                by_period[period_str]["metrics"][metric_name] = float(f.value)

    # Sort periods chronologically
    sorted_periods = sorted(by_period.values(), key=lambda p: p["period_end"])

    # Compute YoY changes where consecutive periods exist
    for i, curr in enumerate(sorted_periods):
        curr["yoy_growth"] = {}
        if i > 0:
            prev = sorted_periods[i - 1]
            for m_name, curr_val in curr["metrics"].items():
                if m_name in prev["metrics"]:
                    prev_val = prev["metrics"][m_name]
                    if prev_val != 0:
                        pct = (curr_val - prev_val) / abs(prev_val) * 100.0
                        curr["yoy_growth"][m_name] = round(pct, 2)

    return sorted_periods
