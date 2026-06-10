---
title: vietcap_iq_fa_firm_type_determination
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Firm-Type Determination Logic Design

**Status:** Design only — not implemented.  
**Date:** 2026-06-10  
**Branch:** `phase/fa-firm-type-determination-design`

---

## 1. Purpose

This document defines how the FA parser will determine, for each symbol, which
firm-type-specific mapping payload to use as the primary lookup under the Option C
(Hybrid gated mapping) strategy. This is one of the two open gates before parser
mapping integration may proceed (see
`docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` §7).

**No parser code is changed by this document.** `line_item_name` remains empty.
This is a pre-implementation design record.

---

## 2. Why Firm-Type Determination Is Needed

The Vietcap IQ `/financial-statement/metrics` endpoint returns a
**firm-type-specific mapping** — not a universal mapping. Four firm types have been
probed:

| Symbol | Firm type | Code count | Prefix examples |
|---|---|---|---|
| VCI, SSI | Securities | 1078 | `bss*`, `iss*`, `cfs*`, `nos*` |
| VCB | Bank | 384 | `bsb*`, `isb*`, `cfb*`, `nob*` |
| BVH | Insurance | 565 | `bsi*`, `isi*`, `noi*` |

Applying a bank mapping to a securities firm's fact rows (or vice versa) would assign
incorrect names to shared codes that have different `titleEn` values across firm types
(88 such conflicts were identified in the union of four payloads).

Under Option C, the parser must know a symbol's firm type to:
1. **Select the correct per-symbol mapping payload** for the primary lookup step
2. **Set `mapping_source_symbol`** correctly in provenance columns
3. **Avoid cross-type mislabeling** — a conflict code must never receive a name from
   a different firm type's mapping

---

## 3. Current Mapping Groups Observed

Four mapping groups have been confirmed by probing:

| Mapping group | Representative symbol | Code prefix pattern | Status |
|---|---|---|---|
| `securities` | VCI (primary), SSI (confirmed identical) | `bss*`, `iss*`, `cfs*`, `nos*` | Probed ✓ |
| `bank` | VCB | `bsb*`, `isb*`, `cfb*`, `nob*` | Probed ✓ |
| `insurance` | BVH | `bsi*`, `isi*`, `noi*` | Probed ✓ |
| `general` | FPT (observed in FA payloads, not probed for mapping) | shares `bsa*`/`isa*` with securities | No dedicated mapping payload |

**`general` covers all non-financial firms** (IT, manufacturing, real estate, consumer, etc.)
where a dedicated mapping group has not been identified. FPT's FA BALANCE_SHEET and CASH_FLOW
payloads contain the same code set as VCI (331 BS, 225 CF codes) — consistent with FPT being
in the `general` / VCI-compatible range, but no dedicated FPT mapping probe has been run.

**Fund (`QU`) firms** have not been probed. They are treated as `general` for now with consensus
fallback only, pending a dedicated fund mapping probe.

---

## 4. Available Local Metadata Fields

The Vietcap IQ universe is captured locally in:

```
data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv
data/processed/dry_run/vietcap_iq_universe/<run_id>/securities_master.csv
```

### 4.1 `instrument_universe.csv` columns (relevant subset)

| Column | Type | Notes |
|---|---|---|
| `symbol` | string | Stock ticker (e.g., `VCI`, `VCB`) |
| `company_type_code` | string | `NH` / `BH` / `CK` / `CT` / `QU` / `""` |
| `is_bank` | bool string | `"True"` / `"False"` — consistent with `company_type_code=NH` |
| `is_index` | bool string | `"True"` for index rows — not company rows |
| `icb_lv1_raw` … `icb_lv4_raw` | JSON string | ICB sector hierarchy (requires JSON parse) |

### 4.2 `securities_master.csv` columns (relevant subset)

| Column | Type | Notes |
|---|---|---|
| `symbol` | string | Stock ticker |
| `organ_code` | string | Vietcap internal org code (e.g., `VCSC` for VCI, `BVH` for BVH) |
| `is_bank` | bool string | `"True"` / `"False"` |
| `is_index` | bool string | `"True"` for index rows |

`securities_master.csv` does **not** contain `company_type_code` or ICB fields. Use
`instrument_universe.csv` as the primary metadata source for firm-type classification.

### 4.3 `company_type_code` distribution (run `20260604T085258Z`, 2080 rows)

| Code | Meaning | Count | Mapping group |
|---|---|---|---|
| `CT` | General company (Công ty) | 1778 | `general` |
| `QU` | Fund (Quỹ) | 181 | `general` (pending fund probe) |
| `CK` | Securities firm (Chứng khoán) | 43 | `securities` |
| `""` | Empty (index rows, etc.) | 34 | `none` (not parseable FA rows) |
| `NH` | Bank (Ngân hàng) | 30 | `bank` |
| `BH` | Insurance (Bảo hiểm) | 14 | `insurance` |

### 4.4 Key symbol lookups (run `20260604T085258Z`)

| Symbol | `company_type_code` | `is_bank` | Mapped group | ICB lv2 |
|---|---|---|---|---|
| VCI | `CK` | `False` | `securities` | Dịch vụ tài chính |
| SSI | `CK` | `False` | `securities` | Dịch vụ tài chính |
| VCB | `NH` | `True` | `bank` | Ngân hàng |
| BVH | `BH` | `False` | `insurance` | Bảo hiểm |
| FPT | `CT` | `False` | `general` | Công nghệ Thông tin |
| MBB | `NH` | `True` | `bank` | Ngân hàng |
| ACB | `NH` | `True` | `bank` | Ngân hàng |
| VHM | `CT` | `False` | `general` | Bất động sản |

### 4.5 `is_bank` field: consistency with `company_type_code`

`is_bank=True` is consistent with `company_type_code=NH` across all tested rows. Both signals
agree for VCB, MBB, TCB, ACB, BID, CTG, VPB, etc. However, `is_bank` alone cannot distinguish
insurance, securities, and general firms — all have `is_bank=False`. Therefore:

- `is_bank=True` → bank (high confidence, consistent with `NH`)
- `is_bank=False` → could be insurance, securities, fund, or general; requires `company_type_code`

---

## 5. Candidate Classification Approaches

### Approach A — Explicit symbol allowlist / mapping table

Maintain a hand-reviewed YAML or CSV config that explicitly assigns each probed symbol to a
mapping group:

```
VCI → securities
SSI → securities
VCB → bank
BVH → insurance
```

| Dimension | Assessment |
|---|---|
| Correctness | High for reviewed symbols — each assignment is explicit and auditable |
| Coverage | Low — only covers symbols explicitly listed; scales poorly to 1778 general firms |
| Maintenance | Manual update required when new firm types are probed |
| Auditability | Excellent — every assignment is a deliberate, reviewed decision |
| Risk | Safe — nothing is implied; unknown symbols fall through |

**Limitation:** Does not scale. Every new symbol requires a manual entry. Suitable only as a
supplement to metadata-driven classification, not as the sole mechanism.

---

### Approach B — Universe metadata-driven classification

Use `company_type_code` from `instrument_universe.csv` as the primary signal:

| `company_type_code` | Mapped group |
|---|---|
| `NH` | `bank` |
| `BH` | `insurance` |
| `CK` | `securities` |
| `CT`, `QU`, `""`, unknown | `general` |

| Dimension | Assessment |
|---|---|
| Correctness | High — `company_type_code` matches observed mapping groups for all tested symbols |
| Coverage | High — field is present for all 2080 rows in the current universe extract |
| Maintenance | Updates when universe is re-fetched; no manual entry per symbol required |
| Auditability | Good — `company_type_code` is a Vietcap-sourced field, documented by source |
| Risk | Moderate — depends on universe data being present and correct; index rows (`""`) must be filtered |

**Limitation:** Requires the universe CSV to be available at parse time. If the universe file is
absent or stale, classification falls back to `general` for all symbols, which is safe but loses
coverage.

---

### Approach C — Mapping-payload-driven classification by code prefixes

Inspect the code prefixes in the FA payload being parsed and infer firm type from the presence
of group-specific codes:

- `bsb*`, `isb*`, `cfb*` present → likely bank
- `bsi*`, `isi*`, `noi*` present → likely insurance
- `bss*`, `iss*`, `nos*` present → likely securities

| Dimension | Assessment |
|---|---|
| Correctness | Low — code prefix patterns overlap; all four groups share `bsa*`/`isa*`/`cfa*` general codes |
| Coverage | High — no external file needed |
| Maintenance | None |
| Auditability | Poor — inference from payload content, not from an authoritative metadata source |
| Risk | High — can produce a wrong mapping group, leading to name mislabeling |

**This approach must not be used for firm-type determination.** Prefix patterns are an audit
signal only — they can flag suspected misclassification but cannot be the source of truth for
which mapping payload to apply.

---

### Approach D — Hybrid: metadata-primary, explicit allowlist as override, prefix as audit signal

1. Use `company_type_code` from the universe CSV as the primary signal (Approach B).
2. Apply an explicit, hand-reviewed override table for the symbols whose mapping has been
   directly probed (Approach A) — these are the most certain assignments.
3. Use `is_bank` as a secondary consistency check: if `is_bank=True` and `company_type_code`
   disagrees, log a warning.
4. Use code-prefix patterns (Approach C) as an **audit-only signal** — emit a note if the
   inferred firm type from prefix does not match the metadata-derived type; never override
   metadata with prefix inference.
5. If universe CSV is absent or the symbol is not found in it, treat as `general`
   (conservative fallback).

| Dimension | Assessment |
|---|---|
| Correctness | High — metadata-driven primary with explicit overrides for known symbols |
| Coverage | High — handles all 2080+ symbols in the universe |
| Maintenance | Low — universe re-fetch updates classifications; overrides only for probed symbols |
| Auditability | High — classification source is recorded per row |
| Risk | Low — unknown symbols default to `general`, never to a wrong firm type |

---

## 6. Recommended Approach: Approach D (Hybrid)

**Recommended: Approach D — Hybrid metadata-primary with explicit overrides.**

Classification order:
1. **Explicit override table** (highest priority — hand-reviewed, directly probed):
   - `VCI` → `securities` (probed, baseline mapping)
   - `SSI` → `securities` (probed, confirmed identical to VCI)
   - `VCB` → `bank` (probed)
   - `BVH` → `insurance` (probed)
2. **`company_type_code` from `instrument_universe.csv`** (covers all 2080 symbols):
   - `NH` → `bank`
   - `BH` → `insurance`
   - `CK` → `securities`
   - `CT`, `QU`, `""`, or any other value → `general`
3. **`is_bank` fallback** (only if `company_type_code` is missing):
   - `is_bank=True` → `bank`
   - `is_bank=False` → `general`
4. **Default** (universe data entirely absent for the symbol): `general`

Consistency check (not a classification override — audit only):
- If `company_type_code=NH` and `is_bank != "True"` → emit a `WARNING` note
- If `is_bank == "True"` and `company_type_code != "NH"` → emit a `WARNING` note
- If code-prefix signals contradict metadata classification → emit a `NOTE` (for future review)

**Confidence levels:**
- `high`: symbol found in explicit override table (directly probed)
- `high`: `company_type_code` is one of `NH`/`BH`/`CK`/`CT`/`QU`
- `medium`: `company_type_code` is missing but `is_bank=True`
- `none`: no signal; defaulted to `general`

---

## 7. Fallback Policy for Unknown Symbol Type

When a symbol's firm type cannot be determined with confidence, or when the symbol maps to
`general` (covering 96% of all symbols — `CT` 1778 + `QU` 181 + unknown 34 = ~1993/2080),
the parser must behave conservatively:

| Condition | `mapping_status` behavior |
|---|---|
| `mapping_group=general` and code found in union consensus (conflict-free, section-matched) | `consensus_fallback` |
| `mapping_group=general` and code not in union consensus | `not_covered` |
| `mapping_group=general` and code is in the 88-conflict set | `conflict_skipped` |
| `mapping_group` known but no saved mapping payload available for that group | `no_mapping_available` |
| Symbol not in universe, group defaulted to `general` | `consensus_fallback` or `not_covered` per above |

**No name is ever invented.** The `general` fallback does not mean "apply securities mapping"
— it means "skip primary lookup; use consensus fallback only."

---

## 8. Auditability and Provenance Requirements

Every row in the parser output that receives a name (or a `mapping_status` value) must record:

| Field | Required value |
|---|---|
| `mapping_group` | One of `bank` / `insurance` / `securities` / `general` |
| `mapping_source_symbol` | Probed symbol whose payload was used (e.g., `VCB`, `BVH`, `VCI`) or `""` for `general` |
| `mapping_source_run_id` | `run_id` of the mapping probe whose payload was loaded |
| `mapping_status` | One of the six values defined in the integration strategy §6.3 |
| `mapping_conflict` | `"true"` if the code is in the 88-conflict set, `"false"` otherwise |
| `firm_type_confidence` | `high` / `medium` / `none` — from this document's classification |
| `firm_type_evidence` | The specific field and value used to derive the group |

`firm_type_confidence` and `firm_type_evidence` are new provenance columns to add alongside the
existing six integration columns defined in
`docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` §6.4.

---

## 9. Impact on Option C Mapping Integration

Under Option C (Hybrid gated mapping), the firm-type determination logic gates the **primary
lookup** step (§6.2 of the integration strategy):

```
For each (section, line_item_code) in a parsed FA row:
  1. Determine mapping_group for the symbol → this document
  2. If mapping_group != general:
       Look up code in the per-symbol mapping for that group
       If found and section matches → primary hit
  3. If not found in primary (or mapping_group=general):
       Look up in union consensus (conflict_free=true, section match only)
       If found → consensus_fallback
  4. If not found in either → not_covered
  5. If code in 88-conflict set → conflict_skipped (overrides steps 2–4)
```

The planner script (`scripts/plan_vietcap_iq_fa_firm_type_mapping.py`) produces the
`mapping_group`, `mapping_source_symbol`, `confidence`, and `evidence` per symbol offline.
This output is consumed by the future parser integration at parse time.

---

## 10. Limitations and Open Questions

1. **Fund (`QU`) mapping not probed.** 181 fund symbols are treated as `general`. If a future
   fund mapping probe reveals a distinct code set, `QU` will be re-classified to `fund` group.
2. **Additional general firm FA payloads not checked against insurance/bank mapping.** FPT's
   FA payloads use the same code set as VCI, but it is not confirmed whether all `CT` firms
   do. A future cross-check probe on a real estate (`VHM`) or industrial (`HPG`) firm is
   recommended.
3. **`company_type_code` field provenance.** The field is sourced from Vietcap IQ's company
   universe endpoint. It has not been cross-checked against an authoritative Vietnamese
   regulatory source (SSC/UBCK). The ICB `icb_lv2_raw` field provides a corroborating signal
   (bank ICB ≈ code `8300`; insurance ICB ≈ code `8500`; securities ICB ≈ code `8700`) but
   requires JSON parsing.
4. **No `is_insurance` field in the Vietcap IQ universe data.** Insurance detection relies
   entirely on `company_type_code=BH`. This is adequate given current evidence but should
   be noted as a single point of failure if `company_type_code` data quality degrades.
5. **Stale universe data.** If the universe CSV is from an old run, a recently reclassified
   firm (e.g., a securities firm converting to a bank holding company) would be misclassified
   until the universe is re-fetched.

---

## 11. Readiness Gates Before Parser Integration

| Gate | Current Status |
|---|---|
| Mapping integration strategy documented | **Done** — `vietcap_iq_fa_mapping_integration_strategy.md` |
| Conflict policy accepted | **Done** — Option C §6.3 |
| Mapping coverage report generated | **Done** — `fa_metric_mapping_union_coverage.csv` |
| Firm-type determination logic designed | **Done** — this document |
| Firm-type determination planner script | **Done** — `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` |
| Tests for planner script | **Done** — `tests/test_plan_vietcap_iq_fa_firm_type_mapping.py` |
| Tests for all Option C lookup behaviors (§6.6) | **Not done** |
| Parser integration code reviewed and approved | **Not done** |

---

## 12. Constraints Unchanged

| Constraint | Status |
|---|---|
| `line_item_name` is empty in all current parser output | **Unchanged** |
| `line_item_name_en` does not exist in current parser output | **Unchanged** |
| DB write is blocked | **Unchanged** — §17 gates not met |
| Backtest is blocked | **Unchanged** — §18 gates not met |
| `publicDate` PIT semantics are unconfirmed | **Unchanged** |
| Mapping coverage gate (95%) is not met | **Unchanged** — union: 89.4% BS / 92.3% IS / 86.7% CF |
| No invented metric names | **Unchanged** |

---

## 13. Relationship to Other Documents

| Document | Role |
|---|---|
| `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` | Parent design — §3.3 and §7 gate that this doc closes |
| `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` | Probe evidence for bank/insurance mapping groups |
| `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` | Securities group baseline (VCI, SSI) |
| `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` | Master gate table — §15 Metric Mapping Policy |
| `scripts/plan_vietcap_iq_fa_firm_type_mapping.py` | Offline planner script — produces firm-type mapping CSV |
| `data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv` | Primary metadata source for classification |
