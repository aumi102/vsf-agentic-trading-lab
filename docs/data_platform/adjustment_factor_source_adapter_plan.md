---
title: adjustment_factor_source_adapter_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjustment Factor Source Adapter Plan

## Purpose

This is the first adapter interface for turning verified adjusted-close or
corporate-action payloads into `AdjustmentFactorRecord` objects. It is
fixture-only in this PR and does not approve any live source.

## Interface

The adapter exposes pure parser functions:

- `parse_adjustment_factor_payload(...)`;
- `build_factor_records_from_adjusted_close_payload(...)`;
- `build_factor_records_from_corporate_action_payload(...)`.

Usable records must include `symbol`, `trade_date`, `factor > 0`, `source_id`,
`raw_path`, `method`, `status=ok`, and empty `reasons`.

## Fixtures

Tiny synthetic fixtures live under `tests/fixtures/adjustment_factors/`.
They are not real market data and are only used to prove the adapter contract.

## Relationship To Factor Application

The generated records are compatible with
`scripts/apply_adjustment_factors.py`. Tests verify this path:

```text
fixture payload -> factor records -> local factor application -> adjusted readiness pass
```

## Boundaries

- No live network request.
- No full-universe crawl.
- No DB mutation in the adapter.
- No adjusted OHLC population unless records are explicitly passed to the local
  factor application module in a test or approved local run.
- No Backtrader strategy work.
- No Docker/scheduler implementation.
- No production-readiness or investment-advice claim.

## Next Step

Use this adapter contract to evaluate an approved live/vendor adjusted-close or
corporate-action endpoint on a small explicit symbol set.
