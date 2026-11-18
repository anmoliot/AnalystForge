"""Optional model loading must follow configuration and retain explicit fallback behaviour."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from analystforge.api.services import news_analytics


def test_disabled_finbert_never_loads_optional_model(monkeypatch):
    loader = Mock(side_effect=AssertionError("Disabled model must never load"))
    monkeypatch.setattr(news_analytics, "_finbert_pipeline", loader)
    result = news_analytics.analyze_sentiment("Revenue and profits increased.")
    assert result["backend"] == "lexical-fallback"
    loader.assert_not_called()


@pytest.mark.parametrize("nested", [False, True])
def test_enabled_model_is_configurable_cached_and_token_truncated(monkeypatch, nested):
    scores = [
        {"label": "positive", "score": 0.9},
        {"label": "neutral", "score": 0.08},
        {"label": "negative", "score": 0.02},
    ]
    classify = Mock(return_value=[scores] if nested else scores)
    factory = Mock(return_value=classify)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(pipeline=factory))
    news_analytics._finbert_pipeline.cache_clear()
    try:
        text = "Revenue and profits increased. " * 100
        for _ in range(2):
            result = news_analytics.analyze_sentiment(
                text, finbert_enabled=True, finbert_model="configured-model"
            )
            assert result["backend"] == "finbert"
            assert result["score"] == pytest.approx(0.88)
        factory.assert_called_once_with(
            "sentiment-analysis", model="configured-model", top_k=None, device=-1
        )
        classify.assert_called_with(text, truncation=True, max_length=512)
    finally:
        news_analytics._finbert_pipeline.cache_clear()


def test_enabled_model_failure_reports_lexical_fallback(monkeypatch, caplog):
    monkeypatch.setattr(news_analytics, "_finbert_pipeline", Mock(side_effect=OSError()))
    result = news_analytics.analyze_sentiment(
        "Revenue and profits increased.", finbert_enabled=True
    )
    assert result["backend"] == "lexical-fallback"
    assert "FinBERT unavailable (OSError)" in caplog.text
