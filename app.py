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



from parsing import split_details, normalize
from data_source import fetch_rows
from sheets_cache import clear_cache
from ui import App
from firebase_sync import FirebaseSync, load_firebase_config
from typing import Optional, Tuple, Dict

# --- Licensing: fingerprint, Ed25519 verify, trial ---
import base64, platform, subprocess, uuid, datetime as _dt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from tkinter import simpledialog as _sd
from user_data import read_user_config, write_user_config, read_license_key, store_license_key


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
        except Exception as e:
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

def load_and_render_async(app: App):
    """Load in background thread."""
    
    def _background_load():
        try:
            # Show loading
            app.after(0, lambda: _update_status(app, "📊 Loading..."))
            
            # Fetch (slow part in background)
            cfg = read_user_config()
            rows = fetch_rows(cfg)
            
            # Rebuild index
            rebuild_index(rows)
            
            # Render in main thread
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
    
    # Start thread
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
    # Fallback: MAC + arch
    mac = uuid.getnode()
    arch = platform.machine()
    return f"{mac:012x}-{arch}".lower()

def verify_license_key(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    """
    license string format (compact JWT-like):
      <payload_b64url>.<signature_b64url>
    payload JSON fields:
      fp: machine fingerprint (string, lowercased)
      prod: product code, e.g., "TrackNote"
      exp: ISO date string "YYYY-MM-DD" (inclusive)
      ver: optional product version, e.g., ">=0.1.0"
    signed with Ed25519 (PUBLIC_KEY_B64).
    """
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

    # semantic checks
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
    """Ask for a key; verify; store if valid. Returns True if activated."""
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
    # Check for license key in license.key file
    key = read_license_key()
    if key:
        ok, msg, pl = verify_license_key(key)
        if ok:
            exp = pl.get("exp")
            return f"Licensed for this computer. Expires: {exp or 'Never (no expiry)'}"
        return f"License present but invalid: {msg}"
    
    # No key → compute trial days left
    cfg = read_user_config()
    created = cfg.get("first_run_date")  # Fixed field name!
    try:
        start = _dt.datetime.fromisoformat(created).date() if created else _dt.date.today()
    except Exception:
        start = _dt.date.today()
    days_used = (_dt.date.today() - start).days
    left = max(0, TRIAL_DAYS - days_used)
    return f"Trial: {left} day(s) left"


# --- First-run version & updater helpers (single source of truth) ---
import sys, datetime, traceback
from pathlib import Path
import json as _json, urllib.request as _u, platform as _plat, webbrowser as _wb
from tkinter import messagebox as _mb
from user_data import create_user_config_if_missing, user_data_dir, load_notes, save_notes

def _bundle_base() -> Path:
    """Folder where bundled files live (works for dev & PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # PyInstaller temp dir
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent  # .../TrackNote.app/Contents/MacOS
    return Path(__file__).resolve().parent

CONFIG_PATH = _bundle_base() / "config_template.json"
CFG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_app_version(default: str = "0.1.0") -> str:
    try:
        return (_bundle_base() / "VERSION").read_text(encoding="utf-8").strip() or default
    except Exception:
        return default

def save_note_for_selected(app):
    """Read text from bottom right box and save to per-user notes_store.json."""
    sel = app.tbl.selection()
    if not sel:
        return
    iid = sel[0]
    try:
        app.txt_note.configure(state='normal')
        note = app.txt_note.get("1.0", "end-1c")
    finally:
        app.txt_note.configure(state='disabled')
    try:
        m = load_notes() or {}
        if note.strip():
            m[iid] = note
        else:
            m.pop(iid, None)
        save_notes(m)
    except Exception:
        pass
    # Update the "Note" indicator in the table
    try:
        vals = list(app.tbl.item(iid, 'values'))
        cols = list(app.tbl['columns'])
        if 'Note' in cols:
            ci = cols.index('Note')
            if ci < len(vals):
                vals[ci] = '📝' if note.strip() else ''
                app.tbl.item(iid, values=tuple(vals))
    except Exception:
        pass

def begin_edit_note(app):
    """Make the bottom right note box editable and focus it."""
    try:
        app.txt_note.configure(state='normal')
        app.txt_note.focus_set()
    except Exception:
        pass

# --- shortcut guard: ignore when typing in note fields ---

def _is_typing_in_note_widget(app) -> bool:
    w = app.focus_get()
    if w is None:
        return False
    # bottom-right Text box
    if w is getattr(app, 'txt_note', None):
        return True
    # inline note Entry overlays
    if hasattr(app, '_note_widgets'):
        try:
            return any(w is ed for ed in app._note_widgets.values())
        except Exception:
            pass
    return False


def _guard_shortcut(app, fn):
    def _handler(ev=None):
        if _is_typing_in_note_widget(app):
            return 'break'  # stop propagation; do nothing
        fn(app)
        return 'break'
    return _handler


def save_note_and_lock(app):
    """Save note for selected row and make the box read-only again."""
    save_note_for_selected(app)
    try:
        app.txt_note.configure(state='disabled')
    except Exception:
        pass

def _semver_tuple(v: str):
    # very small semver parser: "1.2.3" -> (1,2,3)
    try:
        parts = v.strip().split(".")
        return tuple(int(p) for p in parts[:3] + ["0"]*(3-len(parts)))
    except Exception:
        return (0,0,0)

def _read_manifest(url: str) -> dict:
    req = _u.Request(url, headers={"User-Agent": "TrackNote/Updater"})
    with _u.urlopen(req, timeout=10) as r:
        return _json.loads(r.read().decode("utf-8"))

def check_for_updates(root, manifest_url: str | None):
    if not manifest_url:
        _mb.showinfo("TrackNote", "Auto-update is not configured yet.")
        return
    try:
        remote = _read_manifest(manifest_url)
        remote_ver = str(remote.get("version", "0.0.0"))
        local_ver = get_app_version()
        if _semver_tuple(remote_ver) <= _semver_tuple(local_ver):
            _mb.showinfo("TrackNote", f"You're on the latest version ({local_ver}).")
            return

        # pick platform URL
        is_mac = (_plat.system() == "Darwin")
        url = remote.get("mac_url" if is_mac else "win_url")
        notes = str(remote.get("notes", "")).strip()
        msg = f"New version {remote_ver} is available.\n\n{notes}" if notes else f"New version {remote_ver} is available."
        if url and _mb.askyesno("TrackNote Update", msg + "\n\nOpen download page?"):
            _wb.open(url)
        elif not url:
            _mb.showwarning("TrackNote Update", "Update is available, but no download URL was provided.")
    except Exception as e:
        _mb.showerror("TrackNote Update", f"Failed to check for updates.\n\n{e}")

# --- Finder launch guard + startup log (single definition) ---
import traceback, datetime

def _startup_log(extra: dict | None = None):
    try:
        log_dir = user_data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "launch.log", "a", encoding="utf-8") as lf:
            rec = {"ts": datetime.datetime.now().isoformat(), "cwd": os.getcwd(),
                   "exe": sys.executable, "argv": sys.argv, "frozen": bool(getattr(sys, "frozen", False))}
            if extra: rec.update(extra)
            lf.write(json.dumps(rec) + "\n")
    except Exception:
        pass

def _guarded_main():
    try:
        _startup_log({"phase": "before-main", "CONFIG_PATH": str(CONFIG_PATH)})
    except Exception:
        pass
    try:
        main()
    except Exception:
        try:
            log_dir = user_data_dir() / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "launch.log", "a", encoding="utf-8") as lf:
                lf.write("\n=== Finder launch error ===\n")
                lf.write(traceback.format_exc())
        except Exception:
            pass
        raise

# ---------- Config / App data ----------

# ---------- Config / App data (with Firebase sync) ----------

APPDATA = os.getenv('APPDATA')
BASE = Path(APPDATA) if APPDATA else (Path.home() / "Library/Application Support")
APPDIR = BASE / "TrackNote"
APPDIR.mkdir(parents=True, exist_ok=True)

# Initialize Firebase sync
FIREBASE_CONFIG = load_firebase_config()
if FIREBASE_CONFIG:
    try:
        # Get the sheet ID from config to use as namespace
        cfg = read_user_config()
        sheet_id = cfg.get('spreadsheet_id', 'default')
        
        FIREBASE_SYNC = FirebaseSync(
            FIREBASE_CONFIG['database_url'],
            FIREBASE_CONFIG['project_id'],
            namespace=sheet_id  # NEW! Use sheet ID as namespace
        )
        if FIREBASE_SYNC.is_connected():
            print("🔥 Firebase sync enabled - changes sync in 5 seconds")
    except Exception as e:
        print(f"⚠ Failed to connect to Firebase: {e}")
        FIREBASE_SYNC = None
else:
    FIREBASE_SYNC = None
    print("ℹ Firebase not configured - using local storage only")

# Fallback local file storage
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
    """Save status to Firebase and local file."""
    # Save to Firebase first
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            for key, val in obj.items():
                FIREBASE_SYNC.set_status(key, val.get('pkg', 0), val.get('stk', 0))
        except Exception as e:
            print(f"Error saving to Firebase: {e}")
    
    # Also save to local file as backup
    try: 
        STATUS_FILE.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    except Exception: 
        pass

STATUS = load_status()

# ---------- Tag colors ----------
TAGS = {
    'none':     {'bg': '#ffffff'},
    'packaged': {'bg': '#fff4b8'},  # pale yellow
    'sticker':  {'bg': '#dcecff'},  # light blue
    'both':     {'bg': '#d6f5d6'},  # light green
}
def status_to_tag(st):
    if st.get('pkg') and st.get('stk'): return 'both'
    if st.get('pkg'): return 'packaged'
    if st.get('stk'): return 'sticker'
    return 'none'

def configure_tags(app: App):
    for name, spec in TAGS.items():
        try: app.tbl.tag_configure(name, background=spec['bg'])
        except Exception: pass
    # Flash tags for visual feedback
    try: 
        app.tbl.tag_configure('flash_none', background='#FFFFFF')
        app.tbl.tag_configure('flash_packaged', background='#FFB700')
        app.tbl.tag_configure('flash_sticker', background='#0099FF')
        app.tbl.tag_configure('flash_both', background='#00FF00')
    except Exception: pass

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
    """OPTIMIZED render - builds cache incrementally."""
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
    
    notes_map = load_notes() or {}
    
    # Initialize or preserve cache
    if not hasattr(app, '_rowkey_to_iid_cache'):
        app._rowkey_to_iid_cache = {}
    
    # Collect visible row keys
    visible_keys = set()
    
    # Insert all rows and build cache incrementally
    for _, r in view.iterrows():
        key = r['key']
        visible_keys.add(key)  # Track visible rows
        note_val = notes_map.get(key, "")
        note_mark = '📝' if str(note_val).strip() else ''
        st = STATUS.get(key, {'pkg':0,'stk':0})
        tag = status_to_tag(st)
        
        app.tbl.insert('', 'end', iid=key,
                      values=(_checkbox_cell_for(key), r['date'], r['price'],
                            r['iban'], r['comment'], r['name'], note_mark),
                      tags=(tag,))
        
        # Build cache incrementally (O(1) per row instead of O(n) at end)
        app._rowkey_to_iid_cache[key] = key
    
    # CLEANUP: Only destroy note widgets for rows NOT in visible set
    if hasattr(app, '_note_widgets'):
        to_remove = [iid for iid in app._note_widgets.keys() if iid not in visible_keys]
        for iid in to_remove:
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
        # No rows visible - clear comment and note areas
        app.set_comment('')
        if hasattr(app, 'txt_note'):
            try:
                app.txt_note.delete('1.0', 'end')
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
        load_and_render(app)
        
    except Exception as e:
        messagebox.showerror("Refresh Error", f"Failed to refresh:\n\n{e}")


def load_and_render(app: App):
    """Load data with progress feedback for slow sources."""
    try:
        cfg = read_user_config()
        
        # Check if using Google Sheets
        is_sheets = cfg.get('data_source') == 'google_sheets'
        
        if is_sheets:
            # Show loading message
            try:
                if hasattr(app, 'lbl_status'):
                    app.lbl_status.config(text="📊 Loading from Google Sheets...")
                    app.update_idletasks()
            except:
                pass
        
        # Fetch data (slow part)
        rows = fetch_rows(cfg)
        
        if is_sheets:
            try:
                if hasattr(app, 'lbl_status'):
                    app.lbl_status.config(text="✓ Loaded! Rendering...")
                    app.update_idletasks()
            except:
                pass
        
    except Exception as e:
        messagebox.showerror("TrackNote", f"Failed to fetch data:\n\n{e}")
        return
    
    rebuild_index(rows)
    render(app)
    
    # Clear status
    try:
        if hasattr(app, 'lbl_status'):
            app.lbl_status.config(text="")
    except:
        pass

# ---------- Toggle / clear actions ----------
def _visible_keys(app: App):
    return list(app.tbl.get_children())

def toggle_status_for_keys(field, keys):
    changed = []
    for key in keys:
        st = STATUS.get(key, {'pkg':0,'stk':0})
        st[field] = 0 if st.get(field) else 1
        STATUS[key] = st
        changed.append((key, status_to_tag(st)))
    save_status(STATUS)
    return changed

def toggle_status(field, app: App):
    # Show quick status
    try:
        if hasattr(app, 'lbl_status'):
            app.lbl_status.config(text="Updating...")
            app.update_idletasks()
    except:
        pass

    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {sel[0]}
    if not keys: return
    changed = toggle_status_for_keys(field, keys)

    # recolor rows and update checkbox glyphs
    for key, tag in changed:
        try:
            vals = app.tbl.item(key, 'values')
            app.tbl.item(key, values=(_checkbox_cell_for(key), *vals[1:]), tags=(tag,))
        except Exception:
            pass
    
    # Update selection color immediately for the last changed row
    last_tag = changed[-1][1] if changed else 'none'
    
    # Darker versions of the status colors for selected state
    tag_to_selected_color = {
        'none': '#79B8FF',      # default blue (unchanged)
        'packaged': '#FFB84D',  # darker yellow/orange
        'sticker': '#5EB1FF',   # darker blue
        'both': '#66D966',      # darker green
    }
    
    tag_to_fg = {
        'none': '#111111',
        'packaged': '#111111',
        'sticker': '#111111',
        'both': '#111111'
    }
    
    # Apply the new selection color based on status
    selected_bg = tag_to_selected_color.get(last_tag, '#79B8FF')
    selected_fg = tag_to_fg.get(last_tag, '#111111')
    
    try:
        app.style.map(
            "Treeview",
            background=[('selected', selected_bg), ('selected','!focus', selected_bg)],
            foreground=[('selected', selected_fg), ('selected','!focus', selected_fg)],
        )
    except Exception:
        pass
    
    # Store current selection colors so reset works
    app._sel_current_bg = selected_bg
    app._sel_current_fg = selected_fg
    
    # Show status message
    if changed:
        field_name = "PACKAGED" if field == 'pkg' else "STICKER"
        status_msgs = {
            'none': f"❌ Cleared from {len(changed)} row(s)",
            'packaged': f"📦 {len(changed)} row(s) → PACKAGED",
            'sticker': f"🏷️ {len(changed)} row(s) → STICKER",
            'both': f"✅ {len(changed)} row(s) → BOTH"
        }
        msg = status_msgs.get(last_tag, f"✓ Toggled {len(changed)} row(s)")
        try:
            original_title = app.title()
            app.title(msg)
            app.after(2000, lambda: app.title(original_title))
        except Exception:
            pass
    try:
        app.lbl_status.config(text="")
    except:
        pass

def clear_status_selected(app: App):
    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {sel[0]}
    if not keys: return
    for key in keys:
        if key in STATUS: del STATUS[key]
        app.tbl.item(key, tags=('none',))
    save_status(STATUS)
    # leave current selection color as-is until selection changes

def on_tree_click(app: App, event):
    region = app.tbl.identify('region', event.x, event.y)
    if region != 'cell': return
    col = app.tbl.identify_column(event.x)  # '#1' is 'sel'
    if col != '#1': return
    row_id = app.tbl.identify_row(event.y)
    if not row_id: return
    if row_id in CHECKED: CHECKED.remove(row_id)
    else: CHECKED.add(row_id)
    vals = app.tbl.item(row_id, 'values')
    app.tbl.item(row_id, values=( _checkbox_cell_for(row_id), *vals[1:] ))

def select_all_visible(app: App):
    CHECKED.clear()
    for key in _visible_keys(app):
        CHECKED.add(key)
        vals = app.tbl.item(key, 'values')
        app.tbl.item(key, values=(_checkbox_cell_for(key), *vals[1:] ))

def clear_selection(app: App):
    for key in list(CHECKED):
        vals = app.tbl.item(key, 'values')
        app.tbl.item(key, values=('  ☐', *vals[1:] ))
    CHECKED.clear()

def clear_filters(app: App):
    try:
        app.var_q.set('')
        app.var_from.set('')
        app.var_to.set('')
        render(app)
    except Exception:
        pass

def flash_row(app: App, iid: str, target_tag: str):
    """Flash row with highly visible animation."""
    try:
        # MUCH brighter flash colors
        flash_colors = {
            'none': '#FFFFFF',      # pure white flash
            'packaged': '#FFB700',  # bright orange/gold flash
            'sticker': '#0099FF',   # vivid blue flash  
            'both': '#00FF00',      # vivid green flash
        }
        flash_color = flash_colors.get(target_tag, '#FFFF00')
        
        # Flash THREE times for visibility
        flash_tag = f'flash_{target_tag}'
        try:
            app.tbl.tag_configure(flash_tag, background=flash_color)
        except Exception:
            pass
        
        # Flash sequence: bright -> normal -> bright -> normal -> bright -> final
        app.tbl.item(iid, tags=(flash_tag,))
        app.after(100, lambda: app.tbl.item(iid, tags=(target_tag,)))
        app.after(200, lambda: app.tbl.item(iid, tags=(flash_tag,)))
        app.after(300, lambda: app.tbl.item(iid, tags=(target_tag,)))
        app.after(400, lambda: app.tbl.item(iid, tags=(flash_tag,)))
        app.after(500, lambda: app.tbl.item(iid, tags=(target_tag,)))
    except Exception:
        pass

def on_select_change(app: App, event=None):
    sel = app.tbl.selection()
    if not sel:
        app.set_comment('')
        # Reset to default blue when nothing selected
        try:
            app.style.map(
                "Treeview",
                background=[('selected', app._sel_default_bg), ('selected','!focus', app._sel_default_bg)],
                foreground=[('selected', app._sel_default_fg), ('selected','!focus', app._sel_default_fg)],
            )
        except Exception:
            pass
        return
    
    iid = sel[0]
    vals = app.tbl.item(iid, 'values')
    cols = list(app.tbl['columns'])
    
    # Get comment
    try:
        ci = cols.index('comment')
        comment = vals[ci] if ci < len(vals) else ''
    except Exception:
        comment = ''
    app.set_comment(comment)
    
    # Update selection color based on this row's status
    try:
        tags = app.tbl.item(iid, 'tags')
        current_tag = tags[0] if tags else 'none'
        
        # Darker versions of status colors for selected state
        tag_to_selected_color = {
            'none': '#79B8FF',      # default blue
            'packaged': '#FFB84D',  # darker yellow
            'sticker': '#5EB1FF',   # darker blue
            'both': '#66D966',      # darker green
        }
        
        selected_bg = tag_to_selected_color.get(current_tag, '#79B8FF')
        selected_fg = '#111111'
        
        app.style.map(
            "Treeview",
            background=[('selected', selected_bg), ('selected','!focus', selected_bg)],
            foreground=[('selected', selected_fg), ('selected','!focus', selected_fg)],
        )
    except Exception:
        pass

# ---------- Main ----------
def main():
    # === CREATE HIDDEN ROOT FIRST TO PREVENT EMPTY WINDOWS ===
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()  # Hide immediately
    
    # === LOADING SCREEN DISABLED ===
    # The loading screen was causing Tk window conflicts
    # Keeping it disabled for stability
    loading = None
    
    # --- Load configuration ---
    cfg = read_user_config()
    if loading and hasattr(loading, 'status'):
        try:
            loading.update_status("Connecting to Firebase...")
        except:
            pass
    
    # --- Trial / license gate ---
    created = cfg.get("first_run_date")
    try:
        start = _dt.datetime.fromisoformat(created).date() if created else _dt.date.today()
    except Exception:
        start = _dt.date.today()
    days_used = (_dt.date.today() - start).days
    days_left = TRIAL_DAYS - days_used

    key = read_license_key()
    licensed = False
    if key:
        ok, _msg, _ = verify_license_key(key)
        licensed = ok

    if not licensed and days_left < 0:
        # Trial over → ask for key; if canceled, exit.
        if loading:
            try:
                loading.close()
            except:
                pass
            loading = None  # Close loading screen for dialogs
        _mb.showwarning("TrackNote", "Your 14-day trial has ended. Please enter a license key to continue.", parent=root)
        if not show_license_dialog(root):
            _mb.showinfo("TrackNote", "TrackNote will now quit.", parent=root)
            sys.exit(0)
        licensed = True
        # Recreate loading screen after license dialog
        try:
            loading = LoadingScreen()
            loading.update_status("Initializing...")
        except:
            loading = None
    
    # --- FIRST RUN SETUP WIZARD ---
    if loading:
        loading.update_status("Checking setup...")
    
    from data_source import is_configured
    if not is_configured(cfg):
        # Close loading screen for setup wizard
        if loading:
            try:
                loading.close()
            except:
                pass
            loading = None
        
        # Show setup wizard on first run
        from setup_wizard import show_setup_wizard
        completed = show_setup_wizard(None)  # Standalone mode
        
        if not completed:
            messagebox.showinfo("TrackNote", "Setup was cancelled. TrackNote will now quit.")
            sys.exit(0)
        
        # Reload config after wizard
        cfg = read_user_config()
        
        # Recreate loading screen after wizard
        try:
            loading = LoadingScreen()
            loading.update_status("Starting application...")
        except:
            loading = None
    
    # First-run: ensure per-user config exists with current app version
    create_user_config_if_missing(get_app_version())
    
    if loading:
        loading.update_status("Creating application...")
    
    # === DESTROY TEMPORARY ROOT AND CREATE MAIN APP ===
    root.destroy()
    
    app = App()
    app.withdraw()  # Keep hidden until fully loaded
    app._is_closing = False  # Flag to prevent threading crashes on close
    
    # === Initialize performance features ===
    try:
        from loading_screen import QuickLoader
        app.quick_loader = QuickLoader(app)
    except:
        pass
    app.debouncer = OperationDebouncer(app, delay=50)
    
    if loading:
        loading.update_status("Connecting to Firebase...")
    
    # Pass Firebase sync to app
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        app.firebase_sync = FIREBASE_SYNC
    else:
        app.firebase_sync = None
    
    # === Setup menus ===
    try:
        app.help_menu.add_separator()
        app.help_menu.add_command(label="License Status", command=lambda: _mb.showinfo("License", license_status_string()))
        app.help_menu.add_command(label="Enter License Key…", command=lambda: show_license_dialog(app))
    except Exception:
        pass
    
# Add Settings menu item
    def show_settings_dialog():
        """Show settings dialog to change data source."""
        from setup_wizard import show_setup_wizard
        completed = show_setup_wizard(app)
        if completed:
            # Reload data after settings change
            load_and_render(app)

    # Actually add it to the menu (OUTSIDE the function)
    try:
        app.help_menu.add_command(label="Settings", command=show_settings_dialog)
    except Exception:
        pass

    # Add Firebase Sync Setup menu item
    def show_firebase_setup_dialog():
        from firebase_gui_dialog import show_firebase_setup
        completed = show_firebase_setup(app)
        if completed:
            messagebox.showinfo(
                "TrackNote",
                "Firebase configured! Please restart TrackNote for sync to work."
            )
    
    try:
        app.help_menu.add_command(label="Configure Firebase Sync...", command=show_firebase_setup_dialog)
    except Exception:
        pass
    
    # Add Show Fingerprint menu item
    def show_fingerprint():
        fp = get_machine_fingerprint()
        messagebox.showinfo(
            "Machine Fingerprint",
            f"Your machine fingerprint:\n\n{fp}\n\n"
            "Send this to support when requesting a license key."
        )

    try:
        app.help_menu.add_command(label="Show Machine Fingerprint", command=show_fingerprint)
    except Exception:
        pass

    _startup_log({"phase": "created-app"})


    # Help → Edit / Save Custom Note
    try:
        app.help_menu.add_separator()
        app.help_menu.add_command(label="Edit Custom Note", command=lambda: begin_edit_note(app))
        app.help_menu.add_command(label="Save Custom Note", command=lambda: save_note_and_lock(app))
    except Exception:
        pass

    # Keyboard shortcuts
    try:
        app.bind('<Command-e>', _guard_shortcut(app, begin_edit_note))
        app.bind('<Command-s>', _guard_shortcut(app, save_note_and_lock))

        # If you also support Windows:
        app.bind('<Control-e>', _guard_shortcut(app, begin_edit_note))
        app.bind('<Control-s>', _guard_shortcut(app, save_note_and_lock))
    except Exception:
        pass


    configure_tags(app)

    # hook up buttons
    app.btn_refresh.configure(command=lambda: refresh_with_cache_clear(app))
    app.btn_clear_filters.configure(command=lambda: clear_filters(app))
    app.btn_select_all.configure(command=lambda: select_all_visible(app))
    app.btn_clear_sel.configure(command=lambda: clear_selection(app))
    app.btn_toggle_pkg.configure(command=lambda: toggle_status('pkg', app))
    app.btn_toggle_stk.configure(command=lambda: toggle_status('stk', app))
    app.btn_clear_status.configure(command=lambda: clear_status_selected(app))

    # === Live search/date filtering (debounced) ===
    def _schedule_render(*_args):
        try:
            render(app)  # Direct call, no debouncing
        except Exception:
            pass

    try:
        app.var_q.trace_add('write', lambda *_: _schedule_render())
        app.var_from.trace_add('write', lambda *_: _schedule_render())
        app.var_to.trace_add('write', lambda *_: _schedule_render())
        for w in (app.ent_name, app.ent_from, app.ent_to):
            w.bind('<KeyRelease>', lambda e: _schedule_render(), add='+')
            w.bind('<<Paste>>', lambda e: _schedule_render(), add='+')
            w.bind('<<Cut>>',   lambda e: _schedule_render(), add='+')
    except Exception:
        pass

    # events
    app.tbl.bind('<Button-1>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<<TreeviewSelect>>', lambda e: on_select_change(app, e))

    # keyboard shortcuts - use the CORRECT guard function
    app.tbl.bind('<space>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<Key-p>', lambda e: toggle_status('pkg', app))
    app.tbl.bind('<Key-s>', lambda e: toggle_status('stk', app))

    # App-wide keys with guard
    app.bind('<Escape>', lambda e: (_guard_shortcut(app, lambda _: clear_filters(app))(e)))
    app.bind('<Command-BackSpace>', lambda e: (_guard_shortcut(app, lambda _: clear_status_selected(app))(e)))


    # initial load
    load_and_render(app)
    _startup_log({"phase": "before-mainloop"})

    # ===== FIREBASE REAL-TIME SYNC =====
    def on_firebase_change(change_type: str, row_key: Optional[str], data):
        """OPTIMIZED Firebase change handler with batching."""
        try:
            global STATUS
            
            # Batch multiple rapid changes
            if not hasattr(app, '_firebase_batch'):
                app._firebase_batch = {'changes': [], 'timer': None}
            
            # Add change to batch
            app._firebase_batch['changes'].append((change_type, row_key, data))
            
            # Cancel existing timer
            if app._firebase_batch['timer']:
                app.after_cancel(app._firebase_batch['timer'])
            
            # Process batch after 100ms (aggregate rapid changes)
            app._firebase_batch['timer'] = app.after(100, lambda: process_firebase_batch(app))
            
        except Exception as e:
            pass  # Silent failure for performance

    def process_firebase_batch(app):
        """OPTIMIZED batch processor."""
        try:
            if not hasattr(app, '_firebase_batch'):
                return
            
            # Check if window still exists
            if not app.winfo_exists():
                return
                
            changes = app._firebase_batch['changes']
            app._firebase_batch = {'changes': [], 'timer': None}
            
            # Group changes by type
            status_updates = {}
            note_updates = {}
            
            for change_type, row_key, data in changes:
                if change_type == 'status' and row_key:
                    status_updates[row_key] = data
                elif change_type == 'notes' and row_key:
                    note_updates[row_key] = data
            
            # Apply status updates ONLY if row is visible
            visible_iids = set(app.tbl.get_children())
            
            for row_key, data in status_updates.items():
                if data:
                    STATUS[row_key] = {'pkg': data.get('pkg', 0), 'stk': data.get('stk', 0)}
                else:
                    STATUS.pop(row_key, None)
                
                # Update UI only if visible
                if row_key in visible_iids:
                    st = STATUS.get(row_key, {'pkg': 0, 'stk': 0})
                    tag = status_to_tag(st)
                    app.tbl.item(row_key, tags=(tag,))
            
            # Apply note updates ONLY if visible
            for row_key, data in note_updates.items():
                if hasattr(app, '_note_store'):
                    if data:
                        app._note_store[row_key] = data
                    else:
                        app._note_store.pop(row_key, None)
                    
                    # Update editor only if exists and not focused
                    if row_key in visible_iids and hasattr(app, '_note_widgets'):
                        editor = app._note_widgets.get(row_key)
                        if editor and editor != app.focus_get():
                            editor.delete('1.0', 'end')
                            if data:
                                editor.insert('1.0', data)
                            app._set_note_entry_bg(editor)
                                
        except Exception:
            pass  # Silent for performance

    # Start Firebase real-time listener
    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            FIREBASE_SYNC.start_listener(on_firebase_change)
            print("✓ Real-time sync active - changes appear in 5 seconds")
        except Exception as e:
            print(f"⚠ Failed to start Firebase listener: {e}")
    # ===== END FIREBASE SYNC =====

    # ===== AUTO-REFRESH: 60 seconds + instant focus refresh =====
    def auto_refresh():
        try:
            # Check if app is closing
            if getattr(app, '_is_closing', False):
                return
            if not app.winfo_exists():
                return  # Window destroyed, stop refreshing
            load_and_render(app)
        except Exception:
            pass
        finally:
            try:
                if not getattr(app, '_is_closing', False) and app.winfo_exists():
                    app.after(60000, auto_refresh)  # Every 60 seconds
            except:
                pass  # Window destroyed, stop

    def on_focus_refresh(event=None):
        """INSTANT refresh when app regains focus."""
        try:
            # Check if app is closing
            if getattr(app, '_is_closing', False):
                return
            if app.winfo_exists():
                load_and_render(app)
        except Exception:
            pass

    # Start both refresh mechanisms
    app.after(60000, auto_refresh)      # First auto-refresh after 60 sec
    app.bind('<FocusIn>', on_focus_refresh)  # Instant refresh on focus
    # ===== END AUTO-REFRESH =====

    # === START MEMORY MANAGEMENT (every 60 seconds) ===
    def periodic_memory_check():
        try:
            # Check if app is closing
            if getattr(app, '_is_closing', False):
                return
            if not app.winfo_exists():
                return  # Window destroyed, stop
            MemoryManager.cleanup_widgets(app)
            MemoryManager.optimize_caches(app)
        except Exception:
            pass
        finally:
            try:
                if not getattr(app, '_is_closing', False) and app.winfo_exists():
                    app.after(60000, periodic_memory_check)
            except:
                pass  # Window destroyed, stop
    
    app.after(60000, periodic_memory_check)
    # === END MEMORY MANAGEMENT ===

    # === PROPER WINDOW CLOSE HANDLER (FIX FOR THREADING CRASH) ===
    def on_closing():
        """Clean shutdown to prevent threading errors."""
        try:
            # Set flag to stop background operations
            app._is_closing = True
            
            # Cancel all pending after() callbacks
            for after_id in app.tk.call('after', 'info'):
                try:
                    app.after_cancel(after_id)
                except:
                    pass
            
            # Stop Firebase listener if active
            if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
                try:
                    FIREBASE_SYNC.stop_listener()
                except:
                    pass
            
            # Destroy window
            app.quit()
            app.destroy()
        except Exception:
            # Force exit if cleanup fails
            import sys
            sys.exit(0)
    
    # Register close handler
    app.protocol("WM_DELETE_WINDOW", on_closing)
    # === END WINDOW CLOSE HANDLER ===

    # Close loading screen and show main app
    if loading:
        try:
            loading.close()
        except:
            pass

    app.deiconify()  # Show main app window
    
    try:
        app.mainloop()
    except Exception as e:
        # Ignore errors during/after window close
        pass
    
if __name__ == '__main__':
    _guarded_main()