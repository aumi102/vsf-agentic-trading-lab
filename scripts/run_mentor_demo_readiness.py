"""Read-only mentor demo readiness check.

This script does not start/stop services and does not mutate QuestDB. It runs
local CLI checks for market, FA, event guardrails, persisted backtests, and
optionally DeepAgents when requested.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass


@dataclass
class CheckResult:
    name: str
    status: str
    exit_code: int
    command: list[str]
    output: str


MARKET_DEEPAGENTS_TOOLS = {"get_symbol_summary", "get_latest_ohlcv", "get_latest_features", "get_latest_signal"}
FINANCIAL_DEEPAGENTS_TOOLS = {"get_latest_financial_report", "get_financial_metrics", "get_financial_report_summary"}
BACKTEST_DEEPAGENTS_TOOLS = {"get_latest_backtest_metrics", "get_backtest_strategy_comparison", "get_backtest_equity_curve"}
LIVE_BACKTRADER_TOOL_NAMES = {"run_ma_backtest", "run_backtrader", "run_backtrader_questdb_demo", "run_backtrader_questdb_persist"}


def _extract_tool_calls(output: str) -> set[str]:
    tools: set[str] = set()
    for line in output.splitlines():
        match = re.match(r"\s*-\s+([A-Za-z0-9_]+)\s+args=", line)
        if match:
            tools.add(match.group(1))
    return tools


def _validate_deepagents_semantics(query: str, output: str) -> tuple[bool, str]:
    lower = output.lower()
    tools = _extract_tool_calls(output)
    if "status: ok" not in lower:
        return False, "DeepAgents status is not ok"
    if query == "summary FPT":
        if not (tools & MARKET_DEEPAGENTS_TOOLS):
            return False, f"summary FPT did not use market summary tools; tools={sorted(tools)}"
        disallowed = tools & (FINANCIAL_DEEPAGENTS_TOOLS | BACKTEST_DEEPAGENTS_TOOLS)
        if disallowed:
            return False, f"summary FPT used disallowed tools; tools={sorted(disallowed)}"
        return True, "semantic route ok"
    if query == "financial report FPT":
        if not (tools & FINANCIAL_DEEPAGENTS_TOOLS):
            return False, f"financial report FPT did not use FA tools; tools={sorted(tools)}"
        return True, "semantic route ok"
    if query == "compare backtest strategies FPT":
        if "get_backtest_strategy_comparison" not in tools:
            return False, f"backtest comparison did not use persisted comparison tool; tools={sorted(tools)}"
        live = tools & LIVE_BACKTRADER_TOOL_NAMES
        if live:
            return False, f"backtest query used live Backtrader tool; tools={sorted(live)}"
        return True, "semantic route ok"
    return True, "no semantic route rule"


def _run(name: str, command: list[str], *, expect_unsupported: bool = False) -> CheckResult:
    print(f"\n=== {name} ===")
    print("$ " + " ".join(command))
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    if output:
        print(output.strip())
    if proc.returncode == 0:
        status = "PASS"
    elif expect_unsupported and "status: unsupported" in output.lower():
        status = "PASS"
    else:
        status = "FAIL"
    print(f"RESULT={status} exit_code={proc.returncode}")
    return CheckResult(name, status, proc.returncode, command, output)


def _run_deepagents(name: str, query: str) -> CheckResult:
    command = [sys.executable, "scripts\\demo_deepagents_questdb_cli.py", query]
    print(f"\n=== {name} ===")
    print("$ " + " ".join(command))
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    if output:
        print(output.strip())
    lower = output.lower()
    if "invalid_api_key" in lower or "incorrect api key" in lower or "401" in lower:
        status = "FAILED_CREDENTIAL"
    elif proc.returncode == 0:
        ok, reason = _validate_deepagents_semantics(query, output)
        status = "PASS" if ok else "FAIL"
        print(f"SEMANTIC_CHECK={status} reason={reason}")
    else:
        status = "FAIL"
    print(f"RESULT={status} exit_code={proc.returncode}")
    return CheckResult(name, status, proc.returncode, command, output)


def _summary(results: list[CheckResult]) -> str:
    required_failures = [r for r in results if r.status == "FAIL" and not r.name.startswith("DeepAgents")]
    optional_failures = [r for r in results if r.status in {"FAIL", "FAILED_CREDENTIAL"} and r.name.startswith("DeepAgents")]
    if required_failures:
        return "FAIL"
    if optional_failures:
        return "PARTIAL"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only mentor demo readiness checks.")
    parser.add_argument("--deepagents", action="store_true", help="Run optional live DeepAgents checks when OPENAI_API_KEY exists.")
    args = parser.parse_args()

    py = sys.executable
    results: list[CheckResult] = []
    checks = [
        ("QuestDB market tables", [py, "scripts\\questdb_tables_status.py"], False),
        ("QuestDB FA tables", [py, "scripts\\questdb_fa_status.py"], False),
        ("QuestDB backtest tables", [py, "scripts\\questdb_backtest_status.py"], False),
        ("Rule market summary", [py, "scripts\\demo_agent_backend_cli.py", "summary FPT"], False),
        ("Rule financial report", [py, "scripts\\demo_agent_backend_cli.py", "financial report FPT"], False),
        ("Rule event guardrail", [py, "scripts\\demo_agent_backend_cli.py", "summary 1 month events and financial report from FPT"], True),
        ("Rule persisted backtest", [py, "scripts\\demo_agent_backend_cli.py", "compare backtest strategies FPT"], False),
    ]
    for name, command, expect_unsupported in checks:
        results.append(_run(name, command, expect_unsupported=expect_unsupported))

    if args.deepagents:
        if not os.environ.get("OPENAI_API_KEY"):
            print("\n=== DeepAgents ===")
            print("RESULT=SKIPPED reason=OPENAI_API_KEY not set")
            results.append(CheckResult("DeepAgents skipped", "SKIPPED", 0, [], ""))
        else:
            for query in ("summary FPT", "financial report FPT", "compare backtest strategies FPT"):
                results.append(_run_deepagents(f"DeepAgents {query}", query))
    else:
        print("\nDeepAgents checks skipped. Use --deepagents to run them.")

    final = _summary(results)
    print("\n=== SUMMARY ===")
    for result in results:
        print(f"{result.status:<18} {result.name}")
    print(f"FINAL_STATUS={final}")
    return 1 if final == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
