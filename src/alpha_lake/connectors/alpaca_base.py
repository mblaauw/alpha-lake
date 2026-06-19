from __future__ import annotations

import os

import httpx
from alpha_lake.config import SourceConfig


def alpaca_client() -> httpx.AsyncClient:
    api_key = os.environ.get("APCA_API_KEY_ID", "")
    secret_key = os.environ.get("APCA_API_SECRET_KEY", "")
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
    }
    return httpx.AsyncClient(base_url="https://data.alpaca.markets", headers=headers, timeout=30.0)
