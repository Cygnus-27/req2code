"""Load eTour requirement documents off disk into `Requirement` objects.

eTour ships one plain-text file per requirement (a use-case description). The
filename stem is the requirement id used in the gold-link file, so it must be
carried through verbatim -- see `Requirement.req_id`.
"""

from __future__ import annotations

from pathlib import Path

from src.contracts import Requirement


def load_requirements(requirements_dir: str | Path) -> list[Requirement]:
    """Read every requirement document in `requirements_dir`.

    Args:
        requirements_dir: Directory of one-file-per-requirement text documents,
            e.g. ``data/etour/requirements/``.

    Returns:
        Requirements sorted by `req_id`, so runs are reproducible regardless of
        filesystem iteration order.

    Implementation notes for whoever fills this in:
        - Use the filename stem as `req_id`. Do not lowercase or strip suffixes
          until you have confirmed against the gold file what the ids look like.
        - Read as UTF-8 with ``errors="replace"``. This corpus was translated
          and has stray non-UTF8 bytes in places; a hard decode error here would
          kill the whole run for one bad character.
        - Keep the raw text. Cleaning/normalisation belongs in index/node_doc.py
          so that the baseline and our method share identical input text.
    """
    raise NotImplementedError
