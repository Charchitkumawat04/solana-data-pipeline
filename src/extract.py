"""
Extract: walk a DEX program's recent transactions and yield parsed swaps.

    for swap in extract_swaps("jupiter", max_txs=300):
        ...

Pagination uses the `before` cursor on getSignaturesForAddress, so this can walk
arbitrarily far back. Each signature then costs one getTransaction call - on the
public RPC that is the slow part (~4 tx/s), which is why `max_txs` exists.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterator

from .parse import Swap, parse_swap
from .rpc import SolanaRPC

logger = logging.getLogger(__name__)

# Program address we page through. Jupiter is the best default: the fee payer
# of a Jupiter transaction is almost always the end user, whereas pool programs
# see a lot of bot and aggregator traffic.
PROGRAMS: dict[str, str] = {
    "jupiter": "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
    "raydium": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "orca": "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "meteora": "LBUZKhRxPF3XUpBCjp4YzTKgLLjTriggingsZx5by39Mj",
}


def extract_swaps(
    program: str,
    max_txs: int = 300,
    since: datetime | None = None,
    skip_signatures: set[str] | None = None,
    rpc: SolanaRPC | None = None,
    page_size: int = 100,
) -> Iterator[Swap]:
    """
    Yield swaps for `program`, most recent first.

    Args:
        program:          key of PROGRAMS or a raw program address
        max_txs:          stop after inspecting this many transactions
        since:            stop once transactions are older than this (UTC)
        skip_signatures:  signatures already in the warehouse (incremental load)
        rpc:              client to use (default: SolanaRPC from env)
    """
    address = PROGRAMS.get(program.lower(), program)
    rpc = rpc or SolanaRPC()
    skip = skip_signatures or set()
    since_ts = int(since.replace(tzinfo=timezone.utc).timestamp()) if since else None

    before: str | None = None
    inspected = parsed = skipped = 0

    logger.info("extracting %s (%s…) max_txs=%d since=%s", program, address[:8], max_txs, since)

    while inspected < max_txs:
        page = rpc.get_signatures_for_address(address, limit=page_size, before=before)
        if not page:
            break

        for entry in page:
            if inspected >= max_txs:
                break
            sig = entry["signature"]
            before = sig
            inspected += 1

            if entry.get("err") is not None:
                continue                       # failed on-chain, no swap to record
            if since_ts and entry.get("blockTime") and entry["blockTime"] < since_ts:
                logger.info("reached since=%s, stopping", since)
                return
            if sig in skip:
                skipped += 1
                continue

            tx = rpc.get_transaction(sig)
            swap = parse_swap(tx) if tx else None
            if swap:
                parsed += 1
                yield swap

            if inspected % 50 == 0:
                logger.info("inspected=%d parsed=%d skipped=%d", inspected, parsed, skipped)

        if len(page) < page_size:
            break                              # no more history

    logger.info("done: inspected=%d parsed=%d skipped=%d", inspected, parsed, skipped)
