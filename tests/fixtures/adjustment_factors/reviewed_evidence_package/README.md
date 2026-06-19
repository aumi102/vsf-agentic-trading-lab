# Reviewed Evidence Package Fixture

This package is synthetic and development-only. It is not real market data and
must not be used as production adjusted-price evidence.

Files:

- `manifest.json`: reviewed metadata for `payload.json`, including SHA-256.
- `payload.json`: synthetic FPT/VNM/VCB adjusted-price rows.
- `payload.csv`: same synthetic rows in CSV form for intake parity checks.

The package QA script computes payload hashes locally and runs the reviewed
intake contract without live network fetches, full VN100, production DB
mutation, Docker/scheduler, or Backtrader.
