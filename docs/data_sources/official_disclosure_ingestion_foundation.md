---
title: official_disclosure_ingestion_foundation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Official Disclosure Ingestion Foundation v1

## Purpose

Establish a reusable, controlled foundation for fetching and normalizing
official disclosure records from HOSE, HNX, and company IR pages. The
foundation does not unblock DB writes, backtests, or full-history fetches.
It is a prerequisite for resolving the VCI `pit_inconclusive` status.

---

## Artifacts

| File | Role |
|---|---|
| `src/trading_agent/source_adapters/disclosure_adapter.py` | Contracts, enums, quality/PIT gate functions |
| `scripts/probe_official_disclosures.py` | CLI: plan/execute/checkpoint |
| `tests/test_probe_official_disclosures.py` | 45 unit tests |
| `docs/data_sources/official_disclosure_source_discovery.md` | Source matrix |

---

## Architecture

### Contracts (`disclosure_adapter.py`)

**`DisclosureTarget`** — a single configured probe target. Key field:
`is_configured` is `True` only when `url` is non-empty.

**`DisclosureRecord`** — normalized bronze output. Fields mirror the bronze
schema: `source_family`, `exchange`, `official_domain`, `adapter_name`,
`disclosure_id`, `symbol`, `issuer_name`, `document_category`, `title`,
`published_at`, `published_date`, `effective_at`, `page_url`, `document_url`,
`attachment_name`, `attachment_type`, `language`, `crawled_at`, `raw_path`,
`metadata_path`, `body_sha256`, `parser_version`, `schema_version`,
`quality_status`, `pit_status`, `warning_codes`, `error_codes`.

**`DisclosurePitStatus`** — enum:
- `canonical_timestamp_available` — full ISO datetime known.
- `date_only_available` — date but no time.
- `official_timestamp_missing` — response received but no date found.
- `non_canonical` — source is a secondary aggregator.
- `not_applicable` — disclosure type not relevant for PIT.
- `blocked` — access blocked, auth required, or target not configured.

**`DisclosureQualityStatus`** — enum: `pass`, `warn`, `fail`.

**`assign_pit_status(published_at, published_date, access_status)`** — pure
function that returns the appropriate `DisclosurePitStatus` value.

**`check_disclosure_quality(record_dict)`** — pure function that checks
required structural fields and returns `(quality_status, warnings, errors)`.
If `error_codes` are already set (e.g. from a blocked fetch), quality is `fail`.

### CLI (`probe_official_disclosures.py`)

```
python scripts/probe_official_disclosures.py [options]

--symbols FPT,VCI       Symbols to include in target set (default: FPT,VCI)
--max-requests 5        Maximum configured targets to probe per run
--sleep-min-seconds 2   Minimum seconds between requests in execute mode
--sleep-max-seconds 5   Maximum seconds between requests in execute mode
--targets-config FILE   JSON file with URL overrides per dataset
--execute               Opt in to live network calls (plan-only by default)
--force                 Re-fetch targets already completed in checkpoint
```

**Plan mode** (default): builds and writes `plan.json` and `plan_report.md`
without making any network calls. All not-configured targets are listed in
`skipped` with `reason=not_configured`.

**Execute mode** (`--execute`): processes configured targets sequentially
(concurrency=1). Random sleep is applied between requests. Raw evidence
is captured before any parsing. Bronze record is written after parsing.

**Checkpoint/resume**: after every request the checkpoint JSON is updated.
On the next `--execute` run, completed datasets are skipped unless `--force`
is supplied.

### Raw Evidence Layout

Each executed target writes to:

```
data/raw/official_disclosures/
  run_id=<id>/
    <dataset>/
      payload.<ext>       # response body (json/html/bin)
      metadata.json       # access_status, http_status, body_sha256, ...
      request.json        # method, url, header_names, request_params
```

### Bronze Output Layout

```
data/bronze/official_disclosures/
  run_id=<id>/
    <dataset>/
      disclosure_record.json   # DisclosureRecord.as_dict()
```

Both `data/raw/` and `data/bronze/` are gitignored. Only reviewed fixture
records may be committed.

### Bronze Parser

`parse_to_bronze_record(response, target, payload_path, metadata_path, crawled_at)`
is a pure function that:

1. Classifies `access_status` from the HTTP response.
2. Attempts JSON parse; falls back to raw text with `warning_codes`.
3. Extracts known disclosure fields (`publishedAt`, `date`, `title`, etc.)
   from JSON objects; lists remain flagged for manual review.
4. Calls `assign_pit_status` to set `pit_status`.
5. Calls `check_disclosure_quality` and merges error/warning codes.
6. Returns a fully populated `DisclosureRecord`.

---

## Default Target Set

Running without `--targets-config` builds four NOT_CONFIGURED targets:

| Dataset | Exchange | Symbol | Note |
|---|---|---|---|
| `hose_disclosures_fpt` | HOSE | FPT | Needs probe URL |
| `hose_disclosures_vci` | HOSE | VCI | Primary unresolved PIT target |
| `hnx_disclosures_fpt` | HNX | FPT | Needs probe URL |
| `hnx_disclosures_vci` | HNX | VCI | Needs probe URL |
| `company_ir_fpt_disclosures` | HOSE | FPT | Positive control; URL known manually |
| `company_ir_vci_disclosures` | HOSE | VCI | Auth required in prior probe |

All are `NOT_CONFIGURED` until a `targets-config` JSON supplies real URLs.
In plan mode, all targets appear in `skipped` with `reason=not_configured`.

---

## Test Coverage

`tests/test_probe_official_disclosures.py` — 45 tests:

- PIT status assignment (7): verified/date-only/missing/blocked/auth/error
- Quality gate (5): pass/warn/fail conditions
- Target configuration (3): `is_configured` cases
- Default target building (5): families, symbols, not-configured default
- Plan mode (6): no network calls, plan JSON, report, guardrails, skip, max
- Execute mode (4): HTTP called, raw evidence, SHA256, bronze output
- Checkpoint (3): write, resume skip, force re-run
- Bronze parsing (3): blocked → pit_blocked, JSON → date_only, timestamp → canonical
- HTTP classification (4): 200/401/403/500
- Config overlay (2): URL applied, unmatched unchanged
- Input validation (3): empty targets, zero max, sleep below minimum

---

## Guardrails

- No network requests unless `--execute` is supplied.
- Targets without a URL are skipped; `status=not_configured`.
- Sequential processing only; concurrency=1.
- Random sleep ≥2 s applied between execute-mode requests.
- Raw payload and metadata captured before any parsing.
- No database write, migration, backtest, or full-universe fetch.
- No secret values written to output files.

---

## Gate Status

This foundation does not change any gate status:

- `publicDate` PIT semantics: still `pit_inconclusive`. VCI official evidence
  is still unresolved. FPT canonical evidence remains supportive.
- DB write: still blocked.
- Backtest: still blocked.
- Mapping coverage gate: unchanged (BS 89.7% / IS 94.5% / CF 87.6%).

To advance the PIT gate, configure a HOSE disclosure URL for VCI and run
`--execute`. If the probe returns a bronze record with
`pit_status=date_only_available` or `canonical_timestamp_available`, record
those dates in the PIT validation CSV and re-run the validator.
