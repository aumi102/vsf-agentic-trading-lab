---
title: live_ohlcv_smoke_report
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Live OHLCV Smoke Report

## Scope

This report records the PR #26 closeout status for the controlled Vietcap IQ
gap-chart live adapter. The adapter is network-capable only when
`--mode live --allow-network` is passed. Default validation remains offline.

## Commands

Offline cached ingestion:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT,VNM,VCB --mode cached
```

Gated live path without network:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live
```

Optional one-symbol live smoke command:

```bash
python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live --allow-network --count-back 100
```

## Closeout Result

| Check | Result |
|---|---|
| Offline tests | pass |
| Cached ingestion | pass |
| Live without allow-network | pass / blocked as expected |
| Live with allow-network FPT countBack=100 | not run |
| Raw artifacts committed | no |
| Traceback | no |

The optional live smoke was not run in this closeout; offline monkeypatched
tests cover adapter behavior, raw payload metadata, ingestion wiring, partial
success, network error handling, and the max-symbol guard.

## Raw Path Behavior

When live mode is explicitly allowed, raw JSON and metadata are written under
the configured `--live-output-dir`, defaulting to the ignored raw data tree.
Those artifacts are source evidence for the local run and must not be committed.

## Caveats

- This is a controlled live adapter foundation, not production ingestion.
- The current live cap is three explicit symbols per run.
- No scheduler, full-universe crawl, QuestDB migration, broker execution, or
  trading action is included.
- Output is data infrastructure evidence only, not financial advice.
