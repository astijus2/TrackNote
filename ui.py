# --- START OF FILE ui.py ---

import tkinter as tk
from tkinter import ttk
import os, json
from pathlib import Path
import tkinter.font as tkfont
from user_data import load_notes, save_notes, user_data_dir
import subprocess, platform
import time
# Platform detection for Windows-specific fixes
IS_WINDOWS = platform.system() == "Windows"

from color_config import ColorConfig

# Show "Open Data/Logs" only in dev or when explicitly enabled
def _support_tools_enabled() -> bool:
    import os, sys
    return (not getattr(sys, "frozen", False)) or bool(os.environ.get("TRACKNOTE_DEV"))


#----------------------------------------------------------------------------------------------------------------------------------------------

def add_placeholder(entry: tk.Entry, text: str):
    entry._ph_text = text
    entry._ph_active = True
    entry.insert(0, text)
    entry.config(fg="#888888")
    def on_focus_in(_):
        if entry._ph_active:
            entry.delete(0, "end"); entry.config(fg="black"); entry._ph_active = False
    def on_focus_out(_):
        if not entry.get():
            entry.insert(0, entry._ph_text); entry.config(fg="#888888"); entry._ph_active = True
    entry.bind("<FocusIn>", on_focus_in); entry.bind("<FocusOut>", on_focus_out)

def _wheel_steps(event) -> int:
    try:
        d = int(getattr(event, "delta", 0))
    except Exception:
        d = 0
    if d == 0:
        return 0
    unit = 120
    return int(d / unit) if abs(d) >= unit else (1 if d > 0 else -1)

def attach_mousewheel(widget):
    # macOS manages scrolling natively and smoothly. 
    # Manual binding interferes and causes "jumping".
    if platform.system() == "Darwin":
        return

    def _on_wheel(e):
        steps = _wheel_steps(e)
        if steps:
            try:
                widget.yview_scroll(-steps, "units")  # minus = natural direction
            except Exception:
                pass
            return "break"  # don't let parent also scroll
    widget.bind("<MouseWheel>", _on_wheel, add="+")



#-----------------------------------------------------------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Užsakymų paieška')
        
        # ---- Help menu: Open Data/Logs ----
        def _open_path(path: str):
            try:
                if platform.system() == "Darwin":
                    subprocess.run(["open", path], check=False)
                elif platform.system() == "Windows":
                    os.startfile(path)  # type: ignore[attr-defined]
                else:
                    subprocess.run(["xdg-open", path], check=False)
            except Exception:
                pass

        menubar = tk.Menu(self)
        self.config(menu=menubar)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Pagalba", menu=help_menu)
        self.help_menu = help_menu  # expose to app.py

        if _support_tools_enabled():
            help_menu.add_command(
                label="Atidaryti duomenų aplanką",
                command=lambda: _open_path(str(user_data_dir()))
            )
            help_menu.add_command(
                label="Atidaryti žurnalų aplanką",
                command=lambda: _open_path(str((user_data_dir() / "logs")))
            )
        # ---- end Help menu ----

        self.configure(bg='white')
        # Force fullscreen on startup
        self.update_idletasks()
        if platform.system() == "Darwin":  # macOS
            try: self.wm_state('zoomed')
            except:
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                self.geometry(f"{screen_width}x{screen_height-50}+0+25")
        else:
            self.state('zoomed')

        self.lift()
        self.focus_force()
        
        self._note_store_path = str(user_data_dir() / "notes_store.json")
        self._note_store = load_notes() or {}
        self._save_after_id = None
        self._interact_after_id = None
        self._firebase_save_after_id = None
        self._last_firebase_save = 0  
        self.firebase_sync = None
        self.after(1000, self._load_firebase_notes)


        # ===== Theme / selection colors =====
        self.style = ttk.Style(self)
        try: self.style.theme_use('clam')
        except Exception: pass
        self.style.configure("Treeview", background="white", fieldbackground="white", foreground="black", rowheight=26)
        self.style.configure("Treeview.Heading", background="#f0f0f0", foreground="black")
        self._sel_default_bg = ColorConfig.SEL_DEFAULT
        self._sel_default_fg = ColorConfig.SEL_FG_DEFAULT
        self.style.map("Treeview", background=[('selected', ColorConfig.SEL_DEFAULT)], foreground=[('selected', ColorConfig.SEL_FG_DEFAULT)])
        
        # --- NEW: Border for selection (using focus ring) ---
        # self.style.configure("Treeview.Item", borderwidth=2, relief="solid") # Doesn't work well on Mac
        # self.style.map("Treeview.Item", bordercolor=[('selected', '#333333'), ('!selected', 'white')])
        
        # Use focus ring as border
        # self.style.map("Treeview", focuscolor=[('selected', '#333333'), ('!selected', 'white')])
        
        # --- NEW: Aggressive Border (Black Box) ---
        self.style.configure("Treeview.Item", borderwidth=1, relief="solid")
        self.style.map("Treeview.Item", 
            lightcolor=[('selected', 'black'), ('!selected', 'white')],
            darkcolor=[('selected', 'black'), ('!selected', 'white')],
            bordercolor=[('selected', 'black'), ('!selected', 'white')]
        )
        # --- NEW: Style for customer group headers ---
        self.style.configure("Group.Treeitem", background="#f0f0f0", font=('Segoe UI', 10, 'bold'))
        self.style.map("Group.Treeitem", background=[('selected', "#f0f0f0")], foreground=[('selected', 'black')])


        # Remove Treeview focus rectangle
        # --- NEW: Explicitly set layout to include focus ring for border ---
        self.style.layout("Treeview.Item", 
            [('Treeitem.padding', {'sticky': 'nswe', 'children': 
                [('Treeitem.indicator', {'side': 'left', 'sticky': ''}), 
                 ('Treeitem.image', {'side': 'left', 'sticky': ''}), 
                 ('Treeitem.focus', {'side': 'left', 'sticky': 'nswe', 'children': 
                    [('Treeitem.text', {'sticky': 'nswe'})]
                 })]
            })]
        )
        
        # Configure focus color to be Black for selection
        self.style.map("Treeview", focuscolor=[('selected', 'black'), ('!selected', 'white')])

        # ===== Top bar =====
        top = tk.Frame(self, bg='white'); top.pack(fill='x', padx=10, pady=10)

        tk.Label(top, text='Vardo filtras:', bg='white', fg='black').pack(side='left', padx=(0,6))
        self.var_q = tk.StringVar()
        self.ent_name = tk.Entry(top, textvariable=self.var_q, width=28, bg='white', fg='black', insertbackground='black')
        self.ent_name.pack(side='left')
        add_placeholder(self.ent_name, "Įveskite vardą ir pavardę…")

        tk.Label(top, text='Nuo:', bg='white', fg='black').pack(side='left', padx=(16,6))
        self.var_from = tk.StringVar()
        self.ent_from = tk.Entry(top, textvariable=self.var_from, width=12, bg='white', fg='black', insertbackground='black')
        self.ent_from.pack(side='left')
        add_placeholder(self.ent_from, "YYYY-MM-DD")

        tk.Label(top, text='Iki:', bg='white', fg='black').pack(side='left', padx=(12,6))
        self.var_to = tk.StringVar()
        self.ent_to = tk.Entry(top, textvariable=self.var_to, width=12, bg='white', fg='black', insertbackground='black')
        self.ent_to.pack(side='left')
        add_placeholder(self.ent_to, "YYYY-MM-DD")

        self.btn_refresh = tk.Button(top, text='Atnaujinti', bg='#e6e6e6', fg='black', relief='raised')
        self.btn_refresh.pack(side='left', padx=12)

        self.btn_import = tk.Button(top, text='Importuoti išrašą', bg='#d0e0f0', relief='raised')
        self.btn_import.pack(side='left', padx=(0, 12))

        self.btn_clear_filters = tk.Button(top, text='Išvalyti filtrus', bg='#f3f3f3', relief='raised')
        self.btn_clear_filters.pack(side='left', padx=8)

        # --- MODIFIED: View toggle button on the right ---
        right_top = tk.Frame(top, bg='white')
        right_top.pack(side='right')

        self.lbl_view_info = tk.Label(right_top, text="", font=('Segoe UI', 10), bg='white', fg='#333')
        self.lbl_view_info.pack(side='left', padx=(0, 10))

        # self.btn_toggle_view = tk.Button(right_top, text='Show Completed History', bg='#6c757d', fg='white', relief='raised', font=('Segoe UI', 9, 'bold'))
        # self.btn_toggle_view.pack(side='left', padx=8)
        
        self.btn_help = tk.Button(right_top, text='Pagalba', bg='#f3f3f3', relief='raised', bd=1, highlightthickness=0)
        self.btn_help.pack(side='left', padx=(8,0))
        self._help_dropdown = tk.Menu(self, tearoff=0)
        self.btn_help.configure(command=lambda: self._show_help_dropdown_at(self.btn_help))
        # --- END OF MODIFICATION ---

        # ===== Action bar =====
        actions = tk.Frame(self, bg='white'); actions.pack(fill='x', padx=10, pady=(0,8))

        left = tk.Frame(actions, bg='white'); left.pack(side='left')
        self.btn_select_all = tk.Button(left, text='Pažymėti viską (matomus)', bg='#f3f3f3', relief='raised')
        self.btn_select_all.pack(side='left', padx=(0,8))
        self.btn_clear_sel = tk.Button(left, text='Išvalyti pažymėjimą', bg='#f3f3f3', relief='raised')
        self.btn_clear_sel.pack(side='left', padx=(0,16))
        self.btn_toggle_pkg = tk.Button(left, text='Žymėti geltona (Supakuota)', bg=ColorConfig.PKG_BG, relief='raised')
        self.btn_toggle_pkg.pack(side='left')
        self.btn_toggle_stk = tk.Button(left, text='Žymėti mėlyna (Lipdukas)', bg=ColorConfig.STK_BG, relief='raised')
        self.btn_toggle_stk.pack(side='left', padx=8)
        self.btn_clear_status = tk.Button(left, text='Išvalyti statusą (pažymėtus)', bg='#f3f3f3', relief='raised')
        self.btn_clear_status.pack(side='left', padx=8)

        # Removed static legend from here to move to bottom
        self.lbl_counts = tk.Label(actions, text='', bg='white', fg='black', font=('Segoe UI', 10, 'bold'))
        self.lbl_counts.pack(side='right', padx=(0, 10))

        # ===== Table (Treeview) =====
        mid = tk.Frame(self, bg='white'); mid.pack(fill='both', expand=True, padx=10, pady=(0,6))
        mid.grid_rowconfigure(0, weight=1); mid.grid_columnconfigure(0, weight=1)
        self._overlay_parent = mid

        cols = ('sel','date','price','iban','comment','name','note')
        self.tbl = ttk.Treeview(mid, columns=cols, show='headings')

        attach_mousewheel(self.tbl)
        headers = {'sel':'', 'date':'Data', 'price':'Kaina', 'iban':'IBAN', 'comment':'Komentaras', 'name':'Vardas', 'note':'Pastaba'}
        for c in cols:
            self.tbl.heading(c, text=headers[c])
        self.tbl.column('sel', width=34, anchor='center')
        self.tbl.column('date', width=160, anchor='w')
        self.tbl.column('price', width=120, anchor='w')
        self.tbl.column('iban', width=220, anchor='w')
        self.tbl.column('comment', width=420, anchor='w')
        self.tbl.column('name', width=220, anchor='w')
        self.tbl.column('note', width=200, anchor='w')
        self.tbl.grid(row=0, column=0, sticky='nsew')

        def _yview_wrapper(*args):
            self.tbl.yview(*args)
            self.tbl.update_idletasks()
            self._place_note_editors_now()
        
        def _xview_wrapper(*args):
            self.tbl.xview(*args)
            self.tbl.update_idletasks()
            self._place_note_editors_now()
        
        self._ysb = tk.Scrollbar(mid, orient='vertical', command=_yview_wrapper)
        self._ysb.grid(row=0, column=1, sticky='ns')
        self._xsb = tk.Scrollbar(mid, orient='horizontal', command=_xview_wrapper)
        self._xsb.grid(row=1, column=0, sticky='ew')

        def _yset_wrapper(*args):
            self._ysb.set(*args)
            self._place_note_editors_now()
        
        def _xset_wrapper(*args):
            self._xsb.set(*args)
            self._place_note_editors_now()
        
        self.tbl.configure(yscrollcommand=_yset_wrapper, xscrollcommand=_xset_wrapper)

        self._note_widgets = {}
        self._note_save_after_id = None
        self._note_col_id = None
        
        self.tbl.bind("<<TreeviewSelect>>", lambda e: self._on_row_interact(), add="+")

        def _on_mousewheel(e):
            self.after(1, self._place_note_editors_now)
        self.tbl.bind("<MouseWheel>", _on_mousewheel, add="+")
        
        def _on_key_nav(e):
            if e.keysym in ("Up","Down","Prior","Next","Home","End"):
                self._on_row_interact()
                self.after(1, self._place_note_editors_now)
        self.tbl.bind("<KeyRelease>", _on_key_nav, add="+")
        self.after(200, self._place_note_editors_now)

        # ===== Bottom area (split into two boxes) =====
        bottom = tk.Frame(self, bg='white'); bottom.pack(fill='x', padx=10, pady=(0,10))
        self.lbl_status = tk.Label(self, text='', bg='white', fg='#007ACC', font=('Segoe UI', 11, 'bold'))
        self.lbl_status.pack(side='bottom', pady=(0, 5))

        BOTTOM_HEIGHT = 100
        bottom.configure(height= BOTTOM_HEIGHT)
        bottom.pack_propagate(False)

        # Main container for bottom content
        bottom_content = tk.Frame(bottom, bg='white')
        bottom_content.pack(fill='both', expand=True)

        # Right: Legend (Pack FIRST to allow it to reserve space)
        right_legend = tk.Frame(bottom_content, bg='white', width=150)
        right_legend.pack(side='right', fill='y', padx=(6,0))

        # Left side: Comment box
        left = tk.Frame(bottom_content, bg='white')
        left.pack(side='left', fill='both', expand=True, padx=(0,6))
        
        # Middle: Note box
        middle = tk.Frame(bottom_content, bg='white')
        middle.pack(side='left', fill='both', expand=True, padx=(6,6))

        tk.Label(left,  text='Išrašo komentaras:', bg='white', fg='black').pack(anchor='w')
        tk.Label(middle, text='Asmeninė pastaba:',       bg='white', fg='black').pack(anchor='w')

        # Legend items
        tk.Label(right_legend, text='Legenda:', bg='white', fg='black', font=('Segoe UI', 9, 'bold')).pack(anchor='nw', pady=(0, 4))
        
        def legend_item(parent, color, text):
            row = tk.Frame(parent, bg='white')
            row.pack(fill='x', pady=1)
            tk.Label(row, width=2, height=1, bg=color, bd=1, relief='solid', font=('Segoe UI', 6)).pack(side='left', padx=(0,4))
            tk.Label(row, text=text, bg='white', fg='black', font=('Segoe UI', 9)).pack(side='left')

        legend_item(right_legend, ColorConfig.NONE_BG, 'Nieko')
        legend_item(right_legend, ColorConfig.PKG_BG, 'Supakuota')
        legend_item(right_legend, ColorConfig.STK_BG, 'Lipdukas')
        legend_item(right_legend, ColorConfig.BOTH_BG, 'Abu')

        self._bottom_font = tkfont.Font(family='Segoe UI', size=14)
        self.txt_stmt = tk.Text(left,  height=3, wrap='word', bg='white', fg='black', font=self._bottom_font)
        attach_mousewheel(self.txt_stmt)
        self.txt_note = tk.Text(middle, height=3, wrap='word', bg='white', fg='black', font=self._bottom_font)
        attach_mousewheel(self.txt_note)

        self.txt_stmt.pack(fill='both', expand=True)
        self.txt_note.pack(fill='both', expand=True)

        for _seq in ('<Command-s>', '<Command-e>', '<Control-s>', '<Control-e>', '<Command-BackSpace>', '<Escape>'):
            self.txt_note.bind(_seq, lambda ev: 'break')
        self._apply_bottom_text_insets(left_px=12, right_px=8, vpad_px=4)
        self.txt_note.bind('<KeyRelease>', self._on_bottom_note_changed, add='+')

        self.txt_stmt.configure(state='disabled')
        self.txt_note.configure(state='disabled')
        self.txt_comment = self.txt_stmt

        # --- Context Menu for Right-Click ---
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Žymėti geltona (Supakuota)", command=lambda: self.event_generate("<<CtxTogglePkg>>"))
        self.context_menu.add_command(label="Žymėti mėlyna (Lipdukas)", command=lambda: self.event_generate("<<CtxToggleStk>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Išvalyti spalvas", command=lambda: self.event_generate("<<CtxClearStatus>>"))

    def _on_row_interact(self):
        if hasattr(self, '_interact_after_id') and self._interact_after_id:
            try: self.after_cancel(self._interact_after_id)
            except: pass
        self._interact_after_id = self.after(200, self._do_row_interact)

    def _do_row_interact(self):
        try:
            self._refresh_bottom_from_selection()
            self._place_note_editors_now()
        except: pass

    def _on_bottom_note_changed(self, _event=None):
        try:
            sel = self.tbl.selection()
            if not sel: return
            iid = sel[0]
            text = self.txt_note.get('1.0', 'end-1c')

            if hasattr(self, '_note_widgets'):
                editor = self._note_widgets.get(iid)
                if editor:
                    try:
                        editor.delete('1.0', 'end')
                        editor.insert('1.0', text)
                        self._set_note_entry_bg(editor)
                    except: pass

            key = self._make_row_key(iid) or str(iid)
            if not hasattr(self, '_note_store'): self._note_store = {}
            self._note_store[key] = text

            if getattr(self, "_save_after_id", None):
                try: self.after_cancel(self._save_after_id)
                except: pass
            self._save_after_id = self.after(500, self._save_note_store)

        except Exception: pass

    def _apply_bottom_text_insets(self, left_px=12, right_px=8, vpad_px=4):
        for w in (self.txt_stmt, self.txt_note):
            try: w.configure(padx=left_px, pady=vpad_px)
            except Exception: pass
            try:
                w.tag_configure("_insets", lmargin1=left_px, lmargin2=left_px, rmargin=right_px)
                w.tag_add("_insets", "1.0", "end")
            except Exception: pass

    def _refresh_bottom_from_selection(self):
        try:
            sel = self.tbl.selection()
            if not sel:
                self.set_comment('')
                self.set_note_view('')
                return

            iid = sel[0]
            # --- NEW: Ignore group headers ---
            # Group header check removed


            vals = self.tbl.item(iid, 'values')
            comment = vals[4] if len(vals) > 4 else ''
            self.set_comment(comment)
            
            note = ''
            try:
                if hasattr(self, '_note_widgets'):
                    w = self._note_widgets.get(iid)
                    if w: note = w.get('1.0', 'end-1c')
                    else:
                        key = self._make_row_key(iid)
                        note = self._note_store.get(key, '') or ''
            except: pass
            self.set_note_view(note)
        except: pass

    def set_note_view(self, text: str):
        try:
            self.txt_note.configure(state="normal")
            self.txt_note.delete("1.0", "end")
            self.txt_note.insert("1.0", text or "")
            self.txt_note.configure(state="disabled")
            self._apply_bottom_text_insets()
        except Exception: pass

    def _show_help_dropdown_at(self, widget):
        try:
            self._rebuild_help_dropdown()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
            self._help_dropdown.tk_popup(x, y)
        finally:
            try: self._help_dropdown.grab_release()
            except Exception: pass
    
    def _rebuild_help_dropdown(self):
        try:
            m = self._help_dropdown
            m.delete(0, 'end')
            end = self.help_menu.index('end')
            if end is None:
                m.add_command(label="(No items)", state='disabled')
                return
            for i in range(end + 1):
                etype = self.help_menu.type(i)
                if etype == 'separator': m.add_separator()
                elif etype == 'command':
                    label = self.help_menu.entrycget(i, 'label')
                    state = self.help_menu.entrycget(i, 'state') or 'normal'
                    m.add_command(label=label, state=state, command=lambda idx=i: self.help_menu.invoke(idx))
                else:
                    label = self.help_menu.entrycget(i, 'label')
                    m.add_command(label=label, state='disabled')
        except Exception: pass

    def _load_note_store(self):
        try:
            data = load_notes()
            return data if isinstance(data, dict) else {}
        except Exception: return {}
        
    def _load_firebase_notes(self):
        try:
            if self.firebase_sync and self.firebase_sync.is_connected():
                firebase_notes = self.firebase_sync.get_all_notes()
                if firebase_notes: self._note_store.update(firebase_notes)
        except Exception: pass

    def _make_row_key(self, iid): return iid

    def _set_note_entry_bg(self, widget):
        try:
            txt = widget.get('1.0', 'end-1c') if isinstance(widget, tk.Text) else widget.get()
        except: txt = ''
        has_text = bool((txt or '').strip())
        bg = '#FFD6D6' if has_text else '#FFFFFF'
        try: widget.configure(bg=bg, insertbackground='black')
        except: pass

    def _place_note_editors_now(self):
        try:
            tree = self.tbl
            if not tree.winfo_ismapped(): return
            
            # --- 1. Identify Note Column X/width ---
            if not self._note_col_id:
                try:
                    note_idx = list(tree['columns']).index('note')
                    self._note_col_id = f"#{note_idx + 1}"
                except ValueError: return
            
            if not hasattr(self, "_note_widgets"): self._note_widgets = {}
            parent = self._overlay_parent
            
            # --- 2. ROBUST VISIBILITY DETECTION (Contiguous Iterator) ---
            # Instead of probing pixels (which can miss rows), we find the top item
            # and walk down the tree using tree.next() until we go off-screen.
            visible_iids = set()
            
            # Find the first visible item at the top
            # Check a range of points at the top to be robust against headers/partial scroll
            start_iid = None
            for y_probe in range(1, 100, 5):
                start_iid = tree.identify_row(y_probe)
                if start_iid: break
            
            if start_iid:
                curr = start_iid
                tree_height = tree.winfo_height()
                
                # Safety break to prevent infinite loops if tree state is corrupted
                max_loops = 200 
                loop_count = 0
                
                while curr and loop_count < max_loops:
                    # Check if this item is actually visible
                    bbox = tree.bbox(curr, self._note_col_id)
                    if not bbox:
                        pass
                    else:
                        _x, y, _w, h = bbox
                        if y > tree_height: break # maximizing efficiency: stop once we leave screen
                        visible_iids.add(curr)
                    
                    curr = tree.next(curr)
                    loop_count += 1
            
            # --- SAFETY CHECK: If we found NO visible rows, something went wrong with detection.
            # DO NOT clear widgets, just abort this update to prevent "flashing" empty.
            if not visible_iids:
                return

            # --- 3. Hide non-visible widgets (Cleanup) ---
            for iid in list(self._note_widgets.keys()):
                if iid not in visible_iids:
                    try: self._note_widgets[iid].place_forget()
                    except: pass
            
            # --- 4. Place visible widgets ---
            try:
                rx = tree.winfo_rootx() - parent.winfo_rootx()
                ry = tree.winfo_rooty() - parent.winfo_rooty()
            except: rx = ry = 0
            
            for iid in visible_iids:
                try:
                    bbox = tree.bbox(iid, self._note_col_id)
                    if not bbox: continue
                    
                    x, y, w, h = bbox
                    
                    # Vertical Clipping: Ensure widget doesn't extend past the bottom
                    tree_height = tree.winfo_height()
                    if y + h > tree_height:
                        h = tree_height - y
                    
                    if h < 10: 
                        if iid in self._note_widgets: self._note_widgets[iid].place_forget()
                        continue 
                    
                    editor = self._note_widgets.get(iid)
                    if editor is None:
                        editor = self._make_note_entry(iid)
                        self._note_widgets[iid] = editor
                    
                    pad_x, pad_y, y_offset = (4, 1, 1) if IS_WINDOWS else (4, 3, 0)
                    
                    final_h = h - 2*pad_y
                    if final_h < 5:
                        editor.place_forget()
                        continue

                    editor.place_configure(x=rx + x + pad_x, y=ry + y + pad_y - y_offset, width=w - 2*pad_x - 2, height=final_h)
                    editor.lift()
                except: pass
        except: pass

    def _make_note_entry(self, iid):
        font_config = ('Segoe UI', 10)
        if IS_WINDOWS:
            e = tk.Text(self._overlay_parent, height=1, wrap='none', bd=1, relief='solid', highlightthickness=0, bg="white", fg="black", insertbackground="black", insertwidth=1, font=font_config, padx=2, pady=1)
        else:
            e = tk.Text(self._overlay_parent, height=1, wrap='none', bd=1, relief='solid', highlightthickness=1, highlightbackground="#D0D0D0", highlightcolor="#4A90E2", bg="white", fg="black", insertbackground="black", insertwidth=1, font=font_config)
        
        e.configure(exportselection=False, selectborderwidth=0, selectbackground='white', inactiveselectbackground='white')
        if IS_WINDOWS:
            try: e.configure(undo=False, autoseparators=False)
            except: pass
        
        try:
            tags = list(e.bindtags()); tags.remove('Text'); tags.insert(0, 'Text'); e.bindtags(tuple(tags))
        except: pass
        
        e.bind('<Key>', lambda ev: 'break', add='+')
        e.bind('<FocusOut>', lambda ev: e.tag_remove('sel', '1.0', 'end'), add='+')
        e.bind("<FocusIn>",  lambda ev, _iid=iid: (self.tbl.selection_set(_iid), self.tbl.focus(_iid)), add="+")
        e.bind("<Button-1>", lambda ev, _iid=iid: (self.tbl.selection_set(_iid), self.tbl.focus(_iid)), add="+")
        
        def _block_nav(ev):
            if ev.keysym.lower() in ("up","down","prior","next","home","end"): return "break"
        e.bind("<KeyPress>", _block_nav, add="+")
        
        init = (self._note_store.get(iid, "") if hasattr(self, "_note_store") else "") or ""
        if init: e.insert('1.0', init)
        self._set_note_entry_bg(e)
        
        def on_change(_ev=None, widget=e):
            try:
                txt = widget.get('1.0', 'end-1c')
                self._set_note_entry_bg(widget)
                
                if not hasattr(self, "_note_store"): self._note_store = {}
                self._note_store[iid] = txt
                
                current_time = time.time()
                if current_time - getattr(self, '_last_firebase_save', 0) > 3:
                    self.after(100, lambda: self._save_note_to_firebase(iid, txt))
                    self._last_firebase_save = current_time
                else:
                    if getattr(self, "_firebase_save_after_id", None):
                        try: self.after_cancel(self._firebase_save_after_id)
                        except: pass
                    self._firebase_save_after_id = self.after(2000, lambda: self._save_note_to_firebase(iid, txt))

                if getattr(self, "_save_after_id", None):
                    try: self.after_cancel(self._save_after_id)
                    except: pass
                self._save_after_id = self.after(500, self._save_note_store)
                
                sel = self.tbl.selection()
                if sel and sel[0] == iid: self.set_note_view(txt)
            except Exception: pass

        e.bind("<KeyRelease>", on_change, add="+")
        return e

    def set_comment(self, text: str):
        try:
            self.txt_stmt.configure(state='normal')
            self.txt_stmt.delete('1.0', 'end')
            self.txt_stmt.insert('1.0', text or '')
            self.txt_stmt.configure(state='disabled')
            self._apply_bottom_text_insets()
        except Exception: pass

    def _save_note_store(self):
        try: save_notes(self._note_store)
        except Exception: pass
        finally: self._save_after_id = None

    def _save_note_to_firebase(self, key, txt):
        try:
            if hasattr(self, 'firebase_sync') and self.firebase_sync:
                self.firebase_sync.set_note(key, txt)
        except Exception: pass
# --- END OF FILE ui.py ---