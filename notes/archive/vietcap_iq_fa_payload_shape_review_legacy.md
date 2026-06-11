# Vietcap IQ FA Payload Shape Review — Archived

**Source:** `docs/data_sources/vietcap_iq_fa_payload_shape_review.md` (archived 2026-06-11)
**Why archived:** This is the initial VCI BALANCE_SHEET payload shape review from 2026-06-09
(run `20260609T035318Z`). The FA parser is now fully implemented (PR #7, 2026-06-10); the
"Design Only — Not Implemented" schema proposals are superseded by the live parser output.
The shape facts remain useful for reference; the parser contract is the authoritative source.

---

## Scope

| Field | Value |
|---|---|
| Review date | 2026-06-09 |
| `run_id` | `20260609T035318Z` |
| Symbol | `VCI` |
| Section | `BALANCE_SHEET` |
| Endpoint | `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement?section=BALANCE_SHEET` |
| Guardrails | No Cookie, No Authorization, No warm-up, No sec-ch-ua*, No parser, No DB write, No backtest |

---

## Metadata Summary

| Field | Value |
|---|---|
| `run_id` | `20260609T035318Z` |
| `http_status` | `200` |
| `access_status` | `verified` |
| `content_type` | `application/json` |
| `byte_size` | `354,443` |
| `content_hash` | `4d81b2994f2c61aa34b8b048b3794ee28467722445e3ee579d56c7557cf6bb19` |
| `manual_cookie_header_set` | `false` |
| `manual_authorization_header_set` | `false` |

---

## Top-Level Wrapper Shape

```
{
  "status": 200,
  "code": 0,
  "successful": true,
  "msg": "Successful",
  "serverDateTime": "2026-06-09T03:53:18.741570191",
  "data": {
    "quarters": [ ... 33 rows ... ],
    "years":    [ ... 8 rows  ... ]
  }
}
```

- `serverDateTime` is the server/crawl timestamp — **not** the financial report publication date.
- `data` is a `dict` with two keys: `quarters` and `years`.

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

### Sample period coverage

| `yearReport` | `lengthReport` | `publicDate` |
|---|---|---|
| 2018 | 1 (Q1) | 2018-04-25 |
| 2018 | 2 (Q2) | 2018-08-17 |
| 2018 | 3 (Q3) | 2018-10-23 |
| … | … | … |
| 2025 | 4 (Q4) | 2026-02-13 |
| 2026 | 1 (Q1) | 2026-04-21 |

---

## data.years Shape

| Property | Value |
|---|---|
| Type | `list` |
| Length | `8` |
| Period coverage | `2018` to `2025` annual |
| `lengthReport` | Always `5` (annual) |
| Row key count | `338` (identical structure to quarters) |

### Sample period coverage

| `yearReport` | `lengthReport` | `publicDate` |
|---|---|---|
| 2018 | 5 (Annual) | 2019-06-19 |
| 2019 | 5 (Annual) | 2020-04-09 |
| … | … | … |
| 2025 | 5 (Annual) | 2026-02-13 |

---

## Inferred Format

| Dimension | Observation |
|---|---|
| Format | **Wide-format**: one row per period, metric codes as columns |
| Metric code readability | Opaque numeric codes only — no human-readable line item names in the payload |
| Value type | `float` or `null`; no string values in metric columns |
| Currency | Not explicit; values are in VND based on magnitude |

**Parser implication:** pivot wide-format into long-format `financial_statement_facts` — each
`(period_row, metric_column)` cell becomes one fact row; a separate mapping is needed for
`line_item_name`. The Option C resolver (PR #7) supplies `line_item_name_en` / `line_item_name_vi`.

---

## PIT / Backtest Warning

`serverDateTime` is the **crawl/server time** — when the HTTP response was generated. It is
**not** the financial report publication date.

`publicDate` (e.g., `2018-04-25` for VCI Q1 2018) is a **candidate availability/publication
field** — semantics unconfirmed against an authoritative source. Until confirmed, do not treat it
as a validated point-in-time availability anchor. See `vietcap_iq_fa_ingestion_v2_readiness.md`
for current gate status.

---

## Proposed Canonical Schemas (Design Only — Superseded)

These schema proposals from the original review have been superseded by the live parser output
columns documented in `vietcap_iq_fa_parser_mapping_integration.md`.

The live output has 19 columns including `mapping_status`, `mapping_source_symbol`,
`mapping_conflict`, `mapping_group`, `line_item_name_en`, `line_item_name_vi`, and
`availability_status`.

---

## Unknowns and Risks (status as of 2026-06-09)

| Unknown | Current status |
|---|---|
| `publicDate` semantics | Unconfirmed — still blocked per readiness doc |
| `createDate` always null | Confirmed — do not use |
| Historical coverage depth | 33 quarters (2018–2026) for VCI |
| Currency unit | VND inferred; not explicit in payload |
