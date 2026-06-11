---
title: vietcap_iq_fa_mapping_coverage_bank_probe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Mapping Coverage — Bank/Insurance Probe Report

**Date:** 2026-06-10

---

## Purpose

Prior probes retrieved the metric mapping for VCI (securities) and found coverage of
62.8% BS / 43.6% IS / 65.8% CF — below the 95% DB write gate. This probe tested whether
querying bank and insurance symbols returns different codes that improve union coverage.

No DB writes. No backtests. No invented names.

---

## 1. Symbol Selection

| Symbol | Type | Rationale |
|---|---|---|
| VCB | Bank | Representative of `isb*` / `bsb*` bank codes |
| BVH | Insurance | Representative of `isi*` / `bsi*` insurance codes |
| SSI | Securities | Consistency check vs VCI baseline |

VCI was the baseline (`run_id=20260610T025420Z`).

---

## 2. Probe Results

| Symbol | run_id | http_status | Status |
|---|---|---|---|
| VCB | `20260610T033851Z` | 200 | `verified` |
| BVH | `20260610T033856Z` | 200 | `verified` |
| SSI | `20260610T033900Z` | 200 | `verified` |

All probes used the clean 8-header profile (no Cookie, no Authorization).

---

## 3. Per-Symbol Mapping Code Counts

| Symbol | Firm Type | BS codes | IS codes | CF codes | NOTE codes | Total |
|---|---|---|---|---|---|---|
| VCI (baseline) | Securities | 208 | 80 | 148 | 642 | 1078 |
| SSI | Securities | 208 | 80 | 148 | 642 | 1078 |
| VCB | Bank | 87 | 26 | 52 | 219 | 384 |
| BVH | Insurance | 151 | 84 | 49 | 281 | 565 |

**Key finding: SSI is identical to VCI.** Mapping is firm-type-specific — probing additional
securities firms adds no new codes. VCB and BVH return distinct codes from different prefix groups
(`bsb*`/`isb*`/`cfb*` for banks; `bsi*`/`isi*`/`noi*` for insurance).

---

## 4. Union Mapping

The union of all 4 payloads (VCI + VCB + BVH + SSI):

| Section | VCI-only | Union codes | Increase |
|---|---|---|---|
| BALANCE_SHEET | 208 | 296 | +88 |
| INCOME_STATEMENT | 80 | 167 | +87 |
| CASH_FLOW | 148 | 195 | +47 |
| NOTE | 642 | 1142 | +500 |
| **Total** | **1078** | **1793** | **+715** |

### Conflict analysis

**88 codes appear in multiple payloads with different `titleEn` values** (4.9% of union codes):

| Code | VCI name | VCB name | BVH name |
|---|---|---|---|
| `bsa2` | Cash and cash equivalents | Cash and precious metals | Cash and cash equivalents |
| `bsb108` | Held-to-maturity investment | Held-to-maturity securities | Held-to-maturity investment |
| `bsa6` | Financial assets at FVTPL | — | Short-term investments |

Conflicting codes are stored with `conflict=true` in `data/processed/vietcap_iq/fa_metric_mapping_union.csv`
and must never be assigned a name without firm-type disambiguation.

---

## 5. Coverage Analysis

Coverage computed by `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` against 5 saved FA payloads.

| Symbol | Section | FA codes | VCI-only % | Union % | Consensus % | Gate (95%) |
|---|---|---|---|---|---|---|
| VCI | BALANCE_SHEET | 331 | 62.8% | **89.4%** | 71.9% | **blocked** |
| VCI | INCOME_STATEMENT | 181 | 43.6% | **92.3%** | 86.2% | **blocked** |
| FPT | BALANCE_SHEET | 331 | 62.8% | **89.4%** | 71.9% | **blocked** |
| VCI | CASH_FLOW | 225 | 65.8% | **86.7%** | 78.2% | **blocked** |
| FPT | CASH_FLOW | 225 | 65.8% | **86.7%** | 78.2% | **blocked** |

Union significantly improves coverage — especially IS (+48.6%). **No section reaches 95%.**

Residual uncovered codes:

| Section | Uncovered | Dominant prefixes |
|---|---|---|
| BALANCE_SHEET | 35 of 331 | `bsi*` (15), `bsb*` (12), `bss*` (5) |
| INCOME_STATEMENT | 14 of 181 | `isi*` (9), `isa*` (4), `iss*` (1) |
| CASH_FLOW | 30 of 225 | `cfs*` (16), `cfa*` (8), `cfi*` (4) |

---

## 6. DB Write Gate Status

| Gate | Status |
|---|---|
| Mapping coverage ≥ 95% per section | **Not met** — union: BS 89.4% / IS 92.3% / CF 86.7% |
| `publicDate` PIT semantics confirmed | **Not met** — unchanged |
| DB write | **Not implemented** — unchanged |
| Backtest | **Not implemented** — unchanged |

---

## 7. Integration Strategy

The probe confirms that mapping is firm-type-specific. **Option C (Hybrid gated mapping) has
been implemented** — see `vietcap_iq_fa_mapping_integration_strategy.md` and
`vietcap_iq_fa_parser_mapping_integration.md` for dry-run validation.

Implementation status: per-symbol primary + union consensus fallback wired into parser dry-run
(2026-06-10); 7 output columns; 53,013 rows; 0 errors. DB write remains blocked.

---

## 8. Remaining Blockers

| Blocker | Notes |
|---|---|
| Mapping union coverage below 95% | BS 89.4% / IS 92.3% / CF 86.7% |
| 88 conflicting codes | Same code, different name across firm types |
| `publicDate` PIT semantics unconfirmed | No cross-check vs exchange filing records |
| Full-history FA fetch not implemented | Blocked on mapping + PIT + schema gates |
| QuestDB schema not designed | Blocked on mapping + PIT |
| DB write blocked | All readiness gates unmet |

---

## Related Documents

- `vietcap_iq_fa_mapping_integration_strategy.md` — Option C design record
- `vietcap_iq_fa_parser_mapping_integration.md` — parser integration block note
- `vietcap_iq_fa_mapping_cashflow_probe.md` — VCI mapping baseline and CASH_FLOW
- `vietcap_iq_fa_ingestion_v2_readiness.md` — full gate table
- `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` — union analysis (39 tests)
