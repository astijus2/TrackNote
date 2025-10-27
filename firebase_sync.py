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
        # Remove trailing slash if present
        self.database_url = database_url.rstrip('/')
        self.project_id = project_id
        self.namespace = namespace
        self._lock = Lock()
        self._connected = False
        self._status_cache = {}
        self._notes_cache = {}
        self._listener_thread = None
        self._listener_running = False
        self._connection_error_count = 0
        
        # OPTIMIZATION: Background write queue (both platforms)
        self._pending_writes = {'status': {}, 'notes': {}}
        self._write_thread = None
        self._write_running = False
        
        # Platform-specific batch sizes
        self._is_windows = platform.system() == "Windows"
        self._batch_interval = 0.5  # 500ms for both platforms
        self._max_batch_size = 20 if self._is_windows else 10
        
        # Test connection
        try:
            self._test_connection()
            self._connected = True
            print(f"✅ Firebase connected: {database_url}")
            
            # Start background write thread
            self._start_write_thread()
            platform_name = "Windows" if self._is_windows else "Mac"
            print(f"⚡ {platform_name}: Background batch write enabled (max {self._max_batch_size} per batch)")
        except Exception as e:
            self._connected = False
            print(f"⚠️ Firebase connection failed: {e}")
            print("   Falling back to local storage only")
    
    def _test_connection(self):
        """Test if we can reach the database."""
        url = f"{self.database_url}/tracknote/{self.namespace}.json"
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
    
    # ===== BACKGROUND WRITE THREAD (PROFESSIONAL PATTERN) =====
    
    def _start_write_thread(self):
        """Start background thread to batch writes."""
        if self._write_running:
            return
        
        self._write_running = True
        self._write_thread = Thread(target=self._batch_write_loop, daemon=True)
        self._write_thread.start()
    
    def _batch_write_loop(self):
        """Background thread that batches writes every 500ms."""
        while self._write_running and self._connected:
            try:
                time.sleep(self._batch_interval)
                
                with self._lock:
                    # Get pending writes
                    status_writes = dict(self._pending_writes['status'])
                    notes_writes = dict(self._pending_writes['notes'])
                    
                    # Clear pending
                    self._pending_writes['status'].clear()
                    self._pending_writes['notes'].clear()
                
                # Execute batched writes (outside lock)
                if status_writes:
                    self._batch_write_status(status_writes)
                
                if notes_writes:
                    self._batch_write_notes(notes_writes)
                    
            except Exception:
                pass  # Silent failure
    
    def _batch_write_status(self, writes: Dict):
        """Write multiple status updates in one request."""
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/status.json"
            
            # Convert to Firebase format
            data = {}
            deletes = []
            
            for row_key, value in writes.items():
                if value is None:
                    # Mark for deletion
                    deletes.append(row_key)
                else:
                    data[row_key] = {
                        'pkg': value['pkg'],
                        'stk': value['stk'],
                        'updated_at': time.time()
                    }
            
            # Batch update
            if data:
                response = requests.patch(url, json=data, timeout=5)
                response.raise_for_status()
            
            # Batch delete
            for row_key in deletes:
                try:
                    del_url = f"{self.database_url}/tracknote/{self.namespace}/status/{row_key}.json"
                    requests.delete(del_url, timeout=3)
                except:
                    pass
            
            self._connection_error_count = 0
                
        except Exception:
            self._connection_error_count += 1
    
    def _batch_write_notes(self, writes: Dict):
        """Write multiple note updates in one request."""
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/notes.json"
            
            # Convert to Firebase format
            data = {}
            deletes = []
            
            for row_key, value in writes.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    # Mark for deletion
                    deletes.append(row_key)
                else:
                    data[row_key] = {
                        'text': value,
                        'updated_at': time.time()
                    }
            
            # Batch update
            if data:
                response = requests.patch(url, json=data, timeout=5)
                response.raise_for_status()
            
            # Batch delete
            for row_key in deletes:
                try:
                    del_url = f"{self.database_url}/tracknote/{self.namespace}/notes/{row_key}.json"
                    requests.delete(del_url, timeout=3)
                except:
                    pass
            
            self._connection_error_count = 0
                
        except Exception:
            self._connection_error_count += 1
    
    # ===== STATUS METHODS (INSTANT LOCAL, BATCHED REMOTE) =====
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get all status entries from Firebase."""
        if not self._connected:
            return self._status_cache
        
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/status.json"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json() or {}
            self._status_cache = data
            self._connection_error_count = 0
            return data
        except Exception as e:
            self._connection_error_count += 1
            if self._connection_error_count >= 3:
                self.reconnect()
            return self._status_cache
    
    def set_status(self, row_key: str, pkg: int, stk: int):
        """
        Set status for a row - INSTANT local update, batched remote save.
        
        CRITICAL: This returns immediately (0ms). UI should update instantly.
        Firebase save happens in background thread after 500ms batching.
        """
        # Update cache INSTANTLY (0ms)
        self._status_cache[row_key] = {'pkg': pkg, 'stk': stk}
        
        if not self._connected:
            return
        
        # Queue for background batch write (non-blocking)
        with self._lock:
            self._pending_writes['status'][row_key] = {'pkg': pkg, 'stk': stk}
    
    def clear_status(self, row_key: str):
        """Clear status for a row - INSTANT local, batched remote."""
        # Update cache INSTANTLY
        self._status_cache.pop(row_key, None)
        
        if not self._connected:
            return
        
        # Queue for background batch delete
        with self._lock:
            self._pending_writes['status'][row_key] = None
    
    # ===== NOTES METHODS (INSTANT LOCAL, BATCHED REMOTE) =====
    
    def get_all_notes(self) -> Dict[str, str]:
        """Get all notes from Firebase."""
        if not self._connected:
            return self._notes_cache
        
        try:
            url = f"{self.database_url}/tracknote/{self.namespace}/notes.json"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json() or {}
            
            # Extract just the text from each note
            notes = {}
            for k, v in data.items():
                if isinstance(v, dict):
                    notes[k] = v.get('text', '')
                elif isinstance(v, str):
                    notes[k] = v
            self._notes_cache = notes
            self._connection_error_count = 0
            return notes
        except Exception:
            self._connection_error_count += 1
            if self._connection_error_count >= 3:
                self.reconnect()
            return self._notes_cache
    
    def set_note(self, row_key: str, note_text: str):
        """
        Set note for a row - INSTANT local update, batched remote save.
        
        CRITICAL: This returns immediately (0ms). Text should appear instantly.
        Firebase save happens in background after batching.
        """
        # Update cache INSTANTLY (0ms)
        if note_text.strip():
            self._notes_cache[row_key] = note_text
        else:
            self._notes_cache.pop(row_key, None)
        
        if not self._connected:
            return
        
        # Queue for background batch write (non-blocking)
        with self._lock:
            self._pending_writes['notes'][row_key] = note_text if note_text.strip() else None
    
    # ===== REAL-TIME LISTENERS =====
    
    def start_listener(self, on_change_callback: Callable):
        """
        Start listening for real-time changes from other computers.
        Polls every 5 seconds (both platforms for consistency).
        
        Args:
            on_change_callback: Function to call when data changes
        """
        if not self._connected:
            return
        
        if self._listener_running:
            return
        
        self._listener_running = True
        self._on_change_callback = on_change_callback
        
        # Start background polling thread
        self._listener_thread = Thread(target=self._poll_changes, daemon=True)
        self._listener_thread.start()
    
    def _poll_changes(self):
        """Background thread that polls for changes every 5 seconds."""
        last_status = {}
        last_notes = {}
        
        # Poll every 5 seconds (both platforms)
        poll_interval = 5
        
        while self._listener_running:
            try:
                # Poll status changes
                current_status = self.get_all_status()
                if current_status != last_status:
                    # Find what changed
                    all_keys = set(current_status.keys()) | set(last_status.keys())
                    for key in all_keys:
                        old = last_status.get(key)
                        new = current_status.get(key)
                        if old != new:
                            self._on_change_callback('status', key, new)
                    last_status = current_status.copy()
                
                # Poll notes changes
                current_notes = self.get_all_notes()
                if current_notes != last_notes:
                    # Find what changed
                    all_keys = set(current_notes.keys()) | set(last_notes.keys())
                    for key in all_keys:
                        old = last_notes.get(key)
                        new = current_notes.get(key)
                        if old != new:
                            self._on_change_callback('notes', key, new)
                    last_notes = current_notes.copy()
                
            except Exception:
                pass  # Silent failure for performance
            
            time.sleep(poll_interval)
    
    def stop_listener(self):
        """Stop the polling thread."""
        self._listener_running = False
        self._write_running = False


def get_resource_path(relative_path):
    """Get absolute path to resource - works for dev and PyInstaller bundle."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = Path(__file__).parent.absolute()
    
    return Path(base_path) / relative_path


def load_firebase_config() -> Optional[Dict]:
    """Load Firebase configuration from bundled file or user config."""
    # Try bundled config first (for pre-configured deployments)
    try:
        bundled_config = get_resource_path('firebase_config.json')
        if bundled_config.exists():
            with open(bundled_config) as f:
                config = json.load(f)
                if config.get('database_url') and config.get('project_id'):
                    print("📦 Using bundled Firebase config")
                    return {
                        'database_url': config['database_url'],
                        'project_id': config['project_id']
                    }
    except Exception as e:
        pass
    
    # Fallback to user config
    try:
        from user_data import read_user_config
        cfg = read_user_config()
        firebase_config = cfg.get('firebase_config')
        
        if not firebase_config:
            return None
        
        database_url = firebase_config.get('databaseURL') or firebase_config.get('database_url')
        project_id = firebase_config.get('projectId') or firebase_config.get('project_id')
        
        if not database_url or not project_id:
            return None
        
        print("👤 Using user Firebase config")
        return {
            'database_url': database_url,
            'project_id': project_id
        }
    except:
        return None


def save_firebase_config(database_url: str, project_id: str):
    """Save Firebase configuration to user config."""
    from user_data import read_user_config, write_user_config
    
    cfg = read_user_config()
    cfg['firebase_config'] = {
        'database_url': database_url,
        'project_id': project_id
    }
    write_user_config(cfg)
    print("✅ Firebase config saved to user config")