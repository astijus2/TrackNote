"""
One-time migration script to transfer data from Firebase to SQLite.
Run this once to migrate existing workspace data to the new local database.
"""

from firebase_sync import FirebaseSync, load_firebase_config
from db_manager import DatabaseManager
from user_data import read_user_config
import sys


def migrate_firebase_to_sqlite(workspace_id: str = None) -> bool:
    """
    Migrate all data from Firebase to local SQLite database.
    
    Args:
        workspace_id: Optional workspace ID. If None, will read from config.
    
    Returns:
        True if migration successful, False otherwise.
    """
    
    print("=" * 60)
    print("TrackNote: Firebase → SQLite Migration")
    print("=" * 60)
    
    # Load Firebase config
    firebase_config = load_firebase_config()
    if not firebase_config:
        print("❌ No Firebase config found")
        print("   Make sure you have either:")
        print("   - firebase_config.json (bundled)")
        print("   - User config with Firebase settings")
        return False
    
    # Load workspace ID
    if not workspace_id:
        cfg = read_user_config()
        workspace_id = cfg.get('workspace_id')
    
    if not workspace_id:
        print("❌ No workspace ID found")
        print("   Set up workspace ID first or provide as argument")
        return False
    
    print(f"\n📍 Workspace ID: {workspace_id}")
    
    # Initialize Firebase connection
    print("\n🔗 Connecting to Firebase...")
    try:
        firebase = FirebaseSync(
            firebase_config['database_url'],
            firebase_config['project_id'],
            workspace_id
        )
        
        if not firebase.is_connected():
            print("❌ Failed to connect to Firebase")
            return False
            
    except Exception as e:
        print(f"❌ Firebase connection error: {e}")
        return False
    
    # Initialize SQLite database
    print("\n💾 Initializing local database...")
    try:
        db = DatabaseManager(workspace_id)
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False
    
    # Download data from Firebase
    print("\n📥 Downloading data from Firebase...")
    try:
        transactions = firebase.get_all_transactions()
        statuses = firebase.get_all_status()
        notes = firebase.get_all_notes()
        
        print(f"   ✅ Transactions: {len(transactions)}")
        print(f"   ✅ Statuses: {len(statuses)}")
        print(f"   ✅ Notes: {len(notes)}")
        
    except Exception as e:
        print(f"❌ Firebase download error: {e}")
        db.close()
        return False
    
    if not transactions:
        print("\n⚠️  No transactions found in Firebase")
        print("   This workspace appears to be empty")
        db.close()
        return True
    
    # Import into SQLite
    print(f"\n💾 Importing {len(transactions)} transactions into SQLite...")
    try:
        db.bulk_insert_transactions(transactions)
        print("   ✅ Transactions imported")
        
    except Exception as e:
        print(f"❌ Transaction import error: {e}")
        db.close()
        return False
    
    # Import statuses
    print(f"\n🏷️  Importing {len(statuses)} statuses...")
    try:
        status_updates = {k: (v.get('pkg', 0), v.get('stk', 0)) for k, v in statuses.items()}
        if status_updates:
            db.bulk_update_status(status_updates)
        print("   ✅ Statuses imported")
        
    except Exception as e:
        print(f"❌ Status import error: {e}")
        db.close()
        return False
    
    # Import notes
    print(f"\n📝 Importing {len(notes)} notes...")
    try:
        for key, note_text in notes.items():
            if note_text and note_text.strip():
                db.update_note(key, note_text)
        print("   ✅ Notes imported")
        
    except Exception as e:
        print(f"❌ Note import error: {e}")
        db.close()
        return False
    
    # Verify migration
    print("\n🔍 Verifying migration...")
    try:
        stats = db.get_stats()
        
        print(f"\n{'=' * 60}")
        print("Migration Summary:")
        print(f"{'=' * 60}")
        print(f"  Total transactions: {stats['total']}")
        print(f"  Active: {stats['active']}")
        print(f"  Archived: {stats['archived']}")
        print(f"\n  Status breakdown (active only):")
        print(f"    None: {stats['none']}")
        print(f"    Packaged: {stats['packaged']}")
        print(f"    Sticker: {stats['sticker']}")
        print(f"    Done: {stats['done']}")
        print(f"{'=' * 60}")
        
        # Check integrity
        if not db.check_integrity():
            print("\n⚠️  Database integrity check failed!")
            print("   Data may be corrupted. Try migration again.")
            db.close()
            return False
        
        print("\n✅ Database integrity: OK")
        
    except Exception as e:
        print(f"❌ Verification error: {e}")
        db.close()
        return False
    
    # Cleanup
    db.close()
    
    print("\n" + "=" * 60)
    print("✅ Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. App will now use local SQLite database")
    print("  2. Firebase will be used for sync only")
    print("  3. Restart the app to use new database\n")
    
    return True


if __name__ == "__main__":
    # Allow workspace ID as command line argument
    workspace_id = sys.argv[1] if len(sys.argv) > 1 else None
    
    success = migrate_firebase_to_sqlite(workspace_id)
    sys.exit(0 if success else 1)
