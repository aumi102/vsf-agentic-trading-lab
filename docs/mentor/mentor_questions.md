---
title: mentor_questions
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Mentor Questions

1. Which baseline should be implemented first: momentum, moving average,
   breakout, mean reversion, or another simple rule-based strategy?
2. Which first universe: FPT/VNM/VCB only, a VN30 subset, or VN100 later?
3. Which execution-price convention: adjusted close, next adjusted open, or a
   clearly labeled VWAP placeholder?
4. What transaction-cost bps should the research run use?
5. What slippage bps should apply by exchange within HOSE/HSX 700-bps and UPCOM
   1500-bps limits?
6. What signal and rebalance frequency is appropriate?
7. What position sizing, maximum holding period, and risk-stop rules reflect the
   intended research risk appetite?
8. What result format should be reviewed: JSON, Markdown, charts, notebook, or
   a concise per-symbol table?
9. Which committed docs/reports and which external generated reports should be
   uploaded to the Vin folder?
10. What must be demonstrated live before approving the first Backtrader
    research scaffold?

Record answers in `strategy_decision_template.md`; do not infer missing choices.
