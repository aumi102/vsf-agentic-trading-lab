---
title: strategy_adapter_registry
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Strategy Adapter Registry

## Purpose

The registry is a static, read-only catalogue of strategy adapter families that
are candidate implementation targets. It records which families exist, their
status, and whether they are implemented and enabled. It runs no strategy,
fetches no data, and mutates nothing. The registry is versioned
(`registry_version=strategy_adapter_registry_v1`).

## Families

| Family | Status | Implemented | Enabled |
|---|---|---|---|
| `noop` | `interface_preview` | yes | yes |
| `moving_average` | `pending_mentor_approval` | no | no |
| `momentum` | `pending_mentor_approval` | no | no |
| `breakout` | `pending_mentor_approval` | no | no |
| `mean_reversion` | `pending_mentor_approval` | no | no |

## Gating

No adapter may run unless **all** of the following hold:

- the strategy contract validates `status=ok`;
- the family is registered;
- the family is enabled;
- the prepared adjusted-OHLC input is ready.

Today only `noop` is enabled, as an interface preview. Every other family stays
disabled and pending a mentor-approved contract. The registry does not wire into
the adapter execution path yet; wiring follows the mentor's family selection.

## Boundaries

No real strategy execution, no Backtrader, no optimizer, no full VN100, no
performance metrics, no DB mutation, no network fetch, and no investment advice.
