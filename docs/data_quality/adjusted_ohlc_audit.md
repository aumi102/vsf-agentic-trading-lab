# Adjusted OHLC source audit

- generated_at: `2026-06-24T08:24:10Z`
- questdb_url: `http://localhost:9000`
- scope_symbols: `FPT, VNM, HPG, A32, AAA, AAH, AAM, AAN, AAS, AAT, AAV, ABB, ABC, ABI, ABR, ABS, ABT, ABW, ACB, ACC, ACE, ACG, ACL, ACM, ACS, ACV, ADC, ADG, ADP, ADS, AFX, AG1, AGF, AGG, AGM, AGP, AGR, AGX, AIC, AIG, ALC, ALT, ALV, AMC, AME, AMP, AMS, AMV, ANT, ANV, APC, APF, APG`
- overall_status: `WARN`

## Result

Adjusted OHLC is internally consistent with a close-derived factor for the audited rows, but the current data remains source-unverified because adjusted OHLC is raw-equivalent and `adjustment_status` contains `adjusted_price_missing_warn`.

This is a validation WARN, not a fabricated PASS. Backtests must continue to disclose the caveat.

## Column availability

- missing_raw_columns: `none`
- missing_adjusted_columns: `none`
- available_evidence_columns: `adjustment_factor, adjustment_status, raw_path, source_id`

## Summary

```json
{
  "overall_status": "WARN",
  "symbols_audited": 53,
  "rows_checked": 147728,
  "non_1_factor_rows": 0,
  "raw_equivalent_rows": 147728,
  "raw_equivalent_ratio": 1.0,
  "audit_status_counts": {
    "WARN": 53
  },
  "source_verification_status_counts": {
    "source_adjustment_unverified_raw_equivalent": 53
  }
}
```

## Per-symbol evidence

| Symbol | Status | Source status | Rows | Non-1 factors | Raw-equivalent close rows | Max factor error | corr(close, adj_close) | adjustment_status |
|---|---|---|---:|---:|---:|---:|---:|---|
| `A32` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,702 | 0 | 1,702 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAA` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,970 | 0 | 3,970 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAH` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 605 | 0 | 605 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAM` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,158 | 0 | 4,158 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAN` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 22 | 0 | 22 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAS` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,475 | 0 | 1,475 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAT` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,308 | 0 | 1,308 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AAV` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,989 | 0 | 1,989 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABB` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,364 | 0 | 1,364 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,454 | 0 | 2,454 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABI` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,083 | 0 | 4,083 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABR` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,896 | 0 | 1,896 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABS` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,563 | 0 | 1,563 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABT` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,487 | 0 | 4,487 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ABW` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 764 | 0 | 764 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACB` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,868 | 0 | 4,868 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,731 | 0 | 3,731 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACE` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,861 | 0 | 3,861 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,202 | 0 | 1,202 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACL` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,317 | 0 | 4,317 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACM` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,343 | 0 | 2,343 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACS` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,710 | 0 | 1,710 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ACV` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,386 | 0 | 2,386 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ADC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,819 | 0 | 3,819 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ADG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,582 | 0 | 1,582 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ADP` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,600 | 0 | 3,600 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ADS` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,493 | 0 | 2,493 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AFX` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,347 | 0 | 2,347 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AG1` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,072 | 0 | 2,072 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGF` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,643 | 0 | 4,643 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,607 | 0 | 1,607 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGM` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,143 | 0 | 3,143 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGP` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,623 | 0 | 2,623 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGR` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,122 | 0 | 4,122 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AGX` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,465 | 0 | 2,465 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AIC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 1,161 | 0 | 1,161 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AIG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 395 | 0 | 395 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ALC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 105 | 0 | 105 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ALT` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,129 | 0 | 4,129 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ALV` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,761 | 0 | 3,761 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AMC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,526 | 0 | 3,526 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AME` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,782 | 0 | 3,782 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AMP` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,233 | 0 | 2,233 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AMS` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,339 | 0 | 2,339 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `AMV` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,804 | 0 | 3,804 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ANT` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,321 | 0 | 2,321 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `ANV` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,612 | 0 | 4,612 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `APC` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 3,975 | 0 | 3,975 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `APF` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 2,196 | 0 | 2,196 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `APG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,040 | 0 | 4,040 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `FPT` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,860 | 0 | 4,860 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `HPG` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 4,631 | 0 | 4,631 | 0 | 1.000000 | `adjusted_price_missing_warn` |
| `VNM` | `WARN` | `source_adjustment_unverified_raw_equivalent` | 5,084 | 0 | 5,084 | 0 | 1.000000 | `adjusted_price_missing_warn` |

## Interpretation

- `PASS` would require source-backed adjustment evidence plus internal factor consistency.
- `WARN` means the data is usable for demos only with explicit adjusted-price caveats.
- `FAIL` means adjusted OHLC fields are internally inconsistent with `adjusted_close / close` factor math.
