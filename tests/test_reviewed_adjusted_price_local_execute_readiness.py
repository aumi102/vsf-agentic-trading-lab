from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from trading_agent.db.schema import create_schema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("scripts/run_reviewed_adjusted_price_local_execute_readiness.py")
PACKAGE = Path("tests/fixtures/adjustment_factors/reviewed_evidence_package")


def test_refuses_missing_db_path(tmp_path: Path) -> None:
    result = _run_internal(tmp_path, db_path=None)

    assert result["status"] == "invalid_request"
    assert "db_path_required" in result["reasons"]


def test_refuses_demo_db_by_default(tmp_path: Path) -> None:
    result = _run_internal(tmp_path, db_path=Path("data/demo/mvp_trading_agent.sqlite"))

    assert result["status"] == "invalid_request"
    assert "demo_db_blocked" in result["reasons"]


def test_allows_demo_db_only_with_explicit_flag(tmp_path: Path) -> None:
    completed = _run_cli(
        tmp_path,
        "--package-dir",
        str(tmp_path / "missing_package"),
        "--db-path",
        "data/demo/mvp_trading_agent.sqlite",
        "--allow-demo-db",
    )

    assert completed.returncode == 1
    assert "demo_db_blocked" not in completed.stdout


def test_valid_temp_db_execute_returns_status_ok(tmp_path: Path) -> None:
    result = _run_internal(tmp_path, db_path=_make_db(tmp_path))

    assert result["status"] == "ok"
    assert result["db_mutation_made"] is True
    assert result["readiness_status"] == "ok"
    assert result["backtest_gate"] == "pass"


def test_readiness_json_written(tmp_path: Path) -> None:
    readiness_output = tmp_path / "readiness.json"

    result = _run_internal(tmp_path, db_path=_make_db(tmp_path), readiness_output=readiness_output)

    assert result["status"] == "ok"
    assert json.loads(readiness_output.read_text(encoding="utf-8"))["status"] == "ok"


def test_markdown_report_written(tmp_path: Path) -> None:
    report = tmp_path / "execute_readiness.md"

    result = _run_internal(tmp_path, db_path=_make_db(tmp_path), report_md=report)

    assert result["status"] == "ok"
    text = report.read_text(encoding="utf-8")
    assert "Reviewed Adjusted Price Local Execute Readiness" in text
    assert "Backtrader/VN100 remains blocked" in text


def test_partial_db_coverage_returns_not_ready(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path, extra_uncovered=True)

    result = _run_internal(tmp_path, db_path=db_path)

    assert result["status"] == "not_ready"
    assert result["backtest_gate"] == "blocked"
    assert any("not_ready" in reason or "blocked" in reason for reason in result["reasons"])


def test_missing_package_exits_one_cleanly(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, "--package-dir", str(tmp_path / "missing"))

    assert completed.returncode == 1
    assert "Traceback" not in completed.stderr
    assert '"status": "not_ready"' in completed.stdout


def test_no_network_imports() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert all(name not in text for name in ["requests", "httpx", "urllib"])


def test_no_backtrader_docker_questdb_behavior() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    assert "import backtrader" not in text
    assert "import docker" not in text
    assert "questdb" not in text


def test_no_generated_files_tracked_by_script() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "git add" not in text
    assert "reports/reviewed_evidence" not in text


def _run_internal(
    tmp_path: Path,
    *,
    db_path: Path | None,
    readiness_output: Path | None = None,
    report_md: Path | None = None,
) -> dict[str, object]:
    from scripts.run_reviewed_adjusted_price_local_execute_readiness import run_local_execute_readiness

    package = tmp_path / "package"
    shutil.copytree(ROOT / PACKAGE, package)
    return run_local_execute_readiness(
        package_dir=package,
        symbols=["FPT", "VNM", "VCB"],
        db_path=db_path,
        factor_output_path=tmp_path / "factors.json",
        validation_output_path=tmp_path / "validation.json",
        readiness_output_path=readiness_output or tmp_path / "readiness.json",
        report_md_path=report_md or tmp_path / "execute_readiness.md",
    )


def _run_cli(tmp_path: Path, *overrides: str) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--package-dir",
        str(_copy_package(tmp_path)),
        "--symbols",
        "FPT,VNM,VCB",
        "--db-path",
        str(_make_db(tmp_path)),
        "--factor-output",
        str(tmp_path / "factors.json"),
        "--validation-output",
        str(tmp_path / "validation.json"),
        "--readiness-output",
        str(tmp_path / "readiness.json"),
        "--report-md",
        str(tmp_path / "execute_readiness.md"),
    ]
    for index in range(0, len(overrides), 2):
        flag = overrides[index]
        if flag == "--allow-demo-db":
            args.append(flag)
            continue
        value = overrides[index + 1]
        if flag in args:
            args[args.index(flag) + 1] = value
        else:
            args.extend([flag, value])
    return subprocess.run(args, cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=False)


def _copy_package(tmp_path: Path) -> Path:
    package = tmp_path / "package_cli"
    if not package.exists():
        shutil.copytree(ROOT / PACKAGE, package)
    return package


def _make_db(tmp_path: Path, *, extra_uncovered: bool = False) -> Path:
    db_path = tmp_path / "execute_readiness.sqlite"
    raw_close = {"FPT": 100.0, "VNM": 200.0, "VCB": 50.0}
    with sqlite3.connect(db_path) as con:
        create_schema(con)
        rows = [(symbol, "2026-01-02", close) for symbol, close in raw_close.items()]
        if extra_uncovered:
            rows.append(("FPT", "2026-01-03", 100.0))
        for symbol, trade_date, close in rows:
            con.execute(
                """
                INSERT INTO daily_prices (
                    security_id, symbol, trade_date, open, high, low, close,
                    volume, value, price_basis, adjustment_status, source_id, raw_path, quality_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"fixture:execute_readiness:{symbol}:{trade_date}",
                    symbol,
                    trade_date,
                    close * 0.95,
                    close * 1.05,
                    close * 0.9,
                    close,
                    1000.0,
                    close * 1000.0,
                    "source_reported",
                    "unknown",
                    "fixture:daily_prices_execute_readiness",
                    f"synthetic://execute-readiness/{symbol.lower()}/{trade_date}",
                    "ok",
                ),
            )
        con.commit()
    return db_path
