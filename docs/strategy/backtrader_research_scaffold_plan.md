---
title: backtrader_research_scaffold_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Backtrader Research Scaffold Plan

This is a plan, not an implementation. After mentor approval, a small adapter
may map the existing adjusted OHLC feed contract into Backtrader's datetime,
open, high, low, close, and volume lines. It must preserve adjusted-price basis,
symbol coverage, ordering, provenance references, and explicit costs.

The scaffold should accept one approved strategy contract, reject pending or
invalid contracts, and expose deterministic research outputs with caveats.
Execution timing and order semantics must match the approved contract and avoid
lookahead.

It must not add an optimizer, parameter sweep, full VN100, production service,
live network source, broker execution, real-money path, profitability guarantee,
or investment advice. Mentor approval and adjusted-readiness gates are required
before implementation starts.
