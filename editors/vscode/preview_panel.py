"""Render the extension's panel in a plain browser, with real engine data.

    python editors/vscode/preview_panel.py            # live data from this repo
    python editors/vscode/preview_panel.py --path X   # live data from repo X
    python editors/vscode/preview_panel.py --offline  # canned data, no engine

Writes `editors/vscode/panel-preview.html` and prints the path. Open it in any
browser.

WHY THIS EXISTS
---------------
Iterating on the panel through VS Code is slow and blind: every CSS change means
rebuild, reinstall, restart, re-open the sidebar, and if something throws you are
reading a webview devtools console nested two processes deep.

This loads *the actual files* -- `media/panel.html`, `media/panel.css`,
`media/panel.js`, unmodified -- stubs the one API VS Code injects
(`acquireVsCodeApi`), supplies VS Code's dark-theme CSS variables, and feeds the
panel the exact payloads the engine returns. What renders is what the extension
renders.

It is a preview of the real thing, not a mockup of it. Nothing is retyped: the
markup is sliced out of `panel.html` at run time, so a preview that looks right
while the extension looks wrong is not a failure mode this can have.

WHAT IT CANNOT SHOW
-------------------
Only the webview half. The CodeLens labels above each method and the status bar
item are native VS Code widgets drawn by the editor, not HTML -- see the
architecture note at the top of `extension.js`. Those you have to look at in
VS Code.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXTENSION = HERE / "req2code"
MEDIA = EXTENSION / "media"
OUTPUT = HERE / "panel-preview.html"

#: Sidebar width in VS Code, near enough. The panel has to work in a narrow
#: column and previewing it full-width would hide every layout problem it has.
PANEL_WIDTH_PX = 340

#: VS Code's Dark Modern values for the variables `panel.css` consumes. The
#: panel itself defines no colours -- it inherits the theme -- so previewing it
#: means supplying a theme.
THEME = """
:root{
 --vscode-font-family:-apple-system,"Segoe UI",system-ui,sans-serif;
 --vscode-font-size:13px;
 --vscode-editor-font-family:"Cascadia Code",Consolas,"Courier New",monospace;
 --vscode-foreground:#cccccc; --vscode-descriptionForeground:#9d9d9d;
 --vscode-panel-border:#2b2b2b; --vscode-focusBorder:#0078d4;
 --vscode-input-background:#313131; --vscode-input-foreground:#cccccc;
 --vscode-input-border:#3c3c3c;
 --vscode-button-background:#0078d4; --vscode-button-foreground:#ffffff;
 --vscode-button-hoverBackground:#026ec1;
 --vscode-button-secondaryBackground:#313131;
 --vscode-button-secondaryForeground:#cccccc;
 --vscode-button-secondaryHoverBackground:#3c3c3c;
 --vscode-textLink-foreground:#4daafc; --vscode-textLink-activeForeground:#4daafc;
 --vscode-list-hoverBackground:#2a2d2e;
 --vscode-charts-green:#89d185; --vscode-charts-red:#f14c4c;
 --vscode-charts-yellow:#d7ba7d; --vscode-charts-blue:#4fa6d9;
 --vscode-symbolIcon-methodForeground:#b180d7;
 --vscode-inputValidation-infoBackground:#063b49;
 --vscode-inputValidation-infoBorder:#1a85ff;
 --vscode-inputValidation-warningBackground:#352a05;
 --vscode-inputValidation-warningBorder:#b89500;
 --vscode-inputValidation-errorBackground:#5a1d1d;
 --vscode-inputValidation-errorBorder:#be1100;
}
body{background:#1f1f1f;margin:0;display:flex;align-items:flex-start;
     font-family:var(--vscode-font-family);}
#previewWrap{width:%(width)spx;flex:0 0 auto;background:#181818;
             border-right:1px solid #2b2b2b;min-height:100vh;}
#previewNote{padding:14px 18px;color:#9d9d9d;font-size:12px;line-height:1.7;
             max-width:30em;}
#previewNote h1{font-size:13px;color:#cccccc;margin:0 0 8px;}
#previewNote code{color:#4daafc;font-family:var(--vscode-editor-font-family);}
#previewTabs{margin-top:10px;}
#previewTabs button{margin-right:6px;}
"""

#: The one API VS Code injects into a webview. Recording posted messages rather
#: than discarding them means clicking a result in the preview shows you the
#: message the extension would have received.
HARNESS = """
const __posted = [];
function acquireVsCodeApi(){
  return {
    postMessage:(m)=>{ __posted.push(m); console.log("postMessage", m);
      const box=document.getElementById("lastMessage");
      if(box) box.textContent = JSON.stringify(m); },
    setState:()=>{}, getState:()=>undefined,
  };
}
"""

CANNED = {
    "status": {
        "root": "/example/project", "mode": "workspace", "read_only": False,
        "files": 43, "nodes": 181, "methods": 171,
        "languages": {"python": 181}, "gold_links": 0,
        "git": {"tracked": True, "head": "20123d3fc88f0a1b", "dirty": 3},
        "requirements": [
            {"req_id": "SR0001", "title": "the system shall detect which files changed",
             "text": "the system shall detect which files changed"},
        ],
        "timings": {},
    },
    "trace": {"query": "example", "req_id": None, "created": None, "hits": []},
    "orphans": {"threshold": 0.25, "methods": 0, "flagged": 0,
                "distribution": {}, "orphans": [],
                "reason": "no engine -- canned data"},
    "fileMap": {"file": "example.py", "nodes": [], "requirements": 0},
}


def capture(repo: Path) -> dict:
    """Run the extension's own engine client and keep what it returns.

    Shelling out to node rather than calling the Python engine directly is the
    point: it exercises `engine.js`, so a preview that renders proves the client
    the extension actually ships works, not just that the server does.
    """
    script = HERE / "_capture.js"
    script.write_text(
        """
const { Engine } = require("./req2code/engine.js");
const root = process.argv[2];
const engine = new Engine({
  enginePath: __dirname + "/../..", workspaceRoot: root,
  pythonPath: "", log: () => {}, onState: () => {},
});
(async () => {
  if (!(await engine.start())) {
    console.error("engine failed to start");
    process.exit(1);
  }
  const out = {
    status: await engine.call("ui_status", {}),
    trace: await engine.call("ui_trace",
      { text: process.argv[3], top_k: 8, log: false }),
    orphans: await engine.call("ui_orphans", { threshold: 0.25, limit: 8 }),
    fileMap: await engine.call("ui_file_map",
      { file: process.argv[4], top_k: 3 }),
  };
  process.stdout.write(JSON.stringify(out));
  engine.stop();
  process.exit(0);
})().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
""",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [
                "node", str(script), str(repo),
                "the system shall detect which files changed in the repository "
                "since the last check, using version control where available",
                "src/ingest/vcs.py",
            ],
            cwd=str(HERE),
            capture_output=True,
            text=True,
            timeout=300,
        )
    finally:
        script.unlink(missing_ok=True)

    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(
            "Could not capture live data.\n"
            + (proc.stderr or "").strip()
            + "\n\nRun with --offline to preview the layout with canned data."
        )
    return json.loads(proc.stdout)


def build(data: dict) -> Path:
    html = (MEDIA / "panel.html").read_text(encoding="utf-8")
    css = (MEDIA / "panel.css").read_text(encoding="utf-8")
    js = (MEDIA / "panel.js").read_text(encoding="utf-8")

    # Slice the real markup out rather than keeping a copy here. A copy would
    # drift, and a preview that drifts from the thing it previews is worse than
    # no preview.
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.S)

    method_node = None
    for node in data["fileMap"].get("nodes", []):
        if node["name"] == "changed_since":
            method_node = node
            break
    if method_node is None and data["fileMap"].get("nodes"):
        method_node = data["fileMap"]["nodes"][0]

    driver = f"""
const P = {json.dumps(data)};
const send = (m) => window.dispatchEvent(new MessageEvent("message", {{ data: m }}));
send({{ type:"state", state:{{ status:"ready", detail:"req2code 0.2.0" }} }});
send({{ type:"status", status:P.status }});
send({{ type:"trace", result:P.trace }});
send({{ type:"orphans", result:P.orphans }});
send({{ type:"method", node:{json.dumps(method_node)},
        file:P.fileMap.file, threshold:0.3 }});
send({{ type:"flash",
  text:"index updated \\u00b7 " + P.status.nodes + " nodes (+3)" }});
document.querySelectorAll("#previewTabs button").forEach((b) => {{
  b.addEventListener("click", () => showTab(b.dataset.go));
}});
"""

    note = """
<div id="previewNote">
  <h1>panel preview</h1>
  <p>This is the extension's real <code>panel.html</code>, <code>panel.css</code>
     and <code>panel.js</code>, loaded unmodified, rendered at the width of a
     VS Code sidebar, and fed the payloads the engine returned when this file was
     generated. It is the panel, not a picture of it.</p>
  <p>Not shown: the CodeLens labels above each method and the status bar item.
     Those are native VS Code widgets, not HTML.</p>
  <div id="previewTabs">
    <button data-go="trace">Trace</button>
    <button data-go="method">Method</button>
    <button data-go="orphans">Orphans</button>
    <button data-go="reqs">Requirements</button>
  </div>
  <p style="margin-top:14px">last postMessage:<br>
     <code id="lastMessage">(click a result)</code></p>
</div>
"""

    OUTPUT.write_text(
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        "<title>req2code panel preview</title>\n"
        f"<style>{THEME % {'width': PANEL_WIDTH_PX}}</style>\n<style>{css}</style>\n"
        f"</head><body>\n<div id='previewWrap'>{body}</div>\n{note}\n"
        f"<script>{HARNESS}</script>\n<script>{js}</script>\n"
        f"<script>{driver}</script>\n</body></html>\n",
        encoding="utf-8",
    )
    return OUTPUT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path", default=".", help="Repository to pull live data from."
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Use canned data; do not start the engine.",
    )
    args = parser.parse_args()

    data = CANNED if args.offline else capture(Path(args.path).resolve())
    path = build(data)
    print(path)
    if args.offline:
        print("(canned data -- layout only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
