"""Data models for Solana swap data."""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class SolanaSwap:
    """Represents a DEX swap transaction on Solana."""
    tx_signature: str
    timestamp: int
    program: str
    signer: str
    token_in_mint: str
    token_in_amount: float
    token_out_mint: str
    token_out_amount: float
    fee_amount: Optional[float] = None
    fee_mint: Optional[str] = None


def parse_helius_swap(raw_tx: dict) -> Optional[SolanaSwap]:
    """
    Parse a Helius API transaction response into a SolanaSwap object.
    
    Args:
        raw_tx: Raw transaction dict from Helius API
        
    Returns:
        SolanaSwap object if successfully parsed, None otherwise
    """
    try:
        # Extract basic transaction info
        signature = raw_tx.get("signature")
        timestamp = raw_tx.get("timestamp", 0)
        
        # Try to parse token transfers from the transaction
        token_transfers = raw_tx.get("tokenTransfers", [])
        if not token_transfers or len(token_transfers) < 2:
            return None
        
        # Identify incoming and outgoing tokens
        # Typically: first transfer is token out, second is token in
        incoming = None
        outgoing = None
        
        for transfer in token_transfers:
            if transfer.get("toUserAccount"):  # Token received
                if not incoming:
                    incoming = transfer
            elif transfer.get("fromUserAccount"):  # Token sent
                if not outgoing:
                    outgoing = transfer
        
        if not incoming or not outgoing:
            return None
        
        # Extract signer (wallet that initiated the swap)
        signer = raw_tx.get("signer") or raw_tx.get("feePayer", "unknown")
        
        # Parse fee information
        fee_amount = None
        fee_mint = "SOL"  # Native SOL fees by default
        if "fee" in raw_tx:
            fee_amount = raw_tx["fee"] / 1_000_000_000  # Convert lamports to SOL
        
        return SolanaSwap(
            tx_signature=signature,
            timestamp=timestamp,
            program=raw_tx.get("type", "UNKNOWN"),
            signer=signer,
            token_in_mint=incoming.get("mint", ""),
            token_in_amount=float(incoming.get("tokenAmount", 0)),
            token_out_mint=outgoing.get("mint", ""),
            token_out_amount=float(outgoing.get("tokenAmount", 0)),
            fee_amount=fee_amount,
            fee_mint=fee_mint,
        )
        
    except (KeyError, ValueError, TypeError) as e:
        return None
