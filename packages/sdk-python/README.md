# AnalystForge Python SDK (`analystforge-py`)

Official Python client for the AnalystForge financial analytics and research assistant platform.

## Installation

```bash
pip install analystforge-py
```

## Quickstart

```python
from analystforge_sdk.client import AnalystForgeClient

# Initialize client with API key or access token
with AnalystForgeClient(base_url="http://localhost:8000", api_key="af_live_secret") as client:
    # 1. Check system and integration health
    health = client.health()
    integrations = client.integrations_meta()
    print("Integrations:", integrations)

    # 2. Company financials and pricing
    company = client.get_company("AAPL")
    prices = client.get_prices("AAPL", start="2024-01-01", end="2024-12-31")

    # 3. Grounded AI Research with Citations
    research = client.query_research(
        query="What are Apple's primary revenue drivers and regulatory risks?", ticker="AAPL"
    )
    print("Answer:", research["answer"])
    for cite in research["citations"]:
        print(f"[{cite['citation_index']}] {cite['title']}: {cite['text']}")

    # 4. Multi-format Reporting & Downloads
    # Formats: PDF, PPTX, EXCEL, CSV, JSON, MARKDOWN
    report = client.generate_report(
        title="Apple Inc. Comprehensive Tearsheet",
        report_type="TEARSHEET",
        ticker="AAPL",
        format="PDF",
    )
    report_id = report["id"]

    # Download binary report stream (PDF)
    pdf_bytes = client.download_report(report_id, format="PDF")
    with open("AAPL_tearsheet.pdf", "wb") as f:
        f.write(pdf_bytes)

    # Download Excel with live dynamic formulas
    excel_bytes = client.download_report(report_id, format="EXCEL")
    with open("AAPL_model.xlsx", "wb") as f:
        f.write(excel_bytes)

    # Email report directly to analyst or stakeholder
    client.email_report(report_id, recipient_email="analyst@firm.com")
```

## Features

- **Typed & Ergonomic Client**: Full typing with connection pooling, retries, and clean exception hierarchies (`AnalystForgeError`).
- **Grounded AI Assistant**: Citations mapped to underlying filings, earnings calls, and news articles.
- **Institutional Reporting**: Native ReportLab PDF, widescreen PowerPoint (python-pptx), and Excel spreadsheets with live dynamic recalculating formulas.
- **Sandboxed Backtesting & Quant Valuation**: DCF, DDM, FCFE, SOTP, Precedent Transactions, and factor regressions.
