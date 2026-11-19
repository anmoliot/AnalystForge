# User guide

The recorded reviewer walkthrough in README.md starts an isolated API and browser test without
provider credentials. For an interactive workspace start the API on port 8000 and Vite on 5173,
configure PostgreSQL and follow RUNBOOK.md. The current migration gaps require attention before
setting up a fresh database for the complete product.

1. Register and sign in through Access. Self-service registration needs deployment restrictions
   described in SECURITY.md. The current role model is incomplete.
2. Open Companies and search a provider-native symbol such as AAPL or RELIANCE.NS.
   Price charts, statements and ratios reflect persisted observations. Check dates, units and
   missing-data notices. NSE and BSE listings are separate instruments, with INR currency.
3. Open Valuation and enter sourced revenue, shares and net debt. Forecast rates are editable
   analyst assumptions. Recalculate to inspect projected cash flows, sensitivities and seeded
   Monte Carlo output. Advanced methods accept JSON parameters matching the API schema.
4. Create a portfolio and record actual transactions or import a file. Inspect holdings, risk
   and transaction validation errors. Insufficient prices produce unavailable risk output.
5. Use Backtest Lab for a built-in strategy or rule group. Review costs, lag, drawdown and
   survivorship warnings. Custom Python strategies require Linux with libseccomp. They compute on
   the supplied data in memory. File access, networking and imports requiring new files are blocked.
6. Run a screen and review the as-of dates. Save a screen or create alerts only after checking
   available inputs and delivery configuration. Missing market cap/ratios remain empty.
7. Ask Research a question grounded in filings/news. Inspect citations and explicit refusals.
   A configured LLM is required for live generated answers. Lexical retrieval/fallback status
   depends on available packages and settings.
8. Generate a report and download its selected format. Current reports include recorded close
   metrics and unavailable-data statements. Complete domain-specific report assembly remains
   pending. Financial Model Excel cells await your sourced inputs.

Use the theme toggle for dark/light display. Settings shows signed-in profile data. Key and TOTP
management is available through the authenticated API. Team/audit browsing is currently unavailable
in the admin interface. Quote the response request ID when reporting an error.

## Indian listings

The seed includes RELIANCE.NS, TCS.NS, RELIANCE.BO and TCS.BO. Only Yahoo mappings are configured
for these listings. Live adapter reads were verified on 2026-11-18. Persisted application prices
still depend on a successful ingestion into your configured database.
SEC fundamentals do not cover these domestic listings through the current adapter.

Exchange filings confirm the issuer symbols and scrip identifiers. Provider pages confirm the
Yahoo suffix mappings. [Reliance filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_GOVERNANCE_154239_29042026175716_iXBRL_WEB.html), [TCS filing](https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_200120_08102026220751_iXBRL_WEB.html), [Reliance NSE](https://finance.yahoo.com/quote/RELIANCE.NS/history/), [Reliance BSE](https://finance.yahoo.com/quote/RELIANCE.BO/), [TCS NSE](https://sg.finance.yahoo.com/quote/TCS.NS/history/), [TCS BSE](https://sg.finance.yahoo.com/quote/TCS.BO/history/).
