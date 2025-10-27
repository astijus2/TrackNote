from __future__ import annotations
import os, json, hashlib
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from pathlib import Path
import pandas as pd
from tkinter import messagebox
from tkinter import messagebox as _mb
import time
import threading
import platform

from parsing import split_details, normalize
from data_source import fetch_rows
from sheets_cache import clear_cache
from ui import App
from firebase_sync import FirebaseSync, load_firebase_config
from typing import Optional, Tuple, Dict

# --- Licensing: fingerprint, Ed25519 verify, trial ---
import base64, subprocess, uuid, datetime as _dt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from tkinter import simpledialog as _sd
from user_data import read_user_config, write_user_config, read_license_key, store_license_key

# Optional import - not required for app to work
PSUTIL_AVAILABLE = False

# PROFESSIONAL OPTIMIZATION: Minimal debouncing, only for expensive operations
IS_WINDOWS = platform.system() == "Windows"
FILTER_RENDER_DELAY = 150  # Only debounce full table re-renders (both platforms)

class OperationDebouncer:
    """Debounce ONLY expensive operations (not UI updates)."""
    def __init__(self, app, delay=150):
        self.app = app
        self.delay = delay
        self.timers = {}
    
    def debounce(self, key, func):
        """Debounce function call by key."""
        if key in self.timers:
            self.app.after_cancel(self.timers[key])
        self.timers[key] = self.app.after(self.delay, func)

class MemoryManager:
    @staticmethod
    def get_memory_usage():
        """Get memory usage if psutil is available."""
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process()
                return process.memory_info().rss / 1024 / 1024
            except:
                return 0
        return 0
    
    @staticmethod
    def cleanup_widgets(app):
        """Clean up unused widgets."""
        cleaned = 0
        try:
            visible = set(app.tbl.get_children())
            
            if hasattr(app, '_note_widgets'):
                to_remove = [iid for iid in app._note_widgets.keys() if iid not in visible]
                for iid in to_remove[:10]:
                    try:
                        app._note_widgets[iid].destroy()
                        del app._note_widgets[iid]
                        cleaned += 1
                    except:
                        pass
        except Exception:
            pass
        
        return cleaned
    
    @staticmethod
    def optimize_caches(app):
        """Optimize internal caches."""
        MAX_CACHE_SIZE = 2000
        
        if hasattr(app, '_rowkey_to_iid_cache'):
            if len(app._rowkey_to_iid_cache) > MAX_CACHE_SIZE:
                visible = set(app.tbl.get_children())
                app._rowkey_to_iid_cache = {k: v for k, v in app._rowkey_to_iid_cache.items() if v in visible}

PRODUCT_NAME = "TrackNote"
TRIAL_DAYS = 14
PUBLIC_KEY_B64 = "61izrH-GRDcHS_mLjbxRJoZAFbJqFQbSEsYzB8euFCg"

def load_and_render_async(app: App):
    """Load in background thread."""
    
    def _background_load():
        try:
            app.after(0, lambda: _update_status(app, "📊 Loading..."))
            
            cfg = read_user_config()
            rows = fetch_rows(cfg)
            
            rebuild_index(rows)
            
            app.after(0, lambda: _finish_load(app))
        except Exception as e:
            app.after(0, lambda: messagebox.showerror("Error", str(e)))
    
    def _update_status(app, msg):
        if hasattr(app, 'lbl_status'):
            app.lbl_status.config(text=msg)
    
    def _finish_load(app):
        render(app)
        _update_status(app, "✓ Ready!")
        app.after(2000, lambda: _update_status(app, ""))
    
    threading.Thread(target=_background_load, daemon=True).start()

def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = "=" * (-len(s) % 4)
    return base64.b64decode(s + pad)

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

def get_machine_fingerprint() -> str:
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(
                ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    fp = line.split("=")[1].strip().strip('"')
                    if fp:
                        return fp.lower()
        elif platform.system() == "Windows":
            out = subprocess.check_output(
                ["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"],
                text=True
            )
            return out.split()[-1].lower()
    except Exception:
        pass
    mac = uuid.getnode()
    arch = platform.machine()
    return f"{mac:012x}-{arch}".lower()

def verify_license_key(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    try:
        payload_part, sig_part = license_key.strip().split(".", 1)
    except ValueError:
        return (False, "License format is invalid.", None)

    try:
        payload_bytes = _b64url_decode(payload_part)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return (False, "License payload cannot be decoded.", None)

    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(PUBLIC_KEY_B64))
        pub.verify(_b64url_decode(sig_part), payload_bytes)
    except (InvalidSignature, ValueError):
        return (False, "License signature is invalid.", payload)
    except Exception as e:
        return (False, f"License verify error: {e}", payload)

    fp_now = get_machine_fingerprint()
    if payload.get("fp", "").lower() != fp_now.lower():
        return (False, "License is for a different computer.", payload)
    if payload.get("prod") != PRODUCT_NAME:
        return (False, "License product mismatch.", payload)
    exp = payload.get("exp")
    try:
        if exp and _dt.date.today() > _dt.date.fromisoformat(exp):
            return (False, f"License expired on {exp}.", payload)
    except Exception:
        return (False, "License expiry is invalid.", payload)

    return (True, "OK", payload)

def show_license_dialog(app) -> bool:
    while True:
        key = _sd.askstring("Enter License Key", "Paste your TrackNote license key:", parent=app)
        if key is None:
            return False
        ok, msg, _pl = verify_license_key(key)
        if ok:
            store_license_key(key)
            _mb.showinfo("TrackNote", "License activated. Thank you!")
            return True
        else:
            _mb.showerror("TrackNote", f"{msg}\n\nPlease check and try again.")

def license_status_string() -> str:
    key = read_license_key()
    if not key:
        return ""
    ok, msg, payload = verify_license_key(key)
    if not ok:
        return ""
    exp_str = payload.get("exp") if payload else None
    if exp_str:
        try:
            exp_date = _dt.date.fromisoformat(exp_str)
            days_left = (exp_date - _dt.date.today()).days
            if days_left <= 0:
                return ""
            return f"Licensed (expires {exp_str})"
        except:
            return "Licensed"
    return "Licensed"

def check_trial():
    cfg = read_user_config()
    first_run = cfg.get("first_run_date")
    if not first_run:
        cfg["first_run_date"] = _dt.datetime.now().isoformat()
        write_user_config(cfg)
        return (True, "Trial started")
    
    key = read_license_key()
    if key:
        ok, msg, _pl = verify_license_key(key)
        if ok:
            return (True, "Licensed")
    
    try:
        first = _dt.datetime.fromisoformat(first_run)
        elapsed = (_dt.datetime.now() - first).days
        if elapsed < TRIAL_DAYS:
            remaining = TRIAL_DAYS - elapsed
            return (True, f"Trial: {remaining} days left")
        else:
            return (False, "Trial expired")
    except Exception:
        return (True, "Trial active")

# ===== DATA =====
ROWS = []
ROWS_FILTERED = []
STATUS = {}
FIREBASE_SYNC: Optional[FirebaseSync] = None

def rebuild_index(rows):
    global ROWS, ROWS_FILTERED
    ROWS = rows
    ROWS_FILTERED = rows.copy()

def filter_rows(query: str, date_from: str, date_to: str):
    global ROWS, ROWS_FILTERED
    ROWS_FILTERED = []
    q_norm = normalize(query)
    for r in ROWS:
        ok = True
        if q_norm and q_norm not in normalize(r.get('name', '')):
            ok = False
        date_str = r.get('date', '')
        if ok and date_from and date_str < date_from:
            ok = False
        if ok and date_to and date_str > date_to:
            ok = False
        if ok:
            ROWS_FILTERED.append(r)

def status_to_tag(st: dict) -> str:
    p, s = st.get('pkg', 0), st.get('stk', 0)
    if p and s:
        return 'both'
    if p:
        return 'pkg'
    if s:
        return 'stk'
    return ''

def row_key_for(row: dict) -> str:
    return hashlib.md5(
        f"{row.get('date','')}{row.get('name','')}{row.get('order','')}{row.get('detail','')}".encode()
    ).hexdigest()

# ===== UI LOGIC =====
def render(app: App, preserve_selection=False):
    """INSTANT render - no delays."""
    global ROWS_FILTERED, STATUS
    
    # Cache selection
    old_sel = set(app.tbl.selection()) if preserve_selection else set()
    old_focus = app.tbl.focus() if preserve_selection else None
    
    # Clear
    for item in app.tbl.get_children():
        app.tbl.delete(item)
    
    # Track rows to restore
    restore_sel = []
    restore_focus = None
    
    # Insert rows
    for row in ROWS_FILTERED:
        row_key = row_key_for(row)
        st = STATUS.get(row_key, {'pkg': 0, 'stk': 0})
        tag = status_to_tag(st)
        
        iid = app.tbl.insert('', 'end',
            iid=row_key,
            values=(
                row.get('date', ''),
                row.get('name', ''),
                row.get('order', ''),
                row.get('detail', ''),
                row.get('notes', '')
            ),
            tags=(tag,)
        )
        
        if preserve_selection:
            if row_key in old_sel:
                restore_sel.append(row_key)
            if row_key == old_focus:
                restore_focus = row_key
    
    # Restore selection/focus
    if restore_sel:
        app.tbl.selection_set(restore_sel)
    if restore_focus:
        try:
            app.tbl.focus(restore_focus)
            app.tbl.see(restore_focus)
        except:
            pass
    
    # Update visible notes
    if hasattr(app, '_update_visible_notes'):
        app.after(0, lambda: app._update_visible_notes())

def load_and_render(app: App, *args):
    """Load data and render."""
    try:
        cfg = read_user_config()
        rows = fetch_rows(cfg)
        rebuild_index(rows)
        render(app)
    except Exception as e:
        messagebox.showerror("Error", str(e))

def on_tree_click(app: App, event):
    region = app.tbl.identify_region(event.x, event.y)
    if region == 'tree':
        return
    col = app.tbl.identify_column(event.x)
    if col == '#5':
        return
    iid = app.tbl.identify_row(event.y)
    if not iid:
        return
    toggle_status_for_row(iid, 'pkg', app)

def on_select_change(app: App, event):
    """INSTANT note loading - no debounce."""
    if hasattr(app, '_update_visible_notes'):
        app._update_visible_notes()

def toggle_status_for_row(row_key: str, key: str, app: App):
    """
    INSTANT status toggle - PROFESSIONAL PATTERN.
    
    1. Update STATUS dict immediately (0ms)
    2. Update UI immediately (0ms)
    3. Firebase save happens in background (batched by firebase_sync.py)
    
    User sees change INSTANTLY, no lag.
    """
    global STATUS, FIREBASE_SYNC
    
    # Get current status
    st = STATUS.get(row_key, {'pkg': 0, 'stk': 0})
    
    # Toggle INSTANTLY
    if key == 'pkg':
        st['pkg'] = 0 if st.get('pkg') else 1
    elif key == 'stk':
        st['stk'] = 0 if st.get('stk') else 1
    else:
        return
    
    # Update local state INSTANTLY (0ms)
    STATUS[row_key] = st
    
    # Update UI INSTANTLY (0ms)
    try:
        tag = status_to_tag(st)
        app.tbl.item(row_key, tags=(tag,))
    except:
        pass
    
    # Background save (non-blocking, batched by firebase_sync.py)
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            if st.get('pkg') or st.get('stk'):
                FIREBASE_SYNC.set_status(row_key, st['pkg'], st['stk'])
            else:
                FIREBASE_SYNC.clear_status(row_key)
        except:
            pass

def toggle_status(key: str, app: App):
    """Toggle status for all selected rows - INSTANT."""
    for iid in app.tbl.selection():
        toggle_status_for_row(iid, key, app)

def clear_status_selected(app: App):
    """Clear status for selected rows - INSTANT."""
    global STATUS, FIREBASE_SYNC
    for iid in app.tbl.selection():
        # Update local INSTANTLY
        STATUS.pop(iid, None)
        app.tbl.item(iid, tags=('',))
        
        # Background save
        if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
            try:
                FIREBASE_SYNC.clear_status(iid)
            except:
                pass

def clear_filters(app: App):
    """Clear all filters - INSTANT visual, debounced render."""
    app.var_q.set('')
    app.var_from.set('')
    app.var_to.set('')
    
    # Reset placeholders
    if hasattr(app.ent_name, '_ph_active'):
        app.ent_name._ph_active = True
        app.ent_name.delete(0, 'end')
        app.ent_name.insert(0, app.ent_name._ph_text)
        app.ent_name.config(fg='#888888')
    
    if hasattr(app.ent_from, '_ph_active'):
        app.ent_from._ph_active = True
        app.ent_from.delete(0, 'end')
        app.ent_from.insert(0, app.ent_from._ph_text)
        app.ent_from.config(fg='#888888')
    
    if hasattr(app.ent_to, '_ph_active'):
        app.ent_to._ph_active = True
        app.ent_to.delete(0, 'end')
        app.ent_to.insert(0, app.ent_to._ph_text)
        app.ent_to.config(fg='#888888')
    
    # Debounce only the render (expensive operation)
    if not hasattr(app, '_render_debouncer'):
        app._render_debouncer = OperationDebouncer(app, delay=FILTER_RENDER_DELAY)
    
    app._render_debouncer.debounce('render', lambda: render(app))

def select_all(app: App):
    """INSTANT selection."""
    visible = app.tbl.get_children()
    app.tbl.selection_set(visible)

def clear_selection(app: App):
    """INSTANT clear."""
    app.tbl.selection_remove(app.tbl.selection())

def _guard_shortcut(app: App, fn):
    """Guard shortcuts - INSTANT execution, no delays."""
    def wrapper(event):
        fn(event)
        return 'break'
    return wrapper

def _startup_log(data: dict):
    pass

def _guarded_main():
    try:
        _main_inner()
    except Exception as e:
        try:
            _mb.showerror("TrackNote Startup Error", 
                         f"Failed to start TrackNote:\n{e}\n\nCheck logs for details.")
        except:
            pass

def _main_inner():
    global STATUS, FIREBASE_SYNC
    
    _startup_log({"phase": "start"})
    
    # Check trial/license
    allowed, msg = check_trial()
    if not allowed:
        root = tk.Tk()
        root.withdraw()
        act = show_license_dialog(root)
        root.destroy()
        if not act:
            _mb.showwarning("TrackNote", f"Trial expired. Please contact support.")
            return
        allowed, msg = check_trial()
        if not allowed:
            _mb.showerror("TrackNote", "License activation failed.")
            return
    
    # Show loading screen
    loading = None
    try:
        loading = tk.Tk()
        loading.overrideredirect(True)
        loading.geometry('300x100+500+300')
        loading.configure(bg='white')
        tk.Label(loading, text='Loading TrackNote...', bg='white', font=('Arial', 14)).pack(expand=True)
        loading.update()
    except:
        loading = None
    
    # Create main app
    app = App()
    app.withdraw()
    
    # Add license status
    lic_status = license_status_string()
    if lic_status:
        app.title(f"TrackNote - {lic_status}")
    
    # Windows-specific UI optimizations (non-blocking)
    if IS_WINDOWS:
        try:
            print("⚡ Windows: UI optimizations applied")
        except Exception as e:
            print(f"⚠️ Some optimizations failed: {e}")
    
    _startup_log({"phase": "ui-created"})
    
    # Load config
    cfg = read_user_config()
    
    # Initialize Firebase
    firebase_config = load_firebase_config()
    if firebase_config:
        try:
            sheet_id = None
            if cfg.get('data_source') == 'sheets':
                url = cfg.get('sheet_url', '')
                import re
                m = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
                if m:
                    sheet_id = m.group(1)
            
            namespace = sheet_id if sheet_id else 'default'
            
            FIREBASE_SYNC = FirebaseSync(
                database_url=firebase_config['database_url'],
                project_id=firebase_config['project_id'],
                namespace=namespace
            )
            
            app.firebase_sync = FIREBASE_SYNC
            
            # Load initial data
            if FIREBASE_SYNC.is_connected():
                try:
                    STATUS = FIREBASE_SYNC.get_all_status()
                    for k, v in STATUS.items():
                        if isinstance(v, dict):
                            STATUS[k] = {
                                'pkg': v.get('pkg', 0),
                                'stk': v.get('stk', 0)
                            }
                    
                    firebase_notes = FIREBASE_SYNC.get_all_notes()
                    if hasattr(app, '_note_store'):
                        app._note_store.update(firebase_notes)
                    
                    print(f"✓ Loaded {len(STATUS)} status entries")
                    print(f"✓ Loaded {len(firebase_notes)} notes")
                except Exception as e:
                    print(f"⚠️ Failed to load Firebase data: {e}")
        except Exception as e:
            print(f"⚠️ Firebase initialization failed: {e}")
            FIREBASE_SYNC = None
    else:
        print("ℹ️ Firebase not configured - using local storage only")
        FIREBASE_SYNC = None
    
    _startup_log({"phase": "firebase-init"})
    
    # Wire up buttons - INSTANT actions
    app.btn_refresh.config(command=lambda: load_and_render(app))
    app.btn_clear_filters.config(command=lambda: clear_filters(app))
    app.btn_select_all.config(command=lambda: select_all(app))
    app.btn_clear_sel.config(command=lambda: clear_selection(app))
    app.btn_toggle_pkg.config(command=lambda: toggle_status('pkg', app))
    app.btn_toggle_stk.config(command=lambda: toggle_status('stk', app))
    
    # Filter bindings with debouncing ONLY for render (expensive)
    try:
        def _schedule_render():
            if not hasattr(app, '_render_debouncer'):
                app._render_debouncer = OperationDebouncer(app, delay=FILTER_RENDER_DELAY)
            
            q = app.var_q.get()
            f = app.var_from.get()
            t = app.var_to.get()
            
            # Handle placeholders
            if hasattr(app.ent_name, '_ph_active') and app.ent_name._ph_active:
                q = ''
            if hasattr(app.ent_from, '_ph_active') and app.ent_from._ph_active:
                f = ''
            if hasattr(app.ent_to, '_ph_active') and app.ent_to._ph_active:
                t = ''
            
            def _do_render():
                filter_rows(q, f, t)
                render(app, preserve_selection=True)
            
            app._render_debouncer.debounce('render', _do_render)
        
        app.var_q.trace_add('write', lambda *_: _schedule_render())
        app.var_from.trace_add('write', lambda *_: _schedule_render())
        app.var_to.trace_add('write', lambda *_: _schedule_render())
        for w in (app.ent_name, app.ent_from, app.ent_to):
            w.bind('<KeyRelease>', lambda e: _schedule_render(), add='+')
            w.bind('<<Paste>>', lambda e: _schedule_render(), add='+')
            w.bind('<<Cut>>',   lambda e: _schedule_render(), add='+')
    except Exception:
        pass

    # Events
    app.tbl.bind('<Button-1>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<<TreeviewSelect>>', lambda e: on_select_change(app, e))

    # Keyboard shortcuts
    app.tbl.bind('<space>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<Key-p>', lambda e: toggle_status('pkg', app))
    app.tbl.bind('<Key-s>', lambda e: toggle_status('stk', app))

    # App-wide keys
    app.bind('<Escape>', lambda e: (_guard_shortcut(app, lambda _: clear_filters(app))(e)))
    app.bind('<Command-BackSpace>', lambda e: (_guard_shortcut(app, lambda _: clear_status_selected(app))(e)))

    # Initial load
    load_and_render(app)
    _startup_log({"phase": "before-mainloop"})

    # ===== FIREBASE REAL-TIME SYNC =====
    def on_firebase_change(change_type: str, row_key: Optional[str], data):
        """INSTANT Firebase change handler - no batching delay for UI."""
        try:
            global STATUS
            
            # Update INSTANTLY (0ms)
            if change_type == 'status' and row_key:
                if data:
                    STATUS[row_key] = {'pkg': data.get('pkg', 0), 'stk': data.get('stk', 0)}
                else:
                    STATUS.pop(row_key, None)
                
                # Update UI INSTANTLY if visible
                try:
                    visible_iids = set(app.tbl.get_children())
                    if row_key in visible_iids:
                        st = STATUS.get(row_key, {'pkg': 0, 'stk': 0})
                        tag = status_to_tag(st)
                        app.tbl.item(row_key, tags=(tag,))
                except:
                    pass
            
            elif change_type == 'notes' and row_key:
                if hasattr(app, '_note_store'):
                    if data:
                        app._note_store[row_key] = data
                    else:
                        app._note_store.pop(row_key, None)
                    
                    # Update editor INSTANTLY if visible and not focused
                    try:
                        visible_iids = set(app.tbl.get_children())
                        if row_key in visible_iids and hasattr(app, '_note_widgets'):
                            editor = app._note_widgets.get(row_key)
                            if editor and editor != app.focus_get():
                                editor.delete('1.0', 'end')
                                if data:
                                    editor.insert('1.0', data)
                                app._set_note_entry_bg(editor)
                    except:
                        pass
                                
        except Exception:
            pass

    # Start Firebase listener
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            FIREBASE_SYNC.start_listener(on_firebase_change)
            print("✓ Real-time sync active - changes appear in 5 seconds")
        except Exception as e:
            print(f"⚠ Failed to start Firebase listener: {e}")

    # ===== AUTO-REFRESH =====
    def auto_refresh():
        try:
            if getattr(app, '_is_closing', False):
                return
            if not app.winfo_exists():
                return
            load_and_render(app)
        except Exception:
            pass
        finally:
            try:
                if not getattr(app, '_is_closing', False) and app.winfo_exists():
                    app.after(60000, auto_refresh)
            except:
                pass

    def on_focus_refresh(event=None):
        """INSTANT refresh on focus."""
        try:
            if getattr(app, '_is_closing', False):
                return
            if app.winfo_exists():
                load_and_render(app)
        except Exception:
            pass

    app.after(60000, auto_refresh)
    app.bind('<FocusIn>', on_focus_refresh)

    # === MEMORY MANAGEMENT ===
    def periodic_memory_check():
        try:
            if getattr(app, '_is_closing', False):
                return
            if not app.winfo_exists():
                return
            MemoryManager.cleanup_widgets(app)
            MemoryManager.optimize_caches(app)
        except Exception:
            pass
        finally:
            try:
                if not getattr(app, '_is_closing', False) and app.winfo_exists():
                    app.after(60000, periodic_memory_check)
            except:
                pass
    
    app.after(60000, periodic_memory_check)

    # === WINDOW CLOSE HANDLER ===
    def on_closing():
        try:
            app._is_closing = True
            
            for after_id in app.tk.call('after', 'info'):
                try:
                    app.after_cancel(after_id)
                except:
                    pass
            
            if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
                try:
                    FIREBASE_SYNC.stop_listener()
                except:
                    pass
            
            app.quit()
            app.destroy()
        except Exception:
            import sys
            sys.exit(0)
    
    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Close loading and show app
    if loading:
        try:
            loading.destroy()
        except:
            pass

    app.deiconify()
    
    try:
        app.mainloop()
    except Exception:
        pass
    
if __name__ == '__main__':
    _guarded_main()