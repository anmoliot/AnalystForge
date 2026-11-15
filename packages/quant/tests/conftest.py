"""Pytest fixtures for the quant suite.

The helper functions live in ``quant_fixtures`` so importing them never depends on
how pytest namespaces ``conftest`` modules across workspace packages.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from analystforge.quant.ratios import MarketData
from analystforge.quant.statements import FinancialStatements
from quant_fixtures import make_statements, reference_market


@dataclass(frozen=True)
class ReferenceCompany:
    current: FinancialStatements
    prior: FinancialStatements
    market: MarketData


@pytest.fixture(scope="session")
def reference() -> ReferenceCompany:
    return ReferenceCompany(
        current=make_statements(2024),
        prior=make_statements(2023),
        market=reference_market(),
    )
