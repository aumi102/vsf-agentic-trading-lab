# QuestDB query benchmark — REST vs PGWire, and the `localhost` finding

Mentor feedback #6: the demo showed *Execute 72.98ms / Network 7.02ms / Total ~80ms*,
while the mentor's own QuestDB execute was ~0.05ms. This document reproduces the
measurement, explains where the 72ms actually went, and records the REST vs PGWire
result.

Reproduce:

```bat
python scripts\benchmark_questdb_query_paths.py --repeats 50
python scripts\benchmark_questdb_query_paths.py --compare-hosts
```

Both are read-only and never mutate QuestDB.

## Headline findings

1. **QuestDB execution is not the bottleneck.** Server-side `execute` time for a
   filtered, indexed query (`... WHERE symbol='FPT' ORDER BY trade_date DESC LIMIT 1`)
   is **~0.0–0.3 ms** — matching the mentor's ~0.05ms. The 72ms seen in the demo was
   client/connection/serialization overhead, not the engine.
2. **`localhost` on Windows costs ~2 seconds per fresh connection.** `localhost`
   resolves to IPv6 `::1` first; QuestDB binds IPv4, so each new connection pays a
   ~2s `::1` connect-timeout fallback before retrying `127.0.0.1`. Using
   `127.0.0.1` removes it. This was the single biggest demo-latency issue.
3. **PGWire (psycopg) is modestly faster than REST for warm repeated reads** —
   roughly 20–30% lower p50 — because it skips REST JSON encoding and reuses a warm
   connection. REST stays the right choice for `/imp` CSV ingestion.

## `localhost` vs `127.0.0.1` (fresh connection, no keep-alive)

`python scripts\benchmark_questdb_query_paths.py --compare-hosts`

| host | p50 ms | min ms | max ms |
|---|---:|---:|---:|
| `http://localhost:9000` | 2048.8 | 2033.4 | 2066.9 |
| `http://127.0.0.1:9000` | 17.9 | 2.3 | 23.2 |

The ~2030ms gap is pure connect overhead. The fix is a one-liner
(`trading_agent.storage.questdb_client.to_ipv4_localhost`) applied at the REST and
PGWire chokepoints: a literal `localhost` host is rewritten to `127.0.0.1`. Real or
remote hostnames are left untouched.

## REST vs PGWire (warm, reused/pooled connection, 50 repeats)

`python scripts\benchmark_questdb_query_paths.py --repeats 50`

| query | path | p50 ms | p95 ms | min ms | max ms | server exec ms |
|---|---|---:|---:|---:|---:|---:|
| latest_ohlcv_FPT | REST | 1.83 | 2.66 | 1.35 | 2.98 | 1.23 |
| latest_ohlcv_FPT | PGWire | 1.60 | 2.54 | 1.16 | 3.34 | 1.48 |
| market_summary_features_FPT | REST | 1.82 | 2.29 | 1.16 | 2.52 | 1.11 |
| market_summary_features_FPT | PGWire | 1.77 | 5.46 | 1.12 | 6.89 | 1.84 |
| latest_signal_FPT | REST | 1.89 | 2.45 | 1.29 | 7.91 | 1.31 |
| latest_signal_FPT | PGWire | 1.39 | 4.46 | 0.93 | 5.17 | 1.48 |
| backtest_comparison_FPT (join) | REST | 1.12 | 1.28 | 0.74 | 1.63 | 0.54 |
| backtest_comparison_FPT (join) | PGWire | 0.76 | 1.09 | 0.38 | 4.77 | 0.72 |
| event_latest_FPT | REST | 0.88 | 1.04 | 0.63 | 1.20 | 0.31 |
| event_latest_FPT | PGWire | 0.57 | 0.96 | 0.20 | 1.05 | 0.46 |
| count_daily_prices | REST | 0.73 | 0.88 | 0.53 | 0.91 | 0.23 |
| count_daily_prices | PGWire | 0.37 | 0.81 | 0.21 | 1.01 | 0.36 |

Mean of per-query p50: **REST = 1.379 ms, PGWire = 1.076 ms** (~22% faster for PGWire).

> Numbers vary run to run (single dev machine, warm cache). The relative picture is
> stable: both paths are low single-digit milliseconds once the connection is warm
> and the host is IPv4.

## Where the demo's 72ms went (decomposition)

| component | typical cost | notes |
|---|---:|---|
| QuestDB `execute` (filtered) | ~0.0–0.3 ms | the actual query engine |
| QuestDB `execute` (full `count()` scan) | ~5.5 ms | avoid full scans / `SELECT *` |
| REST JSON encode + HTTP round trip (warm) | ~0.7–2.5 ms | per call |
| **fresh connection to `localhost` (IPv6 fallback)** | **~2000 ms** | the real culprit; fixed via `127.0.0.1` |
| Web Console / browser render | variable | the 72ms was a console-side figure |

## What we changed for speed (Task H)

1. Normalize `localhost` → `127.0.0.1` for all REST/PGWire reads.
2. Reuse connections: persistent httpx client (REST) and a cached/pooled psycopg
   connection (PGWire), so the connect cost is paid once, not per query.
3. Use `timings=true` on REST `/exec` to report the real server `execute` time in
   API responses (`query_mode`, `execute_ms`, `total_ms`).
4. Filtered, indexed reads with `LIMIT` (no `SELECT *`, no needless full scans).
5. Short-TTL caching (10–30s) for non-mutating demo views (status, menu, benchmark).

## Recommendation

- Keep **REST as the default** (`QUESTDB_QUERY_MODE=rest`); it is simple and within
  noise of PGWire for our query sizes.
- **PGWire is wired and ready** behind `QUESTDB_QUERY_MODE=pgwire` for low-latency
  repeated reads; switch selected read-only APIs to it if a load test shows benefit.
- Keep **REST `/imp`** for CSV ingestion regardless.
- Always use **`127.0.0.1`** (not `localhost`) on Windows demo machines.
