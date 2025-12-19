from __future__ import annotations
import os, json, hashlib
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import pandas as pd
from tkinter import messagebox
from tkinter import messagebox as _mb
import time
import threading
import platform
import re

# Updated import to include the new parser and its errors
from parsing import split_details, normalize, BankStatementParser, StatementParsingError
from data_source import fetch_rows
from sheets_cache import clear_cache
from ui import App
from color_config import ColorConfig
from firebase_sync import FirebaseSync, load_firebase_config
from db_manager import DatabaseManager



from typing import Optional, Tuple, Dict, List

import base64, subprocess, uuid, datetime as _dt
# --- Licensing: fingerprint, Ed25519 verify, trial ---
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from tkinter import simpledialog as _sd
from user_data import read_user_config, write_user_config, read_license_key, store_license_key

# Platform detection for maximum optimization
IS_WINDOWS = platform.system() == "Windows"

# WINDOWS OPTIMIZATION: Aggressive performance settings
if IS_WINDOWS:
    RENDER_BATCH_SIZE = 100
    SCROLL_DEBOUNCE = 50
    FILTER_DEBOUNCE = 200
    MAX_VISIBLE_ROWS = 500
else:
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
        if PSUTIL_AVAILABLE:
            try:
                import psutil
                process = psutil.Process()
                return process.memory_info().rss / 1024 / 1024
            except: return 0
        return 0
    
    @staticmethod
    def cleanup_widgets(app):
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
                    except: pass
        except Exception: pass
        return cleaned
    
    @staticmethod
    def optimize_caches(app):
        MAX_CACHE_SIZE = 2000
        if hasattr(app, '_rowkey_to_iid_cache'):
            if len(app._rowkey_to_iid_cache) > MAX_CACHE_SIZE:
                visible = set(app.tbl.get_children())
                app._rowkey_to_iid_cache = {k: v for k, v in app._rowkey_to_iid_cache.items() if v in visible}

PRODUCT_NAME = "TrackNote"
TRIAL_DAYS = 14
PUBLIC_KEY_B64 = "61izrH-GRDcHS_mLjbxRJoZAFbJqFQbSEsYzB8euFCg"

def _b64url_decode(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/")
    pad = "=" * (-len(s) % 4)
    return base64.b64decode(s + pad)

def get_machine_fingerprint() -> str:
    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    fp = line.split("=")[1].strip().strip('"')
                    if fp: return fp.lower()
        elif platform.system() == "Windows":
            out = subprocess.check_output(["reg", "query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"], text=True)
            return out.split()[-1].lower()
    except Exception: pass
    mac = uuid.getnode()
    arch = platform.machine()
    return f"{mac:012x}-{arch}".lower()

def verify_license_key(license_key: str) -> Tuple[bool, str, Optional[Dict]]:
    try:
        payload_part, sig_part = license_key.strip().split(".", 1)
    except ValueError: return (False, "License format is invalid.", None)
    try:
        payload_bytes = _b64url_decode(payload_part)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception: return (False, "License payload cannot be decoded.", None)
    try:
        pub = Ed25519PublicKey.from_public_bytes(_b64url_decode(PUBLIC_KEY_B64))
        pub.verify(_b64url_decode(sig_part), payload_bytes)
    except (InvalidSignature, ValueError): return (False, "License signature is invalid.", payload)
    except Exception as e: return (False, f"License verify error: {e}", payload)
    fp_now = get_machine_fingerprint()
    if payload.get("fp", "").lower() != fp_now.lower(): return (False, "License is for a different computer.", payload)
    if payload.get("prod") != PRODUCT_NAME: return (False, "License product mismatch.", payload)
    exp = payload.get("exp")
    try:
        if exp and _dt.date.today() > _dt.date.fromisoformat(exp): return (False, f"License expired on {exp}.", payload)
    except Exception: return (False, "License expiry is invalid.", payload)
    return (True, "OK", payload)

def show_license_dialog(app) -> bool:
    while True:
        key = _sd.askstring("Įveskite licencijos raktą", "Įklijuokite savo TrackNote licencijos raktą:", parent=app)
        if key is None: return False
        ok, msg, _pl = verify_license_key(key)
        if ok:
            store_license_key(key)
            _mb.showinfo("TrackNote", "Licencija aktyvuota. Ačiū!")
            return True
        else:
            _mb.showerror("TrackNote", f"{msg}\n\nPatikrinkite ir bandykite dar kartą.")

def license_status_string() -> str:
    key = read_license_key()
    if not key: return ""
    ok, msg, payload = verify_license_key(key)
    if not ok: return ""
    exp_str = payload.get("exp") if payload else None
    if exp_str:
        try:
            exp_date = _dt.date.fromisoformat(exp_str)
            days_left = (exp_date - _dt.date.today()).days
            if days_left <= 0: return ""
            return f"Licencijuota (galioja iki {exp_str})"
        except: return "Licencijuota"
    return "Licencijuota"

def check_trial():
    cfg = read_user_config()
    first_run = cfg.get("first_run_date")
    if not first_run:
        cfg["first_run_date"] = _dt.datetime.now().isoformat()
        write_user_config(cfg)
        return (True, "Bandomoji versija pradėta")
    key = read_license_key()
    if key:
        ok, msg, _pl = verify_license_key(key)
        if ok: return (True, "Licencijuota")
    try:
        first = _dt.datetime.fromisoformat(first_run)
        elapsed = (_dt.datetime.now() - first).days
        if elapsed < TRIAL_DAYS:
            remaining = TRIAL_DAYS - elapsed
            return (True, f"Bandomoji versija: liko {remaining} d.")
        else: return (False, "Bandomoji versija baigėsi")
    except Exception: return (True, "Bandomoji versija aktyvi")

# ===== GLOBALS & APP STATE =====
FIREBASE_SYNC: Optional[FirebaseSync] = None
DB_MANAGER: Optional[DatabaseManager] = None
# VIEW_MODE removed

# ---------- Tag colors & Configuration ----------
def status_to_tag(st: Optional[dict]) -> str:
    if not isinstance(st, dict): st = {}
    return ColorConfig.get_status_tag(st.get('pkg', 0), st.get('stk', 0))

def configure_tags(app: App):
    for name, spec in ColorConfig.get_tag_config().items():
        try: app.tbl.tag_configure(name, background=spec['bg'])
        except Exception: pass

# ---------- Checkbox selection state ----------
# ---------- Checkbox selection state ----------
CHECKED = set()
def _checkbox_cell_for(key): return '  ☑' if key in CHECKED else '  ☐'

# ---------- Undo History ----------
HISTORY = []

def undo_last_action(app: App):
    if not HISTORY: return
    
    last_action = HISTORY.pop()
    if last_action['type'] == 'status':
        data = last_action['data']
        for key, old_status in data.items():
            # Restore status
            pkg, stk = old_status.get('pkg', 0), old_status.get('stk', 0)
            STATUS[key] = old_status
            FIREBASE_SYNC.set_status(key, pkg, stk)
            
            # Optimistic UI update
            if app.tbl.exists(key):
                new_tag = status_to_tag(old_status)
                current_tags = list(app.tbl.item(key, "tags"))
                for t in ColorConfig.get_tag_config().keys():
                    if t in current_tags: current_tags.remove(t)
                current_tags.append(new_tag)
                app.tbl.item(key, tags=tuple(current_tags))
        
        # Update selection style to match restored status
        update_selection_style(app)
        update_counts(app)
        # app.lbl_status.config(text="↺ Undid last action")
        # app.after(2000, lambda: app.lbl_status.config(text=""))

# ---------- Data Handling & Parsing ----------
def _parse_date_input(s: str):
    s = (s or '').strip()
    if not s: return None
    try: return pd.to_datetime(s, errors='raise').date()
    except Exception: return None

def _val(entry, var):
    try:
        if getattr(entry, "_ph_active", False): return ""
    except Exception: pass
    try: return var.get()
    except Exception: return ""

def _parse_price(value) -> float:
    if value is None: return 0.0
    if isinstance(value, (int, float)): return float(value)
    try:
        s = str(value).strip().replace('$', '').replace('€', '').replace('£', '').replace(',', '')
        return float(s) if s else 0.0
    except (ValueError, TypeError): return 0.0

def _create_transaction_fingerprint(tx: dict) -> str:
    try:
        amount_float = _parse_price(tx.get('amount', 0.0))
        standard_amount = f"{amount_float:.2f}"
    except (ValueError, TypeError): standard_amount = "0.00"
    raw_string = "|".join([str(tx.get('date', '')).strip(), str(tx.get('payer', '')).strip(), str(tx.get('details', '')).strip(), standard_amount])
    return hashlib.sha1(raw_string.encode("utf-8")).hexdigest()

# ---------- Status Counting ----------
def update_counts(app: App):
    """Updates the count label in the top bar with current status statistics."""
    global DB_MANAGER
    
    if not DB_MANAGER:
        app.lbl_counts.config(text="")
        return

    # Get stats from SQLite (instant, optimized query)
    stats = DB_MANAGER.get_stats()
    
    total = stats['active']  # Show only active (non-archived) count
    c_none = stats['none']
    c_pkg = stats['packaged']
    c_stk = stats['sticker']
    c_both = stats['done']
    
    # Format: Iš viso: 50 | Nieko: 10 | Supakuota: 5 | Lipdukas: 5 | Atlikta: 30
    text = f"Iš viso: {total}   |   Nieko: {c_none}   |   Supakuota: {c_pkg}   |   Lipdukas: {c_stk}   |   Atlikta: {c_both}"
    app.lbl_counts.config(text=text)

# ---------- Core Rendering Logic ----------
def render(app: App, max_visible_rows: int = 1000, append_mode: bool = False):
    """Renders transactions from SQLite with filtering and virtual scrolling."""
    global DB_MANAGER
    
    if not append_mode:
        # Clear on fresh render
        app.tbl.delete(*app.tbl.get_children())
    else:
        # Remove existing "Load More" button if present
        if app.tbl.exists('load_more_btn'):
            app.tbl.delete('load_more_btn')
    
    if not DB_MANAGER:
        app.lbl_view_info.config(text="Nėra duomenų bazės ryšio.")
        return

    # Get filter values (ignore placeholder text)
    q = (_val(app.ent_name, app.var_q) or "").lower().strip()
    d_from_date = _parse_date_input(_val(app.ent_from, app.var_from))
    d_to_date = _parse_date_input(_val(app.ent_to, app.var_to))
    
    # Convert dates to strings for SQL query
    d_from = str(d_from_date) if d_from_date else None
    d_to = str(d_to_date) if d_to_date else None
    
    # Check if archive view is active
    include_archived = getattr(app, '_archive_visible', False)
    
    # Determine offset for pagination
    if append_mode:
        # Load next batch starting from currently loaded count
        offset = getattr(app, '_loaded_count', 0)
    else:
        # Fresh render, start from 0
        offset = 0
        app._loaded_count = 0
    
    # Store current filters for Load More button
    app._current_filters = {
        'name_query': q if q else None,
        'date_from': d_from,
        'date_to': d_to,
        'include_archived': include_archived
    }
    
    # Query SQLite with filters and VIRTUAL SCROLLING limit
    transactions, total_count = DB_MANAGER.search_transactions(
        name_query=app._current_filters['name_query'],
        date_from=app._current_filters['date_from'],
        date_to=app._current_filters['date_to'],
        include_archived=app._current_filters['include_archived'],
        limit=max_visible_rows,
        offset=offset
    )
    
    # Store total count
    app._total_count = total_count
    
    count = len(transactions)
    if count == 0 and not append_mode:
        app.lbl_view_info.config(text="Nerasta atitinkančių transakcijų.")
        update_counts(app)
        return
    
    # Update loaded count
    if append_mode:
        app._loaded_count += count
    else:
        app._loaded_count = count
    
    # Show viewport info with helpful message
    archive_suffix = " (įskaitant archyvą)" if include_archived else ""
    if app._total_count > app._loaded_count:
        # More results available
        app.lbl_view_info.config(
            text=f"Rodoma {app._loaded_count:,} iš {app._total_count:,} iš viso{archive_suffix} (paspauskite 'Įkelti daugiau' kitai daliai)"
        )
    else:
        # Showing all results
        app.lbl_view_info.config(
            text=f"Rodomos visos {app._loaded_count:,} transakcij{'os' if app._loaded_count!=1 else 'a'}{archive_suffix}"
        )
    
    # Optimized batch rendering
    batch_size = 300 if IS_WINDOWS else 200
    delay = 10 if IS_WINDOWS else 5
    
    # Cancel any previous batch job
    if hasattr(app, 'current_batch_job') and app.current_batch_job:
        try: app.after_cancel(app.current_batch_job)
        except: pass
    app.current_batch_job = None
    
    def _insert_batch(start_idx):
        if getattr(app, '_is_closing', False): 
            return
        
        end_idx = min(start_idx + batch_size, count)
        
        for i in range(start_idx, end_idx):
            tx = transactions[i]
            key = tx['key']
            
            # Determine status tag
            pkg = tx.get('pkg', 0) or 0
            stk = tx.get('stk', 0) or 0
            tag = ColorConfig.get_status_tag(pkg, stk)
            
            values = (
                _checkbox_cell_for(key),
                tx['date'],
                tx.get('price', 0),
                tx.get('iban', ''),
                tx.get('comment', ''),
                tx['name'],
                ''
            )
            
            app.tbl.insert('', 'end', iid=key, values=values, tags=(tag,))
        
        if end_idx < count:
            # Schedule next batch
            app.current_batch_job = app.after(delay, lambda: _insert_batch(end_idx))
        else:
            # Finished rendering all transactions in this batch
            app.current_batch_job = None
            
            # Add "Load More" button if more data available
            if app._loaded_count < app._total_count:
                _add_load_more_button(app)

    # Start first batch immediately
    _insert_batch(0)

    # Update counts after render
    update_counts(app)

def _add_load_more_button(app: App):
    """Adds a Load More button row at the bottom of the Treeview."""
    remaining = app._total_count - app._loaded_count
    button_text = f"▼ Įkelti dar {min(1000, remaining):,} (liko {remaining:,}) ▼"
    
    # Insert special row with button text
    app.tbl.insert('', 'end', iid='load_more_btn', 
                   values=('', '', '', button_text, '', '', ''),
                   tags=('load_more',))
    
    # Style the load more row (blue background, centered text)
    app.tbl.tag_configure('load_more', background='#E3F2FD', foreground='#1976D2', 
                         font=('Segoe UI', 10, 'bold'))

def load_more_transactions(app: App):
    """Loads the next batch of transactions and appends to existing view."""
    render(app, max_visible_rows=1000, append_mode=True)

def load_and_render_async(app: App, include_archive=False):
    """Loads data from local SQLite (instant) and syncs with Firebase in background."""
    global DB_MANAGER
    
    app.lbl_status.config(text="📊 Įkeliami duomenys...")
    
    def _background_load():
        try:
            # INSTANT: Load from local SQLite database
            app.after(0, lambda: render(app))
            app.after(0, lambda: app.lbl_status.config(text="✅ Įkelta"))
            app.after(2000, lambda: app.lbl_status.config(text=""))
            
            # BACKGROUND: Sync with Firebase (non-blocking)
            if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
                _sync_with_firebase()
                
        except Exception as e:
            app.after(0, lambda: messagebox.showerror("Įkėlimo klaida", f"Nepavyko įkelti duomenų:\n{e}"))
            app.after(0, lambda: app.lbl_status.config(text="Įkėlimas nepavyko"))
    
    def _sync_with_firebase():

        """Background sync with Firebase - updates SQLite if there are changes."""
        try:
            # Get Firebase data
            firebase_transactions = FIREBASE_SYNC.get_all_transactions()
            firebase_statuses = FIREBASE_SYNC.get_all_status()
            firebase_notes = FIREBASE_SYNC.get_all_notes()
            
            # Check if we need to import from Firebase (first time or empty DB)
            stats = DB_MANAGER.get_stats()
            if stats['total'] == 0 and firebase_transactions:
                # Import all from Firebase
                print("📥 Importing from Firebase to SQLite...")
                DB_MANAGER.bulk_insert_transactions(firebase_transactions)
                
                # Import statuses
                status_updates = {k: (v.get('pkg', 0), v.get('stk', 0)) 
                                for k, v in firebase_statuses.items()}
                if status_updates:
                    DB_MANAGER.bulk_update_status(status_updates)
                
                # Import notes
                for key, note_text in firebase_notes.items():
                    if note_text and note_text.strip():
                        DB_MANAGER.update_note(key, note_text)
                
                # Refresh UI
                app.after(0, lambda: render(app))
                print("✅ Firebase sync complete")
            
        except Exception as e:
            print(f"⚠️ Background Firebase sync failed: {e}")
    
    threading.Thread(target=_background_load, daemon=True).start()

def import_statement(app: App):
    if not (FIREBASE_SYNC and FIREBASE_SYNC.is_connected()):
        messagebox.showerror("Sinchronizavimo klaida", "Negalima importuoti: nėra ryšio su sinchronizavimo paslauga.")
        return

    def _select_and_import():
        # Prevent crash on macOS by ensuring the dialog opens after the button click event is fully processed
        filepath = filedialog.askopenfilename(
            title="Pasirinkite banko išrašą",
            parent=app,
            filetypes=(
                ("Visi palaikomi", "*.xlsx *.xls *.xml *.pdf"), 
                ("Excel failai", "*.xlsx"), 
                ("XML failai", "*.xml"), 
                ("PDF failai", "*.pdf"), 
                ("Visi failai", "*.*")
            )
        )
        if not filepath: return

        try:
            parser = BankStatementParser()
            parsed_transactions = parser.parse(filepath)
            existing_keys = FIREBASE_SYNC.get_transaction_keys()
            new_records_batch = {}
            new_count, db_duplicate_count, file_duplicate_count = 0, 0, 0
            keys_in_this_import = set()

            for tx in parsed_transactions:
                tx_for_hash = {'date': tx['date'], 'payer': tx['payer'], 'details': tx['details'], 'amount': tx['amount']}
                fingerprint = _create_transaction_fingerprint(tx_for_hash)

                if fingerprint in existing_keys or fingerprint in keys_in_this_import:
                    if fingerprint in existing_keys: db_duplicate_count += 1
                    else: file_duplicate_count += 1
                    continue

                keys_in_this_import.add(fingerprint)
                name, iban, comment = split_details(tx['payer'])
                full_comment = f"{comment} | {tx['details']}".strip(" |") if tx['details'] else comment
                
                # Use parsed IBAN if available, otherwise stick to split_details result
                parsed_iban = tx.get('iban', '')
                final_iban = parsed_iban if parsed_iban else iban

                new_records_batch[fingerprint] = {
                    'key': fingerprint, 'date': tx['date'], 'price': _parse_price(tx['amount']),
                    'name': name, 'iban': final_iban, 'comment': full_comment,
                    'row_no': 0, 'name_norm': normalize(name),
                    'date_obj': pd.to_datetime(tx['date'], errors='coerce').date().isoformat()
                }
                new_count += 1

            if new_records_batch:
                FIREBASE_SYNC.set_transactions_batch(new_records_batch)

            summary = (f"Importavimas baigtas!\n\n✅ Naujų: {new_count}\n⏭️ Praleista (DB): {db_duplicate_count}\n⏭️ Praleista (faile): {file_duplicate_count}")
            messagebox.showinfo("Importavimo santrauka", summary)
            
            # Auto-refresh after import
            load_and_render_async(app)

        except StatementParsingError as e:
            messagebox.showerror("Netinkamas išrašo failas", str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Importavimo klaida", f"Įvyko netikėta klaida: {e}")

    # Initialize idle tasks to process any pending events (like cursor changes) before opening dialog
    app.update_idletasks()
    # Schedule the dialog to open with a slight delay to allow the button click to resolve
    app.after(50, _select_and_import)

def prompt_for_workspace_id(app) -> Optional[str]:
    while True:
        ws_id = _sd.askstring("Debesų sinchronizavimo nustatymas", "Norint sinchronizuoti duomenis, sukurkite unikalų darbo srities ID.\n\nĮveskite *tą patį ID* visuose savo kompiuteriuose.\n\nDarbo srities ID:", parent=app)
        if ws_id is None: return None
        if ws_id and not ws_id.isspace(): return ws_id.strip()
        _mb.showwarning("Netinkamas ID", "Darbo srities ID negali būti tuščias. Bandykite dar kartą.", parent=app)



# ---------- UI Actions & Event Handlers ----------
# toggle_view removed


def _batch_update_tags(app: App, updates: list):
    """
    Updates item tags in batches to prevent UI freeze.
    updates: list of (key, new_tag) tuples
    """
    total = len(updates)
    # Windows needs larger batches less frequently to avoid event loop starvation
    batch_size = 200 if IS_WINDOWS else 50
    delay = 10 if IS_WINDOWS else 5
    
    def _update_chunk(start_idx):
        if getattr(app, '_is_closing', False): return
        end_idx = min(start_idx + batch_size, total)
        
        for i in range(start_idx, end_idx):
            key, new_tag = updates[i]
            if app.tbl.exists(key):
                # Preserve existing tags (like 'sel') but replace status tag
                current_tags = list(app.tbl.item(key, "tags"))
                for t in ColorConfig.get_tag_config().keys():
                    if t in current_tags: current_tags.remove(t)
                current_tags.append(new_tag)
                app.tbl.item(key, tags=tuple(current_tags))
        
        if end_idx < total:
            app.after(delay, lambda: _update_chunk(end_idx))
            
    _update_chunk(0)


def toggle_status(field, app: App):
    global DB_MANAGER
    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {s for s in sel if not s.startswith('group_')}
    if not keys: return
    
    # Save history (for undo feature - simplified for now)
    # TODO: Implement proper undo with SQLite
    
    updates = []
    for key in keys:
        # Get current status from SQLite
        pkg, stk = DB_MANAGER.get_status(key)
        
        # Toggle the field
        if field == 'pkg':
            pkg = 0 if pkg else 1
        else:  # field == 'stk'
            stk = 0 if stk else 1
        
        # Update SQLite immediately (instant)
        DB_MANAGER.update_status(key, pkg, stk)
        
        # Update Firebase in background
        if FIREBASE_SYNC:
            FIREBASE_SYNC.set_status(key, pkg, stk)
        
        # Prepare UI update
        new_tag = ColorConfig.get_status_tag(pkg, stk)
        updates.append((key, new_tag))
    
    # Execute batched UI update
    _batch_update_tags(app, updates)
    
    # Update selection style to match new status
    update_selection_style(app)
    update_counts(app)

def context_toggle_status(field, app: App):
    """Context menu action: Targets SELECTION only, ignores checkboxes."""
    global DB_MANAGER
    sel = app.tbl.selection()
    keys = {s for s in sel if not s.startswith('group_')}
    if not keys: return

    for key in keys:
        # Get current status from SQLite
        pkg, stk = DB_MANAGER.get_status(key)
        
        # Toggle the field
        if field == 'pkg':
            pkg = 0 if pkg else 1
        else:
            stk = 0 if stk else 1
        
        # Update SQLite
        DB_MANAGER.update_status(key, pkg, stk)
        
        # Update Firebase
        if FIREBASE_SYNC:
            FIREBASE_SYNC.set_status(key, pkg, stk)
        
        # Optimistic UI update
        if app.tbl.exists(key):
            new_tag = ColorConfig.get_status_tag(pkg, stk)
            current_tags = list(app.tbl.item(key, "tags"))
            for t in ColorConfig.get_tag_config().keys():
                if t in current_tags: current_tags.remove(t)
            current_tags.append(new_tag)
            app.tbl.item(key, tags=tuple(current_tags))
    
    # Update selection style to match new status
    update_selection_style(app)
    update_counts(app)

def context_clear_status(app: App):
    """Context menu action: Targets SELECTION only."""
    global DB_MANAGER
    sel = app.tbl.selection()
    keys = {s for s in sel if not s.startswith('group_')}
    if not keys: return
    
    for key in keys:
        # Clear status in SQLite
        DB_MANAGER.update_status(key, 0, 0)
        
        # Clear in Firebase
        if FIREBASE_SYNC:
            FIREBASE_SYNC.set_status(key, 0, 0)
        
        # Optimistic UI update
        if app.tbl.exists(key):
            new_tag = 'none'
            current_tags = list(app.tbl.item(key, "tags"))
            for t in ColorConfig.get_tag_config().keys():
                if t in current_tags: current_tags.remove(t)
            current_tags.append(new_tag)
            app.tbl.item(key, tags=tuple(current_tags))
            
    # Update selection style to match new status
    update_selection_style(app)
    update_counts(app)

def clear_status_selected(app: App):
    global DB_MANAGER
    keys = set(CHECKED)
    if not keys:
        sel = app.tbl.selection()
        if sel: keys = {s for s in sel if not s.startswith('group_')}
    if not keys: return
    
    updates = []
    for key in keys:
        # Clear status in SQLite
        DB_MANAGER.update_status(key, 0, 0)
        
        # Clear in Firebase
        if FIREBASE_SYNC:
            FIREBASE_SYNC.set_status(key, 0, 0)
        
        # Prepare UI update
        new_tag = 'none'
        updates.append((key, new_tag))
            
    # Execute batched UI update
    _batch_update_tags(app, updates)
            
    # Update selection style to match new status
    update_selection_style(app)
    update_counts(app)

def on_tree_click(app: App, event):
    """Handles clicks on the treeview (for checkbox toggle)."""
    region = app.tbl.identify_region(event.x, event.y)
    if region != 'cell':
        return
    
    iid = app.tbl.identify_row(event.y)
    if not iid:
        return
    
    # Check if user clicked on Load More button
    if iid == 'load_more_btn':
        load_more_transactions(app)
        return
    
    # Group header check removed


    if app.tbl.identify_region(event.x, event.y) == 'cell' and app.tbl.identify_column(event.x) == '#1':
        if iid in CHECKED: CHECKED.remove(iid)
        else: CHECKED.add(iid)
        vals = app.tbl.item(iid, 'values')
        app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))

def update_selection_style(app: App):
    """Updates the Treeview selection color based on the status of selected rows."""
    global DB_MANAGER
    sel = app.tbl.selection()
    keys = {s for s in sel if not s.startswith('group_')}
    
    if not keys:
        # Default Grey
        app.style.map("Treeview", background=[('selected', '#808080')], foreground=[('selected', 'white')])
        return

    # Determine common status from SQLite
    statuses = []
    for k in keys:
        pkg, stk = DB_MANAGER.get_status(k) if DB_MANAGER else (0, 0)
        statuses.append(ColorConfig.get_status_tag(pkg, stk))
    
    unique_statuses = set(statuses)
    
    bg_color = ColorConfig.SEL_DEFAULT
    fg_color = ColorConfig.SEL_FG_DEFAULT
    # bd_color is unused in new UI style as we use focus ring
    
    if len(unique_statuses) == 1:
        status = unique_statuses.pop()
        if status == 'packaged':
            bg_color = ColorConfig.SEL_PKG
            fg_color = ColorConfig.SEL_FG_DARK
        elif status == 'sticker':
            bg_color = ColorConfig.SEL_STK
            fg_color = ColorConfig.SEL_FG_DARK
        elif status == 'both':
            bg_color = ColorConfig.SEL_BOTH
            fg_color = ColorConfig.SEL_FG_DARK
            
    app.style.map("Treeview", background=[('selected', bg_color)], foreground=[('selected', fg_color)])
    # Enforce Black Focus Ring for all selections
    app.style.map("Treeview", focuscolor=[('selected', ColorConfig.BORDER_FOCUS), ('!selected', 'white')])

def on_select_change(app: App, event):
    update_selection_style(app)
    if hasattr(app, '_refresh_bottom_from_selection'):
        try: app._refresh_bottom_from_selection()
        except Exception: pass

def select_all(app: App):
    # Select all items (using DataFrame if available to ensure we get everything, even if not rendered)
    global _df
    if not _df.empty:
        all_keys = _df.index.tolist()
        CHECKED.update(all_keys)
        # Update visible rows
        for iid in app.tbl.get_children(''):
            try:
                vals = app.tbl.item(iid, 'values')
                app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))
            except: pass
    else:
        # Fallback if _df is empty (shouldn't happen if there's data)
        all_items = app.tbl.get_children('')
        CHECKED.update(all_items)
        for iid in all_items:
            try:
                vals = app.tbl.item(iid, 'values')
                app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))
            except: pass

def clear_selection(app: App):
    all_items = app.tbl.get_children('')

    CHECKED.clear()
    for iid in all_items:
        try:
            vals = app.tbl.item(iid, 'values')
            app.tbl.item(iid, values=(_checkbox_cell_for(iid), *vals[1:]))
        except: pass

def clear_filters(app: App):
    app.var_q.set('')
    app.var_from.set('')
    app.var_to.set('')
    for entry in [app.ent_name, app.ent_from, app.ent_to]:
        if hasattr(entry, '_ph_active'):
            entry._ph_active = True
            entry.delete(0, 'end')
            entry.insert(0, entry._ph_text)
            entry.config(fg='#888888')
    if not hasattr(app, '_render_debouncer'):
        app._render_debouncer = OperationDebouncer(app, delay=FILTER_DEBOUNCE)
    app._render_debouncer.debounce('render', lambda: render(app))

def _guard_shortcut(app, fn):
    def wrapper(event):
        fn(app)
        return 'break'
    return wrapper

def _guarded_main():
    try: _main_inner()
    except Exception as e:
        try: _mb.showerror("TrackNote paleidimo klaida", f"Nepavyko paleisti TrackNote:\n{e}\n\nPatikrinkite žurnalus dėl išsamesnės informacijos.")
        except: pass

def _main_inner():
    global DB_MANAGER, FIREBASE_SYNC
    
    allowed, msg = check_trial()
    if not allowed:
        root = tk.Tk(); root.withdraw()
        act = show_license_dialog(root)
        root.destroy()
        if not act:
            _mb.showwarning("TrackNote", "Bandomoji versija baigėsi. Susisiekite su palaikymu.")
            return
        allowed, msg = check_trial()
        if not allowed:
            _mb.showerror("TrackNote", "Licencijos aktyvavimas nepavyko.")
            return
    
    app = App(); app.withdraw()
    lic_status = license_status_string()
    if lic_status: app.title(f"TrackNote - {lic_status}")
    
    cfg = read_user_config()
    
    namespace = cfg.get('workspace_id')
    if not namespace:
        namespace = prompt_for_workspace_id(app)
        if not namespace:
            app.destroy()
            return
        cfg['workspace_id'] = namespace
        write_user_config(cfg)
    
    # ===== INITIALIZE SQLite DATABASE =====
    print(f"💾 Initializing local database for workspace: {namespace}")
    try:
        DB_MANAGER = DatabaseManager(namespace)
        app.db_manager = DB_MANAGER
        print("✅ Vietinė duomenų bazė paruošta")
    except Exception as e:
        print(f"❌ Duomenų bazės inicijavimas nepavyko: {e}")
        _mb.showerror("Duomenų bazės klaida", f"Nepavyko inicijuoti vietinės duomenų bazės:\n{e}")
        app.destroy()
        return
    
    # ===== INITIALIZE FIREBASE (optional) =====
    firebase_config = load_firebase_config()
    if firebase_config:
        try:
            FIREBASE_SYNC = FirebaseSync(database_url=firebase_config['database_url'], project_id=firebase_config['project_id'], namespace=namespace)
            app.firebase_sync = FIREBASE_SYNC
        except Exception as e:
            print(f"⚠️ Firebase initialization failed: {e}")
            FIREBASE_SYNC = None
    
    # app.btn_toggle_view.config(command=lambda: toggle_view(app)) # Removed
    app.btn_refresh.config(command=lambda: load_and_render_async(app))
    app.btn_import.config(command=lambda: import_statement(app))
    app.btn_clear_filters.config(command=lambda: clear_filters(app))
    app.btn_select_all.config(command=lambda: select_all(app))
    app.btn_clear_sel.config(command=lambda: clear_selection(app))
    app.btn_toggle_pkg.config(command=lambda: toggle_status('pkg', app))
    app.btn_toggle_stk.config(command=lambda: toggle_status('stk', app))
    app.btn_clear_status.config(command=lambda: clear_status_selected(app))
    
    app.realtime_render_debouncer = OperationDebouncer(app, delay=300)

    debouncer = OperationDebouncer(app, delay=FILTER_DEBOUNCE)
    def _schedule_render(*_): debouncer.debounce('render', lambda: render(app))
    app.var_q.trace_add('write', _schedule_render)
    app.var_from.trace_add('write', _schedule_render)
    app.var_to.trace_add('write', _schedule_render)

    app.tbl.bind('<Button-1>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<<TreeviewSelect>>', lambda e: on_select_change(app, e))
    app.tbl.bind('<space>', lambda e: on_tree_click(app, e))
    app.tbl.bind('<Key-p>', lambda e: toggle_status('pkg', app))
    app.tbl.bind('<Key-s>', lambda e: toggle_status('stk', app))
    app.bind('<Escape>', lambda e: (_guard_shortcut(app, lambda _: clear_filters(app))(e)))
    app.bind('<Command-BackSpace>', lambda e: (_guard_shortcut(app, lambda _: clear_status_selected(app))(e)))
    
    # --- Context Menu Bindings ---
    def show_context_menu(event):
        iid = app.tbl.identify_row(event.y)
        if iid:
            # Select the row under cursor if not already selected
            if iid not in app.tbl.selection():
                app.tbl.selection_set(iid)
                # Also update CHECKED set to match selection for consistent behavior
                # (Optional: depends if we want right-click to act on selection or just the row)
                # For now, let's just ensure the row is selected so the action applies to it
            
            # Ensure CHECKED is updated to match selection if it's empty
            # This allows right-click -> Action to work on the row under cursor
            if not CHECKED:
                CHECKED.add(iid)
            
            try: app.context_menu.tk_popup(event.x_root, event.y_root)
            finally: app.context_menu.grab_release()

    if IS_WINDOWS:
        app.tbl.bind("<Button-3>", show_context_menu)
    else:
        app.tbl.bind("<Button-2>", show_context_menu)
        app.tbl.bind("<Button-3>", show_context_menu) # Support both on Mac just in case

    app.bind("<<CtxTogglePkg>>", lambda e: context_toggle_status('pkg', app))
    app.bind("<<CtxToggleStk>>", lambda e: context_toggle_status('stk', app))
    app.bind("<<CtxClearStatus>>", lambda e: context_clear_status(app))
    
    # Undo binding
    app.bind("<Control-z>", lambda e: undo_last_action(app))
    app.bind("<Command-z>", lambda e: undo_last_action(app))

    load_and_render_async(app)
    configure_tags(app)

    def on_firebase_change(change_type: str, key: Optional[str], data):
        global STATUS, _df
        if not key: return

        needs_render = False
        if change_type == 'status':
            # Incremental update: Update data AND UI directly without full re-render
            if data: STATUS[key] = data
            else: STATUS.pop(key, None)
            
            # Direct UI update
            if app.tbl.exists(key):
                new_tag = status_to_tag(STATUS.get(key, {}))
                # Preserve existing tags (like 'sel') if any, but usually we just set the status tag
                # We need to keep 'group_header' if it was there, but keys are usually transactions
                current_tags = list(app.tbl.item(key, "tags"))
                # Remove old status tags
                for t in ColorConfig.get_tag_config().keys():
                    if t in current_tags: current_tags.remove(t)
                current_tags.append(new_tag)
                app.tbl.item(key, tags=tuple(current_tags))
            
            # Update counts on external change
            update_counts(app)
            
            # Do NOT trigger full render for status changes
            needs_render = False
        
        elif change_type == 'transaction':
            if data:
                s = pd.Series(data, name=key)
                if all(col in _df.columns for col in s.index):
                    _df.loc[key] = s
                else:
                    new_row = pd.DataFrame([data], index=[key])
                    _df = pd.concat([_df, new_row])
            elif key in _df.index:
                _df.drop(key, inplace=True)
            needs_render = True
        
        if needs_render:
            app.realtime_render_debouncer.debounce('render', lambda: render(app))

    if FIREBASE_SYNC and FIREBASE_SYNC.is_connected():
        try:
            FIREBASE_SYNC.start_listener(on_firebase_change)
            print("✓ Real-time sync active for all data")
        except Exception as e: print(f"⚠ Failed to start Firebase listener: {e}")

    def on_closing():
        try:
            app._is_closing = True
            for after_id in app.tk.call('after', 'info'): app.after_cancel(after_id)
            if FIREBASE_SYNC and FIREBASE_SYNC.is_connected(): FIREBASE_SYNC.stop_listener()
            app.quit(); app.destroy()
        except Exception:
            import sys; sys.exit(0)
    app.protocol("WM_DELETE_WINDOW", on_closing)

    app.deiconify()
    app.mainloop()

def main():
    """Entry point for the launcher."""
    _guarded_main()

if __name__ == '__main__':
    _guarded_main()