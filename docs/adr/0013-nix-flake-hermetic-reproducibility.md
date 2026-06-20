# ADR-0013: Nix flake as hermetic reproducibility ceiling

**Status:** Superseded — Superseded by OCI image + uv.lock + vendored wheelhouse per ADR-0012. The OCI image is the deploy and reproducibility unit in cloud-native tiers. `flake.nix` remains as a development convenience but is not the reproducibility guarantee.

**Implementation:** `flake.nix` at repo root with Python 3.14, uv, docker-compose in a devShell.

**Context:** Compose + uv provides practical reproducibility. A Nix flake provides the maximal hermetic ceiling, pinning every tool at the OS level.

**Decision:** Provide `flake.nix` as the hermetic reproducibility ceiling alongside the pragmatic Compose + uv defaults. Not required for daily development. The flake pins the chosen development interpreter while the package metadata keeps the runtime floor at Python >=3.12 for wheel availability.

**Consequences:**
- Positive: Maximal reproducibility for CI and deployment
- Positive: Catches tooling version drift
- Negative: Additional maintenance burden
- Negative: Nix learning curve for contributors

**References:**
- DESIGN.md §23, §29

**Date:** 2026-06-18
