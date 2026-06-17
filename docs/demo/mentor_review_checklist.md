---
title: mentor_review_checklist
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Review Checklist

Use this checklist during and after the demo session to confirm the current state and decide next engineering steps. Focus on tool flow, output quality, backtest assumptions, and product direction.

---

## What To Run

### One-time build

```bash
python scripts/build_mvp_db.py --symbols FPT,VNM,VCB
```

Expected: prints `symbols_loaded=FPT,VCB,VNM`, row counts, and DB path. No network calls.

### Full suite

```bash
python scripts/run_mentor_demo_suite.py
```

Expected: status table with OK for market brief, risk check, compare, and Backtest MVP rows. Expected nonzero edge cases are labeled OK when status matches.

### Backtest MVP focus commands

```bash
python scripts/run_backtest_demo.py --symbols FPT,VNM,VCB --strategy-id mvp_ma20_ma50_momentum
python scripts/run_backtest_demo.py --symbols FPT,HPG --strategy-id mvp_ma20_ma50_momentum
python scripts/run_backtest_demo.py --symbols FPT --start-date 2030-01-01 --end-date 2030-12-31
```

---

## What To Inspect

| Item | What to look for |
|---|---|
| FPT market brief | Latest date, signal, risk flag, adjustment caveat |
| VCB risk check | Risk flags, `thin_recent_volume`, quality status |
| Compare table | FPT/VNM/VCB rows in input order |
| FPT vs HPG compare | FPT ok; HPG `not_found`; no traceback |
| Backtest base run | `status=ok`; metrics present; gates pass/warn |
| Backtest FPT,HPG | `symbols_missing=["HPG"]`; still `status=ok` |
| Backtest 2030 date range | `status=not_found`; no usable rows; no traceback |
| `not_financial_advice` | Always `true` |

---

## Questions For Mentor

1. Is the current SQLite MVP demo sufficient for the next stakeholder meeting, or does it need additional symbols, improved wording, or a different output format?
2. Is same-day close acceptable for exploratory demo, or should next-bar execution be required immediately?
3. Are flat transaction cost and slippage assumptions acceptable for MVP?
4. Which symbols or universe should the first real backtest cover?
5. Should the next implementation step be backtest hardening, DuckDB/QuestDB migration, or LLM tool-selection?
6. Which store should we move to next: keep SQLite temporarily, migrate to DuckDB, implement QuestDB, or use Postgres/TimescaleDB?
7. Should BUY/SELL/HOLD be shown to non-technical stakeholders, or kept as internal signal values with caveats?
8. Which output details should remain private: raw risk flags, `quality_status=warn`, adjustment caveats, or tool-call trace JSON?

---

## After The Demo Session

Record answers in `docs/demo/mentor_feedback_capture.md` and update `docs/plans/post_demo_technical_roadmap.md` with the agreed next phase.

Current blockers:

- Production DB write: blocked until store decision is made.
- Production backtest hardening: blocked until execution convention, assumptions, and universe are confirmed.
- Full-history FA fetch: blocked on mapping, PIT, and schema gates.
- LLM reasoning: blocked until backtest is validated or explicitly deferred.
- Realtime feed: blocked until data contracts are stable.
