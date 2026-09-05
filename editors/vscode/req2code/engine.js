"use strict";
/**
 * A dependency-free MCP client.
 *
 * WHY NOT @modelcontextprotocol/sdk
 * --------------------------------
 * Because then this extension would need `npm install`, a bundler, and a build
 * step, and installing it would stop being "copy the folder into
 * ~/.vscode/extensions and reload". The project's whole posture is offline and
 * no-setup; an extension that needs a network round trip before it runs
 * contradicts that.
 *
 * The cost is this file. MCP over stdio is newline-delimited JSON-RPC 2.0 and
 * the handshake is three messages, so the cost is small and it is paid once.
 *
 * WHY MCP AND NOT A PRIVATE PROTOCOL
 * ----------------------------------
 * There is exactly one engine. `scripts/mcp_server.py` already serves Claude
 * Code, Cursor and Zed; making the extension speak the same protocol means the
 * UI cannot drift from what those editors see, and there is no second server to
 * keep alive. The UI-shaped answers come back in `structuredContent`, which is
 * what that field is for.
 */

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const PROTOCOL_VERSION = "2025-06-18";

/** Milliseconds before a call is abandoned. The engine's slowest operation is
 *  a cold index of a large repository, which happens once, at boot. */
const CALL_TIMEOUT_MS = 120000;

class Engine {
  /**
   * @param {object} opts
   * @param {string} opts.enginePath  req2code checkout (contains scripts/)
   * @param {string} opts.workspaceRoot  repository to trace
   * @param {string} opts.pythonPath  interpreter, or "" to auto-detect
   * @param {(line: string) => void} opts.log
   * @param {(state: object) => void} opts.onState
   */
  constructor(opts) {
    this.opts = opts;
    this.proc = null;
    this.buffer = "";
    this.pending = new Map();
    this.nextId = 0;
    this.ready = false;
    this.state = { status: "stopped", detail: "" };
  }

  setState(status, detail) {
    this.state = { status, detail: detail || "" };
    this.opts.onState(this.state);
  }

  /** Interpreter to run with: explicit setting, then the engine's own venv,
   *  then bare `python`. The venv step matters — the engine needs torch, and a
   *  user's default interpreter almost certainly does not have it. */
  resolvePython() {
    if (this.opts.pythonPath) return this.opts.pythonPath;
    const candidates =
      process.platform === "win32"
        ? [path.join(this.opts.enginePath, ".venv", "Scripts", "python.exe")]
        : [path.join(this.opts.enginePath, ".venv", "bin", "python")];
    for (const c of candidates) {
      try {
        if (fs.existsSync(c)) return c;
      } catch (_) {
        /* fall through */
      }
    }
    return process.platform === "win32" ? "python" : "python3";
  }

  start() {
    if (this.proc) return;
    const python = this.resolvePython();
    this.setState("starting", "indexing…");
    this.opts.log(`spawn ${python} -m scripts.mcp_server`);
    this.opts.log(`  cwd           ${this.opts.enginePath}`);
    this.opts.log(`  REQ2CODE_ROOT ${this.opts.workspaceRoot}`);

    this.proc = spawn(python, ["-m", "scripts.mcp_server"], {
      cwd: this.opts.enginePath,
      env: {
        ...process.env,
        REQ2CODE_ROOT: this.opts.workspaceRoot,
        // The engine imports `src.*`, and it is only importable from its own
        // root. Setting this explicitly means the extension does not depend on
        // req2code having been pip-installed.
        PYTHONPATH: this.opts.enginePath,
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8",
      },
    });

    this.proc.on("error", (err) => {
      this.setState("error", `could not start ${python}: ${err.message}`);
      this.opts.log(`spawn failed: ${err.message}`);
      this.proc = null;
    });

    this.proc.stdout.on("data", (chunk) => this.onStdout(chunk));
    // The engine prints progress and warnings to stderr. It is the only place
    // a misconfiguration (missing torch, wrong interpreter) is explained, so it
    // goes to the output channel verbatim rather than being swallowed.
    this.proc.stderr.on("data", (chunk) => {
      String(chunk)
        .split(/\r?\n/)
        .filter(Boolean)
        .forEach((line) => this.opts.log(`[engine] ${line}`));
    });
    this.proc.on("exit", (code, signal) => {
      this.ready = false;
      this.proc = null;
      for (const [, entry] of this.pending) {
        entry.reject(new Error("engine exited"));
      }
      this.pending.clear();
      if (this.state.status !== "stopped") {
        this.setState("error", `engine exited (code ${code}${signal ? ", " + signal : ""})`);
      }
    });

    return this.handshake();
  }

  onStdout(chunk) {
    this.buffer += chunk.toString("utf8");
    let newline;
    while ((newline = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, newline).trim();
      this.buffer = this.buffer.slice(newline + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch (_) {
        // Not every line on stdout is ours to interpret; a stray print from a
        // dependency must not kill the connection.
        this.opts.log(`non-JSON on stdout: ${line.slice(0, 200)}`);
        continue;
      }
      const entry = this.pending.get(message.id);
      if (entry) {
        this.pending.delete(message.id);
        clearTimeout(entry.timer);
        entry.resolve(message);
      }
    }
  }

  request(method, params) {
    return new Promise((resolve, reject) => {
      if (!this.proc) return reject(new Error("engine is not running"));
      const id = ++this.nextId;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out after ${CALL_TIMEOUT_MS}ms`));
      }, CALL_TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timer });
      this.proc.stdin.write(
        JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n"
      );
    });
  }

  notify(method, params) {
    if (!this.proc) return;
    this.proc.stdin.write(JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n");
  }

  async handshake() {
    try {
      const res = await this.request("initialize", {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "req2code-vscode", version: "0.1.0" },
      });
      if (res.error) throw new Error(res.error.message || "initialize failed");
      this.notify("notifications/initialized", {});
      this.ready = true;
      const info = res.result && res.result.serverInfo;
      this.setState("ready", info ? `${info.name} ${info.version}` : "connected");
      return true;
    } catch (err) {
      this.setState("error", err.message);
      this.opts.log(`handshake failed: ${err.message}`);
      return false;
    }
  }

  /**
   * Call a tool and return its structured result.
   *
   * Prefers `structuredContent` and falls back to parsing the text block,
   * because a tool that returns a plain string (the prose tools, meant for
   * language models) has no structured half at all.
   */
  async call(name, args) {
    const res = await this.request("tools/call", { name, arguments: args || {} });
    if (res.error) throw new Error(res.error.message || `${name} failed`);
    const result = res.result || {};
    if (result.isError) {
      const text = (result.content || []).map((c) => c.text).join("\n");
      throw new Error(text || `${name} reported an error`);
    }
    if (result.structuredContent) return result.structuredContent;
    const text = (result.content || []).map((c) => c.text).join("\n");
    try {
      return JSON.parse(text);
    } catch (_) {
      return { text };
    }
  }

  stop() {
    this.setState("stopped", "");
    this.ready = false;
    if (this.proc) {
      this.proc.kill();
      this.proc = null;
    }
  }
}

module.exports = { Engine };
