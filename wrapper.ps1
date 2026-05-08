#Requires -Version 7.1
<#
.SYNOPSIS
    Context-menu launcher: transcode a video file using Python directly.
.PARAMETER Resolution
    Target resolution key (e.g. 720p, 1080p, 4k, pal).
.PARAMETER FilePath
    Absolute path to the selected video file.
    Called once per file by Windows Explorer (MultiSelectModel=Player).
#>
param(
    [Parameter(Mandatory)][string]$Resolution,
    [Parameter(Mandatory)][string]$FilePath
)

# Keep the window open and show errors if anything goes wrong.
trap {
    Write-Host ""
    Write-Host "ERROR: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    Write-Host ""
    Write-Host "Press Enter to close..."
    $null = Read-Host
    exit 1
}

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms

# ── Find Python ───────────────────────────────────────────────────────────────
# Explorer's PATH differs from a terminal session so we use known full paths.

$pythonCandidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Launcher\py.exe",
    "C:\Python312\python.exe",
    "C:\Python3\python.exe"
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    [System.Windows.Forms.MessageBox]::Show(
        "python.exe not found. Update the paths in wrapper.ps1.",
        "Transcode", "OK", "Error") | Out-Null
    exit 1
}

$codeRoot = Split-Path $PSScriptRoot -Parent

# ── Helpers ───────────────────────────────────────────────────────────────────

function Get-BareStem([string]$stem) {
    return $stem -ireplace '_(4k|1080[pi]|720[pi]|pal)(_\d+fps)?$|_\d+fps$', ''
}

function Show-YesNoCancel([string]$message, [string]$title) {
    return [System.Windows.Forms.MessageBox]::Show(
        $message, $title,
        [System.Windows.Forms.MessageBoxButtons]::YesNoCancel,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
}

# ── Resolve source file ───────────────────────────────────────────────────────

$dir  = [System.IO.Path]::GetDirectoryName($FilePath)
$name = [System.IO.Path]::GetFileName($FilePath)
$ext  = [System.IO.Path]::GetExtension($name)
$stem = [System.IO.Path]::GetFileNameWithoutExtension($name)

$bareStem = Get-BareStem $stem

if ($bareStem -ne $stem) {
    $candidateOriginal = Join-Path $dir "$bareStem$ext"
    if (Test-Path -LiteralPath $candidateOriginal) {
        Write-Host "Using original: $bareStem$ext  (instead of $name)"
        $srcPath = $candidateOriginal
    } else {
        $srcPath = $FilePath
    }
} else {
    $srcPath  = $FilePath
    $bareStem = $stem
}

# ── Compute output path ───────────────────────────────────────────────────────

$outName = "${bareStem}_${Resolution}${ext}"
$outPath = Join-Path $dir $outName

# ── Overwrite check ───────────────────────────────────────────────────────────

$overwriteArgs = @()
if (Test-Path -LiteralPath $outPath) {
    $answer = Show-YesNoCancel `
        "Output already exists:`n$outPath`n`nOverwrite?" `
        "Transcode"
    if ($answer -eq [System.Windows.Forms.DialogResult]::Cancel) { exit 0 }
    if ($answer -eq [System.Windows.Forms.DialogResult]::No)    { exit 0 }
    $overwriteArgs = @("--overwrite")
}

# ── Header ───────────────────────────────────────────────────────────────────

$srcName = [System.IO.Path]::GetFileName($srcPath)

$Host.UI.RawUI.WindowTitle = "Transcode $srcName -> $Resolution"

Write-Host "========================================"
Write-Host "  Transcode"
Write-Host "    Source     : $srcName"
if ($srcName -ne $name) {
    Write-Host "    (clicked)  : $name"
}
Write-Host "    Resolution : $Resolution"
Write-Host "    Output     : $outName"
Write-Host "    Folder     : $dir"
Write-Host "========================================"
Write-Host ""

# ── Run transcoder ───────────────────────────────────────────────────────────

$env:PYTHONPATH = $codeRoot
& $python -m transcode.cli --resolution $Resolution @overwriteArgs $srcPath

$exitCode = $LASTEXITCODE

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "Done: $outName" -ForegroundColor Green
} else {
    Write-Host "FAILED (exit $exitCode)" -ForegroundColor Red
}

Write-Host ""
Write-Host "Press Enter to close..."
$null = Read-Host
exit $exitCode
