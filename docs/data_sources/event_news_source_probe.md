# Event/news source probe

- generated_at: `2026-06-24T08:30:05Z`
- execute_mode: `True`
- raw_evidence_root: `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\event_news_probe`
- plan_path: `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\event_news_probe\raw\20260624T082955Z\plan.json`
- report_path: `D:\Nguyen_Duc_Hoang_Phuc\vsf\data\processed\dry_run\event_news_probe\raw\20260624T082955Z\plan_report.md`

## Summary

```json
{
  "run_id": "20260624T082955Z",
  "started_at": "2026-06-24T08:29:55.549250+00:00",
  "mode": "execute",
  "network_requests_made": true,
  "output_base": "D:\\Nguyen_Duc_Hoang_Phuc\\vsf\\data\\processed\\dry_run\\event_news_probe\\raw",
  "bronze_base": "D:\\Nguyen_Duc_Hoang_Phuc\\vsf\\data\\processed\\dry_run\\event_news_probe\\bronze",
  "checkpoint_path": "D:\\Nguyen_Duc_Hoang_Phuc\\vsf\\data\\processed\\dry_run\\event_news_probe\\raw\\20260624T082955Z\\checkpoint.json",
  "total_targets": 9,
  "configured_targets": 5,
  "planned_request_count": 5,
  "max_requests": 5,
  "sleep_min_seconds": 2.0,
  "sleep_max_seconds": 2.0,
  "force": true,
  "completed_datasets": [
    "company_ir_fpt_disclosures",
    "company_ir_vci_fy2025_fs",
    "company_ir_vci_q1_2026_fs",
    "hose_disclosures_fpt"
  ],
  "failed_datasets": [
    "hnx_disclosures_fpt"
  ],
  "pending_datasets": [],
  "guardrails": [
    "No network requests unless --execute is supplied.",
    "Targets without a configured URL are skipped; status=not_configured.",
    "Requests processed sequentially with concurrency=1.",
    "Random sleep applied between execute-mode requests.",
    "Raw payload and metadata captured before parsing.",
    "No database write, migration, backtest, or full-universe fetch.",
    "No secret values written to output files."
  ]
}
```

## Candidate source status

| Dataset | Source family | Symbol | Access/parse status | Records | Candidate fields | Limitation |
|---|---|---|---|---:|---|---|
| `hose_disclosures_fpt` | `hose` | `None` | `js_app_shell` | 0 | symbol, title, published_at/published_date, document_url | js_app_shell_no_structured_data |
| `hnx_disclosures_fpt` | `hnx` | `None` | `error` | 0 | symbol, title, published_at/published_date, document_url | request_error:<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1016)> |
| `company_ir_fpt_disclosures` | `company_ir` | `None` | `verified` | 20 | symbol, title, published_at/published_date, document_url |  |
| `company_ir_vci_fy2025_fs` | `company_ir` | `None` | `verified` | 1 | symbol, title, published_at/published_date, document_url |  |
| `company_ir_vci_q1_2026_fs` | `company_ir` | `None` | `verified` | 1 | symbol, title, published_at/published_date, document_url |  |

## Usability decision

A minimal `event_news_items` ingestion can be built from parsed official disclosure records. These are disclosure/event records, not general news.

The current minimal QuestDB event layer is intentionally scoped to parsed official disclosure records. The first tracked ingest loaded FPT disclosure records; VNM/HPG remain unavailable until a source with symbol-level records is added.

## Caveats

- Official disclosure records are event-like evidence, not broad market news.
- HOSE/HNX parent pages can be JS/AJAX shells; those are not ingested as records.
- Raw payloads are intentionally kept under ignored `data/processed/dry_run/event_news_probe/`.
