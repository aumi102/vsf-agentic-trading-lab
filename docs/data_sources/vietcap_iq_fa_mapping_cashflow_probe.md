---
title: vietcap_iq_fa_mapping_cashflow_probe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Mapping and CASH_FLOW Probe Report

**Date:** 2026-06-10

---

## Purpose

Two controlled probes:

1. **Metric mapping re-probe** — repeat attempt of `/financial-statement/metrics` (prior run DNS-failed).
   Goal: retrieve a code-to-name mapping for FA metric codes.
2. **CASH_FLOW shape probe** — first FA probe of CASH_FLOW for VCI and FPT.
   Goal: confirm payload envelope, code count, `publicDate` presence, shape consistency.

No DB writes. No backtests. No invented names.

---

## 1. Metric Mapping Probe

| Field | Value |
|---|---|
| `run_id` | `20260610T025420Z` |
| `http_status` | 200 |
| `access_status` | `verified` |
| Symbol | VCI |

### Code counts from mapping payload

| Section | Total entries | Null-field headers | Metric codes |
|---|---|---|---|
| BALANCE_SHEET | 212 | 4 | 208 |
| INCOME_STATEMENT | 80 | 0 | 80 |
| CASH_FLOW | 153 | 5 | 148 |
| NOTE | 642 | 0 | 642 |
| **Total** | **1087** | **9** | **1078** |

Null-field entries are UI display headers (no `field` value) — excluded from the mapping index.
Each metric entry has `field`, `titleEn`, `titleVi`, `fullTitleEn`, `fullTitleVi`, `level`, `parent`.

---

## 2. Mapping Coverage (VCI-only)

Coverage computed against 5 saved FA probe payloads:

| Probe | Symbol | Section | Codes in Payload | Covered | Coverage |
|---|---|---|---|---|---|
| `20260609T035318Z` | VCI | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260609T075846Z` | VCI | INCOME_STATEMENT | 181 | 79 | **43.6%** |
| `20260609T075857Z` | FPT | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260610T025429Z` | VCI | CASH_FLOW | 225 | 148 | **65.8%** |
| `20260610T025440Z` | FPT | CASH_FLOW | 225 | 148 | **65.8%** |

**Below the 95% DB write gate.** Uncovered codes are firm-type-specific variants not in the VCI
(securities) mapping. Bank and insurance probes later confirmed union coverage improves to
BS 89.4% / IS 92.3% / CF 86.7% — still below gate. See `vietcap_iq_fa_mapping_coverage_bank_probe.md`.

---

## 3. CASH_FLOW Shape Probe

| run_id | Symbol | http_status |
|---|---|---|
| `20260610T025429Z` | VCI | 200 |
| `20260610T025440Z` | FPT | 200 |

Both used the clean 8-header profile (no Cookie, no Authorization).

### CASH_FLOW payload shape

| Field | VCI | FPT |
|---|---|---|
| Quarters | 33 | 33 |
| Annual rows | 8 | 8 |
| Metric columns per row | 225 | 225 |
| `publicDate` non-null (quarterly) | 33/33 | 33/33 |
| `publicDate` non-null (annual) | 8/8 | 8/8 |
| First quarterly `publicDate` | `2018-08-17T00:00:00` | same format |
| Envelope structure | `data.quarters` + `data.years` | Same |

**CASH_FLOW envelope is identical to BALANCE_SHEET and INCOME_STATEMENT.** The same parser
handles all three sections without modification.

---

## 4. Mapping Dry-Run Parser

**Script:** `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py`

Pure offline parser (no network, no DB writes). Reads saved mapping `payload.json`; outputs
a flat CSV (`_MAPPING_COLUMNS`): `section`, `line_item_code`, `line_item_name_en`,
`line_item_name_vi`, `level`, `parent`, `is_header`. Null-field entries included with
`is_header=true`. Optionally computes per-(symbol, section) coverage against saved probe
payloads. Output is deterministic and sorted. **50 tests pass.**

---

## 5. Confirmed Facts

| Fact | Evidence |
|---|---|
| `/financial-statement/metrics` returns HTTP 200 with full mapping | `run_id=20260610T025420Z`, `verified` |
| Mapping structured as section-keyed dict of entry objects | Keys: `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `NOTE` |
| 1078 non-null metric codes across four sections | Parsed from mapping payload |
| 9 null-field entries are section-level UI headers — not metric codes | Confirmed by inspection |
| VCI-only coverage: 62.8% BS / 43.6% IS / 65.8% CF (below 95% gate) | Dry-run parser against saved payloads |
| CASH_FLOW envelope: `data.quarters` + `data.years` | VCI and FPT HTTP 200 |
| CASH_FLOW: 33 quarterly and 8 annual rows; 225 codes per row | Shape confirmed for both symbols |
| `publicDate` non-null for all CASH_FLOW rows in VCI and FPT | Payload inspection |

---

## 6. Outstanding Unknowns

| Unknown | Status |
|---|---|
| Why IS coverage is only 43.6% | Partially resolved — bank/insurance probes raised union IS to 92.3%; residual 7.7% is unaccounted for across all 4 firm types |
| Whether querying a different symbol type returns more codes | Resolved — SSI=VCI; VCB (bank) and BVH (insurance) confirmed distinct codes; union coverage still below 95% |
| `publicDate` PIT semantics | **Unconfirmed** — candidate field only; not cross-checked vs exchange filing records |
| NOTE section coverage in practice | No saved NOTE FA payload to test against |
| `nos*` codes in mapping | VCI has non-null `nos*` values; FPT does not; NOTE section codes not tested |

---

## 7. Gate Status

| Gate | Status after this probe |
|---|---|
| Mapping coverage ≥ 95% | **Not met** — VCI-only: 43–66%; union (after later bank/insurance probe): 87–92% |
| CASH_FLOW section confirmed | **Met** — HTTP 200; identical envelope; 225 codes; `publicDate` non-null |
| `publicDate` PIT semantics confirmed | **Not met** — unchanged |
| DB write | **Blocked** — mapping and PIT gates unmet |

---

## Related Documents

- `vietcap_iq_fa_mapping_coverage_bank_probe.md` — bank/insurance union coverage analysis
- `vietcap_iq_fa_mapping_integration_strategy.md` — Option C design record
- `vietcap_iq_fa_metric_mapping_discovery.md` — mapping discovery history
- `vietcap_iq_fa_ingestion_v2_readiness.md` — full gate table
- `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` — mapping parser (50 tests)
