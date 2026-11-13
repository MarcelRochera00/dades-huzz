# One-time setup on Windows. Run from the repo root: ./scripts/setup.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$missing = @()
foreach ($tool in "git", "uv", "gh") {
    if (Get-Command $tool -ErrorAction SilentlyContinue) {
        Write-Host "[ok] $tool"
    } else {
        Write-Host "[missing] $tool"
        $missing += $tool
    }
}
if ($missing -contains "uv") { Write-Host "  install uv: https://docs.astral.sh/uv/getting-started/installation/" }
if ($missing -contains "gh") { Write-Host "  install gh: https://cli.github.com (then: gh auth login)" }
if ($missing -contains "git" -or $missing -contains "uv") { exit 1 }

uv sync
if ($LASTEXITCODE -ne 0) { exit 1 }
uv run pytest -q
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Skills in this repo:"
Get-ChildItem .agents/skills -Directory | ForEach-Object { Write-Host "  - $($_.Name)" }
Write-Host ""
Write-Host "Ready. Open your agent in this folder and check it lists the skills above."
Write-Host "Read docs/COM-TREBALLEM.md next."
