"""The ablation runner. This table is the project.

Each row isolates exactly one variable from the row above it, so that any gain
can be attributed to a specific cause rather than to "our system". Reviewers do
not accept "our pipeline scores 0.62"; they accept "node granularity contributed
+0.04, semantics contributed +0.11, and here is the run that shows it".

    Run  Representation           Granularity  Isolates
    B0   TF-IDF                   file         classic baseline
    B1   TF-IDF                   AST node     does node granularity alone help?
    E0   embeddings               file         does semantics alone help?
    E1   embeddings               AST node     our core method
    E2   E1 + query expansion     AST node     does requirement rewriting help?
    E3   E2 + identifier overlap  AST node     does lexical signal add on top?

B0 vs E1 is the headline claim. B1 and E0 are what make it survive scrutiny --
they are the two obvious "isn't it just...?" objections, answered pre-emptively.

All six are evaluated at FILE level after max-aggregation (see metrics.py), so
every number in the table is comparable to every other.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunConfig:
    """One row of the ablation table.

    Frozen and fully explicit: this object is what gets logged alongside the
    results, and it is what makes "every number traceable to a logged config"
    true rather than aspirational.
    """

    run_id: str
    representation: str  # "tfidf" | "embedding"
    granularity: str  # "file" | "node"
    query_expansion: bool = False
    beta: float = 0.0  # identifier-overlap weight; 0 disables


ABLATION_RUNS: tuple[RunConfig, ...] = (
    RunConfig("B0", "tfidf", "file"),
    RunConfig("B1", "tfidf", "node"),
    RunConfig("E0", "embedding", "file"),
    RunConfig("E1", "embedding", "node"),
    RunConfig("E2", "embedding", "node", query_expansion=True),
    RunConfig("E3", "embedding", "node", query_expansion=True, beta=0.3),
)


def run_ablation(
    data_dir: str | Path, results_dir: str | Path, top_k: int = 10
) -> dict[str, dict[str, float]]:
    """Execute every configuration and return ``run_id -> {metric: value}``.

    Implementation notes:
        - Parse and embed ONCE, then reuse across runs. The corpus does not
          change between configurations; only the scoring does. Re-embedding per
          run turns a 30-second job into a five-minute one for no reason.
        - Write each run's raw rows to ``results/{run_id}.csv`` before computing
          metrics. If a metric turns out to be buggy you can recompute from the
          CSVs instead of re-running the pipeline.
        - Set every seed you can reach and log the config next to the numbers.
    """
    raise NotImplementedError
