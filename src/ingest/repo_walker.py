"""Walk the target source repository and yield files to parse.

Deliberately dumb: it finds files, it does not read or parse them. Parsing is
parse/'s job. Keeping the two separate means we can swap in a second language
later (the iTrust generalisation claim) by changing one glob.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def walk_source_files(repo_root: str | Path, suffix: str = ".java") -> Iterator[Path]:
    """Yield every source file under `repo_root` with the given suffix.

    Args:
        repo_root: Root of the code corpus, e.g. ``data/etour/source/``.
        suffix: File extension to match. Defaults to Java, the only language in
            eTour.

    Yields:
        Paths, sorted, so that node ids and therefore results are stable across
        runs and across machines.

    Implementation notes:
        - Skip anything under a directory named ``test``/``tests``. Test code
          inflates the orphan count with nodes no requirement could ever claim,
          which would make novelty claim #2 look noisier than it is. If you do
          include tests, say so explicitly in the output.
        - Yield absolute paths; the caller converts to repo-relative for
          `CodeNode.file_path`.
    """
    raise NotImplementedError
