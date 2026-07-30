# req2code

**Requirement-to-Code Traceability via AST-Aware Retrieval**

Recovering the lost mapping between what software was supposed to do and the
code that actually does it — by matching meaning rather than keywords, and by
tracing to individual methods rather than whole files.

> **Status: working prototype.** The full pipeline runs end to end on eTour —
> parse → index → retrieve → evaluate → justify. `python -m scripts.run_demo`
> completes in ~1.2 s, fully offline. Numbers below are real.

---

## The problem

Every non-trivial software project starts with requirements — a specification of
what the system must do. Every project then spends years drifting away from
them. The link between requirement #37 and the code satisfying it lives in
someone's head, and then that person leaves.

This matters concretely when you need to answer:

- *"We're changing this requirement — what code is affected?"*
- *"What is this method for? Did anyone ask for it?"*
- *"Can we prove every safety requirement is implemented?"* (in regulated
  domains, an audit question with legal weight)

Recovering those links automatically is a long-standing research problem. The
classic approach — TF-IDF over requirement text vs. source text — has a known
ceiling, because requirements and code describe the same behaviour in almost
disjoint vocabulary. A requirement says *"the system shall notify the user"*;
the code says `sendAlert()`. No keyword overlap, same idea.

## What this does

Three things that distinguish it from standard traceability tooling:

**1. Traces to AST nodes, not files.**
Existing tools tell you `TourGuide.java` is relevant — a 600-line file. This
traces to `TourGuide.findNearbyAttractions()` at lines 142–171. Code is parsed
into an AST and each method, constructor, and class becomes an independently
retrievable unit, ranked by embedding similarity blended with structural signal.

**2. Runs bidirectionally, and flags orphans.**
As well as requirement → code, it runs code → requirement, then flags code nodes
that *no* requirement appears to claim. Those orphans are dead code,
undocumented features, or scope that crept in without ever being written down.
No standard traceability toolkit reports them.

**3. Explains its traces.**
Each proposed link comes with a natural-language justification of *why* that
method satisfies that requirement, grounded in specific identifiers in the code.
A ranked list of scores is not reviewable by a human; an argument is.

### How it works

The central trick is in how code is represented. Raw source is a poor embedding
input — mostly syntax, and written in a vocabulary no English sentence model
understands. So instead of embedding source, we build a *pseudo-English document*
for each AST node from:

- the node name, split on camelCase/snake_case (`dispatchEvent` → "dispatch event")
- the signature, including parameter names
- attached comments and Javadoc
- identifiers from the body, also split
- the enclosing class name

**Identifier splitting is the highest-impact step in the pipeline.** It is what
bridges *"the system shall notify the user"* ↔ `sendAlert()`, and it is why a
general-purpose sentence model works here without a code-specific one.

Nodes are then scored against each requirement:

```
score = α · cosine(requirement, node_document) + β · jaccard(req_tokens, node_identifiers)
```

α weights the semantic signal, β the lexical one. The baseline comparison starts
at α=1, β=0 (pure semantics); adding β is a measured ablation, not a tuning
exercise.

## Quickstart

Requires **Python 3.13** and **git**.

```bash
git clone https://github.com/<user>/req2code.git
cd req2code

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

python -m pip install -r requirements.txt
```

Check `python --version` reports 3.13 before creating the venv. If you *just*
installed Python, an already-open terminal will still have the old `PATH` — open
a new one, or call the interpreter by full path:
`%LOCALAPPDATA%\Programs\Python\Python313\python.exe -m venv .venv`.

Verify the install with the parser spike, which is the dependency most likely to
misbehave on a new machine:

```bash
python spikes/spike_treesitter.py    # expect: "OK - tree-sitter works, proceed"
```

### Fetching the dataset

`data/` is gitignored — the corpus is not redistributed with this repo (see
[Dataset & attribution](#dataset--attribution)). Fetch it once:

```bash
# Clone OUTSIDE this repository
cd ..
git clone https://github.com/tobhey/finegrained-traceability.git

# Copy only the eTour data back in
cd req2code
mkdir -p data
cp -r ../finegrained-traceability/datasets/etour data/
```

You should end up with `data/etour/` containing the requirement documents, the
Java source tree, and the gold answer set.

### Running

```bash
python -m scripts.run_demo        # the Review 1 demo — offline, ~1.2s
python -m scripts.run_ablation    # full evaluation, writes results/
pytest                            # tests
```

Optionally regenerate the LLM justifications (the only script that touches the
network — needs `pip install anthropic` and an API key):

```bash
python -m scripts.generate_justifications --dry-run
```

The first run downloads the sentence-transformer model (~80 MB) into `models/`.
Every subsequent run — including the demo — is fully offline.

## Results

Measured on eTour: 58 requirements, 1210 AST nodes across 116 files, 308 gold
links. Regenerate with `python -m scripts.run_ablation` (writes
`results/ablation.md` and `results/config.json`).

Each row changes exactly one variable from the rows above it, so any gain can be
attributed to a specific cause rather than to "the system".

| Run | Representation | Granularity | Isolates | MAP | P@5 | R@10 |
|-----|----------------|-------------|----------|-----|-----|------|
| B0 | TF-IDF | file | classic baseline | 0.233 | 0.263 | 0.398 |
| B1 | TF-IDF | AST node | does node granularity alone help? | 0.263 | 0.298 | 0.409 |
| E0 | embeddings | file | does semantics alone help? | 0.366 | 0.393 | 0.516 |
| E1 | embeddings | AST node | **our core method** | **0.409** | 0.407 | 0.556 |
| E2 | E1 + query expansion | AST node | does requirement rewriting help? | 0.406 | 0.418 | **0.600** |
| E3 | E2 + identifier overlap | AST node | does lexical signal add on top? | 0.405 | **0.432** | 0.598 |

**B0 → E1 is +0.176 MAP, a 76% relative improvement.** B1 and E0 are what make
that defensible: they separately rule out "the gain is just from smaller chunks"
and "the gain is just from embeddings".

The decomposition is the interesting part:

- node granularity alone (B0→B1): **+0.030**
- semantics alone (B0→E0): **+0.133**
- both together (B0→E1): **+0.176**

0.030 + 0.133 = 0.163, but the combination gives 0.176 — the two effects are
**more than additive**. Finer granularity gives the embedding model a cleaner
unit to match against, so the techniques are complementary rather than redundant.

**E2 and E3 are honest negatives on the headline metric.** Both lose ~0.004 MAP
against E1 while improving other columns: E2 gives the best recall (R@10 0.600 vs
0.556) and E3 the best precision (P@5 0.432 vs 0.407). Query expansion and lexical
overlap help find and rank links, but neither improves the ranked-order quality
MAP measures. Reported as measured, not filtered to the flattering subset.

### Fair-comparison note

Node-level runs retrieve a deep pool of nodes (20× the evaluated *k*), aggregate
to file level, and are then truncated to exactly *k* files — the same number the
file-level runs get. Without this, 10 retrieved nodes collapse into only ~5.8
distinct files, and node-level runs would be silently penalised on recall for
reasons unrelated to retrieval quality. See `NODE_FETCH_MULTIPLIER` in
[ablation.py](src/eval/ablation.py).

## Limitations

Stated up front, because a prototype that hides its caveats is worth less than
one that names them.

- **Evaluation granularity does not match retrieval granularity.** The eTour
  gold links map requirements to *files*, but we retrieve *methods*. We
  therefore aggregate node scores up to file level (a file scores as well as its
  best-matching node) and evaluate there, so the numbers stay comparable with
  the baseline and with published results. Node-level output is reported
  qualitatively, in the demo. This is a real limitation of the evaluation, not
  of the method — and the absence of node-level gold data is precisely why
  finer-grained traceability is under-studied.

- **One dataset, one language.** eTour only: English requirements, Java code.
  iTrust is planned as a second dataset to support any generalisation claim.
  Nothing here has been shown to transfer to another language.

- **Small corpus.** ~58 requirements, ~116 code artifacts, ~308 gold links.
  Large enough to compare configurations, too small for any claim about
  industrial-scale codebases.

- **The orphan threshold is uncalibrated.** The 0.30 default flags 311 of 995
  methods (31%) — far too many to review by hand. The 5th percentile of the
  observed score distribution (0.17) flags 49 (5%), which is reviewable, but that
  is an observation rather than a principled cutoff. The demo prints the full
  distribution so the reader can pick their own. Calibrating this properly is
  open work.

- **Most orphans are boring.** In any real codebase the majority of unclaimed
  nodes are getters, logging, and framework glue that legitimately implement no
  requirement — the most-orphaned method in eTour is `getFont()`. The claim is
  that this surfaces a small reviewable set, not that everything flagged is a
  defect.

- **One requirement has no gold links.** eTour ships 58 use cases but only 57
  appear in the answer set — UC37 ("Logout") was never linked by the original
  annotators. It is excluded from MAP rather than scored 0.0, which would drag
  every configuration down by the same constant and break comparability with
  published eTour results.

- **Justifications are not yet evaluated.** They are generated and cached, but
  scoring them against human rationale is future work. The committed cache was
  authored by Claude in the session that built this pipeline rather than through
  the API script; each entry records its own provenance in a `model` field, and
  `python -m scripts.generate_justifications` regenerates them through the API
  when credentials are available.

- **Italian-language datasets excluded.** SMOS, eAnci, and Albergate were
  originally Italian; translation artifacts would confound the vocabulary-gap
  analysis that the whole method rests on.

## Dataset & attribution

This project uses the **eTour** dataset, obtained via the
[finegrained-traceability](https://github.com/tobhey/finegrained-traceability)
(FTLR) repository by Tobias Hey et al.

eTour originates with the **Center of Excellence for Software & Systems
Traceability (CoEST)** and has been widely used in traceability research. Full
credit for the corpus belongs to its original authors and to the FTLR authors
for the cleaned, packaged form.

> **We use their data only — never their code.**
> The FTLR repository is licensed **GPL-3.0**; this project is **Apache-2.0**.
> Copying FTLR source into this repository would create a license conflict, so
> we do not do it. Reading their work for ideas is fine and normal; copying
> implementation is not. `data/` is gitignored so no part of their corpus enters
> this repository's history.

See [NOTICE](NOTICE) for the full attribution statement.

## Project layout

```
src/
  contracts.py   ← frozen data contracts; everything depends on these
  ingest/        requirements loader, repo walker
  parse/         tree-sitter → CodeNode
  index/         node-document builder, embedder, vector store
  retrieve/      req→code, code→req, orphans, hybrid scorer, query expansion
  justify/       LLM prompt + committed cache/
  eval/          gold loader, metrics, TF-IDF baseline, ablation runner
scripts/         run_demo.py, run_ablation.py
spikes/          throwaway learning scripts (not imported by src/)
tests/
```

`src/contracts.py` defines `Requirement`, `CodeNode`, and the results CSV
schema. These are frozen by agreement between both authors: freezing the
interface is what lets the two halves of the project be built in parallel
without blocking on each other.

## Non-functional requirements

- **Offline** — models and LLM outputs cached locally; the demo makes no network
  calls
- **Reproducible** — pinned dependencies, fixed seeds, single entry-point script
- **Fast** — prototype demo runs in under 60 seconds
- **Traceable** — every number in the report maps to a committed script and a
  logged config

## License

Apache-2.0. See [LICENSE](LICENSE).
