"""
Firebase Realtime Database integration using REST API.
PROPERLY OPTIMIZED: Instant local updates, batched background saves.
"""

import requests
import time
from typing import Dict, Optional, Callable
from threading import Thread, Lock
import json
import sys
import platform
from pathlib import Path


class FirebaseSync:
    """Real-time sync manager for TrackNote using Firebase REST API."""
    
    def __init__(self, database_url: str, project_id: str, namespace: str = "default"):
        """
        Initialize Firebase connection.
        
        Args:
            database_url: Firebase Realtime Database URL
            project_id: Firebase project ID
            namespace: Namespace for data separation (e.g., sheet_id)
        """
        self.database_url = database_url.rstrip('/')
        self.project_id = project_id
        self.namespace = namespace
        self._lock = Lock()
        self._connected = False
        self._status_cache = {}
        self._notes_cache = {}
        self._transactions_cache = {}
        self._listener_thread = None
        self._listener_running = False
        self._connection_error_count = 0
        
        self._pending_writes = {'status': {}, 'notes': {}, 'transactions': {}}
        self._write_thread = None
        self._write_running = False
        
        self._is_windows = platform.system() == "Windows"
        self._batch_interval = 0.5
        self._max_batch_size = 20 if self._is_windows else 10
        
        try:
            self._test_connection()
            self._connected = True
            print(f"✅ Firebase connected: {database_url}")
            self._start_write_thread()
            platform_name = "Windows" if self._is_windows else "Mac"
            print(f"⚡ {platform_name}: Background batch write enabled (max {self._max_batch_size} per batch)")
        except Exception as e:
            self._connected = False
            print(f"⚠️ Firebase connection failed: {e}")
            print("   Falling back to local storage only")
    
    def _test_connection(self):
        """Test if we can reach the database."""
        url = f"{self.database_url}/tracknote/{self.namespace}.json?shallow=true"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
    
    def is_connected(self) -> bool:
        """Check if Firebase is connected."""
        return self._connected
    
    def reconnect(self) -> bool:
        """Try to reconnect to Firebase."""
        try:
            self._test_connection()
            self._connected = True
            self._connection_error_count = 0
            print("✅ Firebase reconnected")
            return True
        except:
            self._connection_error_count += 1
            return False
    
    # ===== BACKGROUND WRITE THREAD =====
    
    def _start_write_thread(self):
        """Start background thread to batch writes."""
        if self._write_running: return
        self._write_running = True
        self._write_thread = Thread(target=self._batch_write_loop, daemon=True)
        self._write_thread.start()
    
    def _batch_write_loop(self):
        """Background thread that batches writes every 500ms."""
        while self._write_running and self._connected:
            try:
                time.sleep(self._batch_interval)
                with self._lock:
                    status_writes = dict(self._pending_writes['status'])
                    notes_writes = dict(self._pending_writes['notes'])
                    transaction_writes = dict(self._pending_writes['transactions'])
                    
                    self._pending_writes['status'].clear()
                    self._pending_writes['notes'].clear()
                    self._pending_writes['transactions'].clear()

                if status_writes: self._batch_write_status(status_writes)
                if notes_writes: self._batch_write_notes(notes_writes)
                if transaction_writes: self._batch_write_transactions(transaction_writes)
                    
            except Exception: pass
    
    def _batch_write_status(self, writes: Dict):
        """Write multiple status updates in one request."""
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/status.json"
            data = {}
            for row_key, value in writes.items():
                # --- CRITICAL: Always include a timestamp for every status change ---
                # This is essential for the "last completed" logic.
                data[row_key] = {
                    'pkg': value.get('pkg', 0), 
                    'stk': value.get('stk', 0), 
                    'updated_at': time.time()
                }
            
            if data:
                requests.patch(url, json=data, timeout=5).raise_for_status()
            self._connection_error_count = 0
        except Exception:
            self._connection_error_count += 1
    
    def _batch_write_notes(self, writes: Dict):
        """Write multiple note updates in one request."""
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/notes.json"
            data, deletes = {}, []
            for row_key, value in writes.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    deletes.append(row_key)
                else:
                    data[row_key] = {'text': value, 'updated_at': time.time()}
            
            if data: requests.patch(url, json=data, timeout=5).raise_for_status()
            for row_key in deletes:
                try: requests.delete(f"{self.database_url}/tracknote/{self.namespace}/notes/{row_key}.json", timeout=3)
                except: pass
            self._connection_error_count = 0
        except Exception: self._connection_error_count += 1

    def _batch_write_transactions(self, writes: Dict):
        """Write multiple transaction updates in one request."""
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/transactions.json"
            for key in writes:
                writes[key]['updated_at'] = time.time()
            
            requests.patch(url, json=writes, timeout=10).raise_for_status()
            self._connection_error_count = 0
        except Exception:
            self._connection_error_count += 1

    # ===== STATUS METHODS =====
    def get_all_status(self) -> Dict[str, Dict]:
        if not self._connected: return self._status_cache
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/status.json"
            data = requests.get(url, timeout=5).json() or {}
            self._status_cache = data
            self._connection_error_count = 0
            return data
        except Exception:
            self._connection_error_count += 1
            if self._connection_error_count >= 3: self.reconnect()
            return self._status_cache
    
    def set_status(self, row_key: str, pkg: int, stk: int):
        status_data = {'pkg': pkg, 'stk': stk}
        self._status_cache[row_key] = status_data
        if not self._connected: return
        with self._lock: self._pending_writes['status'][row_key] = status_data
    
    # ===== NOTES METHODS =====
    def get_all_notes(self) -> Dict[str, str]:
        if not self._connected: return self._notes_cache
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/notes.json"
            data = requests.get(url, timeout=5).json() or {}
            notes = {k: v.get('text', '') if isinstance(v, dict) else v for k, v in data.items()}
            self._notes_cache = notes
            self._connection_error_count = 0
            return notes
        except Exception:
            self._connection_error_count += 1
            if self._connection_error_count >= 3: self.reconnect()
            return self._notes_cache
    
    def set_note(self, row_key: str, note_text: str):
        if note_text.strip(): self._notes_cache[row_key] = note_text
        else: self._notes_cache.pop(row_key, None)
        if not self._connected: return
        with self._lock: self._pending_writes['notes'][row_key] = note_text if note_text.strip() else None

    # ===== TRANSACTION DATA METHODS =====
    def get_all_transactions(self) -> Dict[str, Dict]:
        """Get all transaction entries from Firebase."""
        if not self._connected: return self._transactions_cache
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/transactions.json"
            data = requests.get(url, timeout=10).json() or {}
            self._transactions_cache = data
            self._connection_error_count = 0
            return data
        except Exception:
            self._connection_error_count += 1
            if self._connection_error_count >= 3: self.reconnect()
            return self._transactions_cache

    def get_transaction_keys(self) -> set:
        """Get only the keys of all transactions for fast duplicate checking."""
        if not self._connected: return set(self._transactions_cache.keys())
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/transactions.json?shallow=true"
            data = requests.get(url, timeout=5).json() or {}
            return set(data.keys())
        except Exception:
            return set(self.get_all_transactions().keys())

    def set_transactions_batch(self, transactions: Dict):
        """Queue a batch of new transactions for writing."""
        for key, value in transactions.items():
            self._transactions_cache[key] = value
        if not self._connected: return
        with self._lock: self._pending_writes['transactions'].update(transactions)

    # ===== REAL-TIME LISTENERS =====
    def start_listener(self, on_change_callback: Callable):
        if not self._connected or self._listener_running: return
        self._listener_running = True
        self._on_change_callback = on_change_callback
        self._listener_thread = Thread(target=self._poll_changes, daemon=True)
        self._listener_thread.start()
    
    def _poll_changes(self):
        """Background thread that polls for all data changes."""
        last_data = {}
        poll_interval = 5
        
        while self._listener_running:
            try:
                url = f"{self.database_url}/tracknote/{self.namespace}.json"
                current_data = requests.get(url, timeout=10).json() or {}
                
                for category in ['status', 'notes', 'transactions']:
                    last_cat_data = last_data.get(category, {})
                    current_cat_data = current_data.get(category, {})
                    
                    if current_cat_data != last_cat_data:
                        all_keys = set(current_cat_data.keys()) | set(last_cat_data.keys())
                        for key in all_keys:
                            old, new = last_cat_data.get(key), current_cat_data.get(key)
                            if old != new:
                                change_type = 'transaction' if category == 'transactions' else category
                                self._on_change_callback(change_type, key, new)
                
                last_data = current_data.copy()
            except Exception: pass
            time.sleep(poll_interval)
    
    def stop_listener(self):
        """Stop the polling thread."""
        self._listener_running = False
        self._write_running = False

def get_resource_path(relative_path):
    try: base_path = sys._MEIPASS
    except AttributeError: base_path = Path(__file__).parent.absolute()
    return Path(base_path) / relative_path

def load_firebase_config() -> Optional[Dict]:
    try:
        bundled_config = get_resource_path('firebase_config.json')
        if bundled_config.exists():
            with open(bundled_config) as f: config = json.load(f)
            if config.get('database_url') and config.get('project_id'):
                print("📦 Using bundled Firebase config")
                return {'database_url': config['database_url'], 'project_id': config['project_id']}
    except Exception: pass
    
    try:
        from user_data import read_user_config
        cfg = read_user_config()
        firebase_config = cfg.get('firebase_config')
        if not firebase_config: return None
        database_url = firebase_config.get('databaseURL') or firebase_config.get('database_url')
        project_id = firebase_config.get('projectId') or firebase_config.get('project_id')
        if not database_url or not project_id: return None
        print("👤 Using user Firebase config")
        return {'database_url': database_url, 'project_id': project_id}
    except: return None