#!/bin/bash

# Project Yolo - Configuration Installer for Linux
# This script symlinks or copies config files from the repository to the home directory.

# --- Configuration ---
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/configs"
BACKUP_DIR="$HOME/.yolo_configs_backup_$(date +%Y%m%d_%H%M%S)"
TARGET_DIR="$HOME/.yolo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Functions ---

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_banner() {
    echo -e "${BLUE}"
    echo "  _____                _              _     __     __    _ "
    echo " |  __ \              (_)            | |    \ \   / /   | |"
    echo " | |__) | __ ___       _  ___  ___  | |_    \ \_/ /__ _| | ___ "
    echo " |  ___/ '__/ _ \     | |/ _ \/ __| | __|    \   / _ \ | |/ _ \\"
    echo " | |   | | | (_) |    | |  __/ (__  | |_      | | (_) | | (_) |"
    echo " |_|   |_|  \___/     | |\___|\___|  \__|     |_|\___/|_|\___/ "
    echo "                     _/ |                                      "
    echo "                    |__/                                       "
    echo -e "         Configuration Installer for Linux${NC}"
    echo "---------------------------------------------------------------"
}

setup_backup() {
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR"
        log_info "Backup directory created at: $BACKUP_DIR"
    fi
}

install_configs() {
    # Check if we need to unpack an archive first
    if [ ! -d "$SOURCE_DIR" ]; then
        if [ -f "configs.tar.gz" ]; then
            log_info "Found configs.tar.gz, unpacking..."
            mkdir -p "$SOURCE_DIR"
            tar -xzf configs.tar.gz -C "$SOURCE_DIR"
        elif [ -f "configs.zip" ]; then
            log_info "Found configs.zip, unpacking..."
            mkdir -p "$SOURCE_DIR"
            unzip configs.zip -d "$SOURCE_DIR"
        else
            log_error "Source directory '$SOURCE_DIR' or archive (configs.tar.gz/zip) not found!"
            exit 1
        fi
    fi

    log_info "Starting installation from $SOURCE_DIR to $TARGET_DIR..."

    # Ensure target directory exists
    if [ ! -d "$TARGET_DIR" ]; then
        mkdir -p "$TARGET_DIR"
        log_success "Created target directory: $TARGET_DIR"
    fi

    # Find all files in the source directory (excluding the directory itself)
    find "$SOURCE_DIR" -maxdepth 1 -not -path "$SOURCE_DIR" | while read -r src; do
        filename=$(basename "$src")
        target="$TARGET_DIR/$filename"

        # Check if target already exists
        if [ -e "$target" ] || [ -L "$target" ]; then
            log_warn "Existing file found: $target. Moving to backup..."
            setup_backup
            mv "$target" "$BACKUP_DIR/"
        fi

        # Create symlink or copy
        if [ "$USE_COPY" = true ]; then
            log_info "Installing (copy): $filename"
            cp -r "$src" "$target"
        else
            log_info "Installing (link): $filename"
            ln -s "$src" "$target"
        fi
        
        if [ $? -eq 0 ]; then
            log_success "Successfully installed $filename"
        else
            log_error "Failed to install $filename"
        fi
    done
}

# --- Main ---

print_banner

# Flags
DRY_RUN=false
USE_COPY=false

for arg in "$@"; do
    if [ "$arg" == "--dry-run" ]; then
        DRY_RUN=true
        log_warn "DRY RUN MODE ENABLED - No changes will be made."
    elif [ "$arg" == "--copy" ]; then
        USE_COPY=true
        log_info "COPY MODE ENABLED - Files will be copied instead of symlinked."
    fi
done

if [ "$DRY_RUN" = true ]; then
    log_info "Files that would be installed from $SOURCE_DIR:"
    if [ -d "$SOURCE_DIR" ]; then
        ls -A "$SOURCE_DIR"
    else
        log_error "Source directory not found."
    fi
    exit 0
fi

# Ask for confirmation
read -p "This script will link config files to your home directory. Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warn "Installation cancelled by user."
    exit 1
fi

install_configs

log_success "Installation complete!"
echo "Backups (if any) are located in: $BACKUP_DIR"
