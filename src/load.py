import duckdb
import pandas as pd 
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "solana_warehouse.duckdb"

SCHEMA = """
        CREATE TABLE IF NOT EXISTS solana_swaps (
        signature              VARCHAR PRIMARY KEY,
        block_date             DATE,
        block_time             BIGINT,
        fee_payer              VARCHAR,
        token_sold_mint        VARCHAR,
        token_sold_symbol      VARCHAR,
        token_bought_amount    VARCHAR,
        program_source         VARCHAR,
        fee_lamports           BIGINT,
        fee_sol                DOUBLE,
        success                BOOLEAN,
        ingested_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

def get_connection(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Get or create DuckDB connection. Initialises schema on first use."""
    conn = duckdb.connect(db_path)
    conn.execute(SCHEMA)
    return conn

def get_last_processed_date(conn: duckdb.DuckDBpyConnection) -> Optional[str]:
    """
    Get the most recent block_date already in the warehouse.
    Used for incremental loading -- only extract data we don't have.
    """
    result = conn.execute(
        "SELECT MAX(block_date) FROM solana_swaps"
    ).fetchone()[0]
    return str(result) if result else None

def load_swaps(
    df: pd.DataFrame,
    conn: duckdb.DuckDBPyConnection
) -> dict:
    """Load a DataFrame of swaps into the DuckDB warehouse.
    Uses INSERT OR IGNORE to handle duplicates gracefully.

    Returns:
    dict with rows_attempted, rows_inserted, rows_skipped
    """
    rows_before = conn.execute("SELECT COUNT(*) FROM solana_swaps").fetchone()[0]

# DuckDB can read DataFrames Directly - No intermediate CSV needed
    conn.execute("""
    INSERT OR IGNORE INTO solana_swaps
    SELECT
    signature,
    CAST(block_date AS Date),
    block_time,
    fee_payer,
    token_sold_mint,
    token_sold_amount,
    token_bought_mint,
    token_bought_amount,
    program_source,
    fee_lamports,
    fee_sol,
    success
    CURRENT_TIMESTAMP
    FROM df
       """
    )

    rows_after = conn.execute("SELECT COUNT(*) FROM solana_swaps").fetchone()[0] 

    rows_inserted = rows_after - rows_before 
    rows_skipped = len(df) - rows_inserted

    logger.info(
        f"Load complete: {rows_inserted} inserted,"
        f"{rows_skipped} skipped (duplicates),"
        f"{rows_after} total in wareshouse"
    )

    return {
        "rows_attempted": len(df),
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_skipped,
        "total_in_db": rows_after
    }

def run_sanity_checks(conn: duckdb.DuckDBPyConnection) -> None:
    """Run post-load validation queries. Log warnings for anomalies."""

    # Check 1: Any NULL signatures?
    null_sigs = conn.execute("SELECT COUNT(*) FROM solana_swaps WHERE signature IS NULL").fetchone()[0]
    if null_sigs > 0:
        logger.warning(f"DATA QUALITY: {null_sigs} rows with NULL signatures")

    #Check 2: Any impossible amounts?
    bad_amounts = conn.execute("""SELECT COUNT(*) FROM solana_swaps WHERE token_sold_amount <= 0 OR token_sold_amount > 1e12""").fetchone()[0]
    if bad_amounts > 0:
        logger.warning(f"DATA QUALITY: {bad_amounts} rows with suspicious amounts")

    #Check 3: Data distribution looks sensible?
    date_check = conn.execute("""SELECT MIN(block_date), MAX(block_date), COUNT(DISTINCT block_date) FROM solana_swaps""").fetchone()
    logger.info(f"Date range: {date_check[0]} to {date_check[1]} ({date_check[2]}days)")

    #Check 4: Top programs (should be recognisable DEX names)
    top_programs = conn.execute("""SELECT program_source, COUNT(*) as cnt FROM solana_swaps GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").df()
    logger.info(f"Top programs:\n{top_programs.to_string()}")