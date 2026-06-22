# QuestDB overnight ingest run

## Run overnight (one command)
```bat
scripts\run_overnight_vietcap_questdb_ingest.bat
```
Loops the operator-safe ingester in rounds until `daily_prices` reaches ~3M rows
or ~1500 distinct symbols. On Vietcap throttling the ingester exits 75; the runner
waits 30 minutes and resumes. Output is teed to `logs\questdb_ingest\overnight_<timestamp>.log`.

## Monitor (anytime, read-only)
```bat
python scripts\questdb_ingest_status.py
```

## Stop safely
Press `Ctrl+C` in the runner window. Progress is checkpointed (`--resume --only-missing`)
and DEDUP makes re-runs idempotent, so just re-run the same command to continue.

## Mentor demo
```bat
python scripts\demo_deep_agent_questdb_cli.py "how many rows are in QuestDB"
python scripts\demo_deep_agent_questdb_cli.py "show latest FPT data"
python scripts\demo_deep_agent_questdb_cli.py "backtest MA strategy for FPT from 2020 to 2025"
python scripts\demo_questdb_strategy_backtest.py --symbol FPT --start-date 2020-01-01 --end-date 2025-12-31 --show-trades 5
```

## Caveat (not complete yet)
The full target is NOT reached until `SELECT count() FROM daily_prices` exceeds
3,000,000 rows and `count_distinct(symbol)` is close to 1500/1597. As of this commit
it is 300,523 rows / 111 symbols because the Vietcap endpoint is returning HTTP 429
(throttled). Run the overnight command above until the count converges.
