---
title: vietcap_iq_fa_mapping_coverage_bank_probe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Mapping Coverage — Bank/Insurance Probe Report

**Date:** 2026-06-10  
**Branch:** `phase/fa-mapping-coverage-bank-probe`

---

## Purpose

Prior probes retrieved the metric mapping for VCI (a securities firm) and found coverage of
62.8% BALANCE_SHEET / 43.6% INCOME_STATEMENT / 65.8% CASH_FLOW — below the 95% DB write gate
threshold. The INCOME_STATEMENT gap (43.6%) was the most significant.

This probe package tests the hypothesis that querying `/financial-statement/metrics` with
bank and insurance symbols returns different mapping codes, and that a union of all
firm-type mappings would improve coverage — particularly for INCOME_STATEMENT.

No DB writes. No backtests. No full-history fetch. No invented names.

---

## 1. Symbol Selection

| Symbol | Type | `is_bank` | Rationale |
|---|---|---|---|
| VCB | Bank | `True` | Major state-owned bank; representative of `isb*` bank IS codes |
| BVH | Insurance | `False` | Insurance conglomerate; representative of `isi*` insurance IS codes |
| SSI | Securities | `False` | Second securities firm; consistency check vs VCI mapping |

All three symbols are confirmed in the local universe file
(`data/processed/dry_run/vietcap_iq_universe/20260604T085258Z/securities_master.csv`).

VCI was the baseline (probed previously in `run_id=20260610T025420Z`). FPT was not re-probed
here — it is a general company sharing the same code structure as VCI but having already been
probed for FA section payloads.

---

## 2. Probe Results

| Symbol | run_id | http_status | access_status | Classification |
|---|---|---|---|---|
| VCB | `20260610T033851Z` | 200 | `verified` | `success_mapping_payload_found` |
| BVH | `20260610T033856Z` | 200 | `verified` | `success_mapping_payload_found` |
| SSI | `20260610T033900Z` | 200 | `verified` | `success_mapping_payload_found` |

All probes used the clean 8-header profile (no Cookie, no Authorization). Paths under
`data/raw/httpx_diagnostic/source=vietcap_iq/`.

---

## 3. Per-Symbol Mapping Code Counts

| Symbol | Firm Type | BS codes | IS codes | CF codes | NOTE codes | Total |
|---|---|---|---|---|---|---|
| VCI (baseline) | Securities | 208 | 80 | 148 | 642 | 1078 |
| SSI | Securities | 208 | 80 | 148 | 642 | 1078 |
| VCB | Bank | 87 | 26 | 52 | 219 | 384 |
| BVH | Insurance | 151 | 84 | 49 | 281 | 565 |

**Key finding: SSI is identical to VCI.** The mapping is firm-type-specific. Securities firms
(VCI, SSI) receive the same mapping response regardless of which securities symbol is queried.
Probing additional securities firms would not improve coverage.

**Bank and insurance mappings are significantly different.** VCB returns bank-specific codes
(`bsb*`, `isb*`, `cfb*`, `nob*`), and BVH returns insurance-specific codes (`bsi*`, `isi*`,
`noi*`). These populate codes absent from the VCI mapping.

---

## 4. Code Prefix Distribution by Firm Type

| Prefix | Probable Category | Appears in |
|---|---|---|
| `bsa*` | General balance sheet | VCI, VCB, BVH, SSI |
| `bsb*` | Bank-specific balance sheet | VCI (some), VCB |
| `bsi*` | Insurance-specific balance sheet | VCI (some), BVH |
| `bss*` | Securities-specific balance sheet | VCI, SSI |
| `isa*` | General income statement | VCI, SSI (some in BVH) |
| `isb*` | Bank-specific income statement | VCB |
| `isi*` | Insurance-specific income statement | BVH |
| `iss*` | Securities-specific income statement | VCI, SSI |
| `cfa*` | General cash flow | VCI, BVH, SSI |
| `cfb*` | Bank-specific cash flow | VCB, VCI (some) |
| `cfi*` | Insurance-specific cash flow | (hypothetical, not confirmed) |
| `cfs*` | Securities-specific cash flow | VCI, SSI |
| `nos*` | Off-balance-sheet notes (general/securities) | VCI, SSI |
| `nob*` | Bank notes | VCB |
| `noi*` | Insurance notes | BVH |

These prefix-to-category assignments are inferred from the mapping payload structure.
Individual code-to-name mappings come from `titleEn` in the saved payloads.

---

## 5. Union Mapping

The union of all 4 mapping payloads (VCI + VCB + BVH + SSI) contains:

| Section | VCI-only codes | Union codes | Increase |
|---|---|---|---|
| BALANCE_SHEET | 208 | 296 | +88 |
| INCOME_STATEMENT | 80 | 167 | +87 |
| CASH_FLOW | 148 | 195 | +47 |
| NOTE | 642 | 1142 | +500 |
| **Total** | **1078** | **1793** | **+715** |

The union adds 715 new codes, primarily from bank (VCB: 384) and insurance (BVH: 565) firm types.

### Conflict analysis

**88 codes have different `titleEn` values across firm types.** These are codes that appear in
multiple mapping payloads with non-identical English labels. Examples:

| Code | VCI name | VCB name | BVH name |
|---|---|---|---|
| `bsa2` | Cash and cash equivalents | Cash and precious metals | Cash and cash equivalents |
| `bsb108` | Held-to-maturity investment | Held-to-maturity securities | Held-to-maturity investment |
| `bsa6` | Financial assets at FVTPL | — | Short-term investments |

Conflicts represent 4.9% of union codes (88 / 1793). For these codes:
- A universal mapping cannot safely assign a single name without knowing the firm type.
- Per-symbol mapping (querying the endpoint per symbol before parsing) avoids conflicts entirely.
- In the union CSV (`data/processed/vietcap_iq/fa_metric_mapping_union.csv`), conflicting codes
  have `conflict=true` and an empty `line_item_name_en_consensus`.

---

## 6. Coverage Analysis

Coverage computed by `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` against 5 saved
FA probe payloads. Two metrics:
- **Union coverage** — codes present in any mapping payload (including conflicting ones)
- **Consensus coverage** — codes with a conflict-free name (safe for universal naming)

| Probe | Symbol | Section | FA codes | VCI-only % | Union % | Consensus % | Delta | Gate (95%) |
|---|---|---|---|---|---|---|---|---|
| `20260609T035318Z` | VCI | BALANCE_SHEET | 331 | 62.8% | **89.4%** | 71.9% | +26.6% | **blocked** |
| `20260609T075846Z` | VCI | INCOME_STATEMENT | 181 | 43.6% | **92.3%** | 86.2% | +48.6% | **blocked** |
| `20260609T075857Z` | FPT | BALANCE_SHEET | 331 | 62.8% | **89.4%** | 71.9% | +26.6% | **blocked** |
| `20260610T025429Z` | VCI | CASH_FLOW | 225 | 65.8% | **86.7%** | 78.2% | +20.9% | **blocked** |
| `20260610T025440Z` | FPT | CASH_FLOW | 225 | 65.8% | **86.7%** | 78.2% | +20.9% | **blocked** |

**The union significantly improves coverage for all sections, especially INCOME_STATEMENT
(+48.6%). However, no section reaches the 95% gate threshold.**

The largest remaining gaps are in BALANCE_SHEET (35 uncovered codes) and CASH_FLOW (30 uncovered
codes). Residual uncovered code prefixes:

| Section | Uncovered count | Dominant uncovered prefixes |
|---|---|---|
| BALANCE_SHEET | 35 of 331 | `bsi*` (15), `bsb*` (12), `bss*` (5), `bsa*` (3) |
| INCOME_STATEMENT | 14 of 181 | `isi*` (9), `isa*` (4), `iss*` (1) |
| CASH_FLOW | 30 of 225 | `cfs*` (16), `cfa*` (8), `cfi*` (4), `cfb*` (2) |

The residual uncovered codes are a mix of:
- Specialized codes not returned by any of the 4 firm types probed
- Codes present in FA payloads but absent from all mapping responses

---

## 7. Impact on DB Write Gates

| Gate | Previous Status | Updated Status |
|---|---|---|
| Metric mapping coverage ≥ 95% per section | Not met — VCI-only: BS 62.8% / IS 43.6% / CF 65.8% | **Not met** — union: BS 89.4% / IS 92.3% / CF 86.7%; still below 95% |
| `publicDate` PIT semantics confirmed | Not met | **Not met** — unchanged |
| DB write | Not implemented | **Not implemented** — unchanged |
| Backtest | Not implemented | **Not implemented** — unchanged |

The mapping gate remains blocked. Union coverage is the best achievable with 4 firm types probed
(VCI, VCB, BVH, SSI). The 95% threshold is not met for any section.

---

## 8. Residual Gap Analysis

The remaining uncovered codes suggest the mapping endpoint does not provide universal coverage
across all possible code variants. Three explanations are plausible:

1. **Additional firm types exist**: Other firm-type-specific mappings (e.g., fund management,
   real estate investment trusts) may contain additional codes.
2. **Mapping is intentionally partial**: The endpoint may deliberately omit some codes that the
   UI does not display, or that are internal/deprecated variants.
3. **Version drift**: Some codes in saved FA payloads may be from an older API version that no
   longer appears in the mapping endpoint's current response.

Without additional evidence, these possibilities cannot be distinguished.

---

## 9. Integration Strategy Implications

The probe data reveals that the mapping is **firm-type-specific**, which has implications for
how mapping integration should eventually be implemented:

- **Option A — Per-symbol mapping**: Before parsing each symbol's FA data, query the mapping
  endpoint with that symbol. Use the symbol-specific response to populate `line_item_name`.
  No union needed; no conflict risk. Coverage would match the per-symbol probe (62.8% BS,
  43.6% IS, 65.8% CF for a securities firm).

- **Option B — Union mapping (universal)**: Build a union of mappings from representative
  firm types. Better coverage (up to 92.3% IS), but 88 codes have conflicting names. The
  conflict requires a firm-type disambiguation step.

- **Option C — Hybrid**: Use per-symbol mapping for the queried symbol's specific codes; use
  the union only for general (`bsa*`, `isa*`, `cfa*`) codes where symbols agree.

None of these options is implemented. **`line_item_name` remains empty in all parsed fact rows.**
This decision requires an implementation design review once coverage is sufficient.

---

## 10. Remaining Blockers

| Blocker | Notes |
|---|---|
| Mapping union coverage < 95% threshold | BS 89.4% / IS 92.3% / CF 86.7% — all below gate |
| 88 conflicting codes in union mapping | Same code, different name across firm types; safe integration requires per-symbol or hybrid strategy |
| `line_item_name` not integrated into FA parser | Requires coverage gate + design review before integration |
| `publicDate` PIT semantics unconfirmed | No cross-check against exchange filing records |
| Full-history FA fetch not implemented | Requires mapping + PIT + schema gates |
| QuestDB schema not designed | Blocked on mapping + PIT |
| DB write blocked | All §17 gates in readiness doc still unmet |
| Backtest blocked | Requires DB write |

---

## 11. Next Recommended Task

1. **Investigate residual uncovered codes** — examine whether the 35 uncovered BS codes,
   14 IS codes, and 30 CF codes belong to specific firm types not yet probed (e.g., fund
   management companies). If a 5th firm type covers these codes, the 95% threshold may become
   reachable.

2. **Design the mapping integration strategy** (Options A, B, or C above) — this decision
   determines the parser API and whether per-symbol probes are needed at production scale.

3. **Validate `publicDate` PIT semantics** — cross-check 5–10 VCI/FPT rows against HOSE/HNX
   official filing records to confirm or refute PIT availability.

---

## Related Documents

- `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` — VCI mapping baseline and CASH_FLOW shape
- `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` — mapping discovery history
- `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` — full gate table
- `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` — union analysis implementation
- `tests/test_analyze_vietcap_iq_fa_metric_mapping_union.py` — 39 tests
