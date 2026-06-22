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
- the decisions needed before one real family can be enabled.

## Talk Track

- “Em đang demo safety gates, chưa demo performance.”
- “Khi anh chọn family/assumptions, em mới enable đúng một family.”

## Boundaries

This is a local research/demo server, not a production UI. It uses synthetic
adjusted-OHLC fixture rows and performs no live fetch or database mutation.
There is no Backtrader, full VN100, optimizer, live trading, broker execution,
performance claim, or investment advice.
