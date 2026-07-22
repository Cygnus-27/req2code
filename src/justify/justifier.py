"""LLM-generated explanations of why a node satisfies a requirement.

Novelty claim #3. A ranked list tells an engineer *that* method X scored 0.71
against requirement R; it does not tell them whether to believe it. A short
natural-language rationale turns an opaque score into something reviewable.

Two hard rules:

1. **Everything is cached to disk as JSON.** The demo must run with the network
   off. Justifications are generated once, committed, and replayed. A live API
   call during a demo is a coin flip on your wifi, and the marginal value of
   freshness is zero -- the corpus does not change.

2. **Justifications are never fed back into scoring.** The LLM sees the trace
   after it is chosen and explains it. If its output influenced the ranking, we
   could no longer claim the retrieval results are reproducible from a fixed
   pipeline, and the eventual "does the rationale match human reasoning?"
   evaluation would be circular.

Scoring the justifications against human rationale is explicitly out of scope
for Review 1. Generate them, cache them, show one.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts import CodeNode, Requirement

CACHE_DIR = Path(__file__).parent / "cache"

PROMPT_TEMPLATE = """\
You are analysing traceability between a software requirement and a code method.

REQUIREMENT ({req_id}):
{req_text}

CODE ({node_id}, lines {start_line}-{end_line}):
{node_text}

In 2-3 sentences, explain whether and how this method contributes to satisfying
the requirement. Refer to specific identifiers in the code. If it does not
appear to satisfy the requirement, say so plainly -- a confident wrong answer is
worse than an honest negative.
"""


def cache_key(req: Requirement, node: CodeNode) -> str:
    """Stable filename-safe key for one (requirement, node) pair.

    Must not contain path separators -- `node_id` embeds a file path, so hash it
    or substitute the separators rather than using it raw.
    """
    raise NotImplementedError


def get_justification(
    req: Requirement, node: CodeNode, cache_dir: Path = CACHE_DIR
) -> str | None:
    """Return the cached justification for a pair, or None if absent.

    Read-only by design: it never calls out to a model. Generation is a separate,
    deliberate, online step (`generate_justifications`), so it is impossible to
    accidentally trigger a network call from the demo path.
    """
    raise NotImplementedError


def generate_justifications(
    pairs: list[tuple[Requirement, CodeNode]], cache_dir: Path = CACHE_DIR
) -> int:
    """Generate and cache justifications. ONLINE -- never called by the demo.

    Run this manually, commit the resulting JSON, and let the demo read it back.
    Returns the number of new justifications written.

    Log the model id and prompt version alongside each cached entry. "Every
    number traceable to a committed script + logged config" applies to generated
    text too -- in six weeks nobody will remember which model wrote these.
    """
    raise NotImplementedError
