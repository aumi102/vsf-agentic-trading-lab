---
title: mentor_demo_decision_capture
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Demo Decision Capture

## Purpose

The local dashboard includes a browser-only form for recording the mentor's
strategy family and research assumptions during the call. It previews a JSON
strategy contract draft without sending or persisting the entered values.

## During the Call

1. Start `python scripts/run_mentor_demo_ui.py`.
2. Complete **9. Mentor Decision Capture** with the agreed family, universe,
   symbols, date range, execution price, costs, rebalance, and risk assumptions.
3. Copy the pending contract draft and review it together.

The generated contract always keeps `mentor_approval_status=pending`. Even a
complete form means only `draft_ready`; it does not authorize execution or
enable a strategy family.

The browser preview is not a canonical project contract. It becomes reviewable
only after it is copied, checked with the mentor, and committed manually in a
separate change.

## After Mentor Confirmation

1. Manually update the reviewed contract and record approval.
2. Run the existing strategy contract validator.
3. Only after validation returns `ok`, enable exactly one agreed family in a
   later, separately reviewed PR.

## Boundaries

The form performs no file write, server persistence, adapter execution, or
registry enablement. There is no Backtrader, optimizer, live trading,
performance claim, or investment advice.
