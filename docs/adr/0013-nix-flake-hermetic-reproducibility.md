# ADR-0013: Nix flake as hermetic reproducibility ceiling

**Status:** Proposed

**Context:** Compose + uv provides practical reproducibility. A Nix flake provides the maximal hermetic ceiling, pinning every tool at the OS level.

**Decision:** Provide `flake.nix` as the hermetic reproducibility ceiling alongside the pragmatic Compose + uv defaults. Not required for daily development.

**Consequences:**
- Positive: Maximal reproducibility for CI and deployment
- Positive: Catches tooling version drift
- Negative: Additional maintenance burden
- Negative: Nix learning curve for contributors

**References:**
- DESIGN.md §23

**Date:** 2026-06-18
