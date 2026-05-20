# lux/memory/semantic.py
# Módulo: Memory
# Dependências: config.py, models/embedder.py, agent/state.py
# Status: IMPLEMENTADO
# Notas: Qdrant wrapper para busca semantica + RRF merge (GAP 5).

from __future__ import annotations

import logging
from typing import Optional

from lux.agent.state import MemoryChunk, MergedResult, SessionSearchResult
from lux.config import get_config
from lux.models.embedder import Embedder

logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Busca semantica via Qdrant.
    Complementa FTS5 com recall conceitual.
    """

    COLLECTION_EPISODIC = "episodic_memory"
    COLLECTION_WORKSPACE = "workspace_knowledge"
    COLLECTION_SKILLS = "skill_patterns"

    def __init__(self, embedder: Optional[Embedder] = None):
        config = get_config()
        self._embedder = embedder or Embedder.get_instance()
        self._qdrant_url = config.qdrant_url
        self._client = None

    async def _ensure_client(self):
        if self._client is not None:
            return
        try:
            from qdrant_client import AsyncQdrantClient
            self._client = AsyncQdrantClient(url=self._qdrant_url)
            logger.info("Qdrant conectado em %s", self._qdrant_url)
        except ImportError:
            logger.warning("qdrant-client nao instalado — busca semantica desabilitada")
            self._client = False
        except Exception as e:
            logger.warning("Falha ao conectar Qdrant: %s — busca semantica desabilitada", e)
            self._client = False

    @property
    def available(self) -> bool:
        return self._client is not None and self._client is not False

    async def search(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        collection: str = "episodic_memory",
    ) -> list[MemoryChunk]:
        await self._ensure_client()
        if not self.available:
            return []

        try:
            embedding = await self._embedder.embed(query)
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            hits = await self._client.search(
                collection_name=collection,
                query_vector=embedding,
                query_filter=Filter(
                    must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                ),
                limit=top_k,
            )
            return [MemoryChunk.from_qdrant(hit.dict() if hasattr(hit, 'dict') else hit) for hit in hits]
        except Exception as e:
            logger.warning("Busca semantica falhou: %s", e)
            return []

    async def close(self):
        if self._client and self._client is not False:
            await self._client.close()
            self._client = None


def merge_search_results_rrf(
    fts5_results: list[SessionSearchResult],
    qdrant_results: list[MemoryChunk],
    fts5_weight: float = 0.6,
    k: int = 60,
) -> list[MergedResult]:
    """
    Reciprocal Rank Fusion (GAP 5).
    Combina resultados de FTS5 (lexical) e Qdrant (semantico).
    
    score(i) = fts5_weight * 1/(k + rank_fts5(i)) + (1-fts5_weight) * 1/(k + rank_qdrant(i))
    """
    if not fts5_results and not qdrant_results:
        return []

    combined: dict[str, MergedResult] = {}
    qdrant_weight = 1.0 - fts5_weight

    for rank, result in enumerate(fts5_results, start=1):
        key = f"fts5_{result.id}"
        score = fts5_weight * (1.0 / (k + rank))
        combined[key] = MergedResult(
            id=result.id,
            content=_strip_snippet_tags(result.snippet),
            score=score,
            sources=["fts5"],
            session_id=result.session_id,
        )

    for rank, chunk in enumerate(qdrant_results, start=1):
        key = f"sem_{chunk.id}"
        score = qdrant_weight * (1.0 / (k + rank))
        if key in combined:
            combined[key].score = max(combined[key].score, score)
            combined[key].sources.append("semantic")
        else:
            combined[key] = MergedResult(
                id=chunk.id,
                content=chunk.content,
                score=score,
                sources=["semantic"],
                session_id=chunk.session_id,
            )

    sorted_results = sorted(
        combined.values(), key=lambda r: r.score, reverse=True
    )
    return [r for r in sorted_results if r.score > 0.005]


def _strip_snippet_tags(snippet: str) -> str:
    import re
    return re.sub(r"</?b>", "", snippet)
