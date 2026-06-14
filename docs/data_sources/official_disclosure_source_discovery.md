---
title: official_disclosure_source_discovery
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Official Disclosure Source Discovery

## Purpose

Map known official disclosure surfaces for Vietnamese listed companies.
Records what is known from actual HTTP probes and live execution. Informs
target configuration for `probe_official_disclosures.py`.

---

## Source Activation Matrix

Live probe runs: `20260612T052922Z` (manual), `20260612T091529Z` (FPT honest-UA production), `20260612T102412Z` (VCI production revalidation).

| Source | Domain | HTTP | Access Status | Data Available | Parser | Blocker |
|---|---|---|---|---|---|---|
| FPT IR | fpt.com | 200 | verified | YES — 689 PDF links, server-rendered | `parse_fpt_ir_html_records` | None |
| VCI IR (FY2025 FS) | www.vietcap.com.vn | 200 | verified | YES — date 2026-02-13, PDF URL | `parse_vci_ir_detail_records` | None |
| VCI IR (Q1 2026 FS) | www.vietcap.com.vn | 200 | verified | YES — date 2026-04-20, PDF URL | `parse_vci_ir_detail_records` | None |
| HOSE CBTT | www.hsx.vn | 200 | js_app_shell | NO — React SPA, 1.9 KB shell | none | React SPA; api.hsx.vn paths unresolved |
| HNX CBTT | www.hnx.vn | timeout | error | NO — timed out in probe | none | Network timeout from probe env |

---

## FPT Company IR (Positive Control)

**Domain:** `fpt.com`
**URL:** `fpt.com/en/ir/information-disclosures`
**CMS:** Sitecore (server-rendered HTML)

**Live probe evidence (run_id=20260612T091529Z):**
- HTTP 200, 1,402,681 bytes, `text/html; charset=utf-8`
- 689+ distinct PDF disclosure links in static HTML

**Bronze parser output (max_records=20):**
- 20 records produced, all `quality_status=pass`
- All `pit_status=date_only_available` (FPT provides M/D/YYYY, no time)
- Captured raw page contains FY2025 audited consolidated/separate FS dated
  `2026-03-19`; those entries are outside the bounded 20-record bronze output.
- Q1 2026 Consolidated FS: `published_date=2026-04-24` ✓
- 2025 Annual Report: `published_date=2026-04-08` ✓
- Issuer: FPT Corporation

**Parser:** `parse_fpt_ir_html_records` in `scripts/probe_official_disclosures.py`

---

## HOSE (HSX)

**Domain:** `www.hsx.vn`
**URL probed:** `www.hsx.vn/Modules/CMS/Web/CategoryDetail?alias=CBTT`

**Live probe evidence (run_id=20260612T052922Z):**
- HTTP 200, 1,900 bytes, React SPA shell
- HTML contains `<div id="HOSE">` and `<noscript>You need to enable JavaScript to run this app.</noscript>`
- All routes return identical SPA shell regardless of path
- Backend at `api.hsx.vn` discovered from JS bundle (`main.d430e296.js`, 2.4 MB)
- API base URL uses `REACT_APP_API_URL_*` env vars replaced at build time
- Actual disclosure endpoint paths not extractable from minified bundle statically

**Access status:** `js_app_shell`
**Parse summary:** zero bronze records, warning `js_app_shell_no_structured_data`.

**Blocker:** Requires browser/JS runtime to execute disclosure API calls against `api.hsx.vn`. Not addressable without headless browser or API contract discovery.

---

## HNX

**Domain:** `www.hnx.vn`
**URL probed:** `www.hnx.vn/en-gb/cong-bo-thong-tin.html`

**Manual capture evidence (run_id=20260612T052922Z):**
- HTTP 200, 41,114 bytes, navigation hub HTML
- 3 jQuery AJAX calls in source; disclosure items loaded dynamically
- No disclosure records in static HTML

**Production execute (run_id=20260612T081136Z):** Timed out (20s limit).

**Access status:** `error` (timeout in production run) / `html_ajax_shell` (manual capture)
**Blocker:** Network timeout from probe environment; even if reachable, AJAX-loaded data requires follow-up endpoint discovery.

---

## VCI Company IR

**VCI** = Viet Capital Securities Corporation (ticker `VCI`, listed HOSE).

**Domain `www.vietcap.com.vn`:** Official VCI Securities IR portal. Live-verified 2026-06-12
(run_id=`20260612T102412Z`). Honest project UA accepted; TLS certificate verified.

**FY2025 FS detail page:**
- URL: `/en/investor-relations/financial-statements-for-financial-year-of-2025`
- HTTP 200; `parse_vci_ir_detail_records` extracted `published_date=2026-02-13`
- `quality_status=pass`, `pit_status=date_only_available`
- PDF: `api/cms-api/uploads/froala/files/20260213 - VCI - Fin...` (on-domain)

**Q1 2026 FS detail page:**
- URL: `/en/investor-relations/financial-statements-q1-2026`
- HTTP 200; `parse_vci_ir_detail_records` extracted `published_date=2026-04-20`
- `quality_status=pass`, `pit_status=date_only_available`
- PDF: `api/cms-api/uploads/froala/files/20260420 - VCI - Fin...` (on-domain)

**Previous wrong-entity probes (for reference only):**
`vietcapital.com.vn` — VCAM (asset management), not VCI. `vcsc.com.vn` — timed out.
Both are superseded by the verified `www.vietcap.com.vn` domain.

---

## Evidence Priority Policy

From `vietcap_iq_fa_publicdate_pit_validation.md`:

1. HOSE official disclosure record.
2. HNX official disclosure record.
3. Company official IR page (directly accessible).
4. Official PDF/report metadata if clearly tied to publication date.

Secondary aggregators (Vietstock, vnstock) are non-canonical. They do not
populate `official_disclosure_date` and do not affect PIT gate computation.

---

## Configuration

Real targets are configured via `config/official_disclosure_targets.example.json`.
Copy and adjust; do not add secrets. Pass via `--targets-config`:

```
python scripts/probe_official_disclosures.py \
  --symbols FPT \
  --targets-config config/official_disclosure_targets.example.json \
  --max-records 20 \
  --execute
```

---

## Open Blockers

1. **HOSE structured API:** React SPA. `api.hsx.vn` endpoint paths require JS runtime or separate API contract documentation.
2. **HNX structured feed:** Navigation hub. Disclosure items load via jQuery AJAX; feed URL not in static HTML. Also times out in probe environment.

VCI IR is fully resolved — both FY2025 and Q1 2026 FS pages are live-verified.
