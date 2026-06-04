---
title: source_provider_matrix
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Provider Matrix

### Purpose

<details open>
<summary>Focused source scope from mentor feedback.</summary>

---

The active source scope is exactly:

- HSX/HOSE official stock market data surfaces.
- Vietcap IQ for company, financial, report, and evidence data.
- VBMA for Vietnam bonds, auctions, rates, and local macro context.
- FRED/fredapi for global macro context.

Do not claim a source is usable until a configured probe captures raw fields and terms/access have been reviewed.

---

#### Focused source table

| Source | Source role | Data categories | Access method | Auth required | Fields to discover | MVP priority | Crawl difficulty | Legal/terms risk | Blocks MVP? | Current repo status | Next action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HSX/HOSE official website/data surfaces | HOSE-specific exchange market data source. | HOSE listed universe, quote-report market data, order book/price board, corporate actions, indexes, trading calendar. | Public page, official API, manual download, or exchange file unknown. | Unknown. | Symbol, exchange, company name, security type, trading date, open/high/low/close, volume, value, reference price, ceiling/floor, bid/ask price levels, bid/ask volumes, event dates, event type, dividend/rights fields. | P0 for HOSE market data. | Medium to high until surfaces are mapped. | Medium; must respect official terms, robots rules, and download limits. | Yes for HOSE-specific market data, no for full-market universe. | Active adapter: `hose`; listed-universe dry run has 403 HOSE stock symbols. | Keep HOSE as exchange-specific; confirm quote-report units/EOD semantics before DB/backtest. |
| Vietcap IQ | Preferred full-market universe candidate plus company/financial/report/evidence source. | Full-market symbol/instrument universe, company profiles/data, financial statements, ratios, financial reports, company reports, documents/evidence. | Public browser-observed API, portal/API/manual export unknown. | Unknown; some endpoints may be public, others may require account access. | Symbol, exchange, company name, instrument type, active/listing status, industry, report title, report type, published_at, document URL/path, statement line items, fiscal year/period, ratio name/value, source document metadata. | P0 for full-market universe probe. | Medium until row-level search/universe payload is verified. | Medium to high; respect Vietcap terms and redistribution limits. | Yes for full-market universe planning if verified. | Active adapter: `vietcap_iq`; mentor expects around 1600 symbols from Vietcap IQ. | Probe `company/search-bar?language=1` first, then compare coverage with HOSE's 403 symbols. |
| VBMA | Vietnam bonds, auctions, rates, issuance, and local macro context. | Bond auctions, bond market data, yields, rates, issuance, reports. | Public page, manual download, official API unknown. | Unknown. | Auction date, issuer, tenor, offered amount, winning amount, winning yield, bid-to-cover, issue date, maturity date, coupon, bond code, curve date, yield, report title, published_at. | P2 probe. | Medium. | Medium; verify terms for downloads/crawling. | No for primary stock OHLCV. | Active adapter: `vbma`. | Manually inspect VBMA surfaces and add rates/auction/report targets to local config. |
| FRED/fredapi | Global macro context. | Macro series, observations, rates, yields, inflation, unemployment, liquidity/regime context. | Official API / `fredapi`. | API key normally required. | Series ID, observation date, value, realtime start/end, release metadata when available. Example series: DGS10, DGS2, T10Y2Y, FEDFUNDS, CPIAUCSL, UNRATE. | P2/P3 probe. | Low when API key exists. | Low if FRED terms are followed. | No for primary stock OHLCV. | Active adapter: `fred`. | Set `FRED_API_KEY` only when macro probing is needed. |

---

</details>
