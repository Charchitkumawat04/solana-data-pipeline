"""
Extract Solana DEX Swap data via Helius API.
"""

import os
import json
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta
from typing import Generator
from pathlib import Path
from dotenv import load_dotenv  

from .models import SolanaSwap, parse_helius_swap

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("HELIUS_API_KEY")
BASE_URL = "https://api-mainnet.helius-rpc.com/v0"

# Known DEX program IDs
PROGRAMS = {
    "RAYDIUM":  "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
    "ORCA":     "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
    "METEORA":  "LBUZKhRxPF3XUpBCjp4YzTKgLLjTriggingsZx5by39Mj",
    "JUPITER":  "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",
}

def fetch_program_transactions(
    program_id: str,
    before_sig: str = None,
    limit: int = 100
) -> list[dict]:
    """Fetch enhanced transactions for a program address."""
    url = f"{BASE_URL}/addresses/{program_id}/transactions"
    params = {
        "api-key": API_KEY,
        "type": "SWAP",
        "limit": limit
    }
    if before_sig:
        params["before"] = before_sig
    
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"Attempt {attempt+1} failed: {e}. Retry in {wait}s")
            time.sleep(wait)

    logger.error(f"All retries failed for {program_id[:8]}...")
    return []

def extract_swaps(
    program: str,
    start_date: datetime
) -> Generator[SolanaSwap, None, None]:
    """
    Extract and parse all swap for a program since start_date.
    """
    program_id = PROGRAMS.get(program.upper())
    if not program_id:
        raise ValueError(f"Unknown program: {program}. Options: {list(PROGRAMS.keys())}")

    before_sig = None
    total = 0
    
    while True:
        batch = fetch_program_transactions(program_id, before_sig)

        if not batch:
            break

        for raw_tx in batch:
            #Check date boundary
            tx_time = datetime.fromtimestamp(raw_tx.get("timestamp", 0))
            if tx_time < start_date:
                logger.info(f"Reached start date. Total extracted: {total}")
                return

            swap = parse_helius_swap(raw_tx)
            if swap:
                total += 1
                yield swap
            
        #paginate using last signature as cursor
        before_sig = batch[-1].get("signature")
        time.sleep(0.1) # rate limit respect

        if total % 500 == 0 and total > 0:
            logger.info(f"Progress: {total} swaps extracted...")
        
def main():
    parser = argparse.ArgumentParser(description="Extract Solana DEX swap")
    parser.add_argument("--program", default="RAYDIUM", help="DEX program name")
    parser.add_argument("--days", type=int, default=1, help="Days to look back")
    args = parser.parse_args()

    start_date = datetime.now() - timedelta(days=args.days)
    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    swaps = []
    for swap in extract_swaps(args.program, start_date):
        swaps.append(swap.__dict__)

    output_file = output_dir / f"{args.program.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, "w") as f:
        json.dump(swaps, f, indent=2)

    logger.info(f"Done. {len(swaps)} swaps saved to {output_file}")

if __name__ == "__main__":
    main()