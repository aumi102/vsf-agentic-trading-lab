# Mentor Live Demo Script

## 1. Demo Purpose

Demonstrate the trading core safety gates in a live mentor call:
- **Approved mode** (default) blocks all backtest/signal because no approved adjusted OHLC source exists.
- **Prototype mode** runs end-to-end with FPT/VNM to prove the pipeline works.
- The system distinguishes "unapproved source" (vnstock) vs "missing source" (HPG/VCB/CTG/VHM).
- Cost/slippage/trade-level metrics are visible and realistic.
- The system refuses to fake adjusted OHLC or fall back to raw prices.

## 2. What This Demo Proves

- Approved mode gate blocks correctly when no approved adjusted OHLC is present.
- Prototype mode runs the full signal → backtest pipeline with FPT/VNM.
- Corporate action source evidence: FPT PDF is scanned, QuestDB event tables are disclosure/news, not structured corporate action.
- Cost model: commission + slippage are charged per trade, visible at per-trade level.
- The system honestly reports blockers without faking data.

## 3. What This Demo Does NOT Prove

- NOT production backtest validity (prototype only).
- NOT adjusted OHLC accuracy (source is vnstock prototype).
- NOT universal coverage (FPT/VNM only in prototype mode).
- NOT cost model precision (bps slippage is a model, not market impact).

## 4. Commands to Run

### Quick text demo
```bat
python scripts\run_mentor_live_trading_demo.py --from 2021-01-01 --to 2025-12-31 --strategy ma_cross_v1 --commission-bps 15 --slippage-bps 5 --price-band-guard
```

### JSON output (for scripted/headless use)
```bat
python scripts\run_mentor_live_trading_demo.py --from 2021-01-01 --to 2025-12-31 --strategy ma_cross_v1 --commission-bps 15 --slippage-bps 5 --price-band-guard --json
```

### With custom QuestDB URL
```bat
python scripts\run_mentor_live_trading_demo.py --questdb-url http://localhost:9000 --from 2021-01-01 --to 2025-12-31 --strategy ma_cross_v1 --commission-bps 15 --slippage-bps 5 --price-band-guard
```

## 5. Approved Mode Explanation

**Approved mode hiện block toàn bộ vì chưa có approved adjusted OHLC source.**

Under `source_policy = approved_only`:
- `FPT` → `BLOCKED_UNAPPROVED_SOURCE` (vnstock-derived, not approved)
- `VNM` → `BLOCKED_UNAPPROVED_SOURCE` (vnstock-derived, not approved)
- `HPG/VCB/CTG/VHM` → `BLOCKED_ADJUSTED_SOURCE_MISSING` (no corporate action source)
- Approved count = **0**
- Official backtest = **BLOCKED**
- Official signal = **BLOCKED**

The system refuses to run official signal/backtest when approved adjusted OHLC is missing. It distinguishes:
1. **Unapproved source** (vnstock-derived) — blocked, different reason
2. **Missing source** — blocked, different reason

`Em đang ưu tiên block đúng hơn là pass sai.`

## 6. Prototype Mode Explanation

**Prototype mode chỉ dùng để chứng minh pipeline chạy được, không claim production backtest.**

Under `source_policy = prototype_allowed`:
- `FPT` → `PASS_PROTOTYPE` (vnstock-derived, marked prototype)
- `VNM` → `PASS_PROTOTYPE` (vnstock-derived, marked prototype)
- Prototype count = **2**
- FPT/VNM have prototype adjusted rows from vnstock nhưng không được tính là approved source.
- Backtest runs with caveat: `PROTOTYPE_ONLY_UNAPPROVED_SOURCE`

This section proves:
- The trading core can run end-to-end when the data gate is relaxed for prototype.
- These results are **not official production backtest**.

## 7. Source Evidence Explanation

**HPG/VCB/CTG/VHM thiếu adjusted/corporate action source.**

Evidence summary:
- `event_news_items` table: exists, 20 rows (all FPT from IR disclosure crawl).
- `event_news_raw_payloads` table: exists, 20 rows (all FPT raw HTML).
- VNM/HPG/VCB/CTG/VHM: **NO DB event rows**.
- FPT official PDF: found at vnstock IR, 769,594 bytes.
- **FPT official PDF hiện là scanned/image-based** nên chưa extract được structured fields nếu không OCR.
- `pdftotext` extracted ~114 bytes only (digital signature line).
- No OCR installed — no heavy dependencies used.
- Required fields missing: `ex_date`, `record_date`, `payment_date`, `cash_dividend_per_share`, `currency`.
- Approved adjusted OHLC remains BLOCKED pending approved source.

## 8. Backtest Realism Explanation

**Cost model:** Every trade charges:
- **Commission:** 15 bps per side (buy + sell)
- **Slippage:** 5 bps per side (bps model, not market impact)
- **Price-band guard:** ±7% HOSE, ±15% UPCoM, ±10% HNX (when enabled)

Trade-level fields visible:
- `raw_base_price` (signal price)
- `execution_price` (after slippage)
- `slippage_bps`, `slippage_value_estimate`
- `commission`
- `gross_value`, `net_value`

Metrics:
- `total_return_pct`, `sharpe_ratio`, `sortino_ratio`
- `profit_factor`, `max_drawdown_pct`, `win_rate`
- `total_commission`, `total_slippage_estimate`
- `trade_count`, `closed_trade_count`

**Note:** Zero-trade strategies (e.g., ma_cross_v1 with no signals) have 0 commission and 0 slippage.

## 9. Current Blockers

1. **FPT official PDF is scanned/image-based** — structured fields cannot be extracted without OCR.
2. **HPG/VCB/CTG/VHM have no corporate action source** — no DB event rows, no vnstock data.
3. **vnstock is not an approved source** — FPT/VNM prototype data exists but is not production-ready.
4. **No approved adjusted OHLC vendor** — CSI, Bloomberg, Refinitiv not integrated.

Three paths forward (all currently blocked):
1. Find text-based FPT BOD resolution PDF or install OCR.
2. Integrate HOSE/HNX official CAF/XML corporate action feed.
3. License CSI/Bloomberg/Refinitiv adjusted OHLC vendor data.

## 10. Suggested Mentor Decision

- **Option A:** Accept prototype-only mode for FPT/VNM research while pursuing approved source.
- **Option B:** Prioritize OCR/text extraction for FPT official PDF.
- **Option C:** Pursue HOSE/HNX CAF/XML corporate action feed integration.
- **Option D:** License a vendor adjusted OHLC source (CSI/Bloomberg/Refinitiv).

**Recommended next step:** Pursue Option A (prototype research) + Option B (FPT PDF text extraction) in parallel.
