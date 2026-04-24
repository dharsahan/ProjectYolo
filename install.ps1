<#
.SYNOPSIS
    Project Yolo - Configuration Installer for Windows
    This script symlinks or copies config files from the repository to the home directory.
#>

$SourceDir = Join-Path $PSScriptRoot "configs"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupDir = Join-Path $HOME ".yolo_configs_backup_$Timestamp"
$TargetDir = Join-Path $HOME ".yolo"

# --- Functions ---

function Log-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Log-Success {
    param([string]$Message)
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green
}

function Log-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Log-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Print-Banner {
    Write-Host @"
  _____                _              _     __     __    _ 
 |  __ \              (_)            | |    \ \   / /   | |
 | |__) | __ ___       _  ___  ___  | |_    \ \_/ /__ _| | ___ 
 |  ___/ '__/ _ \     | |/ _ \/ __| | __|    \   / _ \ | |/ _ \
 | |   | | | (_) |    | |  __/ (__  | |_      | | (_) | | (_) |
 |_|   |_|  \___/     | |\___|\___|  \__|     |_|\___/|_|\___/ 
                     _/ |                                      
                    |__/                                       
         Configuration Installer for Windows
---------------------------------------------------------------
"@ -ForegroundColor Blue
}

function Setup-Backup {
    if (-not (Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
        Log-Info "Backup directory created at: $BackupDir"
    }
}

function Install-Configs {
    param([bool]$UseCopy)

    # Check if source directory exists
    if (-not (Test-Path $SourceDir)) {
        if (Test-Path "configs.zip") {
            Log-Info "Found configs.zip, unpacking..."
            Expand-Archive -Path "configs.zip" -DestinationPath $SourceDir
        } else {
            Log-Error "Source directory '$SourceDir' or archive (configs.zip) not found!"
            exit 1
        }
    }

    Log-Info "Starting installation from $SourceDir to $TargetDir..."

    # Ensure target directory exists
    if (-not (Test-Path $TargetDir)) {
        New-Item -ItemType Directory -Path $TargetDir | Out-Null
        Log-Success "Created target directory: $TargetDir"
    }

    $Items = Get-ChildItem -Path $SourceDir
    foreach ($Item in $Items) {
        $TargetFile = Join-Path $TargetDir $Item.Name

        # Check if target already exists
        if (Test-Path $TargetFile) {
            Log-Warn "Existing item found: $TargetFile. Moving to backup..."
            Setup-Backup
            Move-Item -Path $TargetFile -Destination $BackupDir
        }

        try {
            if ($UseCopy) {
                Log-Info "Installing (copy): $($Item.Name)"
                Copy-Item -Path $Item.FullName -Destination $TargetFile -Recurse
            } else {
                Log-Info "Installing (link): $($Item.Name)"
                # PowerShell requires New-Item for symbolic links
                New-Item -ItemType SymbolicLink -Path $TargetFile -Value $Item.FullName | Out-Null
            }
            Log-Success "Successfully installed $($Item.Name)"
        } catch {
            Log-Error "Failed to install $($Item.Name): $($_.Exception.Message)"
        }
    }
}

# --- Main ---

Print-Banner

$DryRun = $false
$UseCopy = $false

foreach ($arg in $args) {
    if ($arg -eq "--dry-run") {
        $DryRun = $true
        Log-Warn "DRY RUN MODE ENABLED - No changes will be made."
    } elseif ($arg -eq "--copy") {
        $UseCopy = $true
        Log-Info "COPY MODE ENABLED - Files will be copied instead of symlinked."
    }
}

if ($DryRun) {
    Log-Info "Files that would be installed from $SourceDir:"
    if (Test-Path $SourceDir) {
        Get-ChildItem -Path $SourceDir | Select-Object -ExpandProperty Name
    } else {
        Log-Error "Source directory not found."
    }
    exit 0
}

$Confirmation = Read-Host "This script will link config files to your home directory. Continue? (y/n)"
if ($Confirmation -notmatch "^[Yy]$") {
    Log-Warn "Installation cancelled by user."
    exit 1
}

Install-Configs -UseCopy $UseCopy

Log-Success "Installation complete!"
if (Test-Path $BackupDir) {
    Log-Info "Backups are located in: $BackupDir"
}
