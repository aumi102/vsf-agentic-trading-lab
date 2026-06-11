---
title: vietcap_iq_fa_payload_shape_review
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Payload Shape Review

**Review date:** 2026-06-09 | **Symbol:** VCI | **Section:** BALANCE_SHEET | **run_id:** `20260609T035318Z`

Full historical review archived at: `notes/archive/vietcap_iq_fa_payload_shape_review_legacy.md`

---

## Key Facts

| Fact | Value |
|---|---|
| HTTP status | `200` |
| Access profile | Clean 8-header (no Cookie, no Authorization) |
| Payload format | Wide-format: one row per period, 331 metric code columns |
| `data.quarters` | 33 rows; 2018 Q1 → 2026 Q1 |
| `data.years` | 8 rows; 2018 → 2025 annual |
| Metadata fields | `ticker`, `organCode`, `yearReport`, `lengthReport`, `publicDate`, `updateDate`, `createDate` |
| `publicDate` | Non-null for all 41 rows; semantics unconfirmed |
| `createDate` | Always `null` — do not use |

## Metric code prefix groups (BALANCE_SHEET, VCI)

| Prefix | Count | Sector |
|---|---|---|
| `bsa*` | 124 | General (all sectors) |
| `bsb*` | 64 | Bank-specific |
| `bsi*` | 46 | Insurance-specific |
| `bss*` | 54 | Securities-company |
| `nos*` | 43 | Off-balance-sheet notes |

High zero density (74.5%) is expected: bank and insurance columns carry no values for securities firm VCI.

## Current status

The FA parser is implemented (PR #7, 2026-06-10). This shape review was the pre-implementation probe.

- Parser pivots wide-format into long-format facts with 19 output columns.
- `line_item_name_en` / `line_item_name_vi` populated via Option C resolver.
- `publicDate` PIT semantics remain unconfirmed — see `vietcap_iq_fa_ingestion_v2_readiness.md`.

## Related documents

- `vietcap_iq_fa_ingestion_v2_readiness.md` — DB write gate status
- `vietcap_iq_fa_parser_mapping_integration.md` — parser output contract
- `vietcap_iq_fa_mapping_cashflow_probe.md` — subsequent probes (IS, CF sections)
