---
title: vietcap_iq_fa_shape_cross_check
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Vietcap IQ FA Payload Shape Cross-Check

## Purpose

The original payload-shape review (`vietcap_iq_fa_payload_shape_review.md`) covered only one symbol (`VCI`) and one section (`BALANCE_SHEET`). This document cross-checks whether:

1. The clean 8-header `fa-direct` access profile generalises to another section (same symbol).
2. The payload shape generalises to another symbol (same section).

These are prerequisites before writing a parser dry-run.

---

## Diagnostics Run

Both runs used the same clean 8-header profile: no warm-up, no Cookie, no Authorization, no `sec-ch-ua*` headers.

### Run 1 — Section generalisation: VCI INCOME_STATEMENT

```
python scripts/probe_vietcap_iq_fa_httpx_session.py \
  --diagnostic-target fa-direct \
  --symbol VCI \
  --section INCOME_STATEMENT \
  --referer-style trading-company-page
```

### Run 2 — Symbol generalisation: FPT BALANCE_SHEET

```
python scripts/probe_vietcap_iq_fa_httpx_session.py \
  --diagnostic-target fa-direct \
  --symbol FPT \
  --section BALANCE_SHEET \
  --referer-style trading-company-page
```

---

## Results

| Field | VCI BALANCE_SHEET (reference) | VCI INCOME_STATEMENT | FPT BALANCE_SHEET |
|---|---|---|---|
| `run_id` | `20260609T035318Z` | `20260609T075846Z` | `20260609T075857Z` |
| `symbol` | `VCI` | `VCI` | `FPT` |
| `section` | `BALANCE_SHEET` | `INCOME_STATEMENT` | `BALANCE_SHEET` |
| `http_status` | `200` | `200` | `200` |
| `access_status` | `verified` | `verified` | `verified` |
| `byte_size` | `354,443` | `197,327` | `358,820` |
| Top-level type | `dict` | `dict` | `dict` |
| Top-level keys | `code, data, exception, msg, serverDateTime, status, successful, traceId` | same | same |
| `data` keys | `quarters, years` | `quarters, years` | `quarters, years` |
| `data.quarters` type | `list` | `list` | `list` |
| `data.quarters` length | `33` | `33` | `33` |
| `data.years` type | `list` | `list` | `list` |
| `data.years` length | `8` | `8` | `8` |
| `yearReport` range (Q) | `2018–2026` | `2018–2026` | `2018–2026` |
| `lengthReport` values (Q) | `1,2,3,4` | `1,2,3,4` | `1,2,3,4` |
| `lengthReport` values (Y) | `5` | `5` | `5` |
| Metric column count | `331` | `181` | `331` |
| Metric prefix groups | `bsa*(124), bsb*(64), bsi*(46), bss*(54), nos*(43)` | `isa*(25), isb*(17), isi*(75), iss*(64)` | `bsa*(124), bsb*(64), bsi*(46), bss*(54), nos*(43)` |
| `publicDate` present | All rows | All rows | All rows |
| `publicDate` non-null | Yes (33/33 Q, 8/8 Y) | Yes (33/33 Q, 8/8 Y) | Yes (33/33 Q, 8/8 Y) |
| `organCode` | `VCSC` | `VCSC` | `FPT` |
| Wide-format | Yes | Yes | Yes |
| Null % (quarters) | `0.5%` | `0.8%` | `13.7%` |
| Zero % (quarters) | `74.5%` | `73.8%` | `61.2%` |
| Non-zero % (quarters) | `25.0%` | `25.4%` | `25.0%` |

---

## Comparison with Reference Payload

### Section generalisation (VCI: BALANCE_SHEET → INCOME_STATEMENT)

**Access:** HTTP 200 with the same clean 8-header profile. The access pattern generalises across sections for the same symbol.

**Structure:** Period encoding (`yearReport`, `lengthReport`, `publicDate`, `updateDate`, `organCode`, `ticker`, `createDate`) is **identical** across both sections — same 7 metadata fields, same range, same `lengthReport` convention.

**Metric columns:** Different prefix family:
- `BALANCE_SHEET` → `bs{sector}*` (`bsa*`, `bsb*`, `bsi*`, `bss*`, `nos*`): 331 columns
- `INCOME_STATEMENT` → `is{sector}*` (`isa*`, `isb*`, `isi*`, `iss*`): 181 columns

The prefix pattern is consistent: `{statement_abbrev}{sector_abbrev}{number}` where `bs`=balance sheet, `is`=income statement, `a`=general, `b`=bank, `i`=insurance, `s`=securities. This strongly suggests other sections (e.g., cash flow) will follow the same convention with a different two-letter statement abbreviation.

**Null/zero density:** Very similar (`~74%` zero, `~25%` non-zero, `~0.5–0.8%` null) — the sparsity pattern is section-consistent for the same company.

### Symbol generalisation (BALANCE_SHEET: VCI → FPT)

**Access:** HTTP 200 with the same clean 8-header profile. The access pattern generalises across symbols for the same section.

**Structure:** Period encoding is **identical** — same 7 metadata fields, same `yearReport` range (2018–2026), same `lengthReport` encoding, same `publicDate` coverage. `organCode` differs (`VCSC` for VCI, `FPT` for FPT); `ticker` matches the symbol in both cases.

**Metric columns:** **Identical** 331-column set for both VCI and FPT on `BALANCE_SHEET`. The column schema is section-level, not symbol-level.

**Null/zero density by prefix group (quarters):**

| Prefix | VCI null/zero/nonzero | FPT null/zero/nonzero | Interpretation |
|---|---|---|---|
| `bsa*` (124 cols, general) | 1% / 62% / 38% | 1% / 33% / 66% | FPT uses more general BS items — consistent with tech firm having diverse assets |
| `bsb*` (64 cols, bank) | 0% / 99% / 1% | 0% / 98% / 2% | Both near-zero — neither is a bank |
| `bsi*` (46 cols, insurance) | 1% / 99% / 0% | 2% / 98% / 0% | Both near-zero — neither is an insurance firm |
| `bss*` (54 cols, securities) | 0% / 64% / 36% | 0% / 100% / 0% | VCI is a securities firm (populated); FPT has all zeros |
| `nos*` (43 cols, off-B/S notes) | 0% / 63% / 37% | **100% / 0% / 0%** | VCI has customer securities data; FPT has all nulls — column group does not apply to FPT |

The `nos*` group is **entirely null for FPT** and significantly populated for VCI. This is the primary source of FPT's higher null rate (13.7% vs 0.5%). It is not a data quality issue — it reflects that off-balance-sheet securities custody notes are specific to the securities industry.

**Parser implication:** `null` and `0.0` must be treated differently:
- `0.0` = line item exists for this company type but has a zero value this period
- `null` = line item does not apply to this company type (or data was not captured)

In the long-format `financial_statement_facts` schema, null rows should either be omitted or carried with a flag (`not_applicable` / `no_data`).

---

## Findings

### Access profile generalisation

The clean 8-header `fa-direct` profile returns HTTP 200 for:
- Multiple sections of the same symbol (VCI BALANCE_SHEET and INCOME_STATEMENT)
- Multiple symbols for the same section (VCI and FPT, BALANCE_SHEET)

This suggests the access pattern is robust across at least these three combinations.

### Period encoding generalisation

`yearReport`, `lengthReport`, `publicDate`, `updateDate` are present and non-null for all rows across all three payloads. The period extraction logic will be the same for all sections and symbols.

### Metric schema generalisation

- The column schema is **section-level** (the same 331 columns appear for all symbols on BALANCE_SHEET; the same 181 columns appear for VCI INCOME_STATEMENT).
- Metric codes within a section are shared across symbols — a single column-name mapping table per section will cover all symbols.
- Different sections use different prefix families (`bs*` vs `is*`); a shared parser needs to apply the correct column list per section.

### Null vs zero semantics

For a given section, some prefix groups may be entirely null for certain company types (e.g., `nos*` for non-securities firms). The parser must preserve this distinction and not treat null as zero.

---

## Parser Implications

The three payloads are **structurally compatible** with a shared dry-run parser. Required capabilities:

1. **Period extraction:** `(yearReport, lengthReport)` → `(fiscal_year, fiscal_quarter, period_type)` — identical across all three.
2. **Wide-to-long pivot:** For each metric column `k` in a row, emit one fact record with `line_item_code=k`, `value=row[k]`. Works identically across sections and symbols.
3. **Section-specific column list:** The parser must know which columns are metric codes vs metadata fields. Metadata fields (`ticker`, `organCode`, `yearReport`, `lengthReport`, `publicDate`, `updateDate`, `createDate`) are the same for all sections; metric columns differ by section.
4. **Null handling:** Emit null-valued facts as `value=null, availability_status=not_applicable` (or omit them); do not coerce to zero.
5. **Column name mapping:** A separate `line_item_code → line_item_name` mapping is still needed. Not present in the payload.

**Parser dry-run can start** for at least BALANCE_SHEET and INCOME_STATEMENT with VCI and FPT payloads. The parser should remain a local dry-run (CSV/report output only) with no DB write until the column-name mapping and multi-section schema are finalised.

---

## PIT / Backtest Warning

`publicDate` is present and non-null for all rows in all three payloads. It is a **candidate availability/publication field**. Its exact semantics — whether it represents the exchange filing date, the auditor sign-off date, or the date Vietcap entered the data — have not yet been confirmed against authoritative filing records.

- **Usable:** These payloads are suitable for current-snapshot fundamental analysis prototyping.
- **Not yet safe:** PIT semantics of `publicDate` must be confirmed against an authoritative source before any historical point-in-time backtest uses this data.

---

## Next Recommended Steps

1. **Write a dry-run parser** for BALANCE_SHEET (and optionally INCOME_STATEMENT) using the three saved payloads. Output should be local CSV/report only — no DB write.
2. **Find or probe a column-name mapping endpoint.** Without `line_item_name`, the long-format output will contain only opaque codes (`bsa1`, `isa25`, etc.).
3. **Probe additional sections** (e.g., `CASH_FLOW`) to verify prefix convention and column count.
4. **Confirm `publicDate` semantics** against one or two known VCI/FPT filing dates from exchange records before using `publicDate` as a point-in-time anchor in backtest.
5. **No full-universe fetch, no DB write, no backtest** until dry-run parser and `publicDate` semantics are reviewed.
