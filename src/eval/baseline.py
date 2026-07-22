"""TF-IDF + cosine baseline -- the classic VSM approach to traceability recovery.

This is what the literature has done since roughly 2003, and it is the number
our method has to beat. It must be implemented fairly and without handicap: a
strawman baseline invalidates the entire comparison, and a weak baseline is the
first thing a reviewer probes.

Fairness checklist:
    - Same requirement text as the embedding runs (no extra cleaning on either
      side)
    - Same corpus of artifacts
    - Same top_k
    - Same evaluation code path

The baseline runs at two granularities so the ablation can separate two effects
that are otherwise confounded:
    B0: TF-IDF over whole files  -- the classic setup
    B1: TF-IDF over AST nodes    -- isolates whether node granularity alone helps

B1 is the row that makes the work defensible. Without it, a reviewer can say
"your gains just come from chopping files into smaller pieces" and there is no
answer. With it, there is a number.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.contracts import CodeNode, Requirement, ResultRow


def tfidf_baseline(
    requirements: Sequence[Requirement],
    documents: Sequence[tuple[str, str]],
    run_id: str,
    top_k: int = 10,
) -> list[ResultRow]:
    """Rank documents against requirements by TF-IDF cosine similarity.

    Args:
        requirements: Queries.
        documents: ``(artifact_id, text)`` pairs. Passing pre-built pairs rather
            than `CodeNode`s is what lets this one function serve both B0 (ids
            are file paths, text is whole-file source) and B1 (ids are node ids,
            text is node documents).
        run_id: "B0" or "B1".
        top_k: Candidates per requirement.

    Implementation notes:
        - Fit the vectoriser on the *documents*, then transform the queries.
          Fitting on both leaks corpus statistics into the query representation.
        - Keep sklearn's default preprocessing. Resist the urge to bolt
          identifier-splitting onto the baseline -- that is our contribution, and
          giving it away here erases the gap the ablation is meant to measure.
          (If you want to know what splitting is worth to TF-IDF specifically,
          that is a legitimate extra row, not a change to B0/B1.)
    """
    raise NotImplementedError


def file_level_documents(nodes: Sequence[CodeNode]) -> list[tuple[str, str]]:
    """Reassemble whole-file documents from parsed nodes, for B0.

    Concatenating node text is preferable to re-reading the file from disk: it
    guarantees B0 and B1 see exactly the same characters, so the only variable
    between them is granularity.
    """
    raise NotImplementedError
