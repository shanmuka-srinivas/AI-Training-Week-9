"""
The embedding model: text in, 384 numbers out.

Loaded once and shared. Vectors are normalised to length 1, so cosine similarity
is just a dot product.
"""

import os

import numpy as np

from .config import EMBEDDING_MODEL, RERANKER_MODEL

# Both models are already in the local Hugging Face cache after the first run,
# so there is no reason to touch the network again.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

_model = None
_reranker = None


def embed(texts):
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return np.asarray(_model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False))


def cross_encoder():
    """The reranker. Only the appendix uses it."""
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker
