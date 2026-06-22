from __future__ import annotations

from fastapi import APIRouter, HTTPException  # type: ignore[unresolved-import]

from alpha_lake.catalog import connect, dataset_health, list_datasets
from alpha_lake.config import get_config

router = APIRouter(prefix="/v1/dashboard")


def _check_enabled() -> None:
    if not get_config().transport.dashboard_enabled:
        raise HTTPException(404)


def _get_con():
    return connect(get_config())


@router.get("/datasets")
async def datasets():
    _check_enabled()
    con = _get_con()
    cfg = get_config()
    all_ds = list_datasets(con)
    result = []
    for ds in all_ds:
        name = str(ds["dataset"])
        hlth = dataset_health(con, name)
        posture = cfg.datasets.get(name)
        result.append(
            {
                "dataset": name,
                "tier": posture.tier if posture else "unknown",
                "supported": posture.supported if posture else False,
                "sla": posture.sla if posture else False,
                "rows": hlth.get("rows", 0),
                "latest_effective_date": str(hlth.get("latest_date", "")),
                "status": hlth.get("status", "unknown"),
                "schema_version": ds.get("schema_version", 0),
            }
        )
    con.close()
    return result


@router.get("/dataset/{name}")
async def dataset_detail(name: str, limit: int = 50):
    _check_enabled()
    con = _get_con()
    names = {d["dataset"] for d in list_datasets(con)}
    if name not in names:
        con.close()
        raise HTTPException(404, f"Dataset '{name}' not found")
    cap = min(limit, 500)
    query = f"SELECT * FROM {name} ORDER BY effective_date DESC NULLS LAST LIMIT {cap}"
    try:
        rows = con.execute(query).fetchall()
        cols = [c[0] for c in con.execute(f"DESCRIBE {name}").fetchall()]
        result = [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception:
        cols = []
        result = []
    con.close()
    from alpha_lake.clock import get_clock

    return {
        "dataset": name,
        "columns": cols,
        "rows": result,
        "fetched_at": get_clock().now().isoformat(),
    }
