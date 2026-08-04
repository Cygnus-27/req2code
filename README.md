# req2code

**Requirement-to-Code Traceability via AST-Aware Retrieval**

Recovering the lost mapping between what software was supposed to do and the
code that actually does it — by matching meaning rather than keywords, and by
tracing to individual methods rather than whole files.

> **Status: working prototype.** The full pipeline runs end to end on eTour —
> parse → index → retrieve → evaluate → justify — offline, in ~1.2s. It also
> runs live inside an editor via MCP, at 0.25ms per query. All numbers below are
> measured, reproducible from committed scripts, and include the negative results.

---

## The problem

Every project starts with requirements and then spends years drifting from them.
The link between requirement #37 and the code satisfying it lives in someone's
head, and then that person leaves. That matters when you need to answer *"we're
changing this requirement — what code breaks?"*, *"what is this method for?"*,
or *"prove every safety requirement is implemented"* — an audit question with
legal weight in regulated domains.

The classic approach — TF-IDF over requirement text vs. source text — has a hard
ceiling, because the two describe the same behaviour in almost disjoint
vocabulary. A requirement says *"the system shall notify the user"*; the code
says `sendAlert()`. No keyword overlap, same idea. This is the **vocabulary
gap**, and it is what the whole project is aimed at.

## What this does

**1. Traces to AST nodes, not files.** Existing tools point at
`TourGuide.java`, a 600-line file. This points at
`TourGuide.findNearbyAttractions()` at lines 142–171. Each method, constructor,
and class is independently retrievable.

**2. Runs bidirectionally, and flags orphans.** As well as requirement → code, it
runs code → requirement and flags nodes that *no* requirement appears to claim —
dead code, undocumented features, or scope that crept in unrecorded. No standard
traceability toolkit reports them.

**3. Explains its traces.** Each link comes with a natural-language argument for
why that method satisfies that requirement, grounded in specific identifiers. A
ranked list of scores is not reviewable by a human; an argument is.

### How it works

The central trick is how code is represented. Raw source is a poor embedding
input — mostly syntax, in a vocabulary no English sentence model understands. So
instead of embedding source, we synthesise a *pseudo-English document* per node
from: the node name split on camelCase (`dispatchEvent` → "dispatch event"), the
signature including parameter names, attached Javadoc, body identifiers (also
split), and the enclosing class name.

**Identifier splitting is the highest-impact step in the pipeline.** It is what
bridges *"notify the user"* ↔ `sendAlert()`, and why a general-purpose sentence
model works here without a code-specific one.

Nodes are then scored against each requirement:

```
score = α · cosine(requirement, node_document) + β · jaccard(req_tokens, node_identifiers)
```

α weights the semantic signal, β the lexical one. The baseline starts at α=1,
β=0; adding β is a measured ablation, not a tuning exercise.

**Nothing is trained.** The embedding model (`all-MiniLM-L6-v2`) is pre-trained
and frozen — no training loop, no gradients, no GPU. With 58 requirements and
308 links there is nowhere near enough data to fine-tune without overfitting. The
accuracy work lives in text preparation, not in the model.

## Quickstart

> Day-to-day operation, tuning, and troubleshooting: **[docs/OPERATING.md](docs/OPERATING.md)**.

Requires **Python 3.13** and **git**. On Windows use the python.org interpreter
explicitly — bare `python` often resolves to the Store build, whose sandbox
breaks `torch` with a cryptic `WinError 126`.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on Unix
python -m pip install -r requirements.txt
python spikes/spike_treesitter.py    # expect: "OK - tree-sitter works, proceed"
```

`data/` is gitignored — the corpus is not redistributed here (see
[Dataset & attribution](#dataset--attribution)). Fetch it once:

```bash
git clone https://github.com/tobhey/finegrained-traceability.git ../finegrained-traceability
mkdir -p data && cp -r ../finegrained-traceability/datasets/etour data/
```

### Running

```bash
python -m scripts.run_demo        # the demo -- offline, ~1.2s
python -m scripts.run_ablation    # full evaluation, writes results/
python -m scripts.bench_latency   # interactive-latency benchmark
pytest                            # tests -- offline, no model, ~1.3s
pytest -m slow                    # + real-model integration tests
```

The first run downloads the model (~80 MB) into `models/`. Everything after is
fully offline.

## Results

Measured on eTour: 58 requirements, 1210 AST nodes across 116 files, 308 gold
links. Each row changes exactly one variable from the rows above it, so any gain
is attributable to a specific cause rather than to "the system".

| Run | Representation | Granularity | Isolates | MAP | P@5 | R@10 |
|-----|----------------|-------------|----------|-----|-----|------|
| B0 | TF-IDF | file | classic baseline | 0.233 | 0.263 | 0.398 |
| B1 | TF-IDF | AST node | does node granularity alone help? | 0.263 | 0.298 | 0.409 |
| E0 | embeddings | file | does semantics alone help? | 0.366 | 0.393 | 0.516 |
| E1 | embeddings | AST node | **our core method** | **0.409** | 0.407 | 0.556 |
| E2 | E1 + query expansion | AST node | does requirement rewriting help? | 0.406 | 0.418 | **0.600** |
| E3 | E2 + identifier overlap | AST node | does lexical signal add on top? | 0.405 | **0.432** | 0.598 |

**B0 → E1 is +0.176 MAP, a 76% relative improvement.** B1 and E0 are what make
that defensible: they separately rule out "the gain is just smaller chunks" and
"the gain is just embeddings".

The decomposition is the interesting part — granularity alone (B0→B1) is
**+0.030**, semantics alone (B0→E0) is **+0.133**, both together (B0→E1) is
**+0.176**. But 0.030 + 0.133 = 0.163, so the two effects are **more than
additive**: finer granularity gives the embedding model a cleaner unit to match
against, making the techniques complementary rather than redundant.

**E2 and E3 are honest negatives on the headline metric.** Both lose ~0.004 MAP
against E1 while winning elsewhere — E2 the best recall (R@10 0.600), E3 the best
precision (P@5 0.432). Query expansion and lexical overlap help find and rank
links, but neither improves the ranked-order quality MAP measures. Reported as
measured, not filtered to the flattering subset. (Note E2's "query expansion" is
a mechanical stripper for use-case boilerplate identical across all 58
requirements, not LLM rewriting — see `retrieve/query_expansion.py`.)

### Fair-comparison note

Node-level runs retrieve a deep pool (20× the evaluated *k*), aggregate to file
level, then truncate to exactly *k* files — the same number file-level runs get.
Without this, 10 retrieved nodes collapse into only ~5.8 distinct files and
node-level runs are silently penalised on recall for reasons unrelated to
retrieval quality. See `NODE_FETCH_MULTIPLIER` in [ablation.py](src/eval/ablation.py).

## Editor integration

The ablation answers *"is it accurate?"*. `python -m scripts.bench_latency`
answers *"is it deployable?"* — measured on eTour:

| | Cost | Budget |
|---|---|---|
| Cold start (once, at server boot) | ~3.5 s (92% model loading) | — |
| Requirement → ranked methods | **0.25 ms** | 100 ms |
| Method → ranked requirements | **0.02 ms** | 100 ms |
| Orphan scan, whole corpus | **0.34 ms** | 100 ms |
| New free-text query (embed + search) | **6.2 ms** | 100 ms |
| Re-index one edited file | **46 ms** | 100 ms |

100 ms is the threshold below which a response is perceived as instantaneous.
Every interactive path is inside it; boot is not and needn't be, since it is paid
once behind the editor's own startup. A full corpus rebuild is 2.6 s, so
per-file incremental re-indexing is ~57× cheaper — that is what makes live
re-indexing viable, and why the embedding cache is keyed **per node** rather than
per corpus.

`python -m scripts.mcp_server` exposes retrieval over the **Model Context
Protocol**, so one server reaches every MCP-speaking editor — Claude Code,
Cursor, Zed, Windsurf, Claude Desktop — rather than needing a VSCode extension
(which would miss Zed) plus a native Zed extension in Rust. Requires
`pip install mcp`; nothing else in the project imports it. Tools exposed:
`trace_requirement`, `search_code`, `whose_requirement`, `find_orphans`,
`justify_link`. Every call first re-indexes any file whose mtime moved (~9 ms to
check), so results never go stale — polling on the read path rather than a
filesystem watcher, which cannot miss an event.

### Running on your own repository

Gold links are an **evaluation** input, not a retrieval one — nothing in
`parse/`, `index/`, `retrieve/` or `justify/` reads them. Any directory with
`req/*.txt` and `code/**.java` therefore works, with or without an answer key:

```bash
REQ2CODE_DATA_DIR=/path/to/your/project python -m scripts.mcp_server
```

Without gold, tracing, orphan detection, and justification behave identically;
you simply get no accuracy numbers, because there is nothing to score against.
Strict validation of the documented eTour answer-key shape stays on for the
bundled corpus, so the published figures keep their guard rails.

## Limitations

Stated up front, because a prototype that hides its caveats is worth less than
one that names them.

- **Evaluation granularity ≠ retrieval granularity.** eTour gold links map
  requirements to *files*; we retrieve *methods*. Node scores are therefore
  max-aggregated to file level for scoring (a file scores as well as its best
  node), keeping numbers comparable with the baseline and published results.
  Node-level output is reported qualitatively, in the demo. This is a limitation
  of the evaluation, not the method — and the absence of node-level gold data is
  precisely why finer-grained traceability is under-studied.
- **One dataset, one language.** English requirements, Java code. iTrust is
  planned as a second dataset; nothing here is yet shown to generalise.
- **Small corpus.** ~58 requirements, ~116 artifacts, ~308 links. Enough to
  compare configurations, too small for claims about industrial codebases.
- **The orphan threshold is uncalibrated.** The 0.30 default flags 311 of 995
  methods (31%) — far too many to review. The 5th percentile of the observed
  distribution (0.17) flags 49 (5%), which is reviewable, but that is an
  observation rather than a principled cutoff. The demo prints the full
  distribution so a reader can pick their own. Calibrating it is open work.
- **Most orphans are boring.** In any real codebase most unclaimed nodes are
  getters, logging, and framework glue that legitimately implement no
  requirement — eTour's most-orphaned method is `getFont()`. The claim is that
  this surfaces a small reviewable set, not that everything flagged is a defect.
- **One requirement has no gold links.** eTour ships 58 use cases but only 57
  appear in the answer set — UC37 ("Logout") was never linked by the original
  annotators. It is excluded from MAP rather than scored 0.0, which would drag
  every configuration down by the same constant and break comparability.
- **Justifications are not yet evaluated.** They are generated and cached, but
  scoring them against human rationale is future work. The committed cache was
  authored by Claude in the session that built the pipeline rather than through
  the API script; each entry records its own provenance in a `model` field.
- **Italian-language datasets excluded.** SMOS, eAnci, and Albergate were
  originally Italian; translation artifacts would confound the vocabulary-gap
  analysis the method rests on.

## Dataset & attribution

Uses the **eTour** dataset, obtained via the
[finegrained-traceability](https://github.com/tobhey/finegrained-traceability)
(FTLR) repository by Tobias Hey et al. eTour originates with the **Center of
Excellence for Software & Systems Traceability (CoEST)**. Full credit for the
corpus belongs to its original authors and to the FTLR authors for the cleaned,
packaged form.

> **We use their data only — never their code.** FTLR is **GPL-3.0**; this
> project is **Apache-2.0**. Copying their source here would create a license
> conflict, so we do not. `data/` is gitignored, so no part of their corpus
> enters this repository's history.

See [NOTICE](NOTICE) for the full attribution statement.

## Project layout

```
src/
  contracts.py   ← frozen data contracts; everything depends on these
  ingest/        requirements loader, repo walker
  parse/         tree-sitter → CodeNode
  index/         node-document builder, per-node embedding cache, vector store
  retrieve/      req→code, code→req, orphans, hybrid scorer, query expansion
  justify/       LLM prompt + committed cache/
  eval/          gold loader, metrics, TF-IDF baseline, ablation runner
  pipeline.py    corpus loading + incremental re-index
scripts/         run_demo, run_ablation, bench_latency, mcp_server, snapshot_results
spikes/          throwaway learning scripts (not imported by src/)
tests/
```

`src/contracts.py` defines `Requirement`, `CodeNode`, and the results CSV schema.
These are frozen by agreement between both authors: freezing the interface is
what lets the two halves of the project be built in parallel without blocking on
each other. It is also why the retrieval engine and the presentation layer were
never coupled — the MCP server is a client of that contract, not of internals.

## Non-functional requirements

- **Offline** — models and LLM outputs cached locally; no network calls at demo
  or serve time (the MCP server pins `HF_HUB_OFFLINE`, which also cuts boot from
  15 s to 3.5 s)
- **Reproducible** — pinned dependencies, fixed seeds, single entry-point scripts
- **Fast** — demo under 60s; every interactive query under 100ms
- **Traceable** — every number maps to a committed script and a logged config

## License

Apache-2.0. See [LICENSE](LICENSE).
