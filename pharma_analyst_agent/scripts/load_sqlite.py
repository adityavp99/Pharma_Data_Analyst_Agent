from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
DB_PATH = BASE_DIR / "data" / "processed" / "pharma_mvp.db"
TABLES = ["trials", "sites", "patients", "adverse_events", "lab_results", "drug_sales"]
INDEXES = [
    ("idx_trials_trial_id", "trials", "trial_id"),
    ("idx_sites_trial_id", "sites", "trial_id"),
    ("idx_patients_trial_id", "patients", "trial_id"),
    ("idx_patients_site_id", "patients", "site_id"),
    ("idx_adverse_events_trial_id", "adverse_events", "trial_id"),
    ("idx_adverse_events_patient_id", "adverse_events", "patient_id"),
    ("idx_lab_results_trial_id", "lab_results", "trial_id"),
    ("idx_lab_results_patient_id", "lab_results", "patient_id"),
    ("idx_drug_sales_drug_name", "drug_sales", "drug_name"),
    ("idx_drug_sales_country", "drug_sales", "country"),
    ("idx_drug_sales_month", "drug_sales", "month"),
]


def load_database() -> dict[str, int]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        for table in TABLES:
            csv_path = RAW_DIR / f"{table}.csv"
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing input CSV: {csv_path}")
            frame = pd.read_csv(csv_path)
            frame.to_sql(table, conn, if_exists="replace", index=False)

        for index_name, table_name, column_name in INDEXES:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_name})")

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLES
        }
    return counts


if __name__ == "__main__":
    row_counts = load_database()
    print(f"SQLite database loaded at {DB_PATH}:")
    for table_name, row_count in row_counts.items():
        print(f"- {table_name}: {row_count:,} rows")
