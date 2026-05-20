## ADR-006: Semaphore+Queue+CircuitBreaker for Rate Limiting

**Status:** Accepted

**Context:** Lux interacts with external APIs (LLM providers, search services, web endpoints) that impose rate limits. Exceeding these limits results in 429 responses, wasted retries, and potential temporary bans. We need a client-side rate limiting strategy that prevents overuse while maximizing throughput under varying load.

**Decision:** Implement a composite rate limiter combining three patterns: (1) `asyncio.Semaphore` to cap concurrent in-flight requests, (2) an `asyncio.Queue`-based token bucket for per-second/per-minute rate enforcement, and (3) a `CircuitBreaker` that opens when error rates exceed a threshold, preventing cascading failures during outages.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| Semaphore + Queue + CircuitBreaker | Three complementary defenses, no external deps | More code to maintain, coordination between components |
| Semaphore only | Simplest | No rate-over-time enforcement, 429 storms possible |
| Token bucket library (aiolimiter) | Well-tested, feature-complete | External dependency with its own release cycle |
| Exponential backoff only | No proactive limiting | Reacts after failure, wastes attempts on doomed requests |
| Redis-based distributed limiter | Works across processes | Requires Redis, overkill for single-process Lux |

**Consequences:** The three components work together: the token bucket prevents sustained over-rate, the semaphore prevents burst overload, and the circuit breaker detects systemic failures. The circuit breaker state is exposed via metrics for observability. Recovery is automatic via half-open probing.

**Implementation:** `lux/utils/rate_limiter.py`
