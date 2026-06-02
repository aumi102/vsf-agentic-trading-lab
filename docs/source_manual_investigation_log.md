---
title: source_manual_investigation_log
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Manual Investigation Log

### Purpose

<details open>
<summary>Human-filled checklist for the four active mentor-named sources.</summary>

---

This is not a verification record until a raw sample is captured by `scripts/probe_sources.py`. Screenshots and manual notes are useful, but raw samples with metadata are better. Do not paste secrets, tokens, passwords, cookies, or private credentials into this file.

---

#### Investigation table

| Source | Candidate URL / endpoint / file | How found | Access type | Auth required | Terms/robots checked | Sample symbol/date supported | Observed raw fields | Likely canonical table | Status | Next action | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HSX/HOSE official website/data surfaces | TBD | Manual website/API/download inspection | Public page/API/download unknown | Unknown | No | Unknown | Unknown | `securities`, `daily_prices`, `order_book_snapshots`, `realtime_quote_snapshots`, `corporate_events`, `index_prices`, `trading_calendar` | not investigated | Find stable official surfaces for universe, OHLCV, order book/price board, actions, indexes, and calendar; add to local config. | Prefer official source; do not scrape aggressively. |
| Vietcap IQ | TBD | Portal/API/export access inspection | Portal/API/manual export unknown | Yes/unknown | No | Symbol likely, date/fiscal period unknown | Unknown | `company_profiles`, `financial_statement_items`, `financial_ratios`, `company_reports`, `report_documents` | not configured | Identify permitted Vietcap IQ report/company/financial access path and add to local config. | Do not label as primary OHLCV unless raw fields prove it. |
| VBMA | TBD | Manual website/download/API inspection | Public/manual/API unknown | Unknown | No | Date likely, symbol not relevant | Unknown | `bond_auctions`, `bond_instruments`, `yield_curve_points`, `bond_reports`, `macro_context_events` | manual only | Identify stable auction, yield/rates, issuance, and report surfaces. | Local macro/bonds context, not stock OHLCV. |
| FRED/fredapi | FRED API observations endpoint | Official API docs | Official API / `fredapi` | API key normally needed | Not yet | Macro series/date range | Series ID, observation date, value, realtime fields | `macro_series`, `macro_observations`, `macro_features` | not configured | Set `FRED_API_KEY` if macro context probing is needed. | Example series: DGS10, DGS2, T10Y2Y, FEDFUNDS, CPIAUCSL, UNRATE. |

---

</details>
