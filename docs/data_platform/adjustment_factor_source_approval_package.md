---
title: adjustment_factor_source_evidence_note
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Adjustment Factor Source Evidence Note

The canonical policy document is now
`docs/data_platform/confirmed_adjusted_price_policy.md`.

Mentor policy is confirmed: VN100 uses the current list, adjusted price is
mandatory, full OHLC must be adjusted, dividend/split factor logic is required,
transaction cost should be researched by the project, and slippage must remain
within HSX/HOSE +/-7% and UPCoM +/-15% bands.

This file remains only as a compatibility note for the prior document path. The
remaining work is implementation verification of adjusted-price or factor
evidence, with `source_id`, `raw_path`, and `adjustment_method` provenance.
Backtrader/VN100 remains blocked until adjusted OHLC is populated and readiness
passes.
