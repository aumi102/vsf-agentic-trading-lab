---
title: confirmed_adjusted_price_policy
toc_min_heading_level: 2
toc_max_heading_level: 3
---

# Confirmed Adjusted Price Policy

## 1. Mentor-confirmed requirements

The adjusted-price policy is confirmed and should be treated as an accepted
requirement, not an open mentor question:

- VN100 uses the current list.
- Adjusted price is mandatory for backtests.
- Full OHLC must be adjusted, not only close.
- Dividend, split, and corporate-action factor logic is required.
- Transaction cost assumptions should be researched by the project.
- Slippage should be reasonable and stay within exchange price bands:
  - HSX/HOSE: +/-7%;
  - UPCoM: +/-15%.

## 2. Adjusted OHLC policy

Backtest feeds must use adjusted open, high, low, and close. Raw OHLC remains
source evidence only. Raw close must never be treated as adjusted close, and a
missing factor must block hardened backtest use for that row or symbol.

## 3. Factor derivation policy

When adjusted price is available, compute the adjustment factor from adjusted
price divided by raw close, then apply that factor consistently to open, high,
low, and close. The factor must reflect dividend, split, or corporate-action
logic and must be traceable to source evidence.

When adjusted price is not available, factor derivation must come from explicit
dividend, split, or corporate-action evidence before adjusted OHLC can be
populated.

## 4. VN100 universe policy

The first broad universe uses the current VN100 list. This introduces a
survivorship caveat for research reporting, but it is the accepted MVP universe
policy for the next Backtrader work once adjusted readiness passes.

## 5. Cost and slippage policy

Transaction cost is not a mentor-blocking question; it is a research task for
the project. Slippage should use a reasonable assumption and must stay within
daily exchange price bands: HSX/HOSE +/-7% and UPCoM +/-15%.

## 6. Implementation implications

The remaining work is implementation verification, not policy approval. The repo
still needs traceable adjusted-price or factor evidence, raw payload provenance,
ETL integration, and a small-symbol adjusted readiness pass before Backtrader.

No source-specific live adapter is implemented yet. No uncontrolled live fetch,
full-universe crawl, adjusted OHLC population, Backtrader, Docker/scheduler, or
production-readiness claim is part of this policy doc.

## 7. Verification gates before Backtrader

Before Backtrader or VN100 research starts:

- verify adjusted-price or factor evidence for `FPT`, `VNM`, and `VCB`;
- preserve `source_id`, `raw_path`, and `adjustment_method` provenance;
- generate usable factor records accepted by controlled local verification;
- apply factors to adjusted OHLC columns for explicit symbols;
- pass `scripts/check_adjusted_ohlc_readiness.py`;
- confirm raw close was never used as adjusted close.

## 8. Next technical PR

The next technical PR should implement adjusted-price/factor evidence
verification for a small explicit symbol set, capture raw evidence, generate
factor records, populate adjusted OHLC locally, and require adjusted readiness to
pass. Backtrader/VN100 work remains blocked until that readiness gate passes.
