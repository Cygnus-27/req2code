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

    @property
    def node_to_file(self) -> dict[str, str]:
        """node_id -> file_path, for max-aggregation up to gold granularity."""
        return {n.node_id: n.file_path for n in self.nodes}

    def node_index(self) -> dict[str, int]:
        """node_id -> row index in `node_vectors`."""
        return {n.node_id: i for i, n in enumerate(self.nodes)}


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
    nodes, docs = parse_repo(data_dir / "code")
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
    )
