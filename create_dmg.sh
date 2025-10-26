#!/usr/bin/env bash
set -euo pipefail

echo "=================================================================="
echo "Creating TrackNote DMG Installer (Free - No Signing)"
echo "=================================================================="
echo

APP_NAME="TrackNote"
DIST="dist"
APP="${DIST}/${APP_NAME}.app"
VERSION="$(tr -d '\r\n' < VERSION)"
STAGE="${DIST}/${APP_NAME}-${VERSION}-staging"
DMG="${DIST}/${APP_NAME}-${VERSION}-mac-arm64.dmg"

# Check if app exists
if [[ ! -d "$APP" ]]; then
  echo "❌ ERROR: $APP not found. Run ./build_mac.sh first." >&2
  exit 1
fi

# Clean previous DMG
rm -rf "$STAGE" "$DMG"
mkdir -p "$STAGE"

echo "📦 Preparing DMG contents..."

# Copy app
cp -R "$APP" "$STAGE/"

# Create Applications symlink
ln -s /Applications "$STAGE/Applications"

# Create README with installation instructions
cat > "$STAGE/HOW TO INSTALL.txt" << 'EOF'
╔══════════════════════════════════════════════════════════════════╗
║                    TrackNote Installation                         ║
╚══════════════════════════════════════════════════════════════════╝

📦 STEP 1: Install
──────────────────
   Drag TrackNote.app to the Applications folder →


🔓 STEP 2: First Launch (IMPORTANT!)
──────────────────────────────────────
   macOS will block the app because it's not signed yet.
   This is NORMAL and SAFE. Here's how to open it:

   METHOD 1 (Easiest):
   ──────────────────
   1. DON'T double-click TrackNote yet
   2. Right-click (or Control+click) on TrackNote.app
   3. Select "Open" from the menu
   4. Click "Open" in the dialog
   5. ✅ Done! macOS will remember this forever

   METHOD 2 (Terminal):
   ────────────────────
   1. Open Terminal (⌘+Space, type "Terminal")
   2. Copy and paste this command:
      
      xattr -cr /Applications/TrackNote.app
   
   3. Press Enter
   4. ✅ Done! Now open TrackNote normally


🎉 STEP 3: Enjoy!
─────────────────
   After the first launch, TrackNote will open normally
   like any other app. You only need to do Step 2 ONCE.


❓ Why This Happens
───────────────────
   TrackNote isn't signed with an Apple certificate yet
   (costs $99/year). The app is 100% safe - this bypass
   just tells macOS you trust it.

   Once we have enough customers, we'll get proper signing
   and this step won't be needed anymore!


📧 Need Help?
─────────────
   Contact: your-email@example.com
   Website: yourwebsite.com

EOF

echo "✅ Created installation instructions"

# Create DMG
echo
echo "🔨 Creating DMG..."
hdiutil create \
  -volname "${APP_NAME} ${VERSION}" \
  -srcfolder "$STAGE" \
  -ov -format UDZO "$DMG"

# Create checksum
echo
echo "🔐 Creating checksum..."
( cd "$DIST" && shasum -a 256 "$(basename "$DMG")" > "$(basename "$DMG").sha256" )

# Get DMG size
DMG_SIZE=$(du -h "$DMG" | cut -f1)

echo
echo "=================================================================="
echo "✅ DMG Created Successfully!"
echo "=================================================================="
echo
echo "📦 DMG: $DMG"
echo "📊 Size: $DMG_SIZE"
echo "🔐 Checksum: ${DMG}.sha256"
echo
echo "📤 Ready to distribute!"
echo
echo "⚠️  IMPORTANT: Include installation instructions"
echo "   Users MUST follow the HOW TO INSTALL.txt steps"
echo
echo "💡 TIP: When you get paying clients, upgrade to Apple"
echo "   Developer account ($99/year) for automatic signing"
echo
