# Autonomous Trading Agents - Paper Notes Day 2 — Archived

**Source:** `docs/research_notes/paper_notes/26-05-2026_Phuc_report.md`
**Archived:** 2026-06-11
**Why archived:** Daily paper study notes (Vietnamese). Historical research material; not a
project technical doc or implementation contract. Preserved here for personal reference.

---

## Papers read (26/05/2026)

1. FinMem: A Performance-Enhanced LLM Trading Agent with Layered Memory and Character Design
2. TradingGPT: Multi-Agent System with Layered Memory and Distinct Characters
3. StockAgent: LLM-based Stock Trading in Simulated Real-world Environments

## Key takeaways

- **Layered memory** is critical for LLM trading agents: short-term / medium-term / long-term structure.
- **Character design** (cautious, aggressive, balanced) creates distinct agent personalities.
- **Multi-agent debate** (TradingGPT) gives multiple viewpoints before a final decision.
- **Simulation environment** (StockAgent) tests agents in conditions closer to real markets.
- Trading agent evaluation needs to consider **test set leakage** (agent should not see future data).

## Comparison table

| Paper | Focus | Key idea |
|---|---|---|
| FinMem | Single agent + layered memory + character | Memory helps agent prioritize and retain relevant info |
| TradingGPT | Multi-agent + memory + distinct characters | Each agent has memory and personality; they debate |
| StockAgent | Simulation environment | Test LLM investor behavior under external factor shocks |

## Prototype options noted

- **Option 1 (FinMem-style):** single agent + memory manager
- **Option 2 (TradingGPT-style):** multi-agent + character + debate
- **Option 3 (StockAgent-style):** simulated market environment

## References

- FinMem: https://arxiv.org/abs/2311.13743 / https://github.com/pipiku915/finmem-llm-stocktrading
- TradingGPT: https://arxiv.org/abs/2309.03736
- StockAgent: https://arxiv.org/abs/2407.18957 / https://github.com/MingyuJ666/Stockagent
