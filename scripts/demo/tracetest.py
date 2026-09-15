"""tracetest -- one command, the offline CLI path, for the demo.

    python -m scripts.demo.tracetest "the system shall ..."

Groups exactly what the professor demo needs into one invocation: state the
requirement, print the ranked trace, print the current orphan snapshot, and
print a performance table for the run that just happened -- then append a
record of it to req2code-orphan-test/.req2code/tracetest_log.jsonl so a whole
session of queries can be replayed or handed over afterward.

Nothing here talks MCP and nothing here is an AI agent -- this is the pipeline
running by itself (parse -> embed -> cosine search), which is the "offline"
half of the demo. The AI-facing half is scripts/demo/mcpaitracetest.py.

WHY IN-PROCESS RATHER THAN A SUBPROCESS WRAPPER AROUND scripts.req2code
------------------------------------------------------------------------
A subprocess pays model load twice if you also want the corpus timings, and
loses the ability to time individual stages. Loading `src.pipeline` and
`src.api` directly gives the same numbers `scripts/req2code.py state` prints,
plus the per-stage timings `index` prints, from one corpus load.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src.index.embedder import pin_offline_if_cached

pin_offline_if_cached()

DEFAULT_REPO = Path(r"C:\Users\Atharv\Desktop\req2code-orphan-test")
BUDGET_MS = 100.0


def _label(corpus, node) -> str:
    enclosing = corpus.enclosing.get(node.node_id, "")
    name = f"{enclosing}.{node.name}()" if enclosing else f"{node.name}()"
    return f"{name}  {node.file_path}:{node.start_line}-{node.end_line}"


def run(repo: Path, text: str, top_k: int, threshold: float) -> dict:
    from src import api
    from src.index.vector_store import search
    from src.pipeline import load_corpus

    t_load0 = time.perf_counter()
    corpus = load_corpus(repo)
    t_load = (time.perf_counter() - t_load0) * 1000

    t_query0 = time.perf_counter()
    requirement, created = corpus.add_requirement(text)
    row = {r.req_id: i for i, r in enumerate(corpus.requirements)}[requirement.req_id]
    hits = search(corpus.req_vectors[row], corpus.node_vectors, top_k=top_k)
    t_query = (time.perf_counter() - t_query0) * 1000

    t_orphan0 = time.perf_counter()
    orphan_payload = api.orphans(corpus, threshold, limit=20)
    t_orphan = (time.perf_counter() - t_orphan0) * 1000

    payload = api.trace(corpus, hits, req=requirement, created=created)

    print(f"{payload['req_id']}{'  (already logged)' if not created else ''}")
    print(f"  {payload['query']}")
    print()
    if not hits:
        print("  (nothing indexed yet)")
    for item in payload["hits"]:
        enclosing = item["enclosing"]
        name = f"{enclosing}.{item['name']}()" if enclosing else f"{item['name']}()"
        print(
            f"  {item['rank']:>3}. {item['score']:.3f}  {name}  "
            f"{item['file']}:{item['start_line']}-{item['end_line']}"
        )

    print()
    print(f"orphans right now: {orphan_payload['flagged']} of {orphan_payload['methods']} "
          f"methods below {orphan_payload['threshold']:.2f}")

    print()
    print("performance -- this run, this machine, offline (no network, no LLM)")
    print("-" * 66)
    rows = [
        ("corpus load (parse + embed, cache-warm)", t_load),
        ("state + rank (embed query, cosine search)", t_query),
        ("orphan scan (whole corpus)", t_orphan),
    ]
    for label, ms in rows:
        mark = "OK" if ms <= BUDGET_MS else "over 100ms budget"
        print(f"  {label:<44} {ms:>8.2f} ms   {mark}")
    total = sum(ms for _, ms in rows)
    print("-" * 66)
    print(f"  {'total':<44} {total:>8.2f} ms")

    record = {
        "kind": "tracetest",
        "ts": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "req_id": payload["req_id"],
        "text": text,
        "top1": payload["hits"][0] if payload["hits"] else None,
        "hits": payload["hits"],
        "orphans_flagged": orphan_payload["flagged"],
        "orphans_total_methods": orphan_payload["methods"],
        "timings_ms": {
            "corpus_load": round(t_load, 2),
            "state_and_rank": round(t_query, 2),
            "orphan_scan": round(t_orphan, 2),
            "total": round(total, 2),
        },
    }
    return record


def _append_log(repo: Path, record: dict) -> Path:
    log_dir = repo / ".req2code"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "tracetest_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracetest",
        description="Offline trace + performance table, in one command, for the demo.",
    )
    parser.add_argument("text", help="Requirement text, in quotes.")
    parser.add_argument(
        "--repo", type=Path, default=DEFAULT_REPO, help="Repository to trace against."
    )
    parser.add_argument("--top-k", "-k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument(
        "--no-log", action="store_true", help="Don't append to tracetest_log.jsonl."
    )
    args = parser.parse_args(argv)

    if not args.repo.exists():
        print(f"No such repository: {args.repo}", file=sys.stderr)
        return 2

    record = run(args.repo, args.text, args.top_k, args.threshold)

    if not args.no_log:
        log_path = _append_log(args.repo, record)
        print()
        print(f"recorded -> {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
