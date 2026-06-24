# Validation gate latest report

**OVERALL_STATUS:** `WARN`

| Gate | Status | Blocking | Caveats | Recommended fix |
|---|---|---:|---|---|
| `market_table_coverage` | `PASS` | `False` |  | Run approved OHLCV ingestion only if market data is genuinely missing. |
| `feature_signal_parity` | `PASS` | `False` |  | Rebuild feature_snapshots and signals from daily_prices. |
| `adjusted_ohlc_gate` | `WARN` | `False` | adjusted close appears unverified or equal to raw for current rows | Verify adjusted OHLC against corporate-action/vendor adjustment evidence. |
| `exchange_metadata_gate` | `PASS` | `False` |  | Fill exchange metadata so price-band guard can pass. |
| `fa_tables_gate` | `PASS` | `False` |  | Run FA ingestion in run-scoped mode and verify questdb_fa_status.py. |
| `fa_mapping_gate` | `WARN` | `False` | FA metric mapping exists but consensus coverage remains below production threshold<br>FA fact rows still carry metric_mapping_unverified quality_status; tools enrich names at read time only | Build and verify Vietcap metric-code mapping before claiming semantic FA metric names. |
| `backtest_tables_gate` | `PASS` | `False` |  | Run scripts/run_backtrader_questdb_persist.py for the demo symbols. |
| `backtest_execution_assumptions_gate` | `WARN` | `False` | slippage_bps is 0; slippage remains a simple demo assumption | Fill exchange metadata and rerun persisted backtests; tune slippage assumptions after mentor approval. |
| `event_news_gate` | `PASS` | `False` | event/news demo coverage is partial; missing VNM, HPG | Expand event/news sources only after source schema and PIT semantics are stable. |
| `agent_guardrail_gate` | `PASS` | `False` |  | Inspect run_mentor_demo_readiness.py output and fix routing/credential issues. |
| `docker_packaging_gate` | `PASS` | `False` |  | Keep image build in CI or demo preflight. |

## Evidence

### market_table_coverage

```json
{
  "daily_prices_rows": 4388880,
  "symbols": 1556,
  "latest_trade_date": "2026-06-22"
}
```

### feature_signal_parity

```json
{
  "daily_prices_rows": 4388880,
  "feature_snapshots_rows": 4388880,
  "signals_rows": 4388880,
  "daily_latest": "2026-06-22",
  "feature_latest": "2026-06-22",
  "signal_latest": "2026-06-22",
  "row_tolerance": 4388
}
```

### adjusted_ohlc_gate

```json
{
  "adjusted_columns_present": [
    "adjusted_close",
    "adjusted_high",
    "adjusted_low",
    "adjusted_open"
  ],
  "source_verification_status": "source_adjustment_unverified_raw_equivalent",
  "adjusted_close_equals_close_rows": 4388880,
  "total_rows": 4388880,
  "raw_equivalent_ratio": 1.0,
  "adjusted_price_missing_warn_rows": 4388880,
  "non_1_factor_rows": 0,
  "corr_high_adjusted_high": 1.0,
  "corr_close_adjusted_close": 1.0,
  "max_factor_application_error": 0.0,
  "internal_consistency_status": "pass"
}
```

### exchange_metadata_gate

```json
{
  "demo_symbols_checked": [
    "FPT",
    "VNM",
    "HPG"
  ],
  "demo_symbol_exchanges": {
    "FPT": "HOSE",
    "VNM": "HOSE",
    "HPG": "HOSE"
  },
  "demo_price_band_status": {
    "FPT": "price_band_guard_pass",
    "VNM": "price_band_guard_pass",
    "HPG": "price_band_guard_pass"
  },
  "missing_demo_symbols": [],
  "unsupported_demo_symbols": [],
  "total_securities": 1556,
  "exchange_non_null_count": 1556,
  "exchange_coverage_pct": 100.0,
  "broader_missing_exchange_count": 0
}
```

### fa_tables_gate

```json
{
  "row_counts": {
    "fa_balance_sheet": 862586,
    "fa_income_statement": 474039,
    "fa_cash_flow": 581400,
    "fa_notes": 557427
  },
  "symbol_counts": {
    "fa_balance_sheet": 53,
    "fa_income_statement": 53,
    "fa_cash_flow": 53,
    "fa_notes": 53
  },
  "latest_complete_run_id": "20260624T044856Z",
  "latest_run_status": "complete"
}
```

### fa_mapping_gate

```json
{
  "quality_status_breakdown": {
    "fa_balance_sheet": {
      "metric_mapping_unverified": 862586
    },
    "fa_income_statement": {
      "metric_mapping_unverified": 474039
    },
    "fa_cash_flow": {
      "metric_mapping_unverified": 581400
    },
    "fa_notes": {
      "metric_mapping_unverified": 557427
    }
  },
  "metric_mapping_unverified_rows": 2475452,
  "fa_metric_mapping_table_exists": true,
  "fa_metric_mapping_rows": 1957,
  "fa_metric_mapping_consensus_rows": 1858,
  "mapping_coverage": {
    "fa_balance_sheet": {
      "fact_distinct_metric_codes": 331,
      "mapped_consensus_metric_codes": 229,
      "mapped_consensus_code_pct": 69.18429003021149
    },
    "fa_income_statement": {
      "fact_distinct_metric_codes": 181,
      "mapped_consensus_metric_codes": 153,
      "mapped_consensus_code_pct": 84.5303867403315
    },
    "fa_cash_flow": {
      "fact_distinct_metric_codes": 225,
      "mapped_consensus_metric_codes": 177,
      "mapped_consensus_code_pct": 78.66666666666666
    },
    "fa_notes": {
      "fact_distinct_metric_codes": 1402,
      "mapped_consensus_metric_codes": 1299,
      "mapped_consensus_code_pct": 92.65335235378032
    }
  },
  "minimum_consensus_code_coverage_pct": 69.18429003021149
}
```

### backtest_tables_gate

```json
{
  "row_counts": {
    "backtest_runs": 36,
    "backtest_metrics": 36,
    "backtest_equity_curve": 53964,
    "backtest_trades": 400
  },
  "symbols": 3,
  "strategies": 3
}
```

### backtest_execution_assumptions_gate

```json
{
  "assumption_breakdown": [
    {
      "commission": 0.001,
      "slippage_bps": 0.0,
      "price_band_status": "price_band_guard_pass",
      "rows": 9
    },
    {
      "commission": 0.001,
      "slippage_bps": 5.0,
      "price_band_status": "price_band_guard_pass",
      "rows": 9
    },
    {
      "commission": 0.001,
      "slippage_bps": 10.0,
      "price_band_status": "price_band_guard_pass",
      "rows": 9
    },
    {
      "commission": 0.001,
      "slippage_bps": 15.0,
      "price_band_status": "price_band_guard_pass",
      "rows": 9
    }
  ]
}
```

### event_news_gate

```json
{
  "tables_present": {
    "event_news_raw_payloads": true,
    "event_news_items": true
  },
  "row_counts": {
    "event_news_raw_payloads": 20,
    "event_news_items": 20
  },
  "symbol_counts": {
    "event_news_raw_payloads": 1,
    "event_news_items": 1
  },
  "demo_symbol_event_counts": {
    "FPT": 20
  },
  "agent_latest_news_exit_code": 0,
  "agent_latest_news_uses_event_tool": true,
  "agent_latest_news_uses_ohlcv_proxy": false
}
```

### agent_guardrail_gate

```json
{
  "exit_code": 0,
  "final_status": "PASS"
}
```

### docker_packaging_gate

```json
{
  "required_files": {
    "Dockerfile": true,
    "docker-compose.yml": true,
    ".dockerignore": true
  },
  "compose_config_exit_code": 0,
  "docker_server_version_exit_code": 0,
  "docker_server_version": "29.2.0",
  "docker_build_exit_code": 0
}
```
