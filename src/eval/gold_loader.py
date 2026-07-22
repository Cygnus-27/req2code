"""Load the eTour gold answer set.

GATE -- do this before building anything on top of it: open the raw gold file by
hand and confirm each line maps a *requirement* to a *code file*. The handoff
assumption is requirement -> file. If it turns out to be requirement ->
requirement, or file -> file, every metric downstream is meaningless and the
granularity strategy has to be rethought. Verify, do not assume.
"""

from __future__ import annotations

from pathlib import Path


def load_gold_links(gold_path: str | Path) -> dict[str, set[str]]:
    """Read the gold trace matrix.

    Args:
        gold_path: Path to eTour's answer-set file.

    Returns:
        Mapping of ``req_id -> set of file paths`` that genuinely implement it.
        A set, not a list, because membership testing is the only operation
        metrics.py needs and duplicates in the source file should collapse.

    Implementation notes:
        - The ids here are authoritative. If `requirements_loader` produces ids
          that do not match these keys, fix the loader, not the gold file.
        - Assert the totals after loading (~58 requirements, ~308 links). A
          silent parse failure that yields 12 links will still "run" and will
          quietly produce excellent-looking recall.
    """
    raise NotImplementedError
