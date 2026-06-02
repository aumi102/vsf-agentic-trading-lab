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
| HSX/HOSE official website/data surfaces | Canonical stock market source target. | Universe stocks, OHLCV price, order book/price board, corporate actions, indexes, trading calendar. | Public page, official API, manual download, or exchange file unknown. | Unknown. | Symbol, exchange, company name, security type, trading date, open/high/low/close, volume, value, reference price, ceiling/floor, bid/ask price levels, bid/ask volumes, event dates, event type, dividend/rights fields. | P0 probe. | Medium to high until surfaces are mapped. | Medium; must respect official terms, robots rules, and download limits. | Yes if verified as stock market source. | Active adapter: `hose`. | Manually identify stable official surfaces and add targets to local config. |
| Vietcap IQ | Company/financial/report/evidence source. | Financial reports, company reports, company profiles/data, financial statements, ratios, documents/evidence. | Portal/API/manual export unknown. | Yes/unknown. | Symbol, company profile fields, report title, report type, published_at, document URL/path, statement line items, fiscal year/period, ratio name/value, source document metadata. | P1/P2 probe. | Medium to high due auth/manual workflow. | Medium to high; respect report licensing and redistribution limits. | No for primary stock OHLCV. | Active adapter: `vietcap_iq`. | Identify permitted Vietcap IQ access path and add report/company/financial targets to local config. |
| VBMA | Vietnam bonds, auctions, rates, issuance, and local macro context. | Bond auctions, bond market data, yields, rates, issuance, reports. | Public page, manual download, official API unknown. | Unknown. | Auction date, issuer, tenor, offered amount, winning amount, winning yield, bid-to-cover, issue date, maturity date, coupon, bond code, curve date, yield, report title, published_at. | P2 probe. | Medium. | Medium; verify terms for downloads/crawling. | No for primary stock OHLCV. | Active adapter: `vbma`. | Manually inspect VBMA surfaces and add rates/auction/report targets to local config. |
| FRED/fredapi | Global macro context. | Macro series, observations, rates, yields, inflation, unemployment, liquidity/regime context. | Official API / `fredapi`. | API key normally required. | Series ID, observation date, value, realtime start/end, release metadata when available. Example series: DGS10, DGS2, T10Y2Y, FEDFUNDS, CPIAUCSL, UNRATE. | P2/P3 probe. | Low when API key exists. | Low if FRED terms are followed. | No for primary stock OHLCV. | Active adapter: `fred`. | Set `FRED_API_KEY` only when macro probing is needed. |

---

</details>
