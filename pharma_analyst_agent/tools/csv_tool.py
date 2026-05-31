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


def load_csv_to_sqlite(file_obj: BinaryIO, db_path: str | Path, table_name: str = "uploaded_data") -> dict[str, object]:
    frame = pd.read_csv(file_obj)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        frame.to_sql(table_name, conn, if_exists="replace", index=False)
    return {
        "db_path": str(db_path),
        "table_name": table_name,
        "rows": len(frame),
        "columns": frame.columns.tolist(),
        "sample_rows": frame.head(5).to_dict("records"),
    }
