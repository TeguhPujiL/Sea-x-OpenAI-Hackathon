param([string]$Python = '.\.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force -Path '.tools/qa-results' | Out-Null
Write-Host 'OFFLINE SYNTHETIC QA REPLAY: no provider calls and no live demo data.'
Write-Host 'G01 CLEAN_CASE_COMPLETION_BLOCKED: v1.1 requires repair_proposal_id; no APPROVE_CASE or fabricated finding is permitted.'
& $Python -m pytest backend/tests -q --tb=short --junitxml=.tools/qa-results/assurance.xml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python -m compileall -q backend/app scripts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $Python scripts/contract_readiness.py --output .tools/qa-results/readiness.json
$readinessExit = $LASTEXITCODE
if ($readinessExit -ne 0) {
    Write-Host 'BLOCKED: full API integration is incomplete; inspect readiness.json. Assurance tests above are a fixture replay.'
}
exit $readinessExit
