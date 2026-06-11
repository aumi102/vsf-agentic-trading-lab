---
title: vietcap_iq_fa_mapping_integration_strategy
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Metric Mapping Integration Strategy

**Status:** Design complete. Parser integration implemented (2026-06-10).  
**Branch:** `phase/fa-mapping-integration-strategy` (design); `phase/fa-parser-mapping-integration` (implementation)

---

## 1. Purpose

Defines the strategy for integrating FA metric mapping into the Vietcap IQ FA parser.
Records the evidence driving the decision and the implementation contract.
Parser integration is done — see `vietcap_iq_fa_parser_mapping_integration.md` for dry-run
validation. This document is the design record.

---

## 2. Evidence Summary

### Coverage (union of VCI, SSI, VCB, BVH mapping payloads)

| Section | VCI-only | Union (4 symbols) | Consensus-only | Gate (95%) |
|---|---|---|---|---|
| BALANCE_SHEET | 62.8% | **89.4%** | 71.9% | **not met** |
| INCOME_STATEMENT | 43.6% | **92.3%** | 86.2% | **not met** |
| CASH_FLOW | 65.8% | **86.7%** | 78.2% | **not met** |

- **88 codes** appear across multiple payloads with different `titleEn` values (4.9% of union codes).
- Mapping is firm-type-specific: VCI = SSI (securities); VCB (bank); BVH (insurance) return distinct code sets.
- Union coverage is below 95% for all three tested sections.

---

## 3. Why Mapping Integration Requires Care

1. **Coverage below gate:** No section reaches 95%. Using a sub-gate union leaves 8–13% of codes
   unnamed even after integration — acceptable only with explicit handling.
2. **88 name conflicts:** A conflicting code must never receive a name from a different firm type's
   mapping — this is a data-integrity risk requiring Option C's conflict-skip policy.
3. **`publicDate` PIT unconfirmed:** Correct names do not unblock DB write. Rushing integration
   does not advance the DB write timeline.

---

## 4. Options Compared

| Dimension | A — Per-symbol | B — Union (universal) | C — Hybrid (chosen) |
|---|---|---|---|
| Correctness | High — firm-type exact | Moderate — bank codes applied to securities rows | High — per-type primary + safe consensus fallback |
| Coverage | Lower (VCI: 62.8% BS) | Highest (peak 92.3%) | Medium-high; below 95% until gap closed |
| Conflict risk | None | Managed (skip 88 codes) | Low — conflicts never populated; provenance tracked |
| Complexity | Medium — live probe or per-symbol CSV | Low — one union CSV | Medium — firm-type determination + two-level lookup |
| Auditability | Good | Poor — which firm type's name? | High — full provenance columns per row |
| Live network needed | Yes (or pre-cached per symbol) | No | No — both inputs are pre-computed offline CSVs |

---

## 5. Recommended Strategy

**Option C — Hybrid gated mapping.** Combines per-symbol correctness with union consensus
coverage improvement. Does not require live network at parse time. DB write remains blocked
regardless — this enrichment does not satisfy PIT or schema gates.

---

## 6. Parser Integration Contract (Implemented)

See `vietcap_iq_fa_parser_mapping_integration.md` for dry-run validation (5 payloads, 53,013 rows, 0 errors).

### 6.1 Input files

| Input | Format | Description |
|---|---|---|
| Per-symbol mapping CSV | `_MAPPING_COLUMNS` schema | From `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` for the symbol-matched firm type |
| Union consensus CSV | `_UNION_COLUMNS` schema | From `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py`; filtered to `conflict=false` rows |
| FA payload file(s) | Saved `payload.json` | No change from current parser input |

Both mapping CSVs must be pre-generated offline. The parser must not fetch them from the network.

### 6.2 Mapping lookup order

For each `(section, line_item_code)` in a parsed FA row:

1. Look up code in the per-symbol (firm-type-specific) mapping.
   - Found and `section` matches → `line_item_name_en` populated, `mapping_status=primary`.
2. If not found in primary, look up in union consensus (conflict-free only).
   - Found and `section` matches → `mapping_status=consensus_fallback`.
3. Not found in either → `mapping_status=not_covered`.
4. Code in union with `conflict=true` → `mapping_status=conflict_skipped`, `mapping_conflict=true`.

### 6.3 Behavior by case

| Case | `line_item_name_en` | `mapping_status` | `mapping_conflict` |
|---|---|---|---|
| Per-symbol mapping hit, section matches | populated | `primary` | `false` |
| Consensus union hit, section matches, no conflict | populated | `consensus_fallback` | `false` |
| Code in union with `conflict=true` | `""` | `conflict_skipped` | `true` |
| Code found in no mapping payload | `""` | `not_covered` | `false` |
| Symbol has no mapping payload for its firm type | `""` (all rows) | `no_mapping_available` | `false` |
| Code found but section does not match mapping section | `""` | `section_mismatch` | `false` |

### 6.4 Output columns added

The existing `line_item_name` column is kept empty (backwards compatibility). New columns:

| Column | Type | Description |
|---|---|---|
| `line_item_name_en` | string | English name; empty if not covered or conflicting |
| `line_item_name_vi` | string | Vietnamese name; empty if not covered |
| `mapping_status` | string | One of the six values in §6.3 |
| `mapping_source_symbol` | string | Symbol whose mapping payload was used (`VCI`, `VCB`, or `union`) |
| `mapping_source_run_id` | string | `run_id` of the mapping payload used |
| `mapping_conflict` | string | `true` if code is in the 88-conflict set; `false` otherwise |

`line_item_name` must remain empty until a formal deprecation decision is made.

---

## 7. Integration Readiness Gates

### Gates before parser integration (all done)

| Gate | Status |
|---|---|
| Mapping strategy documented | Done |
| Conflict policy accepted (never populate for conflicts) | Done |
| Coverage report generated | Done — `fa_metric_mapping_union_coverage.csv` |
| Firm-type determination logic designed | Done — `vietcap_iq_fa_firm_type_determination.md` |
| Tests for all Option C lookup behaviors | Done — 65 integration tests + 74 resolver tests |
| Parser integration dry-run implemented and merged | Done — `8886058` (main) |

### Gates before DB write (all blocked)

| Gate | Status |
|---|---|
| Mapping coverage ≥ 95% per section | **Not met** — best union: 89.4% / 92.3% / 86.7% |
| `publicDate` PIT semantics confirmed | **Not met** |
| Canonical QuestDB schema designed and reviewed | **Not met** |
| Natural key / dedup policy defined | **Not met** |
| Full-history FA fetch tested (small symbol set) | **Not met** |
| Parser `--strict` on full-universe sample | **Not met** |

---

## 8. Constraints Unchanged

| Constraint | Status |
|---|---|
| `line_item_name` empty in all parser output | Unchanged |
| DB write blocked | Unchanged — DB write gates not met |
| Backtest blocked | Unchanged |
| `publicDate` PIT unconfirmed | Unchanged |
| No invented metric names | Unchanged — `_check_no_invented_names` enforced |

---

## 9. Relationship to Other Documents

| Document | Role |
|---|---|
| `vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table — DB write and backtest gates |
| `vietcap_iq_fa_parser_mapping_integration.md` | Parser dry-run validation block note |
| `vietcap_iq_fa_firm_type_determination.md` | Approach D firm-type determination design |
| `vietcap_iq_fa_mapping_coverage_bank_probe.md` | Bank/insurance union coverage analysis |
| `vietcap_iq_fa_mapping_cashflow_probe.md` | VCI mapping baseline and CASH_FLOW probe |
| `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` | Parser |
| `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` | Union mapping builder and coverage |
| `data/processed/vietcap_iq/fa_metric_mapping_union.csv` | Union mapping with conflict flags |
