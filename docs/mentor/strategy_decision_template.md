---
title: strategy_decision_template
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Decision Template

Complete and approve this before a real adjusted-basis strategy run.
A strategy is not approved until this template has mentor-approved values.

| Field | Mentor-approved value |
|---|---|
| `strategy_id` | |
| strategy type (`momentum`, `moving_average`, `breakout`, `mean_reversion`, `rule_based_baseline`) | |
| universe | |
| date range | |
| price basis | `adjusted_ohlc` |
| entry rule | |
| exit rule | |
| rebalance rule/frequency | |
| execution price (`adjusted_close`, `next_adjusted_open`, approved placeholder) | |
| transaction cost bps | |
| slippage bps | |
| exchange band | |
| position sizing | |
| maximum holding period | |
| risk stop | |
| validation gates | |
| expected caveats | |
| mentor/reviewer | |
| decision date | |
| approval status | `pending` |

The strategy must remain small-symbol and gated until separately approved.
Outputs are research diagnostics, not investment advice.
