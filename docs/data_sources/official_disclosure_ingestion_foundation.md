---
title: official_disclosure_ingestion_foundation
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Official Disclosure Ingestion Foundation v1

## Purpose

Provide a controlled foundation for fetching and normalizing official disclosure
records from HOSE, HNX, and company IR pages. It supports the current
`publicDate` small sample, but does not unblock DB writes, backtests, or
full-history fetches.

## Artifacts

| File | Role |
|---|---|
| `src/trading_agent/source_adapters/disclosure_adapter.py` | Contracts, enums, quality/PIT helpers |
| `scripts/probe_official_disclosures.py` | Plan/execute CLI, raw capture, checkpoint, parse summaries, parsers |
| `config/official_disclosure_targets.example.json` | Official target configuration |
| `tests/test_probe_official_disclosures.py` | 179 focused tests |
| `docs/data_sources/official_disclosure_source_discovery.md` | Source matrix and live evidence |
| `config/pit_breadth_validation_v2_targets.json` | Draft multi-sector PIT breadth target registry |

## Contracts And CLI

`DisclosureTarget` defines source family, exchange, official domain, adapter,
dataset, symbol, URL, headers, request params, and terms notes. There is no
`ssl_verify` field; official disclosure fetches always verify TLS.

`DisclosureRecord` is the bronze schema for real disclosure rows. SPA shells,
auth pages, blocked requests, network/TLS errors, and valid no-match pages do
not create fake records.

The CLI defaults to plan-only mode. `--execute` is required for live requests.
Requests are sequential, sleep between targets, capture raw payload/metadata
before parsing, and do not write to DB.

## Security And Config

Request headers use the honest project User-Agent:
`vsf-agentic-trading-lab/0.1 official-source-probe`.

Config validation rejects forbidden keys recursively: `ssl_verify`, `verify`,
`insecure`, auth headers, cookies, and secret-like keys such as token,
`api_key`, password, `client_secret`, or session. Allowed headers are `Accept`,
`Accept-Language`, `Connection`, and `User-Agent` only when it exactly equals
the project UA. Browser impersonation User-Agent values are rejected.

Target URLs must be HTTPS and match the configured official domain.

## Parsers

FPT parser:

- Parses server-rendered Sitecore disclosure blocks from `fpt.com`.
- Extracts title, updated date, document URL, category, and attachment metadata.
- Accepts HTTPS same-domain or root-relative document URLs.
- Rejects unsafe schemes, protocol-relative URLs, non-HTTPS URLs, malformed
  URLs, deceptive suffix domains, userinfo host tricks, and third-party domains
  with specific warnings.
- Returns no pseudo rows when no disclosure blocks match.

Vietcap parser:

- Parses `www.vietcap.com.vn` IR detail pages.
- Binds title/date extraction to the disclosure detail container, not global
  page chrome.
- Extracts document URL from the disclosure article.
- Validates target semantics: FY2025 target must match FY2025 financial
  statements; Q1 2026 target must match Q1 2026 financial statements.
- Returns zero rows and a parse-summary warning on semantic mismatch.

## Parse Summaries

Each execute target writes `parse_summary.json` and the aggregate summary is
stored in the run plan and checkpoint. The summary includes dataset, source
family, official domain, access status, HTTP status, parser name, parse status,
bronze record count, warning/error codes, raw path, metadata path, and body
SHA-256.

## Live Evidence

| Source | Run ID | HTTP | Rows | Dates | Quality/PIT |
|---|---|---:|---:|---|---|
| FPT IR | `20260612T091529Z` | 200 | 20 | Q1 2026 FS `2026-04-24`; Annual Report 2025 separately categorized; raw page contains FY2025 audited FS `2026-03-19` outside bounded bronze output | all pass / `date_only_available` |
| VCI FY2025 FS | `20260612T102412Z` | 200 | 1 | `2026-02-13` | pass / `date_only_available` |
| VCI Q1 2026 FS | `20260612T102412Z` | 200 | 1 | `2026-04-20` | pass / `date_only_available` |
| HOSE parent page | `20260612T052922Z` | 200 | 0 | React SPA shell | parse summary warning |
| HNX parent page | `20260612T081136Z` | timeout | 0 | structured endpoint unresolved | parse summary error |

PIT Breadth Validation v2 added a bounded draft run (`20260614T130404Z`)
against FPT, VCI, HPG, KDH, MWG, VCB, SSI, and VNM. It found new official-only
date-level evidence for HPG FY2025 (`2026-03-27`), HPG Q1 2026 (`2026-04-29`),
and KDH Q1 2026 (`2026-04-29`), but did not reach the breadth PIT threshold.

Both `data/raw/` and `data/bronze/` are gitignored; live outputs are not
committed.

## Gate Status

- PIT sample: 8/8 statement rows credible, 4/4 unique official disclosure
  events credible, 2 issuers, zero red flags, `pit_supported_small_sample`.
- Breadth v2 sample: 20 rows, 4 credible comparable unique events, 8 target
  issuers, 7 target sectors, zero red flags, `pit_inconclusive`.
- This is not full PIT confirmation; evidence is date-level, not timestamp-level.
- Broader issuer/exchange validation is still required.
- Mapping coverage remains below 95%.
- QuestDB schema not implemented.
- Full-history fetch not implemented.
- DB write and backtest remain blocked.
