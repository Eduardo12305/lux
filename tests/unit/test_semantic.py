# tests/unit/test_semantic.py
# Módulo: Testes de busca semantica + RRF merge
# Status: IMPLEMENTADO

from __future__ import annotations

from lux.agent.state import MemoryChunk, MergedResult, SessionSearchResult
from lux.memory.semantic import merge_search_results_rrf, _strip_snippet_tags


def test_rrf_both_have_results():
    fts5 = [
        SessionSearchResult(
            id="m1", session_id="s1", timestamp="2026-01-01",
            role="user", snippet="<b>resultado</b> fts5", score=0.9,
        ),
        SessionSearchResult(
            id="m2", session_id="s1", timestamp="2026-01-02",
            role="assistant", snippet="segundo hit", score=0.5,
        ),
    ]
    qdrant = [
        MemoryChunk(id="c1", content="resultado semantico", score=0.85, source="semantic"),
    ]
    merged = merge_search_results_rrf(fts5, qdrant, fts5_weight=0.6)
    assert len(merged) >= 2
    assert merged[0].score > merged[-1].score


def test_rrf_fts5_only():
    fts5 = [
        SessionSearchResult(
            id="m1", session_id="s1", timestamp="2026-01-01",
            role="user", snippet="hit", score=0.9,
        ),
    ]
    merged = merge_search_results_rrf(fts5, [], fts5_weight=0.6)
    assert len(merged) == 1
    assert "fts5" in merged[0].sources


def test_rrf_qdrant_only():
    qdrant = [
        MemoryChunk(id="c1", content="hit semantico", score=0.9, source="semantic"),
    ]
    merged = merge_search_results_rrf([], qdrant, fts5_weight=0.6)
    assert len(merged) == 1
    assert "semantic" in merged[0].sources


def test_rrf_empty():
    merged = merge_search_results_rrf([], [])
    assert len(merged) == 0


def test_rrf_deduplicate_same_content():
    fts5_result = SessionSearchResult(
        id="shared", session_id="s1", timestamp="2026-01-01",
        role="user", snippet="conteudo compartilhado", score=0.9,
    )
    qdrant_result = MemoryChunk(id="shared", content="conteudo compartilhado", score=0.85, source="semantic")
    merged = merge_search_results_rrf([fts5_result], [qdrant_result])
    assert len(merged) == 2  # IDs diferentes no dict key (fts5_shared vs sem_shared)


def test_rrf_score_decays_with_rank():
    results = [
        SessionSearchResult(
            id=f"m{i}", session_id="s1", timestamp="2026-01-01",
            role="user", snippet=f"hit {i}", score=0.9,
        )
        for i in range(10)
    ]
    merged = merge_search_results_rrf(results, [])
    assert merged[0].score > merged[-1].score


def test_strip_snippet_tags():
    assert _strip_snippet_tags("<b>hit</b>") == "hit"
    assert _strip_snippet_tags("no tags") == "no tags"
    assert _strip_snippet_tags("<b>start... end</b>") == "start... end"
