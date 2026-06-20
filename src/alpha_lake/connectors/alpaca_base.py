from __future__ import annotations

import httpx

from alpha_lake.secrets import get_store


def alpaca_client() -> httpx.AsyncClient:
    store = get_store()
    api_key = store.get("alpaca_api_key_id")
    secret_key = store.get("alpaca_api_secret_key")
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    return httpx.AsyncClient(base_url="https://data.alpaca.markets", headers=headers, timeout=30.0)
