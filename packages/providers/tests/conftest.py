from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_bytes() -> Callable[[str], bytes]:
    def load(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return load


@pytest.fixture
def fixture_text() -> Callable[[str], str]:
    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return load
