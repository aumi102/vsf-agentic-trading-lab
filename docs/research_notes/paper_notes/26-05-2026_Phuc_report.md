---
id: autonomous-trading-agents-paper-notes-day-2
title: "Autonomous Trading Agents - Paper Notes Day 2"
sidebar_label: "Autonomous Trading Agents Day 2"
description: "Ghi chú ngày 2 về các paper liên quan đến LLM trading agents, layered memory, character design và stock trading simulation."
tags:
  - autonomous-trading-agents
  - llm-agent
  - layered-memory
  - multi-agent
  - stockagent
---

# Autonomous Trading Agents - Paper Notes Day 2

**Date:** 26/05/2026

Paper study notes — Day 2. Full notes archived at:
`notes/archive/research_notes/26-05-2026_Phuc_report.md`

---

## Papers

1. **FinMem** — single LLM trading agent with layered memory (short/medium/long-term) and character design.
2. **TradingGPT** — multi-agent system; each agent has layered memory and a distinct trading personality (cautious, aggressive, balanced); agents debate before a final decision.
3. **StockAgent** — LLM-based stock trading simulation; tests investor behavior under external factor shocks (news, policy, macro); notes test-set leakage risk.

## Key takeaways

- Layered memory improves LLM agent decision quality by separating short-term signals from long-term patterns.
- Character design makes agent behavior more controllable and interpretable.
- Simulation environments (StockAgent) give richer evaluation than simple historical backtesting.
- Test set leakage (LLM knowing future data) must be explicitly prevented.
