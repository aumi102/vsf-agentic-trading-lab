---
title: mentor_demo_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Demo Report

**Date:** 2026-06-16
**Branch at time of run:** `phase/mentor-demo-package` (based on main `0ec2a7c`)
**Store:** `data/demo/mvp_trading_agent.sqlite` (gitignored, not committed)

This report documents a live run of all demo scenarios. It is not a claim of production readiness or investment usefulness.

---

## Build

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

| Field | Value |
|---|---|
| Available local payloads | FPT, REE, SAM, VCB, VNM |
| Symbols loaded | FPT, VCB, VNM |
| daily_prices rows | 14,079 |
| feature_snapshots rows | 14,071 |
| signals rows | 14,071 |
| securities rows | 3 |
| OHLC fail rows excluded | 8 |
| Date range: FPT | 2006-12-13 → 2026-06-05 (4,852 rows) |
| Date range: VNM | 2006-05-18 → 2026-06-05 (5,000 rows) |
| Date range: VCB | 2009-06-30 → 2026-06-05 (4,227 rows) |
| quality_status: daily_prices | warn (adjustment_status=unknown on all rows) |
| quality_status: securities | pass |

---

## Demo Runs

### market_brief — direct symbol

```bash
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
```

| Field | Value |
|---|---|
| Exit code | 0 |
| status | ok |
| symbol resolved | FPT |
| Latest date | 2026-06-05 |
| Close | 75,000.00 |
| Return 1D / 5D / 20D | −1.45% / +4.75% / +5.75% |
| MA20 / MA50 | 73,173.29 / 73,673.10 |
| Signal | HOLD (`MIXED_OR_NEUTRAL_MOMENTUM`) |
| Risk flag | `normal_20d_volatility` |
| Tool trace | market_data → features → signal → risk → report (5 tools) |
| not_financial_advice | true |

---

### market_brief — natural-language query

```bash
python scripts/run_agent_demo.py --scenario market_brief --query "FPT hôm nay thế nào?"
```

| Field | Value |
|---|---|
| Exit code | 0 |
| status | ok |
| Symbol extracted | FPT (deterministic; no LLM call) |
| Answer | identical to direct-symbol run |

---

### risk_check — VCB

```bash
python scripts/run_agent_demo.py --scenario risk_check --symbol VCB
```

| Field | Value |
|---|---|
| Exit code | 0 |
| status | ok |
| Latest date | 2026-06-05 |
| Risk flags | `normal_20d_volatility`, `thin_recent_volume` |
| Risk quality_status | warn |
| Tool trace | market_data → features → signal → risk → report (5 tools) |
| not_financial_advice | true |

---

### compare — three known symbols

```bash
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
```

| Exit | 0 |
|---|---|
| status | ok |
| Row count | 3 (input order preserved) |

Comparison table from output:

| Symbol | Status | Date | Close | R1D | R5D | R20D | Signal | Risk Flags |
|---|---|---|---|---|---|---|---|---|
| FPT | ok | 2026-06-05 | 75,000 | −1.45% | +4.75% | +5.75% | HOLD | normal_20d_volatility |
| VNM | ok | 2026-06-05 | 58,400 | −0.34% | −1.35% | −4.11% | SELL | normal_20d_volatility |
| VCB | ok | 2026-06-05 | 61,700 | −0.80% | −0.48% | +1.65% | HOLD | normal_20d_volatility, thin_recent_volume |

_Table is for demo only. Not ranked as investment advice. Signals are rule-based, not forward-looking._

---

### compare — one missing symbol

```bash
python scripts/run_agent_demo.py --scenario compare --symbols FPT,HPG
```

| Field | Value |
|---|---|
| Exit code | 0 |
| status | ok (FPT present) |
| FPT row | ok, HOLD |
| HPG row | not_found (not in demo store) |
| Traceback | none |

---

### compare — all symbols missing

```bash
python scripts/run_agent_demo.py --scenario compare --symbols HPG,XYZ
```

| Field | Value |
|---|---|
| Exit code | 1 |
| status | not_found |
| HPG row | not_found |
| XYZ row | not_found |
| Traceback | none |

---

## Summary Table

| Command | Exit | Status | Key result |
|---|---:|---|---|
| `market_brief --symbol FPT` | 0 | ok | HOLD, close 75000, 5-tool trace |
| `market_brief --query "FPT hôm nay thế nào?"` | 0 | ok | FPT resolved without LLM |
| `risk_check --symbol VCB` | 0 | ok | `normal_20d_volatility`, `thin_recent_volume` |
| `compare --symbols FPT,VNM,VCB` | 0 | ok | 3 rows, input order, signals differ per symbol |
| `compare --symbols FPT,HPG` | 0 | ok | FPT ok, HPG not_found, no traceback |
| `compare --symbols HPG,XYZ` | 1 | not_found | all rows missing, no traceback |

---

## Validation

| Check | Result |
|---|---|
| `python -m py_compile` (demo_runner, run_agent_demo) | OK |
| `pytest tests/test_agent_demo_runner.py -q` | 17 passed |
| `pytest -q` (full suite) | 781 passed |
| `git diff --check` | OK |
| Docusaurus build | SUCCESS |

---

## Generated Files — Not Committed

| File | Status |
|---|---|
| `data/demo/mvp_trading_agent.sqlite` | gitignored via `data/` |
| `website/build/` | gitignored via `website/.gitignore` |
| `.pytest_tmp*` | gitignored |
| `__pycache__/` | gitignored |

---

## Limitations

- Data is saved Vietcap IQ gap-chart payloads, not an official exchange feed.
- Latest observation: 2026-06-05. No real-time update.
- Corporate-action adjustment status is unknown on all rows.
- No backtest, no broker execution, no production DB write.
- No LLM reasoning — answers are deterministic rule-based outputs.
- Not financial advice.
