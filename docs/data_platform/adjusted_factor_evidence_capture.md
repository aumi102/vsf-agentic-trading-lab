---
title: adjusted_factor_evidence_capture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjusted Factor Evidence Capture

## Purpose

PR #33 added a dry-run adjusted-factor source probe and local payload inspector.
This evidence-capture layer records what a local payload appears to contain,
hashes the payload content, and preserves enough provenance for later review
before any ETL integration.

This is still not adjusted OHLC population. It does not mark any market data as
adjusted and does not unblock Backtrader/VN100 work by itself.

## Scope

- Read local JSON payloads only.
- Capture candidate adjusted close fields, adjustment factor fields, and
  corporate-action terms.
- Record `symbol`, `source`, `payload_path`, and SHA-256 `content_hash`.
- Print evidence JSON to stdout.
- Write evidence JSON only when `--output` is explicitly provided.
- Treat generated evidence JSON as an artifact; do not commit it unless it is
  intentionally curated as a reviewed fixture.
- Always report `network_request_made=false`, `db_mutation_made=false`, and
  `adjusted_ohlc_populated=false`.

## Evidence Record

Each evidence record includes:

- `symbol`;
- `source`;
- `payload_path`;
- `content_hash`;
- `evidence_strength`;
- `adjusted_close_fields`;
- `adjustment_factor_fields`;
- `corporate_action_terms`;
- `can_derive_factor`;
- `status`;
- `reasons`.

`can_derive_factor=true` is only a candidate signal from adjusted close or
usable adjustment-factor fields. Corporate-action terms alone do not mean a
complete factor can already be derived.

## Commands

```bash
python scripts/capture_adjusted_factor_evidence.py --source tracked_fixtures --symbol FPT --payload path/to/payload.json
python scripts/capture_adjusted_factor_evidence.py --source vietcap_iq_gap_chart --symbol FPT --payload path/to/gap_chart_payload.json --output reports/adjusted_factor_evidence.json
```

Missing payload files and invalid JSON return clean JSON errors and exit 1.
Invalid metadata, such as an empty symbol or source, also returns a clean JSON
error and exit 1. Captured evidence and no-evidence records exit 0.

## Limitations

- No live network request.
- No DB mutation.
- No adjusted OHLC population.
- No full-universe probing.
- No Backtrader strategy work.
- No Docker/scheduler implementation.
- No production-readiness or investment-advice claim.

## Next Step

Use approved local or controlled probe outputs to identify a verified adjusted
close or corporate-action factor source, then integrate that verified factor
source into ETL for a small explicit symbol set with readiness-gate validation.
The local factor application foundation is documented in
`docs/data_platform/apply_adjustment_factors_plan.md`.
