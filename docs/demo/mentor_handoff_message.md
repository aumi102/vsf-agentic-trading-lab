---
title: mentor_handoff_message
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Handoff Message

## Tin nhắn gửi mentor

Dạ anh Khánh, anh xem giúp em bản demo hiện tại của VSF agentic trading lab. Repo đang private. Em đã hoàn tất luồng demo cục bộ gồm SQLite MVP store, tool calls, deterministic orchestrator, scenario runner, Backtest MVP, và mentor demo suite. Bản này chỉ dùng dữ liệu cache/local, không có live trading, broker execution, QuestDB, LLM reasoning, hay network crawl. Kết quả chỉ để review kỹ thuật, không phải khuyến nghị đầu tư.

Em cần anh xác nhận các giả định backtest và hướng đi tiếp theo trước khi mở rộng universe hoặc làm QuestDB/LLM.

---

## Repo State

- Repo: private `somene112/vsf-agentic-trading-lab`.
- PR #16 through PR #23 are merged.
- PR #15 remains draft as a PIT breadth side-track and is not part of this demo path.
- Current demo includes SQLite DB, market/features/signal/risk/report tools, deterministic orchestrator, scenario runner, Backtest MVP, and mentor suite.

---

## Commands To Run

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
python scripts/run_mentor_demo_suite.py
python scripts/run_agent_demo.py --scenario market_brief --symbol FPT
python scripts/run_agent_demo.py --scenario compare --symbols FPT,VNM,VCB
python scripts/run_backtest_demo.py --symbols FPT,VNM,VCB --strategy-id mvp_ma20_ma50_momentum
```

If the local shell has Vietnamese encoding issues, use the ASCII fallback query from the runbook.

---

## Files To Read

- `docs/demo/mentor_demo_runbook.md`
- `docs/reports/mentor_demo_report.md`
- `docs/reports/backtest_mvp_demo_report.md`
- `docs/demo/mentor_review_checklist.md`
- `docs/demo/mentor_feedback_capture.md`

---

## Decisions Needed

1. Should exploratory backtest execution keep same-day close, or require next-bar execution immediately?
2. Are flat transaction cost and slippage assumptions acceptable for the MVP?
3. Which symbols or universe should the first real backtest cover?
4. Which DB path should come next: keep SQLite, migrate to DuckDB, implement QuestDB, or use Postgres/TimescaleDB?
5. Should BUY/SELL/HOLD be shown to stakeholders, or kept as internal signal values?
6. Should the next work be backtest hardening, DB migration, or LLM tool-selection?

---

## Current Boundaries

- Exploratory demo only; not production-ready and not financial advice.
- Cached local data only.
- No broker execution, live trading, shorting, portfolio optimization, QuestDB implementation, network crawl, or LLM-generated decisions.
- Await mentor feedback before QuestDB/LLM/backtest hardening.
