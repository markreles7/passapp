$ErrorActionPreference = 'Stop'
$workspaceRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$releaseRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot 'build\chatgpt-release\PassAppQt'))
$targetRoot = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot 'dist\PassAppQt'))
$targetExe = Join-Path $targetRoot 'PassAppQt.exe'

# All copy targets must remain inside this application workspace.
foreach ($taskPath in @($releaseRoot, $targetRoot)) {
    if (-not $taskPath.StartsWith($workspaceRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Percorso di aggiornamento esterno alla cartella del gestionale.'
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $releaseRoot 'PassAppQt.exe'))) {
    throw 'Versione ChatGPT non preparata: manca build\chatgpt-release\PassAppQt\PassAppQt.exe.'
}
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.Equals($targetExe, [System.StringComparison]::OrdinalIgnoreCase)
}
if ($running) {
    throw 'Chiudi prima PassApp, poi esegui nuovamente INSTALLA_CHATGPT.bat. Nessun file e stato sostituito.'
}

$backupRoot = Join-Path $workspaceRoot ('build\backup-prima-chatgpt-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
if (Test-Path -LiteralPath $targetExe) {
    Copy-Item -LiteralPath $targetExe -Destination $backupRoot
}
$internalRoot = Join-Path $targetRoot '_internal'
if (Test-Path -LiteralPath $internalRoot) {
    Copy-Item -LiteralPath $internalRoot -Destination $backupRoot -Recurse
}
$configPath = Join-Path $targetRoot 'data\config.json'
if (Test-Path -LiteralPath $configPath) {
    Copy-Item -LiteralPath $configPath -Destination (Join-Path $backupRoot 'config.json')
}

New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
New-Item -ItemType Directory -Path $internalRoot -Force | Out-Null
# Preserve operator data, configured paths, installed templates, and assets.
foreach ($entry in Get-ChildItem -LiteralPath (Join-Path $releaseRoot '_internal')) {
    if ($entry.Name -notin @('data', 'templates', 'assets')) {
        Copy-Item -LiteralPath $entry.FullName -Destination $internalRoot -Recurse -Force
    }
}
foreach ($resourceName in @('data', 'templates', 'assets')) {
    $resourceTarget = Join-Path $internalRoot $resourceName
    $resourceSource = Join-Path (Join-Path $releaseRoot '_internal') $resourceName
    if (-not (Test-Path -LiteralPath $resourceTarget) -and (Test-Path -LiteralPath $resourceSource)) {
        Copy-Item -LiteralPath $resourceSource -Destination $internalRoot -Recurse
    }
}
Copy-Item -LiteralPath (Join-Path $releaseRoot 'PassAppQt.exe') -Destination $targetExe -Force
Write-Host 'PassApp aggiornato con ChatGPT. Dati e percorsi conservati.'
Write-Host ('Backup della versione precedente: ' + $backupRoot)
Start-Process -FilePath $targetExe -WorkingDirectory $targetRoot -WindowStyle Hidden
