# req2code for VS Code

Map plain-English requirements to the methods that implement them — live, in any
repository, fully offline.

The extension is a **thin client**. Every answer comes from
`scripts/mcp_server.py`, the same engine Claude Code, Cursor and Zed talk to.
Nothing here parses source, embeds text, or ranks anything; if it did, the editor
and the AI clients could disagree about the same repository.

---

## Install

**Prerequisite: a working engine.** From your req2code checkout:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install mcp
python -m scripts.req2code --path . index
```

That last command must print an index summary. The first run downloads the
model (~80 MB) into `models/`; everything after is offline. **If it does not
work in the terminal, the extension cannot make it work.**

**Then install the extension:**

```bash
python editors/vscode/build_vsix.py
code --install-extension editors/vscode/req2code-0.1.0.vsix
```

No `npm`, no `vsce`, no build step — the extension is plain JavaScript with zero
dependencies, and `build_vsix.py` just zips it.

<details>
<summary>Alternative: copy the folder</summary>

Copy `editors/vscode/req2code` into `~/.vscode/extensions/req2code.req2code-0.1.0`
(`%USERPROFILE%\.vscode\extensions\...` on Windows) and **fully restart VS Code**
— it caches the extension list, so a window reload is not enough.
</details>

<details>
<summary>Alternative: run it from source (for developing the extension)</summary>

Open `editors/vscode/req2code` as its own VS Code window and press **F5**. That
launches an Extension Development Host with the extension loaded, and changes
take effect on reload without reinstalling.
</details>

**To remove it:** `code --uninstall-extension req2code.req2code`

---

## Point it at a project

Two roots are involved and mixing them up is the one thing that reliably goes
wrong:

- the **engine path** — your req2code checkout, the folder with `scripts/`
- the **workspace** — the repository you want traced, whatever you have open

Set the engine path once, in Settings (`Ctrl+,` → search "req2code"), or in
`settings.json`:

```json
{
  "req2code.enginePath": "C:\\Users\\you\\Desktop\\project\\req2code"
}
```

If the workspace you have open *is* the req2code checkout, it is detected
automatically and you can skip this.

Then open any repository. The engine starts on its own and indexes the workspace.
First start takes a few seconds (loading the model); after that it stays warm.

---

## The panel

Click the req2code icon in the activity bar. The four tabs are the four questions
the tool answers, in the order you would ask them.

### Trace — requirement → code

Type what the system should do and press **Trace & record**:

> the system shall notify the traveller about attractions located nearby

You get a ranked list of methods with scores and exact line ranges. **Click any
result to jump straight to it.** The bar under each row shows score strength on a
fixed scale, so a list of weak matches looks weak rather than being normalised to
look confident.

- **Trace & record** adds the requirement to the project's set, so it counts for
  orphan detection and the Method tab. This is the primary path.
- **Search only** is a throwaway query that changes nothing.

`Ctrl+Enter` in the box is the same as Trace & record.

Requirements are appended to `.req2code/requirements.jsonl` in the workspace —
local, gitignored, never leaves the machine. On a real project nobody has a
folder of numbered use-case documents, so the requirement set is built by asking.

### Method — code → requirement

Follows your cursor. Put the caret inside any method and this tab shows which
requirements claim it, ranked. If the best score is below the threshold, it says
**unclaimed** — the same number as orphan detection, read as a different
question. Click a requirement to re-trace it.

### Orphans — code nothing asks for

Methods no stated requirement claims: dead code, undocumented features, or
plumbing. Drag the threshold and rescan.

The score distribution is shown alongside the list on purpose. The 0.30 default
is **not** a calibrated result, and a bare list invites reading it as one — the
percentiles are what let you pick a defensible cutoff for your repository.

Expect most orphans to be boring. The claim is that this surfaces a small
reviewable set, not that everything flagged is a defect.

### Requirements — the session log

Everything stated so far. Click an id to re-trace it, `×` to forget it.

---

## Inline labels

Every method gets a CodeLens above it naming its best-matching requirement and
score, or marking it unclaimed. The absence of a requirement is the finding, so
it is labelled rather than left blank.

One engine call covers a whole file, not one per method — scrolling a 600-line
file would otherwise be thirty round trips. Toggle with
**req2code: Toggle inline requirement labels**, or
`"req2code.codeLens.enabled": false`.

---

## Status

The status bar shows engine state and index size. The panel header shows the
same plus the language breakdown and git head, and flashes when the index
changes underneath you.

Watch it while you work: edit a file and the node count moves; switch branches
and the map follows. That is the live claim, visible.

| Dot | Meaning |
|---|---|
| grey | engine stopped |
| amber, pulsing | starting — loading the model and indexing |
| green | ready |
| red | error — click **log** for the engine's own output |

**When something is wrong, click `log`.** The engine's stderr goes there
verbatim, and it is the only place a bad interpreter or a missing dependency is
actually explained.

---

## Settings

| Setting | Default | |
|---|---|---|
| `req2code.enginePath` | *(auto)* | Your req2code checkout. Required unless the workspace *is* the checkout. |
| `req2code.pythonPath` | *(auto)* | Interpreter. Defaults to `.venv` inside the engine path, then `python`. |
| `req2code.orphanThreshold` | `0.3` | Unclaimed cutoff. Uncalibrated — read it against the distribution. |
| `req2code.topK` | `20` | Results per trace. |
| `req2code.codeLens.enabled` | `true` | Inline requirement labels. |
| `req2code.statusPollSeconds` | `4` | Status refresh. Each poll also re-syncs the index with the repository. |
| `req2code.autoStart` | `true` | Start the engine when a workspace opens. |

---

## Troubleshooting

**"engine path not set"** — set `req2code.enginePath` to the folder containing
`scripts/mcp_server.py`.

**"could not start python"** — set `req2code.pythonPath` to the interpreter with
req2code's dependencies, usually `<enginePath>/.venv/Scripts/python.exe`.

**Engine exits immediately** — click `log`. Almost always `ModuleNotFoundError:
No module named 'mcp'` (run `pip install mcp`) or a missing torch, meaning the
wrong interpreter.

**Everything is an orphan** — correct, and expected at the start. Orphans are
scored against the requirements *you* have stated, so state a few first.

**Results look wrong** — scores are honest about it; a bad trace usually scores
around 0.3 where a good one is above 0.5. There is no answer key for an arbitrary
repository, so retrieval quality here is demonstrated, not measured. See the
Limitations section in the root README.

---

## Offline

No network, no API keys, no telemetry. The model loads from `models/` with
HuggingFace pinned offline; git is invoked only through a read-only, remote-free
allowlist; the extension has no dependencies to fetch. Nothing in this path can
dial out, which is what lets it run on a codebase that is not allowed to leave
the machine.
