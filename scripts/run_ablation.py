"""Run the full ablation table and write results.

    python -m scripts.run_ablation

Not part of the Review 1 demo -- this is the evaluation run that produces the
numbers for the report. Slower than the demo and allowed to be.

Writes:
    results/{run_id}.csv    raw ranked rows, frozen schema (see contracts.py)
    results/ablation.md     the summary table, pasteable into the report
    results/config.json     every RunConfig plus versions and seeds

That last file is what makes "every number traceable to a committed script and a
logged config" real. Write it every run, without exception -- the run you forget
to log is the one you will need to reproduce.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_DATA_DIR = Path("data/etour")
DEFAULT_RESULTS_DIR = Path("results")


def main() -> int:
    """Entry point. Delegates to `src.eval.ablation.run_ablation`."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--top-k", type=int, default=10)
    parser.parse_args()
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
