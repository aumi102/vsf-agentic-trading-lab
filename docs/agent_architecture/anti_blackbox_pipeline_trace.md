# Anti-blackbox pipeline trace

Mentor feedback #2: knowing *which tool was called* is not enough. For every demo
action the UI/API must show **where we are in the pipeline, which agent/sub-agent is
handling the request, what it decided, why, and what caveats apply**.

`src/trading_agent/observability/pipeline_trace.py` builds a structured,
JSON-serializable trace for every demo action and `/api/demo/ask`. It exposes only
concise *decision reasons* — never hidden chain-of-thought or private model reasoning.

## Trace schema

```jsonc
{
  "request_id": "…",
  "user_query": "compare backtest strategies FPT",
  "domain": "market_summary|financial_report|backtest|event_news|validation|system",
  "pipeline_position": {
    "layer": "agent_answer",
    "path": ["source","raw","bronze","silver","gold","signal","backtest","validation","agent_answer"],
    "current_step": "backtest",
    "upstream_tables": ["backtest_runs","backtest_metrics"]
  },
  "agents": [
    {
      "agent_name": "RouterAgent",
      "role": "classify user intent and choose the allowed tool group",
      "decision": "route -> backtest",
      "reason": "Classified as backtest because the query contains 'compare'; persisted rows are used (no live Backtrader).",
      "allowed_tools": ["get_latest_backtest_metrics","get_backtest_strategy_comparison","…"],
      "rejected_tools": ["run_ma_backtest","run_backtrader","run_backtrader_questdb_persist"],
      "caveats": []
    },
    {
      "agent_name": "BacktestAgent",
      "role": "read persisted Backtrader research results; never run live Backtrader",
      "decision": "answered using get_backtest_strategy_comparison",
      "reason": "Used persisted backtest rows because the agent runtime must not run live Backtrader.",
      "tool_calls": [ … ]
    }
  ],
  "final_answer_basis": { "source": "QuestDB", "tables": ["…"], "query_mode": "REST", "caveats": ["…"] },
  "next_actions": [ … ]
}
```

## How it is built

Two agents are always represented:

1. **RouterAgent** — classifies the query into a domain and picks the allowed tool
   group. The domain comes from the same rule-classifier the agent actually uses
   (`questdb_agent_service.classify` → `INTENT_TO_DOMAIN`), so the trace matches real
   routing rather than re-deriving it.
2. **The domain specialist** — `MarketDataAgent`, `FinancialReportAgent`,
   `BacktestAgent`, `EventNewsAgent`, `ValidationAgent`, or `SystemAgent`. Its
   `tool_calls` are the tools that actually ran (from the agent result), and its
   `decision`/`reason` summarize what it did.

`trace_from_rule_result(query, result, query_mode)` takes the rule agent's structured
result (intent, tool_calls, status, caveats) and assembles the full trace.
`pipeline_position.upstream_tables` and `final_answer_basis.tables` are derived from
the tools that ran (e.g. `get_backtest_strategy_comparison` → `backtest_runs`,
`backtest_metrics`).

## Allowed vs rejected tools (the guardrails, made visible)

| domain | allowed (examples) | rejected (examples) |
|---|---|---|
| market_summary | `get_symbol_summary`, `get_latest_ohlcv`, `get_latest_signal` | `run_ma_backtest`, `run_backtrader` |
| financial_report | `get_latest_financial_report`, `get_financial_report_summary` | `get_latest_ohlcv`, `get_symbol_summary` |
| backtest | `get_latest_backtest_metrics`, `get_backtest_strategy_comparison` | `run_ma_backtest`, `run_backtrader`, `run_backtrader_questdb_persist` |
| event_news | `get_symbol_event_news` | `get_latest_ohlcv`, `get_symbol_summary`, `get_latest_financial_report` |

These two facts are the heart of the anti-blackbox guarantee for the mentor:

- **Backtest** answers reject live-Backtrader tools and use persisted rows.
- **Event/news** answers reject market-price tools, so a missing symbol returns
  `unavailable` rather than an OHLCV proxy (e.g. VNM events → `status=unsupported`).

## Decision reasons are concise, not chain-of-thought

By design the `reason` strings are short, auditable statements — e.g.:

- "Classified as backtest because the query contains 'compare'; persisted rows are
  used (no live Backtrader)."
- "Event/news data is unavailable; OHLCV proxy is forbidden, so the answer is
  'unavailable'."
- "Used persisted backtest rows because the agent runtime must not run live
  Backtrader."

No private/hidden reasoning is exposed.

## Where it shows up

- `GET /api/demo/market|fa|backtest|events/{symbol}` and `POST /api/demo/ask` each
  return a `trace` field.
- `GET /api/demo/trace/examples` returns full traces for each domain.
- The `/demo` console renders the pipeline path (active step highlighted), each agent
  with its decision/reason, allowed/rejected tool chips, tool calls, the final basis
  (source + query_mode + tables), caveats, and the next recommended action.
