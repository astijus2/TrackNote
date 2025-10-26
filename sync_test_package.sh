#!/usr/bin/env bash
set -euo pipefail

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           TrackNote Customer Package Builder                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

PACKAGE_NAME="TrackNote_$(date +%Y%m%d_%H%M%S)"
PACKAGE_DIR="$HOME/Desktop/$PACKAGE_NAME"

echo "📦 Creating customer package: $PACKAGE_NAME"
echo

# Create package directory
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# ============================================================================
# Copy core application files
# ============================================================================
echo "📄 Copying application files..."

REQUIRED_FILES=(
    "TrackNote_Launcher.py"
    "app.py"
    "ui.py"
    "user_data.py"
    "data_source.py"
    "parsing.py"
    "sheets_cache.py"
    "firebase_sync.py"
    "firebase_setup.py"
    "firebase_gui_dialog.py"
    "setup_wizard.py"
    "license_manager.py"
    "loading_screen.py"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$PACKAGE_DIR/"
        echo "  ✓ $file"
    else
        echo "  ⚠️  Missing: $file"
    fi
done

# ============================================================================
# Copy configuration templates
# ============================================================================
echo
echo "⚙️  Copying configuration files..."
for file in config_template.json firebase_config.json; do
    if [ -f "$file" ]; then
        cp "$file" "$PACKAGE_DIR/"
        echo "  ✓ $file"
    fi
done

# ============================================================================
# Copy optional files
# ============================================================================
echo
echo "📎 Copying optional files..."

# Icon
if [ -f "icon.icns" ]; then
    cp "icon.icns" "$PACKAGE_DIR/"
    echo "  ✓ icon.icns"
fi

# Credentials
if [ -d "credentials" ]; then
    cp -r "credentials" "$PACKAGE_DIR/"
    echo "  ✓ credentials/"
fi

# Version
if [ -f "VERSION" ]; then
    cp "VERSION" "$PACKAGE_DIR/"
else
    echo "1.0.0" > "$PACKAGE_DIR/VERSION"
fi
echo "  ✓ VERSION"

# ============================================================================
# Create macOS launcher script (simple double-click)
# ============================================================================
echo
echo "🚀 Creating START_TRACKNOTE.command..."
cat > "$PACKAGE_DIR/START_TRACKNOTE.command" <<'LAUNCHER'
#!/bin/bash
cd "$(dirname "$0")"
python3 TrackNote_Launcher.py
LAUNCHER

chmod +x "$PACKAGE_DIR/START_TRACKNOTE.command"
echo "  ✓ START_TRACKNOTE.command created"

# ============================================================================
# Create macOS unblock script
# ============================================================================
echo
echo "🔓 Creating UNBLOCK_MACOS.command..."
cat > "$PACKAGE_DIR/UNBLOCK_MACOS.command" <<'UNBLOCK'
#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        TrackNote - macOS Security Unblock Script               ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "This script removes macOS quarantine flags so TrackNote can run."
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "📂 Removing quarantine from: $SCRIPT_DIR"
echo ""

# Remove quarantine from all files in the directory
xattr -dr com.apple.quarantine "$SCRIPT_DIR" 2>/dev/null

# Make launchers executable
chmod +x "$SCRIPT_DIR/START_TRACKNOTE.command" 2>/dev/null
chmod +x "$SCRIPT_DIR/"*.py 2>/dev/null

echo "✅ Done! Quarantine removed."
echo ""
echo "Now you can double-click START_TRACKNOTE.command"
echo ""
UNBLOCK

chmod +x "$PACKAGE_DIR/UNBLOCK_MACOS.command"
echo "  ✓ UNBLOCK_MACOS.command created"

# ============================================================================
# Create macOS security instructions
# ============================================================================
echo
echo "📄 Creating MACOS_SECURITY_FIX.txt..."
cat > "$PACKAGE_DIR/MACOS_SECURITY_FIX.txt" <<'SECURITY'
╔════════════════════════════════════════════════════════════════╗
║            macOS SECURITY WARNING - HOW TO FIX                 ║
╚════════════════════════════════════════════════════════════════╝

If you see a warning about "malware" or "unidentified developer",
this is normal macOS security. TrackNote is safe!

═══════════════════════════════════════════════════════════════

🔓 METHOD 1: Use the Unblock Script (EASIEST)
═══════════════════════════════════════════════════════════════

1. Double-click: UNBLOCK_MACOS.command

2. If that doesn't work, open Terminal and type:
   chmod +x UNBLOCK_MACOS.command
   ./UNBLOCK_MACOS.command

3. Now double-click START_TRACKNOTE.command - it will work!

═══════════════════════════════════════════════════════════════

🔓 METHOD 2: Right-Click Method
═══════════════════════════════════════════════════════════════

1. Right-click (or Control-click) on START_TRACKNOTE.command

2. Select "Open" from the menu

3. Click "Open" in the dialog

Note: Only works the FIRST time you see the warning.

═══════════════════════════════════════════════════════════════

🔓 METHOD 3: Terminal (Direct Launch)
═══════════════════════════════════════════════════════════════

1. Open Terminal

2. Type: cd (then drag TrackNote folder into Terminal)

3. Press Enter

4. Type: python3 TrackNote_Launcher.py

═══════════════════════════════════════════════════════════════

❓ WHY THIS HAPPENS
═══════════════════════════════════════════════════════════════

Apple's "Gatekeeper" blocks apps from unidentified developers.
TrackNote is safe - macOS is just being cautious!

═══════════════════════════════════════════════════════════════
SECURITY

echo "  ✓ MACOS_SECURITY_FIX.txt created"

# ============================================================================
# Create customer README
# ============================================================================
echo
echo "📖 Creating README.txt..."
cat > "$PACKAGE_DIR/README.txt" <<'README'
╔════════════════════════════════════════════════════════════════╗
║                        TrackNote                               ║
║                   Installation Guide                           ║
╚════════════════════════════════════════════════════════════════╝

🚀 QUICK START (2 MINUTES)
════════════════════════════════════════════════════════════════

macOS:
------
1. Double-click: START_TRACKNOTE.command
2. If you get a security warning, see MACOS_SECURITY_FIX.txt
   OR run the unblock script: ./UNBLOCK_MACOS.command
3. Wait for loading screen (2 minutes first time)
4. Complete setup wizard
5. Start using TrackNote!

Windows:
--------
1. Double-click: TrackNote_Launcher.py
2. Wait for loading screen (2 minutes first time)
3. Complete setup wizard
4. Start using TrackNote!

Linux:
------
1. Open terminal in this folder
2. Run: python3 TrackNote_Launcher.py
3. Wait for loading screen
4. Complete setup wizard
5. Start using TrackNote!


📋 WHAT HAPPENS ON FIRST RUN
════════════════════════════════════════════════════════════════

✓ Python environment created automatically
✓ All dependencies installed automatically
✓ Setup wizard appears
✓ You configure your Google Sheet
✓ TrackNote starts!

No terminal commands needed!


🔧 REQUIREMENTS
════════════════════════════════════════════════════════════════

✓ Python 3.8 or newer (pre-installed on macOS/most Linux)
✓ Internet connection (for setup only)
✓ Google account (for data sync)


📊 FEATURES
════════════════════════════════════════════════════════════════

✓ Real-time data sync across multiple computers
✓ Works offline - syncs when online
✓ Keyboard shortcuts for fast workflow
✓ Automatic Google Sheets backup
✓ Firebase cloud sync


⌨️ KEYBOARD SHORTCUTS
════════════════════════════════════════════════════════════════

P         - Toggle "Packaged" (yellow)
S         - Toggle "Sticker" (blue)
Cmd+E     - Edit note
Cmd+S     - Save note
↑/↓       - Navigate rows


🐛 TROUBLESHOOTING
════════════════════════════════════════════════════════════════

"Python not found"
------------------
macOS: Python 3 is pre-installed
Windows: Download from python.org
Linux: sudo apt install python3

"Loading screen stuck"
----------------------
1. Close TrackNote
2. Delete .venv folder in this directory
3. Run START_TRACKNOTE.command again

"Setup wizard errors"
---------------------
Check you have:
✓ Internet connection
✓ Google account
✓ Google Sheets API enabled

"Sync not working"
------------------
1. Check firebase_config.json exists
2. Verify Google Sheet ID is correct
3. Check internet connection
4. View logs in:
   macOS: ~/Library/Application Support/TrackNote/logs/
   Windows: %LOCALAPPDATA%\TrackNote\logs\
   Linux: ~/.local/share/TrackNote/logs/


📞 SUPPORT
════════════════════════════════════════════════════════════════

Configuration files:
- Firebase: ./firebase_config.json
- User config: 
  macOS: ~/Library/Application Support/TrackNote/
  Windows: %LOCALAPPDATA%\TrackNote\
  Linux: ~/.local/share/TrackNote/

Logs location:
- Same as user config + /logs/

Test Firebase:
python3 firebase_setup.py


💡 TIPS
════════════════════════════════════════════════════════════════

• First run takes 2 minutes (setup)
• Later runs start instantly
• Works on multiple computers with same Google Sheet
• Each Sheet ID = separate database
• Offline changes sync automatically


🎯 NEXT STEPS
════════════════════════════════════════════════════════════════

After setup:
1. Configure your Google Sheet in setup wizard
2. Start using TrackNote
3. Install on other computers using same Sheet ID
4. Changes sync automatically!


Enjoy TrackNote! 🎵
README

echo "  ✓ README.txt created"

# ============================================================================
# Create Windows batch launcher
# ============================================================================
echo
echo "🪟 Creating START_TRACKNOTE.bat..."
cat > "$PACKAGE_DIR/START_TRACKNOTE.bat" <<'BATCH'
@echo off
cd /d "%~dp0"
python TrackNote_Launcher.py
pause
BATCH

echo "  ✓ START_TRACKNOTE.bat created"

# ============================================================================
# Create installation test script
# ============================================================================
echo
echo "🧪 Creating test_installation.py..."
cat > "$PACKAGE_DIR/test_installation.py" <<'TEST'
#!/usr/bin/env python3
"""Test that TrackNote can be launched"""
import sys
import os
from pathlib import Path

print("╔════════════════════════════════════════════════════════════════╗")
print("║              TrackNote Installation Test                      ║")
print("╚════════════════════════════════════════════════════════════════╝")
print()

# Check Python version
print("🐍 Python version:", sys.version)
if sys.version_info < (3, 8):
    print("❌ Python 3.8+ required")
    sys.exit(1)
print("  ✓ Python version OK")
print()

# Check files exist
print("📄 Checking files...")
required_files = [
    "TrackNote_Launcher.py",
    "app.py",
    "ui.py",
    "setup_wizard.py",
    "firebase_sync.py"
]

all_exist = True
for file in required_files:
    if Path(file).exists():
        print(f"  ✓ {file}")
    else:
        print(f"  ❌ {file} missing")
        all_exist = False

if not all_exist:
    print("\n❌ Some files are missing!")
    sys.exit(1)

print()
print("✅ Installation looks good!")
print()
print("Next step: Run START_TRACKNOTE.command (macOS) or START_TRACKNOTE.bat (Windows)")
TEST

chmod +x "$PACKAGE_DIR/test_installation.py"
echo "  ✓ test_installation.py created"

# ============================================================================
# Create .gitignore
# ============================================================================
echo
echo "🙈 Creating .gitignore..."
cat > "$PACKAGE_DIR/.gitignore" <<'GITIGNORE'
# Python
__pycache__/
*.py[cod]
*$py.class
.Python
.venv/
venv/
ENV/

# TrackNote specific
user_config.json
*.log
.cache/

# OS
.DS_Store
Thumbs.db
GITIGNORE

echo "  ✓ .gitignore created"

# ============================================================================
# Create ZIP archive
# ============================================================================
echo
echo "📦 Creating ZIP archive..."
cd "$HOME/Desktop"
ZIP_NAME="${PACKAGE_NAME}.zip"
zip -r "$ZIP_NAME" "$PACKAGE_NAME" > /dev/null 2>&1

ZIP_SIZE=$(du -h "$ZIP_NAME" | cut -f1)

# ============================================================================
# Success message
# ============================================================================
echo
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║              ✅ CUSTOMER PACKAGE READY!                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo
echo "📂 Package location:"
echo "   $HOME/Desktop/$ZIP_NAME"
echo
echo "📊 Package size: $ZIP_SIZE"
echo
echo "📤 Send to customer:"
echo "   1. Upload $ZIP_NAME to cloud storage"
echo "   2. Send download link"
echo
echo "👤 Customer instructions:"
echo "   1. Download and unzip"
echo "   2. Double-click START_TRACKNOTE.command (Mac) or .bat (Win)"
echo "   3. Wait for loading screen (2 min first time)"
echo "   4. Complete setup wizard"
echo "   5. Done!"
echo
echo "🎯 Features included:"
echo "   ✓ Automatic dependency installation"
echo "   ✓ Loading screen (no terminal)"
echo "   ✓ Setup wizard"
echo "   ✓ Firebase sync"
echo "   ✓ Multi-platform support"
echo
echo "🧪 Test before sending:"
echo "   cd $PACKAGE_DIR"
echo "   ./START_TRACKNOTE.command"
echo