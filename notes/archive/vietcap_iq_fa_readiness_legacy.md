# Vietcap IQ FA Ingestion V2 Readiness — Archived Policy Sections

**Source:** `docs/data_sources/vietcap_iq_fa_ingestion_v2_readiness.md` (compacted 2026-06-11)  
**Why archived:** These policy and schema sections exceeded the 1500-word limit and contain
detail better suited to operational implementation than to the compact gate-table function of
the readiness doc. The core gate tables (DB write gates, backtest gates, next steps) remain in
the canonical readiness doc.

---

## §4. Full-History FA Fetch Policy

- **Gate before full-history fetch:** Mapping coverage ≥ 95% per section AND `publicDate` PIT semantics confirmed.
- **Scope:** All symbols in the listed-market universe (1,598 candidates). Do not fetch index rows (`is_index=True`).
- **Rate-limit:** Sequential symbol fetching with random sleep 1–3 seconds between requests and 5–10 seconds between sections. No async or concurrent fetching.
- **Checkpoint:** A checkpoint JSON records completed, failed, and pending symbols. Re-run after crash without re-fetching completed symbols.
- **Batch size:** Process one section (BS / IS / CF) for all symbols before moving to the next section.
- **Storage:** Save raw `payload.json` and `metadata.json` for every symbol × section × period (quarterly and annual) under `data/raw/httpx_diagnostic/source=vietcap_iq/`.

---

## §5. Symbol Universe Policy

- **Source:** `data/processed/dry_run/vietcap_iq_universe/<run_id>/instrument_universe.csv`
- **Filter:** `is_index=False` and exchange in `{HOSE, HNX, UPCOM}` — 1,598 candidates.
- **Not final tradable assets:** Liquidity and data-completeness filters applied during strategy phase.
- **Universe refresh:** Re-fetch universe before each full-history FA fetch run.
- **Index rows:** Store in a separate index universe; do not fetch FA for index rows.

---

## §6. Supported Statement Sections (detail)

| Section | Probe | Parser | Code count | Notes |
|---|---|---|---|---|
| `BALANCE_SHEET` | VCI + FPT | Done | 331 codes | `bss*` / `bsb*` / `bsi*` / `bsa*` prefixes |
| `INCOME_STATEMENT` | VCI | Done | 181 codes | `iss*` / `isb*` / `isi*` / `isa*` prefixes |
| `CASH_FLOW` | VCI + FPT | Done | 225 codes | `cfs*` / `cfb*` / `cfa*` prefixes |
| NOTE | Not probed | Not implemented | ~642 (mapping only) | Off-balance-sheet notes |

---

## §7. Period and Frequency Policy

- **Quarterly:** `data.quarters` — 33 quarters per saved payload (VCI, FPT).
- **Annual:** `data.years` — 8 years per saved payload (VCI, FPT).
- **No daily or monthly FA data observed.** FA payloads contain only quarterly and annual periods.
- **Period label format:** Quarters use `YYYY-QN` style; annual use `YYYY` style.
- **Historical depth:** Observed quarterly depth to ~2018 for VCI/FPT. Full depth unknown without a larger probe sample.

---

## §8. Rate-Limit / Retry / Cache Policy

- Use random sleep 1–3s between symbol requests; 5–10s between sections.
- Retry on HTTP 429 (Too Many Requests) with exponential back-off (max 3 retries, ceiling 60s).
- Retry on HTTP 5xx (server error) with linear back-off (max 2 retries, 30s each).
- Do not retry on HTTP 4xx (client error) — log and mark symbol as failed.
- Cache raw payloads on disk by `run_id`; a subsequent run must not re-fetch if a valid cached payload exists for that `(symbol, section, run_id)`.

---

## §9. Raw Payload Storage Policy

- Store exact response bytes as `payload.json`.
- Store request metadata (headers sent, endpoint, HTTP status, timestamp) as `metadata.json`.
- Compute `content_hash` (SHA-256) over raw bytes and store in metadata.
- Path pattern: `data/raw/httpx_diagnostic/source=vietcap_iq/run_id=<run_id>/<dataset>/`
- Do not modify or re-encode the raw payload.
- Preserve `null` and `0.0` as distinct at all stages; never collapse to a single representation.

---

## §10. Manifest Format

Output of `scripts/plan_vietcap_iq_fa_full_history_manifest.py`:

| Field | Notes |
|---|---|
| `symbol` | Stock ticker |
| `section` | `BALANCE_SHEET`, `INCOME_STATEMENT`, or `CASH_FLOW` |
| `period_type` | `quarterly` or `annual` |
| `fetch_scope` | `full_history` |
| `mapping_group` | `bank` / `insurance` / `securities` / `general` |
| `mapping_source_symbol` | Symbol whose mapping payload to use |
| `firm_type_confidence` | `high` / `medium` / `none` |
| `estimated_rows` | Estimated fact rows after parsing |
| `checkpoint_status` | `pending` / `completed` / `failed` |
| `error_notes` | Error reason if failed |

---

## §11. Parser I/O Contract (pre-implementation notes)

**Inputs:**
- One or more saved `payload.json` files (one per symbol × section × period)
- Optionally: `--mapping-csv` (per-symbol mapping), `--union-csv` (consensus union), `--firm-type-plan-csv`

**Outputs:**
- `all_facts.csv`: long-format, one row per (symbol, section, period, line_item_code)
- `all_errors.csv`: parse errors and validation failures
- `validation_report.json`: summary of all validation checks

**Key invariants:**
- `line_item_name` always empty (legacy, backwards-compat only)
- `value=None` → `value_status=missing`; `value=0.0` → `value_status=zero`
- Deterministic sort: `(section, symbol, period_type, period, line_item_code)`
- `--strict` mode exits non-zero on any validation error

---

## §12. Schema (long-format output columns)

| Column | Type | Notes |
|---|---|---|
| `symbol` | string | Stock ticker |
| `section` | string | `BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW` |
| `period_type` | string | `quarterly` or `annual` |
| `period` | string | `2024-Q1` or `2024` |
| `publicDate` | string | ISO date string; PIT semantics unconfirmed |
| `line_item_code` | string | Opaque metric code (e.g., `bsa1`) |
| `line_item_name` | string | Always empty (legacy) |
| `line_item_name_en` | string | English name via Option C resolver; empty if not covered/conflicting |
| `line_item_name_vi` | string | Vietnamese name; empty if not covered |
| `value` | string | Numeric string or `""` for missing |
| `value_status` | string | `present`, `zero`, or `missing` |
| `nos_column` | string | `nos*` column name (securities firms only) |
| `nos_value` | string | `nos*` value; null for non-securities firms |
| `mapping_status` | string | One of 6 values: `primary`, `consensus_fallback`, `conflict_skipped`, `not_covered`, `no_mapping_available`, `section_mismatch` |
| `mapping_source_symbol` | string | Symbol whose mapping was used |
| `mapping_source_run_id` | string | `run_id` of the mapping payload |
| `mapping_conflict` | string | `true` if in 88-conflict set |
| `mapping_group` | string | `bank` / `insurance` / `securities` / `general` |
| `availability_status` | string | `unknown_until_publicDate_validated` |

---

## §13. Natural Key Contract

Candidate natural key for dedup: `(symbol, section, period_type, period, line_item_code)`.

- This key is stable across re-fetches of the same payload.
- A symbol's FA data can be re-fetched; the natural key ensures idempotent ingestion if values are unchanged.
- If a value changes on re-fetch (source restatement), the new row replaces the old under QuestDB dedup.
- `publicDate` is NOT part of the natural key — it is a PIT candidate field that may change if Vietcap IQ restates it.

---

## §19. Production Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Vietcap IQ API endpoint changes | Medium | Save raw payloads; parser version in output |
| `publicDate` semantics are wrong | High | Do not use for backtest until validated |
| Mapping coverage drops below current level | Low | Union mapping is computed offline; re-run if new payloads arrive |
| Symbol universe changes (de-listings, new listings) | Medium | Re-fetch universe before each full-history run |
| Rate-limiting or IP ban during full-history fetch | Medium | Sequential fetch with random sleep; checkpoint for resume |
| Parser version mismatch with saved outputs | Low | `parser_version` recorded in all output rows |
