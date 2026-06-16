from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trading_agent.tools._store import DEFAULT_DB_PATH

BUILD_SCRIPT = "scripts/build_mvp_db.py"
BUILD_ARGS = ["--symbols", "FPT,VNM,VCB"]

DEMO_SCENARIOS = [
    {
        "label": "market_brief --symbol FPT",
        "args": ["--scenario", "market_brief", "--symbol", "FPT"],
        "expect_exit": 0,
    },
    {
        "label": 'market_brief --query "FPT hôm nay thế nào?"',
        "args": ["--scenario", "market_brief", "--query", "FPT hôm nay thế nào?"],
        "expect_exit": 0,
    },
    {
        "label": "risk_check --symbol VCB",
        "args": ["--scenario", "risk_check", "--symbol", "VCB"],
        "expect_exit": 0,
    },
    {
        "label": "compare --symbols FPT,VNM,VCB",
        "args": ["--scenario", "compare", "--symbols", "FPT,VNM,VCB"],
        "expect_exit": 0,
    },
    {
        "label": "compare --symbols FPT,HPG",
        "args": ["--scenario", "compare", "--symbols", "FPT,HPG"],
        "expect_exit": 0,
    },
    {
        "label": "compare --symbols HPG,XYZ",
        "args": ["--scenario", "compare", "--symbols", "HPG,XYZ"],
        "expect_exit": 1,
    },
]


def _run(args: list[str], *, db_path: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "scripts/run_agent_demo.py", *args]
    if db_path:
        cmd += ["--db-path", db_path]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def _build(db_path: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, BUILD_SCRIPT, *BUILD_ARGS]
    if db_path:
        cmd += ["--db-path", db_path]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


def main(db_path: str | None = None, skip_build: bool = False) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not skip_build:
        print("## Build")
        built = _build(db_path)
        print(built.stdout.strip())
        if built.returncode != 0:
            print(f"[FAIL] build exited {built.returncode}")
            print(built.stderr.strip())
            return 1
        print()

    col_w = 45
    print(f"## Demo suite  ({'custom db' if db_path else DEFAULT_DB_PATH})")
    print(f"{'Command':<{col_w}}  {'Exit':>4}  {'Expected':>8}  {'Pass?':>5}  Status")
    print("-" * (col_w + 35))

    any_fail = False
    for scenario in DEMO_SCENARIOS:
        args = scenario["args"]
        if db_path:
            extra = ["--db-path", db_path]
        else:
            extra = []
        result = _run(args + extra)
        got_exit = result.returncode
        want_exit = scenario["expect_exit"]
        passed = got_exit == want_exit

        status_str = ""
        try:
            for line in result.stdout.splitlines():
                if line.strip().startswith('"status"'):
                    status_str = line.strip()
                    break
        except Exception:
            pass

        mark = "OK  " if passed else "FAIL"
        label = scenario["label"][:col_w]
        print(f"{label:<{col_w}}  {got_exit:>4}  {want_exit:>8}  {mark:>5}  {status_str}")
        if not passed:
            any_fail = True

    print()
    if any_fail:
        print("[FAIL] one or more scenarios did not exit as expected")
        return 1
    print("[OK] all scenarios exited as expected")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the full mentor demo suite and print a status table.")
    parser.add_argument("--db-path", default=None, help="Override DB path (for testing).")
    parser.add_argument("--skip-build", action="store_true", help="Skip the build step (useful when DB is pre-built).")
    args = parser.parse_args()
    raise SystemExit(main(db_path=args.db_path, skip_build=args.skip_build))
