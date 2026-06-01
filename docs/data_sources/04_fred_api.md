---
title: 04_fred_api
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot
<details open>
<summary>FRED is a global macro source for external-rate, inflation, growth, and liquidity context.</summary>
---
#### Source role

- **source** = Federal Reserve Economic Data through the FRED API.
- **purpose** = collect global macro time series such as rates, CPI, GDP, unemployment, Treasury yields, and liquidity proxies.
- **agent usage** = Macro Agent, Risk Agent, Regime Agent, and Evidence Agent.
- **official fact** = FRED API lets programs retrieve economic data by source, release, category, series, and other preferences, using web requests.
- **MVP stance** = use a small curated series list, not a broad macro crawl.

---
#### Access surface

- **Access:** REST API over HTTPS with JSON or XML responses.
- **Build it:** API client with series whitelist, date range, and frequency mapping.
- **Your own code:** Python can call the API directly or through a wrapper such as `fredapi`, then store normalized observations.

---
</details>

### Data Categories
<details open>
<summary>FRED data is series-based and often revised, so vintage handling matters.</summary>
---
#### Candidate series families

| Family | Example use | Agent use |
|---|---|---|
| policy rates | Fed Funds rate | global risk and liquidity context. |
| Treasury yields | `2Y`, `10Y`, yield curve slope | discount-rate pressure and risk appetite. |
| inflation | CPI and inflation expectations | macro regime. |
| growth | GDP and industrial production | business-cycle context. |
| labor | unemployment and payrolls | risk-on/risk-off context. |
| dollar liquidity | USD index proxy or financial conditions proxies | external pressure on emerging markets. |

---
#### Important fields

- `series_id` = official FRED series ID.
- `observation_date` = date the value describes.
- `value` = numeric observation.
- `frequency` = daily, weekly, monthly, quarterly, or annual.
- `unit` = percent, index, currency, or level.
- `realtime_start` and `realtime_end` = vintage fields when available.
- `source_id` = FRED source or release reference.

---
</details>

### Proposed Schema
<details open>
<summary>Macro observations should be stored separately from market data and joined point-in-time.</summary>
---
#### Tables

| Table | Fields | Notes |
|---|---|---|
| `macro_series` | `series_id`, `name`, `frequency`, `unit`, `source`, `release_name` | one row per series. |
| `macro_observations` | `series_id`, `observation_date`, `value`, `realtime_start`, `realtime_end`, `source_id` | one row per observation and vintage. |
| `macro_features` | `series_id`, `feature_date`, `transformation`, `feature_value` | transformed macro inputs. |
| `macro_release_calendar` | `series_id`, `release_date`, `period` | prevents future leakage. |

---
#### Worked example

- **series** = effective policy rate series.
- **observation** = monthly value `5.25%` for `2024-05`.
- **daily alignment** = use the latest value known as of each trading day, not the month-end value before it is released.
- **feature** = `rate_change_3m = current_rate - rate_3_months_ago`.
- **read** = macro features are context variables; they should not be joined without release-date control.

---
</details>

### Quality And Usage
<details open>
<summary>The main risk is leaking future macro revisions into historical backtests.</summary>
---
#### Data quality issues

- **revision risk** = some macro series are revised after first release.
- **frequency mismatch** = monthly or quarterly data must be aligned to daily trading data.
- **release-date risk** = observation date is not the same as the date the market learned the value.
- **series selection risk** = too many macro series can create data-mining bias.
- **country mismatch** = US macro can influence Vietnam, but the link must be argued, not assumed.

---
#### Agent rules

- Macro Agent must state whether a series is used as global context or direct input.
- Backtest Agent must use point-in-time macro values when macro is part of a signal.
- Strategy Agent should not promote a strategy only because one macro relationship looks good in-sample.
- Answer Composer should explain macro uncertainty and avoid causal overclaiming.

---
#### Cons and references

- **main con** = macro data is often low-frequency and revised, so it is easier to misuse than daily prices.
- **net** = FRED is valuable for regime context, but the MVP should start with a small series whitelist.
- `REF_FRED_API_OVERVIEW`: FRED API official overview.
- `REF_FRED_SERIES_OBSERVATIONS`: FRED series observations endpoint and frequency aggregation.

---
</details>
