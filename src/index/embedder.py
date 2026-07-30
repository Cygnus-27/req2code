"""Text -> dense vectors, via sentence-transformers.

Model: ``all-MiniLM-L6-v2``. Chosen because it is small (~80MB), fast on CPU,
and produces 384-dimensional vectors -- meaning the entire eTour corpus is a
matrix of roughly 1200x384 floats, about 1.8MB. That is what makes plain numpy
viable as the "vector database" (see vector_store.py).

A code-aware model is a later ablation row, not a starting point. Establish that
the pipeline works with the boring model first; swapping models is a one-line
change once everything around it is correct.

OFFLINE: the model is downloaded once into ``models/`` and loaded from there
afterwards. Embeddings are additionally cached to ``.npy`` keyed by a hash of the
input text, so a warm run does no model work at all.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

#: Local model store. Committed to .gitignore; re-downloadable.
MODEL_DIR = Path("models")

#: Where cached embedding matrices live.
CACHE_DIR = Path("models/.embcache")

_model = None


def _load_model(model_name: str = MODEL_NAME):
    """Load the sentence-transformer once per process.

    Deferred import: sentence-transformers pulls in torch, which takes a couple
    of seconds. Modules that only need `cache_key` should not pay that cost.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        _model = SentenceTransformer(
            model_name, cache_folder=str(MODEL_DIR), device="cpu"
        )
    return _model


def cache_key(texts: list[str], model_name: str = MODEL_NAME) -> str:
    """Content hash of the input corpus, so the cache invalidates automatically.

    Keying on content rather than a filename means changing node_doc.py silently
    produces a different key and forces a re-embed -- which is what you want,
    because stale vectors from an older document builder would be invisible and
    would quietly corrupt every result downstream.
    """
    digest = hashlib.sha256(model_name.encode())
    for text in texts:
        digest.update(text.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def embed_texts(
    texts: list[str],
    model_name: str = MODEL_NAME,
    cache_name: str | None = None,
    show_progress: bool = False,
) -> np.ndarray:
    """Embed a list of texts into an L2-normalised matrix.

    Args:
        texts: Documents to embed -- requirement texts or node documents.
        model_name: sentence-transformers model id.
        cache_name: Optional label for the on-disk cache ("nodes", "reqs"). The
            actual filename also includes a content hash.
        show_progress: Show the encoding progress bar.

    Returns:
        Array of shape ``(len(texts), EMBEDDING_DIM)``, dtype float32, with each
        row L2-normalised.

    Why normalise here rather than at search time: once every vector is unit
    length, cosine similarity is exactly the dot product. That collapses the
    entire search step into one matrix multiply (see vector_store.py) with no
    per-query division and no risk of normalising twice.
    """
    if not texts:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    cache_path: Path | None = None
    if cache_name:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CACHE_DIR / f"{cache_name}-{cache_key(texts, model_name)}.npy"
        if cache_path.exists():
            cached = np.load(cache_path)
            if cached.shape == (len(texts), EMBEDDING_DIM):
                return cached

    model = _load_model(model_name)
    vectors = model.encode(
        texts,
        batch_size=64,
        convert_to_numpy=True,
        normalize_embeddings=True,  # unit length -> dot product == cosine
        show_progress_bar=show_progress,
    ).astype(np.float32)

    if cache_path is not None:
        np.save(cache_path, vectors)
    return vectors


def is_offline() -> bool:
    """Whether HF is pinned offline. The demo asserts this indirectly by working."""
    return os.environ.get("HF_HUB_OFFLINE") == "1"
