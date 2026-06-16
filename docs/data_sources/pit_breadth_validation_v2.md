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

Controls remain FPT and VCI. The bounded sample now tracks eight additional
candidate issuers across six additional sectors. Only FPT, VCI, and HPG are
comparable.

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
| ACB | Bank | official event found | official event found | ACB fa-direct returned 403; no publicDate comparison row |
| DGC | Materials/chemical | unresolved | official event found | DGC fa-direct returned 403; no publicDate comparison row |

BVH was replaced by KDH because the bounded official BVH financial-report URL
returned 404 during source discovery; KDH preserved sector diversity.

## Live Execution

Plan run: `20260614T130355Z`. Execute run: `20260614T130404Z`.
Closeout official-source runs: `20260616T014621Z`, `20260616T014940Z`, and
`20260616T015329Z`. Closeout Vietcap fa-direct runs: ACB
`20260616T015509Z`, DGC `20260616T015532Z`.

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

ACB official year pages exposed consolidated audited FY2025 (`2026-02-27`) and
consolidated Q1 2026 (`2026-04-23`) statements. DGC official IR exposed Q1 2026
consolidated and separate statement entries dated `2026-04-28`. Single
BALANCE_SHEET fa-direct probes for ACB and DGC both returned HTTP 403
`text/html` with no JSON payload, so no `publicDate` comparison rows are
available.

HPG comparison rows used a single bounded Vietcap IQ BALANCE_SHEET direct
probe (run_id=`20260614T134035Z`). One payload serves both FY2025 and Q1 2026.

## Validator Result

Committed sample: `docs/data_sources/pit_breadth_validation_v2_samples.csv`.

| Metric | Count |
|---|---:|
| Target issuers | 10 |
| Target sectors | 8 |
| Statement/target rows | 23 |
| Credible comparable statement rows | 10 |
| Credible unique official evidence events | 6 |
| Comparable issuers | 3 |
| Comparable sectors | 3 |
| Annual evidence events | 3 |
| Quarterly evidence events | 3 |
| blocked rows | 3 |
| network_error rows | 2 |
| Unresolved/not-comparable rows | 13 |
| Red flags | 0 |

Date-delta distribution for credible events: 1 exact, 3 near matches, 2
Vietcap-after-official events, and 0 Vietcap-before-official red flags. Statement
rows are not independent evidence events.

Final breadth sample status: `pit_inconclusive`. The prior FPT/VCI control CSV
still returns `pit_supported_small_sample`.

## Limitations

The minimum closeout threshold was not reached. The breadth gate requires at
least 6 comparable issuers, 5 comparable sectors, 12 credible unique evidence
events, annual and quarterly representation, credible evidence ratio >=0.80, and
zero red flags. This pass remains at 3 comparable issuers, 3 comparable sectors,
and 6 credible unique events because new ACB and DGC official events lack usable
Vietcap publicDate payloads.

Evidence is date-level only. No secondary aggregator source populates canonical
dates. Mapping remains below 95% (BS 89.7%, IS 94.5%, CF 87.6%). QuestDB schema
is not implemented. Full-history FA fetch is not implemented. DB write and
backtest remain blocked.

## Next Gate

Resolve official access or detail endpoints for more issuers, then add bounded
Vietcap publicDate comparison rows for the newly verified official events.
