---
title: vietcap_iq_fa_metric_mapping_discovery
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Metric Mapping Discovery

## Purpose

The FA parser dry-run (`scripts/parse_vietcap_iq_fa_payloads_dry_run.py`) produces long-format
fact rows with opaque `line_item_code` values (`bsa1`, `bss212`, `isa25`, `nos8`, etc.) and
an empty `line_item_name` column. This document records the search for a code-to-name mapping
that would allow human-readable line item names to be populated.

---

## Local Audit Result

**No code-to-name mapping exists anywhere in the local repository.**

| Location | Result |
|---|---|
| FA payload rows (VCI BALANCE_SHEET, run `20260609T035318Z`) | 338 keys per row: 7 metadata + 331 opaque metric codes. Zero name/label/display/mapping fields. |
| FA payload rows (VCI INCOME_STATEMENT, run `20260609T075846Z`) | 188 keys per row: 7 metadata + 181 opaque metric codes. Zero name/label fields. |
| FA payload rows (FPT BALANCE_SHEET, run `20260609T075857Z`) | Same as VCI BS — zero name/label fields. |
| All saved metadata files | No mapping fields present. |
| `docs/data_sources/vietcap_iq_fa_payload_shape_review.md` | Explicitly notes "no human-readable names in payload"; mapping listed as required next step. |
| `docs/data_sources/vietcap_iq_fa_shape_cross_check.md` | Same — no mapping found. |
| `scripts/probe_vietcap_iq_fa_httpx_session.py` | No mapping endpoint or config. |
| `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` | `line_item_name` column always empty; parser explicitly notes mapping not available. |

Prefix groups are documented by inferred category only (not a verified mapping):

| Prefix | Inferred category (unverified) |
|---|---|
| `bsa*` | General balance sheet items |
| `bsb*` | Bank-specific balance sheet items |
| `bsi*` | Insurance-specific balance sheet items |
| `bss*` | Securities-company balance sheet items |
| `nos*` | Off-balance-sheet notes |
| `isa*` | General income statement items |
| `isb*` | Bank-specific income statement items |
| `isi*` | Insurance-specific income statement items |
| `iss*` | Securities-specific income statement items |

These prefix-level descriptions are inferred from zero/nonzero density patterns across VCI and FPT.
Individual codes (e.g., `bsa1` → "Total Assets") are **unknown**.

---

## Live Mapping Probe

### Candidate endpoint probed

`https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement/metrics`

This endpoint path follows the same base URL and service path as the confirmed FA data endpoint
(`/financial-statement?section=BALANCE_SHEET`), with `/metrics` appended. It was identified as
the most likely candidate for a code-to-name mapping response.

### Command used

```
python scripts/probe_vietcap_iq_fa_httpx_session.py \
  --diagnostic-target fa-direct \
  --symbol VCI \
  --section BALANCE_SHEET \
  --referer-style trading-company-page \
  --api-url "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement/metrics" \
  --dataset "vietcap_iq_fa_financial_statement_metrics_mapping_probe"
```

### Result

| Field | Value |
|---|---|
| `run_id` | `20260609T091305Z` |
| `http_status` | `null` — no HTTP response received |
| `access_status` | `error` |
| `error` | `[Errno 11001] getaddrinfo failed` — DNS resolution failure |
| Payload saved | No |
| Mapping found | Unknown — probe did not reach the server |

The probe failed at the DNS/connection level before any HTTP exchange occurred. This is **not**
an HTTP 403/auth-required result — it is a network-level failure. It does not indicate whether
the endpoint exists, returns 200, or contains mapping data. The result is inconclusive.

The same clean 8-header profile (no Cookie, no Authorization, no `sec-ch-ua*`) was used as for
the successful FA data probes. The failure is environmental, not caused by the request profile.

---

## Alternative Mapping Candidates (Not Yet Probed)

| Candidate URL | Priority | Notes |
|---|---|---|
| `https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement/metrics` | P0 | Primary candidate — re-probe when network available |
| `https://trading.vietcap.com.vn/vietcap-iq/language/vi/company.json` | P1 | Localization JSON referenced in `01_vietcap_iq.md`; may contain FA field labels for UI |
| `/financial-statement/template` or `/financial-statement/fields` | P2 | Hypothetical alternatives — not confirmed to exist; requires browser DevTools inspection |
| Browser DevTools on Vietcap IQ financial statement page | P1 | Most reliable way to discover actual mapping endpoint used by the UI |

---

## Mapping Coverage

**Not measurable.** No mapping data was found locally or retrieved via probe. Coverage report
(`scripts/check_vietcap_iq_fa_mapping_coverage.py` or similar) will be written once a mapping
payload is available.

Current parser state: `line_item_name` is empty for all 34,563 fact rows across three parsed
payloads.

---

## Unknowns and Risks

| Unknown | Impact |
|---|---|
| Whether `/financial-statement/metrics` exists and returns 200 | Cannot assess until re-probed successfully |
| Whether mapping endpoint returns a flat code → name dict or a structured list | Parser integration design depends on response shape |
| Whether names are in Vietnamese, English, or both | Localisation handling may be needed |
| Whether the mapping is section-specific or shared across all FA sections | Parser must know whether to load one mapping file or one per section |
| Whether `bsa1` codes are stable across API versions | Mapping table may need a version field |

---

## Next Recommended Steps

1. **Re-probe `/financial-statement/metrics`** when network access to `iq.vietcap.com.vn` is
   restored. Use the same command documented above. If HTTP 200 JSON is returned, inspect the
   payload shape and document it here.

2. **If /metrics returns 403 or 404**: Try the localization JSON endpoints
   (`/vietcap-iq/language/vi/company.json`) or inspect browser DevTools on the financial
   statement page to identify the actual mapping endpoint.

3. **Once mapping payload is confirmed**: Write a coverage check script to count how many of the
   331 BALANCE_SHEET and 181 INCOME_STATEMENT codes are covered by the mapping.

4. **Only after mapping is verified**: Integrate mapping into the parser dry-run as a
   `line_item_name` lookup. No production parser, no DB write, until coverage is sufficient.

5. **No full-universe fetch, no DB write, no backtest** until mapping, PIT validation, and
   parser hardening are complete.
