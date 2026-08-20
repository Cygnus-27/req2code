"""Walk the target source repository and yield files to parse.

Deliberately dumb: it finds files, it does not read or parse them. Parsing is
parse/'s job. Keeping the two separate is what made adding six languages a
matter of adding specs rather than rewriting the walk.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from src.parse.languages import SUPPORTED_SUFFIXES

#: Directory names whose contents are skipped.
#:
#: Two groups, for two different reasons:
#:
#: - Test directories: test code inflates the orphan count with nodes no
#:   requirement could ever claim, which makes orphan detection look noisier
#:   than it is.
#: - Build output, dependencies, and VCS metadata: these are not the project's
#:   own code. Indexing `node_modules` would bury a repository's own methods
#:   under a hundred thousand vendored ones, and is the single fastest way to
#:   turn a 0.25ms query into an unusable one.
SKIP_DIRS = frozenset(
    {
        # tests
        "test",
        "tests",
        "__tests__",
        "spec",
        "testdata",
        # build output
        "build",
        "dist",
        "out",
        "target",
        "bin",
        "obj",
        "cmake-build-debug",
        # dependencies / vendored code
        "node_modules",
        "vendor",
        "third_party",
        "site-packages",
        ".venv",
        "venv",
        "env",
        # tooling and VCS
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)

#: Files larger than this are skipped.
#:
#: A source file this size is machine-generated -- a parser table, a bundled
#: minified script, an embedded blob. Parsing one costs seconds and contributes
#: a single enormous node whose vector is meaningless. The cap is on bytes
#: rather than lines because it must be decidable from `stat()`, without
#: reading the file.
MAX_FILE_BYTES = 1_000_000


def walk_source_files(
    repo_root: str | Path,
    suffix: str | None = None,
    suffixes: Iterable[str] | None = None,
    max_bytes: int = MAX_FILE_BYTES,
) -> Iterator[Path]:
    """Yield every parseable source file under `repo_root`.

    Args:
        repo_root: Root of the code corpus, e.g. `data/etour/code/`.
        suffix: A single extension, for callers that want exactly one language.
            Kept for backwards compatibility with the Java-only signature.
        suffixes: Explicit set of extensions. Defaults to every suffix any
            installed `LanguageSpec` claims, so adding a language automatically
            widens the walk with no change here.
        max_bytes: Skip files larger than this. See `MAX_FILE_BYTES`.

    Yields:
        Absolute paths, sorted, so node ids and results are stable across runs
        and across machines.
    """
    repo_root = Path(repo_root)
    if not repo_root.is_dir():
        raise FileNotFoundError(
            f"Source directory not found: {repo_root}\n"
            "Fetch the dataset first -- see the README quickstart."
        )

    if suffix is not None:
        suffixes = (suffix,)
    chosen = suffixes if suffixes is not None else SUPPORTED_SUFFIXES
    wanted = {s.lower() for s in chosen}

    for path in sorted(repo_root.rglob("*")):
        if path.suffix.lower() not in wanted:
            continue
        if any(part.lower() in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > max_bytes:
                continue
        except OSError:
            # A file that vanished between listing and stat-ing, or that we
            # cannot read. Skipping is correct: an index is allowed to be
            # incomplete, but a crawler that dies on one unreadable file in a
            # real repository is not usable.
            continue
        yield path.resolve()
