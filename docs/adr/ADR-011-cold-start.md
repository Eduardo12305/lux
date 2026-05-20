## ADR-011: ProcessLauncher for Cold Start

**Status:** Accepted

**Context:** Lux runs as a long-lived service, but certain operations (model loading, external process invocation, voice pipeline initialization) are memory-intensive and may cause OOM if all launched eagerly at startup. We need a mechanism to lazily launch these heavy processes on first use without blocking the main event loop.

**Decision:** Implement `ProcessLauncher` that subprocesses heavy workloads on demand. Each launcher entry defines the command, environment, startup timeout, and health check endpoint. The launcher manages process lifecycle (start, monitor, graceful shutdown) using `asyncio.create_subprocess_exec`. Process state is tracked, and callers await readiness before sending work.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| ProcessLauncher with subprocess | True process isolation, lazy startup, crash recovery | IPC overhead, subprocess management complexity |
| Load-everything-at-startup | Simplest calling code | Huge memory footprint, slow initial startup |
| Thread-pool workers | Lighter than subprocess, shared memory | No isolation, GIL contention, crash takes down main process |
| Docker/podman containers | Maximum isolation | Requires container runtime, heavyweight, complex networking |

**Consequences:** Heavy components start only when needed and can be restarted independently if they crash. The health-check pattern (same as ADR-009) is reused here. Process exit is monitored, and unexpected exits trigger configurable restart policies. Memory is reclaimed on process termination, unlike in-process alternatives.

**Implementation:** `lux/core/process_launcher.py`
