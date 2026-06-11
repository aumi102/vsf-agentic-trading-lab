---
id: autonomous-trading-agents-architecture-pipeline-notes-day-3
title: "Autonomous Trading Agents - Architecture & Pipeline Notes Day 3"
sidebar_label: "Architecture & Pipeline Notes Day 3"
description: "Ghi chú ngày 3 về autonomous trading agents, bổ sung kiến trúc và pipeline đề xuất để review."
tags:
  - autonomous-trading-agents
  - llm-agent
  - market-simulation
  - stockbench
  - reinforcement-learning
  - multi-agent
  - algorithmic-collusion
  - architecture
  - pipeline
---

# Autonomous Trading Agents - Architecture & Pipeline Notes Day 3

**Date:** 27/05/2026

Paper study notes with synthesized architecture — Day 3. Full notes archived at:
`notes/archive/research_notes/27-05-2026_Phuc_report.md`

---

## Papers

1. **ABIDES** — agent-based discrete-event market simulation (exchange agent, order book, message passing, latency). Richer than simple backtesting.
2. **StockBench** — benchmarks LLM trading agents with daily trading over months; evaluates cumulative return, max drawdown, Sortino vs buy-and-hold.
3. **Multi-agent Deep RL** — multiple RL agents with different investment preferences combined via hierarchical aggregator; uses TimesNet for time-series features.
4. **AI-Powered Trading & Algorithmic Collusion** — RL agents can independently develop collusion-like behavior that reduces market price efficiency.

## Key takeaways

- Evaluation layer matters as much as agent architecture; StockBench and ABIDES show different evaluation depths.
- LLM agents excel at reasoning/text; RL agents excel at learning strategy from time-series.
- Multiple AI agents on a market can create systemic risks (collusion, price efficiency reduction).
- **Recommended MVP path:** StockBench-style daily trading benchmark — simplest to prototype and measure.
