"""
Run the full pipeline: Solana RPC -> parsed swaps -> DuckDB.

    python -m src.pipeline                          # 300 recent Jupiter swaps, incremental
    python -m src.pipeline --program raydium --max-txs 500
    python -m src.pipeline --fresh                  # drop the table first (replace fake data)
    python -m src.pipeline --since 2026-10-10       # stop at this date

Then in ../dbt/dbt_solana_models:  dbt build
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from dotenv import load_dotenv

from .extract import PROGRAMS, extract_swaps
from .load import connect, db_path, existing_signatures, load_swaps, reset_table, summary

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


def run(program: str, max_txs: int, since: datetime | None, fresh: bool) -> dict:
    t0 = time.time()
    conn = connect()
    logger.info("warehouse: %s", db_path())

    if fresh:
        reset_table(conn)
    known = existing_signatures(conn)
    logger.info("%d signatures already in warehouse", len(known))

    rows = [s.to_row() for s in extract_swaps(program, max_txs=max_txs, since=since, skip_signatures=known)]
    stats = load_swaps(conn, rows)

    print("\n== warehouse by program ==")
    print(summary(conn).to_string(index=False))
    conn.close()

    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Solana DEX swaps -> DuckDB")
    ap.add_argument("--program", default="jupiter", help=f"one of {list(PROGRAMS)} or a program address")
    ap.add_argument("--max-txs", type=int, default=300, help="transactions to inspect (public RPC ~4/s)")
    ap.add_argument("--since", type=lambda s: datetime.fromisoformat(s), default=None, help="YYYY-MM-DD, stop at older txs")
    ap.add_argument("--fresh", action="store_true", help="drop solana_swaps first")
    args = ap.parse_args()

    stats = run(args.program, args.max_txs, args.since, args.fresh)
    print("\n== run ==")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
