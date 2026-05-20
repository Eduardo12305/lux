# Changelog

## v1.0.0 (2026-05-19)

### Added
- Agent loop completo com tool calling, compressao e budget warnings
- Sistema de memoria em 3 camadas: MEMORY.md + FTS5 + Qdrant
- Skills com progressive disclosure L0/L1/L2 + criacao autonoma
- Tools: terminal, filesystem, memory, session search, status
- Approval system com ALWAYS_DANGEROUS e WARN_PATTERNS
- ContextCompressor com tool pair rescue e session lineage
- VRAMGuard com thresholds e graceful degradation
- LlamaClient com slot management (GAP 3), ThinkingParser (GAP 4), rate limiting (GAP 6)
- WhisperLifecycleManager com refcount atomico (GAP 7)
- SkillVersionStore com backup e rollback (GAP 8)
- StartupCoordinator com health checks (GAP 9)
- ProcessLauncher para cold start (GAP 11)
- SchemaVersionManager com migrations SQL (GAP 10)
- RRF merge para FTS5 + Qdrant (GAP 5)
- Dependency Inversion via Protocols (Risco 8 resolvido)
- CLI basico com comandos /help, /quit, /status, /doctor
- docker-compose para Qdrant e Redis
- Makefile com targets: setup, run, test, lint, format, clean
- 105 testes unitarios passando
- 11 ADRs documentados
