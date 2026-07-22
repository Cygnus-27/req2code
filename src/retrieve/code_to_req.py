"""Reverse direction: code node -> ranked requirements.

Half of novelty claim #2. Standard traceability tools run only forward, which
answers "where is this requirement implemented?" but never "why does this code
exist?" -- the question an engineer inheriting a codebase actually asks.

Mechanically this is cheap: the similarity matrix from the forward direction,
transposed. That is worth noticing rather than hiding -- with a symmetric
similarity measure, bidirectionality is nearly free, and the contribution is
in *asking* the reverse question and acting on the answer (see orphans.py),
not in the arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.contracts import CodeNode, Requirement, ResultRow


def trace_code_to_requirements(
    nodes: Sequence[CodeNode],
    requirements: Sequence[Requirement],
    run_id: str,
    top_k: int = 5,
) -> list[ResultRow]:
    """Rank requirements against each code node.

    Returns:
        `ResultRow`s where `req_id` holds the *node* id and `artifact_id` holds
        the requirement id.

    Note the field-role inversion above. It is slightly awkward, and the
    alternative -- a second CSV schema -- is worse: it would double the parsing
    surface in eval/ for no gain. Document it wherever these rows are written
    and keep reverse-direction results in their own file.
    """
    raise NotImplementedError
