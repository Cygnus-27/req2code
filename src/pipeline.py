"""Corpus loading, wired once and reused by every run.

Both entry points (demo and ablation) need the same expensive setup: parse the
repo, build node documents, embed everything. Doing that once and reusing it is
what keeps a six-configuration ablation to seconds rather than minutes -- the
corpus does not change between configurations, only the scoring does.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.contracts import CodeNode, Requirement

DEFAULT_DATA_DIR = Path("data/etour")
GOLD_FILENAME = "etour_solution_links_english.txt"


@dataclass
class Corpus:
    """Everything the retrieval and evaluation layers need, loaded once."""

    requirements: list[Requirement]
    nodes: list[CodeNode]
    docs: dict[str, str]  # node_id -> raw javadoc
    enclosing: dict[str, str]  # node_id -> enclosing class name
    node_documents: list[str]  # row-aligned with nodes
    gold: dict[str, set[str]]
    req_vectors: np.ndarray = field(repr=False)
    node_vectors: np.ndarray = field(repr=False)
    timings: dict[str, float] = field(default_factory=dict, repr=False)
    code_root: Path | None = field(default=None, repr=False)
    mtimes: dict[str, float] = field(default_factory=dict, repr=False)

    @property
    def node_to_file(self) -> dict[str, str]:
        """node_id -> file_path, for max-aggregation up to gold granularity."""
        return {n.node_id: n.file_path for n in self.nodes}

    def node_index(self) -> dict[str, int]:
        """node_id -> row index in `node_vectors`."""
        return {n.node_id: i for i, n in enumerate(self.nodes)}

    # -- incremental update ------------------------------------------------
    #
    # A corpus that can only be rebuilt from scratch cannot live in an editor:
    # a full rebuild is ~2.7s of embedding, which is 30x over the ~100ms budget
    # where a user stops perceiving an action as instant. Re-embedding only the
    # edited file costs ~45ms, because the per-text cache in index/embedder.py
    # means unchanged nodes are dict lookups rather than model calls.
    #
    # Row alignment between `nodes`, `node_documents` and `node_vectors` is the
    # invariant everything downstream depends on, so all three are rebuilt
    # together, never separately.

    def reindex_file(self, path: str | Path) -> int:
        """Re-parse and re-embed a single source file in place.

        Args:
            path: Path to the ``.java`` file. May be absolute or relative to
                the repo root. A file that no longer exists has its nodes
                dropped, which is what makes deletion work.

        Returns:
            Number of nodes the file now contributes (0 if deleted).
        """
        from src.index.embedder import embed_texts
        from src.index.node_doc import build_all_documents
        from src.parse.java_parser import enclosing_class_map, parse_file

        if self.code_root is None:
            raise RuntimeError("Corpus was not built from a code root; cannot reindex.")

        path = Path(path)
        rel = str(path.resolve().relative_to(self.code_root.resolve())).replace(
            "\\", "/"
        )

        # Drop everything the old version of this file contributed.
        keep = [i for i, n in enumerate(self.nodes) if n.file_path != rel]
        for node in self.nodes:
            if node.file_path == rel:
                self.docs.pop(node.node_id, None)
                self.enclosing.pop(node.node_id, None)

        if path.exists():
            new_nodes, new_docs = parse_file(path, self.code_root)
            new_enclosing = enclosing_class_map(new_nodes)
            new_documents = build_all_documents(new_nodes, new_enclosing, new_docs)
            new_vectors = embed_texts(new_documents, cache_name="nodes")
            self.docs.update(new_docs)
            self.enclosing.update(new_enclosing)
            self.mtimes[rel] = path.stat().st_mtime
        else:
            new_nodes, new_documents = [], []
            new_vectors = np.zeros((0, self.node_vectors.shape[1]), dtype=np.float32)
            self.mtimes.pop(rel, None)

        self.nodes = [self.nodes[i] for i in keep] + new_nodes
        self.node_documents = [self.node_documents[i] for i in keep] + new_documents
        self.node_vectors = np.vstack([self.node_vectors[keep], new_vectors])
        return len(new_nodes)

    def refresh(self) -> list[str]:
        """Reindex every source file whose mtime changed since the last look.

        Returns the list of files that were reindexed.

        Polling mtimes rather than running a filesystem watcher is deliberate:
        stat-ing eTour's 116 files costs ~9ms, comfortably inside the ~100ms
        interaction budget, so it can run on every query. That removes a
        dependency, a background thread, and the whole class of bugs where a
        watcher misses an event and the index goes quietly stale.
        """
        if self.code_root is None:
            return []
        from src.ingest.repo_walker import walk_source_files

        # Resolve the root once, not once per file: `Path.resolve()` touches the
        # filesystem, and doing it 116 times is most of this function's cost.
        root = self.code_root.resolve()
        changed: list[str] = []
        seen: set[str] = set()
        for path in walk_source_files(self.code_root):
            rel = str(path.relative_to(root)).replace("\\", "/")
            seen.add(rel)
            if self.mtimes.get(rel) != path.stat().st_mtime:
                self.reindex_file(path)
                changed.append(rel)

        for rel in [r for r in self.mtimes if r not in seen]:
            self.reindex_file(self.code_root / rel)
            changed.append(rel)
        return changed


def load_corpus(
    data_dir: str | Path = DEFAULT_DATA_DIR,
    strict_gold: bool = True,
    verbose: bool = False,
) -> Corpus:
    """Parse, document-build, and embed the whole corpus.

    Embeddings are content-hash cached to ``models/.embcache``, so the first run
    pays the model cost (~10s) and every later run is near-instant.
    """
    from src.eval.gold_loader import load_gold_links
    from src.index.embedder import embed_texts
    from src.index.node_doc import build_all_documents
    from src.ingest.requirements_loader import load_requirements
    from src.parse.java_parser import enclosing_class_map, parse_repo

    data_dir = Path(data_dir)
    timings: dict[str, float] = {}

    def step(label: str):
        start = time.perf_counter()

        def done():
            timings[label] = time.perf_counter() - start
            if verbose:
                print(f"  {label:22} {timings[label]:6.2f}s")

        return done

    finish = step("load requirements")
    requirements = load_requirements(data_dir / "req")
    finish()

    finish = step("parse java")
    code_root = data_dir / "code"
    nodes, docs = parse_repo(code_root)
    enclosing = enclosing_class_map(nodes)
    finish()

    finish = step("build node docs")
    node_documents = build_all_documents(nodes, enclosing, docs)
    finish()

    finish = step("load gold links")
    gold = load_gold_links(data_dir / GOLD_FILENAME, strict=strict_gold)
    finish()

    finish = step("embed requirements")
    req_vectors = embed_texts([r.text for r in requirements], cache_name="reqs")
    finish()

    finish = step("embed nodes")
    node_vectors = embed_texts(node_documents, cache_name="nodes")
    finish()

    from src.ingest.repo_walker import walk_source_files

    mtimes = {
        str(p.resolve().relative_to(code_root.resolve())).replace(
            "\\", "/"
        ): p.stat().st_mtime
        for p in walk_source_files(code_root)
    }

    return Corpus(
        requirements=requirements,
        nodes=nodes,
        docs=docs,
        enclosing=enclosing,
        node_documents=node_documents,
        gold=gold,
        req_vectors=req_vectors,
        node_vectors=node_vectors,
        timings=timings,
        code_root=code_root,
        mtimes=mtimes,
    )
