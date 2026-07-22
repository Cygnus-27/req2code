"""Requirement rewriting, to close the vocabulary gap. Ablation run E2.

The problem: requirements are written in user/business language ("the tourist
shall be able to search for nearby cultural sites") while code is written in
implementation language (`findPOIByRadius`). The two describe the same behaviour
with almost disjoint vocabulary. This is the central difficulty of traceability
recovery and the reason lexical baselines plateau.

The idea: rewrite each requirement into something closer to how a developer
would name things, then embed *that*.

E2 exists to test whether it helps. It may not -- expansion can also add noise
and drag in unrelated methods. A negative result here is a perfectly good
ablation row and should be reported as one.

Offline constraint: if expansion uses an LLM, expanded queries are generated
once and committed to disk as JSON, exactly like the justification cache. The
demo must never make a network call.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts import Requirement


def expand_requirement(req: Requirement, cache: dict[str, str]) -> str:
    """Return the expanded query text for a requirement.

    Args:
        req: The original requirement.
        cache: Pre-generated ``req_id -> expanded text``, loaded from disk.

    Returns:
        Expanded text, or `req.text` unchanged on a cache miss. Falling back to
        the original rather than raising means a partially populated cache still
        produces a complete, interpretable run.
    """
    raise NotImplementedError


def load_expansion_cache(cache_path: str | Path) -> dict[str, str]:
    """Load pre-generated expansions. Returns ``{}`` if the file does not exist."""
    raise NotImplementedError
