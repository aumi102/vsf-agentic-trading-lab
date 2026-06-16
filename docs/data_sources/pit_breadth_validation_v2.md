---
title: pit_breadth_validation_v2
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# PIT Breadth Validation v2

## Purpose

Expand official-source-first PIT validation beyond FPT and VCI while preserving
raw evidence, unique-event grouping, and conservative gate language. This is a
draft breadth pass: it does not unblock DB writes, backtests, full-history FA
fetches, or full PIT confirmation.

## Sample Design

Controls remain FPT and VCI. The new bounded sample targeted six issuers across
five additional sectors.

| Symbol | Sector | FY2025 | Q1 2026 | Status |
|---|---|---|---|---|
| FPT | Technology | control | control | comparable PIT evidence |
| VCI | Securities | control | control | comparable PIT evidence |
| HPG | Industrial/materials | comparable PIT evidence | comparable PIT evidence | Vietcap publicDate comparison rows committed |
| KDH | Real estate | unresolved | official event found | KDH fa-direct returned 403; no publicDate comparison row |
| MWG | Retail | unresolved | unresolved | official page lacked usable date-bound match |
| VCB | Bank | network_error | network_error | bounded request timed out; no access-control block observed |
| SSI | Securities | unresolved | unresolved | parent page only in bounded request |
| VNM | Consumer | unresolved | unresolved | calendar page only in bounded request |

BVH was replaced by KDH because the bounded official BVH financial-report URL
returned 404 during source discovery; KDH preserved sector diversity.

## Live Execution

Plan run: `20260614T130355Z`. Execute run: `20260614T130404Z`.

The execute run used concurrency 1, bounded requests, honest project User-Agent,
TLS verification, raw capture, metadata capture, checkpointing, and per-target
parse summaries. Live raw and bronze payloads remain ignored under `data/`.

Verified new official-only events with Vietcap publicDate comparison:

| Symbol | Period | Official date | Vietcap publicDate | Delta | Match status |
|---|---|---|---|---:|---|
| HPG | FY2025 | 2026-03-27 | 2026-03-30 | +3 | near_match_1_3_days |
| HPG | Q1 2026 | 2026-04-29 | 2026-05-04 | +5 | vietcap_after_official |

KDH Q1 2026 official date `2026-04-29` remains `not_comparable`. A single
KDH `BALANCE_SHEET` fa-direct probe (run_id=`20260616T011504Z`) returned HTTP
403 `text/html` with no JSON payload, so there is no explicit `yearReport=2026`,
`lengthReport=1`, or `publicDate` to compare. The official KDH title is
parent-company-only (`Cong ty Me`), and no basis-compatible Vietcap row was
available from this pass.

HPG comparison rows used a single bounded Vietcap IQ BALANCE_SHEET direct
probe (run_id=`20260614T134035Z`). One payload serves both FY2025 and Q1 2026.

## Validator Result

Committed sample: `docs/data_sources/pit_breadth_validation_v2_samples.csv`.

| Metric | Count |
|---|---:|
| Target issuers | 8 |
| Target sectors | 7 |
| Statement/target rows | 20 |
| Credible comparable statement rows | 10 |
| Credible unique official evidence events | 6 |
| Comparable issuers | 3 |
| Comparable sectors | 3 |
| Annual evidence events | 3 |
| Quarterly evidence events | 3 |
| network_error rows | 2 |
| Unresolved/not-comparable rows | 10 |
| Red flags | 0 |

Date-delta distribution for credible events: 1 exact, 3 near matches, 2
Vietcap-after-official events, and 0 Vietcap-before-official red flags. Statement
rows are not independent evidence events.

Final breadth sample status: `pit_inconclusive`. The prior FPT/VCI control CSV
still returns `pit_supported_small_sample`.

## Limitations

The minimum closeout threshold was not reached. New official canonical evidence
covered 2 new issuers, 2 new sectors, and 3 new events; the threshold requires
at least 4 new issuers, 4 sectors, and 8 new canonical official events.

Evidence is date-level only. No secondary aggregator source populates canonical
dates. Mapping remains below 95% (BS 89.7%, IS 94.5%, CF 87.6%). QuestDB schema
is not implemented. Full-history FA fetch is not implemented. DB write and
backtest remain blocked.

## Next Gate

Resolve official access or detail endpoints for more issuers, then add bounded
Vietcap publicDate comparison rows for the newly verified official events.
