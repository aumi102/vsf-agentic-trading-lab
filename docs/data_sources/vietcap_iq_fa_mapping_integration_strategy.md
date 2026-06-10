---
title: vietcap_iq_fa_mapping_integration_strategy
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Metric Mapping Integration Strategy

**Status:** Design complete. Parser integration implemented (2026-06-10) — see `docs/data_sources/vietcap_iq_fa_parser_mapping_integration.md`.  
**Date:** 2026-06-10  
**Branch:** `phase/fa-mapping-integration-strategy` (design); `phase/fa-parser-mapping-integration` (implementation)

---

## 1. Purpose

This document defines the strategy for integrating FA metric mapping into the Vietcap IQ FA
parser. It records the options considered, the evidence driving the decision, and the
implementation contract that must be satisfied before any parser code changes are made.

**No parser code is changed by this document.** `line_item_name` remains empty in all current
parser output. This is a pre-implementation design record.

---

## 2. Current Evidence Summary

### FA parser output

- Script: `scripts/parse_vietcap_iq_fa_payloads_dry_run.py`
- Output column: `line_item_name` — **always empty** (`""`)
- Guard: `_check_no_invented_names` ensures no names are written without a verified mapping
- 34,563 long-format fact rows parsed from 5 saved payloads; `line_item_name` empty in all

### Mapping payloads retrieved

| Symbol | Firm type | Run ID | HTTP | Notes |
|---|---|---|---|---|
| VCI | Securities | `20260610T025420Z` | 200 | Baseline probe |
| SSI | Securities | `20260610T033900Z` | 200 | Identical to VCI; confirms securities-type consistency |
| VCB | Bank | `20260610T033851Z` | 200 | Returns bank-specific codes (`isb*`, `bsb*`, `cfb*`) |
| BVH | Insurance | `20260610T033856Z` | 200 | Returns insurance-specific codes (`isi*`, `bsi*`, `noi*`) |

### Key finding: mapping is firm-type-specific

The `/financial-statement/metrics` endpoint does not return a universal mapping. It returns a
firm-type-specific mapping: securities firms (VCI, SSI) receive one mapping; banks (VCB) receive
another; insurance firms (BVH) receive another. Querying with a different symbol of the same firm
type returns the same mapping (SSI = VCI confirms this).

### Coverage summary

Coverage computed by `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` against 5 saved
FA probe payloads:

| Section | VCI-only | Union (VCI+VCB+BVH+SSI) | Consensus-only | Gate (95%) |
|---|---|---|---|---|
| BALANCE_SHEET | 62.8% | **89.4%** | 71.9% | **not met** |
| INCOME_STATEMENT | 43.6% | **92.3%** | 86.2% | **not met** |
| CASH_FLOW | 65.8% | **86.7%** | 78.2% | **not met** |
| NOTE | untested | untested | untested | untested |

- **Union coverage** = code present in any mapping payload (including conflicting codes)
- **Consensus coverage** = code with a conflict-free, consistent `titleEn` across all payloads
- Best observed union coverage is below 95% for all three tested sections

### Conflict summary

- 88 codes appear in multiple mapping payloads with **different `titleEn` values**
- These conflicts exist across firm types (e.g., `bsa2` = "Cash" in VCI, "Cash and precious
  metals" in VCB)
- Conflicting codes are flagged with `conflict=true` and an empty `line_item_name_en_consensus`
  in the union CSV (`data/processed/vietcap_iq/fa_metric_mapping_union.csv`)
- A universal mapping cannot safely assign a single name to a conflicting code without knowing
  the firm type of the symbol being parsed

---

## 3. Why Mapping Integration Is Not Safe Yet

The following conditions make parser integration premature:

1. **Coverage below gate:** No FA section reaches the 95% coverage threshold. Using a union
   with < 95% coverage would leave 8–13% of codes with empty `line_item_name_en` even after
   integration — acceptable only if the integration strategy handles this explicitly.

2. **88 name conflicts:** If the parser writes a conflicting name for a code, the output would
   contain a wrong or misleading name that depends on which firm type's mapping happened to be
   loaded. This is a data corruption risk for downstream consumers.

3. **Firm-type determination logic not yet integrated into parser:** The determination logic
   is now designed and documented (`docs/data_sources/vietcap_iq_fa_firm_type_determination.md`)
   with a planner script (`scripts/plan_vietcap_iq_fa_firm_type_mapping.py`). However, the
   parser code has not been changed. The planner output must be wired into the parser's primary
   lookup step (§6.2) before integration can proceed.

4. **`publicDate` PIT unconfirmed:** Even with correct names, DB write remains blocked on PIT
   validation. Rushing mapping integration does not unblock DB write by itself.

5. **No integration tests written:** The test suite validates that `line_item_name` is always
   empty. Integration would require new tests covering lookup, fallback, and conflict handling
   before any code change.

---

## 4. Integration Options

### Option A — Per-symbol mapping

**Behavior:** Before parsing a symbol's FA payload, query `/financial-statement/metrics` with
that symbol. Use the returned firm-type-specific mapping to populate `line_item_name_en`. No
union mapping involved.

| Dimension | Assessment |
|---|---|
| Correctness | High — names match the firm type exactly; no cross-type conflicts |
| Coverage per parse | Lower than union — securities firms get 62.8% BS / 43.6% IS / 65.8% CF; banks and insurance get their own coverage |
| Conflict risk | None — single source per symbol |
| Implementation complexity | Medium — parser must accept a mapping file or query the mapping endpoint before each symbol's parse; introduces a live network dependency if mapping is fetched at parse time |
| Auditability | Good — the `mapping_source_symbol` and `mapping_source_run_id` fields clearly identify the mapping used |
| DB-readiness | Still blocked on PIT and schema gates |
| Backtest-readiness | Still blocked |

**Limitation:** Requires either a live mapping probe per symbol (network dependency) or a
pre-cached mapping file per symbol (storage and freshness concern). Does not benefit from the
additional codes discovered by bank/insurance mapping probes when parsing a securities symbol.

---

### Option B — Universal union mapping

**Behavior:** Build the union mapping from all available firm-type payloads. Apply it
universally to every symbol regardless of firm type. Skip conflicting codes (leave `line_item_name_en`
empty for codes in the 88-conflict set).

| Dimension | Assessment |
|---|---|
| Correctness | Moderate — non-conflicting codes are correct; conflicting codes are skipped rather than wrong; but non-conflicting bank codes applied to a securities symbol may be misleading |
| Coverage | Highest — union gives 89.4% / 92.3% / 86.7%, still below 95% |
| Conflict risk | Managed — conflicting codes are silently skipped; but consensus codes may still be firm-type-inappropriate for some symbols |
| Implementation complexity | Low — one union CSV loaded at parse time; no per-symbol logic |
| Auditability | Poor — `mapping_source_symbol` would be ambiguous; not clear which firm type's name was used for codes shared across types |
| DB-readiness | Still blocked |
| Backtest-readiness | Still blocked |

**Limitation:** Applying bank-specific `bsb*` names to a securities firm's fact rows (where
those codes appear as zero/missing) is technically harmless but confusing in output. The
auditability of "which mapping produced this name" is lost.

---

### Option C — Hybrid gated mapping (Recommended)

**Behavior:**

1. **Primary lookup:** Use the firm-type-specific mapping for the symbol being parsed.
   - Determine the firm type using the Approach D hybrid logic (see
     `docs/data_sources/vietcap_iq_fa_firm_type_determination.md`): explicit override table
     for directly-probed symbols, then `company_type_code` from the Vietcap IQ universe CSV.
   - If a saved mapping payload for that firm type exists, use it as primary.
2. **Consensus fallback:** For codes not covered by the primary mapping, fall back to the
   union consensus mapping — but only if:
   - the code has `conflict=false` in the union CSV;
   - the code's `section` matches the FA section being parsed.
3. **No name for uncovered, conflicting, or mismatched codes.** Leave `line_item_name_en` empty
   with explicit `mapping_status` values (see §6.3).
4. **Record the mapping provenance** for every populated name via new output columns.

| Dimension | Assessment |
|---|---|
| Correctness | High — firm-type primary avoids cross-type mislabeling; consensus fallback is safe because conflict-free codes have identical names across firm types |
| Coverage | Medium-high — primary gives firm-type-accurate names; consensus fallback adds non-conflicting codes from other firm types; still < 95% until residual gap is closed |
| Conflict risk | Low — conflicting codes are never populated; provenance is recorded |
| Implementation complexity | Medium — requires firm-type determination logic and two-level lookup; but both mapping inputs (per-symbol CSV and union consensus CSV) already exist |
| Auditability | High — `mapping_source_symbol`, `mapping_source_run_id`, `mapping_conflict`, and `mapping_status` make the provenance traceable per row |
| DB-readiness | Still blocked on PIT and coverage gates, but the output is closer to production quality |
| Backtest-readiness | Still blocked |

---

## 5. Recommended Strategy

**Recommended: Option C — Hybrid gated mapping.**

Rationale:
- Per-symbol mapping (Option A) gives the most correct names but requires either a live
  network dependency or a pre-cached file per symbol. It also does not benefit from the
  coverage improvement that bank/insurance mapping adds for general codes shared across
  firm types.
- Universal union (Option B) is simpler but loses auditability and may apply bank-specific
  names in securities firm rows.
- Hybrid (Option C) combines the correctness of per-symbol mapping with the coverage
  improvement of the consensus union fallback, while keeping all provenance traceable.
  It does not require live network at parse time — both inputs are saved CSV files.

**The hybrid design is an enrichment layer, not a pre-condition for DB write.** Even after
implementation, DB write remains blocked on PIT validation, QuestDB schema design, and the
full-history fetch gate.

---

## 6. Future Parser Integration Contract

This section defines the intended behavior when integration is eventually implemented. **No
code changes are made here.** This contract must be reviewed and accepted before any
`parse_vietcap_iq_fa_payloads_dry_run.py` changes are committed.

### 6.1 Input files

| Input | Format | Description |
|---|---|---|
| Per-symbol mapping CSV | `_MAPPING_COLUMNS` schema | Output of `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` run with the symbol-matched mapping payload |
| Union consensus CSV | `_UNION_COLUMNS` schema | Output of `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py`; filtered to `conflict=false` rows only |
| FA payload file(s) | Saved `payload.json` files | No change from current parser input |

Both mapping CSVs must be pre-generated offline before the parser is invoked. The parser
must not fetch them from the network.

### 6.2 Mapping lookup order

For each `(section, line_item_code)` in a parsed FA row:

1. Look up `line_item_code` in the per-symbol (firm-type-specific) mapping for the current
   symbol's firm type.
   - If found and `section` matches → use `line_item_name_en`, set `mapping_status=primary`,
     set `mapping_source_symbol` to the symbol used for that mapping payload.
2. If not found in primary, look up in the union consensus mapping (conflict-free only).
   - If found and `section` matches → use `line_item_name_en_consensus`, set
     `mapping_status=consensus_fallback`, set `mapping_source_symbol=union`.
3. If not found in either → `line_item_name_en=""`, `mapping_status=not_covered`.
4. If the code appears in the union CSV with `conflict=true` → `line_item_name_en=""`,
   `mapping_status=conflict_skipped`, `mapping_conflict=true`.

### 6.3 Behavior by case

| Case | `line_item_name_en` | `mapping_status` | `mapping_conflict` |
|---|---|---|---|
| Code found in per-symbol mapping, section matches | populated | `primary` | `false` |
| Code found in consensus union, section matches, no conflict | populated | `consensus_fallback` | `false` |
| Code in union but `conflict=true` | `""` | `conflict_skipped` | `true` |
| Code found in no mapping payload | `""` | `not_covered` | `false` |
| Symbol has no mapping payload for its firm type | `""` (all rows) | `no_mapping_available` | `false` |
| Code found but section does not match mapping section | `""` | `section_mismatch` | `false` |

### 6.4 Output columns to add

The parser's `_LONG_FORMAT_COLUMNS` must be extended. The existing `line_item_name` column
is kept (and kept empty) for backwards compatibility until a migration decision is made.
New columns to add alongside it:

| New column | Type | Description |
|---|---|---|
| `line_item_name_en` | string | English name from mapping; empty if not covered or conflicting |
| `line_item_name_vi` | string | Vietnamese name from mapping; empty if not covered |
| `mapping_status` | string | One of `primary`, `consensus_fallback`, `conflict_skipped`, `not_covered`, `no_mapping_available`, `section_mismatch` |
| `mapping_source_symbol` | string | Symbol whose mapping payload was used (e.g., `VCI`, `VCB`, or `union`) |
| `mapping_source_run_id` | string | `run_id` of the mapping payload used; empty if not applicable |
| `mapping_conflict` | string | `true` if code is in a known conflict set; `false` otherwise |

The existing `line_item_name` column **must remain empty** during integration until a
deliberate deprecation decision is documented and the column is formally replaced.

### 6.5 Validation checks required before code integration

All of the following checks must be added to the parser and must pass before any mapping
integration is merged:

| Check | Severity | Description |
|---|---|---|
| `_check_mapping_status_validity` | error | `mapping_status` must be one of the six defined values |
| `_check_no_invented_names` (extended) | error | `line_item_name_en` must be empty for every code with `mapping_status` in `{conflict_skipped, not_covered, no_mapping_available, section_mismatch}` |
| `_check_conflict_flag_consistency` | error | If `mapping_conflict=true`, `line_item_name_en` must be empty |
| `_check_primary_coverage` | info/warning | Report what fraction of fact rows received `mapping_status=primary`; warn if below 50% |
| `_check_fallback_coverage` | info | Report what fraction received `consensus_fallback`; informational only |
| `_check_not_covered_fraction` | warning | Warn if `not_covered` exceeds configured threshold |
| `_check_mapping_source_run_id_present` | warning | Warn if `mapping_source_run_id` is empty for rows with `mapping_status=primary` |

### 6.6 Tests required before code integration

Before any parser integration code is merged, the following test groups must exist and pass:

| Test group | Description |
|---|---|
| Primary lookup — hit | Code found in per-symbol mapping with matching section; verify `line_item_name_en` populated and `mapping_status=primary` |
| Primary lookup — section mismatch | Code found in mapping but section differs; verify `line_item_name_en` empty and `mapping_status=section_mismatch` |
| Primary lookup — miss, consensus hit | Code not in primary, found in consensus (conflict-free); verify `mapping_status=consensus_fallback` |
| Conflict code skipped | Code in union with `conflict=true`; verify `line_item_name_en` empty and `mapping_status=conflict_skipped` |
| Not covered | Code in neither primary nor consensus; verify `mapping_status=not_covered` |
| No mapping file for firm type | Symbol with no available mapping payload; verify all rows have `mapping_status=no_mapping_available` |
| Backwards compatibility | Existing `line_item_name` column is still present and empty |
| No invented names | `_check_no_invented_names` still passes with the extended logic |
| Deterministic output | Same inputs → same output column order and row order |
| No network calls | Parser must not import `httpx` or `requests` |
| No DB calls | Parser must not write to any DB file format (`.db`, `.sqlite`, etc.) |

---

## 7. Integration Readiness Gates

### Gates before parser integration may proceed

| Gate | Current Status |
|---|---|
| Mapping integration strategy documented | **Done** — this document |
| Conflict policy accepted (never populate for conflicting codes) | **Done** — defined in §6.3 |
| Mapping coverage report generated from current saved payloads | **Done** — `data/processed/vietcap_iq/fa_metric_mapping_union_coverage.csv` |
| Firm-type determination logic designed | **Done** — `docs/data_sources/vietcap_iq_fa_firm_type_determination.md`; planner script `scripts/plan_vietcap_iq_fa_firm_type_mapping.py`; 46 tests |
| Tests for all lookup behaviors written (§6.6) | **Done** — 65 integration tests + 74 resolver tests |
| Parser integration code reviewed and approved | **Done** — `phase/fa-parser-mapping-integration` |

### Gates before DB write (unchanged from readiness doc §17)

| Gate | Current Status |
|---|---|
| Mapping integration dry-run passes on 5+ saved payloads | **Done** — 5 payloads, 53,013 rows, 0 errors |
| Mapping coverage ≥ 95% per section | **Not met** — best union: 89.4% / 92.3% / 86.7% |
| `publicDate` PIT semantics confirmed | **Not met** |
| Canonical QuestDB schema designed and reviewed | **Not met** |
| Natural key / dedup policy for re-ingestion defined | **Not met** |
| Full-history FA fetch tested for a small symbol set | **Not met** |
| Parser `--strict` mode passes on full-universe sample | **Not met** |

---

## 8. Constraints That Remain Unchanged

| Constraint | Status |
|---|---|
| `line_item_name` is empty in all current parser output | **Unchanged** |
| DB write is blocked | **Unchanged** — §17 gates not met |
| Backtest is blocked | **Unchanged** — §18 gates not met |
| `publicDate` PIT semantics are unconfirmed | **Unchanged** |
| No invented metric names | **Unchanged** — `_check_no_invented_names` enforced |
| Full-history FA fetch is not implemented | **Unchanged** |

---

## 9. Relationship to Other Documents

| Document | Role |
|---|---|
| `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table (§13, §15, §17, §18) — this doc extends §15 |
| `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` | VCI mapping baseline and CASH_FLOW shape evidence |
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` | Bank/insurance union coverage analysis and Options A/B/C overview |
| `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` | VCI-only and union coverage tables |
| `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` | Current parser — `line_item_name` empty |
| `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` | Offline per-symbol mapping parser |
| `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` | Union mapping builder and coverage analysis |
| `data/processed/vietcap_iq/fa_metric_mapping_union.csv` | Union mapping output (conflict flags included) |
| `data/processed/vietcap_iq/fa_metric_mapping_union_coverage.csv` | Coverage output |
