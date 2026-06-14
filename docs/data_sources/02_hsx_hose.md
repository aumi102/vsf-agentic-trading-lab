---
title: 02_hsx_hose
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot
<details open>
<summary>HSX/HOSE is a core official source for Vietnamese exchange market data and listed-company context.</summary>
---
#### Source role

- **source** = Ho Chi Minh Stock Exchange, often written as HOSE or HSX.
- **purpose** = collect exchange-level trading data, listed securities, trading summaries, event calendars, and official information products.
- **agent usage** = Data Agent, TA Agent, Backtest Agent, Risk Agent, and Schema Agent.
- **official fact** = HOSE end-of-day information products include fields such as ticker, open, close, high, low, trading volume, trading value, percent change, and next-session reference price.
- **MVP stance** = use HOSE-style daily OHLCV fields as the canonical market-data schema for VN stocks.

---
#### Access surface

- **Access:** official website, downloadable tables, paid information services, and public pages where available.
- **Build it:** start with manual download or stable table scraping; upgrade only after access rules are clear.
- **Your own code:** parser code can normalize Vietnamese headers, units, ticker, dates, prices, and volumes.

---
</details>

### Data Categories
<details open>
<summary>HOSE-like data supports TA, backtesting, liquidity checks, and trading calendar validation.</summary>
---
#### Categories

| Category | Example | Agent use |
|---|---|---|
| daily trading data | open, high, low, close, volume, value | TA and backtest input. |
| market summary | total market volume and value | market regime and breadth context. |
| listed securities | ticker, company, exchange, security type | symbol master. |
| corporate events | listing, delisting, dividends, splits if available | adjustment and point-in-time checks. |
| trading calendar | trading days and holidays | missing-date validation. |
| index data | VN-Index and VN30 values | benchmark and regime analysis. |

---
#### Important fields

- `security_id` = internal stable instrument ID.
- `ticker` = exchange ticker such as `FPT`.
- `exchange` = `HOSE`.
- `trade_date` = official trading date.
- `open`, `high`, `low`, `close` = price fields with unit recorded.
- `volume` = number of shares or source-specific unit.
- `value` = traded value with currency and unit.
- `reference_price_next` = next-session reference price when provided.
- `source_id` = source batch or file.

---
</details>

### Proposed Schema
<details open>
<summary>Daily prices should be separated from symbol identity and source files.</summary>
---
#### Tables

| Table | Fields | Notes |
|---|---|---|
| `exchanges` | `exchange_id`, `name`, `country`, `timezone` | `HOSE` uses Vietnam market context. |
| `securities` | `security_id`, `ticker`, `company_id`, `exchange_id`, `security_type` | stable instrument identity. |
| `daily_prices` | `security_id`, `trade_date`, `open`, `high`, `low`, `close`, `volume`, `value`, `source_id` | one row per security per date. |
| `trading_calendar` | `exchange_id`, `date`, `is_trading_day`, `holiday_name` | missing-date checks. |
| `market_summaries` | `exchange_id`, `trade_date`, `total_volume`, `total_value`, `advancers`, `decliners` | breadth and regime. |

---
#### Worked example

- **row** = `FPT`, `2025-01-10`, open `95.0`, high `97.0`, low `94.5`, close `96.5`, volume `2,000,000` shares.
- **OHLC check** = high `97.0 >= 96.5` and low `94.5 <= 95.0`, so the row passes.
- **return** = if previous close is `95.0`, close-to-close return is `(96.5 / 95.0) - 1 = 1.58%`.
- **read** = the row is valid for feature computation only if units, date, and source are known.

---
</details>

### Quality And Usage
<details open>
<summary>The main risks are units, adjusted prices, symbol changes, and missing trading-calendar context.</summary>
---
#### Data quality issues

- **unit issue** = some official tables may state volume in hundreds of shares or another unit; the parser must normalize this.
- **adjustment issue** = raw prices around dividends and splits can distort returns if not adjusted.
- **calendar issue** = weekends and holidays must not be treated as missing trading days.
- **symbol issue** = ticker changes and listing events require a stable `security_id`.
- **source issue** = scraped public pages may differ from paid official data products.

---
#### Agent rules

- Data Agent must validate OHLC consistency before feature generation.
- TA Agent can use HOSE-style OHLCV for moving averages, RSI, gaps, and volume features.
- Backtest Agent must know whether prices are adjusted or unadjusted.
- Risk Agent should use volume and value to check liquidity and slippage assumptions.

---
#### Cons and references

- **main con** = official access terms and downloadable formats may constrain automation.
- **net** = HOSE is central for VN market data, but the schema must explicitly record units and adjustment state.
- `REF_HOSE_END_OF_DAY`: HOSE end-of-day statistics and information-service descriptions.
- `REF_HOSE_SERVICES`: HOSE information-service documents listing EOD trading fields.

---
</details>

### Disclosure Probe Status

HOSE is the primary official disclosure source for VCI and other HOSE-listed issuers.
A disclosure probe has been executed. See:

- `docs/data_sources/official_disclosure_source_discovery.md` — surface matrix + live results
- `docs/data_sources/official_disclosure_ingestion_foundation.md` — adapter/CLI design
- `scripts/probe_official_disclosures.py` — controlled CLI (plan/execute/checkpoint)
- `config/official_disclosure_targets.example.json` — real URL configuration

**Live probe result (run_id=20260612T052922Z):** `www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT`
returns HTTP 200 but is a React SPA shell (1,900 bytes, `id="HOSE"`,
`noscript>You need to enable JavaScript to run this app.`). Access status: `js_app_shell`.
PIT status: `blocked`. No structured disclosure data available without JS execution.

**Backend:** `api.hsx.vn` discovered from first-party JS bundle. Actual disclosure endpoint
paths are embedded in minified JS (env-var substituted at build time) and not recoverable
without a JS runtime.

**Blocker:** Headless browser or separate API contract documentation required to access
HOSE structured disclosure feed. HOSE official parent page is captured; structured API unresolved.

Do not rely on Vietstock or other secondary aggregators as canonical disclosure evidence.

---
