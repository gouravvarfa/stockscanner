# Auto-restart supervisor for the backend.
#
# The Tapetide MCP SDK's own background GET/SSE reconnect loop has a known
# failure mode (anyio "cancel scope entered in a different task" error) that
# can crash the whole FastAPI process when Tapetide's stream drops mid-session.
# That originates inside the third-party mcp library's transport internals,
# not this app's own code, so instead of trying to patch it, this loop just
# brings the server back up automatically - a crash means a few seconds of
# downtime instead of a stuck app.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

while ($true) {
    Write-Host ("[{0}] Starting backend..." -f (Get-Date -Format "HH:mm:ss"))
    & .\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
    Write-Host ("[{0}] Backend exited (code {1}) - restarting in 2s..." -f (Get-Date -Format "HH:mm:ss"), $LASTEXITCODE)
    Start-Sleep -Seconds 2
}
