---
title: controlled_factor_source_verification
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Controlled Factor Source Verification

## Purpose

This is a controlled, no-network-by-default verification layer for evaluating
adjusted-price or corporate-action factor evidence on a small explicit symbol
set (default `FPT`, `VNM`, `VCB`). It confirms that a payload can produce
usable, provenance-backed factor records before any ETL adjusted-OHLC
population. It does not perform full-universe crawling and does not populate
adjusted OHLC from unverified data.

PR #37 created this controlled local verification layer; it did not wire a live
source or populate adjusted OHLC.

## Relation To The Source Adapter (PR #36)

PR #36 added the fixture-only adjustment-factor source adapter
(`src/trading_agent/ingestion/sources/adjustment_factor_source.py`). This
verification layer reuses `parse_adjustment_factor_payload(...)` from that
adapter and adds:

- `plan_factor_source_verification(...)` — plan-only candidate steps, blocked
  reasons, and guardrails;
- `verify_factor_source_payload(...)` — parses a local payload and reports
  usable / missing / invalid factor records for the requested symbols.

## No-Network Default

- `allow_network_default` is `false`; the plan blocks `allow_network` because no
  live/vendor source verification is implemented yet.
- `verify_factor_source_payload(...)` reads a local payload only; it never makes
  a network request and never mutates a DB.

## Local Payload Verification Commands

```bash
python scripts/verify_factor_source_payload.py \
  --payload tests/fixtures/adjustment_factors/adjusted_close_payload.json \
  --method adjusted_close_ratio \
  --source-id fixture:adjusted_close \
  --raw-path tests/fixtures/adjustment_factors/adjusted_close_payload.json \
  --symbols FPT

python scripts/verify_factor_source_payload.py \
  --payload tests/fixtures/adjustment_factors/corporate_action_factor_payload.json \
  --method corporate_action_derived \
  --source-id fixture:corporate_action \
  --raw-path tests/fixtures/adjustment_factors/corporate_action_factor_payload.json \
  --symbols FPT
```

The CLI exits `0` only when there is at least one usable factor record for the
requested symbols. It exits `1` cleanly (no traceback) for a missing payload,
invalid JSON, an unknown method, or no usable records.

## Required Provenance

A usable factor record must carry `source_id`, `raw_path`, and `method`, plus a
positive `factor`, `symbol`, `trade_date`, and `status=ok` with empty `reasons`.
Factor provenance stays separate from raw OHLC source lineage.

## Configuration

`configs/ingestion/verified_factor_source_check_mvp.json` defines the default
symbols, `max_symbols_per_check = 3`, `allow_network_default = false`, candidate
methods (`adjusted_close_ratio`, `corporate_action_derived`), and required
provenance.

## Limitations

- No live/vendor source is wired in yet.
- No full-universe crawl.
- No adjusted OHLC population from this layer.
- No Backtrader/VN100 unblock.
- No Docker/scheduler.
- No production-readiness or investment-advice claim.

## Next Step

Mentor policy is confirmed in
`docs/data_platform/confirmed_adjusted_price_policy.md`: adjusted price is
mandatory, full OHLC must be adjusted, VN100 uses the current list, transaction
cost should be researched, and slippage must stay within HSX/HOSE +/-7% and
UPCoM +/-15%.

The next step is implementation verification of adjusted-price or factor
evidence. Verify a small explicit symbol set, then run the local factor
application path and confirm adjusted readiness before any Backtrader VN100 work.
