"use strict";
/**
 * Panel rendering. No framework, no build step, no dependencies -- the whole
 * extension installs by copying a folder, and a bundler would end that.
 *
 * All DOM is built with createElement and textContent rather than innerHTML.
 * That is not ceremony: every string here is either a requirement the user
 * typed or an identifier read out of their source code, and both would happily
 * carry a `<script>` tag into a webview that has script execution enabled.
 */

const vscode = acquireVsCodeApi();

const $ = (id) => document.getElementById(id);

let currentStatus = null;
let flashTimer = null;

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

const TABS = ["trace", "method", "orphans", "reqs"];

function showTab(name) {
  for (const tab of TABS) {
    $("panel-" + tab).hidden = tab !== name;
  }
  document.querySelectorAll(".tab").forEach((el) => {
    el.classList.toggle("tab-active", el.dataset.tab === name);
  });
  // The orphan scan is the one view that costs a round trip to fill, so it is
  // fetched on arrival rather than kept warm.
  if (name === "orphans" && !$("orphansList").childElementCount) {
    requestOrphans();
  }
}

document.querySelectorAll(".tab").forEach((el) => {
  el.addEventListener("click", () => showTab(el.dataset.tab));
});

// ---------------------------------------------------------------------------
// Small builders
// ---------------------------------------------------------------------------

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function reveal(file, startLine, endLine) {
  vscode.postMessage({ type: "reveal", file, start_line: startLine, end_line: endLine });
}

/**
 * One retrieved method, as a clickable row.
 *
 * The bar width is the score mapped through a fixed 0..0.8 range rather than
 * normalised against the top hit. Normalising would make the best result a full
 * bar every time, including when the best result scores 0.12 and means nothing
 * -- the bar has to be able to say "all of these are weak".
 */
function hitRow(hit) {
  const item = document.createElement("li");
  const button = el("button", "hit");
  button.type = "button";

  const top = el("div", "hit-top");
  top.appendChild(el("span", "rank", hit.rank != null ? hit.rank + "." : ""));

  const symbol = el("span", "symbol");
  if (hit.enclosing) {
    symbol.appendChild(el("span", "enclosing", hit.enclosing + "."));
  }
  symbol.appendChild(el("span", "name", hit.name + "()"));
  if (hit.gold) symbol.appendChild(el("span", "gold", "  gold"));
  top.appendChild(symbol);
  top.appendChild(el("span", "score", hit.score.toFixed(3)));
  button.appendChild(top);

  button.appendChild(
    el("div", "hit-loc", `${hit.file}:${hit.start_line}-${hit.end_line}`)
  );

  const bar = el("div", "bar");
  bar.style.width = Math.max(1, Math.min(100, (hit.score / 0.8) * 100)) + "%";
  button.appendChild(bar);

  button.addEventListener("click", () =>
    reveal(hit.file, hit.start_line, hit.end_line)
  );
  item.appendChild(button);
  return item;
}

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

function renderState(state) {
  const dot = $("dot");
  dot.className = "dot dot-" + (state.status || "stopped");
  const labels = {
    stopped: "engine stopped",
    starting: "starting engine…",
    ready: "engine ready",
    error: "engine error",
  };
  $("statusText").textContent = labels[state.status] || state.status;
  if (state.status === "error" || state.status === "starting") {
    $("statusDetail").textContent = state.detail || "";
  }
}

function renderStatus(status) {
  currentStatus = status;
  const langs = Object.entries(status.languages || {})
    .map(([name, count]) => `${name} ${count}`)
    .join(" · ");
  const git = status.git && status.git.tracked
    ? `git ${String(status.git.head || "no commits").slice(0, 8)}` +
      (status.git.dirty ? ` · ${status.git.dirty} dirty` : " · clean")
    : "not a git repo — polling file times";

  $("statusDetail").textContent =
    `${status.nodes} nodes · ${status.files} files · ` +
    `${status.requirements.length} requirement${status.requirements.length === 1 ? "" : "s"}\n` +
    `${langs || "nothing parsed"}\n${git}`;

  renderRequirements(status.requirements, status.read_only);
}

function flash(text) {
  const box = $("flash");
  box.textContent = text;
  box.hidden = false;
  if (flashTimer) clearTimeout(flashTimer);
  flashTimer = setTimeout(() => {
    box.hidden = true;
  }, 4000);
}

// ---------------------------------------------------------------------------
// Trace
// ---------------------------------------------------------------------------

function submit(log) {
  const text = $("query").value.trim();
  if (!text) return;
  $("traceHead").textContent = "tracing…";
  $("traceList").replaceChildren();
  vscode.postMessage({ type: "trace", text, log });
}

$("stateBtn").addEventListener("click", () => submit(true));
$("searchBtn").addEventListener("click", () => submit(false));
$("query").addEventListener("keydown", (event) => {
  // Ctrl/Cmd+Enter records; plain Enter would fight with writing a multi-line
  // requirement, which people do.
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") submit(true);
});

function renderTrace(result) {
  const head = $("traceHead");
  const list = $("traceList");
  list.replaceChildren();

  if (result.error) {
    head.textContent = result.error;
    return;
  }
  if (!result.hits.length) {
    head.textContent = "No code indexed to match against.";
    return;
  }

  head.replaceChildren();
  if (result.req_id) {
    const line = el("div");
    line.appendChild(el("span", "mono", result.req_id));
    line.appendChild(
      document.createTextNode(
        result.created === false
          ? " — already in the requirement set"
          : " — recorded in the requirement set"
      )
    );
    head.appendChild(line);
  } else {
    head.appendChild(el("div", null, "Throwaway query — not recorded."));
  }
  head.appendChild(el("div", null, `${result.hits.length} methods, best first.`));

  for (const hit of result.hits) list.appendChild(hitRow(hit));
  showTab("trace");
}

// ---------------------------------------------------------------------------
// Method (cursor-following)
// ---------------------------------------------------------------------------

function renderMethod(message) {
  const body = $("methodBody");
  body.replaceChildren();
  const node = message.node;

  if (!node) {
    body.appendChild(
      el("p", "empty", "Put the cursor inside a method to see what it implements.")
    );
    return;
  }

  const name = el("div", "method-name");
  if (node.enclosing) name.appendChild(el("span", "enclosing", node.enclosing + "."));
  name.appendChild(el("span", null, node.name + "()"));
  body.appendChild(name);
  body.appendChild(
    el("div", "method-loc", `${message.file}:${node.start_line}-${node.end_line}`)
  );

  if (!node.requirements || !node.requirements.length) {
    body.appendChild(
      el(
        "p",
        "empty",
        "No requirements have been stated yet, so there is nothing to rank this against."
      )
    );
    return;
  }

  const orphan = (node.best_score || 0) < (message.threshold || 0.3);
  if (orphan) {
    body.appendChild(
      el(
        "div",
        "badge",
        `unclaimed — best match only ${(node.best_score || 0).toFixed(3)}`
      )
    );
  }

  const list = el("div");
  list.style.marginTop = "10px";
  for (const req of node.requirements) {
    const row = el("div", "req-hit");
    const head = el("div");
    head.appendChild(el("span", "mono", req.score.toFixed(3) + "  "));
    head.appendChild(el("span", "req-id", req.req_id));
    row.appendChild(head);
    row.appendChild(el("div", "req-text", req.title));
    row.addEventListener("click", () =>
      vscode.postMessage({ type: "retrace", req_id: req.req_id })
    );
    list.appendChild(row);
  }
  body.appendChild(list);
}

// ---------------------------------------------------------------------------
// Orphans
// ---------------------------------------------------------------------------

const slider = $("threshold");
slider.addEventListener("input", () => {
  $("thresholdValue").textContent = Number(slider.value).toFixed(2);
});
slider.addEventListener("change", requestOrphans);
$("orphansBtn").addEventListener("click", requestOrphans);

function requestOrphans() {
  $("orphansHead").textContent = "scanning…";
  $("orphansList").replaceChildren();
  vscode.postMessage({ type: "orphans", threshold: Number(slider.value) });
}

function renderOrphans(result) {
  const head = $("orphansHead");
  const list = $("orphansList");
  head.replaceChildren();
  list.replaceChildren();

  if (result.reason) {
    head.textContent = `Not meaningful yet: ${result.reason}.`;
    return;
  }

  const share = result.methods ? Math.round((result.flagged / result.methods) * 100) : 0;
  head.appendChild(
    el(
      "div",
      null,
      `${result.flagged} of ${result.methods} methods (${share}%) score below ${result.threshold.toFixed(2)}.`
    )
  );

  // The distribution ships with the list because the threshold is uncalibrated
  // and a bare list invites reading the cutoff as a result.
  const dist = result.distribution || {};
  if (Object.keys(dist).length) {
    const row = el("div", "dist");
    for (const key of ["min", "p5", "median", "p75", "max"]) {
      if (dist[key] === undefined) continue;
      row.appendChild(el("span", null, `${key} ${dist[key].toFixed(3)}`));
    }
    head.appendChild(row);
    head.appendChild(
      el(
        "div",
        null,
        "The ranked order is the reliable signal; the threshold is an untuned default."
      )
    );
  }

  for (const hit of result.orphans) list.appendChild(hitRow(hit));
}

// ---------------------------------------------------------------------------
// Requirements
// ---------------------------------------------------------------------------

function renderRequirements(requirements, readOnly) {
  const body = $("reqsBody");
  body.replaceChildren();

  if (!requirements.length) {
    body.appendChild(
      el(
        "p",
        "empty",
        "No requirements stated yet. On a normal repository the requirement set is built by asking — use the Trace tab."
      )
    );
    return;
  }

  for (const req of requirements) {
    const row = el("div", "req");
    const id = el("span", "req-id", req.req_id);
    id.title = "Re-trace this requirement";
    id.addEventListener("click", () =>
      vscode.postMessage({ type: "retrace", req_id: req.req_id })
    );
    row.appendChild(id);
    row.appendChild(el("span", "req-text", req.title));

    if (!readOnly) {
      const del = el("button", "req-del", "×");
      del.title = "Forget this requirement";
      del.addEventListener("click", () =>
        vscode.postMessage({ type: "forget", req_id: req.req_id })
      );
      row.appendChild(del);
    }
    body.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

$("restart").addEventListener("click", () => vscode.postMessage({ type: "restart" }));
$("log").addEventListener("click", () => vscode.postMessage({ type: "showOutput" }));

window.addEventListener("message", (event) => {
  const message = event.data;
  switch (message.type) {
    case "state":
      return renderState(message.state);
    case "status":
      return renderStatus(message.status);
    case "trace":
      return renderTrace(message.result);
    case "method":
      return renderMethod(message);
    case "orphans":
      return renderOrphans(message.result);
    case "flash":
      return flash(message.text);
    case "orphansStale":
      // The requirement set changed, so every orphan score is now wrong.
      // Re-scan if the tab is open; otherwise clear it so the next visit
      // re-fetches rather than showing figures from a previous requirement set.
      $("orphansList").replaceChildren();
      $("orphansHead").textContent = "";
      if (!$("panel-orphans").hidden) requestOrphans();
      return;
    case "busy":
      return;
    case "error": {
      const box = $("error");
      box.textContent = message.message;
      box.hidden = false;
      setTimeout(() => {
        box.hidden = true;
      }, 8000);
      $("traceHead").textContent = "";
      return;
    }
  }
});

vscode.postMessage({ type: "ready" });
