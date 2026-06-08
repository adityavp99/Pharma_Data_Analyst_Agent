from __future__ import annotations

from io import BytesIO
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.csv_tool import load_csv_to_sqlite, safe_table_name


def test_safe_table_name() -> None:
    assert safe_table_name("Sales Export.csv") == "sales_export"
    assert safe_table_name("123 bad name.csv") == "uploaded_data"


def test_load_csv_to_sqlite(tmp_path: Path) -> None:
    csv = BytesIO(b"month,sales\n2025-01,10\n2025-02,20\n")
    db_path = tmp_path / "uploaded.db"
    result = load_csv_to_sqlite(csv, db_path, "sales")
    assert result["rows"] == 2
    assert result["columns"] == ["month", "sales"]
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    assert count == 2


def test_load_csv_to_sqlite_uses_chunks(tmp_path: Path) -> None:
    csv = BytesIO(b"month,sales\n2025-01,10\n2025-02,20\n2025-03,30\n")
    db_path = tmp_path / "uploaded.db"
    result = load_csv_to_sqlite(csv, db_path, "sales", chunk_size=1)
    assert result["rows"] == 3
    assert result["sample_rows"] == [{"month": "2025-01", "sales": 10}]
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT SUM(sales) FROM sales").fetchone()[0]
    assert total == 60
