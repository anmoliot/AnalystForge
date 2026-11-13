# Data licensing and attribution

AnalystForge stores and displays data from third-party providers. The deployment operator is
responsible for complying with each provider's terms. This file is a starting point, not legal
advice.

| Source | Access | Key | Terms / notes |
|---|---|---|---|
| SEC EDGAR (XBRL company facts, submissions, filings) | Public | None; descriptive `User-Agent` required | US government public data. Respect SEC fair-access limits (≤10 requests/s, declared User-Agent). |
| FRED (St. Louis Fed) | Public | Optional API key | Series may be sourced from third parties; check individual series notes. Attribution to FRED required. |
| ECB Data Portal | Public | None | Attribution required. |
| World Bank Open Data | Public | None | CC BY 4.0 generally; check indicator metadata. |
| Stooq | Public CSV endpoints | None | Best-effort, unofficial. Currently serves a browser challenge to non-browser clients, so live fallback is blocked on the verification host. Commercial use requires checking Stooq terms. |
| Yahoo Finance chart API | Public | None | Unofficial and best-effort; Yahoo terms restrict redistribution/commercial use. Used as the keyless development default; production deployment requires a terms review. Quotes may be delayed. |
| Alpha Vantage | API | Yes | Free tier limits; redistribution restrictions apply. |
| Twelve Data | API | Yes | Plan-dependent licensing. |
| Polygon.io | API | Yes | Paid plan; exchange licensing may restrict display/redistribution. |
| Financial Modeling Prep | API | Yes | Plan-dependent. |
| GDELT | Public | None | CC BY 4.0 for GDELT datasets; check current terms. |
| NewsAPI | API | Yes | Free tier is development-only; production requires a paid plan. |
| RSS feeds / company IR pages | Public | None | Article text remains the publisher's copyright. Store for internal research; do not redistribute full text. |
| CoinGecko | API | Optional key | Attribution required; rate limits apply. |
| Ken French Data Library | Public | None | Fama-French factors; cite the source. |
| exchangerate.host / ECB FX | Public | Optional | Check terms; ECB reference rates are informational. Phase 1 defaults to ECB reference rates. |

## Storage and redistribution

- Raw provider payloads are retained for audit and reproducibility. Retention should be reviewed
  against each provider's terms before enabling multi-tenant redistribution.
- Full article text is stored for internal retrieval and citation; the UI links to the original
  source and shows only the passages needed for the analyst's question.
- Exports and shared links include source attribution and the data's as-of timestamp.

## Demo data

Any bundled demo dataset is synthetic, clearly labelled `DEMO`, disabled by default and blocked in
production. It is never mixed with live provider data.
