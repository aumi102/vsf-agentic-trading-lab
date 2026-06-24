# Validation gate latest report

**OVERALL_STATUS:** `WARN`

| Gate | Status | Blocking | Caveats | Recommended fix |
|---|---|---:|---|---|
| `market_table_coverage` | `PASS` | `False` |  | Run approved OHLCV ingestion only if market data is genuinely missing. |
| `feature_signal_parity` | `PASS` | `False` |  | Rebuild feature_snapshots and signals from daily_prices. |
| `adjusted_ohlc_gate` | `WARN` | `False` | adjusted close appears unverified or equal to raw for current rows | Verify adjusted OHLC against corporate-action/vendor adjustment evidence. |
| `exchange_metadata_gate` | `WARN` | `False` | demo symbols missing exchange: FPT, VNM, HPG | Fill exchange metadata so price-band guard can pass. |
| `fa_tables_gate` | `PASS` | `False` |  | Run FA ingestion in run-scoped mode and verify questdb_fa_status.py. |
| `fa_mapping_gate` | `WARN` | `False` | FA metric mapping is still unverified; raw opaque metric evidence is usable but names may be blank | Build and verify Vietcap metric-code mapping before claiming semantic FA metric names. |
| `backtest_tables_gate` | `PASS` | `False` |  | Run scripts/run_backtrader_questdb_persist.py for the demo symbols. |
| `backtest_execution_assumptions_gate` | `WARN` | `False` | exchange metadata missing; price-band guard cannot be fully verified | Fill exchange metadata and rerun persisted backtests; tune slippage assumptions after mentor approval. |
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
  "adjusted_close_equals_close_rows": 4388880,
  "total_rows": 4388880,
  "adjusted_price_missing_warn_rows": 4388880,
  "corr_high_adjusted_high": 1.0,
  "corr_close_adjusted_close": 1.0
}
```

### exchange_metadata_gate

```json
{
  "securities_rows": 1556,
  "known_exchange_rows": 1548,
  "known_exchange_pct": 99.48586118251927,
  "demo_symbols": {
    "FPT": null,
    "HPG": null,
    "VNM": null
  }
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
  "metric_mapping_unverified_rows": 2475452
}
```

### backtest_tables_gate

```json
{
  "row_counts": {
    "backtest_runs": 9,
    "backtest_metrics": 9,
    "backtest_equity_curve": 13491,
    "backtest_trades": 100
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
      "price_band_status": "exchange_unknown_price_band_guard_not_fully_verified",
      "rows": 9
    }
  ]
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
