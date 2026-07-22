"""Orphan detection: code that no requirement claims.

The other half of novelty claim #2, and the part with no equivalent in standard
traceability toolkits. An orphan is a code node whose best-matching requirement
still scores below a threshold -- nothing in the specification appears to ask
for it.

Orphans are interesting because they are usually one of:
    - dead code
    - an undocumented feature (a real finding -- scope crept and nobody wrote it
      down)
    - infrastructure that legitimately implements no requirement (getters,
      logging, framework glue)

That third category is the honest caveat: most orphans in any real codebase are
boring plumbing. Say so. The claim worth making is "this surfaces a small
reviewable set of unclaimed behaviour", not "everything flagged is a defect".
"""

from __future__ import annotations

from collections.abc import Sequence

from src.contracts import CodeNode, ResultRow


def find_orphans(
    reverse_results: Sequence[ResultRow],
    nodes: Sequence[CodeNode],
    threshold: float = 0.3,
) -> list[tuple[CodeNode, float]]:
    """Flag nodes whose best requirement match falls below `threshold`.

    Args:
        reverse_results: Output of `trace_code_to_requirements`.
        nodes: The full node corpus, so nodes that matched *nothing* and are
            therefore absent from `reverse_results` are still considered.
        threshold: Cosine below which a node counts as unclaimed.

    Returns:
        ``(node, best_score)`` pairs, lowest score first -- most orphaned first.

    On the threshold: 0.3 is a starting guess, not a result. Cosine similarities
        from MiniLM cluster in a narrow band, so pick the value by looking at the
        actual score distribution once the pipeline runs, and report which value
        was used. Better still, report the ranked list and let the reader pick
        the cutoff -- a sorted list is honest in a way a hard threshold is not.

    For Review 1 one convincing flagged orphan, with a sentence explaining why it
        is unclaimed, demonstrates the claim better than a list of forty.
    """
    raise NotImplementedError
