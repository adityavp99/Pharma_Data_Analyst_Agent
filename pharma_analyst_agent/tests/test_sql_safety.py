from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.sql_tool import maybe_add_limit, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO trials VALUES (1)",
        "UPDATE trials SET status = 'Completed'",
        "DELETE FROM trials",
        "DROP TABLE trials",
        "ALTER TABLE trials ADD COLUMN x TEXT",
        "CREATE TABLE x (id INTEGER)",
        "REPLACE INTO trials VALUES (1)",
        "TRUNCATE TABLE trials",
        "ATTACH DATABASE 'x.db' AS x",
        "DETACH DATABASE x",
        "PRAGMA table_info(trials)",
        "VACUUM",
    ],
)
def test_validate_sql_rejects_mutations_and_admin_commands(sql: str) -> None:
    with pytest.raises(ValueError):
        validate_sql(sql)


def test_validate_sql_rejects_multiple_statements() -> None:
    with pytest.raises(ValueError):
        validate_sql("SELECT * FROM trials; SELECT * FROM patients;")


def test_validate_sql_allows_select_and_with() -> None:
    validate_sql("SELECT * FROM trials")
    validate_sql("WITH x AS (SELECT * FROM trials) SELECT * FROM x")


def test_maybe_add_limit_preserves_existing_limit() -> None:
    assert maybe_add_limit("SELECT * FROM trials LIMIT 5", 200).endswith("LIMIT 5")


def test_maybe_add_limit_adds_default_limit() -> None:
    assert maybe_add_limit("SELECT * FROM trials", 200).endswith("LIMIT 200")
