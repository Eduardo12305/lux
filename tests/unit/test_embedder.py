# tests/unit/test_embedder.py
# Módulo: Testes de Embedder
# Status: IMPLEMENTADO

from __future__ import annotations

import pytest

from lux.models.embedder import Embedder, EmbedderError


@pytest.fixture
def embedder():
    return Embedder(model_name="all-MiniLM-L6-v2")


def test_embedder_default_dimension(embedder):
    assert embedder.dimension == 384


def test_embedder_not_loaded_initially(embedder):
    assert embedder.is_loaded is False


def test_embedder_setup_fallback(embedder):
    embedder._setup_fallback()
    assert embedder.is_loaded is True
    assert embedder._fallback is True


def test_embedder_embed_fallback(embedder):
    embedder._setup_fallback()
    result = embedder._embed_fallback("test text")
    assert isinstance(result, list)
    assert len(result) == embedder._dim
    assert all(isinstance(v, float) for v in result)


def test_embedder_embed_fallback_multiple_texts(embedder):
    embedder._setup_fallback()
    r1 = embedder._embed_fallback("first text")
    r2 = embedder._embed_fallback("second different")
    assert isinstance(r1, list)
    assert isinstance(r2, list)
    assert len(r1) == embedder._dim
    assert len(r2) == embedder._dim
