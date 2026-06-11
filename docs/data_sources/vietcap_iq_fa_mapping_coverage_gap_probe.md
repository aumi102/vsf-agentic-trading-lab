---
title: vietcap_iq_fa_mapping_coverage_gap_probe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Mapping Coverage Gap Probe

**Date:** 2026-06-11  
**Branch:** `phase/fa-mapping-coverage-gap-probe`  
**Baseline:** BS 89.4% / IS 92.3% / CF 86.7% (union: VCI+VCB+BVH+SSI, 1793 codes, 88 conflicts)

---

## 1. Purpose

Probe the remaining unrepresented firm types (`CT`/general and `QU`/fund) to determine whether
adding their mapping payloads to the union can lift coverage above the 95% DB write gate.

Prior probes covered `securities` (VCI, SSI), `bank` (VCB), and `insurance` (BVH). The general
group — approximately 96% of the 2080-symbol universe (CT=1778, QU=181, unknown=34) — had no
directly probed mapping payload.

---

## 2. Candidate Selection

| Symbol | `company_type_code` | Rationale |
|---|---|---|
| FPT | CT | Large, well-known general firm; previously observed to share VCI codes in FA payloads |
| HPG | CT | Cross-check: different sector (steel vs. tech), same CT type |
| E1VFVN30 | QU | Only fund (QU) representative in the universe; tests QU vs CT mapping equivalence |

All three are within the 3–5 symbol limit and cover both sub-types (`CT` and `QU`) of the general group.

---

## 3. Probe Results

All probes used the clean 8-header profile (`build_search_bar_headers()`, no Cookie, no
Authorization, no `sec-ch-ua*`) against the `/financial-statement/metrics` endpoint.

| Symbol | `run_id` | HTTP | Status | BS | IS | CF | NOTE | Total |
|---|---|---|---|---|---|---|---|---|
| FPT | 20260611T083439Z | 200 | verified | 122 | 25 | 41 | 157 | 345 |
| HPG | 20260611T083445Z | 200 | verified | 122 | 25 | 41 | 157 | 345 |
| E1VFVN30 | 20260611T083447Z | 200 | verified | 122 | 25 | 41 | 157 | 345 |

All three returned identical 345-code payloads. The `CT` and `QU` mapping payloads are the same.

---

## 4. Key Finding: All Firm Types Exhausted

The general mapping (345 codes) is a strict subset of the existing union (1793 codes from
VCI+VCB+BVH+SSI). It adds only 7 genuinely new codes:

| Section | New codes |
|---|---|
| BALANCE_SHEET | `bsa79` |
| INCOME_STATEMENT | `isa8`, `isa12`, `isa13`, `isa14` |
| CASH_FLOW | `cfa5`, `cfa33` |

All major firm types in the Vietcap IQ universe are now represented in the union mapping:
securities (VCI, SSI), bank (VCB), insurance (BVH), general/CT (FPT, HPG), fund/QU (E1VFVN30).
No additional firm-type payloads remain to probe.

---

## 5. Union After Gap Probe

| Metric | Before | After | Delta |
|---|---|---|---|
| Total union codes | 1793 | 1957 | +164 |
| Name conflicts | 88 | 99 | +11 |
| Payloads | 4 (VCI, SSI, VCB, BVH) | 7 (+FPT, HPG, E1VFVN30) | +3 |

The +164 codes are mainly `nos*` / `nob*` / `noi*` NOTE-section codes reprocessed from existing
payloads under the updated union builder. The 7 truly new metric codes listed above drove the
coverage delta. The 11 new conflicts arise from NOTE-section codes with differing names across
firm types.

---

## 6. Coverage After Gap Probe

| Section | Baseline | After probe | Delta | 95% gate |
|---|---|---|---|---|
| BALANCE_SHEET | 89.4% (296/331) | **89.7%** (297/331) | +0.3 pp | Blocked |
| INCOME_STATEMENT | 92.3% (167/181) | **94.5%** (171/181) | +2.2 pp | Blocked |
| CASH_FLOW | 86.7% (195/225) | **87.6%** (197/225) | +0.9 pp | Blocked |

No section reached 95%. IS is closest at 94.5% — 1 code (`isi1` or equivalent) away from the
gate if the remaining 10 uncovered IS codes were mappable.

---

## 7. Residual Uncovered Codes

Codes that appear in FA section payloads but in no mapping payload (union miss):

| Section | Count | Prefixes |
|---|---|---|
| BALANCE_SHEET | 34 | `bsi*` (15), `bsb*` (12), `bss*` (5), `bsa*` (2) |
| INCOME_STATEMENT | 10 | `isi*` (9), `iss*` (1) |
| CASH_FLOW | 28 | `cfs*` (16), `cfa*` (6), `cfi*` (4), `cfb*` (2) |

Prefix patterns show the residuals are firm-type-specific codes appearing in FA payloads but
absent from the `/metrics` mapping endpoint for all probed firm types:
- `bsi*` / `isi*`: insurance-specific codes present in BVH FA payloads but absent from BVH mapping
- `bss*` / `iss*` / `cfs*`: securities-specific codes present in VCI FA payloads but absent from VCI mapping
- `bsb*` / `cfb*`: bank-specific codes present in VCB FA payloads but absent from VCB mapping
- `cfi*`: present in insurance CF payloads, absent from BVH mapping

These codes are structurally unmappable from the `/metrics` endpoint alone: they are used in
financial statement payloads but the mapping endpoint does not define them for any known firm type.

---

## 8. Coverage Gate Status

| Gate | Status |
|---|---|
| BALANCE_SHEET ≥ 95% | **Not met** — 89.7% |
| INCOME_STATEMENT ≥ 95% | **Not met** — 94.5% |
| CASH_FLOW ≥ 95% | **Not met** — 87.6% |

The residual gap is structural: the `/metrics` endpoint does not expose names for certain
firm-type-specific codes. To reach 95%, a supplementary mapping source would be required
(e.g., scraping HTML page labels, a separate annotation layer, or accepting `not_covered`
status as tolerable below a new threshold).

---

## 9. Planner Script Update

`FPT`, `HPG`, and `E1VFVN30` were added to `_EXPLICIT_OVERRIDES` in
`scripts/plan_vietcap_iq_fa_firm_type_mapping.py` as `"general"`. This records the direct probe
evidence without changing `_GROUP_TO_SOURCE_SYMBOL["general"]` (which remains `""`) or
any fallback policy. Existing tests are unaffected; 9 new tests added in
`tests/test_plan_vietcap_iq_fa_firm_type_mapping.py`.

---

## 10. Next Recommended Action

The coverage gap is structural and cannot be closed by probing more firm types. Options:

1. **Lower the gate threshold** — document that 94.5% IS / 87.6% CF is the practical ceiling
   for the `/metrics`-only mapping approach and accept a revised gate (e.g., 90%).
2. **Supplement mapping** — source human-readable names for `bsi*`/`bss*`/`bsb*`/`cfs*`/`cfi*`
   codes from a secondary source (HTML scrape, annotation CSV, or vendor documentation).
3. **Block on PIT validation** — redirect effort to the other DB write gate
   (`publicDate` PIT confirmation) while the mapping gap is noted but deprioritised.

No action taken in this probe branch. Gate remains blocked.

---

## 11. Related Documents

- `vietcap_iq_fa_mapping_coverage_bank_probe.md` — baseline probe (VCI, SSI, VCB, BVH)
- `vietcap_iq_fa_firm_type_determination.md` — firm-type classification design
- `vietcap_iq_fa_ingestion_v2_readiness.md` — master gate table
