from __future__ import annotations

from alpha_lake.config import DatasetPostureConfig, SourceConfig, SourceDatasetConfig, get_config


def get_source(source_id: str) -> SourceConfig:
    cfg = get_config()
    found = cfg.sources.get(source_id)
    if found is None:
        raise KeyError(f"Source '{source_id}' not configured")
    return found


def get_dataset_sources(dataset: str) -> dict[str, SourceDatasetConfig]:
    cfg = get_config()
    result: dict[str, SourceDatasetConfig] = {}
    for source_id, datasets in cfg.source_datasets.items():
        if dataset in datasets:
            dc = datasets[dataset]
            if dc.enabled:
                result[source_id] = dc
    return result


def get_dataset_posture(dataset: str) -> DatasetPostureConfig:
    cfg = get_config()
    return cfg.datasets.get(dataset, DatasetPostureConfig())


def is_experimental_dataset(dataset: str) -> bool:
    return get_dataset_posture(dataset).tier == "experimental"


def get_primary_source(dataset: str) -> str | None:
    precedence = get_source_precedence(dataset)
    try:
        cfg = get_config()
        for source_id in precedence:
            ds_configs = cfg.source_datasets.get(source_id, {})
            dc = ds_configs.get(dataset)
            if dc is not None and dc.enabled:
                return source_id
        available = get_dataset_sources(dataset)
        if available:
            return next(iter(available))
        return None
    except AssertionError:
        return precedence[0] if precedence else None


def get_source_precedence(dataset: str) -> list[str]:
    try:
        cfg = get_config()
        return cfg.precedence.get(dataset, [])
    except AssertionError:
        return []
