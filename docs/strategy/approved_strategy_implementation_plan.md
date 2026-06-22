---
title: approved_strategy_implementation_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Approved Strategy Implementation Plan

After the mentor call:

1. replace pending template values with explicit mentor decisions;
2. validate the contract and require `status=ok`;
3. implement one selected adapter only;
4. test lookahead policy and feature timing;
5. test that prepared adjusted OHLC is the only price basis;
6. test symbol coverage and frozen cost/slippage assumptions;
7. review deterministic signal intents and caveats;
8. only then consider a separately approved Backtrader research scaffold.

The candidate families are catalogued in the read-only
[strategy adapter registry](./strategy_adapter_registry.md). Enabling exactly one
candidate adapter (step 3) flips that family's registry status in a later PR;
until then only `noop` is enabled. See the
[mentor strategy selection flow](./mentor_strategy_selection_flow.md).

Optimization, full VN100, live fetch, broker execution, production use,
performance claims, and investment advice remain excluded.
