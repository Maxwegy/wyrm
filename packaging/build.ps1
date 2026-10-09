# Builds dist\Wyrm\Wyrm.exe (a folder you can zip or copy anywhere).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
python -m pip install -e ".[dev]"
python -m pytest -q
python packaging\make_icon.py
python -m PyInstaller --noconfirm --clean packaging\wyrm.spec
Write-Host "Built: $root\dist\Wyrm\Wyrm.exe"
