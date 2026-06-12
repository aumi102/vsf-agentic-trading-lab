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

**`DisclosureTarget`** — configured probe target. `is_configured` is `True` only when `url` is non-empty. No `ssl_verify` field — TLS certificate verification is always enforced.

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

Request headers use an honest project User-Agent (`vsf-agentic-trading-lab/0.1 official-source-probe`).
TLS certificates are always verified; there is no `ssl_verify` bypass.

### FPT IR HTML Parser

`parse_fpt_ir_html_records(body, target, payload_path, metadata_path, crawled_at, max_records=20)`

Parses FPT Corporation's official IR page (Sitecore CMS, server-rendered HTML).
Dispatched from `extract_disclosure_records` when `official_domain == "fpt.com"` and content type is HTML.

- Regex matches `<div class="media-download-section-key-information-content">` blocks.
- Extracts title, `Updated: M/D/YYYY` date (calendar-validated via `strptime`), and PDF href per block.
- Domain-validates absolute hrefs: off-domain URLs are rejected (empty string).
- Normalizes relative hrefs against `https://fpt.com`.
- Infers document category from title keywords (annual_report, quarterly_financial_statement, financial_statement, board_resolution).
- Generates deterministic `disclosure_id` from `sha256(doc_url)[:12]`.
- Decodes HTML entities in title (&#39; → ', &amp; → &, etc.).
- Returns up to `max_records` records; returns `[]` if no items match (no pseudo rows).

### Vietcap IR Detail-Page Parser

`parse_vci_ir_detail_records(body, target, payload_path, metadata_path, crawled_at)`

Parses a Vietcap Securities IR detail page. One record per detail page.
Dispatched from `extract_disclosure_records` when `official_domain == "www.vietcap.com.vn"` and content type is HTML.

- Extracts title from `<h1>`, `<h2>`, or `<title>` tag (strips site-name suffix).
- Extracts first date in `D Mon YYYY` format (calendar-validated via `strptime`).
- Extracts first on-domain PDF URL; off-domain PDFs are rejected.
- Infers category from URL slug (annual_financial_statement, quarterly_financial_statement).
- Returns `[]` if no title and no date found (no pseudo rows).

**Live verification (run_id=20260612T090059Z):**
- FY2025 FS → `published_date=2026-02-13`, `quality=pass`, `pit=date_only_available`
- Q1 2026 FS → `published_date=2026-04-20`, `quality=pass`, `pit=date_only_available`

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

## Live Activation Results

| Source | Run ID | HTTP | Access Status | Bronze Rows | PIT Level | Quality |
|---|---|---|---|---|---|---|
| FPT IR (`fpt.com`) | 20260612T081136Z | 200 | verified | 20 | date_only_available (all) | pass (all) |
| VCI IR FY2025 FS (`www.vietcap.com.vn`) | 20260612T090059Z | 200 | verified | 1 | date_only_available | pass |
| VCI IR Q1 2026 FS (`www.vietcap.com.vn`) | 20260612T090059Z | 200 | verified | 1 | date_only_available | pass |
| HOSE (`www.hsx.vn`) | 20260612T052922Z | 200 | js_app_shell | 0 | blocked | — |
| HNX (`www.hnx.vn`) | 20260612T052922Z | timeout | error | 0 | — | — |

FPT Q1 2026 `published_date=2026-04-24`, VCI FY2025 `published_date=2026-02-13`, VCI Q1 2026 `published_date=2026-04-20` — all match PIT validation CSV entries.

---

## Target Set

| Dataset | Source | Symbol | Status after config |
|---|---|---|---|
| `company_ir_fpt_disclosures` | fpt.com | FPT | configured — verified, 20 bronze records |
| `company_ir_vci_fy2025_fs` | www.vietcap.com.vn | VCI | configured — verified, published_date=2026-02-13 |
| `company_ir_vci_q1_2026_fs` | www.vietcap.com.vn | VCI | configured — verified, published_date=2026-04-20 |
| `hose_disclosures_fpt` | www.hsx.vn | FPT | configured — js_app_shell, no disclosure records |
| `hose_disclosures_vci` | www.hsx.vn | VCI | configured — js_app_shell, no disclosure records |
| `hnx_disclosures_fpt` | www.hnx.vn | FPT | configured — timeout in production run |
| `hnx_disclosures_vci` | www.hnx.vn | VCI | configured — timeout in production run |

---

## Test Coverage

`tests/test_probe_official_disclosures.py` — 107 tests:

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
- FPT HTML parser (11): title, date, URL, ID, limit, no-items (empty), entities, attachment, PIT, quality, execute
- Dispatch / extract_disclosure_records (4): FPT HTML, JSON fallback, js_app_shell, auth, error
- js_app_shell classification (3)
- Config / activation (4)
- FPT execute integration / js_app_shell checkpoint (2)
- Security: honest UA (2), no ssl_verify field (2)
- Probe-only status returns no records (4): js_app_shell, auth_required, error, js_app_shell execute
- URL domain validation (7): FPT on/off-domain, VCI on/off-domain
- Date validation (8): FPT strptime valid/invalid, VCI textual format Feb/Apr/invalid/wrong-format
- VCI IR detail parser (11): title, FY2025 date, Q1 2026 date, PIT, PDF URL, off-domain PDF, no content, quality, dispatch
- VCI config activation (2)
- Document category semantics (6): FPT annual/quarterly/plain FS, FPT annual≠FS, VCI FY/Q1

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

- `publicDate` PIT semantics: `pit_supported_small_sample` (8/8 credible, 0 red flags). FPT IR 20 records (`date_only_available`). VCI FY2025 (`2026-02-13`) and Q1 2026 (`2026-04-20`) exact-matched or near-matched Vietcap `publicDate`. Do not claim full PIT confirmation; small sample only.
- DB write: still blocked.
- Backtest: still blocked.
- Mapping coverage gate: unchanged (BS 89.7% / IS 94.5% / CF 87.6%).
- Security: fake browser UA removed; honest project UA in use. TLS bypass removed; certificates always verified. No pseudo disclosure rows for shells or parse failures.
