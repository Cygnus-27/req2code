"""Walk the target source repository and yield files to parse.

Deliberately dumb: it finds files, it does not read or parse them. Parsing is
parse/'s job. Keeping the two separate means we can swap in a second language
later (the iTrust generalisation claim) by changing one glob.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

#: Directory names whose contents are skipped. eTour's code/ directory is flat,
#: so this currently matches nothing -- it is here for iTrust, which is a real
#: source tree with tests in it.
SKIP_DIRS = frozenset({"test", "tests", "build", "target", ".git"})


def walk_source_files(repo_root: str | Path, suffix: str = ".java") -> Iterator[Path]:
    """Yield every source file under `repo_root` with the given suffix.

    Args:
        repo_root: Root of the code corpus, e.g. ``data/etour/code/``.
        suffix: File extension to match. Defaults to Java, the only language in
            eTour.

    Yields:
        Absolute paths, sorted, so node ids and results are stable across runs
        and across machines.

    Test code is skipped: it inflates the orphan count with nodes no requirement
    could ever claim, which would make the orphan-detection claim look noisier
    than it is.
    """
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        raise FileNotFoundError(
            f"Source directory not found: {repo_root}\n"
            "Fetch the dataset first -- see the README quickstart."
        )

    for path in sorted(repo_root.rglob(f"*{suffix}")):
        if any(part.lower() in SKIP_DIRS for part in path.parts):
            continue
        yield path.resolve()
