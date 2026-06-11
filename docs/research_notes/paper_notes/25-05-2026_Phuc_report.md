---
id: autonomous-trading-agents-paper-notes
title: "Autonomous Trading Agents - Paper Notes"
sidebar_label: "Autonomous Trading Agents"
description: "Ghi chú ngắn gọn về các paper đã đọc liên quan đến autonomous trading agents."
tags:
  - autonomous-trading-agents
  - llm-agent
  - trading
  - reinforcement-learning
  - multi-agent
---

# Autonomous Trading Agents - Paper Notes

**Date:** 25/05/2026

Paper study notes — Day 1. Full notes archived at:
`notes/archive/research_notes/25-05-2026_Phuc_report.md`

---

## Papers

1. **Large Language Model Agent in Financial Trading: A Survey** — survey of LLM agent approaches in finance; taxonomy of architectures, inputs, evaluation methods.
2. **FinRL: Deep Reinforcement Learning Framework to Automate Trading** — DRL pipeline: state → action → reward → environment loop.
3. **TradingAgents: Multi-Agents LLM Financial Trading Framework** — models a trading firm with separate analyst, trader, bull/bear researcher, and risk manager agents.

## Key takeaways

- Three main approaches: (1) LLM agent for text/news analysis, (2) RL for strategy learning, (3) multi-agent for multi-perspective debate.
- Backtesting is required but not sufficient for production confidence.
- A trading agent is a system (data + analysis + decision + backtest + risk), not just a price predictor.
