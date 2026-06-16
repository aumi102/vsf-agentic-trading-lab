from __future__ import annotations

import pandas as pd


FEATURE_VERSION = "mvp_daily_v1"


def compute_feature_snapshots(daily_prices: pd.DataFrame) -> pd.DataFrame:
    if daily_prices.empty:
        return pd.DataFrame(
            columns=[
                "security_id",
                "symbol",
                "as_of_date",
                "return_1d",
                "return_5d",
                "return_20d",
                "ma_20",
                "ma_50",
                "volatility_20d",
                "volume_ratio_20d",
                "feature_version",
                "lookback_coverage",
                "quality_status",
            ]
        )

    frames = []
    ordered = daily_prices.sort_values(["security_id", "trade_date"]).copy()
    ordered["close"] = pd.to_numeric(ordered["close"], errors="coerce")
    ordered["volume"] = pd.to_numeric(ordered["volume"], errors="coerce")

    for _, group in ordered.groupby("security_id", sort=False):
        g = group.copy()
        close = g["close"]
        volume = g["volume"]
        g["as_of_date"] = g["trade_date"]
        g["return_1d"] = close.pct_change(1)
        g["return_5d"] = close.pct_change(5)
        g["return_20d"] = close.pct_change(20)
        g["ma_20"] = close.rolling(20, min_periods=20).mean()
        g["ma_50"] = close.rolling(50, min_periods=50).mean()
        g["volatility_20d"] = close.pct_change(1).rolling(20, min_periods=20).std()
        g["volume_ratio_20d"] = volume / volume.rolling(20, min_periods=20).mean()
        g["lookback_coverage"] = range(1, len(g) + 1)
        g["feature_version"] = FEATURE_VERSION
        g["quality_status"] = g["lookback_coverage"].apply(lambda value: "pass" if value >= 50 else "warn")
        frames.append(
            g[
                [
                    "security_id",
                    "symbol",
                    "as_of_date",
                    "return_1d",
                    "return_5d",
                    "return_20d",
                    "ma_20",
                    "ma_50",
                    "volatility_20d",
                    "volume_ratio_20d",
                    "feature_version",
                    "lookback_coverage",
                    "quality_status",
                ]
            ]
        )
    result = pd.concat(frames, ignore_index=True)
    return result.where(pd.notna(result), None)
