from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.tools._store import DEFAULT_DB_PATH
from trading_agent.tools.feature_tool import compute_latest_features
from trading_agent.tools.market_data_tool import get_latest_market_data
from trading_agent.tools.report_tool import compose_market_answer
from trading_agent.tools.risk_tool import assess_symbol_risk
from trading_agent.tools.signal_tool import evaluate_active_signals


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run deterministic MVP agent tool calls for one symbol.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    symbol = args.symbol.strip().upper()
    outputs = {
        "market_data": get_latest_market_data(symbol, args.db_path),
        "features": compute_latest_features(symbol, args.db_path),
        "signal": evaluate_active_signals(symbol, args.db_path),
        "risk": assess_symbol_risk(symbol, args.db_path),
    }
    for name, output in outputs.items():
        print(f"## {name}")
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    report = compose_market_answer(symbol, language="vi", db_path=args.db_path)
    print("## final_answer")
    print(report["answer_markdown"])
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
