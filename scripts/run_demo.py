"""The Review 1 demo. One command, offline, under 60 seconds.

    python -m scripts.run_demo

Prints one table covering all three novelty claims on a deliberately narrow
slice of eTour:

    (a) one requirement -> ranked method-level code nodes      [claim 1]
    (b) the same requirement through the TF-IDF file baseline  [the comparison]
    (c) one flagged orphan code node                           [claim 2]
    (d) one cached LLM justification                           [claim 3]

Design rule for this script: a complete narrow slice, not a half-built system.
The whole pipeline running on ten requirements is a far better demonstration
than half the pipeline running on all fifty-eight -- it proves the architecture
works end to end, and scaling it up is then just a parameter.

Everything here reads from disk. No network calls, no model downloads at
demo time, no API keys.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_DATA_DIR = Path("data/etour")

#: Demo slice size. Small enough to stay well inside the 60s budget while still
#: showing the pipeline is general rather than hardcoded to one example.
DEMO_REQUIREMENT_COUNT = 5


def print_demo_table() -> None:
    """Render the demo output. Give this a real signature once the shapes settle.

    Formatting guidance -- the table is the deliverable, so it deserves care:
        - Show the requirement text, truncated to ~80 chars, not just its id.
          The audience cannot evaluate a trace they cannot read.
        - For each hit show: rank, score, `Class.method()`, file:line. The
          file:line is what makes "we trace to precise AST nodes" concrete
          rather than a claim.
        - Put the baseline column directly alongside, same requirement, same k.
          The contrast is the argument; making the reader hold two tables in
          their head weakens it.
        - State the file-level aggregation caveat in a footer line. Volunteering
          the limitation reads as rigour; being caught omitting it does not.
        - Plain text. No colour libraries, no box-drawing dependencies.
    """
    raise NotImplementedError


def main() -> int:
    """Entry point.

    Suggested order, so a failure tells you exactly which stage broke:
        1. Load requirements + gold links; print corpus stats (counts prove the
           data loaded correctly before anything else runs)
        2. Parse the repo into CodeNodes; print node count and any parse errors
        3. Build node documents; print one example document in full -- this is
           the single most useful debugging output in the project
        4. Embed, search, rank
        5. Run the TF-IDF baseline on the same requirement
        6. Reverse-trace and pick one orphan
        7. Load one cached justification
        8. Print the table, with timing
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--top-k", type=int, default=5)
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
