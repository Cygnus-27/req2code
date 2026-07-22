"""Text -> dense vectors, via sentence-transformers.

Model: ``all-MiniLM-L6-v2``. Chosen because it is small (~80MB), fast on CPU,
and produces 384-dimensional vectors -- meaning the entire eTour corpus is a
matrix of roughly 2000x384 floats, about 3MB. That is what makes plain numpy
viable as the "vector database" (see vector_store.py).

A code-aware model is a later ablation row, not a starting point. Establish that
the pipeline works with the boring model first; swapping models is a one-line
change once everything around it is correct.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


def embed_texts(
    texts: list[str], model_name: str = MODEL_NAME, cache_path: str | Path | None = None
) -> np.ndarray:
    """Embed a list of texts into an L2-normalised matrix.

    Args:
        texts: Documents to embed -- requirement texts or node documents.
        model_name: sentence-transformers model id.
        cache_path: Optional ``.npy`` path. If it exists, load instead of
            recomputing.

    Returns:
        Array of shape ``(len(texts), EMBEDDING_DIM)``, dtype float32, with each
        row L2-normalised.

    Why normalise here rather than at search time: once every vector is unit
    length, cosine similarity is exactly the dot product. That collapses the
    entire search step into one matrix multiply (see vector_store.py) with no
    per-query division and no risk of normalising twice.

    Offline requirement: the model must be downloaded once and cached under
        ``models/``. Set ``HF_HUB_OFFLINE=1`` and confirm the demo still runs
        with the network off -- before demo day, not during it.
    """
    raise NotImplementedError
