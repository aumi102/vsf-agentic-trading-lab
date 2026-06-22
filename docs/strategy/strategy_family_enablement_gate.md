---
title: strategy_family_enablement_gate
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Family Enablement Gate

## Purpose

The enablement gate wires the read-only
[strategy adapter registry](./strategy_adapter_registry.md) into the
[strategy adapter preview](./strategy_adapter_interface.md). After a contract
validates `status=ok`, the adapter reads `strategy_family` and requires that the
family be **enabled** in the registry before any preview rows are produced. It is
an enablement gate only — it runs no strategy and computes no signals. **This gate
is not a strategy implementation.**

## Why only enabled families can run

A valid, mentor-approved contract is necessary but not sufficient. The family it
names must also be implemented and enabled in the registry. This keeps disabled
candidate families from running through the preview before the mentor selects
one and a future PR enables exactly one.

## Behaviour

- Contract readiness is checked first; a pending/rejected/invalid contract blocks
  with `contract_not_ready:<status>` before the family gate runs.
- The adapter then calls `validate_family_enabled(strategy_family)`:
  - unknown family blocks with `unknown_family:<family>`;
  - disabled family blocks with `strategy_family_not_enabled:<family>`.

## Current state

- Enabled family: **`noop`** only.
- Blocked families: `moving_average`, `momentum`, `breakout`, `mean_reversion`
  (all `pending_mentor_approval`).

So a valid approved contract with `strategy_family=noop` can pass the gate; an
otherwise-valid contract naming any other family blocks until enablement.

## Process to enable one real family later

1. Mentor selects the family.
2. The strategy contract is approved and validates `ok`.
3. A PR changes the registry status for **exactly one** family (implemented +
   enabled).
4. The real adapter is implemented in a separate PR.
5. Tests and caveats are reviewed before any execution.

## Boundaries

No real strategy execution, no Backtrader, no optimizer, no full VN100, no
PnL/equity/returns, no DB mutation, no network fetch, and no investment advice.
