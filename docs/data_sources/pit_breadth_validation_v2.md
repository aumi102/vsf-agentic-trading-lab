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
| HPG | Industrial/materials | official event found | official event found | no committed Vietcap comparison row |
| KDH | Real estate | unresolved | official event found | no committed Vietcap comparison row |
| MWG | Retail | unresolved | unresolved | official page lacked usable date-bound match |
| VCB | Bank | blocked | blocked | bounded request failed |
| SSI | Securities | unresolved | unresolved | parent page only in bounded request |
| VNM | Consumer | unresolved | unresolved | calendar page only in bounded request |

BVH was replaced by KDH because the bounded official BVH financial-report URL
returned 404 during source discovery; KDH preserved sector diversity.

## Live Execution

Plan run: `20260614T130355Z`. Execute run: `20260614T130404Z`.

The execute run used concurrency 1, bounded requests, honest project User-Agent,
TLS verification, raw capture, metadata capture, checkpointing, and per-target
parse summaries. Live raw and bronze payloads remain ignored under `data/`.

Verified new official-only events:

| Symbol | Period | Official date | Source |
|---|---|---|---|
| HPG | FY2025 | 2026-03-27 | company IR listing |
| HPG | Q1 2026 | 2026-04-29 | company IR listing |
| KDH | Q1 2026 | 2026-04-29 | company IR listing |

These are official date-level disclosures, but they are not counted as credible
PIT support until matching Vietcap publicDate observations are committed.

## Validator Result

Committed sample: `docs/data_sources/pit_breadth_validation_v2_samples.csv`.

| Metric | Count |
|---|---:|
| Target issuers | 8 |
| Target sectors | 7 |
| Statement/target rows | 20 |
| Credible comparable statement rows | 8 |
| Credible unique official evidence events | 4 |
| Comparable issuers | 2 |
| Comparable sectors | 2 |
| Annual evidence events | 2 |
| Quarterly evidence events | 2 |
| Blocked/manual/unresolved/not-comparable rows | 12 |
| Red flags | 0 |

Date-delta distribution for credible events: 1 exact, 2 near matches, 1
Vietcap-after-official event, and 0 Vietcap-before-official red flags. Statement
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
