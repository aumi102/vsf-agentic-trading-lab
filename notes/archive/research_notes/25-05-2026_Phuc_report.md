# Autonomous Trading Agents - Paper Notes (Day 1) — Archived

**Source:** `docs/research_notes/paper_notes/25-05-2026_Phuc_report.md` (archived 2026-06-11)
**Why archived:** Daily paper study notes (Vietnamese). Historical research material; not a
project technical doc or implementation contract. Preserved here for personal reference.

---

## Papers read (25/05/2026)

1. Large Language Model Agent in Financial Trading: A Survey
2. FinRL: Deep Reinforcement Learning Framework to Automate Trading in Quantitative Finance
3. TradingAgents: Multi-Agents LLM Financial Trading Framework

## Key takeaways

- Autonomous trading agents are systems, not just price-prediction models.
- Three main approaches: (1) LLM agent for text analysis, (2) Reinforcement Learning for strategy learning, (3) Multi-agent for multi-perspective analysis and debate.
- TradingAgents models a trading firm — separate analyst, trader, bull/bear researcher, and risk manager agents.
- FinRL provides a DRL pipeline: state → action → reward → environment loop.
- Backtesting is required but not sufficient for production confidence.

## Comparison table

| Paper | Approach | Use for |
|---|---|---|
| LLM Trading Survey | Survey | Overall orientation, taxonomy |
| FinRL | Deep RL | RL-based trading strategy baseline |
| TradingAgents | Multi-agent LLM | Multi-role trading firm simulation |

## Research questions

- Which is easier to prototype: FinRL or TradingAgents?
- Which evaluation metrics matter most for trading agents?
- How to control LLM hallucination in trading contexts?

## References

- Survey: https://arxiv.org/abs/2408.06361
- FinRL: https://arxiv.org/abs/2111.09395
- TradingAgents: https://arxiv.org/abs/2412.20138
- TradingAgents project: https://tradingagents-ai.github.io/
