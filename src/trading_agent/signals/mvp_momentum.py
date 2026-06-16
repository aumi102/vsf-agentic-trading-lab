from __future__ import annotations

import pandas as pd


STRATEGY_ID = "mvp_ma20_ma50_momentum"
SIGNAL_VERSION = "mvp_momentum_v1"


def generate_signals(feature_snapshots: pd.DataFrame, daily_prices: pd.DataFrame) -> pd.DataFrame:
    if feature_snapshots.empty:
        return pd.DataFrame(
            columns=[
                "security_id",
                "symbol",
                "as_of_date",
                "strategy_id",
                "action",
                "score",
                "reason_code",
                "reason_text",
                "signal_version",
                "quality_status",
            ]
        )
    prices = daily_prices[["security_id", "trade_date", "close"]].rename(columns={"trade_date": "as_of_date"})
    merged = feature_snapshots.merge(prices, on=["security_id", "as_of_date"], how="left")
    rows = [_signal_row(row) for _, row in merged.iterrows()]
    return pd.DataFrame(rows)


def evaluate_momentum_signal(close: float | None, ma_20: float | None, ma_50: float | None, return_20d: float | None, lookback_coverage: int) -> dict[str, object]:
    if lookback_coverage < 50 or close is None or ma_20 is None or ma_50 is None or return_20d is None:
        return {
            "action": "HOLD_WITH_LOW_CONFIDENCE",
            "score": 0.0,
            "reason_code": "INSUFFICIENT_LOOKBACK",
            "reason_text": "Insufficient 50-day lookback or missing moving-average inputs.",
            "quality_status": "warn",
        }
    if close > ma_20 > ma_50 and return_20d > 0:
        return {
            "action": "BUY",
            "score": 1.0,
            "reason_code": "BULLISH_MA20_MA50_MOMENTUM",
            "reason_text": "Close is above MA20, MA20 is above MA50, and 20-day return is positive.",
            "quality_status": "pass",
        }
    if close < ma_20 < ma_50 and return_20d < 0:
        return {
            "action": "SELL",
            "score": -1.0,
            "reason_code": "BEARISH_MA20_MA50_MOMENTUM",
            "reason_text": "Close is below MA20, MA20 is below MA50, and 20-day return is negative.",
            "quality_status": "pass",
        }
    return {
        "action": "HOLD",
        "score": 0.0,
        "reason_code": "MIXED_OR_NEUTRAL_MOMENTUM",
        "reason_text": "The MA20/MA50 momentum rule is not decisively bullish or bearish.",
        "quality_status": "pass",
    }


def _signal_row(row: pd.Series) -> dict[str, object]:
    signal = evaluate_momentum_signal(
        _none_if_na(row.get("close")),
        _none_if_na(row.get("ma_20")),
        _none_if_na(row.get("ma_50")),
        _none_if_na(row.get("return_20d")),
        int(row.get("lookback_coverage") or 0),
    )
    return {
        "security_id": row["security_id"],
        "symbol": row["symbol"],
        "as_of_date": row["as_of_date"],
        "strategy_id": STRATEGY_ID,
        "action": signal["action"],
        "score": signal["score"],
        "reason_code": signal["reason_code"],
        "reason_text": signal["reason_text"],
        "signal_version": SIGNAL_VERSION,
        "quality_status": signal["quality_status"],
    }


def _none_if_na(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
