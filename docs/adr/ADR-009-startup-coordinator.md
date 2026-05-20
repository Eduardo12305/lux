## ADR-009: StartupCoordinator with Health Checks

**Status:** Accepted

**Context:** Lux has multiple subsystems (database, model loader, voice pipeline, gateway, plugins, cron scheduler) that must start in a specific order and each may take variable time to become ready. Starting them in the wrong order causes cryptic failures. We need a coordinator that orchestrates startup with health checks and graceful degradation.

**Decision:** Implement `StartupCoordinator` that manages subsystem initialization as a directed acyclic graph (DAG). Each subsystem declares its dependencies. The coordinator starts subsystems in topological order, concurrently where dependencies allow. Each subsystem exposes an async `health_check()` method. The coordinator polls health checks until all are green or a timeout is reached, then signals readiness.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| DAG-based coordinator with health checks | Correct ordering, parallelism, observable | Implementation complexity |
| Sequential hardcoded startup | Simple | Fragile, slow, no parallelism |
| Docker Compose / process supervisor | Battle-tested, external | Separate process, doesn't integrate with Python config |
| Event-driven startup (signals) | Decoupled | Hard to debug ordering, easy to miss dependencies |

**Consequences:** Adding a new subsystem only requires declaring its dependencies and implementing `health_check()`. The DAG is validated at startup — circular dependencies are rejected with a clear error. Components that fail health checks are marked degraded, and Lux can start in a reduced-capability mode if configured.

**Implementation:** `lux/core/startup.py`
