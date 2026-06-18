---
title: adjusted_factor_source_probe_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted Factor Source Probe Plan

## Purpose

PR #32 added the adjustment-factor source foundation and confirmed that tracked
gap-chart evidence does not prove adjusted close or corporate-action factors.
This probe adds a controlled way to plan source checks and inspect local JSON
payloads for adjustment evidence before any ETL population.

## Default Behavior

The probe is dry-run and no-network by default. It does not mutate the database
and does not populate adjusted OHLC columns. If `--allow-network` is supplied,
the plan is blocked because live probing is not implemented in this PR.

## Candidate Sources

- `vietcap_iq_gap_chart`
- `vietcap_iq_company_events`
- `tracked_fixtures`

The MVP config is `configs/ingestion/adjusted_factor_probe_mvp.json` and limits
the default symbol set to `FPT,VNM,VCB`.

## Evidence Fields

The local payload inspector searches for adjusted close field names
(`adjusted_close`, `adj_close`, `adjustedClose`, `adjClose`), adjustment factor
field names (`adjustment_factor`, `adjust_factor`, `factor`), and corporate
action terms (`dividend`, `split`, `bonus`, `rights`, `ex_date`,
`record_date`).

## Commands

```bash
python scripts/probe_adjusted_factor_sources.py --symbols FPT,VNM,VCB
python scripts/probe_adjusted_factor_sources.py --symbols FPT,VNM,VCB,MSN
python scripts/probe_adjusted_factor_sources.py --inspect-payload path/to/local.json
```

The four-symbol command is expected to return a blocked plan. That is a guardrail,
not a traceback.

## Current Limitation

This probe captures planning and local evidence only. Adjusted OHLC population,
Backtrader/VN100 research, Docker scheduling, and live/full-universe probing
remain out of scope.
