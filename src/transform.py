"""
transform.py
Transforms raw Helius swap data into clean analytical records.
"""

import json
import pandas as pd
from typing import List, Dict
from pathlib import Path


# Solana token mint addresses → human readable symbols
KNOWN_TOKENS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "So11111111111111111111111111111111111111112": "SOL",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
}


def resolve_token_symbol(mint: str) -> str:
    """Convert mint address to token symbol."""
    return KNOWN_TOKENS.get(mint, mint[:8] + "...")  # truncate unknown mints


def clean_amount(raw_amount: str, decimals: int = 6) -> float:
    """Convert raw token amount to human-readable float."""
    try:
        return float(raw_amount) / (10 ** decimals)
    except (ValueError, TypeError):
        return 0.0


def transform_swaps(raw_path: str) -> pd.DataFrame:
    """
    Transform raw swap JSON into clean analytical DataFrame.

    Solana-specific transformations:
    - Mint addresses → token symbols
    - Lamports → SOL (divide by 1e9)
    - Unix timestamps → datetime
    - Raw token amounts → human-readable (divide by decimals)
    """
    with open(raw_path) as f:
        raw_swaps = json.load(f)

    cleaned = []
    for swap in raw_swaps:
        if not swap:
            continue

        cleaned.append({
            "tx_id": swap.get("tx_id"),
            "block_date": swap.get("block_date"),
            "trader": swap.get("trader"),
            "project": swap.get("project", "").lower(),
            "token_sold": resolve_token_symbol(swap.get("token_sold_mint", "")),
            "token_bought": resolve_token_symbol(swap.get("token_bought_mint", "")),
            "amount_sold": clean_amount(swap.get("token_sold_amount", 0)),
            "amount_bought": clean_amount(swap.get("token_bought_amount", 0)),
            "fee_sol": swap.get("fee_sol", 0),
            "success": swap.get("success", False),
        })

    df = pd.DataFrame(cleaned)

    # Remove failed transactions
    df = df[df["success"] == True]

    # Remove dust trades (< $0.01)
    # Note: without price data we can't filter by USD — that's added in DBT

    print(f"Transformed {len(df)} valid swaps from {len(raw_swaps)} raw records")
    return df


if __name__ == "__main__":
    df = transform_swaps("data/raw_swaps.json")
    df.to_parquet("data/clean_swaps.parquet", index=False)  # parquet > CSV for large data
    print(df.head())
    print(df.dtypes)