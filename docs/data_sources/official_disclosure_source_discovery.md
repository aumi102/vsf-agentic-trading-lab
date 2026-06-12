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

Live probe run: `20260612T052922Z` (manual capture) and `20260612T081136Z` (production CLI).

| Source | Domain | HTTP | Access Status | Data Available | Parser | Blocker |
|---|---|---|---|---|---|---|
| FPT IR | fpt.com | 200 | verified | YES — 689 PDF links, server-rendered | `parse_fpt_ir_html_records` | None |
| HOSE CBTT | www.hsx.vn | 200 | js_app_shell | NO — React SPA, 1.9 KB shell | none | React SPA; api.hsx.vn paths unresolved |
| HNX CBTT | www.hnx.vn | timeout | error | NO — timed out in probe | none | Network timeout from probe env |
| VCI IR | vietcapital.com.vn | 200 (wrong entity) | wrong_entity | NO — VCAM, not VCI | none | Wrong company; real domain unresolved |
| VCI IR | vcsc.com.vn | timeout | error | NO — timed out | none | Not accessible from probe env |

---

## FPT Company IR (Positive Control)

**Domain:** `fpt.com`
**URL:** `fpt.com/en/ir/information-disclosures`
**CMS:** Sitecore (server-rendered HTML)

**Live probe evidence (run_id=20260612T081136Z):**
- HTTP 200, 1,402,681 bytes, `text/html; charset=utf-8`
- Cloudflare CDN requires browser User-Agent (Python default UA returns 403)
- 689+ distinct PDF disclosure links in static HTML

**Bronze parser output (max_records=20):**
- 20 records produced, all `quality_status=pass`
- All `pit_status=date_only_available` (FPT provides M/D/YYYY, no time)
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
**Bronze record:** `pit_status=blocked`, `quality_status=warn`, warning `js_app_shell_no_structured_data`

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
Not to be confused with VCAM (Viet Capital Asset Management, ticker `VCAMBF`).

**Domain `vietcapital.com.vn`:** HTTP 200, 4,721 bytes, page title "VCAM | VietCapital".
This is the asset management subsidiary, not the securities broker.
`rails_session` cookie and `x-runtime` header confirm a Ruby on Rails app (VCAM portal).
**Status: wrong entity** — removed from config and docs.

**Domain `vcsc.com.vn`:** Connection timed out (20s) from probe environment.
Cannot verify whether this is the correct VCI Securities domain.
**Status: unresolved (timeout)**

**VCI IR target:** `NOT_CONFIGURED`. Official domain must be verified manually before
any execute-mode probe. See `company_ir_vci_disclosures` target in default set.

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

1. **VCI IR domain:** Unresolved. `vietcapital.com.vn` is wrong entity (VCAM). `vcsc.com.vn` timed out. Verify via HOSE official issuer profile page (requires JS execution).
2. **HOSE structured API:** React SPA. api.hsx.vn endpoint paths require JS runtime or separate API contract documentation.
3. **HNX structured feed:** Navigation hub. Disclosure items load via jQuery AJAX; feed URL not in static HTML.
