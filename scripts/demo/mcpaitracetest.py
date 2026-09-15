"""mcpaitracetest -- the AI-agent path, over the real MCP protocol.

    python -m scripts.demo.mcpaitracetest "the system shall ..."

Companion to scripts/demo/tracetest.py. That script runs the pipeline
in-process, offline, no agent involved -- this one launches the actual
`scripts.mcp_server` subprocess and talks to it exactly as Claude Code, Cursor,
or any other MCP-speaking editor would: over stdio, with a real MCP handshake,
calling the same `state_requirement` and `find_orphans` tools an AI agent
would call. That distinction matters for the demo -- one number is "the
pipeline is fast", the other is "this is what the agent actually sees".

WHAT THIS ADDS OVER tracetest.py
---------------------------------
The MCP round trip (handshake + tool call), and a token estimate: how many
tokens the agent's context spends reading the tool's answer, versus how many
it would have spent reading the whole file that answer points into. That is
the concrete form of "the agent can refer to the traced record directly
instead of re-discovering it by reading code" -- the same idea, but here it is
priced in tokens per model call rather than lines of code once.

Token counts are approximate (chars / 4, the standard rule-of-thumb estimate)
and reported as such -- this script does not depend on any tokenizer, so it
stays fully offline like everything else here.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

DEFAULT_REPO = Path(r"C:\Users\Atharv\Desktop\req2code-orphan-test")
REQ2CODE_ROOT = Path(__file__).resolve().parents[2]
CHARS_PER_TOKEN = 4.0  # standard rough estimate; no tokenizer dependency


def _chars_to_tokens(n_chars: int) -> float:
    return n_chars / CHARS_PER_TOKEN


async def _call(repo: Path, text: str, top_k: int, threshold: float) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scripts.mcp_server"],
        env={"REQ2CODE_ROOT": str(repo)},
        cwd=str(REQ2CODE_ROOT),
    )

    t_boot0 = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            t_boot = (time.perf_counter() - t_boot0) * 1000

            t_call0 = time.perf_counter()
            result = await session.call_tool(
                "state_requirement", {"text": text, "top_k": top_k}
            )
            t_call = (time.perf_counter() - t_call0) * 1000
            answer_text = "\n".join(
                block.text for block in result.content if hasattr(block, "text")
            )

            t_orphan0 = time.perf_counter()
            orphan_result = await session.call_tool(
                "find_orphans", {"threshold": threshold, "limit": 20}
            )
            t_orphan = (time.perf_counter() - t_orphan0) * 1000
            orphan_text = "\n".join(
                block.text for block in orphan_result.content if hasattr(block, "text")
            )

    return {
        "answer_text": answer_text,
        "orphan_text": orphan_text,
        "boot_ms": t_boot,
        "call_ms": t_call,
        "orphan_ms": t_orphan,
    }


def _file_char_count(repo: Path, rel_file: str) -> int:
    path = repo / rel_file
    try:
        return len(path.read_text(encoding="utf-8"))
    except OSError:
        return 0


def _parse_first_hit_file(answer_text: str) -> str | None:
    for line in answer_text.splitlines():
        line = line.strip()
        if line[:1].isdigit() and "." in line and " " in line:
            # "  1. 0.748  TaskManager.add_task()  app/tasks.py:8-12"
            tail = line.rsplit(" ", 1)[-1]
            if ":" in tail:
                return tail.split(":")[0]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcpaitracetest",
        description="The AI-agent path: real MCP handshake + tool calls, with a token estimate.",
    )
    parser.add_argument("text", help="Requirement text, in quotes.")
    parser.add_argument(
        "--repo", type=Path, default=DEFAULT_REPO, help="Repository the MCP server indexes."
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

    result = asyncio.run(_call(args.repo, args.text, args.top_k, args.threshold))

    print("MCP tool call: state_requirement  (this is exactly what an AI editor sees)")
    print("-" * 74)
    print(result["answer_text"])
    print()
    print("MCP tool call: find_orphans")
    print("-" * 74)
    print(result["orphan_text"])

    print()
    print("performance -- MCP round trip, this run")
    print("-" * 66)
    print(f"  {'handshake + server boot (once per session)':<44} {result['boot_ms']:>8.2f} ms")
    print(f"  {'state_requirement tool call':<44} {result['call_ms']:>8.2f} ms")
    print(f"  {'find_orphans tool call':<44} {result['orphan_ms']:>8.2f} ms")

    answer_chars = len(result["answer_text"])
    answer_tokens = _chars_to_tokens(answer_chars)

    matched_file = _parse_first_hit_file(result["answer_text"])
    file_chars = _file_char_count(args.repo, matched_file) if matched_file else 0
    repo_chars = sum(
        _file_char_count(args.repo, str(p.relative_to(args.repo)))
        for p in args.repo.rglob("*.py")
    )

    print()
    print("token cost -- what the agent actually spends its context on")
    print("-" * 66)
    print(f"  tool response the agent reads         ~{answer_tokens:>7.0f} tokens  ({answer_chars} chars)")
    if matched_file:
        file_tokens = _chars_to_tokens(file_chars)
        print(f"  vs. reading the whole matched file    ~{file_tokens:>7.0f} tokens  ({matched_file}, {file_chars} chars)")
        if file_chars:
            saved = 100 * (1 - answer_chars / max(file_chars, 1))
            print(f"  saved on this one file                 {saved:>7.1f}%")
    repo_tokens = _chars_to_tokens(repo_chars)
    print(f"  vs. reading every .py file in the repo ~{repo_tokens:>6.0f} tokens  ({repo_chars} chars, no req2code)")
    if repo_chars:
        saved_repo = 100 * (1 - answer_chars / max(repo_chars, 1))
        print(f"  saved vs. reading the whole repo       {saved_repo:>7.1f}%")
    print()
    print(
        "  Approximate (chars/4), not a real tokenizer count -- say so if asked. "
        "The point is structural: the agent gets a direct pointer instead of "
        "having to read or grep its way to one."
    )

    if not args.no_log:
        log_dir = args.repo / ".req2code"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "tracetest_log.jsonl"
        record = {
            "kind": "mcpaitracetest",
            "ts": datetime.now(timezone.utc).isoformat(),
            "repo": str(args.repo),
            "text": args.text,
            "answer_text": result["answer_text"],
            "matched_file": matched_file,
            "timings_ms": {
                "boot": round(result["boot_ms"], 2),
                "state_requirement_call": round(result["call_ms"], 2),
                "find_orphans_call": round(result["orphan_ms"], 2),
            },
            "tokens_est": {
                "answer": round(answer_tokens, 1),
                "matched_file": round(_chars_to_tokens(file_chars), 1) if matched_file else None,
                "whole_repo": round(repo_tokens, 1),
            },
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print()
        print(f"recorded -> {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
