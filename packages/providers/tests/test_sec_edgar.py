"""SEC EDGAR companyfacts/submissions parsing against recorded payloads."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import httpx
import pytest
import respx

from analystforge.providers.errors import ProviderDataError, ProviderNotConfiguredError
from analystforge.providers.fundamentals.sec_edgar import (
    SecEdgarProvider,
    _normalize_cik,
    _parse_fact,
    _parse_filings,
)

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK0000320193.json"


def _provider() -> SecEdgarProvider:
    return SecEdgarProvider(user_agent="AnalystForge tests contact@example.com")


async def test_parses_company_facts_and_filings(
    fixture_bytes: Callable[[str], bytes],
) -> None:
    provider = _provider()
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_FACTS_URL).mock(
                return_value=httpx.Response(
                    200, content=fixture_bytes("sec_companyfacts_aapl.json")
                )
            )
            mock.get(_SUBMISSIONS_URL).mock(
                return_value=httpx.Response(200, content=fixture_bytes("sec_submissions_aapl.json"))
            )
            company = await provider.fetch_company("320193")
    finally:
        await provider.aclose()

    assert company.cik == "0000320193"
    assert company.entity_name == "Apple Inc."
    assert len(company.facts) == 18
    assert len(company.filings) == 8
    assets = [fact for fact in company.facts if fact.concept == "Assets"]
    assert assets
    assert all(fact.unit == "USD" for fact in assets)
    assert all(fact.value > 0 for fact in assets)
    latest = company.filings[0]
    assert latest.form == "4"
    assert latest.filed == date(2026, 11, 12)
    assert latest.document_url.startswith(
        "https://www.sec.gov/Archives/edgar/data/320193/000114036126043484/"
    )
    ten_k = next(filing for filing in company.filings if filing.form == "10-K")
    assert ten_k.period_of_report == date(2026, 9, 26)
    assert ten_k.primary_document == "aapl-20260926.htm"


def test_cik_normalization() -> None:
    assert _normalize_cik("320193") == "0000320193"
    assert _normalize_cik("CIK0000320193") == "0000320193"
    assert _normalize_cik(" 320193 ") == "0000320193"
    assert _normalize_cik("not-a-cik") == ""


async def test_non_numeric_cik_is_rejected() -> None:
    provider = _provider()
    try:
        with pytest.raises(ProviderNotConfiguredError, match="numeric CIK"):
            await provider.fetch_company("Apple")
    finally:
        await provider.aclose()


def test_empty_user_agent_is_not_configured() -> None:
    assert _provider().is_configured() is True
    assert SecEdgarProvider(user_agent="   ").is_configured() is False


def test_boolean_values_are_not_facts() -> None:
    entry = {"val": True, "end": "2024-09-28", "filed": "2024-11-01", "accn": "1", "form": "10-K"}
    assert _parse_fact("dei", "Flag", "boolean", entry) is None


def test_missing_required_fields_are_skipped() -> None:
    assert _parse_fact("us-gaap", "Thing", "USD", {"val": 1}) is None


def test_long_taxonomy_concepts_are_preserved() -> None:
    concept = (
        "ShareBasedCompensationArrangementByShareBasedPaymentAwardAwardVestingRightsPercentage" * 2
    )
    entry = {
        "val": "12.5",
        "end": "2024-09-28",
        "start": "2023-09-30",
        "filed": "2024-11-01",
        "accn": "0000320193-24-000123",
        "form": "10-K",
        "fy": 2024,
        "fp": "FY",
        "frame": "CY2024",
    }
    fact = _parse_fact("us-gaap", concept, "pure", entry)
    assert fact is not None
    assert fact.concept == concept
    assert len(fact.concept) > 100
    assert fact.value == Decimal("12.5")


def test_filings_require_documents_and_accessions() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["10-K", "8-K"],
                "accessionNumber": ["0000320193-24-000123", ""],
                "filingDate": ["2024-11-01", "2024-10-01"],
                "reportDate": ["2024-09-28", "2024-09-30"],
                "primaryDocument": ["aapl.htm", "other.htm"],
            }
        }
    }
    filings = _parse_filings(payload, "0000320193")
    assert len(filings) == 1
    assert filings[0].accession == "0000320193-24-000123"


async def test_empty_company_is_a_data_error() -> None:
    provider = _provider()
    try:
        with respx.mock(assert_all_called=True) as mock:
            mock.get(_FACTS_URL).mock(
                return_value=httpx.Response(200, json={"entityName": "Empty", "facts": {}})
            )
            mock.get(_SUBMISSIONS_URL).mock(
                return_value=httpx.Response(200, json={"name": "Empty", "filings": {"recent": {}}})
            )
            with pytest.raises(ProviderDataError, match="no XBRL facts"):
                await provider.fetch_company("0000320193")
    finally:
        await provider.aclose()
