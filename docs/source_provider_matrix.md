---
title: source_provider_matrix
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Provider Matrix

### Purpose

<details open>
<summary>Current source candidates for source-first market-data infrastructure.</summary>

---

This matrix records candidate sources for the Autonomous Trading Agent MVP. It is a planning document, not a verification record. Do not claim a source is usable until access, auth, terms, raw response shape, and sample capture are verified in a source probe.

---

#### Provider table

| Source | Source role | Data categories | Access method | Auth required | Likely fields | MVP priority | Crawl difficulty | Legal/terms risk | Blocks MVP? | Current repo status | Next action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HSX/HOSE official website/data surfaces | Official exchange reference and first source to inspect for symbol/exchange/trading data. | Symbol list, listed securities, market data pages, trading stats, issuer/event information if exposed. | Public page, manual download, official file/API unknown. | Unknown. | Symbol, exchange, security type, company name, trade date, OHLCV-like fields if exposed, event/disclosure fields if exposed. | P0 probe. | Medium to high until surfaces are mapped. | Medium; must respect website terms, robots rules, and download limits. | Blocks MVP only if it is selected as primary OHLCV and access is verified. | Existing docs mention HSX/HOSE; no source adapter yet. | Probe official surfaces and capture raw samples before schema decisions. |
| SSI FastConnect Data | Candidate vendor API for production-grade market data. | Securities, securities details, daily OHLC, intraday OHLC, daily index, daily stock price, possibly streaming data. | Paid API or vendor API; websocket possible for streaming. | Yes or unknown until credentials/config are verified. | Candidate APIs: `Securities`, `SecuritiesDetails`, `DailyOhlc`, `IntradayOhlc`, `DailyIndex`, `DailyStockPrice`, streaming ticks/quotes if provided. | P0/P1 probe. | Medium if docs/credentials exist; high without them. | Low to medium if licensed; high if used without confirmed access terms. | Blocks MVP only after verified access and chosen as primary OHLCV. | No adapter yet. | Add config-driven probe that fails cleanly when credentials are absent. |
| Vietcap IQ / Vietcap Research | Reports/evidence and company research context; not primary OHLCV. | Research reports, company notes, recommendations, narrative evidence, possibly company metadata. | Paid portal/API/manual download unknown. | Yes/unknown. | Report title, symbol, analyst/source, publish date, content, URL/file path, tags, company metadata. | P2. | Medium to high due auth/manual workflow. | Medium to high; respect report licensing and redistribution limits. | No for first OHLCV MVP. | Existing data-source docs only. | Probe access mode and document whether reports can be stored locally. |
| FiinGroup Datafeed | Candidate vendor feed for richer market data and adjusted pricing. | EOD price, foreign trading, adjusted price, corporate actions, market depth if provided. | Paid API/datafeed unknown. | Yes/unknown. | Candidate HOSE Stock V2-style fields: EOD price, adjusted price, foreign trading, bid/ask depth if provided, symbol, exchange, trade date, volume, value. | P1 probe. | Medium with docs/credentials; high without them. | Low to medium if licensed; high if unverified. | Blocks MVP only after verified access and chosen as primary source. | No adapter yet. | Probe only with explicit credentials/config; record available fields. |
| VBMA | Vietnam bond/rates context, not equity OHLCV. | Bond yields, rates, market summaries, fixed-income context. | Public page, manual download, API unknown. | Unknown. | Date, tenor, yield/rate, bond market indicator, publication timestamp if exposed. | P2/P3. | Medium. | Medium; verify terms for scraping/downloads. | No. | Existing docs mark as macro/rates context. | Probe later after equity source path is stable. |
| FRED API | Global macro context, not Vietnam equity OHLCV. | Macro series, rates, inflation, global indicators. | Official API. | Usually API key for normal use; exact config must be verified locally. | Series ID, observation date, value, realtime start/end, release metadata when available. | P2/P3. | Low. | Low if API terms followed. | No. | Existing docs mark as optional macro context. | Add later macro adapter with point-in-time release checks. |
| `vnstock` | Prototype/fallback/reference adapter only. | Symbol listing, exchange mapping, OHLCV, corporate events, company metadata depending on library/version. | Python wrapper library. | No direct provider auth in current prototype. | Library-shaped columns such as symbol, exchange, time, open, high, low, close, volume, event fields. | Prototype only. | Low for demo, but low transparency. | Medium; wrapper hides source/provider provenance and terms may depend on underlying data. | No. | Prototype ingestion exists and produced raw/silver/report outputs. | Keep for fallback and normalizer tests; do not use as canonical MVP source. |

---

#### Current decision

- Source-first crawling/fetching is canonical.
- `vnstock` remains useful for prototypes and regression tests, but does not define the MVP data infrastructure.
- FRED and VBMA are macro/rates context and do not block the first equity OHLCV pipeline.
- Vietcap is report/evidence context and does not block the first equity OHLCV pipeline.

---

</details>
