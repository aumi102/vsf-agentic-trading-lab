# Exchange metadata status

- output_config: `D:\Nguyen_Duc_Hoang_Phuc\vsf\configs\exchange_metadata_overrides.csv`
- source_files: `4`
- raw_source_rows_seen: `4070`
- securities_total: `1556`
- securities_known_exchange_before_apply: `1551`
- source_backed_override_rows: `1556`
- source_backed_coverage_pct_vs_securities: `100.00%`
- conflicts_skipped: `0`

## Sources

- `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\vietcap_iq_universe\20260604T101513Z\symbol_universe.csv`
- `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\vietcap_iq_universe\20260604T101513Z\exchange_listings.csv`
- `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\hose_listed_universe_all_pages\20260603T080254Z\symbol_universe.csv`
- `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\hose_listed_universe_all_pages\20260603T080254Z\exchange_listings.csv`

## Conflicts

No source conflicts detected among generated override rows.

## Caveats

- This config updates only symbols found in QuestDB `securities`.
- Symbols absent from captured source evidence are not assigned an exchange.
- Applying the config updates only `securities.exchange`; it does not mutate OHLCV, FA, or backtest tables.
