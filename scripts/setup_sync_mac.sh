#!/bin/bash
# setup_sync_mac.sh
# Automates linking the cloud-synced .gemini folder on MacOS.

# Default attempt for Google Drive
CLOUD_PATH="$HOME/Google Drive"

# Try to find the CloudStorage mount if standard folder doesn't exist
if [ ! -d "$CLOUD_PATH" ]; then
    # Look for GoogleDrive mount in Library/CloudStorage
    GD_MOUNT=$(find "$HOME/Library/CloudStorage" -maxdepth 1 -name "GoogleDrive-*" -type d -print -quit)
    if [ ! -z "$GD_MOUNT" ]; then
        CLOUD_PATH="$GD_MOUNT/My Drive"
    fi
fi

GEMINI_CLOUD_PATH="$CLOUD_PATH/.gemini"
GEMINI_LOCAL_PATH="$HOME/.gemini"

echo "Using Cloud Path: $GEMINI_CLOUD_PATH"

if [ ! -d "$GEMINI_CLOUD_PATH" ]; then
    echo "Error: Could not find synced .gemini folder at $GEMINI_CLOUD_PATH"
    echo "Please ensure your cloud provider has finished syncing the folder from Windows first."
    exit 1
fi

if [ -d "$GEMINI_LOCAL_PATH" ] && [ ! -L "$GEMINI_LOCAL_PATH" ]; then
    echo "Warning: A local .gemini folder already exists and is not a link."
    read -p "Do you want to back it up and replace it with the link? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        mv "$GEMINI_LOCAL_PATH" "${GEMINI_LOCAL_PATH}_backup_$(date +%s)"
        echo "Backed up existing .gemini."
    else
        echo "Aborting."
        exit 1
    fi
fi

if [ -L "$GEMINI_LOCAL_PATH" ]; then
    echo "Link already exists."
    ls -l "$GEMINI_LOCAL_PATH"
else
    echo "Creating symbolic link..."
    ln -s "$GEMINI_CLOUD_PATH" "$GEMINI_LOCAL_PATH"
    echo "Success! Linked $GEMINI_LOCAL_PATH -> $GEMINI_CLOUD_PATH"
fi
