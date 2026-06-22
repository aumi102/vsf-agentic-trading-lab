---
title: strategy_adapter_interface
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Adapter Interface

## Inputs

- mentor-approved strategy contract JSON whose validator returns `status=ok`;
- prepared adjusted OHLC input JSON with ready status, covering every contract
  symbol, and rows. Extra represented symbols are allowed but ignored; output
  rows are emitted only for contract symbols.

## Output Contract

- `status`, `adapter_stage`, `strategy_id`, and `price_basis`;
- requested `symbols`;
- `signal_intent_rows` with symbol, datetime, action, and reason;
- `reasons`, `caveats`, and `not_financial_advice=true`.

Allowed intent actions are `NO_SIGNAL`, `ENTER_LONG_INTENT`, and
`EXIT_LONG_INTENT`. These are internal research intents, not trades or
recommendations.

## Forbidden

Adapters must not emit buy/sell/hold recommendation wording, trades, PnL,
equity, returns, broker actions, or Backtrader execution. Raw OHLC cannot replace
the prepared adjusted OHLC basis. PR #56 implements only `NO_SIGNAL` as an
interface preview.
