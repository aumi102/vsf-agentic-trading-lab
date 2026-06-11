# Autonomous Trading Agents - Architecture & Pipeline Notes Day 3 — Archived

**Source:** `docs/research_notes/paper_notes/27-05-2026_Phuc_report.md`
**Archived:** 2026-06-11
**Why archived:** Daily paper study notes (Vietnamese) plus synthesized architecture diagrams.
Historical research material; not a project technical doc or implementation contract.
Preserved here for personal reference.

---

## Papers read (27/05/2026)

1. ABIDES: Towards High-Fidelity Market Simulation for AI Research
2. StockBench: Can LLM Agents Trade Stocks Profitably in Real-world Markets?
3. A Multi-agent Deep Reinforcement Learning Framework for Optimizing Financial Trading Strategies
4. AI-Powered Trading, Algorithmic Collusion, and Price Efficiency

## Key takeaways

- **ABIDES:** agent-based discrete-event market simulation (exchange agent, order book, message passing, latency). Enables richer agent evaluation than simple historical backtesting.
- **StockBench:** benchmarks LLM agents with daily trading over months; evaluates cumulative return, max drawdown, Sortino vs buy-and-hold. Shows that financial QA ability ≠ profitable trading.
- **Multi-agent RL:** agents with different investment preferences (profit-seeking, risk-averse, short-term, long-term) are combined via a hierarchical aggregator; uses TimesNet for time-series features.
- **Algorithmic Collusion:** RL agents can independently learn collusion-like behavior without explicit coordination, reducing price efficiency — a market-level risk.

## Synthesized 6-layer architecture

```
Data Sources → Data Processing → Agent Layer → Decision Layer → Evaluation/Simulation → Insight & Governance
```

- Agent layer: LLM agent (reasoning/text), RL agent (strategy learning), multi-agent RL, risk agent.
- Evaluation: StockBench-style (portfolio metrics) and ABIDES-style (market simulation).
- Governance: collusion detection, price efficiency analysis, regulation notes.

## Recommended MVP direction

**StockBench-style LLM Trading Agent Benchmark** — simplest to prototype:
```
Data loader → Daily context builder → LLM decision maker → Risk checker → Portfolio simulator → Metrics
```

Extendable with: memory (FinMem/TradingGPT), multi-agent roles, deeper simulation (ABIDES).

## References

- ABIDES: https://arxiv.org/abs/1904.12066 / https://github.com/abides-sim/abides
- StockBench: https://arxiv.org/abs/2510.02209
- Multi-agent RL (TimesNet): https://www.sciencedirect.com/science/article/abs/pii/S0957417423020043
- AI-Powered Trading & Collusion: https://www.nber.org/papers/w34054
