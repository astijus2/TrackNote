#!/usr/bin/env python3
"""
TrackNote Firebase Configuration & Diagnostics
==============================================
Run this to setup and test your Firebase connection.

Usage: python firebase_setup.py
"""

import json
import sys
from pathlib import Path
import time

# Add parent directory to path so we can import user_data
sys.path.insert(0, str(Path(__file__).parent))

from user_data import read_user_config, write_user_config, user_data_dir


def show_current_status():
    """Show current configuration and Firebase status."""
    print("\n" + "=" * 70)
    print("Current Configuration Status")
    print("=" * 70)
    
    # Show config file location
    config_path = user_data_dir() / "user_config.json"
    print(f"\n📁 Config file location:")
    print(f"   {config_path}")
    print(f"   Exists: {'✅ Yes' if config_path.exists() else '❌ No'}")
    
    # Read current config
    try:
        cfg = read_user_config()
        print(f"\n📋 Current data source:")
        source = cfg.get('data_source', cfg.get('source', 'not set'))
        print(f"   {source}")
        
        # Check Firebase config
        firebase_config = cfg.get('firebase_config')
        if firebase_config:
            print(f"\n🔥 Firebase Configuration:")
            print(f"   Database URL: {firebase_config.get('database_url', 'Not set')}")
            print(f"   Project ID: {firebase_config.get('project_id', 'Not set')}")
            print(f"   Status: ✅ Configured")
        else:
            print(f"\n🔥 Firebase: ❌ Not configured")
        
        return firebase_config is not None
        
    except Exception as e:
        print(f"\n❌ Error reading config: {e}")
        return False


def test_firebase_connection(database_url, project_id):
    """Test if Firebase connection works."""
    print("\n" + "=" * 70)
    print("Testing Firebase Connection")
    print("=" * 70)
    
    try:
        from firebase_sync import FirebaseSync
        
        print("\n🔄 Connecting to Firebase...")
        sync = FirebaseSync(database_url, project_id)
        
        if sync.is_connected():
            print("✅ Connection successful!")
            
            # Try to read/write test data
            print("\n📝 Testing read/write operations...")
            test_key = "_test_connection_" + str(int(time.time()))
            
            # Write test
            print(f"   Writing test data (key: {test_key})...")
            sync.set_status(test_key, 1, 0)
            
            # Read test
            print(f"   Reading back data...")
            status = sync.get_all_status()
            
            if test_key in status:
                print("✅ Read/write operations work!")
                
                # Clean up
                print(f"   Cleaning up test data...")
                sync.clear_status(test_key)
                
                print("\n🎉 Firebase is working perfectly!")
                return True
            else:
                print("⚠️ Connected but read/write failed")
                print("   Check your Firebase security rules")
                return False
        else:
            print("❌ Failed to connect to Firebase")
            print("\nPossible issues:")
            print("   1. Database URL is incorrect")
            print("   2. Database doesn't exist")
            print("   3. Network connection problem")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("\nPossible fixes:")
        print("   1. Check your Database URL (should be https://...firebaseio.com)")
        print("   2. Make sure the Realtime Database is created in Firebase Console")
        print("   3. Check Firebase security rules allow read/write access")
        return False


def setup_firebase():
    """Interactive Firebase setup."""
    print("\n" + "=" * 70)
    print("Firebase Setup Wizard")
    print("=" * 70)
    print()
    print("You need ONE Firebase project for ALL clients:")
    print()
    print("1️⃣  Realtime Database URL")
    print("   📍 Go to: Firebase Console → Realtime Database")
    print("   📋 Example: https://tracknote-app.firebaseio.com")
    print()
    print("2️⃣  Project ID")
    print("   📍 Go to: Firebase Console → Project Settings")
    print("   📋 Example: tracknote-app")
    print()
    print("⚠️  NOTE: All clients will use this SAME Firebase project")
    print("   Data is automatically separated by their Google Sheet ID")
    print()
    print("=" * 70)
    print()
    print()
    
    # Get Database URL
    while True:
        database_url = input("🔥 Enter your Firebase Database URL: ").strip()
        if not database_url:
            print("❌ Database URL is required!")
            retry = input("   Try again? (yes/no): ").lower()
            if retry != 'yes':
                return False
            continue
        
        # Clean up URL
        database_url = database_url.rstrip('/')
        
        # Validate URL format
        if not database_url.startswith('https://'):
            print("⚠️  URL should start with 'https://'")
            database_url = 'https://' + database_url.lstrip('http://')
            print(f"   Using: {database_url}")
        
        if not '.firebaseio.com' in database_url:
            print("⚠️  URL should end with '.firebaseio.com'")
            use_anyway = input("   Use this URL anyway? (yes/no): ").lower()
            if use_anyway != 'yes':
                continue
        
        break
    
    # Get Project ID
    while True:
        project_id = input("\n🆔 Enter your Firebase Project ID: ").strip()
        if not project_id:
            print("❌ Project ID is required!")
            retry = input("   Try again? (yes/no): ").lower()
            if retry != 'yes':
                return False
            continue
        break
    
    print()
    
    # Test connection
    if not test_firebase_connection(database_url, project_id):
        print("\n⚠️  Connection test failed.")
        save_anyway = input("\n💾 Save configuration anyway? (yes/no): ").lower()
        if save_anyway != 'yes':
            print("❌ Setup cancelled.")
            return False
    
    # Save to config
    print("\n💾 Saving Firebase configuration...")
    try:
        cfg = read_user_config()
        cfg['firebase_config'] = {
            'database_url': database_url,
            'project_id': project_id
        }
        write_user_config(cfg)
        
        print("✅ Configuration saved!")
        print()
        print("🎉 Next steps:")
        print("   1. Restart TrackNote")
        print("   2. Your changes will sync across all computers")
        print("   3. Make sure all computers use this same Firebase configuration")
        print()
        return True
        
    except Exception as e:
        print(f"❌ Failed to save configuration: {e}")
        return False


def remove_firebase_config():
    """Remove Firebase configuration."""
    print("\n🗑️  Removing Firebase Configuration")
    print("=" * 70)
    
    try:
        cfg = read_user_config()
        if 'firebase_config' in cfg:
            del cfg['firebase_config']
            write_user_config(cfg)
            print("✅ Firebase configuration removed")
            print("\n⚠️  Note: TrackNote will now use local storage only")
            print("   Changes will NOT sync between computers")
        else:
            print("ℹ️  No Firebase configuration to remove")
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main menu."""
    print("\n" + "=" * 70)
    print("TrackNote Firebase Configuration & Diagnostics")
    print("=" * 70)
    
    # Show current status first
    has_firebase = show_current_status()
    
    while True:
        print("\n" + "=" * 70)
        print("What would you like to do?")
        print("=" * 70)
        print()
        print("1. 🔥 Setup/Update Firebase Configuration")
        print("2. 🧪 Test Current Firebase Connection")
        print("3. 📋 Show Current Configuration")
        print("4. 🗑️  Remove Firebase Configuration")
        print("5. 🚪 Exit")
        print()
        
        choice = input("Choose an option (1-5): ").strip()
        
        if choice == '1':
            setup_firebase()
        elif choice == '2':
            cfg = read_user_config()
            fb = cfg.get('firebase_config')
            if fb:
                test_firebase_connection(
                    fb.get('database_url', ''),
                    fb.get('project_id', '')
                )
            else:
                print("\n❌ Firebase not configured yet!")
                print("   Choose option 1 to set it up.")
        elif choice == '3':
            show_current_status()
        elif choice == '4':
            confirm = input("\n⚠️  Are you sure you want to remove Firebase? (yes/no): ").lower()
            if confirm == 'yes':
                remove_firebase_config()
        elif choice == '5':
            print("\n👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        print("\nIf you need help, check:")
        print("   • Firebase Console: https://console.firebase.google.com")
        print("   • Your Database URL should end with '.firebaseio.com'")
        print("   • Make sure Realtime Database is created (not Firestore)")
        print("   • Check security rules allow read/write access")
