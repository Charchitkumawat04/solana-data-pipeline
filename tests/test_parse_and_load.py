import copy
import json
from pathlib import Path

import duckdb
import pytest

from src.parse import parse_swap
from src.load import SCHEMA_SQL, load_swaps, existing_signatures

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "jupiter_usdc_to_sol.json"


@pytest.fixture
def tx():
    return json.loads(FIXTURE.read_text())


def test_parses_user_side_of_routed_swap(tx):
    """USDC -> (Raydium hop) -> SOL via Jupiter. We must record USDC->SOL, once."""
    swap = parse_swap(tx)
    assert swap is not None
    assert swap.signature.startswith("5VERv8")
    assert swap.fee_payer == "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
    assert swap.token_sold_symbol == "USDC"
    assert swap.token_sold_amount == pytest.approx(250.0)
    assert swap.token_bought_symbol == "SOL"
    # post - pre + fee = 6484985000 - 5000000000 + 15000 = 1.485 SOL
    assert swap.token_bought_amount == pytest.approx(1.485)
    assert swap.program_source == "Jupiter"        # top-level program wins over inner hop
    assert swap.fee_lamports == 15000
    assert swap.fee_sol == pytest.approx(0.000015)
    assert swap.success is True
    assert swap.block_date == "2026-10-12"


def test_failed_tx_is_flagged_not_dropped(tx):
    tx["meta"]["err"] = {"InstructionError": [0, "Custom"]}
    swap = parse_swap(tx)
    assert swap is not None and swap.success is False   # staging layer filters it


def test_transfer_without_second_leg_is_not_a_swap(tx):
    tx["meta"]["postBalances"][0] = tx["meta"]["preBalances"][0] - tx["meta"]["fee"]  # SOL unchanged
    assert parse_swap(tx) is None


def test_inner_program_used_when_no_top_level_match(tx):
    tx["transaction"]["message"]["instructions"][0]["programId"] = "ComputeBudget111111111111111111111111111111"
    assert parse_swap(tx).program_source == "Raydium"


def test_unknown_mint_gets_readable_symbol(tx):
    tx["meta"]["preTokenBalances"][0]["mint"] = "Fake11111111111111111111111111111111111Mint"
    tx["meta"]["postTokenBalances"][0]["mint"] = "Fake11111111111111111111111111111111111Mint"
    assert parse_swap(tx).token_sold_symbol == "Fake..Mint"


def test_load_is_idempotent(tx):
    conn = duckdb.connect(":memory:")
    conn.execute(SCHEMA_SQL)
    row = parse_swap(tx).to_row()

    first = load_swaps(conn, [row, copy.deepcopy(row)])
    assert first["inserted"] == 1 and first["skipped"] == 0   # in-batch dedupe

    second = load_swaps(conn, [row])
    assert second["inserted"] == 0 and second["skipped"] == 1  # already in warehouse
    assert existing_signatures(conn) == {row["signature"]}

    cols = [c[0] for c in conn.execute("DESCRIBE solana_swaps").fetchall()]
    assert cols == list(row.keys())                            # schema matches dbt source
