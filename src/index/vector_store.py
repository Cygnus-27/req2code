"""Similarity search over the node embedding matrix.

Why plain numpy and not FAISS:

FAISS is an approximate-nearest-neighbour library. Approximation is a tradeoff
you make when exact search is too slow -- which happens somewhere north of a
million vectors. eTour yields a few thousand nodes. A ``(2000, 384) @ (384, 1)``
matmul is well under a millisecond, it is *exact*, and it removes a dependency
that is a genuine install hazard on Windows.

Using FAISS here would be slower to set up, slower to explain, and would give
worse answers. Revisit only if node count exceeds ~50k.
"""

from __future__ import annotations

import numpy as np


def search(
    query_vec: np.ndarray, matrix: np.ndarray, top_k: int = 10
) -> list[tuple[int, float]]:
    """Return the `top_k` most similar rows of `matrix` to `query_vec`.

    Args:
        query_vec: Shape ``(dim,)``, L2-normalised.
        matrix: Shape ``(n, dim)``, rows L2-normalised.
        top_k: How many results to return.

    Returns:
        ``(row_index, score)`` pairs, best first. Scores are cosine similarities
        in [-1, 1] -- in practice [0, 1] for this kind of text.

    Implementation note: because both sides are unit-normalised, this is just
        ``matrix @ query_vec``. Use ``np.argpartition`` for the top-k rather
        than sorting the full array -- O(n) instead of O(n log n). At this scale
        it makes no measurable difference, but it is the correct habit and it
        costs one line.
    """
    raise NotImplementedError


def search_batch(
    query_matrix: np.ndarray, matrix: np.ndarray, top_k: int = 10
) -> list[list[tuple[int, float]]]:
    """Search many queries at once -- all 58 requirements in a single matmul.

    Batching matters more than any micro-optimisation inside `search`: one
    ``(58, 384) @ (384, 2000)`` product is dramatically faster than 58 separate
    ones, because it saturates BLAS instead of paying Python loop overhead.
    """
    raise NotImplementedError
