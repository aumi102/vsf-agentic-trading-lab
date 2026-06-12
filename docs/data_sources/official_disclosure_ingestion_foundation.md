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
| `scripts/probe_official_disclosures.py` | CLI: plan/execute/checkpoint + FPT HTML parser |
| `config/official_disclosure_targets.example.json` | Real target config with evidence-backed access statuses |
| `tests/test_probe_official_disclosures.py` | 67 unit tests |
| `docs/data_sources/official_disclosure_source_discovery.md` | Source matrix with live probe results |

---

## Architecture

### Contracts (`disclosure_adapter.py`)

**`DisclosureTarget`** — configured probe target. `is_configured` is `True` only when `url` is non-empty. Fields include `ssl_verify` (default `True`) for targets requiring SSL bypass.

**`DisclosureRecord`** — normalized bronze output. Fields: `source_family`, `exchange`, `official_domain`, `adapter_name`, `disclosure_id`, `symbol`, `issuer_name`, `document_category`, `title`, `published_at`, `published_date`, `effective_at`, `page_url`, `document_url`, `attachment_name`, `attachment_type`, `language`, `crawled_at`, `raw_path`, `metadata_path`, `body_sha256`, `parser_version`, `schema_version`, `quality_status`, `pit_status`, `warning_codes`, `error_codes`.

**`DisclosurePitStatus`** — enum:
- `canonical_timestamp_available` — full ISO datetime known.
- `date_only_available` — date but no time.
- `official_timestamp_missing` — response received but no date found.
- `non_canonical` — source is a secondary aggregator.
- `not_applicable` — disclosure type not relevant for PIT.
- `blocked` — access blocked, auth required, JS shell, or target not configured.

**`DisclosureQualityStatus`** — enum: `pass`, `warn`, `fail`.

### CLI (`probe_official_disclosures.py`)

```
python scripts/probe_official_disclosures.py [options]

--symbols FPT,VCI        Symbols to include in target set (default: FPT,VCI)
--max-requests 5         Maximum configured targets to probe per run
--max-records 20         Max disclosure records to parse per HTML target
--sleep-min-seconds 2    Minimum seconds between requests in execute mode
--sleep-max-seconds 5    Maximum seconds between requests in execute mode
--targets-config FILE    JSON file with URL overrides per dataset
--execute                Opt in to live network calls (plan-only by default)
--force                  Re-fetch targets already completed in checkpoint
```

Default request headers include a browser User-Agent to pass CDN bot filters.
Per-target `ssl_verify: false` available for sites with non-standard CAs (e.g. HNX).

### FPT IR HTML Parser

`parse_fpt_ir_html_records(body, target, payload_path, metadata_path, crawled_at, max_records=20)`

Parses FPT Corporation's official IR page (Sitecore CMS, server-rendered HTML).
Dispatched from `extract_disclosure_records` when `official_domain == "fpt.com"` and content type is HTML.

- Regex matches `<div class="media-download-section-key-information-content">` blocks.
- Extracts title, `Updated: M/D/YYYY` date, and PDF href per block.
- Normalizes relative hrefs against `https://fpt.com`.
- Parses date `M/D/YYYY` → `YYYY-MM-DD`; empty on parse failure.
- Infers document category from title keywords (annual_report, quarterly_financial_statement, disclosure, board_resolution).
- Generates deterministic `disclosure_id` from `sha256(doc_url)[:12]`.
- Decodes HTML entities in title (&#39; → ', &amp; → &, etc.).
- Returns up to `max_records` records; returns a single WARN record if no items match.

### Raw Evidence Layout

```
data/raw/official_disclosures/
  <run_id>/
    <dataset>/
      payload.<ext>       # response body (json/html/bin)
      metadata.json       # access_status, http_status, body_sha256, ...
      request.json        # method, url, header_names, request_params
```

### Bronze Output Layout

```
data/bronze/official_disclosures/
  <run_id>/
    <dataset>/
      disclosure_record.json        # single-record targets (JSON/non-HTML)
      disclosure_record_000.json    # multi-record targets (FPT HTML)
      disclosure_record_001.json
      ...
```

Both `data/raw/` and `data/bronze/` are gitignored.

---

## Live Activation Results (run_id=20260612T081136Z)

| Source | HTTP | Access Status | Bronze Rows | PIT Level | Quality |
|---|---|---|---|---|---|
| FPT IR (`fpt.com`) | 200 | verified | 20 | date_only_available (all) | pass (all) |
| HOSE (`www.hsx.vn`) | 200 | js_app_shell | 1 | blocked | warn |
| HNX (`www.hnx.vn`) | timeout | error | 0 | — | — |
| VCI IR | N/A | NOT_CONFIGURED | 0 | — | — |

FPT Q1 2026 Consolidated FS `published_date=2026-04-24` — matches PIT validation CSV entry.

---

## Target Set

| Dataset | Source | Symbol | Status after config |
|---|---|---|---|
| `company_ir_fpt_disclosures` | fpt.com | FPT | configured — verified, 20 bronze records |
| `hose_disclosures_fpt` | www.hsx.vn | FPT | configured — js_app_shell, no structured data |
| `hose_disclosures_vci` | www.hsx.vn | VCI | configured — js_app_shell, no structured data |
| `hnx_disclosures_fpt` | www.hnx.vn | FPT | configured — timeout in production run |
| `hnx_disclosures_vci` | www.hnx.vn | VCI | configured — timeout in production run |
| `company_ir_vci_disclosures` | unresolved | VCI | NOT_CONFIGURED — domain unknown |

---

## Test Coverage

`tests/test_probe_official_disclosures.py` — 67 tests:

- PIT status assignment (7)
- Quality gate (5)
- Target configuration (3)
- Default target building / parse_symbols (5)
- Plan mode (6)
- Execute mode (4)
- Checkpoint (3)
- Bronze parsing: JSON (3)
- HTTP classification (4)
- Config overlay (2)
- Input validation (3)
- FPT HTML parser (12): title, date, URL, ID, limit, missing-date, no-items, entities, attachment, PIT, quality, execute
- Dispatch / extract_disclosure_records (2)
- js_app_shell classification (3)
- Config / activation (4)
- FPT execute integration / js_app_shell checkpoint (2)

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

- `publicDate` PIT semantics: still `pit_inconclusive`. FPT IR verified live (`date_only_available`, 20 records). VCI official evidence still unresolved.
- DB write: still blocked.
- Backtest: still blocked.
- Mapping coverage gate: unchanged (BS 89.7% / IS 94.5% / CF 87.6%).

To advance the PIT gate for VCI: resolve the VCI official IR domain, configure it, and run `--execute`. If the probe returns bronze records with `pit_status=date_only_available`, record dates in the PIT validation CSV and re-run the validator.
