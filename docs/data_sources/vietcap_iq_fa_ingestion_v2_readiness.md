---
title: vietcap_iq_fa_ingestion_v2_readiness
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Ingestion V2 Readiness

## Purpose

This document defines the readiness state for production Vietcap IQ financial-statement
(FA) ingestion. It is written at the end of the dry-run / hardening phase to capture every
confirmed fact, every open gate, and every constraint that must be satisfied before a DB
write is permitted. No DB write or backtest is implemented in this phase.

---

## 1. Current Status

| Item | Status |
|---|---|
| FA endpoint access | **Confirmed** — HTTP 200 JSON for VCI BALANCE_SHEET, VCI INCOME_STATEMENT, FPT BALANCE_SHEET using clean 8-header profile |
| Payload shape reviewed | **Confirmed** — wide-format `data.quarters` + `data.years`; opaque metric codes; `publicDate` present |
| Parser dry-run | **Implemented** — `scripts/parse_vietcap_iq_fa_payloads_dry_run.py`; 34,563 long-format fact rows from 3 saved payloads |
| Parser hardening | **Done** — 7 validation checks; `--strict` mode; deterministic sort; 235 tests pass |
| Metric code-to-name mapping | **Partially retrieved** — VCI-only: 1078 codes, BS 62.8% / IS 43.6% / CF 65.8%; union across VCI+VCB+BVH+SSI: 1793 codes, BS 89.4% / IS 92.3% / CF 86.7%; 88 conflicts; no section reaches 95% gate threshold |
| `publicDate` PIT semantics | **Unconfirmed** — present in payload as candidate field only; semantics not validated against exchange filings |
| Full-history FA fetch | **Not implemented** — no fetcher script; no symbol universe loop |
| DB write | **Not implemented** — explicitly blocked |
| Backtest | **Not implemented** — explicitly blocked |
| Manifest planner | **Implemented** — `scripts/plan_vietcap_iq_fa_full_history_manifest.py` (dry-run, no network) |

---

## 2. Confirmed Facts

| Fact | Evidence |
|---|---|
| FA endpoint is reachable with a clean 8-header HTTP profile (no Cookie, no Authorization) | Runs `20260609T035318Z`, `20260609T075846Z`, `20260609T075857Z` all returned HTTP 200 |
| Payload envelope is `{"data": {"quarters": [...], "years": [...]}, "serverDateTime": "...", ...}` | Reviewed in `vietcap_iq_fa_payload_shape_review.md` |
| BALANCE_SHEET rows have 331 opaque metric codes per row; INCOME_STATEMENT has 181 | Shape cross-check confirmed across VCI and FPT |
| Row metadata fields are `ticker`, `organCode`, `yearReport`, `lengthReport`, `publicDate`, `updateDate`, `createDate` | Parser METADATA_FIELDS constant |
| `lengthReport=1..4` encodes Q1..Q4; `lengthReport=5` encodes annual | Confirmed from shape review; used in parser period encoding |
| `publicDate` is present and non-empty for all rows in all three saved payloads | Parser dry-run output; `q_publicdate_nonnull` = row count for all three runs |
| `publicDate` values follow ISO date format (`YYYY-MM-DDT00:00:00`) in saved payloads | `_check_publicdate_format` check passes with `severity=info` |
| `nos*` columns are entirely null for non-securities firms (FPT) | `_check_nos_pattern` result; VCI (securities firm) has non-null `nos*` values |
| `null` and `0.0` are distinct in the payload and must stay distinct in the output | Validated by `value_status` logic and `test_validate_preserves_null_vs_zero_distinction` |
| The parser produces deterministic output given the same saved payloads | `_sort_facts` + `test_sort_facts_is_deterministic` |
| No duplicate natural keys across the three parsed payloads | `_check_duplicate_keys` passes with `severity=info` |
| Three originally parsed payloads cover VCI BALANCE_SHEET, VCI INCOME_STATEMENT, FPT BALANCE_SHEET | The full FA symbol/section universe has not been fetched |
| CASH_FLOW section uses the same `data.quarters` + `data.years` envelope as BALANCE_SHEET and INCOME_STATEMENT | VCI and FPT CASH_FLOW probes, `run_id=20260610T025429Z` and `20260610T025440Z` |
| CASH_FLOW rows have 225 metric columns; `publicDate` is non-null for all quarterly and annual rows | Confirmed from VCI and FPT CASH_FLOW payloads |
| `/financial-statement/metrics` returns HTTP 200 with a full mapping payload | `run_id=20260610T025420Z`; data keys: BALANCE_SHEET, INCOME_STATEMENT, CASH_FLOW, NOTE |
| Mapping payload has 1078 non-null metric codes and 9 null-field display headers across 4 sections | Parsed by `scripts/parse_vietcap_iq_fa_metric_mapping_dry_run.py` |
| VCI-only mapping coverage: 62.8% BS / 43.6% IS / 65.8% CF | Coverage computed from 5 saved probe payloads; below 95% gate threshold |
| Union mapping coverage (VCI+VCB+BVH+SSI): 89.4% BS / 92.3% IS / 86.7% CF | Union has 1793 codes, 88 conflicts; still below 95% gate; mapping is firm-type-specific |

---

## 3. Unconfirmed Assumptions

| Assumption | Why Unconfirmed | Required to Unblock |
|---|---|---|
| `publicDate` represents the exchange filing/publication date usable for PIT availability | No cross-check against HOSE/HSX/HNX official filing records or Vietcap documentation | PIT validation gate (see §14) |
| Metric codes (`bsa1`, `isa25`, etc.) map to human-readable line-item names | Mapping payload retrieved (run `20260610T025420Z`); coverage 62.8% BS / 43.6% IS / 65.8% CF — below 95% gate; remaining codes have no verified name | Metric mapping gate (see §13) — coverage must reach ≥ 95% per section |
| Endpoint returns the same shape for all HOSE/HNX/UPCOM listed firms and all FA sections | Only tested for VCI (securities) and FPT (general) on BS, IS, and CF | Broader symbol/section probe |
| `accumulatedValue` / trading-value units are consistent across symbols | Not reviewed for FA endpoint; documented open risk for gap-chart | FA-specific payload review |
| The endpoint is stable at scale (1598-symbol fetch) | Only 2 symbols (VCI, FPT) across 5 saved FA payloads have been reviewed; no full-universe stability test has been run | Rate-limit and access review |
| `organCode` is always equal to `ticker` for all non-securities firms | Sometimes differs; parser emits `WARNING_CODE_TICKER_DIFFER` per row | Source documentation |

---

## 4. Full-History FA Fetch Policy

**Current state:** Not implemented. No fetcher script exists for FA full-history.

**Intended future design (subject to gate satisfaction):**

- Target: all listed-market symbols from the Vietcap IQ universe (`HOSE`, `HNX`, `UPCOM`;
  excluding indexes, `OTC`, `OTHER`, `STOP`).
- Request scope: all confirmed FA sections (`BALANCE_SHEET`, `INCOME_STATEMENT`,
  `CASH_FLOW`, and others as verified) for each symbol.
- History depth: full available history per symbol per section; the endpoint appears to
  return full historical quarters and years without a `countBack` limit based on shape review.
- Fetch order: sequential; one symbol at a time; random sleep between requests.
- No aggressive async or high-concurrency fetch until rate-limit behavior is reviewed.
- Checkpoint/resume: a fetch checkpoint file must record completed, failed, and pending
  (symbol, section) pairs so a crashed fetch job can resume.
- Raw payload preservation: save each response before parsing.
- Do not fetch until mapping, PIT, and schema gates are satisfied.

---

## 5. Symbol Universe Policy

- **Source:** Vietcap IQ search-bar payload (`company/search-bar?language=1`).
- **Fetch scope:** `HOSE`, `HNX`, and `UPCOM` listed-market rows with `isIndex=false`.
- **Excluded:** `OTC`, `OTHER`, `STOP`, index candidates, quality-fail rows.
- **Count:** 1,598 listed-market fetch candidates (as of the most recent dry run).
- **Not final tradable assets:** the fetch universe is broader than the final tradable
  asset list; dynamic liquidity and data-completeness filters apply later during the
  strategy phase.
- **Prior to production FA fetch:** the symbol universe must be refreshed from the
  search-bar payload at fetch time, not hardcoded.

---

## 6. Supported Statement Sections

| Section | Probe Status | Parser Status | Notes |
|---|---|---|---|
| `BALANCE_SHEET` | **Confirmed** — VCI + FPT | **Implemented** | 331 metric codes per row for both tested symbols |
| `INCOME_STATEMENT` | **Confirmed** — VCI only | **Implemented** | 181 metric codes per row |
| `CASH_FLOW` | **Not yet probed** | Not implemented | Assumed by analogy; must be probed before adding to fetch plan |
| Other sections (ratios, notes) | **Not discovered** | Not implemented | Requires DevTools discovery |

The manifest planner currently accepts `BALANCE_SHEET`, `INCOME_STATEMENT`, and
`CASH_FLOW`. `CASH_FLOW` rows will carry a `requires_network=yes` readiness note.

---

## 7. Period / Frequency Policy

| Field | Encoding | Status |
|---|---|---|
| `yearReport` | Integer fiscal year (e.g., `2024`) | Confirmed |
| `lengthReport` | `1–4` = Q1–Q4; `5` = annual | Confirmed |
| `source_period_label` | `{year}Q{quarter}` or `{year}Y` | Parser output |
| `fiscal_quarter` | Integer `1–4` for quarterly; empty string for annual | Parser output |
| Both quarterly and annual rows | Returned in same payload | Confirmed |

There is no intra-day or monthly period encoding observed. The endpoint appears to return
the full available period history for each section without pagination.

---

## 8. Rate-Limit / Retry / Cache Policy

**Not yet characterized.** The following constraints apply until empirical evidence is available:

- **Rate limit:** Unknown. Only VCI and FPT (2 symbols, 5 saved FA payloads) have been
  successfully probed; no 429 or throttle response has been observed.
- **Retry policy:** No retry logic implemented. If the endpoint returns a non-200 response,
  the payload should be recorded as failed and the checkpoint updated. Manual review before
  retry.
- **Cache:** No local response cache has been implemented. The checkpoint file records
  completed (symbol, section) pairs to avoid re-fetching.
- **Sleep between requests:** A random sleep (suggested range: 2–10 seconds between requests)
  must be implemented in any production fetcher to reduce rate-limit and IP-ban risk.
- **Session / cookie / auth:** The current working profile uses a clean 8-header request
  (no Cookie, no Authorization). If future probes begin returning `403`, re-investigate
  the session/cookie requirement before adding credentials.

---

## 9. Raw Payload Storage Policy

- Each (symbol, section, run_id) fetch saves exactly two files:
  - `payload.json`: the raw HTTP response body
  - `metadata.json`: a structured record containing `symbol`, `section`, `run_id`,
    `http_status`, `access_status`, `raw_path`, `content_hash`, `crawled_at`,
    `target_url`, `diagnostic_target`, and `dataset`
- Path convention (suggested):
  `data/raw/vietcap_iq/fa/run_id={run_id}/{dataset}/payload.json`
- `diagnostic_target` must be `fa-direct` for FA endpoint payloads.
- `access_status` must be `verified` for a payload to be eligible for parsing.
- Raw payloads must be saved before parsing. The parser reads from disk, not from a
  live network response.
- Do not commit raw payloads containing cookies, tokens, or personal data to git.

---

## 10. Manifest Format

The full-history manifest is a deterministic planning artifact. It is generated by
`scripts/plan_vietcap_iq_fa_full_history_manifest.py` without any network requests.

Columns:

| Column | Description |
|---|---|
| `symbol` | Ticker symbol (e.g., `VCI`) |
| `section` | FA section name (e.g., `BALANCE_SHEET`) |
| `request_type` | HTTP method; currently `GET` for all FA endpoints |
| `endpoint_template_or_name` | Endpoint URL template with `{symbol}` and `{section}` placeholders |
| `status` | Readiness status: `planned_pending_gates` until all gates are met |
| `reason` | Pipe-delimited list of open gates blocking this fetch row |
| `requires_network` | `yes` — all FA fetch rows require live network access |
| `requires_mapping` | `yes` — DB write requires a verified metric code-to-name mapping |
| `requires_pit_validation` | `yes` — backtest requires confirmed `publicDate` PIT semantics |
| `planned_raw_storage_prefix` | Local path prefix where raw payloads would be saved |
| `notes` | Free-text notes about section probe status or known risks |

Output format: CSV. Sorted deterministically by `(symbol, section)`.

---

## 11. Parser Input / Output Contract

### Input

- A list of metadata dicts, each with keys: `run_id`, `symbol`, `section`,
  `diagnostic_target` (must be `fa-direct`), `access_status` (must be `verified`),
  `raw_path` (must exist on disk), `content_hash`, `crawled_at`, `dataset`.
- Payloads must conform to the confirmed envelope shape:
  `{"data": {"quarters": [...], "years": [...]}, "serverDateTime": "...", ...}`.

### Output

- Long-format CSV or JSONL with columns defined by `_LONG_FORMAT_COLUMNS` in the parser.
- One row per `(symbol, section, period_label, line_item_code)`.
- `line_item_name` is always empty; populated only after a verified mapping is loaded.
- `value_status` is exactly one of `present`, `zero`, or `missing`.
- `public_date_semantics` is always `candidate_availability_publication_date_unconfirmed`.
- `availability_status` is always `unknown_until_publicDate_validated`.
- `parser_warning` carries pipe-delimited flags per row.

### Invariants

- No DB write.
- No live network request.
- No invented line-item names.
- Deterministic sort by `(symbol, section, source_period_label, line_item_code, source_run_id)`.

---

## 12. Canonical Long-Format Fact Schema

| Column | Type | Notes |
|---|---|---|
| `source_name` | string | Always `vietcap_iq` |
| `symbol` | string | Ticker (e.g., `VCI`) |
| `organ_code` | string | `organCode` from payload row |
| `statement_type` | string | Same as `section` |
| `section` | string | `BALANCE_SHEET`, `INCOME_STATEMENT`, etc. |
| `period_type` | string | `quarter` or `year` |
| `fiscal_year` | integer | `yearReport` |
| `fiscal_quarter` | integer or empty | `1–4` for quarterly; empty for annual |
| `length_report` | integer | Raw `lengthReport` from payload |
| `source_period_label` | string | `{year}Q{q}` or `{year}Y` |
| `public_date` | string | `publicDate` copied verbatim — candidate field only |
| `public_date_semantics` | string | Always `candidate_availability_publication_date_unconfirmed` |
| `line_item_code` | string | Opaque metric code (e.g., `bsa1`) |
| `line_item_name` | string | **Always empty** until verified mapping is loaded |
| `value` | numeric or empty | Raw numeric value; empty string if null |
| `value_status` | string | `present`, `zero`, or `missing` |
| `unit` | string | Empty — unit not present in payload |
| `currency` | string | Empty — currency not confirmed in payload |
| `source_run_id` | string | Run ID of the diagnostic that fetched the payload |
| `source_dataset` | string | Dataset name |
| `source_content_hash` | string | SHA-256 or similar hash of raw payload |
| `source_payload_path` | string | Absolute path to `payload.json` on disk |
| `source_server_datetime` | string | `serverDateTime` from payload envelope |
| `crawled_at` | string | ISO datetime when the payload was saved |
| `availability_status` | string | Always `unknown_until_publicDate_validated` |
| `parser_warning` | string | Pipe-delimited warning flags per row |

---

## 13. Natural Key / Uniqueness Contract

The natural composite key for a long-format fact row is:

```
(source_run_id, symbol, section, source_period_label, line_item_code)
```

This key must be unique within any single parse run. The `_check_duplicate_keys` check
enforces this. Across multiple parse runs (e.g., a full-universe production fetch run
versus a re-fetch run), rows from different `source_run_id` values are treated as separate
observations and are **not** deduplicated by the parser.

Future DB write design must define a canonical DB-level uniqueness key that can handle
re-ingestion from multiple runs (e.g., a dedup/upsert policy on
`(symbol, section, source_period_label, line_item_code)` ignoring `source_run_id`).

---

## 14. Null vs Zero Policy

- `value=None` in the source payload → `value_status=missing`, `value=""` in CSV output.
- `value=0.0` in the source payload → `value_status=zero`, `value=0.0` in CSV output.
- These two states must never be collapsed. `nos*` columns for non-securities firms are
  expected to be entirely `missing`; collapsing `missing` to `zero` would introduce false
  financial data.
- The parser enforces this distinction via `_value_status()` and `_check_value_status_validity()`.

---

## 15. Metric Mapping Policy

- **Current state:** Mapping payloads retrieved for 4 firm types: VCI (securities, run
  `20260610T025420Z`), VCB (bank, `20260610T033851Z`), BVH (insurance, `20260610T033856Z`),
  SSI (securities, `20260610T033900Z`; identical to VCI). SSI confirmed that securities mapping
  is firm-type-consistent. Union: 1793 codes, 88 name conflicts. Union coverage: 89.4% BS /
  92.3% IS / 86.7% CF — still below 95% gate. `line_item_name` remains empty for all parsed
  fact rows.
- **Key finding:** The mapping endpoint is firm-type-specific. VCB returns bank codes (`isb*`,
  `bsb*`, `cfb*`); BVH returns insurance codes (`isi*`, `bsi*`). A universal mapping requires
  either per-symbol querying or a union with conflict resolution.
- **What is needed:** Coverage ≥ 95% per section is still required before parser integration
  proceeds. The integration strategy has been documented (Option C).
- **Sources confirmed:** `/financial-statement/metrics` endpoint returns the mapping.
  Additional firm types (fund management, etc.) may cover residual uncovered codes.
- **Integration strategy:** Option C (Hybrid gated mapping) is the documented recommended
  approach — per-symbol mapping as primary, union consensus as fallback for conflict-free,
  section-matched codes, with full provenance tracking. See
  `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` for the full design.
  The strategy is **designed, not implemented.** Parser code has not been changed.
- **Firm-type determination:** How the parser selects the correct firm-type mapping group for
  each symbol is designed in `docs/data_sources/vietcap_iq_fa_firm_type_determination.md`.
  Classification uses `company_type_code` from the Vietcap IQ universe CSV (`NH`=bank,
  `BH`=insurance, `CK`=securities, others=general) with an explicit override table for the
  four directly-probed symbols (VCI, SSI, VCB, BVH). Planner script:
  `scripts/plan_vietcap_iq_fa_firm_type_mapping.py`. Not yet integrated into the parser.
- **Future integration rule:** When the parser integration is eventually implemented, it
  must populate `line_item_name_en` (and `line_item_name_vi`) via the hybrid lookup, not
  the legacy `line_item_name` column. The `_check_no_invented_names` guard must still pass —
  conflicting, uncovered, and section-mismatched codes must leave `line_item_name_en` empty.
  The existing `line_item_name` column must remain empty until a deliberate deprecation or
  migration decision is separately documented and reviewed.
- **Mapping integration does not unblock DB write by itself.** DB write remains blocked until
  PIT validation, QuestDB schema design, full-history fetch, and all §17 quality gates are
  cleared — independent of whether mapping integration is implemented.
- **Do not invent names.** Prefix-level inferences (`bsa*` ≈ balance sheet assets) are
  not verified and must not be written into any name field.
- **Coverage threshold:** The mapping must cover ≥95% of observed codes per section before
  the mapping gate in §17 can be marked met.
- **Current parser output:** `line_item_name` remains empty in all current parser output.
  `line_item_name_en` does not yet exist in parser output — it is a planned future column.

---

## 16. PIT Availability Policy

- `publicDate` is present in all parsed rows. Its value follows ISO date format.
- **It is a candidate availability field only.** Its exact semantics — whether it
  represents the exchange filing date, the auditor sign-off date, the date Vietcap
  entered the data, or another event — have **not** been confirmed.
- **Do not use `publicDate` as a confirmed point-in-time availability date** for any
  backtest, look-ahead avoidance, or historical simulation.
- PIT validation requires cross-checking `publicDate` values against authoritative
  filing records (HOSE/HSX, HNX, or the State Securities Commission of Vietnam) for a
  sample of symbols and periods.
- Until PIT is validated, `availability_status` remains `unknown_until_publicDate_validated`
  for all fact rows, and the `WARNING_PIT` flag is emitted in `parser_warning`.

---

## 17. DB Write Readiness Gates

All of the following gates must be satisfied before any DB write is implemented:

| Gate | Current Status |
|---|---|
| Metric mapping verified and coverage ≥ threshold | **Not met** — VCI-only 62.8%/43.6%/65.8%; union (VCI+VCB+BVH+SSI) 89.4%/92.3%/86.7% (BS/IS/CF); no section reaches 95%; 88 name conflicts in union |
| `publicDate` PIT semantics confirmed | **Not met** — unconfirmed |
| Canonical DB schema designed and reviewed | **Not met** — schema defined in long-format only; QuestDB table design not implemented |
| Natural key / dedup policy for re-ingestion defined | **Not met** — design exists in concept only |
| Full-history FA fetch tested for at least a small symbol set | **Not met** — only 3 saved payloads / 2 symbols / 3 tested cases have been reviewed so far; no fetcher |
| Parser `--strict` mode passes on full-universe sample | **Not met** — only 3 saved payloads tested |
| QuestDB migration implemented and reviewed | **Not met** |
| Ingestion tests cover round-trip (fetch → parse → write → query) | **Not met** |

---

## 18. Backtest Readiness Gates

All DB write gates (§17) must be met first. Additionally:

| Gate | Current Status |
|---|---|
| `publicDate` PIT semantics validated (gate §17 item 2) | **Not met** |
| Full-history FA data ingested to DB for at least the backtest symbol universe | **Not met** |
| Data-completeness audit on ingested FA data | **Not met** |
| Strategy definition that uses FA signals | **Not met** |
| Backtest framework selected or designed | **Not met** |

---

## 19. Production Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Endpoint requires session/cookie for certain symbols or after rate limiting | Medium | Monitor access_status; implement clean-profile retry before adding cookie/auth handling |
| `publicDate` turns out to be data-entry date, not filing date — invalidates PIT use | High | Do not use for PIT until cross-validated; see §16 |
| Metric codes are version-specific and may change across API versions | Medium | Record API version in metadata if discoverable; version-stamp the mapping |
| `nos*` null patterns may differ for unfamiliar firm types beyond securities/general | Low | `_check_nos_pattern` emits warnings for mixed patterns; review before DB write |
| Full-universe fetch (1,598 × N sections) may trigger IP throttling or ban | High | Sequential fetch with random sleep; start with a tiny controlled batch |
| Mapping never becomes available (obfuscated codes) | High | If no mapping endpoint is found, evaluate whether partial naming from prefix groups is acceptable or whether raw codes are sufficient for downstream use |
| `publicDate` absent for some symbols or future API versions | Low | `fail_on_missing_public_date` flag available; default is permissive |

---

## 20. Next Implementation Steps

**All steps below require human review and approval before execution.**

| Step | Depends On | Description |
|---|---|---|
| 1. Re-probe `/financial-statement/metrics` | ~~Network access restored~~ | **Done** — HTTP 200, `run_id=20260610T025420Z`; 1078 codes, coverage 43–66%; see `vietcap_iq_fa_mapping_cashflow_probe.md` |
| 2. Probe CASH_FLOW section for VCI and FPT | ~~None~~ | **Done** — `run_id=20260610T025429Z` (VCI) and `20260610T025440Z` (FPT); identical envelope; 33Q + 8Y; 225 codes; publicDate non-null |
| 3. Probe 3–5 additional symbols across HOSE/HNX/UPCOM | None | Check that payload shape is consistent across firm types |
| 4. Build metric mapping integration | Step 1; strategy designed | **Strategy designed** — Option C (Hybrid gated) documented in `vietcap_iq_fa_mapping_integration_strategy.md`; parser not yet modified; `line_item_name` still empty |
| 5. Run mapping coverage check | Step 4 | Verify ≥ threshold coverage before DB gate discussion |
| 6. Validate `publicDate` PIT semantics | External filing records | Cross-check 5–10 sample rows against HOSE/HNX filing dates |
| 7. Design canonical DB schema | Steps 4–6 complete | Define QuestDB table(s), dedup key, and upsert policy |
| 8. Build a production FA fetcher | Steps 1–3 complete; rate-limit behavior reviewed | Sequential fetcher with checkpoint, sleep, and raw-payload preservation |
| 9. Small-batch end-to-end dry run | Steps 4–8 complete | Fetch → parse → local output for 5–10 symbols; no DB write yet |
| 10. Implement DB write | All §17 gates met | QuestDB migration + write; verify with a query round-trip |
| 11. Implement backtest | All §18 gates met | Not started until §10 is proven |

**Hard constraints that apply to all steps:**
- Do not implement DB writes until §17 gates are all met.
- Do not implement backtests until §18 gates are all met.
- Do not invent metric names.
- Do not treat `publicDate` as confirmed PIT.
- Do not fetch the full 1,598-symbol universe until a small controlled batch has been
  reviewed and rate-limit behavior is understood.

---

## Related Documents

- `docs/data_sources/vietcap_iq_fa_payload_shape_review.md` — payload structure review
- `docs/data_sources/vietcap_iq_fa_shape_cross_check.md` — cross-section/symbol check
- `docs/data_sources/vietcap_iq_fa_parser_dry_run.md` — parser command and output
- `docs/data_sources/vietcap_iq_fa_metric_mapping_discovery.md` — mapping probe results
- `docs/data_sources/vietcap_iq_fa_mapping_cashflow_probe.md` — mapping re-probe and CASH_FLOW probe results
- `docs/data_sources/vietcap_iq_fa_mapping_coverage_bank_probe.md` — bank/insurance union coverage and Options A/B/C overview
- `docs/data_sources/vietcap_iq_fa_mapping_integration_strategy.md` — integration strategy design (Option C recommended)
- `docs/data_sources/vietcap_iq_fa_parser_hardening.md` — validation checks and test coverage
- `docs/ingestion_v2_schema_plan.md` — overall ingestion V2 context
- `scripts/parse_vietcap_iq_fa_payloads_dry_run.py` — parser implementation
- `scripts/plan_vietcap_iq_fa_full_history_manifest.py` — manifest planner (dry-run)
