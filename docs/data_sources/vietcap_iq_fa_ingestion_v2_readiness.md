---
title: vietcap_iq_fa_ingestion_v2_readiness
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Ingestion V2 Readiness

Master gate table for production Vietcap IQ FA ingestion. No DB write until all gates below are met.

---

## Current Status

| Item | Status |
|---|---|
| FA endpoint access | **Confirmed** — HTTP 200 (clean 8-header, no Cookie/Auth) for BS/IS/CF on VCI and FPT |
| Parser dry-run | **Done** — 53,013 fact rows from saved payloads; 7 validation checks; 583 tests pass |
| Option C mapping integration | **Done** — Mode B active; 7 output columns; 71 parser integration tests; dry-run: 0 errors |
| Metric mapping coverage | **Below gate** — union (7 payloads, all known groups sampled): BS 89.7% / IS 94.5% / CF 87.6%; 99 conflicts; gap appears structural for `/metrics` endpoint |
| `publicDate` PIT semantics | **Unconfirmed** — sample status `pit_inconclusive`; all 8 rows compared; no red flags; VCI evidence from secondary source only (confidence low) |
| Full-history FA fetch | **Not implemented** |
| DB write | **Blocked** — DB write gates not met |
| Backtest | **Blocked** — DB write not implemented |

---

## Key Confirmed Facts

| Fact | Evidence |
|---|---|
| FA endpoint HTTP 200 (clean 8-header profile, no Cookie/Auth) | Runs `20260609T035318Z`, `20260609T075846Z`, `20260609T075857Z` |
| Payload shape: `data.quarters` + `data.years`; opaque metric codes; `publicDate` present | Reviewed for VCI BS/IS, FPT BS, VCI CF, FPT CF |
| `publicDate` values follow ISO date format and are non-empty in all 5 saved payloads | `_check_publicdate_format` passes |
| PIT spot-check | 8 saved rows reviewed by CSV validator; status `pit_inconclusive`; all 8 rows have comparison evidence; no red flag found; VCI from Vietstock secondary source (confidence low) |
| `null` and `0.0` are distinct in payload; must stay distinct in output | `value_status` logic; `test_validate_preserves_null_vs_zero_distinction` |
| `nos*` columns null for non-securities firms (FPT) | `_check_nos_pattern` result |
| Mapping is firm-type-specific: SSI = VCI; VCB/BVH return different codes | 4 mapping probes |
| Union mapping (7 payloads: VCI+SSI+VCB+BVH+FPT+HPG+E1VFVN30): 1957 codes, 99 conflicts (5.1%); all known groups sampled | `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py` |
| CASH_FLOW: same envelope shape; 225 codes; `publicDate` non-null | VCI + FPT CASH_FLOW probes |

---

## Supported Sections

| Section | Probe | Parser |
|---|---|---|
| `BALANCE_SHEET` | VCI + FPT | Done — 331 codes |
| `INCOME_STATEMENT` | VCI | Done — 181 codes |
| `CASH_FLOW` | VCI + FPT | Done — 225 codes |
| Other (ratios, notes) | Not probed | Not implemented |

---

## Mapping Policy

- Option C (Hybrid) resolver wired into parser dry-run. See `vietcap_iq_fa_parser_mapping_integration.md`.
- Mode B active: general symbols use FPT as representative primary mapping, then union consensus fallback.
- This rescues general-symbol `bsa*` union conflicts via FPT primary; it does not close the global gate.
- `line_item_name` (legacy) always empty — never populated.
- `line_item_name_en` / `vi` populated via resolver; empty for conflicts, uncovered, or section-mismatch codes.
- Mapping integration does **not** unblock DB write — all DB write gates still apply.
- Coverage gate below 95% for all tested sections.

---

## PIT Availability Policy

`publicDate` is present in all parsed rows. The current sample validator returns
`pit_inconclusive`: all 8 rows now have comparison evidence (FPT via official company IR,
VCI via Vietstock secondary source); no `vietcap_before_official` red flag was found.
VCI dates are excluded from the credible-comparable count (confidence `low`), keeping the
ratio at 0.50 (below the 0.70 threshold for `pit_supported_small_sample`). Its exact
semantics remain **unconfirmed**. Do not use for PIT or look-ahead avoidance until
official HOSE or company IR dates for VCI (or a second issuer) are confirmed.
`availability_status` remains `unknown_until_publicDate_validated` for all rows.

---

## Null vs Zero Policy

- Payload `null` → `value_status=missing`, `value=""` in output.
- Payload `0.0` → `value_status=zero`, `value=0.0` in output.
- Must never be collapsed. `nos*` columns for non-securities firms are expected entirely `missing`.

---

## DB Write Readiness Gates

| Gate | Current Status |
|---|---|
| Metric mapping coverage ≥ 95% per section | **Not met** — union (7 payloads): BS 89.7% / IS 94.5% / CF 87.6%; gap appears structural for `/metrics` endpoint |
| `publicDate` PIT semantics confirmed | **Not met** |
| Canonical QuestDB schema designed and reviewed | **Not met** |
| Natural key / dedup policy for re-ingestion defined | **Not met** |
| Full-history FA fetch tested for a small symbol set | **Not met** |
| Parser `--strict` on full-universe sample | **Not met** |
| QuestDB migration implemented and reviewed | **Not met** |
| Round-trip ingestion tests (fetch → parse → write → query) | **Not met** |

---

## Backtest Readiness Gates

All DB write gates must be met first. Additionally:

| Gate | Status |
|---|---|
| `publicDate` PIT validated | Not met |
| Full-history FA data ingested | Not met |
| FA data completeness audit | Not met |
| Strategy using FA signals defined | Not met |
| Backtest framework selected | Not met |

---

## Next Steps

| Step | Depends On |
|---|---|
| ~~Probe additional firm types~~ — gap is structural; all known groups sampled | Done |
| Consider supplementary mapping source or revised gate threshold | Coverage gap analysis |
| Broaden `publicDate` PIT check beyond FPT spot sample | External records |
| Design canonical QuestDB schema + dedup/upsert policy | Coverage + PIT |
| Build full-history FA fetcher | Mapping + PIT + schema gates |
| Small-batch end-to-end dry run (5–10 symbols) | All above |
| Implement DB write | All DB write gates met |
| Implement backtest | All backtest gates met |

---

## Related Documents

- `vietcap_iq_fa_mapping_integration_strategy.md` — Option C design record
- `vietcap_iq_fa_parser_mapping_integration.md` — parser integration block note
- `vietcap_iq_fa_publicdate_pit_validation.md` — small PIT sample validator
- `vietcap_iq_fa_firm_type_determination.md` — firm-type determination (Approach D)
- `vietcap_iq_fa_mapping_coverage_bank_probe.md` — bank/insurance union coverage
- `vietcap_iq_fa_mapping_coverage_gap_probe.md` — general/fund gap probe; all known groups sampled
- `vietcap_iq_fa_mapping_cashflow_probe.md` — VCI mapping baseline and CASH_FLOW probe
- `vietcap_iq_fa_metric_mapping_discovery.md` — VCI-only coverage tables
- `notes/archive/vietcap_iq_fa_readiness_legacy.md` — full historical policy sections (§4–§13, §19)
