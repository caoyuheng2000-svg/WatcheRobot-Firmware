[CmdletBinding()]
param(
    [switch]$InstallDeps,
    [switch]$ShowLogs,
    [switch]$AutoStart
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if ($InstallDeps) {
    python -m pip install -r requirements.txt
}

$argsList = @((Join-Path $ScriptDir "voice_wake_tester\wake_gui.py"))
if ($ShowLogs) {
    $argsList += "--show-logs"
}
if ($AutoStart) {
    $argsList += "--auto-start"
}

python @argsList
