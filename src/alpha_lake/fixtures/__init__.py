"""Test fixture freezing for golden replay.

Freeze raw payloads, manifests, canonical rows, and available_at values
for deterministic replay testing. Intended for the `just freeze-fixtures` recipe.
"""


def freeze() -> None:
    """Freeze current test fixtures for golden replay."""
    print("Freezing fixtures — not yet implemented.")
