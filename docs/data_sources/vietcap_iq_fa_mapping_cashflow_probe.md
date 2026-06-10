---
title: vietcap_iq_fa_mapping_cashflow_probe
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Mapping and CASH_FLOW Probe Report

**Date:** 2026-06-10  
**Branch:** `phase/fa-mapping-cashflow-probe`

---

## Purpose

This document records the results of two controlled probes:

1. **Metric mapping re-probe** — a repeat attempt of the `/financial-statement/metrics` endpoint
   that previously failed at DNS level (run `20260609T091305Z`). Objective: retrieve a code-to-name
   mapping for FA metric codes.
2. **CASH_FLOW shape probe** — a first-time FA probe of the CASH_FLOW section for VCI and FPT.
   Objective: confirm the payload envelope, metric code count, `publicDate` presence, and whether
   the shape matches BALANCE_SHEET and INCOME_STATEMENT.

No DB writes. No backtests. No invented metric names. All conclusions are drawn solely from saved
probe payloads.

---

## 1. Metric Mapping Probe

### Endpoint

`https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement/metrics`

This is the same endpoint targeted in the prior inconclusive probe (`run_id=20260609T091305Z`,
DNS failure). It was re-probed on 2026-06-10 when DNS resolution was available.

### Command

```
python scripts/probe_vietcap_iq_fa_httpx_session.py \
  --diagnostic-target fa-direct \
  --symbol VCI \
  --section BALANCE_SHEET \
  --referer-style trading-company-page \
  --api-url "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/VCI/financial-statement/metrics" \
  --dataset "vietcap_iq_fa_metrics_mapping_probe"
```

### Result

| Field | Value |
|---|---|
| `run_id` | `20260610T025420Z` |
| `http_status` | `200` |
| `access_status` | `verified` |
| Payload saved | Yes |
| Mapping found | **Yes** |

**Path:** `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260610T025420Z/vietcap_iq_fa_metrics_mapping_probe/`

### Payload Structure

The response `data` field is a dict keyed by FA section name. Each value is an ordered list of
entry objects:

```
data:
  BALANCE_SHEET: [entry, ...]      # 212 entries: 208 metric codes, 4 section headers
  INCOME_STATEMENT: [entry, ...]   # 80 entries: all metric codes, 0 headers
  CASH_FLOW: [entry, ...]          # 153 entries: 148 metric codes, 5 section headers
  NOTE: [entry, ...]               # 642 entries: all metric codes, 0 headers
```

Each entry has the following fields:

| Field | Type | Notes |
|---|---|---|
| `field` | `str \| null` | Metric code (e.g., `bsa1`). Null for section-level display headers. |
| `name` | `str` | Uppercase variant of the code (e.g., `BSA1`). |
| `titleEn` | `str` | English label (e.g., `"CURRENT ASSETS"`). |
| `titleVi` | `str` | Vietnamese label. |
| `fullTitleEn` | `str` | Full English label (may equal `titleEn`). |
| `fullTitleVi` | `str` | Full Vietnamese label. |
| `level` | `int` | Hierarchy depth (1 = top-level). |
| `parent` | `str \| null` | Parent code, or null if top-level. |

**Null-field entries** (section headers) are display items in the Vietcap IQ UI, not metric codes.
They must be excluded from the code-to-name mapping index. They are identified by `field=null`.

### Total Codes

| Section | Total entries | Null-field (headers) | Non-null (metric codes) |
|---|---|---|---|
| BALANCE_SHEET | 212 | 4 | 208 |
| INCOME_STATEMENT | 80 | 0 | 80 |
| CASH_FLOW | 153 | 5 | 148 |
| NOTE | 642 | 0 | 642 |
| **Total** | **1087** | **9** | **1078** |

---

## 2. Mapping Coverage Analysis

Coverage was computed by `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py --probe-dir`
against the saved FA probe payloads. See §4 for the parser script.

| Probe | Symbol | Section | Codes in Payload | Covered by Mapping | Coverage |
|---|---|---|---|---|---|
| `20260609T035318Z` | VCI | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260609T075846Z` | VCI | INCOME_STATEMENT | 181 | 79 | **43.6%** |
| `20260609T075857Z` | FPT | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260610T025429Z` | VCI | CASH_FLOW | 225 | 148 | **65.8%** |
| `20260610T025440Z` | FPT | CASH_FLOW | 225 | 148 | **65.8%** |

**Coverage is partial and below the 95% DB write threshold.** The uncovered codes are firm-type-specific
or section-specific variants not included in the mapping response for this symbol (VCI, a securities firm).

Possible reasons for uncovered codes:
- The mapping endpoint may return a template appropriate for the queried symbol's firm type.
  A universal mapping across all firm types might require querying multiple symbols.
- Firm-type variants (`bss*`, `bsb*`, `bsi*`) may have limited coverage for their specialized codes.
- The NOTE section (642 codes) was not tested in saved probe payloads — coverage there is unknown.

**The mapping is a genuine discovery but is not yet sufficient for a DB write gate.**

---

## 3. CASH_FLOW Section Probe

### Probes Executed

| run_id | Symbol | Section | Command target |
|---|---|---|---|
| `20260610T025429Z` | VCI | CASH_FLOW | `fa-direct` with CASH_FLOW URL |
| `20260610T025440Z` | FPT | CASH_FLOW | `fa-direct` with CASH_FLOW URL |

Both probes used the same clean 8-header profile (no Cookie, no Authorization) as all prior FA probes.

### Results

Both probes returned HTTP 200 with `access_status=verified`.

**Paths:**
- `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260610T025429Z/vietcap_iq_fa_cash_flow_vci_probe/`
- `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260610T025440Z/vietcap_iq_fa_cash_flow_fpt_probe/`

### CASH_FLOW Payload Shape

| Field | VCI | FPT |
|---|---|---|
| Quarters | 33 | 33 |
| Annual rows | 8 | 8 |
| Metric columns per row | 225 | 225 |
| `publicDate` non-null (quarterly) | 33/33 | 33/33 |
| `publicDate` non-null (annual) | 8/8 | 8/8 |
| First quarterly `publicDate` | `2018-08-17T00:00:00` | (same format) |
| Envelope structure | `data.quarters` + `data.years` | Same |

**The CASH_FLOW envelope is identical to BALANCE_SHEET and INCOME_STATEMENT.** The same parser
handles all three sections without modification.

### CASH_FLOW Metric Code Prefix Sample

First 5 codes observed (VCI): `cfa1`, `cfa2`, `cfa3`, `cfa4`, `cfa5`

Prefix groups (unverified inferences, same methodology as prior sections):

| Prefix | Probable category (unverified) |
|---|---|
| `cfa*` | General cash flow items |
| `cfs*` | Securities-firm-specific cash flow items |
| `cfb*` | Bank-specific cash flow items (hypothetical) |
| `cfi*` | Insurance-specific cash flow items (hypothetical) |

These are structural inferences from code patterns only. Individual code names come from the
mapping (65.8% coverage); the remaining 34.2% of codes have no name available.

### `publicDate` Observations

`publicDate` is non-null for all 33 quarterly and 8 annual rows in both VCI and FPT CASH_FLOW.
This is consistent with BALANCE_SHEET and INCOME_STATEMENT behaviour. **The PIT semantics of
`publicDate` remain unconfirmed** — it is a candidate availability field only. See the readiness
doc §16.

---

## 4. Mapping Dry-Run Parser

### Script

`scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py`

No network. No DB writes. Pure offline parser.

### Behaviour

- Reads the saved mapping `payload.json` from the probe run directory.
- Parses all sections into a flat CSV (`_MAPPING_COLUMNS`): `section`, `line_item_code`,
  `line_item_name_en`, `line_item_name_vi`, `level`, `parent`, `name`, `is_header`.
- Null-field entries are included with `is_header=true` so callers can filter them.
- Optionally scans `--probe-dir` for saved FA probe payloads and outputs a per-(symbol, section)
  coverage CSV (`_COVERAGE_COLUMNS`).
- Output is deterministic and sorted: `section` → `is_header` → `line_item_code`.
- Does not invent names. Codes not in the mapping produce no output entry.

### Example Usage

```bash
# Parse mapping only
python scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py \
  --output-mapping data/processed/vietcap_iq/fa_metric_mapping.csv

# Parse mapping + compute coverage against saved probes
python scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py \
  --output-mapping data/processed/vietcap_iq/fa_metric_mapping.csv \
  --probe-dir data/raw/httpx_diagnostic/source=vietcap_iq \
  --output-coverage data/processed/vietcap_iq/fa_metric_mapping_coverage.csv
```

### Tests

50 new tests in `tests/test_parse_vietcap_iq_fa_metric_mapping_dry_run.py`. All pass.

---

## 5. Confirmed Facts (This Probe Package)

| Fact | Evidence |
|---|---|
| `/financial-statement/metrics` returns HTTP 200 with a full mapping payload | `run_id=20260610T025420Z`, `access_status=verified` |
| Mapping is structured as a section-keyed dict of entry objects | Payload `data` keys: `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, `NOTE` |
| 1078 non-null metric codes are present across four sections | Parsed from mapping payload |
| 9 null-field entries are section-level display headers, not metric codes | Confirmed by inspection; headers have no `field` value |
| Mapping coverage is partial: 62.8% BS / 43.6% IS / 65.8% CF (vs 95% gate threshold) | Coverage computed by dry-run parser against saved probe payloads |
| CASH_FLOW uses identical envelope: `data.quarters` + `data.years` | VCI and FPT CASH_FLOW probes, HTTP 200 |
| CASH_FLOW has 33 quarterly and 8 annual rows (same depth as BS/IS) | Shape confirmed for both VCI and FPT |
| `publicDate` is non-null for all CASH_FLOW rows in both VCI and FPT probes | Confirmed from payload inspection |
| CASH_FLOW metric codes start with `cfa*` prefix (general) | First 5 codes: `cfa1`–`cfa5` |

---

## 6. Outstanding Unknowns

| Unknown | Impact |
|---|---|
| Why IS coverage is only 43.6% (lower than BS/CF) | May indicate the mapping is not universal; may require querying a different symbol type |
| Whether mapping covers NOTE section codes in practice | No saved NOTE FA payload to test against |
| Whether querying the mapping endpoint with a different symbol returns more codes | VCI is a securities firm; a general/bank/insurance firm may have a different mapping response |
| `publicDate` PIT semantics | Unconfirmed; see readiness doc §16 |
| Coverage of `nos*` codes in mapping | VCI has non-null `nos*` values; FPT does not. `nos*` codes may exist in NOTE section. |

---

## 7. Gate Status Update

| Gate | Previous Status | Updated Status |
|---|---|---|
| Metric mapping verified and coverage ≥ 95% threshold | Not met — no mapping available | **Not met** — mapping retrieved (1078 codes); coverage 43–66% across sections; below 95% threshold |
| CASH_FLOW section confirmed | Not met — unprobed | **Met** — HTTP 200, identical envelope, 225 codes per row, publicDate non-null |
| `publicDate` PIT semantics confirmed | Not met | **Not met** — unchanged |

The mapping gate remains blocked — partial coverage is a real advance but not sufficient for DB
write approval.

---

## 8. Next Recommended Steps

1. **Probe mapping endpoint with additional symbol types** (bank, insurance) to check if
   a broader symbol returns higher IS coverage.
2. **Probe additional FA sections** (NOTE, and any section not yet confirmed) for 1–2 symbols.
3. **Probe 3–5 additional symbols** (HOSE/HNX/UPCOM) to confirm shape consistency at scale.
4. **Investigate NOTE section coverage** — retrieve a NOTE-section FA payload to test the
   642 NOTE mapping codes against real data.
5. **Do not** integrate mapping into the parser or write DB until coverage meets the gate threshold.
6. **Do not** confirm `publicDate` as PIT without cross-checking against filing records.

---

## Related Documents

- `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` — updated with this probe result
- `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` — gate status updates in §1 and §17
- `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` — mapping parser implementation
- `tests/test_parse_vietcap_iq_fa_metric_mapping_dry_run.py` — 50 tests
