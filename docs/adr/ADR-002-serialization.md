## ADR-002: dataclasses_json for Checkpoint Serialization

**Status:** Accepted

**Context:** Checkpoints capture the full state of a conversation session so it can be paused, resumed, or inspected. This state includes messages, tool calls, model context, and metadata. We needed a serialization format that is human-readable (for debugging), structurally typed, and can round-trip through disk and network without loss.

**Decision:** Use Python `dataclasses` decorated with `dataclasses_json` for checkpoint serialization. All checkpoint types are defined as dataclasses with `@dataclass_json` decorators, providing automatic `to_json()` and `from_json()` methods.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| dataclasses_json | Zero boilerplate, type-safe, JSON-native | Requires dataclass discipline, schema evolution is manual |
| Pydantic | Validation, schema generation, widespread | Heavier dependency, validation not needed at serialization layer |
| pickle | Simple, any Python object | Unsafe, not portable, Python-version dependent |
| MessagePack | Compact binary format | Not human-readable, extra tooling needed for inspection |
| Manual JSON with json.dumps | No dependencies | Boilerplate encoders/decoders, error-prone |

**Consequences:** Checkpoints are readable JSON files on disk. Schema changes require careful handling for backward compatibility (addressed by `SchemaVersionManager` in ADR-010). We trade Pydantic's validation for lighter weight and simpler internals.

**Implementation:** `lux/checkpoints/models.py`
