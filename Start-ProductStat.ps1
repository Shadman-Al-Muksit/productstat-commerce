param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$linuxPath = (wsl.exe -d Ubuntu -- wslpath -a $projectRoot).Trim()
if ($Preview) { wsl.exe -d Ubuntu -- bash "$linuxPath/scripts/dev.sh" --preview }
else { wsl.exe -d Ubuntu -- bash "$linuxPath/scripts/dev.sh" }
