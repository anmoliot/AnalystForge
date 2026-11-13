"""SEC EDGAR XBRL adapter.

Uses the public companyfacts and submissions JSON endpoints. SEC fair-access
rules require a descriptive User-Agent with a contact address and limit clients
to roughly ten requests per second; this adapter paces at about six per second
and caches responses for a day.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from analystforge.providers.base import FundamentalsProvider
from analystforge.providers.cache import ResponseCache
from analystforge.providers.errors import ProviderDataError, ProviderNotConfiguredError
from analystforge.providers.http import ProviderHttpClient
from analystforge.providers.models import CompanyFacts, Filing, FundamentalFact

_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
_CACHE_TTL_SECONDS = 24 * 3600.0
_MAX_FILINGS = 40


class SecEdgarProvider(FundamentalsProvider):
    name = "sec_edgar"

    def __init__(
        self,
        *,
        user_agent: str,
        cache: ResponseCache | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._user_agent = user_agent.strip()
        self._client = ProviderHttpClient(
            self.name,
            user_agent=self._user_agent,
            cache=cache,
            timeout_seconds=timeout_seconds,
            max_attempts=3,
            min_interval_seconds=0.16,
        )

    def is_configured(self) -> bool:
        return bool(self._user_agent)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_company(self, cik: str) -> CompanyFacts:
        normalized = _normalize_cik(cik)
        if not normalized:
            raise ProviderNotConfiguredError(self.name, "a numeric CIK is required")
        facts_payload = await self._client.get_json(
            _FACTS_URL.format(cik=normalized), ttl_seconds=_CACHE_TTL_SECONDS
        )
        submissions_payload = await self._client.get_json(
            _SUBMISSIONS_URL.format(cik=normalized), ttl_seconds=_CACHE_TTL_SECONDS
        )
        entity_name = str(facts_payload.get("entityName") or submissions_payload.get("name") or "")
        facts = _parse_facts(facts_payload)
        if not facts:
            raise ProviderDataError(self.name, f"no XBRL facts for CIK {normalized}")
        filings = _parse_filings(submissions_payload, normalized)
        return CompanyFacts(cik=normalized, entity_name=entity_name, facts=facts, filings=filings)


def _normalize_cik(cik: str) -> str:
    digits = "".join(character for character in str(cik) if character.isdigit())
    if not digits:
        return ""
    return digits.zfill(10)


def _parse_facts(payload: Any) -> list[FundamentalFact]:
    if not isinstance(payload, dict):
        raise ProviderDataError("sec_edgar", "companyfacts response is not an object")
    facts_by_key: dict[tuple[str, str, str, date, date, str], FundamentalFact] = {}
    for taxonomy, concepts in (payload.get("facts") or {}).items():
        if not isinstance(concepts, dict):
            continue
        for concept, body in concepts.items():
            if not isinstance(body, dict):
                continue
            for unit, entries in (body.get("units") or {}).items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    fact = _parse_fact(str(taxonomy), str(concept), str(unit), entry)
                    if fact is None:
                        continue
                    key = (
                        fact.taxonomy,
                        fact.concept,
                        fact.unit,
                        fact.period_start,
                        fact.period_end,
                        fact.accession,
                    )
                    facts_by_key[key] = fact
    facts = list(facts_by_key.values())
    facts.sort(key=lambda fact: (fact.period_end, fact.concept, fact.accession))
    return facts


def _parse_fact(taxonomy: str, concept: str, unit: str, entry: Any) -> FundamentalFact | None:
    if not isinstance(entry, dict):
        return None
    try:
        raw_value = entry["val"]
        if isinstance(raw_value, bool):
            return None
        value = Decimal(str(raw_value))
        if not value.is_finite():
            return None
        period_end = date.fromisoformat(str(entry["end"]))
        period_start = date.fromisoformat(str(entry["start"])) if entry.get("start") else period_end
        filed = date.fromisoformat(str(entry["filed"]))
        accession = str(entry["accn"]).strip()
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if not accession:
        return None
    fiscal_year: int | None
    try:
        fiscal_year = int(entry["fy"]) if entry.get("fy") is not None else None
    except (TypeError, ValueError):
        fiscal_year = None
    fiscal_period = str(entry["fp"]) if entry.get("fp") is not None else None
    frame = str(entry["frame"]) if entry.get("frame") is not None else None
    form = str(entry.get("form") or "").strip()
    if not form or period_start > period_end:
        return None
    return FundamentalFact(
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        value=value,
        period_start=period_start,
        period_end=period_end,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form=form,
        filed=filed,
        frame=frame,
        accession=accession,
    )


def _parse_filings(payload: Any, cik: str) -> list[Filing]:
    if not isinstance(payload, dict):
        return []
    recent = (payload.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    filed_dates = recent.get("filingDate") or []
    report_dates = recent.get("reportDate") or []
    documents = recent.get("primaryDocument") or []
    filings: list[Filing] = []
    seen: set[str] = set()
    for index in range(min(len(forms), len(accessions), len(filed_dates), len(documents))):
        accession = str(accessions[index]).strip()
        if not accession or accession in seen:
            continue
        try:
            filed = date.fromisoformat(str(filed_dates[index]))
        except ValueError:
            continue
        report_raw = report_dates[index] if index < len(report_dates) else ""
        try:
            period = date.fromisoformat(str(report_raw)) if report_raw else None
        except ValueError:
            period = None
        document = str(documents[index] or "").strip()
        accession_nodash = accession.replace("-", "")
        filings.append(
            Filing(
                accession=accession,
                form=str(forms[index] or "").strip(),
                filed=filed,
                period_of_report=period,
                primary_document=document,
                document_url=_ARCHIVE_URL.format(
                    cik=cik.lstrip("0") or "0",
                    accession=accession_nodash,
                    document=document,
                ),
            )
        )
        seen.add(accession)
        if len(filings) >= _MAX_FILINGS:
            break
    filings.sort(key=lambda filing: filing.filed, reverse=True)
    return filings
