"""Load real optional FinBERT weights through the application and verify inference."""

import argparse
import json
import math
from importlib.metadata import version

from analystforge.api.services.news_analytics import analyze_sentiment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", default="ProsusAI/finbert", help="Model ID or verified local snapshot"
    )
    args = parser.parse_args()
    result = analyze_sentiment(
        "The company reported a significant increase in revenue and profits.",
        finbert_enabled=True,
        finbert_model=args.model,
    )
    if result["backend"] != "finbert":
        raise RuntimeError("Real FinBERT inference did not run. The application used its fallback.")
    probabilities = result["probabilities"]
    if set(probabilities) != {"positive", "negative", "neutral"}:
        raise RuntimeError("FinBERT did not return all three sentiment classes.")
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities.values()):
        raise RuntimeError("FinBERT returned invalid probabilities.")
    if abs(sum(probabilities.values()) - 1) > 0.001:
        raise RuntimeError("FinBERT probabilities do not sum to one.")
    print(
        json.dumps(
            {
                "status": "passed",
                "backend": result["backend"],
                "transformers": version("transformers"),
                "torch": version("torch"),
                "label": result["label"],
                "probabilities": probabilities,
            }
        )
    )


if __name__ == "__main__":
    main()
