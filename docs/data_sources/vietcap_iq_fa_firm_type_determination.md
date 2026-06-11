---
title: vietcap_iq_fa_firm_type_determination
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Firm-Type Determination Logic Design

**Status:** Implemented (2026-06-10) — wired into parser via `--firm-type-plan-csv`.  
**Date:** 2026-06-10

---

## 1. Purpose

Defines how the FA parser determines, for each symbol, which firm-type-specific mapping
payload to use as the primary lookup under Option C (Hybrid gated mapping). See
`vietcap_iq_fa_mapping_integration_strategy.md` for the full Option C design.

The planner script `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` produces a CSV per symbol
that is passed to the parser via `--firm-type-plan-csv`. DB write remains blocked.

---

## 2. Why Firm-Type Determination Is Needed

The `/financial-statement/metrics` endpoint returns a firm-type-specific mapping, not a universal one:

| Symbol | Firm type | Code count | Prefix examples |
|---|---|---|---|
| VCI, SSI | Securities | 1078 | `bss*`, `iss*`, `cfs*`, `nos*` |
| VCB | Bank | 384 | `bsb*`, `isb*`, `cfb*`, `nob*` |
| BVH | Insurance | 565 | `bsi*`, `isi*`, `noi*` |

88 codes appear across firm types with different `titleEn` values. Applying the wrong mapping
produces mislabeled output. The parser must know a symbol's firm type to select the correct
primary mapping payload.

---

## 3. Mapping Groups

| Mapping group | Representative symbol | Status |
|---|---|---|
| `securities` | VCI (primary), SSI (confirmed identical) | Probed |
| `bank` | VCB | Probed |
| `insurance` | BVH | Probed |
| `general` | FPT and all `CT`/`QU` firms | No dedicated payload — consensus fallback only |

`general` covers approximately 96% of the 2080-symbol universe (`CT`=1778 + `QU`=181 + unknown=34).

---

## 4. Available Metadata

Primary source: `data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv`

| Column | Notes |
|---|---|
| `symbol` | Stock ticker |
| `company_type_code` | `NH`=bank / `BH`=insurance / `CK`=securities / `CT`=general / `QU`=fund / `""`=index |
| `is_bank` | `"True"` consistent with `company_type_code=NH`; `"False"` cannot distinguish insurance/securities/general |

`company_type_code` is present for all 2080 rows and is the primary classification signal.
`is_bank` is a secondary consistency check only.

---

## 5. Approaches Compared

| Dimension | A — Symbol allowlist | B — `company_type_code` | C — Prefix inference | D — Hybrid (chosen) |
|---|---|---|---|---|
| Correctness | High for listed symbols | High — matches all tested symbols | Low — prefixes overlap across types | High |
| Coverage | Low — manual per symbol | High — all 2080 symbols | High — no external file | High — all 2080 symbols |
| Conflict risk | None | Low | High — can misclassify | Low |
| Maintenance | Manual update per new symbol | Auto on universe re-fetch | None | Low — overrides only for probed symbols |
| Auditability | Excellent | Good | Poor | High — source recorded per row |
| Use | Override table only | Primary signal | Audit signal only | Primary + override + audit |

---

## 6. Recommended Approach: D (Hybrid)

Classification order (first match wins):

1. **Explicit override table** (directly probed — highest confidence):
   - `VCI` → `securities`; `SSI` → `securities`; `VCB` → `bank`; `BVH` → `insurance`
2. **`company_type_code` from `instrument_universe.csv`**:
   - `NH` → `bank`; `BH` → `insurance`; `CK` → `securities`; `CT` / `QU` / `""` → `general`
3. **`is_bank` fallback** (only if `company_type_code` missing):
   - `is_bank=True` → `bank`; `is_bank=False` → `general`
4. **Default** (universe data absent for symbol): `general`

Confidence levels:
- `high`: symbol in override table OR `company_type_code` in `{NH, BH, CK, CT, QU}`
- `medium`: `company_type_code` missing but `is_bank=True`
- `none`: no signal; defaulted to `general`

Consistency checks (audit only — never override classification):
- `company_type_code=NH` and `is_bank != "True"` → emit WARNING
- `is_bank=True` and `company_type_code != "NH"` → emit WARNING
- Code-prefix signals contradict metadata type → emit NOTE

---

## 7. Fallback Policy

| Condition | `mapping_status` |
|---|---|
| `mapping_group=general`, code in consensus (conflict-free, section-matched) | `consensus_fallback` |
| `mapping_group=general`, code not in consensus | `not_covered` |
| `mapping_group=general`, code in 88-conflict set | `conflict_skipped` |
| `mapping_group` known but no saved payload for that group | `no_mapping_available` |

**No name is ever invented.** `general` means "skip primary lookup; use consensus fallback only."

---

## 8. Provenance Requirements

Every row receiving a name (or `mapping_status`) must record:

| Field | Value |
|---|---|
| `mapping_group` | One of `bank` / `insurance` / `securities` / `general` |
| `mapping_source_symbol` | Probed symbol used (e.g., `VCB`, `VCI`) or `""` for general |
| `mapping_source_run_id` | `run_id` of the mapping payload loaded |
| `mapping_status` | One of the six values in the strategy doc §6.3 |
| `mapping_conflict` | `"true"` if in 88-conflict set; `"false"` otherwise |
| `firm_type_confidence` | `high` / `medium` / `none` |
| `firm_type_evidence` | Field and value used to derive the group |

---

## 9. Limitations

1. **Fund (`QU`) mapping not probed.** 181 fund symbols treated as `general`. Re-classify when a dedicated fund probe is run.
2. **`general` code uniformity not confirmed.** FPT uses the same codes as VCI, but not all `CT` firms have been verified. Cross-check `VHM` or `HPG` in a future probe.
3. **`company_type_code` not cross-checked against SSC/UBCK.** ICB `icb_lv2_raw` provides a corroborating signal but requires JSON parsing.
4. **No `is_insurance` field.** Insurance detection relies solely on `company_type_code=BH`.
5. **Stale universe.** If the universe CSV is from an old run, recently reclassified firms will be misclassified until the universe is re-fetched.

---

## 10. Readiness Gates

| Gate | Status |
|---|---|
| Mapping strategy documented | Done |
| Conflict policy accepted | Done |
| Coverage report generated | Done |
| Firm-type planner script | Done — `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` |
| Planner tests | Done — `tests/test_plan_vietcap_iq_fa_firm_type_mapping.py` (46 tests) |
| Option C lookup tests | Done — 65 integration tests + 74 resolver tests |
| Parser integration reviewed and merged | Done — `8886058` (main) |

---

## 11. Constraints

| Constraint | Status |
|---|---|
| `line_item_name` empty in all parser output | Unchanged |
| `line_item_name_en` / `vi` populated via Option C resolver (not `line_item_name`) | Implemented |
| DB write blocked | Unchanged — DB write gates not met |
| Backtest blocked | Unchanged |
| `publicDate` PIT unconfirmed | Unchanged |
| Mapping coverage gate (95%) not met | Unchanged — union: BS 89.4% / IS 92.3% / CF 86.7% |

---

## 12. Relationship to Other Documents

| Document | Role |
|---|---|
| `vietcap_iq_fa_mapping_integration_strategy.md` | Parent design — Option C §6 |
| `vietcap_iq_fa_mapping_coverage_bank_probe.md` | Probe evidence for bank/insurance groups |
| `vietcap_iq_fa_metric_mapping_discovery.md` | Securities baseline (VCI, SSI) |
| `vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table |
| `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` | Planner script — produces firm-type CSV |
| `data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv` | Primary metadata |
