"""
SQLite Database Manager for TrackNote
Handles local storage of transactions, status, and notes with high performance.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time
from user_data import user_data_dir


class DatabaseManager:
    """Manages local SQLite database for transactions."""
    
    def __init__(self, workspace_id: str):
        """Initialize database connection and create schema if needed."""
        self.workspace_id = workspace_id
        self.db_path = user_data_dir() / f"tracknote_{workspace_id}.db"
        self.conn = None
        self._initialize_db()
    
    def _initialize_db(self):
        """Create database and tables if they don't exist."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Return dict-like rows
        
        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")
        
        # Create schema
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                key TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                price REAL,
                name TEXT,
                iban TEXT,
                comment TEXT,
                name_norm TEXT,
                row_no INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                updated_at REAL DEFAULT (strftime('%s', 'now'))
            );
            
            CREATE TABLE IF NOT EXISTS status (
                transaction_key TEXT PRIMARY KEY,
                pkg INTEGER DEFAULT 0,
                stk INTEGER DEFAULT 0,
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (transaction_key) REFERENCES transactions(key) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS notes (
                transaction_key TEXT PRIMARY KEY,
                text TEXT,
                updated_at REAL DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (transaction_key) REFERENCES transactions(key) ON DELETE CASCADE
            );
            
            -- Performance indexes for fast queries
            CREATE INDEX IF NOT EXISTS idx_date ON transactions(date DESC);
            CREATE INDEX IF NOT EXISTS idx_name_norm ON transactions(name_norm);
            CREATE INDEX IF NOT EXISTS idx_archived ON transactions(archived);
            CREATE INDEX IF NOT EXISTS idx_date_archived ON transactions(date, archived);
            CREATE INDEX IF NOT EXISTS idx_status ON status(pkg, stk);
        """)
        self.conn.commit()
        print(f"✅ Database initialized: {self.db_path}")
    
    # ===== TRANSACTION OPERATIONS =====
    
    def insert_transaction(self, tx: Dict) -> bool:
        """Insert or update a single transaction."""
        try:
            self.conn.execute("""
                INSERT OR REPLACE INTO transactions 
                (key, date, price, name, iban, comment, name_norm, row_no, archived, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tx['key'], 
                tx['date'], 
                tx.get('price', 0), 
                tx['name'],
                tx.get('iban', ''), 
                tx.get('comment', ''), 
                tx['name_norm'],
                tx.get('row_no', 0), 
                tx.get('archived', 0), 
                time.time()
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error inserting transaction: {e}")
            return False
    
    def bulk_insert_transactions(self, transactions: Dict[str, Dict]):
        """Insert multiple transactions efficiently (batch operation)."""
        data = [
            (k, v['date'], v.get('price', 0), v['name'], v.get('iban', ''),
             v.get('comment', ''), v['name_norm'], v.get('row_no', 0),
             v.get('archived', 0), time.time())
            for k, v in transactions.items()
        ]
        
        self.conn.executemany("""
            INSERT OR REPLACE INTO transactions 
            (key, date, price, name, iban, comment, name_norm, row_no, archived, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        self.conn.commit()
        print(f"✅ Bulk inserted {len(data)} transactions")
    
    def get_active_transactions(self, limit: Optional[int] = None) -> List[Dict]:
        """Get non-archived transactions, sorted by name and date."""
        query = """
            SELECT t.*, s.pkg, s.stk, n.text as note
            FROM transactions t
            LEFT JOIN status s ON t.key = s.transaction_key
            LEFT JOIN notes n ON t.key = n.transaction_key
            WHERE t.archived = 0
            ORDER BY t.name_norm, t.date DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_all_transactions(self, include_archived: bool = False) -> List[Dict]:
        """Get all transactions (optionally including archived)."""
        where_clause = "" if include_archived else "WHERE t.archived = 0"
        
        query = f"""
            SELECT t.*, s.pkg, s.stk, n.text as note
            FROM transactions t
            LEFT JOIN status s ON t.key = s.transaction_key
            LEFT JOIN notes n ON t.key = n.transaction_key
            {where_clause}
            ORDER BY t.name_norm, t.date DESC
        """
        
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]
    
    def search_transactions(self, name_query: str = None, 
                          date_from: str = None, 
                          date_to: str = None,
                          include_archived: bool = False,
                          limit: Optional[int] = None,
                          offset: int = 0) -> Tuple[List[Dict], int]:
        """
        Search transactions with optional filters and pagination.
        
        Returns:
            Tuple of (list of transactions, total count before limit)
        
        Args:
            name_query: Filter by name (case-insensitive)
            date_from: Filter by start date (inclusive)
            date_to: Filter by end date (inclusive)
            include_archived: Include archived transactions
            limit: Maximum number of results to return (for virtual scrolling)
            offset: Number of results to skip (for pagination)
        """
        conditions = []
        params = []
        
        if not include_archived:
            conditions.append("t.archived = 0")
        
        if name_query:
            conditions.append("t.name_norm LIKE ?")
            params.append(f"%{name_query.lower()}%")
        
        if date_from:
            conditions.append("t.date >= ?")
            params.append(date_from)
        
        if date_to:
            conditions.append("t.date <= ?")
            params.append(date_to)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Base query for actual results
        query = f"""
            SELECT t.*, s.pkg, s.stk, n.text as note
            FROM transactions t
            LEFT JOIN status s ON t.key = s.transaction_key
            LEFT JOIN notes n ON t.key = n.transaction_key
            WHERE {where_clause}
            ORDER BY t.name_norm, t.date DESC
        """
        
        # Get total count (before limit/offset)
        count_query = f"""
            SELECT COUNT(*) 
            FROM transactions t
            WHERE {where_clause}
        """
        total_count = self.conn.execute(count_query, params).fetchone()[0]
        
        # Add pagination if specified
        if limit is not None:
            query += f" LIMIT {limit}"
            if offset > 0:
                query += f" OFFSET {offset}"
        
        cursor = self.conn.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]
        
        return results, total_count
    
    # ===== STATUS OPERATIONS =====
    
    def update_status(self, key: str, pkg: int, stk: int):
        """Update transaction status (packaged/sticker flags)."""
        self.conn.execute("""
            INSERT OR REPLACE INTO status (transaction_key, pkg, stk, updated_at)
            VALUES (?, ?, ?, ?)
        """, (key, pkg, stk, time.time()))
        self.conn.commit()
    
    def get_status(self, key: str) -> Tuple[int, int]:
        """Get status for a single transaction. Returns (pkg, stk)."""
        cursor = self.conn.execute(
            "SELECT pkg, stk FROM status WHERE transaction_key = ?", (key,)
        )
        row = cursor.fetchone()
        return (row['pkg'], row['stk']) if row else (0, 0)
    
    def bulk_update_status(self, updates: Dict[str, Tuple[int, int]]):
        """Bulk update statuses. updates = {key: (pkg, stk), ...}"""
        data = [(key, pkg, stk, time.time()) for key, (pkg, stk) in updates.items()]
        self.conn.executemany("""
            INSERT OR REPLACE INTO status (transaction_key, pkg, stk, updated_at)
            VALUES (?, ?, ?, ?)
        """, data)
        self.conn.commit()
    
    # ===== NOTE OPERATIONS =====
    
    def update_note(self, key: str, note_text: str):
        """Update or delete transaction note."""
        if note_text and note_text.strip():
            self.conn.execute("""
                INSERT OR REPLACE INTO notes (transaction_key, text, updated_at)
                VALUES (?, ?, ?)
            """, (key, note_text.strip(), time.time()))
        else:
            # Delete note if empty
            self.conn.execute("DELETE FROM notes WHERE transaction_key = ?", (key,))
        self.conn.commit()
    
    def get_note(self, key: str) -> Optional[str]:
        """Get note for a single transaction."""
        cursor = self.conn.execute(
            "SELECT text FROM notes WHERE transaction_key = ?", (key,)
        )
        row = cursor.fetchone()
        return row['text'] if row else None
    
    # ===== ARCHIVE OPERATIONS =====
    
    def archive_old_transactions(self, days: int = 90) -> int:
        """Archive transactions older than N days. Returns count of archived items."""
        cutoff_date = time.strftime('%Y-%m-%d', 
                                    time.localtime(time.time() - days * 86400))
        
        cursor = self.conn.execute("""
            UPDATE transactions 
            SET archived = 1, updated_at = ?
            WHERE date < ? AND archived = 0
        """, (time.time(), cutoff_date))
        
        self.conn.commit()
        count = cursor.rowcount
        
        if count > 0:
            print(f"📦 Archived {count} transactions older than {cutoff_date}")
        
        return count
    
    def unarchive_transaction(self, key: str):
        """Restore a transaction from archive."""
        self.conn.execute("""
            UPDATE transactions 
            SET archived = 0, updated_at = ?
            WHERE key = ?
        """, (time.time(), key))
        self.conn.commit()
    
    # ===== STATISTICS =====
    
    def get_stats(self) -> Dict:
        """Get database statistics for status bar display."""
        # Total/active/archived counts
        cursor = self.conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN archived = 0 THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN archived = 1 THEN 1 ELSE 0 END) as archived
            FROM transactions
        """)
        row = cursor.fetchone()
        
        # Status breakdown (only active transactions)
        status_cursor = self.conn.execute("""
            SELECT 
                SUM(CASE WHEN s.pkg = 0 AND s.stk = 0 THEN 1 
                         WHEN s.transaction_key IS NULL THEN 1 
                         ELSE 0 END) as none,
                SUM(CASE WHEN s.pkg = 1 AND s.stk = 0 THEN 1 ELSE 0 END) as packaged,
                SUM(CASE WHEN s.pkg = 0 AND s.stk = 1 THEN 1 ELSE 0 END) as sticker,
                SUM(CASE WHEN s.pkg = 1 AND s.stk = 1 THEN 1 ELSE 0 END) as done
            FROM transactions t
            LEFT JOIN status s ON t.key = s.transaction_key
            WHERE t.archived = 0
        """)
        status_row = status_cursor.fetchone()
        
        return {
            'total': row['total'] or 0,
            'active': row['active'] or 0,
            'archived': row['archived'] or 0,
            'none': status_row['none'] or 0,
            'packaged': status_row['packaged'] or 0,
            'sticker': status_row['sticker'] or 0,
            'done': status_row['done'] or 0
        }
    
    # ===== MAINTENANCE =====
    
    def vacuum(self):
        """Optimize database (reclaim space after deletes/archives)."""
        self.conn.execute("VACUUM")
        print("✅ Database optimized")
    
    def check_integrity(self) -> bool:
        """Verify database integrity. Returns True if OK."""
        cursor = self.conn.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        return result == "ok"
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
