"""Trading strategy signal generator -- BUY / SELL / HOLD.

Reads adjusted OHLCV bars from QuestDB daily_prices and computes
strategy signals for the given symbols.

BLOCKED -- if adjusted OHLCV readiness check fails (no source-backed adjustment factors).

Signal contract per symbol:
  {
    symbol, as_of, strategy, signal: BUY|SELL|HOLD,
    score, features_used, reason, risk_flags,
    data_source, caveats
  }
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "src"), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from trading_agent.storage import questdb_client as qdb  # noqa: E402
from scripts.adjusted_ohlc_readiness import check_adjusted_readiness  # noqa: E402

DEFAULT_URL = qdb.DEFAULT_QUESTDB_URL

# Strategy registry
STRATEGIES = {
    "momentum_v1": "MA20/MA50 cross (trend following)",
    "ma_cross_v1": "MA20/MA60 cross (trend following, alias for momentum_v1)",
    "mean_reversion_v1": "RSI(14) mean reversion",
    "buy_hold_v1": "Long everything",
    "baseline_buy_hold_v1": "Long everything (baseline, engine validation only)",
}


# ─── data fetch ───────────────────────────────────────────────────────────────

def _fetch_bars(client, base_url: str, symbol: str, lookback: int = 120) -> list[dict[str, Any]] | None:
    """Read bars from adjusted_daily_prices only. Returns None if no source-backed data.

    NEVER falls back to raw daily_prices — blocked symbols return None.
    """
    # Check if source-backed table has data for this symbol (limit 1 for speed)
    adj_exists_sql = (
        f"SELECT trade_date FROM adjusted_daily_prices WHERE symbol = '{symbol}' "
        f"AND adjustment_status = 'source_backed_corporate_action' "
        f"ORDER BY trade_date DESC LIMIT 1"
    )
    try:
        adj_exists = qdb.exec_scalar(client, base_url, adj_exists_sql)
    except Exception:
        adj_exists = None

    if adj_exists is None:
        # No source-backed data for this symbol — BLOCKED, no raw fallback
        return None

    # Use source-backed adjusted table (filter to last 5 years to reduce partitions)
    five_years_ago = "2021-01-01"
    sql = (
        f"SELECT trade_date, open, high, low, close, volume, "
        f"adjustment_factor, adjustment_status, exchange "
        f"FROM adjusted_daily_prices "
        f"WHERE symbol = '{symbol}' "
        f"AND adjustment_status = 'source_backed_corporate_action' "
        f"AND trade_date >= '{five_years_ago}' "
        f"ORDER BY trade_date DESC "
        f"LIMIT {lookback}"
    )
    cols, rows = qdb.exec_rows(client, base_url, sql)
    result = []
    for r in rows[::-1]:  # oldest first
        d = _row_to_dict(cols, r)
        d["adjusted_open"] = d.get("open")
        d["adjusted_high"] = d.get("high")
        d["adjusted_low"] = d.get("low")
        d["adjusted_close"] = d.get("close")
        result.append(d)
    return result


def _row_to_dict(cols: list[str], row: list) -> dict[str, Any]:
    return {c: v for c, v in zip(cols, row)}


# ─── price helpers ──────────────────────────────────────────────────────────

def _sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period < 1:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < 2:
        return out
    ups, downs = [0.0] * len(values), [0.0] * len(values)
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        ups[i] = max(d, 0.0)
        downs[i] = max(-d, 0.0)
    au = _sma(ups, period)
    ad = _sma(downs, period)
    for i in range(len(values)):
        a_u, a_d = au[i], ad[i]
        if a_u is None or a_d is None:
            continue
        out[i] = 100.0 - 100.0 / (1.0 + (a_u / a_d if a_d else 1e-9))
    return out


# ─── signals ────────────────────────────────────────────────────────────────

def _signal_momentum_v1(bars: list[dict]) -> dict[str, Any]:
    adj_closes = [float(b["adjusted_close"]) for b in bars if b["adjusted_close"] is not None]
    adj_highs = [float(b["adjusted_high"]) for b in bars if b["adjusted_high"] is not None]
    adj_lows = [float(b["adjusted_low"]) for b in bars if b["adjusted_low"] is not None]
    volumes = [float(b["volume"]) for b in bars if b["volume"] is not None]
    adj_status = bars[-1]["adjustment_status"] if bars else "unknown"

    if len(adj_closes) < 60:
        return _hold("insufficient_bars", -1.0, adj_closes, volumes, adj_status, "need >= 60 bars")

    ma20 = _sma(adj_closes, 20)
    ma50 = _sma(adj_closes, 50)
    ret20 = (adj_closes[-1] / adj_closes[-21] - 1) * 100 if len(adj_closes) > 20 else 0.0
    vol_avg = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1.0
    vol_now = volumes[-1] if volumes else 0.0
    vol_ok = vol_now >= vol_avg * 0.5  # no hard filter, just flag

    diff = (ma20[-1] or 0) - (ma50[-1] or 0)
    ma20_above = (ma20[-1] or 0) > (ma50[-1] or 0)
    prev_diff = (ma20[-2] or 0) - (ma50[-2] or 0) if len(ma20) > 1 else 0.0
    crossed_up = prev_diff <= 0 < diff
    crossed_down = prev_diff >= 0 > diff

    # Compute score
    score = round(ret20 / 10.0, 4)  # -1 to +1 approx
    risk_flags = []
    if adj_status == "adjusted_price_missing_warn":
        risk_flags.append("adjusted_feed_fabricated")
    if not vol_ok:
        risk_flags.append("low_volume")

    if ma20_above and (crossed_up or diff > 0):
        return {
            "signal": "BUY",
            "score": min(score, 1.0),
            "features_used": {
                "ma20": round(ma20[-1], 2) if ma20[-1] else None,
                "ma50": round(ma50[-1], 2) if ma50[-1] else None,
                "ret20d": round(ret20, 2),
                "vol_ratio": round(vol_now / vol_avg, 3) if vol_avg else None,
            },
            "reason": (
                f"MA20 ({ma20[-1]:.2f}) above MA50 ({ma50[-1]:.2f}), "
                f"20d return {ret20:.1f}%, vol ratio {vol_now/vol_avg:.1f}x avg"
            ),
            "risk_flags": risk_flags,
        }
    elif crossed_down or (not ma20_above and diff < -1.0):
        return {
            "signal": "SELL",
            "score": max(score, -1.0),
            "features_used": {
                "ma20": round(ma20[-1], 2) if ma20[-1] else None,
                "ma50": round(ma50[-1], 2) if ma50[-1] else None,
                "ret20d": round(ret20, 2),
                "vol_ratio": round(vol_now / vol_avg, 3) if vol_avg else None,
            },
            "reason": (
                f"MA20 ({ma20[-1]:.2f}) below MA50 ({ma50[-1]:.2f}), "
                f"20d return {ret20:.1f}%"
            ),
            "risk_flags": risk_flags,
        }
    return {
        "signal": "HOLD",
        "score": 0.0,
        "features_used": {
            "ma20": round(ma20[-1], 2) if ma20[-1] else None,
            "ma50": round(ma50[-1], 2) if ma50[-1] else None,
            "ret20d": round(ret20, 2),
        },
        "reason": f"No cross; MA20/MA50 diff={diff:.2f}",
        "risk_flags": risk_flags,
    }


def _signal_mean_reversion_v1(bars: list[dict]) -> dict[str, Any]:
    adj_closes = [float(b["adjusted_close"]) for b in bars if b["adjusted_close"] is not None]
    adj_highs = [float(b["adjusted_high"]) for b in bars if b["adjusted_high"] is not None]
    adj_lows = [float(b["adjusted_low"]) for b in bars if b["adjusted_low"] is not None]
    volumes = [float(b["volume"]) for b in bars if b["volume"] is not None]
    adj_status = bars[-1]["adjustment_status"] if bars else "unknown"

    if len(adj_closes) < 20:
        return _hold("insufficient_bars", 0.0, adj_closes, volumes, adj_status, "need >= 20 bars")

    ma20 = _sma(adj_closes, 20)
    rsi14 = _rsi(adj_closes, 14)
    vol_avg = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1.0
    vol_now = volumes[-1] if volumes else 0.0
    z = (adj_closes[-1] - (ma20[-1] or 0)) / (ma20[-1] or 1e-9)
    rsi = rsi14[-1] if rsi14[-1] is not None else 50.0
    illiquid = vol_now < vol_avg * 0.3

    risk_flags = []
    if adj_status == "adjusted_price_missing_warn":
        risk_flags.append("adjusted_feed_fabricated")
    if illiquid:
        risk_flags.append("illiquid")

    if rsi < 30 and z < -0.5 and not illiquid:
        return {
            "signal": "BUY",
            "score": round((30 - rsi) / 30, 4),
            "features_used": {"rsi14": round(rsi, 1), "z_score": round(z, 3), "ma20": round(ma20[-1], 2) if ma20[-1] else None},
            "reason": f"RSI({rsi:.0f}) < 30, z={z:.2f}, vol OK",
            "risk_flags": risk_flags,
        }
    elif rsi > 55:
        return {
            "signal": "SELL",
            "score": round((rsi - 55) / 45, 4),
            "features_used": {"rsi14": round(rsi, 1), "z_score": round(z, 3), "ma20": round(ma20[-1], 2) if ma20[-1] else None},
            "reason": f"RSI({rsi:.0f}) > 55",
            "risk_flags": risk_flags,
        }
    return {
        "signal": "HOLD",
        "score": 0.0,
        "features_used": {"rsi14": round(rsi, 1), "z_score": round(z, 3)},
        "reason": f"RSI({rsi:.0f}) neutral, z={z:.2f}",
        "risk_flags": risk_flags,
    }


def _signal_buy_hold_v1(bars: list[dict], adj_status: str) -> dict[str, Any]:
    risk_flags = []
    if adj_status == "adjusted_price_missing_warn":
        risk_flags.append("adjusted_feed_fabricated")
    return {
        "signal": "BUY",
        "score": 1.0,
        "features_used": {"bars": len(bars)},
        "reason": f"Buy-hold: all bars (n={len(bars)})",
        "risk_flags": risk_flags,
    }


def _hold(reason: str, score: float, closes: list[float], volumes: list[float], status: str, detail: str) -> dict[str, Any]:
    risk_flags = ["insufficient_data"] if "insufficient" in reason else []
    if status == "adjusted_price_missing_warn":
        risk_flags.append("adjusted_feed_fabricated")
    return {
        "signal": "HOLD", "score": score,
        "features_used": {},
        "reason": f"{detail} -- {reason}",
        "risk_flags": risk_flags,
    }


# ─── main ──────────────────────────────────────────────────────────────────

def compute_signals(
    client, base_url: str,
    symbols: list[str],
    strategy: str,
    lookback: int = 120,
    require_all: bool = False,
    source_policy: str = "approved_only",
) -> tuple[list[dict], list[str]]:
    readiness = check_adjusted_readiness(client, base_url, symbols,
                                          source_policy=source_policy)
    by_symbol = readiness.get("by_symbol", [])
    sym_status = {s["symbol"]: s for s in by_symbol}

    caveats_out = readiness["caveats"][:]
    results = []
    pass_count = 0
    block_count = 0

    for sym in symbols:
        sym_info = sym_status.get(sym, {})
        if sym_info.get("backtest_gate") in ("pass", "partial"):
            bars = _fetch_bars(client, base_url, sym, lookback)
            if bars is None:
                # Should not happen but guard anyway
                block_count += 1
                results.append(_blocked_signal(sym, strategy, sym_info.get("blocked_reason")))
                continue

            adj_status = bars[-1]["adjustment_status"] if bars else "unknown"
            feat_strategy = strategy.replace("_v1", "")
            if feat_strategy in ("momentum", "ma_cross"):
                sig = _signal_momentum_v1(bars)
            elif feat_strategy == "mean_reversion":
                sig = _signal_mean_reversion_v1(bars)
            elif feat_strategy in ("buy_hold", "baseline_buy_hold"):
                sig = _signal_buy_hold_v1(bars, adj_status)
            else:
                sig = _hold("unknown_strategy", 0.0, [], [], adj_status, f"strategy={strategy}")
            results.append({
                "symbol": sym,
                "as_of": bars[-1]["trade_date"] if bars else None,
                "strategy": strategy,
                **sig,
                "data_source": "adjusted_daily_prices",
                "adjustment_status": adj_status,
                "gate": "pass",
                "caveats": [
                    "corporate-event-derived adjusted OHLC (vnstock company_events)",
                    "adjusted OHLCV readiness only -- not financial advice",
                ],
            })
            pass_count += 1
        else:
            block_count += 1
            results.append(_blocked_signal(sym, strategy, sym_info.get("blocked_reason")))

    # Overall status
    if block_count == 0:
        overall = "ok"
    elif pass_count == 0:
        overall = "blocked"
    else:
        overall = "partial"

    if require_all and block_count > 0:
        raise RuntimeError(
            f"SIGNAL_BLOCKED: {block_count} of {len(symbols)} symbols blocked "
            f"(require_all=True). Blocked symbols: "
            f"{[s for s in symbols if sym_status.get(s, {}).get('backtest_gate') != 'pass']}"
        )

    return results, caveats_out, overall


def _blocked_signal(symbol: str, strategy: str, reason: str | None) -> dict:
    return {
        "symbol": symbol,
        "as_of": None,
        "strategy": strategy,
        "signal": "BLOCKED",
        "score": None,
        "features_used": {},
        "reason": reason or "No source-backed adjusted OHLC for this symbol.",
        "risk_flags": ["no_adjusted_source"],
        "data_source": None,
        "adjustment_status": None,
        "gate": "blocked",
        "caveats": [
            "BLOCKED -- no corporate action source. "
            "Raw daily_prices MUST NOT be used as adjusted for trading.",
            "adjusted OHLCV readiness only -- not financial advice",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trading strategy signal generator.")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. FPT,HPG,VCB")
    parser.add_argument("--as-of", default="latest", help="Signal date (default: latest)")
    parser.add_argument("--strategy", default="momentum_v1",
                        choices=["momentum_v1", "ma_cross_v1", "mean_reversion_v1", "buy_hold_v1", "baseline_buy_hold_v1"],
                        help="Strategy to run")
    parser.add_argument("--questdb-url", default=DEFAULT_URL)
    parser.add_argument("--lookback", type=int, default=120, help="Lookback bars")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--require-all", action="store_true",
        help="Exit 1 if any requested symbol is blocked"
    )
    parser.add_argument(
        "--source-policy",
        choices=["approved_only", "prototype_allowed"],
        default="approved_only",
        help="approved_only: vnstock rows are BLOCKED (default). "
             "prototype_allowed: vnstock rows count as PASS_PROTOTYPE.",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    base_url = args.questdb_url.rstrip("/")

    import json as _json

    try:
        with qdb.open_client(timeout_seconds=60.0) as client:
            results, caveats, overall = compute_signals(
                client, base_url, symbols, args.strategy,
                args.lookback, require_all=args.require_all,
                source_policy=args.source_policy,
            )
    except RuntimeError as e:
        if args.json:
            print(_json.dumps({
                "status": "PARTIAL_BLOCKED",
                "error": str(e),
                "symbols": symbols,
                "strategy": args.strategy,
            }, indent=2))
        else:
            print(f"{'='*60}")
            print(f"  SIGNAL PARTIAL BLOCKED")
            print(f"{'='*60}")
            print(f"  {e}")
            print(f"{'='*60}")
        return 1

    if overall == "blocked":
        # All symbols blocked -- exit 1
        if args.json:
            print(_json.dumps({
                "status": "blocked",
                "strategy": args.strategy,
                "signals": results,
                "caveats": caveats,
            }, indent=2))
        else:
            print(f"{'='*60}")
            print(f"Trading Signals  strategy={args.strategy}  overall=BLOCKED")
            print(f"{'='*60}")
            for r in results:
                print(f"\n  [BLOCKED] {r['symbol']}")
                print(f"            {r['reason']}")
            if caveats:
                print(f"\n{'='*60}")
                print("  Caveats:")
                for c in caveats:
                    print(f"    - {c}")
            print(f"{'='*60}")
        return 1

    if args.json:
        print(_json.dumps({
            "status": overall,
            "strategy": args.strategy,
            "signals": results,
            "caveats": caveats,
        }, indent=2))
        return 0 if overall != "blocked" else 1

    print(f"{'='*60}")
    print(f"Trading Signals  strategy={args.strategy}  overall={overall}")
    print(f"{'='*60}")
    for r in results:
        print(f"\n  [{str(r['signal']):4s}] {r['symbol']}  score={r.get('score')}  as_of={r['as_of']}")
        print(f"           reason: {r['reason']}")
        if r.get('features_used'):
            print(f"           features: {r['features_used']}")
        if r.get('risk_flags'):
            print(f"           risk_flags: {r['risk_flags']}")
    if caveats:
        print(f"\n{'='*60}")
        print("  Caveats:")
        for c in caveats:
            print(f"    - {c}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
