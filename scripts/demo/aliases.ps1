# req2code demo aliases -- dot-source this file to get `tracetest` and
# `mcpaitracetest` as commands in the current PowerShell session.
#
#   . C:\Users\Atharv\Desktop\req2codeProj\req2code\scripts\demo\aliases.ps1
#
# To have them available in every new terminal, add that line to your
# PowerShell profile ($PROFILE) once.
#
#   tracetest        -- offline pipeline path (no MCP, no AI agent):
#                        parse -> embed -> cosine search, in-process, then a
#                        performance table for that run.
#   mcpaitracetest   -- the AI-agent path: launches scripts.mcp_server and
#                        talks to it over a real MCP handshake, exactly as
#                        Claude Code / Cursor / Zed would, then estimates the
#                        token cost of the agent's context.
#
# Both default to C:\Users\Atharv\Desktop\req2code-orphan-test and append a
# record of the run to <repo>\.req2code\tracetest_log.jsonl. Pass -repo to
# point at a different one; extra arguments after the requirement text pass
# straight through (e.g. -top_k 5).

$Req2CodeRoot = "C:\Users\Atharv\Desktop\req2codeProj\req2code"
$Req2CodePython = Join-Path $Req2CodeRoot ".venv\Scripts\python.exe"

function tracetest {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Requirement,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Rest
    )
    Push-Location $Req2CodeRoot
    try {
        & $Req2CodePython -m scripts.demo.tracetest $Requirement @Rest
    }
    finally {
        Pop-Location
    }
}

function mcpaitracetest {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Requirement,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Rest
    )
    Push-Location $Req2CodeRoot
    try {
        & $Req2CodePython -m scripts.demo.mcpaitracetest $Requirement @Rest
    }
    finally {
        Pop-Location
    }
}

Write-Host "req2code demo aliases loaded: tracetest, mcpaitracetest" -ForegroundColor DarkGray
