# solana-data-pipeline

Ingests Solana DEX swaps straight from the chain into a local DuckDB warehouse.
This is the **E** and **L** that feeds [`dbt-solana-models`](../dbt/dbt_solana_models) (the **T**).

```
Solana JSON-RPC ──► src/rpc.py ──► src/parse.py ──► src/load.py ──► solana_warehouse.duckdb ──► dbt build
 (any endpoint)     retry/backoff   balance deltas    anti-join insert   solana_swaps table       7 models, 31 tests
```

No API key required: it runs against the public `api.mainnet-beta.solana.com` endpoint.
Point `SOLANA_RPC_URL` at Helius / Tatum / QuickNode for ~20x throughput.

## How swaps are detected

Rather than decoding each DEX's instruction layout, the parser reads the balance changes the
validator already computed: `meta.preTokenBalances` / `postTokenBalances` for the fee payer,
plus the native SOL delta. Most-negative delta = token sold, most-positive = token bought.

This deliberately ignores routing hops. A Jupiter trade USDC → SOL → BONK is recorded once, as
USDC → BONK, because that is what the user gave and got. Reading inner swaps instead would
double-count volume and invent pairs the user never traded.

The DEX name comes from the program IDs in the transaction (top-level first, then inner), mapped
to the five values the dbt tests accept: `Jupiter`, `Raydium`, `Orca`, `Meteora`, `unknown`.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                   # defaults work as-is

python -m pytest                       # 6 tests, no network needed

python -m src.pipeline --fresh         # 300 recent Jupiter swaps -> DuckDB (~2 min on public RPC)
python -m src.pipeline                 # run again: incremental, only new signatures

cd ../dbt/dbt_solana_models && dbt build   # models + tests over real data
```

Options:

```
--program  jupiter | raydium | orca | meteora | <any program address>   (default: jupiter)
--max-txs  transactions to inspect, newest first                        (default: 300)
--since    YYYY-MM-DD, stop when transactions get older than this
--fresh    drop solana_swaps before loading (replaces fake/seed data)
```

## Output schema (`solana_swaps`)

| column | type | source |
|---|---|---|
| signature | VARCHAR | `transaction.signatures[0]` |
| block_date, block_time | DATE, TIMESTAMP | `blockTime` (UTC) |
| fee_payer | VARCHAR | `accountKeys[0]` |
| token_sold_symbol, token_bought_symbol | VARCHAR | mint → symbol map (`src/parse.py`) |
| token_sold_amount, token_bought_amount | DOUBLE | token / SOL balance deltas |
| program_source | VARCHAR | DEX program ID match |
| fee_lamports, fee_sol | INTEGER, DOUBLE | `meta.fee` |
| success | BOOLEAN | `meta.err IS NULL` |

Failed transactions are loaded with `success = false` and filtered in the dbt staging layer,
so the raw table stays a faithful record of what was observed.

## Production patterns in here

- **Retry with exponential backoff** on 429 / 5xx / network errors (`src/rpc.py`)
- **Client-side throttling** so the public RPC doesn't ban you
- **Cursor pagination** via `before=<signature>`, walks arbitrarily far back
- **Incremental loads**: signatures already in the warehouse are skipped before the expensive `getTransaction` call
- **Idempotent writes**: anti-join insert, safe to re-run
- **Schema contract** with the downstream dbt project, enforced by a test

## Known limits (honest list)

- Public RPC ≈ 4 tx/s. 300 swaps takes ~2 minutes. Use a keyed RPC for backfills.
- Symbols for unlisted mints render as `AbCd..WxYz`; USD pricing in dbt covers SOL/USDC/BONK/JUP/WIF only.
- A transaction where the fee payer is a bot wallet or a program (not an end user) is still recorded as that wallet's swap — which is correct, just worth knowing when reading trader counts.

## Repo layout

```
src/rpc.py        JSON-RPC client
src/parse.py      transaction -> Swap
src/extract.py    pagination + filtering, yields Swaps
src/load.py       DuckDB schema + idempotent insert
src/pipeline.py   CLI entrypoint
tests/            parse + load tests against fixtures/
queries/          example analytics SQL over the warehouse
```
