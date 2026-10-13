"""
Thin Solana JSON-RPC client with retry, backoff and rate-limit handling.

Works against any Solana RPC endpoint. The public endpoint
(https://api.mainnet-beta.solana.com) needs no API key but is rate-limited,
so requests are spaced out and 429s are retried with exponential backoff.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"


class SolanaRPC:
    def __init__(
        self,
        url: str | None = None,
        min_interval: float = 0.25,
        max_retries: int = 5,
        timeout: int = 30,
    ) -> None:
        self.url = url or os.getenv("SOLANA_RPC_URL") or DEFAULT_RPC_URL
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = requests.Session()
        self._last_call = 0.0
        self._id = 0

    # ------------------------------------------------------------------ core

    def call(self, method: str, params: list[Any]) -> Any:
        """Make one JSON-RPC call. Retries on 429 / 5xx / network errors."""
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}

        for attempt in range(self.max_retries):
            self._throttle()
            try:
                resp = self._session.post(self.url, json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("429 rate limited on %s, sleeping %ss", method, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                body = resp.json()
                if "error" in body:
                    # RPC-level error (bad params, node behind, etc.) - not retryable
                    raise RuntimeError(f"RPC error on {method}: {body['error']}")
                return body.get("result")
            except (requests.ConnectionError, requests.Timeout) as exc:
                wait = 2 ** attempt
                logger.warning("%s on %s (attempt %d), retry in %ss", type(exc).__name__, method, attempt + 1, wait)
                time.sleep(wait)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code >= 500:
                    wait = 2 ** attempt
                    logger.warning("HTTP %s on %s, retry in %ss", exc.response.status_code, method, wait)
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError(f"{method} failed after {self.max_retries} attempts")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    # --------------------------------------------------------------- helpers

    def get_signatures_for_address(
        self, address: str, limit: int = 100, before: str | None = None
    ) -> list[dict]:
        """Most-recent-first list of {signature, blockTime, err, slot} for an address."""
        opts: dict[str, Any] = {"limit": min(limit, 1000)}
        if before:
            opts["before"] = before
        return self.call("getSignaturesForAddress", [address, opts]) or []

    def get_transaction(self, signature: str) -> dict | None:
        """Full transaction with parsed instructions and pre/post balances."""
        return self.call(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}],
        )

    def get_slot(self) -> int:
        return int(self.call("getSlot", []))
