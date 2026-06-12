---
title: vietcap_iq_fa_publicdate_pit_validation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA publicDate PIT Validation

## Purpose

Check whether Vietcap IQ FA `publicDate` can be treated as a point-in-time
availability/publication field. This is a small validation pass only; it does
not unblock DB writes or backtests.

## Sample Selection

The sample uses saved local FA payloads only. It covers FPT and VCI where saved
payloads exist, BALANCE_SHEET / INCOME_STATEMENT / CASH_FLOW, annual and Q1
periods, and recent periods most likely to have accessible disclosure pages.

Saved payload sources:

- FPT BALANCE_SHEET: `20260609T075857Z`
- FPT CASH_FLOW: `20260610T025440Z`
- VCI BALANCE_SHEET: `20260609T035318Z`
- VCI INCOME_STATEMENT: `20260609T075846Z`
- VCI CASH_FLOW: `20260610T025429Z`

## Validation Method

For each sample row, compare Vietcap `publicDate` to the best official or
authoritative disclosure evidence found in a tiny manual lookup. Source priority
was exchange/company official disclosure pages first. FPT official IR disclosures
were accessible. Vietcap official disclosure pages returned 403 from this
environment, and no HOSE disclosure date was recovered in this pass.

Classification:

- `exact_match`: same date.
- `near_match_1_3_days`: Vietcap date is within 1-3 days of official date.
- `after_official`: Vietcap date is later than official date by more than 3 days.
- `before_official`: Vietcap date is earlier than official date.
- `not_found`: official disclosure date was not found.
- `ambiguous`: source date is not clearly a disclosure date.

## Sample Results

| Symbol | Section | Period | Vietcap `publicDate` | Official evidence | Official date | Delta | Status | Note |
|---|---|---:|---|---|---|---:|---|---|
| FPT | BALANCE_SHEET | 2025 annual | 2026-03-20 | FPT IR: audited consolidated/separate FS 2025 | 2026-03-19 | +1 | near_match_1_3_days | Conservative by 1 day |
| FPT | CASH_FLOW | 2025 annual | 2026-03-20 | FPT IR: audited consolidated/separate FS 2025 | 2026-03-19 | +1 | near_match_1_3_days | Same period source |
| FPT | BALANCE_SHEET | 2026 Q1 | 2026-04-28 | FPT IR: consolidated/separate FS Q1 2026 | 2026-04-24 | +4 | after_official | Conservative by 4 days |
| FPT | CASH_FLOW | 2026 Q1 | 2026-04-28 | FPT IR: consolidated/separate FS Q1 2026 | 2026-04-24 | +4 | after_official | Same period source |
| VCI | BALANCE_SHEET | 2025 annual | 2026-02-13 | Vietcap official page blocked; HOSE not found |  |  | not_found | Do not infer |
| VCI | INCOME_STATEMENT | 2025 annual | 2026-02-13 | Vietcap official page blocked; HOSE not found |  |  | not_found | Do not infer |
| VCI | BALANCE_SHEET | 2026 Q1 | 2026-04-21 | Vietcap official page blocked; HOSE not found |  |  | not_found | Do not infer |
| VCI | CASH_FLOW | 2026 Q1 | 2026-04-21 | Vietcap official page blocked; HOSE not found |  |  | not_found | Do not infer |

Official source used for FPT:
`https://fpt.com/en/ir/information-disclosures` (checked 2026-06-12).

## Findings

- FPT rows are not early versus official disclosure evidence.
- FPT 2025 annual rows are within 1 day of the official IR update date.
- FPT 2026 Q1 rows are 4 days after the official IR update date, which is
  conservative for PIT use but not an exact match.
- VCI rows could not be validated in this pass because official disclosure
  evidence was not accessible/found.
- No `before_official` red flag was observed in the validated FPT rows.

Sample evidence supports `publicDate` as a candidate PIT availability field, but
sample size is too small for full confirmation.

## Risk Assessment

`publicDate` remains unconfirmed. The main unresolved risks are:

- FPT-only official matches may not generalize to VCI or other issuers.
- Company IR "updated" dates may differ from exchange filing timestamps.
- VCI official evidence was blocked or not found in this tiny pass.
- Older periods were not cross-checked against official filing records.

## Gate Status

- Mapping coverage gate remains below 95%: BS 89.7%, IS 94.5%, CF 87.6%.
- DB write remains blocked.
- Backtest remains blocked.
- QuestDB schema not designed.
- Full-history FA fetch not implemented.
- `publicDate` PIT semantics remain unconfirmed.

## Next Action

Broaden the manual PIT check to exchange records for VCI plus at least one more
HOSE issuer. Confirm that `publicDate` is never before the official disclosure
date before using it as a PIT availability field.
