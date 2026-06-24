# FA metric mapping status

- mapping_source_file: `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\vietcap_iq\fa_metric_mapping_union_v2.csv`
- questdb_table: `fa_metric_mapping`
- rows_loaded: `1957`

## Mapping row quality

| quality_status | rows |
|---|---:|
| `source_backed_consensus` | 1,858 |
| `source_mapping_conflict` | 99 |

## Coverage against current QuestDB FA fact tables

| Statement | Fact rows | Distinct codes | Consensus mapped codes | Code coverage | Consensus mapped rows | Row coverage |
|---|---:|---:|---:|---:|---:|---:|
| `BALANCE_SHEET` | 862,586 | 331 | 229 | 69.2% | 596,774 | 69.2% |
| `INCOME_STATEMENT` | 474,039 | 181 | 153 | 84.5% | 400,707 | 84.5% |
| `CASH_FLOW` | 581,400 | 225 | 177 | 78.7% | 457,368 | 78.7% |
| `NOTE` | 557,427 | 1,402 | 1,299 | 92.7% | 521,829 | 93.6% |

## Caveats

- Mapping is source-backed from captured Vietcap IQ metric mapping artifacts, but it is still partial.
- Conflicting or blank consensus rows are loaded for auditability but should not be treated as semantic metric names.
- FA fact rows remain untouched; tools only enrich names when a consensus mapping is available.
