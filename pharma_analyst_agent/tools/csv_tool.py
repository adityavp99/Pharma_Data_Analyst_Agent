from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
import re
import sqlite3

import pandas as pd


def safe_table_name(file_name: str, default: str = "uploaded_data") -> str:
    stem = Path(file_name).stem.lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", stem).strip("_")
    if not cleaned or cleaned[0].isdigit():
        return default
    return cleaned[:48]


def load_csv_to_sqlite(
    file_obj: BinaryIO,
    db_path: str | Path,
    table_name: str = "uploaded_data",
    chunk_size: int = 100_000,
) -> dict[str, object]:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    columns: list[str] = []
    sample_rows: list[dict[str, object]] = []

    with sqlite3.connect(db_path) as conn:
        for chunk_index, frame in enumerate(pd.read_csv(file_obj, chunksize=chunk_size, low_memory=False)):
            if chunk_index == 0:
                columns = frame.columns.tolist()
                sample_rows = frame.head(5).to_dict("records")
                if_exists = "replace"
            else:
                if_exists = "append"

            frame.to_sql(table_name, conn, if_exists=if_exists, index=False)
            total_rows += len(frame)

    return {
        "db_path": str(db_path),
        "table_name": table_name,
        "rows": total_rows,
        "columns": columns,
        "sample_rows": sample_rows,
    }
