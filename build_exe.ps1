# build_exe.ps1 — full pipeline: static frontend export, then both shippable
# builds from it — JobHunterAI.exe (Windows, onefile) and JobHunterAI-mac.zip
# (Mac: source + run.command, since PyInstaller can't cross-compile).
# Run from the repo root.
$ErrorActionPreference = "Stop"

Push-Location frontend
npm run build
Pop-Location

.\.venv\Scripts\python.exe -m pip show pyinstaller > $null 2>&1
if ($LASTEXITCODE -ne 0) {
  .\.venv\Scripts\python.exe -m pip install pyinstaller
}

.\.venv\Scripts\python.exe -m PyInstaller pyinstaller.spec --distpath backend\dist --workpath backend\build

Write-Host "Built: backend\dist\JobHunterAI.exe"

.\.venv\Scripts\python.exe packaging\build_mac.py
