---
title: source_crawling_plan
toc_min_heading_level: 2
toc_max_heading_level: 3
---

## Source Crawling Plan

### Purpose

<details open>
<summary>Define the next implementation direction for source-first data infrastructure.</summary>

---

This plan defines how the project should probe only the mentor-named sources: HSX/HOSE, Vietcap IQ, VBMA, and FRED/fredapi. The next coding tasks should remain source probes and adapter skeletons until raw fields and access are verified.

---

</details>

### Source-First Principle

<details open>
<summary>Canonical data must come from verified HSX/HOSE, Vietcap IQ, VBMA, or FRED/fredapi payloads.</summary>

---

The project should learn the data infrastructure by inspecting and preserving source-level fields from the four active sources. The canonical MVP should be built from adapters that know which source produced each row, what request generated it, what raw payload was captured, and how it maps into canonical tables.

---

</details>

### Target Architecture

<details open>
<summary>The source pipeline keeps raw evidence before canonical normalization.</summary>

---

```text
source -> raw capture -> bronze parser -> silver canonical table -> quality report
```

| Stage | Responsibility | Required output |
|---|---|---|
| `source` | Public page, official API, vendor API, manual file, websocket, or other verified surface. | source config and probe result. |
| `raw capture` | Save exact payload before interpretation. | raw file, metadata JSON, content hash. |
| `bronze parser` | Parse minimally into source-shaped rows. | parser status, original fields, parser version. |
| `silver canonical table` | Normalize into source-agnostic contracts. | `securities`, `daily_prices`, `corporate_events`, or later tables. |
| `quality report` | Validate schema, duplicates, OHLC, timestamps, and source linkage. | pass/warn/fail gates and limitations. |

---

</details>

### Source Probe Before Full Crawler

<details open>
<summary>Every source starts with a small probe.</summary>

---

Probe goals:

- Determine whether access is public, authenticated, manual-only, blocked, or unknown.
- Capture a tiny raw sample for one or two symbols and a short date range where allowed.
- Record original fields, timestamps, IDs, status codes, and content types.
- Identify whether terms/auth make the source usable for the project.
- Decide whether the source can map into `securities`, `daily_prices`, `corporate_events`, or only reference/evidence tables.

Probe statuses:

- `verified`
- `rejected_response`
- `auth_required`
- `manual_only`
- `blocked`
- `not_configured`
- `unknown`

---

</details>

### Response Validation

<details open>
<summary>HTTP success is not enough when the body is a rejection page or wrong shape.</summary>

---

Configured source targets may include optional response validation fields:

| Field | Type | Meaning |
|---|---|---|
| `expected_content_type_contains` | string or list of strings | Required substring or substrings that must appear in the response `Content-Type`. |
| `expected_body_startswith_json` | boolean | If `true`, the body must start with `{` or `[` after leading whitespace. |
| `reject_body_contains` | list of strings | If any marker appears in the response body, reject the sample even when HTTP status is 200. |
| `min_body_bytes` | integer | Minimum acceptable response size in bytes. |
| `body_json` | object | Optional JSON request body for configured `POST` probes. |

If a response violates these rules:

- access status should be `rejected_response`.
- raw payload may still be stored for debugging.
- metadata/report must explain the validation reason.
- the sample must not be treated as verified usable data.

Use this for HSX/HOSE quote-report endpoints, where HTTP 200 can still return an HTML `Request Rejected` body.

Configured target method behavior:

- `GET` sends no request body.
- `POST` serializes `body_json` to UTF-8 JSON bytes. Use `{}` when the source expects an empty JSON object.
- Methods other than `GET` and `POST` are rejected as unsupported.
- Metadata may record `method`, `body_present`, `body_size_bytes`, and `body_json_keys`.
- Metadata must not store full header values, cookies, or sensitive body values.

---

</details>

### Raw Sample Storage Convention

<details open>
<summary>Raw probe output must be reproducible and auditable.</summary>

---

Use this convention for source probes:

```text
data/raw/source_probe/source=<source_name>/run_id=<timestamp>/<dataset_or_endpoint>/
├── payload.<ext>
└── metadata.json
```

For full ingestion, use:

```text
data/raw/<source_name>/run_id=<timestamp>/<dataset>/...
```

Do not commit generated raw data unless explicitly requested.

---

</details>

### Metadata JSON Convention

<details open>
<summary>Each raw payload needs machine-readable provenance.</summary>

---

Required metadata fields:

- `source_name`
- `adapter_name`
- `dataset`
- `endpoint_or_surface`
- `request_params`
- `symbol`
- `start`
- `end`
- `crawled_at`
- `source_timestamp`
- `access_status`
- `auth_mode`
- `http_status`
- `content_type`
- `original_columns`
- `row_count`
- `content_hash`
- `raw_path`
- `parser_version`
- `schema_version`
- `status`
- `error`
- `terms_notes`

Secrets must never be written to metadata.

---

</details>

### Source Adapter Interface

<details open>
<summary>The target interface is documented here; do not implement it until the next coding task.</summary>

---

```python
class SourceAdapter:
    source_name: str

    def probe(self) -> SourceProbeResult:
        ...

    def fetch_symbols(self) -> FetchResult:
        ...

    def fetch_daily_ohlcv(self, symbol, start, end) -> FetchResult:
        ...

    def fetch_corporate_actions(self, symbol) -> FetchResult:
        ...

    def fetch_reports(self, symbol) -> FetchResult:
        ...
```

Expected result objects:

- `SourceProbeResult`: source name, access status, available datasets, auth status, sample raw paths, field names, terms notes, warnings, errors.
- `FetchResult`: dataset, status, raw payload or parsed source-shaped rows, raw path, metadata path, warning list, error.

Adapters must fail clearly when credentials/config are absent.

---

</details>

### Canonical Table Mapping

<details open>
<summary>Source-specific fields map into source-agnostic tables.</summary>

---

| Canonical table | Source-specific inputs | Required mapping decision |
|---|---|---|
| `securities` | symbol lists, securities APIs, exchange listing files. | stable `security_id`, exchange normalization, security type, company name. |
| `daily_prices` | daily OHLC, EOD price, adjusted price, daily stock price APIs/files. | trade date, OHLC, volume, value, adjustment status, source row ID. |
| `corporate_events` | corporate actions, dividends, rights issues, issuer disclosures. | event ID, event type, announcement/ex/execution dates, dividend/ratio fields. |
| `reports` | research portals, manual report downloads, evidence stores. | publication timestamp, source, symbol, URL/file path, content hash. |

Raw source columns must remain available through `raw_path` and metadata even after canonical normalization.

---

</details>

### Access And Auth Handling

<details open>
<summary>Source probes must distinguish missing access from data failure.</summary>

---

- Read credentials from environment variables or local config files that are ignored by git.
- Never hard-code secrets.
- If credentials are absent, return `not_configured`, not `fail`.
- If credentials are invalid, return `auth_required` or `blocked` with the provider error.
- If manual download is required, document exact manual steps and expected file format.
- If terms are unclear, mark legal/terms risk as `unknown` and do not promote the source to canonical.

---

</details>

### Rate Limit And Polite Crawling Rules

<details open>
<summary>Probes should be small and respectful by default.</summary>

---

- Start with one or two symbols and a short date range.
- Use configurable request delays.
- Respect provider rate limits and robots/terms guidance.
- Set a clear user agent where allowed.
- Avoid retries that amplify blocked or rate-limited requests.
- Record retry count and rate-limit responses in metadata.

---

</details>

### Failure Handling

<details open>
<summary>Source failures must be visible and structured.</summary>

---

Failure categories:

- `not_configured`
- `auth_required`
- `network_error`
- `rate_limited`
- `schema_unknown`
- `schema_drift`
- `empty_response`
- `manual_required`
- `terms_unclear`
- `blocked`

Downstream code must not substitute legacy prototype sources for failed active source probes.

---

</details>

### Source Probe Report Format

<details open>
<summary>The probe report should make source readiness obvious.</summary>

---

Write:

```text
reports/source_probe_report.md
```

Required sections:

- run ID and crawl time.
- sources probed.
- access/auth status.
- endpoint or surface checked.
- sample symbols/date range.
- raw sample paths.
- original fields observed.
- likely canonical table mapping.
- legal/terms risk notes.
- blocking issues.
- recommended next action.

---

</details>

### Acceptance Criteria

<details open>
<summary>The next implementation should stop at source probing.</summary>

---

The source-probe task is acceptable if:

- source adapters are skeletons/probes, not full ingestion.
- active probes cover only HSX/HOSE, Vietcap IQ, VBMA, and FRED/fredapi.
- raw probe metadata is generated for successful probes.
- `reports/source_probe_report.md` explains which source can or cannot support canonical OHLCV.
- no backtest, feature expansion, database, agent orchestration, or vector search is implemented.

---

</details>
