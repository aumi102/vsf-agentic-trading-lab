---
title: strategy_contract_schema
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Contract Schema

## Purpose

A strategy contract freezes research assumptions before execution. No contract
means no real backtest; mentor approval is required. Validation does not execute
a strategy or imply expected performance.

Every field below is required. For an `approved` contract, decisive values must
not be empty or contain `PENDING`, `placeholder`, `TBD`, `TODO`, or `N/A`.
Placeholder-bearing approved contracts are blocked with
`placeholder_value_present:<field>`. Pending templates remain `not_ready`.

## Fields

| Field | Requirement |
|---|---|
| `strategy_id` | Stable explicit identifier. |
| `strategy_family` | Mentor-reviewed baseline family. |
| `universe` / `symbols` | Universe policy and explicit small symbol list. |
| `date_range` | ISO `start` and `end`. |
| `price_basis` | Must be `adjusted_ohlc`. |
| `feature_inputs` | Inputs and lookbacks available before execution. |
| `entry_rule` / `exit_rule` | Frozen deterministic rules. |
| `rebalance_rule` | Timing and frequency. |
| `execution_price` | Adjusted-price execution convention. |
| `transaction_cost_bps` / `slippage_bps` | Explicit non-negative assumptions. |
| `exchange` / `slippage_band_bps` | HOSE/HSX 700; UPCOM 1500 maximum band. |
| `position_sizing` / `risk_rule` | Frozen sizing and risk behavior. |
| `max_holding_period` | Explicit duration or documented absence. |
| `lookahead_policy` | Rule preventing future information use. |
| `data_quality_gates` | Adjusted readiness, provenance, and coverage gates. |
| `expected_outputs` | Research-only report contract. |
| `caveats` | Data, universe, and execution limitations. |
| `mentor_approval_status` | `pending`, `approved`, or `rejected`. |

Run `python scripts/validate_strategy_contract.py --contract path/to/strategy_contract.json`.
Only an approved and otherwise valid contract returns `status=ok`.
