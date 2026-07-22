"""The hybrid scoring function.

    score = alpha * cosine(req, node_doc) + beta * jaccard(req_tokens, node_identifiers)

Two signals, deliberately kept separate:

- **cosine** is semantic. It catches "notify the user" ~ `sendAlert`, where the
  words differ but the meaning does not. This is what the baseline cannot do.
- **jaccard** is lexical. It catches exact domain-vocabulary overlap -- when a
  requirement says "Bancomat" and the method is called `checkBancomat`, that is
  a near-certain link, and an embedding model that has never seen the word may
  well dilute it.

Start at alpha=1, beta=0 -- i.e. pure embeddings (run E1). Introducing beta is
run E3, one row of the ablation table.

Discipline on beta: try at most two values. This is a study of whether a lexical
signal helps *at all*, not a hyperparameter search. Sweeping twenty values and
reporting the best one on the same data you evaluated on is overfitting, and any
examiner will spot it. Two values, both reported, whatever the outcome.
"""

from __future__ import annotations


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity: ``|a & b| / |a | b|``. Empty inputs score 0.0."""
    raise NotImplementedError


def hybrid_score(
    cosine_sim: float,
    req_tokens: set[str],
    node_identifiers: set[str],
    alpha: float = 1.0,
    beta: float = 0.0,
) -> float:
    """Blend the semantic and lexical signals into a single score.

    Note the two terms are on comparable [0, 1] scales already, so no
    normalisation is needed before blending -- which is precisely why Jaccard was
    chosen over a raw overlap count.
    """
    raise NotImplementedError
