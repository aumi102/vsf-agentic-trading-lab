---
title: mentor_demo_ui_runbook
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Demo UI Runbook

## Start the Local UI

From the repository root, run one command:

```bash
python scripts/run_mentor_demo_ui.py
```

The local-only dashboard opens at `http://127.0.0.1:8765`. Use `--no-open` to
serve without opening a browser, or `--once-json` to print the same summary and
exit. No npm or external assets are required.

## What the Mentor Will See

- current safe-system status and minimal Vin upload files;
- the pending strategy contract blocked as `not_ready`;
- the registry with only `noop` enabled;
- an approved noop adapter preview returning `NO_SIGNAL` for FPT/VNM/VCB;
- `moving_average` blocked until mentor approval;
- browser-only mentor decision capture and pending contract draft preview;
- the decisions needed before one real family can be enabled.
- final readiness checks and a copyable five-minute demo script.

Use the [decision capture guide](./mentor_demo_decision_capture.md) during the
call. Form values stay in the browser and are not persisted by the server.
The sample-fill values are examples only, blank number fields remain
`null`/`not_ready`, and the copied talk track explains why every draft stays
pending and non-executing.

Before the call, review the [final readiness guide](./mentor_demo_final_readiness.md)
and use **Check Demo Readiness** in section 10.

## Talk Track

- “Em đang demo safety gates, chưa demo performance.”
- “Khi anh chọn family/assumptions, em mới enable đúng một family.”

## Boundaries

This is a local research/demo server, not a production UI. It uses synthetic
adjusted-OHLC fixture rows and performs no live fetch or database mutation.
There is no Backtrader, full VN100, optimizer, live trading, broker execution,
performance claim, or investment advice.
