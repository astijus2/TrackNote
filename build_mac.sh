#!/bin/bash
# TrackNote Professional Build Script
# This creates a proper .app bundle that works on any Mac

set -e  # Exit on error

echo "🚀 TrackNote Professional Build Script"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check Python version
echo "📋 Step 1/6: Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "   Found: Python $PYTHON_VERSION"

MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]); then
    echo -e "${RED}❌ Error: Python 3.9+ required${NC}"
    exit 1
fi
echo -e "${GREEN}   ✓ Python version OK${NC}"
echo ""

# Step 2: Create/activate virtual environment
echo "📦 Step 2/6: Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "   Created new virtual environment"
else
    echo "   Using existing virtual environment"
fi

source .venv/bin/activate
echo -e "${GREEN}   ✓ Virtual environment ready${NC}"
echo ""

# Step 3: Install/upgrade dependencies
echo "📥 Step 3/6: Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "${GREEN}   ✓ All dependencies installed${NC}"
echo ""

# Step 4: Fix Python 3.9 compatibility
echo "🔧 Step 4/6: Ensuring Python 3.9 compatibility..."
if ! grep -q "from __future__ import annotations" app.py; then
    # Add future annotations at the beginning
    echo "from __future__ import annotations" | cat - app.py > app_temp.py
    mv app_temp.py app.py
    echo "   Added Python 3.9 compatibility fix"
else
    echo "   Compatibility fix already present"
fi
echo -e "${GREEN}   ✓ Code is Python 3.9 compatible${NC}"
echo ""

# Step 5: Clean previous builds
echo "🧹 Step 5/6: Cleaning previous builds..."
rm -rf build dist
echo -e "${GREEN}   ✓ Clean slate ready${NC}"
echo ""

# Step 6: Build the app
echo "🏗️  Step 6/6: Building TrackNote.app..."
echo "   This may take 2-3 minutes..."

# Create/update .spec file if needed
if [ ! -f "TrackNote.spec" ]; then
    echo "   Creating PyInstaller spec file..."
    cat > TrackNote.spec << 'EOF'
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['TrackNote_Launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('credentials', 'credentials'),
        ('icon.icns', '.'),
        ('VERSION', '.'),
        ('config_template.json', '.'),
        ('*.py', '.'),
    ],
    hiddenimports=[
        'pandas',
        'openpyxl',
        'gspread',
        'google.auth',
        'cryptography',
        'requests',
        'ttkbootstrap',
        'firebase_setup',
        'firebase_sync',
        'firebase_gui_dialog',
        'data_source',
        'setup_wizard',
        'loading_screen',
        'ui',
        'user_data',
        'parsing',
        'sheets_cache',
        'license_manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TrackNote',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TrackNote',
)

app = BUNDLE(
    coll,
    name='TrackNote.app',
    icon='icon.icns',
    bundle_identifier='com.tracknote.app',
    info_plist={
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHumanReadableCopyright': 'TrackNote',
    },
)
EOF
fi

# Run PyInstaller
pyinstaller TrackNote.spec --noconfirm --clean

if [ -d "dist/TrackNote.app" ]; then
    echo -e "${GREEN}   ✓ Build successful!${NC}"
    echo ""
    echo "═══════════════════════════════════════"
    echo -e "${GREEN}✅ BUILD COMPLETE!${NC}"
    echo "═══════════════════════════════════════"
    echo ""
    echo "📱 Your app is ready: dist/TrackNote.app"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Test the app: open dist/TrackNote.app"
    echo "   2. Compress for distribution: "
    echo "      cd dist && zip -r TrackNote.zip TrackNote.app"
    echo "   3. Send TrackNote.zip to your client"
    echo ""
    echo "💡 Your client just needs to:"
    echo "   - Unzip the file"
    echo "   - Drag TrackNote.app to Applications"
    echo "   - Double-click to open"
    echo ""
else
    echo -e "${RED}❌ Build failed - check errors above${NC}"
    exit 1
fi
