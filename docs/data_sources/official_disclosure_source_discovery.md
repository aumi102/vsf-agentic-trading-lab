---
title: official_disclosure_source_discovery
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Official Disclosure Source Discovery

## Purpose

Map known official disclosure surfaces for Vietnamese listed companies. Records
come from bounded HTTP probes and live execution, and inform
`probe_official_disclosures.py` target configuration.

## Source Activation Matrix

Live runs: `20260612T052922Z` (manual), `20260612T091529Z` (FPT honest-UA),
`20260612T102412Z` (VCI revalidation), and `20260614T130404Z` (PIT breadth v2
draft).

| Source | Domain | Access | Data Available | Parser | Blocker |
|---|---|---|---|---|---|
| FPT IR | fpt.com | verified | 689 PDF links; FY2025 raw date `2026-03-19`; Q1 2026 date `2026-04-24` | `parse_fpt_ir_html_records` | None |
| VCI FY2025 FS | www.vietcap.com.vn | verified | date `2026-02-13`, PDF URL | `parse_vci_ir_detail_records` | None |
| VCI Q1 2026 FS | www.vietcap.com.vn | verified | date `2026-04-20`, PDF URL | `parse_vci_ir_detail_records` | None |
| HPG IR | www.hoaphat.com.vn | verified | FY2025 `2026-03-27`; Q1 2026 `2026-04-29` | `parse_company_ir_listing_records` | Vietcap comparison rows not committed |
| KDH IR | www.khangdien.com.vn | partial | Q1 2026 `2026-04-29`; FY2025 unresolved | `parse_company_ir_listing_records` | Static page did not expose FY2025 |
| MWG IR | mwg.vn | unresolved | report links without usable publication date | `parse_company_ir_listing_records` | Date binding unresolved |
| VCB IR | portal.vietcombank.com.vn | network_error | none | none | Bounded request timed out; no HTTP denial or access-control block observed |
| SSI IR | www.ssi.com.vn | unresolved | parent page only | `parse_company_ir_listing_records` | Detail endpoint unresolved |
| VNM IR | www.vinamilk.com.vn | unresolved | calendar page only | `parse_company_ir_listing_records` | FS attachment unresolved |
| HOSE CBTT | www.hsx.vn | js_app_shell | React SPA shell only | none | Structured endpoint unresolved |
| HNX CBTT | www.hnx.vn | error | timeout / AJAX shell | none | Feed URL unresolved |

## Positive Controls

FPT official IR is a server-rendered Sitecore page. The honest-UA run
`20260612T091529Z` returned HTTP 200 and 20 bounded bronze records, all quality
pass and `date_only_available`. Q1 2026 financial statements are in bounded
bronze output. FY2025 audited financial statements are present in captured raw
HTML but outside that 20-row bounded output.

VCI official IR has direct detail pages for FY2025 and Q1 2026 financial
statements. Run `20260612T102412Z` returned HTTP 200 for both pages, one bronze
record per target, quality pass, and `date_only_available`.

## PIT Breadth v2 Draft

Registry: `config/pit_breadth_validation_v2_targets.json`.
Sample: `docs/data_sources/pit_breadth_validation_v2_samples.csv`.

The draft added six non-control issuer candidates across bank, industrial,
real estate, retail, securities, and consumer sectors. It verified three new
official-only date-level events: HPG FY2025, HPG Q1 2026, and KDH Q1 2026.
Those events do not count as credible PIT support until bounded Vietcap
publicDate comparison rows are committed. Statement rows are not independent
evidence events.

Breadth result: `pit_inconclusive`, zero red flags, no full PIT confirmation.
DB write and backtest remain blocked.

## Evidence Priority Policy

Canonical PIT evidence must come from official sources: HOSE, HNX, company IR,
or official report/PDF metadata clearly tied to publication date. Secondary
aggregators such as Vietstock, vnstock, Cafef, and FireAnt are investigation
leads only; they do not populate `official_disclosure_date`.

## Open Blockers

1. HOSE structured disclosure API remains unresolved behind the React SPA.
2. HNX structured feed remains unresolved.
3. PIT breadth v2 did not reach the minimum new-issuer/new-sector event gate.
