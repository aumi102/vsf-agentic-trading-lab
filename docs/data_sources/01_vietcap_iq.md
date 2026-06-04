---
title: 01_vietcap_iq
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Review

### Snapshot

<details open>
<summary>Vietcap IQ is now the preferred full-market universe candidate, while reports remain evidence inputs.</summary>

---

#### Mentor direction

- Vietcap IQ should be treated as the main candidate provider for the full Vietnamese market universe.
- Mentor guidance says Vietcap IQ can provide around 1600 symbols.
- HOSE listed universe currently has 403 symbols, so it is HOSE-specific and should not be treated as the full-market universe.
- Vietcap IQ universe discovery should support `securities_master`, `exchange_listings`, `symbol_universe`, and `instrument_universe`.
- This remains discovery/probe stage until a row-level payload is verified and source terms are reviewed.

---

#### Source role

- **source** = Vietcap IQ / Vietcap Trading browser-observed data surfaces.
- **primary candidate use** = full-market symbol and instrument universe.
- **secondary use** = company profiles, financial statements, financial ratios, company reports, and document/evidence metadata.
- **agent usage later** = FA Agent, Evidence Agent, Strategy Agent, and Answer Composer.
- **MVP stance** = probe Vietcap IQ universe first; do not promote it to canonical storage until raw fields, coverage, access, and terms are verified.

---

</details>

### Candidate URL Assessment

<details open>
<summary>Browser-observed Vietcap endpoints should be probed safely before parser planning.</summary>

---

| Priority | URL | Classification | Why it matters | Next action |
|---|---|---|---|---|
| P0 | `https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1` | likely universe candidate | Strongest full-market symbol search/universe candidate; may expose around 1600 instruments if mentor guidance matches payload. | Add to local probe config first and verify row-level JSON fields. |
| P1 | `https://trading.vietcap.com.vn/order/locales/vi/stock-asset.json?v=1780043897253` | secondary universe candidate | May contain stock asset localization or symbol list. | Probe only if the P0 search-bar payload is incomplete. |
| P1 | `https://trading.vietcap.com.vn/order/locales/vi/stock-asset-bond.json?v=1780043897253` | secondary universe candidate | May contain bond or mixed instrument asset labels. | Probe after P0 if bond/instrument classification is needed. |
| P2 | `https://trading.vietcap.com.vn/vietcap-iq/language/vi/company.json?v=1778834931080` | metadata/localization | Likely label/localization data for company UI fields, not the universe itself. | Use only to decode labels if needed. |
| P2 | `https://trading.vietcap.com.vn/vietcap-iq/language/vi/market.json?v=1778834931080` | metadata/localization | Likely label/localization data for market UI fields. | Use only to decode labels if needed. |
| P2 | `https://trading.vietcap.com.vn/api/market-data-service/v1/data-version` | metadata/localization | May expose data version metadata, not row-level universe. | Probe later to understand cache/version behavior. |
| P3 | `https://trading.vietcap.com.vn/api/price/marketStatus/getAll` | market status | Market/session state, not full universe. | Context-only; does not replace universe source. |
| P3 | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VNINDEX/price-chart?lengthReport=3&toCurrent=true` | chart-specific | Index-specific chart data for `VNINDEX`, not full universe. | Not a universe target. |
| P3 | `https://trading.vietcap.com.vn/vietcap-iq/data/stock-with-highest.json` | ranking/top list | Ranking/list endpoint, likely partial by design. | Not a full-universe target. |
| P3 | `https://trading.vietcap.com.vn/api/market-data-service/v1/tickers/price/top-stock` | ranking/top list | Top-stock endpoint, partial by design. | Not a full-universe target. |

---

</details>

### Canonical Mapping Target

<details open>
<summary>The first Vietcap IQ probe should establish full-market instrument coverage and field shape.</summary>

---

#### Candidate canonical tables

| Canonical table | Vietcap IQ role | Fields to discover |
|---|---|---|
| `securities_master` | one row per security/instrument | symbol, exchange, company name, short name, ISIN, instrument type, industry, status |
| `exchange_listings` | listing-level metadata | symbol, exchange, listed status, listed date, security type |
| `symbol_universe` | normalized tradable universe | symbol, exchange, display name, active flag, instrument category |
| `instrument_universe` | broader instrument set | stocks, bonds, ETFs, funds, covered warrants, indexes if present |

---

#### Discovery rules

- Do not assume all returned rows are ordinary stocks.
- Preserve the raw payload and metadata before any normalization.
- Record row count, observed fields, and instrument categories if present.
- Compare Vietcap IQ universe size against mentor guidance of around 1600 symbols.
- Compare overlap with HOSE's 403 listed-stock symbols after a verified payload exists.
- Do not use browser cookies, tokens, or local-only headers in committed config or docs.

---

</details>

### Reports And Evidence

<details open>
<summary>Vietcap IQ reports remain useful, but they are secondary to universe discovery for the next step.</summary>

---

#### Supporting data categories

| Category | Example | Later agent use |
|---|---|---|
| company report | ticker update report | FA thesis and valuation context. |
| industry report | banking, real estate, technology | sector regime and peer comparison. |
| market report | VN-Index daily or monthly wrap | market context and breadth narrative. |
| macro report | rates, FX, liquidity, policy | macro regime input. |
| recommendation fields | rating, target price, upside | evidence input, not automatic trade decision. |

---

#### Evidence safeguards

- Backtests must not use report content before `published_at`.
- Analyst text should be cited as opinion, not observed market fact.
- Report/document retrieval needs access and terms review before parser planning.

---

</details>
