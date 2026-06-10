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

### Probe 1 (2026-06-09) — DNS failure, inconclusive

`run_id=20260609T091305Z`

| Field | Value |
|---|---|
| `http_status` | `null` — no HTTP response received |
| `access_status` | `error` |
| `error` | `[Errno 11001] getaddrinfo failed` — DNS resolution failure |
| Payload saved | No |
| Mapping found | Unknown — probe did not reach the server |

The probe failed at DNS level before any HTTP exchange. Not an auth failure — environmental.
Result is inconclusive.

### Probe 2 (2026-06-10) — HTTP 200, mapping payload found

`run_id=20260610T025420Z`

| Field | Value |
|---|---|
| `http_status` | `200` |
| `access_status` | `verified` |
| Payload saved | Yes |
| Mapping found | **Yes** |
| Path | `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=20260610T025420Z/vietcap_iq_fa_metrics_mapping_probe/` |

The re-probe succeeded when DNS resolved. The response `data` field is a section-keyed dict:

```
data:
  BALANCE_SHEET: [...]   # 208 metric codes + 4 null-field headers
  INCOME_STATEMENT: [...] # 80 metric codes
  CASH_FLOW: [...]        # 148 metric codes + 5 null-field headers
  NOTE: [...]             # 642 metric codes
  # 1078 non-null codes total; 9 null-field display headers
```

Each entry has: `field` (code, e.g. `bsa1`), `name` (uppercase, e.g. `BSA1`), `titleEn`,
`titleVi`, `fullTitleEn`, `fullTitleVi`, `level`, `parent`. Null-field entries are section
display headers, not metric codes. See `vietcap_iq_fa_mapping_cashflow_probe.md` for full
payload structure detail.

The same clean 8-header profile (no Cookie, no Authorization) was used as for all FA probes.

---

## Mapping Coverage

### VCI-only coverage (baseline)

Coverage computed by `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py`:

| Probe | Symbol | Section | Codes in Payload | Covered | Coverage |
|---|---|---|---|---|---|
| `20260609T035318Z` | VCI | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260609T075846Z` | VCI | INCOME_STATEMENT | 181 | 79 | **43.6%** |
| `20260609T075857Z` | FPT | BALANCE_SHEET | 331 | 208 | **62.8%** |
| `20260610T025429Z` | VCI | CASH_FLOW | 225 | 148 | **65.8%** |
| `20260610T025440Z` | FPT | CASH_FLOW | 225 | 148 | **65.8%** |

### Union coverage (VCI + VCB + BVH + SSI)

Additional mapping probes for VCB (bank, `run_id=20260610T033851Z`), BVH (insurance,
`20260610T033856Z`), and SSI (securities, `20260610T033900Z`) were run. Key finding: **the
mapping is firm-type-specific**. SSI returned the identical mapping to VCI (securities firms
share a mapping). VCB returned bank-specific codes (`isb*`, `bsb*`, `cfb*`). BVH returned
insurance-specific codes (`isi*`, `bsi*`).

The union of all 4 payloads has 1793 codes with 88 name conflicts:

| Section | VCI-only % | Union % | Consensus % | Gate (95%) |
|---|---|---|---|---|
| BALANCE_SHEET | 62.8% | **89.4%** | 71.9% | **blocked** |
| INCOME_STATEMENT | 43.6% | **92.3%** | 86.2% | **blocked** |
| CASH_FLOW | 65.8% | **86.7%** | 78.2% | **blocked** |

Best observed union coverage across tested firm types so far (VCI, VCB, BVH, SSI). **No
section reaches the 95% gate threshold.** Coverage is significantly improved from VCI-only,
but additional firm types may still improve coverage. Mapping integration remains blocked
because no section reaches 95% and the 88 conflicts require an integration strategy decision.

Computed by `scripts/analyze_vietcap_iq_fa_metric_mapping_union.py`. See
`docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` for full analysis.

---

## Unknowns and Risks

| Unknown | Impact |
|---|---|
| Whether additional firm types (fund management, etc.) cover the remaining 8–13% | May close or narrow the gap to 95%; cannot determine without a probe |
| Whether the 88 conflicting codes prevent safe universal naming | Integration strategy must decide per-symbol vs union approach |
| Whether codes are stable across API versions | Mapping table should include a probe run_id/version stamp |
| NOTE section codes coverage against real FA data | No saved NOTE section FA payload; cannot measure |

---

## Next Recommended Steps

1. **Investigate residual uncovered codes** — check whether a fund management or other firm
   type covers the remaining uncovered BS/IS/CF codes.

2. **Design the mapping integration strategy** — decide between per-symbol mapping (no
   conflicts, lower coverage per probe) or union mapping (higher coverage, 88 conflicts
   requiring disambiguation).

3. **Integrate mapping into the parser dry-run** once coverage is sufficient (≥ 95% threshold)
   and an integration strategy is decided. Do not write names for uncovered codes.

4. **No full-universe fetch, no DB write, no backtest** until mapping, PIT validation, and
   parser hardening gates are all met.
