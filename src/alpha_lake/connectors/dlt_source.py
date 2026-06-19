from __future__ import annotations

from typing import Any

import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.paginators import PageNumberPaginator


@dlt.source
def market_data_source(
    base_url: str,
    api_key: str | None = None,
    pagination: bool = True,
    page_size: int = 100,
):
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    client_kwargs: dict[str, Any] = {
        "base_url": base_url,
        "headers": headers,
    }

    if pagination:
        client_kwargs["paginator"] = PageNumberPaginator(
            base_page=1,
            total_path=None,
            page_size=page_size,
        )

    client = RESTClient(**client_kwargs)
    return client
