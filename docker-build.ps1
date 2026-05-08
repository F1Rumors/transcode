#Requires -Version 5
<#
.SYNOPSIS
    Build (or rebuild) the transcode Docker image.
.DESCRIPTION
    Run this whenever the transcode code changes.
    The image is tagged transcode:latest.
#>

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -LiteralPath $MyInvocation.MyCommand.Path -Parent

Write-Host "Building transcode:latest from $scriptDir ..."
docker build --tag transcode:latest $scriptDir

if ($LASTEXITCODE -eq 0) {
    Write-Host "Build complete."
} else {
    Write-Error "docker build failed (exit $LASTEXITCODE)"
}
