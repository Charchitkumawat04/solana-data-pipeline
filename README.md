# solana-data-pipeline

End-to-end data pipeline for Solana DEX analytics.

## Architecture

[diagram: Solana RPC → Helius API → extract.py → transform.py → DuckDB → SQL]

Helius API → raw JSON → validated swaps → DuckDB warehouse → analytics queries

## What It Does
- Extracts swap transactions from Solana DEX programs via Helius enhanced API
- Parses and validates: token pairs, amounts, fees, program sources
- Loads incrementally into DuckDB (no re-processing of historical data)
- Supports Raydium, Orca, Meteora, Jupiter

## Setup
pip install -r requirements.txt
cp .env.example .env
# Add your Helius API key to .env

## Run
python -m src.pipeline --program RAYDIUM --days 1

## Example Output
[include a screenshot or sample output here]

## Tech Stack
Python · DuckDB · Helius API · Solana