---
title: vietcap_iq_fa_payload_shape_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Payload Shape Review

## Scope

| Field | Value |
|---|---|
| Review date | 2026-06-09 |
| `run_id` | `20260609T035318Z` |
| Symbol | `VCI` |
| Section | `BALANCE_SHEET` |
| Endpoint | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement?section=BALANCE_SHEET` |
| Diagnostic command | `python scripts/probe_vietcap_iq_fa_httpx_session.py --diagnostic-target fa-direct --symbol VCI --section BALANCE_SHEET --referer-style trading-company-page` |
| Metadata path | `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260609T035318Z/vietcap_iq_fa_financial_statement_balance_sheet_direct_parity/metadata.json` |
| Payload path | `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260609T035318Z/vietcap_iq_fa_financial_statement_balance_sheet_direct_parity/payload.json` |
| Guardrails | No Cookie, No Authorization, No warm-up, No sec-ch-ua*, No parser, No DB write, No backtest |

---

## Metadata Summary

| Field | Value |
|---|---|
| `run_id` | `20260609T035318Z` |
| `diagnostic_target` | `fa-direct` |
| `symbol` | `VCI` |
| `section` | `BALANCE_SHEET` |
| `http_status` | `200` |
| `access_status` | `verified` |
| `content_type` | `application/json` |
| `byte_size` | `354,443` |
| `content_hash` | `4d81b2994f2c61aa34b8b048b3794ee28467722445e3ee579d56c7557cf6bb19` |
| `manual_header_names` | `Accept, Accept-Language, Origin, Referer, Sec-Fetch-Dest, Sec-Fetch-Mode, Sec-Fetch-Site, User-Agent` |
| `manual_cookie_header_set` | `false` |
| `manual_authorization_header_set` | `false` |
| `cookies_saved` | `false` |
| `authorization_saved` | `false` |

---

## Top-Level Wrapper Shape

```
{
  "status": 200,
  "code": 0,
  "successful": true,
  "msg": "Successful",
  "exception": null,
  "serverDateTime": "2026-06-09T03:53:18.741570191",
  "traceId": "<present>",
  "data": {
    "quarters": [ ... 33 rows ... ],
    "years":    [ ... 8 rows  ... ]
  }
}
```

- `serverDateTime` is the server/crawl timestamp — **not** the financial report publication date.
- `data` is a `dict` with two keys: `quarters` and `years`.
- Both `quarters` and `years` are lists of row objects.

---

## data.quarters Shape

| Property | Value |
|---|---|
| Type | `list` |
| Length | `33` |
| Period coverage | `2018 Q1` to `2026 Q1` |
| Sort order | Chronological oldest-first |
| Row key count | `338` (7 metadata fields + 331 metric codes) |

### Metadata fields per row

| Field | Description | Always present |
|---|---|---|
| `ticker` | Stock ticker (`VCI`) | Yes |
| `organCode` | Organisation code (`VCSC`) | Yes |
| `yearReport` | Fiscal year (`int`) | Yes |
| `lengthReport` | Period type: `1`=Q1, `2`=Q2, `3`=Q3, `4`=Q4 | Yes |
| `publicDate` | Candidate report publication/availability date (ISO datetime, no timezone) — exact semantics unconfirmed | Yes — non-null for all 33 rows |
| `updateDate` | Record last-updated timestamp | Yes — non-null for all 33 rows |
| `createDate` | Record creation timestamp | Always `null` — do not rely on |

### Metric code groups (331 columns)

| Prefix | Count | Inferred content |
|---|---|---|
| `bsa*` | 124 | General balance sheet asset items (standard, applicable to all sectors) |
| `bsb*` | 64 | Bank-specific balance sheet items (mostly zero for securities firm VCI) |
| `bsi*` | 46 | Insurance-specific balance sheet items (mostly zero for VCI) |
| `bss*` | 54 | Securities-company balance sheet items (populated for VCI/VCSC) |
| `nos*` | 43 | Off-balance-sheet notes / customer securities holdings |

### Null and zero density

| Category | Count | Percentage |
|---|---|---|
| Null cells | `57 / 10,923` | `0.5%` |
| Zero cells | `8,140 / 10,923` | `74.5%` |
| Non-zero cells | `2,726 / 10,923` | `25.0%` |

High zero density is expected: bank (`bsb*`) and insurance (`bsi*`) columns carry no values for a securities firm.

### Sample period coverage (first 3 and last 3 rows)

| `yearReport` | `lengthReport` | `publicDate` |
|---|---|---|
| 2018 | 1 (Q1) | 2018-04-25 |
| 2018 | 2 (Q2) | 2018-08-17 |
| 2018 | 3 (Q3) | 2018-10-23 |
| … | … | … |
| 2025 | 3 (Q3) | 2025-10-16 |
| 2025 | 4 (Q4) | 2026-02-13 |
| 2026 | 1 (Q1) | 2026-04-21 |

---

## data.years Shape

| Property | Value |
|---|---|
| Type | `list` |
| Length | `8` |
| Period coverage | `2018` to `2025` annual |
| Sort order | Chronological oldest-first |
| Row key count | `338` (identical structure to quarters) |

### Metadata fields per row

Identical set as `quarters`. Key difference: `lengthReport=5` encodes annual reports for all 8 rows.

| Field | Notes |
|---|---|
| `lengthReport` | Always `5` (annual) |
| `publicDate` | Candidate report publication/availability date (ISO datetime, no timezone) — exact semantics unconfirmed; non-null for all 8 rows |
| `createDate` | Always `null` |

### Null and zero density

| Category | Count | Percentage |
|---|---|---|
| Null cells | `8 / 2,648` | `0.3%` |
| Zero cells | `1,986 / 2,648` | `75.0%` |
| Non-zero cells | `654 / 2,648` | `24.7%` |

### Sample period coverage

| `yearReport` | `lengthReport` | `publicDate` |
|---|---|---|
| 2018 | 5 (Annual) | 2019-06-19 |
| 2019 | 5 (Annual) | 2020-04-09 |
| 2020 | 5 (Annual) | 2021-10-11 |
| … | … | … |
| 2024 | 5 (Annual) | 2025-03-27 |
| 2025 | 5 (Annual) | 2026-02-13 |

---

## Sample Key Sets

Both `quarters[0]` and `years[0]` share the same 338-key structure. Non-exhaustive key samples:

```
Meta:   ticker, organCode, yearReport, lengthReport, publicDate, updateDate, createDate
bsa:    bsa1, bsa2, bsa3, bsa4, bsa5, bsa6, ..., bsa96
bsb:    bsb97, bsb98, bsb99, bsb100, ..., bsb132, bsb157, bsb158, bsb179-186, bsb258-275
bsi:    bsi139-156, bsi190-208, bsi279-287
bss:    bss133-138, bss187, bss189, bss212-257
nos:    nos355-362, nos370, nos375-396, nos399, nos410-413, nos607-616
```

Largest observed values (Q1 2018, VND):
- `nos379`: `20,879,083,390,000` — likely customer securities under management/custody
- `nos380`: `20,275,315,700,000` — related off-balance-sheet item
- `bsa53` / `bsa96`: `7,176,055,864,295` — likely total assets (both equal, likely balance-check pair)
- `bsa1`:  `7,113,171,810,074` — likely total assets excluding one sub-category

---

## Inferred Format

| Dimension | Observation |
|---|---|
| Format | **Wide-format**: one row per period, metric codes as columns |
| Periods | Rows (oldest-first) |
| Metric / line items | Columns (`bsa*`, `bsb*`, `bsi*`, `bss*`, `nos*`) |
| Period identifier | `(yearReport, lengthReport)` pair |
| Quarter/year structure | Identical key schema — parser can treat them uniformly |
| Metric code readability | **Opaque numeric codes only** — no human-readable line item names in the payload |
| Value type | `float` or `null`; no string values in metric columns |
| Currency | Not explicit; values are in VND based on magnitude (10¹⁰–10¹³ range) |
| Sector schema | Multi-sector: `bsa*` general; `bsb*` bank; `bsi*` insurance; `bss*` securities; `nos*` off-balance-sheet |

**Key implication for parser**: The parser must pivot this wide-format into a long-format `financial_statement_facts` table. Each `(period_row, metric_column)` cell becomes one fact row. The opaque code (`bsa1`) becomes the `line_item_code`; a separate mapping is needed for `line_item_name`.

---

## Parser-Readiness Assessment

| Item | Status |
|---|---|
| Raw payload captured | **Yes** — `run_id=20260609T035318Z` |
| Payload shape documented | **Yes** — this review |
| Parser readiness | **`ready_for_parser_planning`** |
| Ready for full ingestion | **`not_ready_for_full_ingestion`** |

### What is ready

- Period encoding (`yearReport`, `lengthReport`, `publicDate`) is clear and consistent.
- Row structure is uniform across quarters and years.
- Null/zero density is low and predictable.
- `publicDate` field is present and non-null — candidate availability/publication field; PIT semantics need confirmation before use in backtest.

### What is not yet ready

- **Only one section** (`BALANCE_SHEET`) for **one symbol** (`VCI`) has been captured. At least `INCOME_STATEMENT` and one additional symbol (e.g., `FPT`) should be inspected before a final parser is written.
- **No column name mapping exists.** Metric codes (`bsa1`, `bss212`, etc.) have no human-readable names in this payload. A separate static mapping table or a `/field-metadata` endpoint is needed before the parser can produce meaningful output.
- **Multi-sector schema**: Different industries use different prefix groups. A manufacturing company may use different sub-prefixes than a securities firm. The parser must handle sparse columns gracefully.
- **Parser must be implemented as dry-run first** — no DB write, no full-universe fetch until schema review is complete.

---

## PIT / Backtest Warning

> **`serverDateTime`** (`2026-06-09T03:53:18`) is the **crawl/server time** — when the HTTP response was generated. It is **not** the financial report publication or availability date.

The field `publicDate` (e.g., `2018-04-25` for VCI Q1 2018) is present and non-null for all rows. It is a **candidate availability/publication field** — it may represent the filing date, the exchange disclosure date, or the date Vietcap entered the data. Its exact semantics have not yet been confirmed against an authoritative source. Until confirmed, do not treat it as a validated point-in-time availability anchor.

| Use case | Status |
|---|---|
| Current-snapshot fundamental analysis prototype | **Usable** — data is fresh and access is confirmed |
| Historical point-in-time backtest | **Not yet safe** — `publicDate` semantics need confirmation (filing date? exchange disclosure date? Vietcap data-entry date?) |

Until `publicDate` semantics are confirmed against an authoritative source (e.g., exchange filings, annual report cover dates), treat all historical FA data as **forward-looking contaminated** for backtest purposes.

---

## Proposed Canonical Schemas (Design Only — Not Implemented)

### A. `financial_statement_facts` (long-format)

| Column | Type | Notes |
|---|---|---|
| `source_name` | string | `vietcap_iq` |
| `symbol` | string | Stock ticker (`VCI`) |
| `organ_code` | string | Source org code (`VCSC`) — keep for lineage |
| `statement_type` | string | e.g., `BALANCE_SHEET`, `INCOME_STATEMENT` |
| `period_type` | enum | `quarter` or `year` |
| `fiscal_year` | int | `yearReport` |
| `fiscal_quarter` | int or null | `lengthReport` (1-4), null for annual |
| `source_period_label` | string | e.g., `2025Q1`, `2025A` |
| `line_item_code` | string | Source metric code (`bsa1`, `bss212`, etc.) |
| `line_item_name` | string or null | Human-readable name — requires separate mapping |
| `value` | float or null | Numeric value |
| `unit` | string | `VND` (inferred, not explicit in payload) |
| `currency` | string | `VND` |
| `display_order` | int or null | Source-defined sort order if available |
| `hierarchy_level` | int or null | Indent/nesting level if available |
| `source_payload_id` | string | `run_id` |
| `content_hash` | string | SHA-256 of serialised payload |
| `publication_date` | datetime or null | `publicDate` from payload row |
| `crawled_at` | datetime | `crawled_at` from metadata |
| `server_datetime` | datetime | `serverDateTime` from payload wrapper |
| `availability_status` | enum | `unknown` until `publicDate` semantics confirmed |

### B. `raw_payload_archive`

| Column | Type | Notes |
|---|---|---|
| `source_name` | string | `vietcap_iq` |
| `endpoint` | string | Full URL |
| `symbol` | string | Stock ticker |
| `section` | string | FA section name |
| `run_id` | string | Diagnostic run identifier |
| `content_hash` | string | SHA-256 of payload bytes |
| `raw_path` | string | Local path to `payload.json` |
| `metadata_path` | string | Local path to `metadata.json` |
| `captured_at` | datetime | `crawled_at` from metadata |
| `access_profile` | string | e.g., `fa-direct-8-header-clean` |

---

## Next Recommended Steps

1. **Probe `INCOME_STATEMENT` for VCI** using `--diagnostic-target fa-direct --section INCOME_STATEMENT`. Compare key structure against this BALANCE_SHEET review.
2. **Probe `BALANCE_SHEET` for FPT** using `--diagnostic-target fa-direct --symbol FPT`. FPT is a non-financial company — compare prefix usage, especially whether `bss*` and `nos*` are zero while `bsa*` is populated differently.
3. **Locate or probe a column-name mapping.** Check whether Vietcap IQ exposes a `/field-metadata` or `/template` endpoint. Without it, `line_item_name` cannot be populated.
4. **Implement parser as dry-run only.** No DB write, no full-universe fetch, no backtest until steps 1–3 are complete.
5. **Confirm `publicDate` semantics.** Cross-reference one or two known VCI filing dates against exchange disclosures.

---

## Unknowns and Risks

| Unknown | Impact |
|---|---|
| `organCode` vs `ticker` — which is canonical for symbol lookup? | Parser must decide which field to join on |
| Column name mapping (`bsa1` → human name) — no names in payload | Parser output will use opaque codes until mapping is found |
| Multi-sector column schema — bsb*/bsi* likely zero for non-bank/insurance | Parser must handle sparse columns and avoid treating zero as missing |
| `publicDate` semantics — filing date, exchange disclosure date, or Vietcap entry date? | PIT backtest correctness depends on this |
| `createDate` always null — may be backend data-quality issue | Do not use this field |
| Historical coverage depth — 33 quarters (2018–2026) and 8 years for VCI; other symbols may differ | Coverage may not extend to pre-2018 for all symbols |
| Currency unit not in payload — VND inferred from magnitude | Parser must hard-code `VND` assumption until confirmed |
