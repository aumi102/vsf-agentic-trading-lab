---
title: official_disclosure_source_discovery
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Official Disclosure Source Discovery

## Purpose

Map known official disclosure surfaces for Vietnamese listed companies.
This doc records what is known about each source before probing. It informs
which targets appear in `probe_official_disclosures.py` and which remain
`NOT_CONFIGURED` pending access verification.

---

## Source Matrix

| Source | Domain | Exchange | Access Status | Surface Type | Response Shape | Priority |
|---|---|---|---|---|---|---|
| HOSE official | www.hsx.vn | HOSE | Needs probe | Web + API | HTML + partial JSON | 1 |
| HNX official | www.hnx.vn | HNX | Needs probe | Web | HTML | 2 |
| SSC regulator | ssc.gov.vn | Both | Needs probe | Web archive | HTML | 3 |
| FPT company IR | fpt.com/en/ir | HOSE | Manual confirmed | HTML listing | HTML | 4 |
| VCI company IR | vietcapital.com.vn | HOSE | Auth required | Login portal | — | 4 |
| Vietstock | vietstock.vn | N/A | Non-canonical | Aggregator | — | N/A |

---

## HOSE (HSX)

**Domain:** `www.hsx.vn`

**Official name:** Ho Chi Minh Stock Exchange.

**Known surfaces:**
- Main website with corporate information disclosure section.
- Downloadable tables and PDF attachments in Vietnamese.
- Disclosure listing pages that filter by company ticker.

**Access notes:**
- Public pages return HTML. Some API endpoints return JSON.
- No credentials required for public disclosure listings in prior manual probes.
- Specific API path needs a controlled GET probe to confirm field shape.

**Evidence use case:** Primary canonical source for HOSE-listed issuers
including VCI. A successful probe would provide `official_disclosure_date`
for VCI rows, potentially moving the credible-comparable ratio from 0.50
toward the 0.70 `pit_supported_small_sample` threshold.

**Current adapter status:** `NOT_CONFIGURED` — URL must be supplied via
`targets-config` JSON before any execute-mode probe.

---

## HNX

**Domain:** `www.hnx.vn`

**Official name:** Hanoi Stock Exchange.

**Known surfaces:**
- Corporate disclosure listing pages for HNX-listed companies.
- Public HTML pages; some machine-readable endpoints may exist.

**Access notes:**
- Manual browse shows disclosure pages with date, title, and document links.
- API shape unknown until probed.

**Current adapter status:** `NOT_CONFIGURED`.

---

## SSC (State Securities Commission)

**Domain:** `ssc.gov.vn`

**Role:** National securities regulator. Receives mandatory disclosures from
all listed companies on both exchanges.

**Access notes:**
- Public archive, but document retrieval may require form submission.
- Useful as a cross-reference for hard-to-find issuer disclosures.

**Current adapter status:** Not yet added to default target list.

---

## FPT Company IR (Positive Control)

**Domain:** `fpt.com`
**IR page manually confirmed:** `fpt.com/en/ir/information-disclosures`

**Access notes:** Accessible without authentication. English-language IR page
lists disclosure date, title, and document link for each report.

**Prior evidence:** Manual probe confirmed disclosure dates for:
- 2025 annual report: 2026-03-19
- 2026 Q1 report: 2026-04-24

These dates produced `near_match_1_3_days` and `vietcap_after_official`
match statuses in the PIT validation sample (confidence=medium).

**Current adapter status:** `NOT_CONFIGURED` in default target list.
Supply the known URL via `targets-config` to enable execute-mode probe.

---

## VCI Company IR (Unresolved Target)

**Domain:** `vietcapital.com.vn`

**Access notes:** In a prior probe attempt, the Vietcap IR portal returned a
login page, making automated access infeasible without credentials. This
remains the primary unresolved PIT target.

**Vietstock secondary leads (non-canonical):** Vietstock.vn pages for VCI
were found during manual investigation but are non-canonical. They appear only
in `reviewer_note` in the PIT validation CSV and do not count toward the
credible-comparable ratio. They are not listed as targets here.

**Current adapter status:** `NOT_CONFIGURED`. Official HOSE disclosure
page for VCI is the preferred alternative route.

---

## Evidence Priority Policy (Reiteration)

From `vietcap_iq_fa_publicdate_pit_validation.md`:

1. HOSE official disclosure record.
2. HNX official disclosure record.
3. Company official IR page (directly accessible).
4. Official PDF/report metadata if clearly tied to publication date.

Secondary aggregators (Vietstock, vnstock) are non-canonical. They do not
populate `official_disclosure_date` and do not affect PIT gate computation.

---

## Configuration

To probe configured targets, supply a JSON file:

```json
{
  "targets": [
    {
      "dataset": "hose_disclosures_vci",
      "url": "https://www.hsx.vn/path/to/disclosures?ticker=VCI"
    }
  ]
}
```

Pass via `--targets-config path/to/file.json` when running
`scripts/probe_official_disclosures.py`. Do not commit files containing real
probe URLs to the repo.

---

## Next Probe Actions

1. Manually locate HOSE disclosure listing URL for VCI.
2. Configure via `targets-config` and run in `--plan` mode first.
3. If plan shows valid target, run `--execute` with a single-symbol tiny batch.
4. Inspect raw evidence (`data/raw/official_disclosures/`).
5. If bronze record has `pit_status=date_only_available`, record in PIT CSV.
