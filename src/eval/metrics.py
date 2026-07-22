"""Retrieval metrics, evaluated at file level.

Why file level, when the entire point of the project is node-level retrieval?

Because the gold links are file-level. Scoring node-level predictions against
file-level truth would be comparing different things, and any number produced
that way would be indefensible under questioning. So:

    1. Retrieve at node level (that is the contribution).
    2. Aggregate node scores up to file level using MAX -- a file scores as well
       as its single best-matching method.
    3. Compute metrics at file level, where they are directly comparable to the
       TF-IDF baseline and to published results on eTour.
    4. Report node-level output qualitatively, in the demo table.

Max-aggregation, rather than mean, because a requirement is typically satisfied
by one or two methods inside a large class. Averaging over the class's other
thirty methods would bury exactly the signal we are trying to demonstrate.

This tradeoff must appear in the demo output and the README. It is a limitation
stated openly, not one hidden.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.contracts import ResultRow


def aggregate_to_file_level(
    rows: Sequence[ResultRow], node_to_file: dict[str, str]
) -> list[ResultRow]:
    """Collapse node-level results into file-level results by max score.

    Args:
        rows: Node-level rows for one or more runs.
        node_to_file: `CodeNode.node_id` -> `CodeNode.file_path`.

    Returns:
        File-level rows, re-ranked densely from 1 within each (run_id, req_id).

    Implementation note: re-rank after aggregating. Carrying the old node ranks
        through would leave gaps (ranks 1, 4, 9...) and quietly corrupt any
        rank-sensitive metric such as MAP or MRR.
    """
    raise NotImplementedError


def precision_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the top-k retrieved artifacts that are in the gold set."""
    raise NotImplementedError


def recall_at_k(ranked: Sequence[str], relevant: set[str], k: int) -> float:
    """Fraction of the gold set that appears in the top-k retrieved artifacts.

    The headline metric for traceability recovery: an engineer would rather see
    a few false positives than miss a real link, so recall is weighted more
    heavily than precision in this domain.
    """
    raise NotImplementedError


def average_precision(ranked: Sequence[str], relevant: set[str]) -> float:
    """Average precision for a single query -- mean over MAP.

    Rewards putting correct links near the top, not merely finding them.
    """
    raise NotImplementedError


def mean_average_precision(
    ranked_per_req: dict[str, Sequence[str]], gold: dict[str, set[str]]
) -> float:
    """MAP across all requirements. The single number the ablation table sorts on.

    Implementation note: requirements with no gold links must be excluded, not
        scored as 0.0. Including them drags every configuration down by the same
        constant, which flatters nothing but makes the numbers non-comparable
        with published eTour results.
    """
    raise NotImplementedError
