$ErrorActionPreference = 'Stop'
if (-not (Test-Path 'compose.yaml')) { throw 'Run from the LabMate root.' }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force reports/evidence | Out-Null
function Docker-Step([string]$StepName, [string]$CommandLine) {
    Write-Host "=== $StepName ==="
    $log = "reports/evidence/closeout-$stamp-$StepName.txt"
    cmd /d /c "$CommandLine 2>&1" | Tee-Object -FilePath $log
    if ($LASTEXITCODE -ne 0) { throw "Stopped: $StepName. See $log" }
}
python "$PSScriptRoot\_lesson08-closeout\install.py"
if ($LASTEXITCODE -ne 0) { throw 'Installer failed.' }
Docker-Step 'build' 'docker compose build api migrate web tests'
Docker-Step 'migration' 'docker compose run --rm migrate'
Docker-Step 'start' 'docker compose up -d --no-deps --force-recreate --wait api web'
Docker-Step 'regression' 'docker compose --profile test run --rm tests'
$credentials = "/tmp/lesson08-login-$stamp.json"
Docker-Step 'accounts' "docker compose exec -T api python -m scripts.bootstrap_lesson08 --output $credentials"
$results = "/tmp/lesson08-closeout-$stamp.json"
Docker-Step 'live' "docker compose exec -T api python -m scripts.verify_lesson08_closeout --credentials $credentials --output $results"
Docker-Step 'copy' "docker compose cp api:$results reports/evidence/lesson08-closeout-$stamp.json"
python -m scripts.archive_closeout "reports/evidence/lesson08-closeout-$stamp.json"
if ($LASTEXITCODE -ne 0) { throw 'Report archiving failed.' }
Write-Host '=== host frontend build for secret scanning ==='
cmd /d /c "npm.cmd --prefix web run build 2>&1" | Tee-Object -FilePath "reports/evidence/closeout-$stamp-host-build.txt"
if ($LASTEXITCODE -ne 0) { throw 'Host frontend build failed.' }
New-Item -ItemType Directory -Force reports/runtime-logs | Out-Null
cmd /d /c "docker compose logs --no-color api publisher worker web 2>&1" | Set-Content -Encoding UTF8 "reports/runtime-logs/closeout-$stamp.log"
$scanStarted = Get-Date
cmd /d /c ".venv\Scripts\python.exe -m scripts.check_security 2>&1" | Tee-Object -FilePath "reports/evidence/closeout-$stamp-security-command.txt"
$scanExit = $LASTEXITCODE
$summary = Get-ChildItem reports/evidence/security-*-summary.json | Where-Object { $_.LastWriteTime -ge $scanStarted.AddSeconds(-2) } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $summary) { throw 'Security tool did not produce a fresh summary; inspect command log.' }
python -m scripts.archive_security_closeout "$($summary.FullName)"
if ($LASTEXITCODE -ne 0) { throw 'Unified scan incomplete; inspect actual results, do not mark done.' }
Write-Host "Security tool exit was $scanExit; vulnerability findings retained rather than auto-fixed."
Write-Host 'Live evidence archived. Login, retrieval isolation, config permissions and skill audit have run.'
Write-Host "Private credentials remain only in api container: $credentials (do not share)."
Write-Host 'Next: run unified security command and ask a real teammate to independently reproduce two checks.'
Write-Host 'Do not mark peer review complete until the teammate signs reports/review-01.md.'
