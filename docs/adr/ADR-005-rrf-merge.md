## ADR-005: Reciprocal Rank Fusion for FTS5+Qdrant Merge

**Status:** Accepted

**Context:** Lux provides hybrid search combining full-text search (SQLite FTS5) and vector similarity search (Qdrant). Each backend returns a ranked list of results with different scoring scales. We need a merging strategy that produces a single coherent ranking without requiring score normalization or calibration.

**Decision:** Use Reciprocal Rank Fusion (RRF) to merge FTS5 and Qdrant result lists. RRF scores each document by the sum of `1 / (k + rank)` across both rankings, where `k` is a constant (default 60). Documents ranking highly in either backend are naturally boosted. Ties are broken by the higher individual rank.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| Reciprocal Rank Fusion | No normalization, parameter-free (single k), robust | Ignores raw scores entirely, can't weight backends differently |
| Min-max normalization | Preserves score magnitudes | Sensitive to outliers, requires score distribution knowledge |
| Z-score normalization | Statistically principled | Assumes normal distribution, expensive to compute |
| Learned combiner (LightGBM) | Optimal if tuned | Requires training data, overkill for initial implementation |

**Consequences:** RRF is simple and effective. The loss of raw score information is acceptable because FTS5 BM25 scores and Qdrant cosine distances are not directly comparable anyway. If backend weighting becomes necessary, we can extend RRF with per-backend weights.

**Implementation:** `lux/retrieval/merger.py`
