# setup_sync_windows.ps1
# Automates moving .gemini to a cloud folder and creating a junction point.

param (
    [string]$CloudPath = "G:\My Drive" # Default for Google Drive Desktop
)

# Try to auto-detect if default doesn't exist
if (!(Test-Path -Path $CloudPath)) {
    $PotentialPaths = @(
        "$env:USERPROFILE\Google Drive",
        "G:\My Drive"
    )
    foreach ($p in $PotentialPaths) {
        if (Test-Path -Path $p) {
            $CloudPath = $p
            break
        }
    }
}


$GeminiLocalPath = "$HOME\.gemini"
$GeminiCloudPath = Join-Path -Path $CloudPath -ChildPath ".gemini"

Write-Host "Checking paths..."
Write-Host "  Local .gemini: $GeminiLocalPath"
Write-Host "  Cloud Sync Path: $GeminiCloudPath"

# Check if Antigravity is running (simple check, might not catch everything but good practice)
# Note: The user should have manually closed the main app, but background processes might exist.
# This script is intended to be run by the user in a separate terminal.

if (!(Test-Path -Path $GeminiLocalPath)) {
    Write-Error "Error: Could not find local .gemini folder at $GeminiLocalPath"
    exit 1
}

if (!(Test-Path -Path $CloudPath)) {
    Write-Error "Error: Cloud path $CloudPath does not exist. Please specify a valid cloud sync root."
    exit 1
}

if (Test-Path -Path $GeminiCloudPath) {
    Write-Warning "Target folder $GeminiCloudPath already exists."
    $response = Read-Host "Do you want to skip moving and just try to link? (y/n)"
    if ($response -ne 'y') {
        exit
    }
} else {
    Write-Host "Moving .gemini to $CloudPath..."
    # Move-Item can be slow for large folders, but it preserves metadata better than copy-delete
    try {
        Move-Item -Path $GeminiLocalPath -Destination $CloudPath -Force -ErrorAction Stop
        Write-Host "Move complete."
    } catch {
        Write-Error "Failed to move folder. Ensure Antigravity is completely closed. Error: $_"
        exit 1
    }
}

# Create Junction
if (Test-Path -Path $GeminiLocalPath) {
    # If the folder still exists (e.g. move failed or it was recreated), we can't link.
    # Unless we just moved it? Move-Item removes the source. 
    # If it exists now, something is wrong or it wasn't moved.
    Write-Error "Local .gemini folder still exists at $GeminiLocalPath. Cannot create junction."
    exit 1
}

Write-Host "Creating Junction..."
cmd /c mklink /J "$GeminiLocalPath" "$GeminiCloudPath"

if ($LASTEXITCODE -eq 0) {
    Write-Host "SUCCESS! Antigravity sync setup on Windows is complete."
} else {
    Write-Error "Failed to create junction."
}
