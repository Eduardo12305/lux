## ADR-004: 4-State ThinkingParser

**Status:** Accepted

**Context:** Lux supports models that emit internal reasoning tokens delimited by `<｜end▁of▁thinking｜>` and `<｜end▁of▁thinking｜>` tags (a convention used by several open-weight models). We need to parse the raw token stream, separate reasoning from final output, and expose both to the caller without losing tokens or misclassifying boundaries.

**Decision:** Implement a finite-state machine `ThinkingParser` with four states: `NORMAL`, `IN_THINKING`, `THINKING_ENDED`, and `COMPLETE`. The parser scans the token stream character by character, transitions states on tag boundaries, and accumulates tokens into separate reasoning and output buffers.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| 4-state FSM | Deterministic, testable, handles streaming | Manual state management, needs careful edge-case handling |
| Regex-based extraction | Concise expression | Fails on partial/incremental (streaming) input |
| Binary classifier per token | ML-based, handles fuzzy boundaries | Over-engineered, latency cost, model dependency |
| Assume XML well-formedness | Simple tree parser | Token streams are not valid XML mid-generation |

**Consequences:** The FSM correctly handles streaming input where tag boundaries may be split across chunks. The `THINKING_ENDED` state is necessary because `<｜end▁of▁thinking｜>` may appear followed by more content (not a real close tag) — we wait for the next `<｜end▁of▁thinking｜>` or end-of-stream to transition to `COMPLETE`.

**Implementation:** `lux/inference/thinking_parser.py`
