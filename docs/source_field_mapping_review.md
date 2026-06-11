# Source Field Mapping Review

**Date:** 2026-06-02 (probe date) | Full historical review archived at: `notes/archive/source_field_mapping_review_legacy.md`

---

## Summary

| Source | Dataset | Ready for ingestion v2? | Decision |
|---|---|---|---|
| `fred` | Global macro time-series (`DGS10`) | Yes | Macro-context ingestion planning only |
| `hose` | Listed-stock API (JSON) | No at this probe; subsequently resolved | Manual endpoint discovery required; see `hose_pipeline.md` |
| `vbma` | Bond auction XLSX (served as `.csv`) | Yes | VBMA auction ingestion planning; 3,268 rows |
| `vietcap_iq` | Research center HTML | No at this probe | Report-list API discovery required; FA endpoint later confirmed |

---

## Current status (as of 2026-06-11)

- **FRED:** Schema planned in `ingestion_v2_schema_plan.md` (`macro_series`, `macro_observations`). DB write not implemented.
- **HOSE:** Listed-stock JSON API confirmed (`api.hsx.vn`); dry-run parser done. Details in `hose_pipeline.md`. DB write blocked by unconfirmed source units / EOD semantics.
- **VBMA:** Schema planned in `ingestion_v2_schema_plan.md` (`bond_instruments`, `bond_auction_results`). DB write not implemented.
- **Vietcap IQ:** FA endpoint confirmed (BS/IS/CF); parser + Option C mapping implemented (PR #7). DB write blocked — mapping coverage below 95%, PIT unconfirmed. See `vietcap_iq_fa_ingestion_v2_readiness.md`.

---

## Related documents

- `ingestion_v2_schema_plan.md` — canonical schema for FRED/VBMA/HOSE/Vietcap IQ
- `hose_pipeline.md` — HOSE pipeline status
- `vietcap_iq_fa_ingestion_v2_readiness.md` — Vietcap IQ FA gate status
