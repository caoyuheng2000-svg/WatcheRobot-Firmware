[CmdletBinding()]
param(
    [switch]$InstallDeps
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if ($InstallDeps) {
    python -m pip install -r requirements.txt
}

$python = Get-Command python -ErrorAction Stop
$pythonw = Join-Path (Split-Path -Parent $python.Source) "pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = $python.Source
}

Start-Process -FilePath $pythonw `
    -ArgumentList @((Join-Path $ScriptDir "ble_wifi_gui_tester.py")) `
    -WorkingDirectory $ScriptDir `
    -WindowStyle Hidden
