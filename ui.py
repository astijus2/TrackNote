import tkinter as tk
from tkinter import ttk
import os, json
from pathlib import Path
import tkinter.font as tkfont
from user_data import load_notes, save_notes, user_data_dir
import subprocess, platform
import time

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
        self.title('Order Lookup')
        
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
        menubar.add_cascade(label="Help", menu=help_menu)
        self.help_menu = help_menu  # expose to app.py

        if _support_tools_enabled():
            help_menu.add_command(
                label="Open Data Folder",
                command=lambda: _open_path(str(user_data_dir()))
            )
            help_menu.add_command(
                label="Open Logs Folder",
                command=lambda: _open_path(str((user_data_dir() / "logs")))
            )
        # ---- end Help menu ----

        self.configure(bg='white')
        # Force fullscreen on startup
        self.update_idletasks()  # Force window to initialize
        if platform.system() == "Darwin":  # macOS
            try:
                # Try native macOS maximize
                self.wm_state('zoomed')
            except:
                # Fallback: manual fullscreen
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                self.geometry(f"{screen_width}x{screen_height-50}+0+25")
        else:
            self.state('zoomed')

        # Ensure window is on top initially
        self.lift()
        self.focus_force()
        
        self._note_store_path = str(user_data_dir() / "notes_store.json")
        # load directly (no method call needed here)
        self._note_store = load_notes() or {}
        self._save_after_id = None
        self._interact_after_id = None
        self._firebase_save_after_id = None
        self._last_firebase_save = 0  
        self.firebase_sync = None  # Will be set by app.py
        # Load Firebase notes after a short delay (after firebase_sync is set)
        self.after(1000, self._load_firebase_notes)


        # ===== Theme / selection colors =====
        self.style = ttk.Style(self)
        try: self.style.theme_use('clam')
        except Exception: pass
        self.style.configure("Treeview", background="white", fieldbackground="white", foreground="black", rowheight=26)
        self.style.configure("Treeview.Heading", background="#f0f0f0", foreground="black")
        self._sel_default_bg = "#79B8FF"   # <- selectoriaus spalva
        self._sel_default_fg = '#111111'   # <- dark text for contrast
        self.style.map(
            "Treeview",
            background=[('selected', self._sel_default_bg), ('selected','!focus', self._sel_default_bg)],
            foreground=[('selected', self._sel_default_fg), ('selected','!focus', self._sel_default_fg)],
        )

        # Remove Treeview focus rectangle (the 4-line outline)
        try:
            layout = self.style.layout("Treeview.Item")
            def _strip_focus(children):
                out = []
                for element, conf in children:
                    if element == "Treeitem.focus":
                        continue
                    if "children" in conf:
                        conf = dict(conf)
                        conf["children"] = _strip_focus(conf["children"])
                    out.append((element, conf))
                return out
            self.style.layout("Treeview.Item", _strip_focus(layout))
        except Exception:
            pass

        # ===== Top bar =====
        top = tk.Frame(self, bg='white'); top.pack(fill='x', padx=10, pady=10)

        tk.Label(top, text='Name filter:', bg='white', fg='black').pack(side='left', padx=(0,6))
        self.var_q = tk.StringVar()
        self.ent_name = tk.Entry(top, textvariable=self.var_q, width=28,
                                 bg='white', fg='black', insertbackground='black')
        self.ent_name.pack(side='left')
        add_placeholder(self.ent_name, "Type name & surname…")

        tk.Label(top, text='From:', bg='white', fg='black').pack(side='left', padx=(16,6))
        self.var_from = tk.StringVar()
        self.ent_from = tk.Entry(top, textvariable=self.var_from, width=12,
                                 bg='white', fg='black', insertbackground='black')
        self.ent_from.pack(side='left')
        add_placeholder(self.ent_from, "YYYY-MM-DD")

        tk.Label(top, text='To:', bg='white', fg='black').pack(side='left', padx=(12,6))
        self.var_to = tk.StringVar()
        self.ent_to = tk.Entry(top, textvariable=self.var_to, width=12,
                               bg='white', fg='black', insertbackground='black')
        self.ent_to.pack(side='left')
        add_placeholder(self.ent_to, "YYYY-MM-DD")

        self.btn_refresh = tk.Button(top, text='Refresh', bg='#e6e6e6', fg='black', relief='raised')
        self.btn_refresh.pack(side='left', padx=12)
        self.btn_clear_filters = tk.Button(top, text='Clear filters', bg='#f3f3f3', relief='raised')
        self.btn_clear_filters.pack(side='left', padx=8)
        # --- In-window Help button (reliable on mac) ---
        self.btn_help = tk.Button(top, text='Help', bg='#f3f3f3', relief='raised', bd=1, highlightthickness=0)
        self.btn_help.pack(side='right', padx=(8,0))
        self._help_dropdown = tk.Menu(self, tearoff=0)
        self.btn_help.configure(command=lambda: self._show_help_dropdown_at(self.btn_help))
        # --- end Help button ---




        # ===== Action bar =====
        actions = tk.Frame(self, bg='white'); actions.pack(fill='x', padx=10, pady=(0,8))

        left = tk.Frame(actions, bg='white'); left.pack(side='left')
        self.btn_select_all = tk.Button(left, text='Select all (visible)', bg='#f3f3f3', relief='raised')
        self.btn_select_all.pack(side='left', padx=(0,8))
        self.btn_clear_sel = tk.Button(left, text='Clear selection', bg='#f3f3f3', relief='raised')
        self.btn_clear_sel.pack(side='left', padx=(0,16))
        self.btn_toggle_pkg = tk.Button(left, text='Toggle "Packaged" (selected)', bg='#fff4b8', relief='raised')
        self.btn_toggle_pkg.pack(side='left')
        self.btn_toggle_stk = tk.Button(left, text='Toggle "Sticker created" (selected)', bg='#dcecff', relief='raised')
        self.btn_toggle_stk.pack(side='left', padx=8)
        self.btn_clear_status = tk.Button(left, text='Clear status (selected)', bg='#f3f3f3', relief='raised')
        self.btn_clear_status.pack(side='left', padx=8)

        legend = tk.Frame(actions, bg='white'); legend.pack(side='right')
        tk.Label(legend, text='Legend:', bg='white', fg='black').pack(side='left', padx=(8,6))
        def legend_item(color, text):
            box = tk.Label(legend, width=2, height=1, bg=color, bd=1, relief='solid')
            box.pack(side='left', padx=(0,2))
            tk.Label(legend, text=text, bg='white', fg='black').pack(side='left', padx=(6,10))
        legend_item('#ffffff', 'None')
        legend_item('#fff4b8', 'Packaged')
        legend_item('#dcecff', 'Sticker')
        legend_item('#d6f5d6', 'Both')

        # ===== Table (Treeview) =====
        mid = tk.Frame(self, bg='white'); mid.pack(fill='both', expand=True, padx=10, pady=(0,6))
        mid.grid_rowconfigure(0, weight=1); mid.grid_columnconfigure(0, weight=1)
        self._overlay_parent = mid

        cols = ('sel','date','price','iban','comment','name','note')  # note column
        self.tbl = ttk.Treeview(mid, columns=cols, show='headings')

        attach_mousewheel(self.tbl)
        headers = {'sel':'', 'date':'Date', 'price':'Price', 'iban':'IBAN', 'comment':'Comment', 'name':'Name', 'note':'Note'}
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

        # Scrollbars with IMMEDIATE repositioning
        def _yview_wrapper(*args):
            self.tbl.yview(*args)
            # Force immediate update (no after_idle)
            self.tbl.update_idletasks()
            self._place_note_editors_now()
        
        def _xview_wrapper(*args):
            self.tbl.xview(*args)
            # Force immediate update (no after_idle)
            self.tbl.update_idletasks()
            self._place_note_editors_now()
        
        self._ysb = tk.Scrollbar(mid, orient='vertical', command=_yview_wrapper)
        self._ysb.grid(row=0, column=1, sticky='ns')
        self._xsb = tk.Scrollbar(mid, orient='horizontal', command=_xview_wrapper)
        self._xsb.grid(row=1, column=0, sticky='ew')

        # Configure treeview scroll commands with immediate repositioning
        def _yset_wrapper(*args):
            self._ysb.set(*args)
            self._place_note_editors_now()
        
        def _xset_wrapper(*args):
            self._xsb.set(*args)
            self._place_note_editors_now()
        
        self.tbl.configure(yscrollcommand=_yset_wrapper, xscrollcommand=_xset_wrapper)

        # --- inline note editors overlay for 'note' column ---
        self._note_widgets = {}        # iid -> tk.Text
        self._note_save_after_id = None

        # Cache column ID for performance
        self._note_col_id = None
        
        # CRITICAL: Only bind essential events
        # Update bottom boxes on selection (DEBOUNCED)
        self.tbl.bind("<<TreeviewSelect>>", lambda e: self._on_row_interact(), add="+")

        # Mouse wheel scroll - IMMEDIATE repositioning
        def _on_mousewheel(e):
            # Let default scroll happen first
            # Then immediately reposition
            self.after(1, self._place_note_editors_now)
        
        self.tbl.bind("<MouseWheel>", _on_mousewheel, add="+")
        
        # Reposition on arrow key navigation
        def _on_key_nav(e):
            if e.keysym in ("Up","Down","Prior","Next","Home","End"):
                self._on_row_interact()
                self.after(1, self._place_note_editors_now)
        
        self.tbl.bind("<KeyRelease>", _on_key_nav, add="+")

        # Initial placement
        self.after(200, self._place_note_editors_now)




        # ===== Bottom area (split into two boxes) =====
        bottom = tk.Frame(self, bg='white'); bottom.pack(fill='x', padx=10, pady=(0,10))
        # Status label for feedback
        self.lbl_status = tk.Label(self, text='', bg='white', fg='#007ACC', font=('Segoe UI', 11, 'bold'))
        self.lbl_status.pack(side='bottom', pady=(0, 5))

        # keep the bottom row a fixed pixel height (adjust to taste)
        BOTTOM_HEIGHT = 110
        bottom.configure(height= BOTTOM_HEIGHT)
        bottom.pack_propagate(False)   # <- prevents children (Text) from resizing the frame

        left = tk.Frame(bottom, bg='white');  left.pack(side='left',  fill='both', expand=True, padx=(0,6))
        right = tk.Frame(bottom, bg='white'); right.pack(side='left', fill='both', expand=True, padx=(6,0))

        tk.Label(left,  text='Statement comment:', bg='white', fg='black').pack(anchor='w')
        tk.Label(right, text='Custom note:',       bg='white', fg='black').pack(anchor='w')

        self._bottom_font = tkfont.Font(family='Segoe UI', size=16)
        self.txt_stmt = tk.Text(left,  height=6, wrap='word', bg='white', fg='black', font=self._bottom_font)
        attach_mousewheel(self.txt_stmt)
        self.txt_note = tk.Text(right, height=6, wrap='word', bg='white', fg='black', font=self._bottom_font)
        attach_mousewheel(self.txt_note)


        self.txt_stmt.pack(fill='both', expand=True)
        self.txt_note.pack(fill='both', expand=True)

        for _seq in ('<Command-s>', '<Command-e>', '<Control-s>', '<Control-e>', '<Command-BackSpace>', '<Escape>'):
            self.txt_note.bind(_seq, lambda ev: 'break')
        self._apply_bottom_text_insets(left_px=12, right_px=8, vpad_px=4)
        # Let typing in the bottom note update the inline cell + color + persistence
        self.txt_note.bind('<KeyRelease>', self._on_bottom_note_changed, add='+')




        # read-only
        self.txt_stmt.configure(state='disabled')
        self.txt_note.configure(state='disabled')

        # backwards-compat: if anything in app.py uses txt_comment, point it to statement box
        self.txt_comment = self.txt_stmt

    def _on_row_interact(self):
        """OPTIMIZED debounced handler - only update bottom boxes."""
        if hasattr(self, '_interact_after_id') and self._interact_after_id:
            try:
                self.after_cancel(self._interact_after_id)
            except:
                pass
        
        # Schedule update after 200ms (reduced frequency)
        self._interact_after_id = self.after(200, self._do_row_interact)

    def _do_row_interact(self):
        """Actually update UI after debounce - FAST VERSION."""
        try:
            self._refresh_bottom_from_selection()
            # Use immediate version for selection changes
            self._place_note_editors_now()
        except:
            pass

    def _on_bottom_note_changed(self, _event=None):
        """OPTIMIZED bottom note change handler."""
        try:
            sel = self.tbl.selection()
            if not sel:
                return
            iid = sel[0]
            text = self.txt_note.get('1.0', 'end-1c')

            # Update inline editor if visible
            if hasattr(self, '_note_widgets'):
                editor = self._note_widgets.get(iid)
                if editor:
                    try:
                        editor.delete('1.0', 'end')
                        editor.insert('1.0', text)
                        self._set_note_entry_bg(editor)
                    except:
                        pass

            # Update store
            key = self._make_row_key(iid) or str(iid)
            if not hasattr(self, '_note_store'):
                self._note_store = {}
            self._note_store[key] = text

            # Debounce save (longer delay)
            if getattr(self, "_save_after_id", None):
                try:
                    self.after_cancel(self._save_after_id)
                except:
                    pass
            self._save_after_id = self.after(500, self._save_note_store)  # Increased from 300ms

        except Exception:
            pass


    def _apply_bottom_text_insets(self, left_px=12, right_px=8, vpad_px=4):
        for w in (self.txt_stmt, self.txt_note):
            try:
                # Internal padding (if available on your Tk build)
                w.configure(padx=left_px, pady=vpad_px)
            except Exception:
                pass
            try:
                # Tag-based margins work everywhere
                w.tag_configure("_insets", lmargin1=left_px, lmargin2=left_px, rmargin=right_px)
                w.tag_add("_insets", "1.0", "end")
            except Exception:
                pass


    def _refresh_bottom_from_selection(self):
        """OPTIMIZED bottom box update - FASTEST version."""
        try:
            sel = self.tbl.selection()
            if not sel:
                self.set_comment('')
                self.set_note_view('')
                return

            iid = sel[0]
            vals = self.tbl.item(iid, 'values')
            
            # Get comment (direct index - comment is at index 4)
            comment = vals[4] if len(vals) > 4 else ''
            self.set_comment(comment)
            
            # Get note (fast path)
            note = ''
            try:
                # Try live editor first (fastest)
                if hasattr(self, '_note_widgets'):
                    w = self._note_widgets.get(iid)
                    if w:
                        note = w.get('1.0', 'end-1c')
                    else:
                        # Fallback to store
                        key = self._make_row_key(iid)
                        note = self._note_store.get(key, '') or ''
            except:
                pass
            
            self.set_note_view(note)
        except:
            pass

    def set_note_view(self, text: str):
        """Bottom box content only (no color change)."""
        try:
            self.txt_note.configure(state="normal")
            self.txt_note.delete("1.0", "end")
            self.txt_note.insert("1.0", text or "")
            self.txt_note.configure(state="disabled")
            self._apply_bottom_text_insets()
        except Exception:
            pass

    
    def _show_help_dropdown_at(self, widget):
        # Build dropdown from the real menubar Help and show under the button
        try:
            self._rebuild_help_dropdown()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height()
            self._help_dropdown.tk_popup(x, y)
        finally:
            try:
                self._help_dropdown.grab_release()
            except Exception:
                pass
    

    def _rebuild_help_dropdown(self):
        """Clone entries from the menubar Help menu into the button's dropdown."""
        try:
            m = self._help_dropdown
            m.delete(0, 'end')
            end = self.help_menu.index('end')
            if end is None:
                m.add_command(label="(No items)", state='disabled')
                return
            for i in range(end + 1):
                etype = self.help_menu.type(i)
                if etype == 'separator':
                    m.add_separator()
                elif etype == 'command':
                    label = self.help_menu.entrycget(i, 'label')
                    state = self.help_menu.entrycget(i, 'state') or 'normal'
                    m.add_command(label=label, state=state,
                                  command=lambda idx=i: self.help_menu.invoke(idx))
                else:
                    label = self.help_menu.entrycget(i, 'label')
                    m.add_command(label=label, state='disabled')
        except Exception:
            pass

    # === Persistence helpers ===
    def _load_note_store(self):
        """Safe loader: return {} if first run or file invalid."""
        try:
            data = load_notes()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
        
    def _load_firebase_notes(self):
        """Load notes from Firebase on startup."""
        try:
            if self.firebase_sync and self.firebase_sync.is_connected():
                firebase_notes = self.firebase_sync.get_all_notes()
                if firebase_notes:
                    self._note_store.update(firebase_notes)
        except Exception:
            pass

    def _make_row_key(self, iid):
        """Build a stable key from row values - CACHED."""
        # Use iid directly if it's the key
        return iid

    # === Note editor helpers ===
    def _set_note_entry_bg(self, widget):
        """Color the INLINE note editor - OPTIMIZED."""
        try:
            if isinstance(widget, tk.Text):
                txt = widget.get('1.0', 'end-1c')
            else:
                txt = widget.get()
        except:
            txt = ''

        has_text = bool((txt or '').strip())
        bg = '#FFD6D6' if has_text else '#FFFFFF'

        try:
            widget.configure(bg=bg, insertbackground='black')
        except:
            pass

    def _place_note_editors_now(self):
        """IMMEDIATE note editor positioning - NO throttling for scroll events."""
        try:
            tree = self.tbl
            if not tree.winfo_ismapped():
                return
            
            # Cache column lookup (ONCE)
            if not self._note_col_id:
                cols = list(tree['columns'])
                try:
                    note_idx = cols.index('note')
                    self._note_col_id = f"#{note_idx + 1}"
                except ValueError:
                    return
            
            if not hasattr(self, "_note_widgets"):
                self._note_widgets = {}
            
            parent = self._overlay_parent
            
            # Get visible rows
            visible_iids = set()
            children = tree.get_children("")
            if not children:
                return
            
            # Find visible rows
            for iid in children:
                try:
                    bbox = tree.bbox(iid, self._note_col_id)
                    if bbox:
                        visible_iids.add(iid)
                    if bbox and bbox[1] > tree.winfo_height():
                        break
                except:
                    pass
            
            # Hide non-visible editors
            for iid in list(self._note_widgets.keys()):
                if iid not in visible_iids:
                    try:
                        self._note_widgets[iid].place_forget()
                    except:
                        pass
            
            # Cache offset
            try:
                rx = tree.winfo_rootx() - parent.winfo_rootx()
                ry = tree.winfo_rooty() - parent.winfo_rooty()
            except:
                rx = ry = 0
            
            # Place visible editors
            for iid in visible_iids:
                try:
                    bbox = tree.bbox(iid, self._note_col_id)
                    if not bbox:
                        continue
                    
                    x, y, w, h = bbox
                    
                    # Reuse existing editor
                    editor = self._note_widgets.get(iid)
                    if editor is None:
                        editor = self._make_note_entry(iid)
                        self._note_widgets[iid] = editor
                    
                    # Quick position update
                    pad_x, pad_y = 4, 3
                    editor.place_configure(
                        x=rx + x + pad_x,
                        y=ry + y + pad_y,
                        width=w - 2*pad_x - 2,
                        height=h - 2*pad_y - 1
                    )
                    editor.lift()
                except:
                    pass
        except:
            pass

    def _place_note_editors(self):
        """ULTRA-OPTIMIZED note editor placement - ONLY visible rows."""
        try:
            # Reduced rate limit for smooth scrolling - max 60 times per second
            current_time = time.time()
            if hasattr(self, '_last_place_time'):
                if current_time - self._last_place_time < 0.016:  # ~60 FPS
                    return
            self._last_place_time = current_time
            
            tree = self.tbl
            if not tree.winfo_ismapped():
                return
            
            # Cache column lookup (ONCE)
            if not self._note_col_id:
                cols = list(tree['columns'])
                try:
                    note_idx = cols.index('note')
                    self._note_col_id = f"#{note_idx + 1}"
                except ValueError:
                    return
            
            if not hasattr(self, "_note_widgets"):
                self._note_widgets = {}
            
            parent = self._overlay_parent
            
            # Get ONLY visible rows (binary search approach)
            visible_iids = set()
            children = tree.get_children("")
            if not children:
                return
            
            # Find visible rows efficiently
            for iid in children:
                try:
                    bbox = tree.bbox(iid, self._note_col_id)
                    if bbox:
                        visible_iids.add(iid)
                    if bbox and bbox[1] > tree.winfo_height():
                        break  # Stop when past visible area
                except:
                    pass
            
            # Hide non-visible editors (batch operation)
            for iid in list(self._note_widgets.keys()):
                if iid not in visible_iids:
                    try:
                        self._note_widgets[iid].place_forget()
                    except:
                        pass
            
            # Cache offset calculation
            try:
                rx = tree.winfo_rootx() - parent.winfo_rootx()
                ry = tree.winfo_rooty() - parent.winfo_rooty()
            except:
                rx = ry = 0
            
            # Place ONLY visible editors
            for iid in visible_iids:
                try:
                    bbox = tree.bbox(iid, self._note_col_id)
                    if not bbox:
                        continue
                    
                    x, y, w, h = bbox
                    
                    # Reuse existing editor
                    editor = self._note_widgets.get(iid)
                    if editor is None:
                        editor = self._make_note_entry(iid)
                        self._note_widgets[iid] = editor
                    
                    # Quick position update
                    pad_x, pad_y = 4, 3
                    editor.place_configure(
                        x=rx + x + pad_x,
                        y=ry + y + pad_y,
                        width=w - 2*pad_x - 2,
                        height=h - 2*pad_y - 1
                    )
                    editor.lift()
                except:
                    pass
        except:
            pass



    def _make_note_entry(self, iid):
        """OPTIMIZED single-line Text widget for inline note editing."""
        e = tk.Text(
            self._overlay_parent,
            height=1, 
            wrap='none',
            bd=1, 
            relief='solid',
            highlightthickness=1,
            highlightbackground="#D0D0D0", 
            highlightcolor="#4A90E2",
            bg="white", 
            fg="black", 
            insertbackground="black", 
            insertwidth=1,
            font=('Segoe UI', 10)
        )
        
        # Block text selection to prevent visual glitches
        e.configure(
            exportselection=False,
            selectborderwidth=0,
            selectbackground='white',
            inactiveselectbackground='white',
        )
        
        # Let Text handle typing first, then block propagation
        try:
            tags = list(e.bindtags())
            if 'Text' in tags:
                tags.remove('Text')
                tags.insert(0, 'Text')
                e.bindtags(tuple(tags))
        except:
            pass
        
        # Block all key events from propagating
        e.bind('<Key>', lambda ev: 'break', add='+')
        
        # Clear selection on blur
        e.bind('<FocusOut>', lambda ev: e.tag_remove('sel', '1.0', 'end'), add='+')
        
        # Keep row selected when clicking in editor
        e.bind("<FocusIn>",  lambda ev, _iid=iid: (self.tbl.selection_set(_iid), self.tbl.focus(_iid)), add="+")
        e.bind("<Button-1>", lambda ev, _iid=iid: (self.tbl.selection_set(_iid), self.tbl.focus(_iid)), add="+")
        
        # Block navigation keys
        def _block_nav(ev):
            if ev.keysym.lower() in ("up","down","prior","next","home","end"):
                return "break"
        e.bind("<KeyPress>", _block_nav, add="+")
        
        # Initialize with saved text
        key = iid  # Use iid directly as key
        init = (self._note_store.get(key, "") if hasattr(self, "_note_store") else "") or ""
        if init:
            e.insert('1.0', init)
        self._set_note_entry_bg(e)
        
        # OPTIMIZED save handler - batch Firebase saves
        def on_change(_ev=None, widget=e):
            try:
                txt = widget.get('1.0', 'end-1c')
                self._set_note_entry_bg(widget)
                
                # Save to local store
                if not hasattr(self, "_note_store"):
                    self._note_store = {}
                key = iid
                self._note_store[key] = txt
                
                # Batch Firebase saves - every 3 seconds max
                current_time = time.time()
                last_save = getattr(self, '_last_firebase_save', 0)
                if current_time - last_save > 3:
                    # Save immediately if 3+ seconds since last save
                    self.after(100, lambda: self._save_note_to_firebase(key, txt))
                    self._last_firebase_save = current_time
                else:
                    # Otherwise debounce 2 seconds
                    if getattr(self, "_firebase_save_after_id", None):
                        try: self.after_cancel(self._firebase_save_after_id)
                        except: pass
                    self._firebase_save_after_id = self.after(2000, lambda: self._save_note_to_firebase(key, txt))

                # Debounced local disk save (backup) - 500ms
                if getattr(self, "_save_after_id", None):
                    try: self.after_cancel(self._save_after_id)
                    except: pass
                self._save_after_id = self.after(500, self._save_note_store)
                
                # Update bottom note box if this row is selected
                sel = self.tbl.selection()
                if sel and sel[0] == iid:
                    self.set_note_view(txt)
            except Exception:
                pass

        e.bind("<KeyRelease>", on_change, add="+")
        return e


    def set_status(self, msg: str): return  # status hidden intentionally


    def reset_selection_color(self):
        """Best-effort: keep selection visuals intact without changing layout."""
        try:
            _ = self.tbl.selection()
            return
        except Exception:
            return

    def set_comment(self, text: str):
        try:
            self.txt_stmt.configure(state='normal')
            self.txt_stmt.delete('1.0', 'end')
            self.txt_stmt.insert('1.0', text or '')
            self.txt_stmt.configure(state='disabled')
            self._apply_bottom_text_insets()
        except Exception:
            pass

    def _save_note_store(self):
        """Persist notes atomically to per-user JSON store."""
        try:
            save_notes(self._note_store)
        except Exception:
            pass
        finally:
            self._save_after_id = None

    def _save_note_to_firebase(self, key, txt):
        """Save note to Firebase - with silent error handling."""
        try:
            if hasattr(self, 'firebase_sync') and self.firebase_sync:
                self.firebase_sync.set_note(key, txt)
        except Exception:
            pass  # Silent failure for performance