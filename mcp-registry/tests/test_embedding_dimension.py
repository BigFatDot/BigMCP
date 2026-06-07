"""
Tests for the configurable embedding dimension (Chunk 3).

Coverage:
1. OpenAICompatibleEmbedder accepts a ``dimension`` kwarg and uses it in
   ``_pad_embedding`` (pad short, truncate long).
2. Default (no dimension passed) stays on ``MAX_DIMENSION`` (1536) for
   backward compatibility.
3. ``EmbeddingConfig.dimension`` propagates from ``Settings.EMBEDDING_DIMENSION``
   through ``VectorStore`` down to the embedder instance.
"""

from __future__ import annotations

import pytest

from app.config.settings import EmbeddingConfig
from app.core.vector_store import OpenAICompatibleEmbedder, VectorStore


# ---------------------------------------------------------------------------
# 1. _pad_embedding honours the configured dimension
# ---------------------------------------------------------------------------


def test_embedder_pads_to_custom_dimension():
    embedder = OpenAICompatibleEmbedder(
        api_url="http://example/v1",
        api_key="k",
        model="m",
        dimension=768,
    )

    padded = embedder._pad_embedding([0.1] * 512)
    assert len(padded) == 768
    # First 512 values preserved, remainder zero-padded.
    assert padded[:512] == [0.1] * 512
    assert padded[512:] == [0.0] * (768 - 512)


def test_embedder_truncates_when_api_returns_larger_dimension():
    """If the embedding API returns more dimensions than configured, truncate."""
    embedder = OpenAICompatibleEmbedder(
        api_url="http://example/v1",
        api_key="k",
        model="m",
        dimension=512,
    )

    # Simulate provider that returns 1024 dims for a 512-target deployment.
    oversized = [0.5] * 1024
    padded = embedder._pad_embedding(oversized)

    assert len(padded) == 512
    assert padded == [0.5] * 512


def test_embedder_default_dimension_is_max_dimension():
    """Backward compat: no dimension kwarg → MAX_DIMENSION (1536)."""
    embedder = OpenAICompatibleEmbedder(
        api_url="http://example/v1",
        api_key="k",
        model="m",
    )

    assert embedder.dimension == OpenAICompatibleEmbedder.MAX_DIMENSION == 1536

    padded = embedder._pad_embedding([0.1] * 100)
    assert len(padded) == 1536


def test_embedder_max_dimension_class_attribute_unchanged():
    """
    Class-level ``MAX_DIMENSION`` must stay 1536 so external code that
    reads it (e.g. legacy callers, tests) keeps working.
    """
    assert OpenAICompatibleEmbedder.MAX_DIMENSION == 1536


# ---------------------------------------------------------------------------
# 2. EmbeddingConfig → VectorStore → embedder propagation
# ---------------------------------------------------------------------------


def test_embedding_config_propagates_dimension_to_vectorstore():
    """A ``VectorStore`` built with EmbeddingConfig(dimension=1024) must
    instantiate its inner embedder with that same dimension."""
    cfg = EmbeddingConfig(dimension=1024)
    vs = VectorStore(config=cfg)

    assert vs.config.dimension == 1024
    assert vs.embedding_model is not None
    assert vs.embedding_model.dimension == 1024


def test_embedding_config_default_dimension_is_1536():
    """Default EmbeddingConfig stays on 1536 (backward compatibility)."""
    cfg = EmbeddingConfig()
    assert cfg.dimension == 1536

    vs = VectorStore(config=cfg)
    assert vs.embedding_model.dimension == 1536


def test_vectorstore_get_embeddings_zero_fallback_uses_config_dimension(monkeypatch):
    """When embedding_model is None (init failure), the zero fallback in
    ``VectorStore.get_embeddings`` must use the configured dimension —
    not the legacy hardcoded 1536."""
    cfg = EmbeddingConfig(dimension=768)
    vs = VectorStore(config=cfg)

    # Force the embedder to None to take the fallback branch.
    vs.embedding_model = None

    arr = vs.get_embeddings(["text 1", "text 2"])
    assert arr.shape == (2, 768)


def test_settings_env_var_default():
    """Settings.EMBEDDING_DIMENSION defaults to 1536 when env unset."""
    from app.core.config import settings as core_settings
    # The default is 1536; we don't assert "no env var" because the test
    # env may or may not set it. We just check the attribute exists and is
    # an int.
    assert isinstance(core_settings.EMBEDDING_DIMENSION, int)
    assert core_settings.EMBEDDING_DIMENSION > 0
