"""
Load: write swaps into the DuckDB warehouse that dbt-solana-models reads from.

The table schema is identical to what the dbt project's sources.yml declares,
so `dbt build` runs unchanged against real data.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parents[1].parent / "dbt" / "solana_warehouse.duckdb"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS solana_swaps (
    signature           VARCHAR,
    block_date          DATE,
    block_time          TIMESTAMP,
    fee_payer           VARCHAR,
    token_sold_symbol   VARCHAR,
    token_bought_symbol VARCHAR,
    token_sold_amount   DOUBLE,
    token_bought_amount DOUBLE,
    program_source      VARCHAR,
    fee_lamports        INTEGER,
    fee_sol             DOUBLE,
    success             BOOLEAN
)
"""

COLUMNS = [
    "signature", "block_date", "block_time", "fee_payer",
    "token_sold_symbol", "token_bought_symbol",
    "token_sold_amount", "token_bought_amount",
    "program_source", "fee_lamports", "fee_sol", "success",
]


def db_path() -> Path:
    return Path(os.getenv("DUCKDB_PATH", str(DEFAULT_DB))).expanduser().resolve()


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    conn.execute(SCHEMA_SQL)
    return conn


def existing_signatures(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT signature FROM solana_swaps").fetchall()
    return {r[0] for r in rows}


def reset_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop and recreate solana_swaps (used to replace fake data with real)."""
    conn.execute("DROP TABLE IF EXISTS solana_swaps")
    conn.execute(SCHEMA_SQL)
    logger.info("solana_swaps reset")


def load_swaps(conn: duckdb.DuckDBPyConnection, rows: list[dict]) -> dict:
    """Insert rows, skipping signatures already present. Returns counts."""
    if not rows:
        return {"attempted": 0, "inserted": 0, "skipped": 0}

    df = pd.DataFrame(rows)[COLUMNS]
    df["block_date"] = pd.to_datetime(df["block_date"]).dt.date
    df["block_time"] = pd.to_datetime(df["block_time"])
    df = df.drop_duplicates(subset=["signature"])

    before = conn.execute("SELECT COUNT(*) FROM solana_swaps").fetchone()[0]
    conn.register("incoming", df)
    conn.execute("""
        INSERT INTO solana_swaps
        SELECT i.* FROM incoming i
        ANTI JOIN solana_swaps s ON s.signature = i.signature
    """)
    conn.unregister("incoming")
    after = conn.execute("SELECT COUNT(*) FROM solana_swaps").fetchone()[0]

    stats = {"attempted": len(df), "inserted": after - before, "skipped": len(df) - (after - before), "total": after}
    logger.info("load: %s", stats)
    return stats


def summary(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute("""
        SELECT program_source,
               COUNT(*)                   AS swaps,
               COUNT(DISTINCT fee_payer)  AS traders,
               MIN(block_time)            AS first_swap,
               MAX(block_time)            AS last_swap
        FROM solana_swaps
        GROUP BY 1 ORDER BY 2 DESC
    """).df()
