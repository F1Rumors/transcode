#Requires -Version 5
<#
.SYNOPSIS
    Install the "Transcode to..." right-click menu for .mp4 files.
    Current user only — no admin required.
    Run uninstall.ps1 to remove.
#>

$ErrorActionPreference = "Stop"

$wrapper  = "S:\misc\python\claude\transcode\wrapper.ps1"
$base     = "HKCU:\Software\Classes\SystemFileAssociations\.mp4\shell\TranscodeTo"
# Use Windows Terminal tabs if available, otherwise a plain PowerShell window.
$pwsh = "C:\Program Files\PowerShell\7\pwsh.exe"
$wt   = (Get-Command wt -ErrorAction SilentlyContinue)?.Source
if ($wt) {
    # -w 0 targets the most-recent Windows Terminal window (creates one if none open).
    # Each file selected gets its own tab in that window.
    $psLaunch = "wt.exe -w 0 new-tab `"$pwsh`" -NoExit -ExecutionPolicy Bypass -File `"$wrapper`" -Resolution {0} -FilePath `"%1`""
} else {
    $psLaunch = "`"$pwsh`" -NoExit -WindowStyle Normal -ExecutionPolicy Bypass -File `"$wrapper`" -Resolution {0} -FilePath `"%1`""
}

$resolutions = [ordered]@{
    "01_4k"    = @{ Label = "4K  (3840x2160)";                Key = "4k"    }
    "02_1080p" = @{ Label = "1080p  (1920x1080)";             Key = "1080p" }
    "03_1080i" = @{ Label = "1080i  (1920x1080 interlaced)";  Key = "1080i" }
    "04_720p"  = @{ Label = "720p  (1280x720)";               Key = "720p"  }
    "05_720i"  = @{ Label = "720i  (1280x720 interlaced)";    Key = "720i"  }
    "06_pal"   = @{ Label = "PAL  (720x576)";                 Key = "pal"   }
}

# Parent key
New-Item -Path $base -Force | Out-Null
Set-ItemProperty -Path $base -Name "MUIVerb"      -Value "Transcode to..."
Set-ItemProperty -Path $base -Name "SubCommands"  -Value ""

# One child per resolution
foreach ($name in $resolutions.Keys) {
    $r        = $resolutions[$name]
    $child    = "$base\Shell\$name"
    $cmdKey   = "$child\command"

    New-Item -Path $child  -Force | Out-Null
    Set-ItemProperty -Path $child -Name "MUIVerb"          -Value $r.Label
    Set-ItemProperty -Path $child -Name "MultiSelectModel" -Value "Player"

    New-Item -Path $cmdKey -Force | Out-Null
    Set-ItemProperty -Path $cmdKey -Name "(default)" -Value ($psLaunch -f $r.Key)
}

Write-Host "Installed. Right-click any .mp4 file to see 'Transcode to...'"
Write-Host "(On Windows 11, look under 'Show more options')"
