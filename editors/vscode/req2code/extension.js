"use strict";
/**
 * req2code for VS Code.
 *
 * WHAT THIS IS
 * ------------
 * A thin client. Every answer comes from `scripts/mcp_server.py`, which is the
 * same engine Claude Code and Cursor talk to. Nothing here parses source, embeds
 * text, or ranks anything -- if it did, the editor and the AI clients could
 * disagree about the same repository, which is the failure this architecture
 * exists to prevent.
 *
 * WHAT IT SHOWS
 * -------------
 *   Trace tab        state a requirement -> ranked methods, click to jump
 *   Method tab       follows the cursor: what does this method implement?
 *   Orphans tab      code no stated requirement claims, with the distribution
 *   Requirements tab the project's requirement set, retrace or forget
 *   Inline labels    the best-matching requirement above every method
 *   Status           engine state, index size, git head, live reindex ticker
 *
 * THE POINT OF THE LAYOUT
 * -----------------------
 * The four tabs are the four questions the research claims to answer, in the
 * order a person asks them. Trace is "where is this implemented", Method is the
 * reverse direction, Orphans is the unclaimed-code claim, Requirements is the
 * session log that makes the last two mean anything on a repository with no
 * corpus. Someone who clicks through them in order has seen the whole system
 * work, which is what makes this a demonstration rather than a viewer.
 */

const vscode = require("vscode");
const path = require("path");
const fs = require("fs");
const { Engine } = require("./engine");

let engine = null;
let panel = null;
let output = null;
let statusBar = null;
let codeLensProvider = null;
let pollTimer = null;

/** Last status payload, so the panel can re-render without a round trip. */
let lastStatus = null;

// ---------------------------------------------------------------------------
// Locating the engine
// ---------------------------------------------------------------------------

/**
 * Where the req2code Python lives. This is NOT the repository being traced --
 * they are different roots and conflating them is the first thing that goes
 * wrong when someone installs this.
 *
 * Order: the explicit setting, then the open workspace if it happens to be the
 * checkout (the dogfooding case, and the one that needs no configuration at
 * all).
 */
function resolveEnginePath() {
  const configured = vscode.workspace.getConfiguration("req2code").get("enginePath");
  if (configured) return configured;
  for (const folder of vscode.workspace.workspaceFolders || []) {
    const candidate = folder.uri.fsPath;
    if (fs.existsSync(path.join(candidate, "scripts", "mcp_server.py"))) {
      return candidate;
    }
  }
  return "";
}

function workspaceRoot() {
  const folders = vscode.workspace.workspaceFolders || [];
  return folders.length ? folders[0].uri.fsPath : "";
}

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

function activate(context) {
  output = vscode.window.createOutputChannel("req2code");
  context.subscriptions.push(output);

  statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBar.command = "req2code.focus";
  statusBar.text = "$(circle-outline) req2code";
  statusBar.tooltip = "req2code — click to open the traceability panel";
  statusBar.show();
  context.subscriptions.push(statusBar);

  panel = new PanelProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("req2code.panel", panel)
  );

  codeLensProvider = new RequirementCodeLensProvider();
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider({ scheme: "file" }, codeLensProvider)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("req2code.focus", () =>
      vscode.commands.executeCommand("req2code.panel.focus")
    ),
    vscode.commands.registerCommand("req2code.restart", () => restart()),
    vscode.commands.registerCommand("req2code.showOutput", () => output.show(true)),
    vscode.commands.registerCommand("req2code.trace", async () => {
      const text = await vscode.window.showInputBox({
        prompt: "Describe what the system should do",
        placeHolder: "the system shall notify the traveller about nearby attractions",
      });
      if (!text) return;
      await vscode.commands.executeCommand("req2code.panel.focus");
      panel.trace(text, true);
    }),
    vscode.commands.registerCommand("req2code.toggleCodeLens", async () => {
      const cfg = vscode.workspace.getConfiguration("req2code");
      const next = !cfg.get("codeLens.enabled");
      await cfg.update("codeLens.enabled", next, true);
      codeLensProvider.refresh();
      vscode.window.showInformationMessage(
        `req2code: inline requirement labels ${next ? "on" : "off"}.`
      );
    }),
    // Clicking a result opens the file at the exact line range. Registered as a
    // command rather than handled in the webview because a webview cannot open
    // an editor itself.
    vscode.commands.registerCommand("req2code.reveal", (file, startLine, endLine) =>
      reveal(file, startLine, endLine)
    )
  );

  // Live behaviour. Three triggers, each for a different kind of change:
  context.subscriptions.push(
    // the cursor moved -> which method are we in?
    vscode.window.onDidChangeTextEditorSelection((e) => panel.onCursor(e)),
    vscode.window.onDidChangeActiveTextEditor(() => panel.onCursor()),
    // a file was saved -> the engine will reindex on its next call, so drop the
    // per-file annotation cache and let the lenses re-ask
    vscode.workspace.onDidSaveTextDocument((doc) => {
      codeLensProvider.invalidate(doc.uri.fsPath);
      codeLensProvider.refresh();
      panel.onCursor();
    })
  );

  if (vscode.workspace.getConfiguration("req2code").get("autoStart")) {
    start();
  }
}

function deactivate() {
  if (pollTimer) clearInterval(pollTimer);
  if (engine) engine.stop();
}

// ---------------------------------------------------------------------------
// Engine lifecycle
// ---------------------------------------------------------------------------

async function start() {
  const enginePath = resolveEnginePath();
  const root = workspaceRoot();

  if (!root) {
    setStatus("error", "no folder open");
    return;
  }
  if (!enginePath) {
    setStatus("error", "engine path not set");
    const pick = await vscode.window.showWarningMessage(
      "req2code: set `req2code.enginePath` to your req2code checkout (the folder containing scripts/mcp_server.py).",
      "Open settings"
    );
    if (pick) {
      vscode.commands.executeCommand(
        "workbench.action.openSettings",
        "req2code.enginePath"
      );
    }
    return;
  }

  engine = new Engine({
    enginePath,
    workspaceRoot: root,
    pythonPath: vscode.workspace.getConfiguration("req2code").get("pythonPath"),
    log: (line) => output.appendLine(line),
    onState: (state) => {
      setStatus(state.status, state.detail);
      panel.postState();
    },
  });

  const ok = await engine.start();
  if (!ok) return;

  await pollStatus();
  const seconds =
    vscode.workspace.getConfiguration("req2code").get("statusPollSeconds") || 4;
  if (pollTimer) clearInterval(pollTimer);
  // Polling doubles as the liveness mechanism: every engine call runs
  // `Corpus.refresh()` first, so asking for status *is* what keeps the index in
  // step with the repository. See the note in scripts/mcp_server.py.
  pollTimer = setInterval(pollStatus, Math.max(1, seconds) * 1000);
}

async function restart() {
  if (pollTimer) clearInterval(pollTimer);
  if (engine) engine.stop();
  codeLensProvider.clear();
  lastStatus = null;
  await start();
}

async function pollStatus() {
  if (!engine || !engine.ready) return;
  try {
    const status = await engine.call("ui_status", {});
    const previous = lastStatus;
    lastStatus = status;
    // A changed node count means files were reindexed since the last look --
    // the visible proof that the map follows the repository.
    if (previous && previous.nodes !== status.nodes) {
      codeLensProvider.clear();
      codeLensProvider.refresh();
      panel.flash(
        `index updated · ${status.nodes} nodes (${status.nodes > previous.nodes ? "+" : ""}${status.nodes - previous.nodes})`
      );
    }
    setStatus("ready", "");
    panel.postStatus(status);
  } catch (err) {
    output.appendLine(`status poll failed: ${err.message}`);
  }
}

function setStatus(state, detail) {
  const icons = {
    stopped: "$(circle-outline)",
    starting: "$(loading~spin)",
    ready: "$(pass-filled)",
    error: "$(error)",
  };
  const icon = icons[state] || "$(circle-outline)";
  const size = lastStatus ? ` ${lastStatus.nodes} nodes` : "";
  statusBar.text = `${icon} req2code${state === "ready" ? size : ""}`;
  statusBar.tooltip =
    state === "ready"
      ? `req2code: ${lastStatus ? `${lastStatus.nodes} nodes in ${lastStatus.files} files, ${lastStatus.requirements.length} requirements` : "ready"}`
      : `req2code: ${state}${detail ? " — " + detail : ""}`;
}

/** Open a repo-relative file at a 1-based line range and select it. */
async function reveal(file, startLine, endLine) {
  const root = workspaceRoot();
  if (!root) return;
  const uri = vscode.Uri.file(path.join(root, file));
  try {
    const doc = await vscode.workspace.openTextDocument(uri);
    const start = Math.max(0, (startLine || 1) - 1);
    const end = Math.max(start, (endLine || startLine || 1) - 1);
    const range = new vscode.Range(start, 0, end, 0);
    await vscode.window.showTextDocument(doc, {
      selection: new vscode.Range(start, 0, start, 0),
      preserveFocus: false,
    });
    const editor = vscode.window.activeTextEditor;
    if (editor) editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
  } catch (err) {
    vscode.window.showErrorMessage(`req2code: cannot open ${file} — ${err.message}`);
  }
}

// ---------------------------------------------------------------------------
// Inline requirement labels
// ---------------------------------------------------------------------------

/**
 * A CodeLens above every declaration saying which requirement claims it.
 *
 * ONE ENGINE CALL PER FILE, NOT PER METHOD. `ui_file_map` returns the whole
 * file's mapping in a single matrix multiply; asking per method would mean
 * thirty round trips every time someone scrolls a 600-line file. The result is
 * cached per file path and dropped on save.
 */
/**
 * Suffixes the engine can parse, mirroring `SUPPORTED_SUFFIXES` in
 * `src/parse/languages.py`.
 *
 * Duplicated deliberately, and it is the only duplication in this extension.
 * The alternative is an engine call for every file the user opens -- README,
 * lockfile, log -- just to be told there is nothing in it. The list is stable
 * (it changes only when a language is added) and being wrong is cheap in both
 * directions: a missing suffix means no labels on that language, an extra one
 * means one wasted call that returns an empty map.
 */
const PARSEABLE = new Set([
  ".c", ".cc", ".cpp", ".cs", ".cxx", ".go", ".h", ".hh",
  ".hpp", ".hxx", ".java", ".py", ".pyi", ".rs",
]);

class RequirementCodeLensProvider {
  constructor() {
    this.cache = new Map();
    this.emitter = new vscode.EventEmitter();
    this.onDidChangeCodeLenses = this.emitter.event;
  }

  refresh() {
    this.emitter.fire();
  }

  clear() {
    this.cache.clear();
  }

  invalidate(fsPath) {
    this.cache.delete(fsPath);
  }

  async provideCodeLenses(document) {
    const cfg = vscode.workspace.getConfiguration("req2code");
    if (!cfg.get("codeLens.enabled")) return [];
    if (!engine || !engine.ready) return [];

    const root = workspaceRoot();
    if (!root || !document.uri.fsPath.startsWith(root)) return [];
    if (!PARSEABLE.has(path.extname(document.uri.fsPath).toLowerCase())) return [];

    const rel = path
      .relative(root, document.uri.fsPath)
      .split(path.sep)
      .join("/");

    let map = this.cache.get(document.uri.fsPath);
    if (!map) {
      try {
        map = await engine.call("ui_file_map", { file: rel, top_k: 1 });
        this.cache.set(document.uri.fsPath, map);
      } catch (err) {
        output.appendLine(`file map failed for ${rel}: ${err.message}`);
        return [];
      }
    }
    if (!map || !map.nodes || !map.nodes.length) return [];

    const threshold = cfg.get("orphanThreshold");
    const lenses = [];
    for (const node of map.nodes) {
      if (node.kind !== "method" && node.kind !== "constructor") continue;
      const line = Math.max(0, node.start_line - 1);
      const range = new vscode.Range(line, 0, line, 0);
      const top = node.requirements && node.requirements[0];
      if (top && node.best_score >= threshold) {
        lenses.push(
          new vscode.CodeLens(range, {
            title: `$(link) ${top.req_id} · ${node.best_score.toFixed(2)} — ${top.title}`,
            tooltip: top.text,
            command: "req2code.focus",
          })
        );
      } else {
        // Saying nothing here would be the safe choice and the wrong one: the
        // absence of a requirement is the finding.
        lenses.push(
          new vscode.CodeLens(range, {
            title: `$(circle-slash) unclaimed · best ${(node.best_score || 0).toFixed(2)}`,
            tooltip:
              "No stated requirement claims this method. It may be plumbing, dead code, or an undocumented feature.",
            command: "req2code.focus",
          })
        );
      }
    }
    return lenses;
  }
}

// ---------------------------------------------------------------------------
// The panel
// ---------------------------------------------------------------------------

class PanelProvider {
  constructor(context) {
    this.context = context;
    this.view = null;
    this.cursorToken = 0;
  }

  resolveWebviewView(view) {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.join(this.context.extensionPath, "media"))],
    };
    view.webview.html = this.html(view.webview);
    view.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
    this.postState();
    if (lastStatus) this.postStatus(lastStatus);
    this.onCursor();
  }

  post(message) {
    if (this.view) this.view.webview.postMessage(message);
  }

  postState() {
    this.post({ type: "state", state: engine ? engine.state : { status: "stopped" } });
  }

  postStatus(status) {
    this.post({ type: "status", status });
  }

  flash(text) {
    this.post({ type: "flash", text });
  }

  async onMessage(msg) {
    try {
      switch (msg.type) {
        case "trace":
          return this.trace(msg.text, msg.log);
        case "retrace": {
          const cfg = vscode.workspace.getConfiguration("req2code");
          const res = await engine.call("ui_retrace", {
            req_id: msg.req_id,
            top_k: cfg.get("topK") || 20,
          });
          return this.post({ type: "trace", result: res });
        }
        case "forget": {
          await engine.call("ui_forget", { req_id: msg.req_id });
          codeLensProvider.clear();
          codeLensProvider.refresh();
          this.post({ type: "orphansStale" });
          return pollStatus();
        }
        case "orphans":
          return this.orphans(msg.threshold);
        case "reveal":
          return reveal(msg.file, msg.start_line, msg.end_line);
        case "restart":
          return restart();
        case "showOutput":
          return output.show(true);
        case "ready":
          this.postState();
          if (lastStatus) this.postStatus(lastStatus);
          return;
      }
    } catch (err) {
      this.post({ type: "error", message: err.message });
    }
  }

  async trace(text, log) {
    if (!engine || !engine.ready) {
      return this.post({ type: "error", message: "engine is not running" });
    }
    this.post({ type: "busy", tab: "trace" });
    try {
      const cfg = vscode.workspace.getConfiguration("req2code");
      const result = await engine.call("ui_trace", {
        text,
        top_k: cfg.get("topK") || 20,
        log: !!log,
      });
      this.post({ type: "trace", result });
      if (log) {
        // A new requirement changes every method's best match, so every cached
        // annotation AND the whole orphan ranking are now wrong. Missing the
        // orphan half is the bug that makes a live demo look broken: the
        // requirement records, the score really moves, and the panel keeps
        // showing the previous requirement set's figures.
        codeLensProvider.clear();
        codeLensProvider.refresh();
        this.post({ type: "orphansStale" });
        pollStatus();
      }
    } catch (err) {
      this.post({ type: "error", message: err.message });
    }
  }

  async orphans(threshold) {
    if (!engine || !engine.ready) return;
    this.post({ type: "busy", tab: "orphans" });
    try {
      const result = await engine.call("ui_orphans", {
        threshold:
          typeof threshold === "number"
            ? threshold
            : vscode.workspace.getConfiguration("req2code").get("orphanThreshold"),
        limit: 200,
      });
      this.post({ type: "orphans", result });
    } catch (err) {
      this.post({ type: "error", message: err.message });
    }
  }

  /**
   * The cursor moved: show what the method under it implements.
   *
   * Answered from the cached per-file map rather than a `whose_requirement`
   * call, so moving the caret costs nothing after the first look at a file.
   * `cursorToken` discards results that arrive after the user has moved on --
   * without it, fast cursor movement makes the panel flicker between answers.
   */
  async onCursor() {
    const editor = vscode.window.activeTextEditor;
    if (!this.view || !engine || !engine.ready || !editor) return;
    const root = workspaceRoot();
    if (!root || !editor.document.uri.fsPath.startsWith(root)) {
      return this.post({ type: "method", node: null });
    }

    if (!PARSEABLE.has(path.extname(editor.document.uri.fsPath).toLowerCase())) {
      return this.post({ type: "method", node: null });
    }

    const token = ++this.cursorToken;
    const rel = path
      .relative(root, editor.document.uri.fsPath)
      .split(path.sep)
      .join("/");
    const line = editor.selection.active.line + 1;

    let map = codeLensProvider.cache.get(editor.document.uri.fsPath);
    if (!map) {
      try {
        map = await engine.call("ui_file_map", { file: rel, top_k: 5 });
        codeLensProvider.cache.set(editor.document.uri.fsPath, map);
      } catch (err) {
        return;
      }
    }
    if (token !== this.cursorToken) return;

    // Innermost containing declaration, matching retrieve/locate.py.
    let best = null;
    for (const node of (map && map.nodes) || []) {
      if (node.start_line <= line && line <= node.end_line) {
        if (!best || node.end_line - node.start_line < best.end_line - best.start_line) {
          best = node;
        }
      }
    }
    this.post({
      type: "method",
      node: best,
      file: rel,
      threshold: vscode.workspace.getConfiguration("req2code").get("orphanThreshold"),
    });
  }

  html(webview) {
    const nonce = String(Math.random()).slice(2);
    const uri = (name) =>
      webview.asWebviewUri(
        vscode.Uri.file(path.join(this.context.extensionPath, "media", name))
      );
    const template = fs.readFileSync(
      path.join(this.context.extensionPath, "media", "panel.html"),
      "utf8"
    );
    return template
      .replace(/\{\{cspSource\}\}/g, webview.cspSource)
      .replace(/\{\{nonce\}\}/g, nonce)
      .replace(/\{\{styleUri\}\}/g, uri("panel.css"))
      .replace(/\{\{scriptUri\}\}/g, uri("panel.js"));
  }
}

module.exports = { activate, deactivate };
