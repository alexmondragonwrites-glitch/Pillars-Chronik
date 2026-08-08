$ErrorActionPreference = 'SilentlyContinue'

$roots = @(
    Join-Path $env:USERPROFILE "Documents\Baldur's Gate - Enhanced Edition Trilogy\save",
    Join-Path $env:USERPROFILE "Documents\Baldur's Gate - Enhanced Edition Trilogy\mpsave",
    Join-Path $env:USERPROFILE "Documents\Baldur's Gate II - Enhanced Edition\save",
    Join-Path $env:USERPROFILE "Documents\Baldur's Gate II - Enhanced Edition\mpsave"
)

if ($env:OneDrive) {
    $roots += @(
        Join-Path $env:OneDrive "Documents\Baldur's Gate - Enhanced Edition Trilogy\save",
        Join-Path $env:OneDrive "Documents\Baldur's Gate - Enhanced Edition Trilogy\mpsave",
        Join-Path $env:OneDrive "Documents\Baldur's Gate II - Enhanced Edition\save",
        Join-Path $env:OneDrive "Documents\Baldur's Gate II - Enhanced Edition\mpsave"
    )
}

$roots = $roots | Select-Object -Unique
$found = @()

Write-Host "Wächterfeder sucht nach EET-Spielständen ..." -ForegroundColor Cyan
Write-Host ""

foreach ($root in $roots) {
    if (Test-Path $root) {
        Write-Host "[gefunden] $root" -ForegroundColor Green
        $found += Get-ChildItem -Path $root -Filter BALDUR.GAM -File -Recurse
    } else {
        Write-Host "[nicht gefunden] $root" -ForegroundColor DarkGray
    }
}

if (-not $found) {
    Write-Host ""
    Write-Host "Kein BALDUR.GAM in den Standardordnern gefunden. Suche breiter unter Dokumente ..." -ForegroundColor Yellow
    $documentRoots = @(
        (Join-Path $env:USERPROFILE "Documents")
    )
    if ($env:OneDrive) {
        $documentRoots += (Join-Path $env:OneDrive "Documents")
    }
    foreach ($root in ($documentRoots | Select-Object -Unique)) {
        if (Test-Path $root) {
            $found += Get-ChildItem -Path $root -Filter BALDUR.GAM -File -Recurse
        }
    }
}

Write-Host ""
if ($found) {
    Write-Host "Neueste EET/BG2EE-Spielstände:" -ForegroundColor Cyan
    $found |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 10 @{Name='Saveordner';Expression={$_.DirectoryName}}, LastWriteTime |
        Format-Table -AutoSize

    $latest = $found | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-Host "Neuester Spielstand:" -ForegroundColor Green
    Write-Host $latest.DirectoryName
} else {
    Write-Host "Kein BALDUR.GAM gefunden." -ForegroundColor Red
    Write-Host "Öffne im Spiel einmal Speichern und erstelle einen neuen manuellen Spielstand. Danach dieses Skript erneut starten."
}
