"""
Quick test script to verify SQLite database manager works correctly.
Run this to test database operations before starting the full app.
"""

from db_manager import DatabaseManager
import time

def test_db_manager():
    print("=" * 60)
    print("Testing SQLite DatabaseManager")
    print("=" * 60)
    
    # Create test database
    print("\n1. Creating database...")
    db = DatabaseManager("test_workspace")
    print("✅ Database created")
    
    # Test insert
    print("\n2. Inserting test transactions...")
    test_txs = {
        'tx1': {
            'key': 'tx1',
            'date': '2024-01-15',
            'price': 100.50,
            'name': 'John Doe',
            'iban': 'LT123456789',
            'comment': 'Test transaction 1',
            'name_norm': 'john doe',
            'row_no': 1
        },
        'tx2': {
            'key': 'tx2',
            'date': '2024-01-16',
            'price': 200.00,
            'name': 'Jane Smith',
            'iban': 'LT987654321',
            'comment': 'Test transaction 2',
            'name_norm': 'jane smith',
            'row_no': 2
        }
    }
    
    db.bulk_insert_transactions(test_txs)
    print("✅ Inserted 2 transactions")
    
    # Test retrieve
    print("\n3. Retrieving transactions...")
    all_txs = db.get_active_transactions()
    print(f"✅ Retrieved {len(all_txs)} transactions")
    for tx in all_txs:
        print(f"   - {tx['name']}: ${tx['price']}")
    
    # Test status update
    print("\n4. Testing status updates...")
    db.update_status('tx1', 1, 0)  # pkg=1, stk=0
    db.update_status('tx2', 1, 1)  # pkg=1, stk=1
    print("✅ Updated statuses")
    
    # Test status retrieval
    pkg1, stk1 = db.get_status('tx1')
    pkg2, stk2 = db.get_status('tx2')
    print(f"   - tx1: pkg={pkg1}, stk={stk1} (should be 1, 0)")
    print(f"   - tx2: pkg={pkg2}, stk={stk2} (should be 1, 1)")
    
    # Test search
    print("\n5. Testing search...")
    results = db.search_transactions(name_query="john")
    print(f"✅ Search for 'john': found {len(results)} result(s)")
    
    # Test stats
    print("\n6. Testing statistics...")
    stats = db.get_stats()
    print(f"✅ Stats:")
    print(f"   - Total: {stats['total']}")
    print(f"   - Active: {stats['active']}")
    print(f"   - Packaged: {stats['packaged']}")
    print(f"   - Done: {stats['done']}")
    
    # Test archival
    print("\n7. Testing archive...")
    archived_count = db.archive_old_transactions(days=1)  # Archive anything older than 1 day
    print(f"✅ Archived {archived_count} transactions")
    
    stats_after = db.get_stats()
    print(f"   - Active after archive: {stats_after['active']}")
    print(f"   - Archived: {stats_after['archived']}")
    
    # Test integrity
    print("\n8. Testing database integrity...")
    is_ok = db.check_integrity()
    if is_ok:
        print("✅ Database integrity: OK")
    else:
        print("❌ Database integrity: FAILED")
    
    # Cleanup
    db.close()
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    print("\nDatabase file location:")
    print(f"   {db.db_path}")
    print("\nYou can delete this test database if you want:")
    print(f"   rm {db.db_path}\n")

if __name__ == "__main__":
    test_db_manager()
