#Requires -Version 5
<#
.SYNOPSIS
    Remove the "Transcode to..." right-click menu for .mp4 files.
#>

$ErrorActionPreference = "Stop"
$base = "HKCU:\Software\Classes\SystemFileAssociations\.mp4\shell\TranscodeTo"

if (Test-Path $base) {
    Remove-Item -Path $base -Recurse -Force
    Write-Host "Uninstalled."
} else {
    Write-Host "Not installed — nothing to remove."
}
