$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$linuxPath = (wsl.exe -d Ubuntu -- wslpath -a $projectRoot).Trim()
wsl.exe -d Ubuntu -- bash "$linuxPath/scripts/dev.sh"
