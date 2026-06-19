# ADR-0016: Kubernetes is future target, not v0.1 development substrate

**Status:** Proposed

**Context:** Kubernetes adds significant complexity for a v0.1 project. The primary development and deployment target should be simpler.

**Decision:** Docker Compose is the v0.1 development and deployment substrate. Kubernetes manifests are maintained for future migration but are not the default path. RustFS clustering is deferred until GA.

**Consequences:**
- Positive: Simpler development and debugging
- Positive: Lower barrier to entry for contributors
- Negative: Migration to K8s will require adaptation
- Negative: RustFS single-node may hit scale limits

**References:**
- DESIGN.md §23, §28 Phase 8

**Date:** 2026-06-18
