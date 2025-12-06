# TrackNote

**Professional transaction tracking and bank statement management application**

TrackNote helps you organize and track financial transactions from bank statements with cloud sync across all your devices.

## Features

- 📊 **Bank Statement Import** - Import transactions from Excel bank statements
- ☁️ **Cloud Sync** - Automatic synchronization across Mac and Windows
- 🎨 **Visual Organization** - Color-coded status tracking (packaged, sticker, both)
- 🔍 **Smart Filtering** - Filter by name, date range, and more
- ✅ **Bulk Actions** - Select multiple transactions for batch operations
- 🔐 **Secure Licensing** - Ed25519 cryptographic license validation
- 📱 **Cross-Platform** - Works seamlessly on macOS and Windows

## System Requirements

### macOS
- macOS 10.13 or later
- Python 3.9+ (for building from source)
- Internet connection for cloud sync

### Windows
- Windows 10 or later
- Python 3.9+ (for building from source)
- Internet connection for cloud sync

## Installation

### For End Users

#### macOS
1. Download `TrackNote-Installer.dmg` from the releases page
2. Open the DMG file
3. Drag TrackNote to your Applications folder
4. Double-click to launch

#### Windows
1. Download `TrackNote-Windows.zip` from the releases page
2. Right-click and select "Extract All"
3. Open the extracted folder
4. Double-click `TrackNote.exe` to launch

### For Developers

#### Building from Source - macOS

```bash
# Clone the repository
git clone <your-repo-url>
cd Track_Note

# Run the build script
./build_mac.sh

# The app will be created at: dist/TrackNote.app
```

#### Building from Source - Windows

```batch
REM Clone the repository
git clone <your-repo-url>
cd Track_Note

REM Run the build script
build_windows.bat

REM The executable will be created at: dist\TrackNote\TrackNote.exe
```

## First-Time Setup

When you launch TrackNote for the first time:

1. **Create Workspace ID** - Enter a unique workspace ID for cloud sync
   - Use the same ID on all your computers to sync data
   - Example: `my-business-2024`

2. **Import Bank Statement** (Optional)
   - Click "Import Statement"
   - Select your bank's Excel statement file
   - Supported format: Swedbank Excel statements

3. **Start Tracking**
   - View all transactions in the main window
   - Use filters to find specific transactions
   - Mark transactions with status colors

## Usage

### Importing Bank Statements

1. Click **File > Import Statement** (or use the Import button)
2. Select your bank statement Excel file
3. TrackNote will parse and import transactions
4. Duplicates are automatically detected and skipped

### Organizing Transactions

- **Color Status**: Click the status buttons to mark transactions
  - 🟡 Packaged (Yellow)
  - 🔵 Sticker (Blue)
  - 🟢 Both (Green)
- **Bulk Selection**: Check multiple items then apply status to all
- **Filters**: Use name and date filters to focus on specific transactions

### Cloud Sync

- All changes sync automatically to the cloud
- Changes appear on all devices using the same Workspace ID
- No manual sync required

### Keyboard Shortcuts

- `Cmd/Ctrl + A` - Select all
- `Cmd/Ctrl + D` - Clear selection
- `Cmd/Ctrl + Z` - Undo last action

## Building for Distribution

### macOS DMG

After running `./build_mac.sh`:

```bash
# Create DMG installer (optional)
./create_dmg.sh  # if available
```

### Windows ZIP

After running `build_windows.bat`:

1. Navigate to `dist\TrackNote` folder
2. Right-click the folder
3. Select "Send to > Compressed (zipped) folder"
4. Distribute the ZIP file

## Configuration

### Firebase Setup (for developers)

1. Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com)
2. Create a Realtime Database
3. Download the configuration
4. Place credentials in the `credentials/` directory

### License System

TrackNote uses a cryptographic licensing system:
- 14-day trial period for new installations
- Lifetime licenses can be generated and validated
- Machine fingerprinting prevents license sharing

## Project Structure

```
Track_Note/
├── app.py                  # Main application logic
├── ui.py                   # User interface components
├── parsing.py              # Bank statement parser
├── firebase_sync.py        # Cloud synchronization
├── user_data.py            # User configuration management
├── TrackNote_Launcher.py   # Application launcher
├── build_mac.sh            # macOS build script
├── build_windows.bat       # Windows build script
├── requirements.txt        # Python dependencies
└── credentials/            # Firebase credentials (not committed)
```

## Dependencies

- **pandas** - Data processing
- **openpyxl** - Excel file handling
- **gspread** - Google Sheets integration (legacy)
- **google-auth** - Authentication
- **ttkbootstrap** - Modern UI theming
- **pyinstaller** - Application packaging
- **cryptography** - License validation
- **requests** - Network communication

## Troubleshooting

### macOS: "App is damaged" message

```bash
xattr -cr /Applications/TrackNote.app
```

### Windows: Antivirus blocking

Some antivirus software may flag PyInstaller executables as suspicious. Add TrackNote.exe to your antivirus exclusions.

### Sync not working

1. Check your internet connection
2. Verify Workspace ID is correct (case-sensitive)
3. Check Firebase configuration

### Import fails

1. Ensure the file is a Swedbank Excel statement (.xlsx)
2. Check that all required columns are present
3. Try exporting a fresh statement from your bank

## Version

Current version: **0.1.0**

## License

Proprietary - Licensed software with trial period and lifetime activation options.

## Support

For support, feature requests, or bug reports, please contact your software provider.

---

**Made with ❤️ for efficient transaction tracking**
