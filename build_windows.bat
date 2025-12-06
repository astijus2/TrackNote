@echo off
REM TrackNote Professional Build Script for Windows
REM This creates a standalone .exe that works on any Windows PC

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   TrackNote Professional Build Script
echo ========================================
echo.

REM Step 1: Check Python version
echo [Step 1/6] Checking Python version...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.9+ from python.org
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo    Found: Python %PYTHON_VERSION%

REM Extract major and minor version
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)

if %MAJOR% LSS 3 (
    echo ERROR: Python 3.9+ required
    pause
    exit /b 1
)
if %MAJOR% EQU 3 if %MINOR% LSS 9 (
    echo ERROR: Python 3.9+ required
    pause
    exit /b 1
)
echo    OK: Python version compatible
echo.

REM Step 2: Create/activate virtual environment
echo [Step 2/6] Setting up virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo    Created new virtual environment
) else (
    echo    Using existing virtual environment
)

call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)
echo    OK: Virtual environment ready
echo.

REM Step 3: Install/upgrade dependencies
echo [Step 3/6] Installing dependencies...
echo    This may take a few minutes...
python -m pip install --upgrade pip --quiet
if %errorlevel% neq 0 (
    echo WARNING: pip upgrade failed, continuing...
)

pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo    OK: All dependencies installed
echo.

REM Step 4: Check for icon file
echo [Step 4/6] Checking icon file...
if not exist "icon.ico" (
    echo    WARNING: icon.ico not found, will use default icon
    echo    You can generate icon.ico from icon.png using:
    echo    - Online converter like cloudconvert.com
    echo    - ImageMagick: convert icon.png -resize 256x256 icon.ico
)
echo.

REM Step 5: Clean previous builds
echo [Step 5/6] Cleaning previous builds...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist
echo    OK: Clean slate ready
echo.

REM Step 6: Build the application
echo [Step 6/6] Building TrackNote.exe...
echo    This may take 2-3 minutes...
echo.

REM Check if spec file exists
if not exist "TrackNote_Windows.spec" (
    echo ERROR: TrackNote_Windows.spec not found
    echo Please ensure TrackNote_Windows.spec is in the current directory
    pause
    exit /b 1
)

pyinstaller TrackNote_Windows.spec --noconfirm --clean

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo   BUILD FAILED
    echo ========================================
    echo.
    echo Please check the error messages above
    pause
    exit /b 1
)

if exist "dist\TrackNote\TrackNote.exe" (
    echo.
    echo ========================================
    echo   BUILD COMPLETE!
    echo ========================================
    echo.
    echo Your app is ready: dist\TrackNote\TrackNote.exe
    echo.
    echo Next steps:
    echo   1. Test the app: dist\TrackNote\TrackNote.exe
    echo   2. Compress for distribution:
    echo      Right-click dist\TrackNote folder
    echo      Send to ^> Compressed (zipped) folder
    echo   3. Send TrackNote.zip to your client
    echo.
    echo Your client just needs to:
    echo   - Unzip the file
    echo   - Double-click TrackNote.exe to run
    echo.
) else (
    echo.
    echo ========================================
    echo   BUILD FAILED
    echo ========================================
    echo.
    echo dist\TrackNote\TrackNote.exe was not created
    echo Please check errors above
    pause
    exit /b 1
)

pause
