$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path 'models\vosk-model-small-ru-0.22\am')) {
    throw 'Run first: python download_model.py'
}
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name BrightnessVoiceControl `
  --icon 'assets\app.ico' `
  --version-file 'version_info.txt' `
  --add-data 'assets\app.ico;assets' `
  --add-data 'models\vosk-model-small-ru-0.22;models\vosk-model-small-ru-0.22' `
  --collect-all vosk --collect-all sounddevice --collect-all pyttsx3 `
  --hidden-import numpy `
  --hidden-import pythoncom --hidden-import win32com.client `
  main.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
Write-Host 'Build complete: dist\BrightnessVoiceControl.exe'
$isccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$isccPath = if ($isccCommand) { $isccCommand.Source } else { $null }
if (-not $isccPath) {
  $known = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
  foreach ($candidate in $known) { if (Test-Path $candidate) { $isccPath = $candidate; break } }
}
if ($isccPath) {
  & $isccPath 'installer\BrightnessVoiceControl.iss'
  if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
  Write-Host 'Build complete: dist\BrightnessVoiceControl-Setup-1.1.1.exe'
} else {
  Write-Host 'Install Inno Setup 6 and run build.ps1 again to create installer.'
}
