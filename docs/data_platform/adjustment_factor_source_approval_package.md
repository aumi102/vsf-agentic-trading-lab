---
title: adjustment_factor_source_approval_package
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjustment Factor Source Approval Package

## 1. Why this is needed

Adjusted OHLC is mandatory before hardened Backtrader or VN100 work. Raw OHLC
cannot be treated as adjusted data, and raw close must never be used as adjusted
close by default. Any adjusted series must be traceable to a trusted adjusted
close, factor, dividend, split, or corporate-action source.

Without traceable adjusted OHLC, backtests can silently mishandle dividends,
splits, and other corporate actions. That would make signals, fills, risk
metrics, Sharpe rankings, and buy-and-hold comparisons unreliable.

## 2. Current implemented foundation

The repo already has the local foundation needed to evaluate a source after it
is approved:

- adjusted OHLC schema columns on `daily_prices`;
- factor provenance columns: `adjustment_source_id`, `adjustment_raw_path`,
  and `adjustment_method`;
- adjusted OHLC readiness gate;
- local factor application for explicit symbols;
- source adapter fixtures for adjusted-close and corporate-action payloads;
- controlled local payload verification for `FPT`, `VNM`, and `VCB`.

Backtrader and VN100 work remains blocked until a real source is approved,
factor records are verified, adjusted OHLC is populated, and readiness passes.

## 3. What is still missing

The missing decision is the real source of adjustment evidence. The repo still
needs:

- approved real adjusted-close or corporate-action source;
- real source payload evidence;
- ETL integration for the approved source;
- small-symbol adjusted readiness pass before any Backtrader unblock.

## 4. Candidate source options

1. Trusted vendor adjusted-close endpoint.

Pros: direct factor derivation from `adjusted_close / close`; simple validation
against current factor-record contracts. Risks: vendor methodology may be opaque
or differ from exchange treatment. Required fields: symbol, trade date, raw
close, adjusted close. Provenance needed: source ID, raw payload path, vendor
method/version if available.

2. Vendor corporate-action endpoint.

Pros: more transparent event-level derivation from dividends, splits, and other
actions. Risks: more implementation complexity and more edge cases around
effective dates. Required fields: symbol, event date, effective/ex-date, action
type, cash or split values, factor or inputs enough to derive factor. Provenance
needed: source ID, raw payload path, action identifiers, derivation method.

3. Official exchange/company corporate-action source if available.

Pros: strongest audit trail when complete and timely. Risks: coverage and format
may be fragmented across exchange pages, company IR pages, PDFs, or disclosures.
Required fields: symbol or issuer, event/effective date, action type, values
needed to derive factor. Provenance needed: official URL or saved raw path,
content hash, disclosure date, parsing method.

4. Manual curated factor fixture only for development, not production.

Pros: useful for deterministic tests and small local dry-runs. Risks: not a
production source and easy to become stale. Required fields: symbol, trade date,
factor, source ID, raw path, method. Provenance needed: curator note, source
reference, and fixture path.

## 5. Minimum acceptance criteria

A source is usable only if it:

- provides adjusted close or explicit factor/corporate-action data enough to
  derive a factor;
- aligns symbols and dates with local OHLC rows;
- carries `source_id` and `raw_path` provenance;
- can be verified for `FPT`, `VNM`, and `VCB` first;
- produces factor records accepted by PR #37 verification;
- lets local factor application populate adjusted OHLC and pass readiness;
- never treats raw close as adjusted close.

## 6. Proposed small-symbol verification plan

Use `FPT`, `VNM`, and `VCB`.

1. Collect one small payload per source/symbol.
2. Store it under an ignored raw/evidence path unless intentionally curated.
3. Run `scripts/verify_factor_source_payload.py`.
4. Convert the payload to factor records.
5. Apply to a local DB with `scripts/apply_adjustment_factors.py --execute`.
6. Run `scripts/check_adjusted_ohlc_readiness.py`.
7. Document the result and blockers.

## 7. Questions for mentor

1. Which source should be treated as approved for adjusted close or corporate actions?
2. Is vendor adjusted close acceptable, or must factor be derived from corporate actions?
3. Should we start with `FPT`, `VNM`, `VCB`, or a VN100 subset?
4. What backtest date range should adjusted readiness cover first?
5. Are transaction cost/slippage assumptions still separate from this source approval?

## 8. Recommended next PR after approval

After mentor approval, the next PR should implement a source-specific adapter for
the approved source, capture raw evidence, generate factor records, apply them
to a small explicit symbol set, and require adjusted readiness to pass. Only
after that should Backtrader small-subset work start.
