from __future__ import annotations

from pathlib import Path

from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools._store import DEFAULT_DB_PATH


def assess_symbol_risk(symbol: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, object]:
    normalized = symbol.strip().upper()
    market = get_latest_market_data(normalized, db_path)
    features = compute_latest_features(normalized, db_path)
    caveats = []
    flags = []
    if market.get("status") != "ok" or features.get("status") != "ok":
        return {
            "status": "not_available",
            "symbol": normalized,
            "risk_flags": ["missing_market_or_feature_data"],
            "quality_status": "fail",
            "caveats": [*(market.get("caveats") or []), *(features.get("caveats") or [])],
        }
    feature_values = features["features"]
    volatility = feature_values.get("volatility_20d")
    volume_ratio = feature_values.get("volume_ratio_20d")
    if volatility is None:
        flags.append("missing_volatility_20d")
    elif volatility > 0.04:
        flags.append("high_20d_volatility")
    elif volatility > 0.025:
        flags.append("moderate_20d_volatility")
    else:
        flags.append("normal_20d_volatility")
    if volume_ratio is None:
        flags.append("missing_volume_ratio_20d")
    elif volume_ratio < 0.5:
        flags.append("thin_recent_volume")
    if market.get("adjustment_status") == "unknown":
        caveats.append("Corporate-action adjustment status is unknown.")
    quality_status = "warn" if caveats or any(flag.startswith("missing_") for flag in flags) else "pass"
    return {
        "status": "ok",
        "symbol": normalized,
        "as_of_date": features["as_of_date"],
        "volatility_20d": volatility,
        "volume_ratio_20d": volume_ratio,
        "risk_flags": flags,
        "quality_status": quality_status,
        "caveats": caveats,
    }
