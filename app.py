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

# Platform detection for maximum optimization
IS_WINDOWS = platform.system() == "Windows"

# WINDOWS OPTIMIZATION: Aggressive performance settings
if IS_WINDOWS:
    # Larger batch sizes for Windows
    RENDER_BATCH_SIZE = 100  # Render 100 rows at a time
    SCROLL_DEBOUNCE = 50     # 50ms scroll debounce
    FILTER_DEBOUNCE = 200    # 200ms filter debounce
    MAX_VISIBLE_ROWS = 500   # Limit visible rows for performance
else:
    # Mac can handle more
    RENDER_BATCH_SIZE = 200
    SCROLL_DEBOUNCE = 0
    FILTER_DEBOUNCE = 150
    MAX_VISIBLE_ROWS = 1000

# Optional import - not required for app to work
PSUTIL_AVAILABLE = False

class OperationDebouncer:
    """Debounce heavy operations to prevent lag."""
    def __init__(self, app, delay=100):
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
        """Clean up unused widgets - OPTIMIZED."""
        cleaned = 0
        try:
            visible = set(app.tbl.get_children())
            
            # Clean note widgets for non-visible rows only
            if hasattr(app, '_note_widgets'):
                to_remove = [iid for iid in app._note_widgets.keys() if iid not in visible]
                # Limit cleanup to prevent UI freeze
                for iid in to_remove[:10]:  # Max 10 at a time
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
        """Optimize internal caches - FASTER VERSION."""
        MAX_CACHE_SIZE = 2000  # Increased from 1000
        
        if hasattr(app, '_rowkey_to_iid_cache'):
            if len(app._rowkey_to_iid_cache) > MAX_CACHE_SIZE:
                visible = set(app.tbl.get_children())
                app._rowkey_to_iid_cache = {k: v for k, v in app._rowkey_to_iid_cache.items() if v in visible}

PRODUCT_NAME = "TrackNote"
TRIAL_DAYS = 14

# Replace this with YOUR public key (bytes) generated once; filler for now:
PUBLIC_KEY_B64 = "61izrH-GRDcHS_mLjbxRJoZAFbJqFQbSEsYzB8euFCg"  # placeholder!

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

# ===== GLOBALS =====
from user_data import user_data_dir
APPDIR = user_data_dir()
APPDIR.mkdir(parents=True, exist_ok=True)

FIREBASE_SYNC: Optional[FirebaseSync] = None
STATUS_FILE = APPDIR / "status.json"

def load_status():
    """Load status from Firebase or local file."""
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            return FIREBASE_SYNC.get_all_status()
        except Exception as e:
            print(f"Error loading from Firebase: {e}")
    
    # Fallback to local file
    try: 
        return json.loads(STATUS_FILE.read_text())
    except Exception: 
        return {}

def save_status(obj):
    """
    OPTIMIZED: Save status asynchronously - NEVER BLOCKS UI.
    
    This function returns IMMEDIATELY. Saves happen in background.
    """
    # INSTANT: Save to Firebase in background (batched)
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            for key, val in obj.items():
                # This returns immediately - batched internally
                FIREBASE_SYNC.set_status(key, val.get('pkg', 0), val.get('stk', 0))
        except Exception as e:
            print(f"Error saving to Firebase: {e}")
    
    # BACKGROUND: Save to local file in thread (non-blocking)
    def _save_local():
        try: 
            STATUS_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        except Exception: 
            pass
    
    threading.Thread(target=_save_local, daemon=True).start()

STATUS = load_status()

# ---------- Tag colors ----------
TAGS = {
    'none':     {'bg': '#ffffff'},
    'packaged': {'bg': '#fff4b8'},  # pale yellow - ORIGINAL
    'sticker':  {'bg': '#dcecff'},  # light blue - ORIGINAL
    'both':     {'bg': '#d6f5d6'},  # light green - ORIGINAL
}

def status_to_tag(st: dict) -> str:
    p, s = st.get('pkg', 0), st.get('stk', 0)
    if p and s:
        return 'both'
    if p:
        return 'packaged'
    if s:
        return 'sticker'
    return 'none'
def configure_tags(app: App):
    """Configure TreeView tags with original colors."""
    for name, spec in TAGS.items():
        try: 
            app.tbl.tag_configure(name, background=spec['bg'])
        except Exception: 
            pass
    
    # Flash tags for visual feedback
    try: 
        app.tbl.tag_configure('flash_none', background='#FFFFFF')
        app.tbl.tag_configure('flash_packaged', background='#FFB700')
        app.tbl.tag_configure('flash_sticker', background='#0099FF')
        app.tbl.tag_configure('flash_both', background='#00FF00')
    except Exception: 
        pass


# ---------- Checkbox selection state ----------
CHECKED = set()  # set of row keys (iids) that are checked

def _checkbox_core(key):
    return '☑' if key in CHECKED else '☐'

def _checkbox_cell_for(key):
    return f'  {_checkbox_core(key)}'

def _visible_keys(app: App):
    return list(app.tbl.get_children())

# ---------- Rendering ----------
def _parse_date_input(s: str):
    s = (s or '').strip()
    if not s: return None
    try: return pd.to_datetime(s, errors='raise').date()
    except Exception: return None

def _val(entry, var):
    try:
        # ignore placeholder if present
        if getattr(entry, "_ph_active", False):
            return ""
    except Exception:
        pass
    try: return var.get()
    except Exception: return ""

def row_key_from_values(date, price, iban, comment, name) -> str:
    # stable per-row key; include row data
    raw = "|".join([date or "", price or "", iban or "", comment or "", name or ""])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

def rebuild_index(raw_rows):
    global _df
    recs = []
    for row_no, date, price, details in raw_rows:
        name, iban, comment = split_details(details)
        try: rn = int(str(row_no).split('.')[0])
        except Exception: rn = 0
        key = row_key_from_values(str(date or ''), str(price or ''), iban, comment, name)
        recs.append({
            'date': '' if date is None else str(date),
            'price': '' if price is None else str(price),
            'name': name, 'iban': iban, 'comment': comment,
            'row_no': rn, 'name_norm': normalize(name), 'key': key
        })
    _df = pd.DataFrame(recs)
    if not _df.empty:
        _df.sort_values(by=['row_no'], ascending=[False], inplace=True)
    _df['date_obj'] = pd.to_datetime(_df['date'], errors='coerce').dt.date

# Dataframe initial
_df = pd.DataFrame(columns=[
    'date','price','name','iban','comment','row_no','name_norm','date_obj','key'
])

def render(app: App):
    """
    DRASTICALLY OPTIMIZED render for Windows.
    
    - Batched row insertion (100 rows at a time)
    - Limit visible rows (500 max)
    - Incremental rendering with progress
    - No blocking operations
    """
    # Get filters
    q = normalize(_val(app.ent_name, app.var_q))
    d_from = _parse_date_input(_val(app.ent_from, app.var_from))
    d_to = _parse_date_input(_val(app.ent_to, app.var_to))
    
    # Fast filter
    view = _df
    if len(_df) > 0:
        if d_from is not None or d_to is not None:
            date_mask = _df['date_obj'].notna()
            if d_from is not None:
                date_mask &= (_df['date_obj'] >= d_from)
            if d_to is not None:
                date_mask &= (_df['date_obj'] <= d_to)
            view = view[date_mask]
        
        if q:
            view = view[view['name_norm'].str.contains(q, na=False)]
    
    # Remember selection
    current_sel = app.tbl.selection()
    current_sel = current_sel[0] if current_sel else None
    
    # Clear table
    app.tbl.delete(*app.tbl.get_children())
    
    from user_data import load_notes
    notes_map = load_notes() or {}
    
    # Initialize or preserve cache
    if not hasattr(app, '_rowkey_to_iid_cache'):
        app._rowkey_to_iid_cache = {}
    
    # Collect visible row keys
    visible_keys = set()
    
    # WINDOWS OPTIMIZATION: Limit visible rows
    total_rows = len(view)
    if IS_WINDOWS and total_rows > MAX_VISIBLE_ROWS:
        # Show status
        if hasattr(app, 'lbl_status'):
            app.lbl_status.config(text=f"⚠️ Showing first {MAX_VISIBLE_ROWS} of {total_rows} rows (filtered)")
        view = view.head(MAX_VISIBLE_ROWS)
    
    # WINDOWS OPTIMIZATION: Batch insert rows
    batch_rows = []
    batch_size = RENDER_BATCH_SIZE
    
    for idx, (_, r) in enumerate(view.iterrows()):
        key = r['key']
        visible_keys.add(key)
        note_val = notes_map.get(key, "")
        note_mark = '📝' if str(note_val).strip() else ''
        st = STATUS.get(key, {'pkg':0,'stk':0})
        tag = status_to_tag(st)
        
        # Collect for batch
        batch_rows.append((key, (_checkbox_cell_for(key), r['date'], r['price'],
                                  r['iban'], r['comment'], r['name'], note_mark), tag))
        
        # Insert batch when full
        if len(batch_rows) >= batch_size:
            _insert_batch(app, batch_rows)
            batch_rows = []
            
            # Update progress on Windows
            if IS_WINDOWS and hasattr(app, 'lbl_status'):
                progress = int((idx / len(view)) * 100)
                app.lbl_status.config(text=f"Rendering... {progress}%")
                app.update_idletasks()
    
    # Insert remaining rows
    if batch_rows:
        _insert_batch(app, batch_rows)
    
    # Build cache
    for key in visible_keys:
        app._rowkey_to_iid_cache[key] = key
    
    # CLEANUP: Only destroy note widgets for rows NOT in visible set
    if hasattr(app, '_note_widgets'):
        to_remove = [iid for iid in app._note_widgets.keys() if iid not in visible_keys]
        for iid in to_remove[:20]:  # Limit to 20 per render
            try:
                app._note_widgets[iid].destroy()
                del app._note_widgets[iid]
            except:
                pass
    
    # Restore selection
    kids = app.tbl.get_children()
    target = current_sel if (current_sel in kids) else (kids[0] if kids else None)
    if target:
        app.tbl.selection_set(target)
        app.tbl.focus(target)
        
        # Update comment
        vals = app.tbl.item(target, 'values')
        cols = list(app.tbl['columns'])
        try:
            ci = cols.index('comment')
            app.set_comment(vals[ci] if ci < len(vals) else '')
        except:
            app.set_comment('')
    else:
        app.set_comment('')
        if hasattr(app, 'txt_note'):
            try:
                app.txt_note.delete('1.0', 'end')
            except:
                pass
    
    # Clear status
    if hasattr(app, 'lbl_status'):
        app.lbl_status.config(text="")

def _insert_batch(app, batch_rows):
    """Insert a batch of rows into TreeView - OPTIMIZED."""
    for key, values, tag in batch_rows:
        try:
            app.tbl.insert('', 'end', iid=key, values=values, tags=(tag,))
        except:
            pass

def refresh_with_cache_clear(app: App):
    """Refresh data, clearing cache first to get fresh Google Sheets data."""
    try:
        cfg = read_user_config()
        is_sheets = cfg.get('data_source') == 'google_sheets'
        
        if is_sheets:
            # Clear cache to force fresh data
            clear_cache()
            print("🔄 Cache cleared - fetching fresh data from Google Sheets...")
            
            # Show status
            if hasattr(app, 'lbl_status'):
                app.lbl_status.config(text="🔄 Refreshing from Google Sheets...")
                app.update_idletasks()
        
        # Now load with fresh data
        load_and_render_async(app)
        
    except Exception as e:
        messagebox.showerror("Refresh Error", f"Failed to refresh:\n\n{e}")

def load_and_render_async(app: App):
    """
    DRASTICALLY OPTIMIZED: Load data in background thread.
    
    - Never blocks UI
    - Shows loading progress
    - Incremental rendering
    - Windows splash screen
    """
    
    # Show loading indicator
    if hasattr(app, 'lbl_status'):
        app.lbl_status.config(text="📊 Loading data...")
    
    def _background_load():
        try:
            cfg = read_user_config()
            is_sheets = cfg.get('data_source') == 'google_sheets'
            
            # Update status on main thread
            if is_sheets:
                app.after(0, lambda: _update_status(app, "📊 Fetching from Google Sheets..."))
            
            # SLOW OPERATION: Fetch in background
            rows = fetch_rows(cfg)
            
            # Update status
            app.after(0, lambda: _update_status(app, "🔄 Processing data..."))
            
            # Rebuild index
            rebuild_index(rows)
            
            # Update status
            app.after(0, lambda: _update_status(app, "🎨 Rendering..."))
            
            # Render on main thread
            app.after(0, lambda: _finish_load(app))
            
        except Exception as e:
            app.after(0, lambda: messagebox.showerror("Error", str(e)))
            app.after(0, lambda: _update_status(app, ""))
    
    def _update_status(app, msg):
        if hasattr(app, 'lbl_status'):
            app.lbl_status.config(text=msg)
    
    def _finish_load(app):
        render(app)
        _update_status(app, "✅ Ready!")
        app.after(2000, lambda: _update_status(app, ""))
    
    # Start background thread
    threading.Thread(target=_background_load, daemon=True).start()

def load_and_render(app: App):
    """Wrapper that calls async version."""
    load_and_render_async(app)

# ---------- Toggle / clear actions ----------

def toggle_status_for_keys(field, keys):
    """OPTIMIZED: Instant status toggle - never blocks."""
    changed = []
    for key in keys:
        st = STATUS.get(key, {'pkg':0,'stk':0})
        st[field] = 0 if st.get(field) else 1
        STATUS[key] = st
        changed.append((key, status_to_tag(st)))
    
    # INSTANT: Save asynchronously (never blocks)
    save_status(STATUS)
    
    return changed

def toggle_status(field, app: App):
    """OPTIMIZED: Instant toggle with no UI lag."""
    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {sel[0]}
    if not keys: return
    
    # Get changes
    changed = toggle_status_for_keys(field, keys)

    # INSTANT: Update UI immediately
    for key, tag in changed:
        try:
            vals = app.tbl.item(key, 'values')
            app.tbl.item(key, values=(_checkbox_cell_for(key), *vals[1:]), tags=(tag,))
        except Exception:
            pass

def clear_status_for_keys(keys):
    """OPTIMIZED: Clear status instantly."""
    for key in keys:
        STATUS.pop(key, None)
    save_status(STATUS)

def clear_status_selected(app: App):
    """OPTIMIZED: Instant clear."""
    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {sel[0]}
    if not keys: return
    
    clear_status_for_keys(keys)
    
    # Update UI instantly
    for key in keys:
        try:
            vals = app.tbl.item(key, 'values')
            app.tbl.item(key, values=(_checkbox_cell_for(key), *vals[1:]), tags=('none',))
        except:
            pass

def on_tree_click(app: App, event):
    """Handle clicks - toggle checkbox if in first column."""
    region = app.tbl.identify_region(event.x, event.y)
    if region != 'cell': return
    
    col = app.tbl.identify_column(event.x)
    iid = app.tbl.identify_row(event.y)
    if not iid: return
    
    # Toggle checkbox
    if col == '#1':
        if iid in CHECKED:
            CHECKED.remove(iid)
        else:
            CHECKED.add(iid)
        vals = app.tbl.item(iid, 'values')
        app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))

def on_select_change(app: App, event):
    """Handle selection changes - update comment and notes."""
    # CRITICAL: Call ui.py's method to refresh bottom boxes (statement + custom note)
    if hasattr(app, '_refresh_bottom_from_selection'):
        try:
            app._refresh_bottom_from_selection()
        except Exception as e:
            print(f"Warning: Failed to refresh bottom boxes: {e}")
    
    # Fallback for comment only
    sel = app.tbl.selection()
    if not sel: 
        if hasattr(app, 'set_comment'):
            app.set_comment('')
        return
    
    vals = app.tbl.item(sel[0], 'values')
    cols = list(app.tbl['columns'])
    
    try:
        ci = cols.index('comment')
        if hasattr(app, 'set_comment'):
            app.set_comment(vals[ci] if ci < len(vals) else '')
    except:
        if hasattr(app, 'set_comment'):
            app.set_comment('')

def select_all(app: App):
    """OPTIMIZED: Instant select all."""
    visible = app.tbl.get_children()
    CHECKED.update(visible)
    for iid in visible:
        try:
            vals = app.tbl.item(iid, 'values')
            app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))
        except:
            pass

def clear_selection(app: App):
    """OPTIMIZED: Instant clear selection."""
    visible = app.tbl.get_children()
    CHECKED.clear()
    for iid in visible:
        try:
            vals = app.tbl.item(iid, 'values')
            app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))
        except:
            pass

def clear_filters(app: App):
    """OPTIMIZED: Clear filters instantly."""
    app.var_q.set('')
    app.var_from.set('')
    app.var_to.set('')
    
    # Reset placeholders
    for entry in [app.ent_name, app.ent_from, app.ent_to]:
        if hasattr(entry, '_ph_active'):
            entry._ph_active = True
            entry.delete(0, 'end')
            entry.insert(0, entry._ph_text)
            entry.config(fg='#888888')
    
    # Debounced render (only expensive operation)
    if not hasattr(app, '_render_debouncer'):
        app._render_debouncer = OperationDebouncer(app, delay=FILTER_DEBOUNCE)
    
    app._render_debouncer.debounce('render', lambda: render(app))

def _guard_shortcut(app, fn):
    """Guard shortcuts."""
    def wrapper(event):
        fn(app)
        return 'break'
    return wrapper

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
    
    # Check trial/license
    allowed, msg = check_trial()
    if not allowed:
        root = tk.Tk()
        root.withdraw()
        act = show_license_dialog(root)
        root.destroy()
        if not act:
            _mb.showwarning("TrackNote", "Trial expired. Please contact support.")
            return
        allowed, msg = check_trial()
        if not allowed:
            _mb.showerror("TrackNote", "License activation failed.")
            return
    
    # WINDOWS OPTIMIZATION: Show loading splash
    loading = None
    if IS_WINDOWS:
        try:
            loading = tk.Tk()
            loading.overrideredirect(True)
            loading.geometry('400x150+500+300')
            loading.configure(bg='white')
            tk.Label(loading, text='⚡ Loading TrackNote...', bg='white', font=('Arial', 16, 'bold')).pack(pady=20)
            tk.Label(loading, text='Optimized for Windows', bg='white', font=('Arial', 10), fg='#666').pack()
            tk.Label(loading, text='Please wait...', bg='white', font=('Arial', 10), fg='#666').pack(pady=10)
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
    
    # Windows optimization notice
    if IS_WINDOWS:
        print("⚡ Windows Performance Mode: MAXIMUM")
        print(f"  • Render batch size: {RENDER_BATCH_SIZE}")
        print(f"  • Max visible rows: {MAX_VISIBLE_ROWS}")
        print(f"  • Async everything: ON")
    
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
                    
                    print(f"✓ Loaded {len(STATUS)} status entries from Firebase")
                except Exception as e:
                    print(f"⚠️ Failed to load Firebase data: {e}")
        except Exception as e:
            print(f"⚠️ Firebase initialization failed: {e}")
            FIREBASE_SYNC = None
    else:
        FIREBASE_SYNC = None
    
    # Wire up buttons
    app.btn_refresh.config(command=lambda: refresh_with_cache_clear(app))
    app.btn_clear_filters.config(command=lambda: clear_filters(app))
    app.btn_select_all.config(command=lambda: select_all(app))
    app.btn_clear_sel.config(command=lambda: clear_selection(app))
    app.btn_toggle_pkg.config(command=lambda: toggle_status('pkg', app))
    app.btn_toggle_stk.config(command=lambda: toggle_status('stk', app))
    
    # OPTIMIZED: Debounced filter bindings
    try:
        debouncer = OperationDebouncer(app, delay=FILTER_DEBOUNCE)
        
        def _schedule_render():
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
            
            debouncer.debounce('render', lambda: render(app))
        
        app.var_q.trace_add('write', lambda *_: _schedule_render())
        app.var_from.trace_add('write', lambda *_: _schedule_render())
        app.var_to.trace_add('write', lambda *_: _schedule_render())
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

    # Initial load (async)
    load_and_render_async(app)

    # Configure TreeView tags
    configure_tags(app)

    # ===== FIREBASE REAL-TIME SYNC =====
    def on_firebase_change(change_type: str, row_key: Optional[str], data):
        """Handle Firebase changes instantly."""
        try:
            global STATUS
            
            if change_type == 'status' and row_key:
                if data:
                    STATUS[row_key] = {'pkg': data.get('pkg', 0), 'stk': data.get('stk', 0)}
                else:
                    STATUS.pop(row_key, None)
                
                # Update UI if visible
                try:
                    visible_iids = set(app.tbl.get_children())
                    if row_key in visible_iids:
                        st = STATUS.get(row_key, {'pkg': 0, 'stk': 0})
                        tag = status_to_tag(st)
                        app.tbl.item(row_key, tags=(tag,))
                except:
                    pass
                    
        except Exception:
            pass

    # Start Firebase listener
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            FIREBASE_SYNC.start_listener(on_firebase_change)
            print("✓ Real-time sync active")
        except Exception as e:
            print(f"⚠ Failed to start Firebase listener: {e}")

    # ===== AUTO-REFRESH =====
    def auto_refresh():
        try:
            if getattr(app, '_is_closing', False):
                return
            if not app.winfo_exists():
                return
            load_and_render_async(app)
        except Exception:
            pass
        finally:
            try:
                if not getattr(app, '_is_closing', False) and app.winfo_exists():
                    app.after(60000, auto_refresh)
            except:
                pass

    app.after(60000, auto_refresh)

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