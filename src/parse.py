"""
Turn a raw Solana transaction (jsonParsed encoding) into one swap record.

How a swap is detected
----------------------
A DEX swap is, from the trader's point of view, "one token balance went down,
another went up, in the same transaction". So instead of decoding every DEX
program's instruction layout, we read the balance changes the validator already
recorded for us:

    meta.preTokenBalances / meta.postTokenBalances  -> SPL token deltas
    meta.preBalances[0]  / meta.postBalances[0]     -> native SOL delta (fee payer)

The most-negative delta is the token sold, the most-positive is the token bought.
Routing hops (USDC -> SOL -> JUP) are invisible at this level, which is exactly
what we want for analytics: we record what the USER gave and got, not what the
router did in between.

Output schema matches the `solana_swaps` source table in dbt-solana-models.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

LAMPORTS_PER_SOL = 1_000_000_000
WSOL_MINT = "So11111111111111111111111111111111111111112"

# Mint address -> symbol. Symbols must match seeds/token_prices.csv in the dbt
# project for USD pricing to work (sol, usdc, bonk, jup, wif). Others are kept
# for readability but will be unpriced.
KNOWN_MINTS: dict[str, str] = {
    WSOL_MINT: "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So": "mSOL",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "ETH",
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "WBTC",
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
    "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL": "JTO",
    "MEW1gQWJ3nEXg2qgERiKu7FAFj79PHvQVREQUzScPP5": "MEW",
    "6p6xgHyF7AeE6TZkSmFsko444wqoP15icUSqi2jfGiPN": "TRUMP",
}

# Program ID -> project name. Names MUST be one of the values accepted by the
# dbt test on stg_solana_swaps.project: raydium / orca / meteora / jupiter / unknown.
DEX_PROGRAMS: dict[str, str] = {
    # Jupiter aggregator (v6, v4)
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
    "JUP4Fb2cqiRUcaTHdrPC8h2gNsA2ETXiPDD33WcGuJB": "Jupiter",
    # Raydium (AMM v4, CLMM, CPMM)
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium",
    # Orca Whirlpools
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca",
    # Meteora (DLMM, pools)
    "LBUZKhRxPF3XUpBCjp4YzTKgLLjTriggingsZx5by39Mj": "Meteora",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora",
}

# Ignore SOL moves smaller than this: rent for temporary accounts, tips, dust.
SOL_DUST_THRESHOLD = 0.001


@dataclass
class Swap:
    signature: str
    block_date: str          # YYYY-MM-DD (UTC)
    block_time: str          # ISO timestamp (UTC)
    fee_payer: str
    token_sold_symbol: str
    token_bought_symbol: str
    token_sold_amount: float
    token_bought_amount: float
    program_source: str
    fee_lamports: int
    fee_sol: float
    success: bool

    def to_row(self) -> dict[str, Any]:
        return asdict(self)


def symbol_for(mint: str) -> str:
    return KNOWN_MINTS.get(mint, f"{mint[:4]}..{mint[-4:]}")


def _ui_amount(bal: dict) -> float:
    ui = bal.get("uiTokenAmount", {})
    if ui.get("uiAmount") is not None:
        return float(ui["uiAmount"])
    try:
        return int(ui.get("amount", 0)) / (10 ** int(ui.get("decimals", 0)))
    except (TypeError, ValueError):
        return 0.0


def _program_source(tx: dict, meta: dict) -> str:
    """Which DEX executed the swap. Checks top-level instructions, then inner."""
    def scan(instructions: list[dict]) -> str | None:
        for ix in instructions:
            name = DEX_PROGRAMS.get(ix.get("programId", ""))
            if name:
                return name
        return None

    top = tx.get("transaction", {}).get("message", {}).get("instructions", [])
    found = scan(top)
    if found:
        return found
    for group in meta.get("innerInstructions", []) or []:
        found = scan(group.get("instructions", []))
        if found:
            return found
    return "unknown"


def parse_swap(tx: dict) -> Swap | None:
    """
    Convert one getTransaction(jsonParsed) result into a Swap, or None when the
    transaction is not a swap from the fee payer's perspective.
    """
    if not tx or not tx.get("meta"):
        return None

    meta = tx["meta"]
    message = tx.get("transaction", {}).get("message", {})
    account_keys = message.get("accountKeys", [])
    if not account_keys:
        return None

    fee_payer = account_keys[0].get("pubkey") if isinstance(account_keys[0], dict) else account_keys[0]
    signature = (tx.get("transaction", {}).get("signatures") or [None])[0]
    if not signature:
        return None

    success = meta.get("err") is None
    fee_lamports = int(meta.get("fee", 0))

    # ---- token deltas for the fee payer -----------------------------------
    deltas: dict[str, float] = {}

    for bal in meta.get("preTokenBalances") or []:
        if bal.get("owner") == fee_payer:
            deltas[bal["mint"]] = deltas.get(bal["mint"], 0.0) - _ui_amount(bal)
    for bal in meta.get("postTokenBalances") or []:
        if bal.get("owner") == fee_payer:
            deltas[bal["mint"]] = deltas.get(bal["mint"], 0.0) + _ui_amount(bal)

    # ---- native SOL delta (account index 0 is always the fee payer) --------
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    if pre and post:
        sol_delta = (post[0] - pre[0] + fee_lamports) / LAMPORTS_PER_SOL
        if abs(sol_delta) >= SOL_DUST_THRESHOLD:
            deltas[WSOL_MINT] = deltas.get(WSOL_MINT, 0.0) + sol_delta

    # drop dust so a swap isn't mis-identified by a tiny rounding residual
    deltas = {m: d for m, d in deltas.items() if abs(d) > 1e-9}
    if len(deltas) < 2:
        return None

    sold_mint, sold_delta = min(deltas.items(), key=lambda kv: kv[1])
    bought_mint, bought_delta = max(deltas.items(), key=lambda kv: kv[1])
    if sold_delta >= 0 or bought_delta <= 0 or sold_mint == bought_mint:
        return None

    block_time = tx.get("blockTime")
    if block_time is None:
        return None
    ts = datetime.fromtimestamp(int(block_time), tz=timezone.utc)

    return Swap(
        signature=signature,
        block_date=ts.strftime("%Y-%m-%d"),
        block_time=ts.strftime("%Y-%m-%d %H:%M:%S"),
        fee_payer=fee_payer,
        token_sold_symbol=symbol_for(sold_mint),
        token_bought_symbol=symbol_for(bought_mint),
        token_sold_amount=abs(sold_delta),
        token_bought_amount=bought_delta,
        program_source=_program_source(tx, meta),
        fee_lamports=fee_lamports,
        fee_sol=fee_lamports / LAMPORTS_PER_SOL,
        success=success,
    )
