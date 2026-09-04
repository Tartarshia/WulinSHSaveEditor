$ErrorActionPreference = 'Stop'
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean --windowed --onefile --name WulinSHSaveEditor app.py
Write-Host 'Build complete: dist\WulinSHSaveEditor.exe'
