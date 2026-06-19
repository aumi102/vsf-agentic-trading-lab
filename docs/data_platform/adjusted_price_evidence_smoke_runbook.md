---
title: adjusted_price_evidence_smoke_runbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted Price Evidence Smoke Runbook

## Purpose

This smoke exercises the local adjusted-price evidence pipeline on the explicit
small-symbol set `FPT,VNM,VCB`. It uses synthetic local payload rows and a
temporary SQLite DB by default. It does not fetch live data, crawl a universe,
populate production adjusted OHLC, or run Backtrader.

## Preconditions

- PR #40 adjusted-price evidence pipeline is available.
- No live source is required.
- Symbols are explicit and capped to `FPT,VNM,VCB`.
- Raw close is not treated as adjusted close.
- No `factor=1` fallback is allowed.

## Temporary Smoke

Run the default smoke:

```bash
python scripts/smoke_adjusted_price_evidence_pipeline.py
```

Expected top-level result:

```json
{
  "status": "ok",
  "symbols": ["FPT", "VNM", "VCB"],
  "artifacts_persisted": false
}
```

The script creates a temporary local payload and DB, runs the pipeline in
dry-run mode, runs execute mode against that temporary DB, then calls adjusted
OHLC readiness. It exits `0` only when dry-run succeeds, execute mode succeeds,
and readiness returns `backtest_gate=pass`.

Invalid requests, such as more than three symbols or symbols outside the
synthetic `FPT,VNM,VCB` smoke set, exit `1` with a JSON `invalid_request`
summary and no DB mutation.

## Persisted Local Artifacts

To inspect the generated local payload, factor files, and temporary DB, provide
an explicit output directory:

```bash
python scripts/smoke_adjusted_price_evidence_pipeline.py --output-dir .pytest_tmp_adjusted_price_smoke
```

Expected artifacts:

- `.pytest_tmp_adjusted_price_smoke/adjusted_price_payload.json`
- `.pytest_tmp_adjusted_price_smoke/factors_dry_run.json`
- `.pytest_tmp_adjusted_price_smoke/factors_execute.json`
- `.pytest_tmp_adjusted_price_smoke/adjusted_price_smoke.sqlite`

## Readiness Check

When using `--output-dir`, the readiness command can be run directly:

```bash
python scripts/check_adjusted_ohlc_readiness.py --db-path .pytest_tmp_adjusted_price_smoke/adjusted_price_smoke.sqlite --symbols FPT,VNM,VCB
```

Expected readiness:

- `status=ok`
- `backtest_gate=pass`
- all selected rows have adjusted OHLC and factor provenance

## Caveats

- This is synthetic fixture evidence, not an approved live source payload.
- It proves the local path works end to end for a small explicit set.
- Production adjusted OHLC remains blocked until reviewed real evidence is used.
- Backtrader/VN100 remains blocked until adjusted OHLC readiness passes on the
  intended dataset.
