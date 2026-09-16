# build_exe.ps1 — full pipeline: static frontend export, then bundle the
# backend + that export into one JobHunterAI.exe. Run from the repo root.
$ErrorActionPreference = "Stop"

Push-Location frontend
npm run build
Pop-Location

.\.venv\Scripts\pip.exe show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
  .\.venv\Scripts\pip.exe install pyinstaller
}

.\.venv\Scripts\pyinstaller.exe pyinstaller.spec --distpath backend\dist --workpath backend\build

Write-Host "Built: backend\dist\JobHunterAI.exe"
