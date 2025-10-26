#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TrackNote Launcher
Single-click launcher that handles all setup with a loading screen
"""

import sys
import os
import subprocess
import json
from pathlib import Path

# Check if we're running as a PyInstaller bundle
RUNNING_FROM_BUNDLE = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

# Check if we're running from the system Python or venv
IN_VENV = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

# Get the directory where this script is located
if RUNNING_FROM_BUNDLE:
    SCRIPT_DIR = Path(sys._MEIPASS)
else:
    SCRIPT_DIR = Path(__file__).parent.absolute()

VENV_DIR = SCRIPT_DIR / ".venv"

def check_dependencies():
    """Check if all dependencies are installed"""
    required_modules = [
        'pandas', 'openpyxl', 'requests', 'gspread', 
        'google.auth', 'cryptography'
    ]
    
    for module in required_modules:
        try:
            __import__(module.replace('.', '_'))
        except ImportError:
            return False
    return True

def launch_setup_process():
    """Launch the setup process with loading screen"""
    # Try loading screen, but fall back to console if it fails
    try:
        from loading_screen import SetupLoadingScreen
        use_gui = True
    except ImportError:
        print("Loading screen not available. Using console mode.")
        use_gui = False
    except Exception as e:
        print(f"Loading screen error: {e}. Using console mode.")
        use_gui = False
    
    if not use_gui:
        return run_console_setup()
    
    # Try to create loading screen
    try:
        screen = SetupLoadingScreen()
    except Exception as e:
        print(f"Could not create loading screen: {e}")
        print("Falling back to console mode...")
        return run_console_setup()
    
    # Setup success flag
    setup_success = [False]
    
    def run_setup():
        """Run the setup process"""
        try:
            # Step 1: Check Python version
            try:
                screen.update_status(
                    "Checking Python version...",
                    f"Found: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                    10,
                    "Step 1 of 7"
                )
            except Exception:
                pass  # Ignore screen update errors
            
            python_version = sys.version_info
            if python_version < (3, 8):
                try:
                    screen.show_error(
                        "Python 3.8+ required",
                        f"Current version: {sys.version}"
                    )
                except Exception:
                    print(f"ERROR: Python 3.8+ required. Current: {sys.version}")
                return False
            
            # Step 2: Create virtual environment
            if not VENV_DIR.exists():
                try:
                    screen.update_status(
                        "Creating virtual environment...",
                        "This may take a moment",
                        15,
                        "Step 2 of 7"
                    )
                except Exception:
                    pass
                subprocess.run(
                    [sys.executable, "-m", "venv", str(VENV_DIR)],
                    check=True,
                    capture_output=True
                )
            
            # Step 3: Determine pip path
            if sys.platform == "win32":
                pip_path = VENV_DIR / "Scripts" / "pip"
                python_path = VENV_DIR / "Scripts" / "python.exe"
            else:
                pip_path = VENV_DIR / "bin" / "pip"
                python_path = VENV_DIR / "bin" / "python"
            
            # Step 4: Upgrade pip
            try:
                screen.update_status(
                    "Upgrading pip...",
                    "Ensuring latest package manager",
                    25,
                    "Step 3 of 7"
                )
            except Exception:
                pass
            
            try:
                subprocess.run(
                    [str(python_path), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
                    check=True,
                    capture_output=True,
                    timeout=120
                )
            except subprocess.TimeoutExpired:
                # Timeout is not critical, continue anyway
                print("⚠️  pip upgrade timed out, continuing...")
            except subprocess.CalledProcessError as e:
                # Try with --break-system-packages flag (macOS workaround)
                try:
                    subprocess.run(
                        [str(python_path), "-m", "pip", "install", "--upgrade", "pip", "--break-system-packages", "--quiet"],
                        check=True,
                        capture_output=True,
                        timeout=120
                    )
                except Exception:
                    # pip upgrade failure is not critical, continue
                    print("⚠️  pip upgrade failed, continuing with existing version...")
            except Exception:
                print("⚠️  pip upgrade had issues, continuing...")
            
            # Step 5: Install dependencies
            dependencies = [
                ("pandas", "Data processing", 35, "Step 4 of 7"),
                ("openpyxl", "Excel support", 50, "Step 5 of 7"),
                ("requests", "Network communication", 60, "Step 5 of 7"),
                ("gspread", "Google Sheets integration", 70, "Step 6 of 7"),
                ("google-auth", "Google authentication", 80, "Step 6 of 7"),
                ("cryptography", "Security features", 90, "Step 7 of 7")
            ]
            
            for dep_name, dep_desc, progress_val, step in dependencies:
                try:
                    screen.update_status(
                        f"Installing {dep_name}...",
                        dep_desc,
                        progress_val,
                        step
                    )
                except Exception:
                    pass
                
                try:
                    subprocess.run(
                        [str(pip_path), "install", dep_name, "--quiet"],
                        check=True,
                        capture_output=True,
                        timeout=120
                    )
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                    # Try with --break-system-packages on macOS
                    try:
                        subprocess.run(
                            [str(pip_path), "install", dep_name, "--break-system-packages", "--quiet"],
                            check=True,
                            capture_output=True,
                            timeout=120
                        )
                    except Exception as e:
                        try:
                            screen.show_error(
                                f"Failed to install {dep_name}",
                                str(e)
                            )
                        except Exception:
                            print(f"ERROR: Failed to install {dep_name}: {e}")
                        return False
            
            try:
                screen.show_success("Setup complete!")
            except Exception:
                print("Setup complete!")
            setup_success[0] = True
            return True
            
        except Exception as e:
            try:
                screen.show_error("Setup failed", str(e))
            except Exception:
                print(f"ERROR: Setup failed: {e}")
            return False
    
    # Run setup in a separate thread to keep UI responsive
    import threading
    
    def setup_thread():
        try:
            run_setup()
        except Exception as e:
            print(f"Setup thread error: {e}")
        finally:
            try:
                screen.close()
            except Exception:
                pass
    
    try:
        thread = threading.Thread(target=setup_thread, daemon=True)
        thread.start()
        screen.show()
    except Exception as e:
        print(f"Threading error: {e}")
        print("Falling back to console setup...")
        return run_console_setup()
    
    # Check if setup was successful
    return setup_success[0]
    
    # Check if setup was successful
    return setup_success[0]

def run_console_setup():
    """Fallback console-based setup"""
    print("Setting up TrackNote...")
    print()
    
    # Check Python version
    print("Checking Python version...")
    if sys.version_info < (3, 8):
        print(f"ERROR: Python 3.8+ required. Current: {sys.version}")
        return False
    print(f"  OK: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Create venv
    if not VENV_DIR.exists():
        print("\nCreating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
        print("  Created")
    
    # Get paths
    if sys.platform == "win32":
        pip_path = VENV_DIR / "Scripts" / "pip"
        python_path = VENV_DIR / "Scripts" / "python.exe"
    else:
        pip_path = VENV_DIR / "bin" / "pip"
        python_path = VENV_DIR / "bin" / "python"
    
    # Upgrade pip
    print("\nUpgrading pip...")
    subprocess.run([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "--quiet"], check=True)
    print("  Done")
    
    # Install dependencies
    print("\nInstalling dependencies...")
    deps = ["pandas", "openpyxl", "requests", "gspread", "google-auth", "cryptography"]
    for dep in deps:
        print(f"  Installing {dep}...")
        try:
            subprocess.run([str(pip_path), "install", dep, "--quiet"], check=True, timeout=120)
        except:
            subprocess.run([str(pip_path), "install", dep, "--break-system-packages", "--quiet"], check=True, timeout=120)
        print(f"    OK: {dep}")
    
    print("\nSetup complete!")
    return True

def main():
    """Main launcher logic"""
    # When running from bundle, don't try to change directory
    if not RUNNING_FROM_BUNDLE:
        os.chdir(SCRIPT_DIR)
    
    # CRITICAL: Skip venv logic entirely when running from bundle
    if RUNNING_FROM_BUNDLE:
        print("Running from bundled app - skipping venv setup")
    else:
        # Only do venv setup when running from source
        if not IN_VENV:
            if not VENV_DIR.exists() or not check_dependencies():
                # Show loading screen and run setup
                if not launch_setup_process():
                    print("ERROR: Setup failed. Please check the error messages.")
                    sys.exit(1)
            
            # Now re-launch ourselves in the venv
            if sys.platform == "win32":
                python_path = VENV_DIR / "Scripts" / "python.exe"
            else:
                python_path = VENV_DIR / "bin" / "python"
            
            # Re-execute this script in the venv
            os.execv(str(python_path), [str(python_path), __file__] + sys.argv[1:])
    
    # Now we're either in the venv (source) or in bundle (bundled)
    # Check if this is first run (no user_config.json)
    config_dir = Path.home() / "Library" / "Application Support" / "TrackNote"
    if sys.platform == "win32":
        config_dir = Path.home() / "AppData" / "Local" / "TrackNote"
    
    user_config = config_dir / "user_config.json"
    
    # First time setup
    if not user_config.exists():
        print("First time setup...")
        try:
            from setup_wizard import show_setup_wizard
            if not show_setup_wizard():
                print("Setup wizard cancelled")
                sys.exit(1)
        except ImportError as e:
            print(f"ERROR: Could not import setup wizard: {e}")
            print("Please ensure setup_wizard.py is in the same directory")
            sys.exit(1)
    
    # Launch the app
    try:
        from app import main as app_main
        app_main()
    except ImportError as e:
        print(f"ERROR: Could not import app: {e}")
        print("Please ensure app.py is in the same directory")
        sys.exit(1)

if __name__ == "__main__":
    main()