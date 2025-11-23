#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup Wizard for TrackNote - Data Source Configuration
PROPERLY STYLED VERSION - Looks great on all systems!
"""

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import json
import re
from user_data import read_user_config, write_user_config
from data_source import test_connection


class SetupWizard(tk.Toplevel):
    """Setup wizard for configuring data source."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("TrackNote Setup")
        self.geometry("650x600")
        self.resizable(False, False)
        
        self.configure(bg='#f5f5f5')
        
        self.withdraw()
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 325
        y = (self.winfo_screenheight() // 2) - 300
        self.geometry(f"650x600+{x}+{y}")
        
        self.is_standalone = False
        try:
            if parent and parent.winfo_exists() and parent.winfo_viewable():
                self.transient(parent)
                self.grab_set()
            else:
                self.is_standalone = True
                self.lift(); self.focus_force()
        except Exception:
            self.is_standalone = True
            self.lift(); self.focus_force()
        
        self.completed = False
        self.source_type = tk.StringVar(value="google_sheets")
        
        self._create_widgets()
        self._load_existing_config()
        
        self.deiconify()
        self.update()
        self.lift()
        
    def _create_widgets(self):
        """Create the setup wizard UI."""
        header = tk.Frame(self, bg='#2C5F8D', height=70)
        header.pack(fill='x'); header.pack_propagate(False)
        tk.Label(header, text="TrackNote Setup", font=('Arial', 20, 'bold'), bg='#2C5F8D', fg='white').pack(pady=20)
        
        self.content = tk.Frame(self, bg='#f5f5f5')
        self.content.pack(fill='both', expand=True, padx=25, pady=20)
        
        self.selection_frame = tk.Frame(self.content, bg='#f5f5f5')
        self.selection_frame.pack(fill='both', expand=True)
        tk.Label(self.selection_frame, text="Choose your data source:", font=('Arial', 13, 'bold'), bg='#f5f5f5', fg='#333').pack(anchor='w', pady=(0, 20))
        
        button_container = tk.Frame(self.selection_frame, bg='#f5f5f5')
        button_container.pack(fill='both', expand=True)
        
        sheets_btn = tk.Button(button_container, text="📊\n\nGoogle Sheets\n\nSync from cloud", command=lambda: self._select_source("google_sheets"), bg='#4285F4', fg='white', font=('Arial', 12, 'bold'), relief='solid', bd=2, padx=30, pady=30, cursor='hand2')
        sheets_btn.pack(side='left', expand=True, fill='both', padx=10)
        
        excel_btn = tk.Button(button_container, text="📁\n\nExcel File (.xlsx)\n\nLocal file on computer", command=lambda: self._select_source("file"), bg='#107C41', fg='white', font=('Arial', 12, 'bold'), relief='solid', bd=2, padx=30, pady=30, cursor='hand2')
        excel_btn.pack(side='left', expand=True, fill='both', padx=10)
        
        self.config_frame = tk.Frame(self.content, bg='#f5f5f5')
        back_frame = tk.Frame(self.config_frame, bg='#f5f5f5')
        back_frame.pack(fill='x', pady=(0, 15))
        tk.Button(back_frame, text="← Back to selection", command=self._show_selection, bg='#f5f5f5', fg='#007ACC', font=('Arial', 12), relief='flat', cursor='hand2').pack(side='left')
        
        self.source_label = tk.Label(self.config_frame, text="", font=('Arial', 12, 'bold'), bg='#f5f5f5', fg='#333')
        self.source_label.pack(anchor='w', pady=(0, 5))
        
        self.error_label = tk.Label(self.config_frame, text="", font=('Arial', 10, 'bold'), bg='#f5f5f5', fg='#dc3545', wraplength=550)
        self.error_label.pack(anchor='w', pady=(0, 10))
        
        self.file_config = tk.Frame(self.config_frame, bg='white', padx=20, pady=20, relief='solid', bd=1)
        tk.Label(self.file_config, text="Select your Excel or CSV file:", bg='white', fg='#666', font=('Arial', 10)).pack(anchor='w', pady=(0, 15))
        file_input_frame = tk.Frame(self.file_config, bg='white')
        file_input_frame.pack(fill='x')
        tk.Label(file_input_frame, text="File:", bg='white', fg='#444', font=('Arial', 10)).pack(side='left', padx=(0, 10))
        self.file_path_var = tk.StringVar()
        self.file_entry = tk.Entry(file_input_frame, textvariable=self.file_path_var, width=40, bg='white', fg='#000000', relief='solid', bd=1, font=('Arial', 10), insertbackground='#000000')
        self.file_entry.pack(side='left', fill='x', expand=True, padx=5, ipady=5)
        self.file_browse_btn = tk.Button(file_input_frame, text="Browse...", command=self._browse_file, bg='#e0e0e0', fg='#333', relief='solid', bd=1, font=('Arial', 9), padx=15, pady=5, cursor='hand2')
        self.file_browse_btn.pack(side='left')
        
        self.sheets_config = tk.Frame(self.config_frame, bg='white', padx=20, pady=20, relief='solid', bd=1)
        tk.Label(self.sheets_config, text="Step 1: Share your Google Sheet with this email:", bg='white', fg='#666', font=('Arial', 10)).pack(anchor='w', pady=(0, 8))
        
        # --- MODIFIED: Email frame now includes a Copy button ---
        email_frame = tk.Frame(self.sheets_config, bg='#f0f8ff', relief='solid', bd=1, padx=10, pady=10)
        email_frame.pack(fill='x', pady=(0, 20))
        
        self.service_email = tk.Entry(email_frame, bg='#f0f8ff', fg='#0066cc', font=('Arial', 10, 'bold'), relief='flat', readonlybackground='#f0f8ff', state='readonly', borderwidth=0)
        self.service_email.pack(side='left', fill='x', expand=True, anchor='w')
        
        self.copy_email_btn = tk.Button(email_frame, text="Copy", command=self._copy_email, bg='#d4edda', fg='#155724', relief='solid', bd=1, font=('Arial', 9), padx=10, pady=2, cursor='hand2')
        self.copy_email_btn.pack(side='left', padx=(10, 0))
        # --- END OF MODIFICATION ---
        
        tk.Label(self.sheets_config, text="Step 2: Paste your Google Sheets URL below:", bg='white', fg='#666', font=('Arial', 10)).pack(anchor='w', pady=(0, 8))
        url_frame = tk.Frame(self.sheets_config, bg='white')
        url_frame.pack(fill='x', pady=(0, 0))
        tk.Label(url_frame, text="Sheet URL:", bg='white', fg='#444', font=('Arial', 10), width=10, anchor='w').pack(side='left', padx=(0, 5))
        self.sheet_url_var = tk.StringVar()
        self.sheet_url_entry = tk.Entry(url_frame, textvariable=self.sheet_url_var, bg='white', fg='#000000', relief='solid', bd=1, font=('Arial', 10), insertbackground='#000000')
        self.sheet_url_entry.pack(side='left', fill='x', expand=True, ipady=5)
        
        tk.Label(self.sheets_config, text="Step 3: Enter the tab/sheet name (default: Sheet1):", bg='white', fg='#666', font=('Arial', 10)).pack(anchor='w', pady=(20, 8))
        tab_frame = tk.Frame(self.sheets_config, bg='white')
        tab_frame.pack(fill='x', pady=(0, 0))
        tk.Label(tab_frame, text="Tab Name:", bg='white', fg='#444', font=('Arial', 10), width=10, anchor='w').pack(side='left', padx=(0, 5))
        self.tab_name_var = tk.StringVar(value="Sheet1")
        self.tab_name_entry = tk.Entry(tab_frame, textvariable=self.tab_name_var, bg='white', fg='#000000', relief='solid', bd=1, font=('Arial', 10), insertbackground='#000000')
        self.tab_name_entry.pack(side='left', fill='x', expand=True, ipady=5)
        
        self.cred_path_var = tk.StringVar()
        
        self.status_label = tk.Label(self.config_frame, text="", bg='#f5f5f5', fg='#666', font=('Arial', 9), wraplength=550)
        self.status_label.pack(pady=15)
        
        btn_frame = tk.Frame(self, bg='#e8e8e8', height=60)
        btn_frame.pack(fill='x', side='bottom'); btn_frame.pack_propagate(False)
        
        self.cancel_btn = tk.Button(btn_frame, text="Cancel", command=self._cancel, bg='#d0d0d0', fg='#333', font=('Arial', 10), relief='solid', bd=1, padx=20, pady=6, cursor='hand2')
        self.cancel_btn.pack(side='left', padx=20, pady=15)
        
        self.test_btn = tk.Button(btn_frame, text="Test Connection", command=self._test_connection, bg='#28a745', fg='white', font=('Arial', 10, 'bold'), relief='solid', bd=0, padx=15, pady=6, cursor='hand2')
        self.save_btn = tk.Button(btn_frame, text="Save & Continue", command=self._save, bg='#007ACC', fg='white', font=('Arial', 10, 'bold'), relief='solid', bd=0, padx=15, pady=6, cursor='hand2')

    # --- NEW: Command for the Copy button ---
    def _copy_email(self):
        """Copies the service account email to the clipboard."""
        email = self.service_email.get()
        if email and 'not found' not in email:
            self.clipboard_clear()
            self.clipboard_append(email)
            
            # Provide visual feedback
            original_text = self.copy_email_btn.cget("text")
            self.copy_email_btn.config(text="Copied!", state="disabled")
            self.after(2000, lambda: self.copy_email_btn.config(text=original_text, state="normal"))

    def _select_source(self, source):
        """Handle source selection from buttons."""
        self.source_type.set(source)
        self.status_label.config(text="")
        self.error_label.config(text="")
        self.selection_frame.pack_forget()
        self.config_frame.pack(fill='both', expand=True)
        self.test_btn.pack(side='right', padx=(0, 10), pady=15)
        self.save_btn.pack(side='right', padx=10, pady=15)
        
        if source == "file":
            self.source_label.config(text="📁 Excel File Configuration")
            self.file_config.pack(fill='x')
            self.sheets_config.pack_forget()
        else:
            self.source_label.config(text="📊 Google Sheets Configuration")
            self.sheets_config.pack(fill='x')
            self.file_config.pack_forget()
            self._load_service_email()
        
        self.update_idletasks()
        self.update()
    
    def _show_selection(self):
        """Return to source selection screen."""
        self.config_frame.pack_forget()
        self.selection_frame.pack(fill='both', expand=True)
        self.status_label.config(text="")
        self.error_label.config(text="")
        self.test_btn.pack_forget()
        self.save_btn.pack_forget()
        self.update_idletasks()
        self.update()
    
    def _load_service_email(self):
        """Load and display service account email from bundled credentials."""
        import sys
        possible_paths = [
            Path('credentials.json'), Path('credentials/service-account.json'),
            Path(__file__).parent / 'credentials.json',
            Path(__file__).parent / 'credentials' / 'service-account.json',
        ]
        try:
            cfg = read_user_config()
            custom_path = cfg.get('credentials_path', '')
            if custom_path: possible_paths.insert(0, Path(custom_path))
        except: pass
        
        for cred_path in possible_paths:
            try:
                if cred_path.exists():
                    with open(cred_path, 'r') as f: creds = json.load(f)
                    email = creds.get('client_email', 'No email found')
                    self.service_email.config(state='normal')
                    self.service_email.delete(0, tk.END)
                    self.service_email.insert(0, email)
                    self.service_email.config(state='readonly', fg='#0066cc', readonlybackground='#f0f8ff')
                    self.cred_path_var.set(str(cred_path))
                    try:
                        cfg = read_user_config()
                        cfg['credentials_path'] = str(cred_path)
                        write_user_config(cfg)
                    except: pass
                    return
            except Exception: continue
        
        self.service_email.config(state='normal')
        self.service_email.delete(0, tk.END)
        self.service_email.insert(0, '⚠️ credentials.json not found in app folder')
        self.service_email.config(state='readonly', fg='#856404', readonlybackground='#fff3cd')
    
    def _browse_file(self):
        """Browse for Excel/CSV file."""
        filetypes = [("Excel files", "*.xlsx *.xls"), ("CSV files", "*.csv"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(title="Select data file", filetypes=filetypes)
        if filename: self.file_path_var.set(filename)
    
    def _load_existing_config(self):
        """Load and display existing configuration."""
        try:
            cfg = read_user_config()
            source = cfg.get('data_source', 'google_sheets')
            
            if source == 'file':
                self.file_path_var.set(cfg.get('file_path', ''))
            elif source == 'google_sheets':
                self.sheet_url_var.set(cfg.get('sheet_url', ''))
                self.tab_name_var.set(cfg.get('tab_name', 'Sheet1'))
                self.cred_path_var.set(cfg.get('credentials_path', ''))
            
            if cfg.get('file_path') or cfg.get('sheet_url'):
                self._select_source(source)
                self.error_label.config(text="")
                self.status_label.config(text="")
        except: pass
    
    def _test_connection(self):
        """Test the configured data source."""
        self.status_label.config(text="Testing connection...", fg='#666')
        self.error_label.config(text="")
        self.update()
        
        try:
            cfg = self._build_config()
            row_count, error = test_connection(cfg)
            
            if error:
                self.error_label.config(text=f"⚠️ Connection Error: {error}")
                self.status_label.config(text="", fg='#666')
            else:
                self.status_label.config(text=f"✓ Success! Connected and found {row_count} rows.", fg='#28a745')
                self.error_label.config(text="")
        except ValueError as e:
            self.error_label.config(text=f"⚠️ {str(e)}")
            self.status_label.config(text="", fg='#666')
        except Exception as e:
            self.error_label.config(text=f"⚠️ Error: {str(e)}")
            self.status_label.config(text="", fg='#666')
    
    def _build_config(self):
        """Build configuration dict from UI inputs."""
        source = self.source_type.get()
        cfg = {'data_source': source}
        
        if source == 'file':
            file_path = self.file_entry.get().strip()
            if not file_path or not Path(file_path).exists():
                raise ValueError("Please select a valid file")
            cfg['file_path'] = file_path
        elif source == 'google_sheets':
            url = self.sheet_url_entry.get().strip()
            if not url: raise ValueError("Please enter your Google Sheets URL")
            
            match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
            if not match: raise ValueError("Could not find a valid Sheet ID in the URL")
            
            cfg['sheet_url'] = url
            cfg['spreadsheet_id'] = match.group(1)
            cfg['tab_name'] = self.tab_name_entry.get().strip() or 'Sheet1'
            cfg['credentials_path'] = self.cred_path_var.get().strip()
            if not cfg['credentials_path']: raise ValueError("Credentials file not found")
        
        return cfg
    
    def _save(self):
        """Save the configuration."""
        try:
            cfg_new = self._build_config()
            cfg = read_user_config()
            cfg.update(cfg_new)
            write_user_config(cfg)
            
            self.completed = True
            messagebox.showinfo("Success", "Configuration saved successfully!", parent=self)
            self.destroy()
        except ValueError as e:
            self.error_label.config(text=f"⚠️ {str(e)}")
            self.status_label.config(text="")
        except Exception as e:
            self.error_label.config(text=f"⚠️ Error: {str(e)}")
            self.status_label.config(text="")
    
    def _cancel(self):
        self.completed = False
        self.destroy()
    
    def destroy(self):
        if not getattr(self, 'is_standalone', False):
            try: self.grab_release()
            except: pass
        try: super().destroy()
        except: pass
    
    def run(self):
        self.wait_window()
        return self.completed

def show_setup_wizard(parent=None):
    """Show the setup wizard dialog."""
    root = parent if parent else tk.Tk()
    if not parent: root.withdraw()
    
    wizard = SetupWizard(root)
    result = wizard.run()
    
    if not parent:
        try: root.destroy()
        except: pass
    return result

if __name__ == "__main__":
    print("Starting setup wizard...")
    completed = show_setup_wizard()
    print(f"Setup completed: {completed}")