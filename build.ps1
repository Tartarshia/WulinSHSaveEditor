$ErrorActionPreference = 'Stop'
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --windowed --onefile --name WulinSHSaveEditor --collect-all UnityPy --add-data "templates;templates" --add-data "static;static" web_app.py
Write-Host 'Build complete: dist\WulinSHSaveEditor.exe'
