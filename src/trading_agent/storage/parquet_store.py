from __future__ import annotations

from pathlib import Path

import pandas as pd


class ParquetStore:
    def __init__(self, base_dir: str | Path = "data/silver") -> None:
        self.base_dir = Path(base_dir)

    def write(self, table_name: str, df: pd.DataFrame) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self.base_dir / f"{table_name}.parquet"
        df.to_parquet(path, index=False)
        return path
