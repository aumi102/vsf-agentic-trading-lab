# Source Field Mapping Review — Archived

**Source:** `docs/source_field_mapping_review.md` (archived 2026-06-11)
**Why archived:** This early-phase source probe review (from 2026-06-02) is now superseded by
source-specific canonical docs (`hose_pipeline.md`, `ingestion_v2_schema_plan.md`, the Vietcap IQ
FA series). The summary decisions and field mappings are preserved here for historical reference.

---

## Summary

| Source | Dataset type | Ready for ingestion v2 planning? | Decision |
|---|---|---|---|
| `fred` | Global macro time-series observations | Yes | Ready for macro-context ingestion planning only |
| `hose` | HOSE website/app shell | No | Needs manual Network-tab endpoint discovery |
| `vbma` | Bond auction result spreadsheet from CSV-like endpoint | Yes | Ready for VBMA auction ingestion planning |
| `vietcap_iq` | Public research center HTML page | No | Needs report-list API endpoint discovery |

---

## FRED

**Probe:** `run_id=20260602T072716Z`, HTTP 200, `application/json; charset=UTF-8`

### Observed Structure

Top-level: `realtime_start`, `realtime_end`, `observation_start`, `observation_end`, `units`, `output_type`, `file_type`, `order_by`, `sort_order`, `count`, `offset`, `limit`, `observations`

Observation fields: `realtime_start`, `realtime_end`, `date`, `value`

Sample: `DGS10`, `count=16804`, `limit=5`.

### Field Mapping

| Raw field | Canonical table | Canonical field | Notes |
|---|---|---|---|
| configured `series_id` | `macro_series` | `series_id` | From request params |
| `units` | `macro_series` | `unit` | e.g., `lin` |
| `observation_start` / `observation_end` | `macro_series` | same | Series-level metadata |
| `observations[].date` | `macro_observations` | `observation_date` | Parse as date |
| `observations[].value` | `macro_observations` | `observation_value` | FRED may use `.` for missing |
| `observations[].realtime_start` / `realtime_end` | `macro_observations` | same | PIT handling |

### Parser Risks

- `value` can be `.` for missing observations.
- FRED realtime revision fields must not be discarded.
- API key must stay outside raw metadata and reports.
- Macro context only — not stock OHLCV.

**Decision:** Ready for ingestion v2 planning for macro context tables. Full schema in `ingestion_v2_schema_plan.md`.

---

## HSX/HOSE

**Probe:** `run_id=20260602T074355Z`, HTTP 200, `text/html`

The sample was an HTML shell for a JavaScript app, not a listing data payload. No parsed listing rows. Useful data loaded by JavaScript through separate XHR/fetch calls.

**Decision:** Not ready for ingestion v2 planning. Required manual Network-tab endpoint discovery. Follow-up work confirmed the JSON listing API (`api.hsx.vn`) — see `hose_pipeline.md`.

---

## VBMA

**Probe:** `run_id=20260602T085214Z`, HTTP 200, `application/octet-stream`

Despite `.csv` endpoint name, payload is XLSX (ZIP signature). Sheet: `Kết quả đấu thầu theo đợt Eng`. 3,268 rows.

### Observed Columns

`Mã trái phiếu`, `Tổ chức phát hành`, `Kỳ hạn (năm)`, `Ngày TCPH`, `Giá trị gọi thầu (tỷ đồng)`, `Giá trị đặt thầu (tỷ đồng)`, `Giá trị trúng thầu (tỷ đồng)`, `Lãi suất trúng thầu (%/y)`, `Lãi suất đấu thầu max`, `Lãi suất đấu thầu min`

### Field Mapping

| Raw field | Canonical table | Canonical field |
|---|---|---|
| `Mã trái phiếu` | `bond_auctions`, `bond_instruments` | `bond_code` |
| `Tổ chức phát hành` | `bond_instruments` | `issuer` |
| `Kỳ hạn (năm)` | `bond_instruments` | `tenor_years` |
| `Ngày TCPH` | `bond_auctions` | `auction_or_issue_date` |
| `Giá trị gọi thầu (tỷ đồng)` | `bond_auctions` | `offered_amount_billion_vnd` |
| `Giá trị đặt thầu (tỷ đồng)` | `bond_auctions` | `bid_amount_billion_vnd` |
| `Giá trị trúng thầu (tỷ đồng)` | `bond_auctions` | `winning_amount_billion_vnd` |
| `Lãi suất trúng thầu (%/y)` | `bond_auctions` | `winning_yield_pct` |
| `Lãi suất đấu thầu max/min` | `bond_auctions` | `bid_yield_max_pct`, `bid_yield_min_pct` |

**Parser risks:** endpoint named `.csv` but returns XLSX; Vietnamese headers include spaces and newlines; `-` in numeric fields = null; `verify_ssl=false` is target-local.

**Decision:** Ready for ingestion v2 planning for bond auction results. Full schema in `ingestion_v2_schema_plan.md`.

---

## Vietcap IQ

**Probe:** `run_id=20260602T090035Z`, HTTP 200, `text/html`

The sample was a public research center HTML page with redirect script to `trading.vietcap.com.vn/iq/report`. No directly extracted report rows.

**Decision:** Not ready for report/document ingestion planning. Later work verified the Vietcap IQ search-bar JSON as the broad full-market fetch universe candidate. FA endpoint (BS/IS/CF) discovered and parser implemented — see the FA doc series.

---

## Final Recommendation (as of 2026-06-02)

| Source | Recommendation |
|---|---|
| `vbma` | Plan ingestion v2 for `bond_auctions` first. |
| `fred` | Plan ingestion v2 for `macro_observations` and `macro_series`. |
| `hose` | Continue manual Network-tab investigation. |
| `vietcap_iq` | Continue manual Network-tab investigation. |
