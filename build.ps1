$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path 'models\vosk-model-small-ru-0.22\am')) {
    throw 'Сначала запустите: python download_model.py'
}
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name BrightnessVoiceControl `
  --add-data 'models\vosk-model-small-ru-0.22;models\vosk-model-small-ru-0.22' `
  --collect-all vosk --collect-all sounddevice --collect-all pyttsx3 `
  --hidden-import pythoncom --hidden-import win32com.client `
  main.py
Write-Host 'Готово: dist\BrightnessVoiceControl.exe'
