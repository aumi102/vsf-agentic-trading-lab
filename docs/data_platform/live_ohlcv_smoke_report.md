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
| Live with allow-network FPT countBack=100 | pass |
| Raw artifacts committed | no |
| Traceback | no after fix |

The first sandboxed attempt was denied socket access with `WinError 10013` and
exposed a Windows path issue because the audit `run_id` contains `:` characters.
The adapter now sanitizes only the filesystem directory component while
preserving the original `run_id` in metadata and database audit rows. After that
fix, the approved one-symbol live smoke succeeded:

- command: `python scripts/run_ohlcv_ingestion.py --symbols FPT --mode live --allow-network --count-back 100`
- status: `ok`
- rows: 100 canonical `daily_prices`, 100 feature rows, 100 signal rows
- source run recorded: yes
- raw payload recorded: yes, under ignored `data/raw/...`
- latest trade date in payload: `2026-06-17`
- traceback: no

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
