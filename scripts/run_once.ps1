# Wrapper for Task Scheduler: drains pending Telegram messages and exits.
# Task Scheduler doesn't offer output redirection on its own, so this
# appends everything to logs/drain.log.

Set-Location $PSScriptRoot\..

$logDir = Join-Path $PSScriptRoot "..\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null

uv run python main.py --once 2>&1 | Out-File -Append -Encoding utf8 (Join-Path $logDir "drain.log")
