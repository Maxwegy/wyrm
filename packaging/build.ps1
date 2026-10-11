# Builds Wyrm.exe (single file) and copies it to the project folder.
# Also leaves the folder build at dist\Wyrm\ (starts faster; zip it to share).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install -e ".[dev]"
python -m pytest -q
python packaging\make_icon.py
python -m PyInstaller --noconfirm --clean --distpath dist\onefile packaging\wyrm-onefile.spec
python -m PyInstaller --noconfirm packaging\wyrm.spec
Copy-Item dist\onefile\Wyrm.exe "$root\Wyrm.exe" -Force
# Wyrm.exe is committed to the repo; stage the fresh build so the next commit ships it.
git -C $root add Wyrm.exe
Write-Host "Built and staged: $root\Wyrm.exe (commit and push to publish it)"
