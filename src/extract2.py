"""
extract.py
Extracts Solana DEX swap transactions via Helius Enhanced Transactions API.
Part of: solana-data-pipeline (GitHub Repo #1)
"""

import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Generator

# Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Config
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")  # never hardcode secrets
HELIUS_BASE_URL = "https://api.helius.xyz/v0"
BATCH_SIZE = 100
RATE_LIMIT_DELAY = 0.1  # seconds between requests


def fetch_transactions(
    address: str,
    before: Optional[str] = None
) -> List[Dict]:
    """
    Fetch parsed transactions for a Solana address.
    
    Args:
        address: Solana wallet or program address
        before: Transaction signature to paginate before
    
    Returns:
        List of parsed transaction dictionaries
    """
    url = f"{HELIUS_BASE_URL}/addresses/{address}/transactions"
    params = {
        "api-key": HELIUS_API_KEY,
        "type": "SWAP",
        "limit": BATCH_SIZE
    }
    if before:
        params["before"] = before
    
    for attempt in range(3):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            transactions = response.json()
            logger.info(f"Fetched {len(transactions)} transactions for {address[:8]}...")
            return transactions
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            logger.warning(f"Attempt {attempt+1} failed: {e}. Retrying in {wait}s")
            time.sleep(wait)
    
    logger.error(f"Failed to fetch transactions for {address}")
    return []


def parse_swap(raw_tx: Dict) -> Optional[Dict]:
    """
    Transform raw Helius transaction into clean swap record.
    
    Args:
        raw_tx: Raw transaction from Helius API
    
    Returns:
        Clean swap dictionary or None if invalid
    """
    try:
        # Extract swap event data
        swap_event = raw_tx.get("events", {}).get("swap", {})
        if not swap_event:
            return None
        
        # Build clean record
        record = {
            "tx_id": raw_tx.get("signature"),
            "block_time": raw_tx.get("timestamp"),
            "block_date": datetime.fromtimestamp(
                raw_tx.get("timestamp", 0)
            ).strftime("%Y-%m-%d"),
            "trader": raw_tx.get("feePayer"),
            "project": swap_event.get("programInfo", {}).get("source", "unknown"),
            "fee_sol": raw_tx.get("fee", 0) / 1e9,  # lamports to SOL
            "success": not raw_tx.get("transactionError"),
            "raw_data": json.dumps(raw_tx)  # keep raw for debugging
        }
        
        # Extract token amounts from transfers
        token_inputs = swap_event.get("tokenInputs", [])
        token_outputs = swap_event.get("tokenOutputs", [])
        
        if token_inputs:
            record["token_sold_mint"] = token_inputs[0].get("mint")
            record["token_sold_amount"] = token_inputs[0].get("rawTokenAmount", {}).get("tokenAmount", 0)
        
        if token_outputs:
            record["token_bought_mint"] = token_outputs[0].get("mint")
            record["token_bought_amount"] = token_outputs[0].get("rawTokenAmount", {}).get("tokenAmount", 0)
        
        return record
    
    except Exception as e:
        logger.warning(f"Failed to parse transaction: {e}")
        return None


def extract_program_swaps(
    program_id: str,
    start_date: datetime
) -> Generator[Dict, None, None]:
    """
    Extract all swaps for a program since start_date.
    Yields individual swap records for streaming processing.
    
    Args:
        program_id: Solana DEX program ID
        start_date: Only extract transactions after this date
    """
    before_sig = None
    total_processed = 0
    
    while True:
        batch = fetch_transactions(program_id, before=before_sig)
        
        if not batch:
            logger.info(f"No more transactions. Total processed: {total_processed}")
            break
        
        for raw_tx in batch:
            # Check if we've gone past our start date
            tx_time = datetime.fromtimestamp(raw_tx.get("timestamp", 0))
            if tx_time < start_date:
                logger.info(f"Reached start date {start_date}. Stopping.")
                return
            
            swap = parse_swap(raw_tx)
            if swap:
                total_processed += 1
                yield swap
        
        # Paginate: use last signature as cursor
        before_sig = batch[-1].get("signature")
        time.sleep(RATE_LIMIT_DELAY)  # respect rate limits


# Raydium AMM program ID (one of Solana's main DEXs)
RAYDIUM_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

import os

if __name__ == "__main__":
    start_date = datetime.now() - timedelta(days=1)
    
    logger.info("Starting Solana DEX extraction...")
    
    os.makedirs("data/raw", exist_ok=True)

    swaps = []
    
    with open("data/raw/raw_swaps.json", "w") as f:
        for swap in extract_program_swaps(RAYDIUM_PROGRAM_ID, start_date):
            swaps.append(swap)
            
            # Save every 50 swaps
            if len(swaps) % 50 == 0:
                json.dump(swaps, f, indent=2)
                f.flush()
                logger.info(f"Saved {len(swaps)} swaps so far...")
    
    logger.info(f"Extraction complete. Total swaps: {len(swaps)}")
    
    # Save to JSON for now (Note #23 loads this into DuckDB)
    with open("data/raw/raw_swaps.json", "w") as f:
        json.dump(swaps, f, indent=2)
    
    logger.info("Saved to data/raw_swaps.json")