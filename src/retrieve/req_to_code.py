"""Forward direction: requirement -> ranked code nodes.

The primary retrieval path, and the one the demo table leads with.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.contracts import CodeNode, Requirement, ResultRow


def trace_requirements_to_code(
    requirements: Sequence[Requirement],
    nodes: Sequence[CodeNode],
    run_id: str,
    top_k: int = 10,
    alpha: float = 1.0,
    beta: float = 0.0,
) -> list[ResultRow]:
    """Rank code nodes against each requirement.

    Args:
        requirements: Queries.
        nodes: The corpus being searched.
        run_id: Ablation configuration id, written into every row ("E1", ...).
        top_k: Candidates to keep per requirement.
        alpha: Weight on the semantic signal.
        beta: Weight on the lexical signal. 0 disables it.

    Returns:
        `ResultRow`s with `artifact_id` set to `CodeNode.node_id`, ranked 1..k
        within each requirement.

    Implementation note: embed all requirements in one batch and all nodes in
        one batch, then do a single matmul. Embedding inside a per-requirement
        loop is the classic way to turn a 3-second run into a 3-minute one.
    """
    raise NotImplementedError
