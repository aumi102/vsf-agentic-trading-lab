# Batch and cron operations

This page documents safe demo and batch operations for the QuestDB-backed VSF trading agent.

## Safety defaults

- Do not run full OHLCV or full FA universe jobs during a mentor demo.
- Run smoke symbols first, then expand only after checking status scripts.
- DeepAgents reads persisted QuestDB results only. It does not run ingestion or live Backtrader.
- Rebuild derived market tables after new OHLCV ingestion.
- Rerun persisted backtests only after a data refresh or strategy/config change.

## Local existing QuestDB demo

Readiness:

```bat
python scripts\run_mentor_demo_readiness.py
python scripts\run_mentor_demo_readiness.py --deepagents
```

Backend:

```bat
python scripts\run_questdb_agent_backend.py --host 127.0.0.1 --port 8010 --questdb-url http://localhost:9000
```

Smoke:

```bat
python scripts\smoke_questdb_agent_backend.py --api-url http://127.0.0.1:8010
```

Validation:

```bat
python scripts\run_validation_gates.py
python scripts\run_validation_gates.py --write-report docs\demo\validation_gate_latest.md
```

## OHLCV batch path

Existing OHLCV ingestion scripts are intentionally not run from this document. For an overnight/local batch, use the existing project runner selected by the operator, then verify:

```bat
python scripts\questdb_tables_status.py
python scripts\build_questdb_derived_tables.py --mode all
python scripts\questdb_tables_status.py
```

Do not drop/recreate `daily_prices`.

## Financial report batches

Smoke only:

```bat
python scripts\ingest_vietcap_financial_reports_to_questdb.py --symbols FPT,VNM,VCB --statements balance_sheet,income_statement,cash_flow,notes --replace-mode table --allow-table-replace
python scripts\questdb_fa_status.py
```

Larger runs should use run-scoped or table replacement intentionally:

```bat
python scripts\ingest_vietcap_financial_reports_to_questdb.py --limit-symbols 20 --statements balance_sheet,income_statement,cash_flow,notes --replace-mode run
python scripts\questdb_fa_status.py
```

Controlled expanded preflight used for mentor-readiness evidence:

```bat
python scripts\ingest_vietcap_financial_reports_to_questdb.py --symbols FPT,VNM,VCB,A32,AAA,AAH,AAM,AAN,AAS,AAT,AAV,ABB,ABC,ABI,ABR,ABS,ABT,ABW,ACB,ACC,ACE,ACG,ACL,ACM,ACS,ACV,ADC,ADG,ADP,ADS,AFX,AG1,AGF,AGG,AGM,AGP,AGR,AGX,AIC,AIG,ALC,ALT,ALV,AMC,AME,AMP,AMS,AMV,ANT,ANV,APC,APF,APG --statements balance_sheet,income_statement,cash_flow,notes --replace-mode run
python scripts\questdb_fa_status.py
```

Do not run full FA universe ingestion during the mentor demo unless explicitly approved.

## Backtest persistence batch

Demo symbols only:

```bat
python scripts\run_backtrader_questdb_persist.py --symbols FPT,VNM,HPG --start-date 2020-01-01 --end-date 2025-12-31 --replace-run-table
python scripts\questdb_backtest_status.py
```

This rebuilds only `backtest_*` result tables. It does not mutate market or FA tables.

## Windows Task Scheduler outline

Use a `.bat` wrapper that activates the `vsf-trading` environment, changes to the repo, runs the approved batch command, and writes logs outside the repository or under an ignored `logs/` directory.

Example wrapper shape:

```bat
@echo off
call conda activate vsf-trading
cd /d D:\Nguyen_Duc_Hoang_Phuc\vsf
python scripts\questdb_tables_status.py
python scripts\build_questdb_derived_tables.py --mode all
python scripts\questdb_tables_status.py
```

Task Scheduler settings:

- Trigger: daily or overnight window.
- Action: run the `.bat` wrapper.
- Start in: `D:\Nguyen_Duc_Hoang_Phuc\vsf`.
- Stop task only by operator decision; do not let demo scripts kill overnight ingestion.

## Docker Compose notes

Packaging files are provided for a fresh demo stack:

```bat
docker compose config
docker compose up --build
```

The Docker stack does not copy the existing local QuestDB dataset. To use the local 4.38M-row dataset in Docker, configure a QuestDB volume/export/import path explicitly. Otherwise the Docker QuestDB service starts empty.

To run only the backend container against the existing host QuestDB dataset:

```bat
docker compose -f docker-compose.backend-local.yml config
docker compose -f docker-compose.backend-local.yml up --build
curl.exe -s http://127.0.0.1:8010/health
curl.exe -s http://127.0.0.1:8010/market/summary/FPT
curl.exe -s http://127.0.0.1:8010/backtest/comparison/FPT
```

The default Docker image is lean and verifies the rule-based/guarded-direct backend demo. Optional live DeepAgents fallback dependencies can be installed with:

```bat
docker build --build-arg INSTALL_DEEPAGENTS=true -t vsf-agent-backend:demo-deepagents .
```

Environment variables:

- `OPENAI_API_KEY` can be provided through an uncommitted `.env` file or operator runtime environment. Do not commit `.env` and do not use `docker compose config` with secret interpolation that prints credentials.
- `VSF_DEEPAGENTS_MODEL` defaults to `gpt-4.1-mini`.
- `QUESTDB_URL` inside the backend container defaults to `http://questdb:9000`.
