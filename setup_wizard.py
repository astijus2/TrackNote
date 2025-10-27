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
        
        # CRITICAL: Set background color explicitly
        self.configure(bg='#f5f5f5')
        
        # Center on screen - do this early
        self.withdraw()  # Hide while setting up
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 325
        y = (self.winfo_screenheight() // 2) - 300
        self.geometry(f"650x600+{x}+{y}")
        
        # Window management
        self.is_standalone = False
        try:
            if parent and parent.winfo_exists() and parent.winfo_viewable():
                # Modal dialog with visible parent
                self.transient(parent)
                self.grab_set()
            else:
                # Standalone window (no parent or hidden parent)
                self.is_standalone = True
                self.lift()
                self.focus_force()
        except Exception:
            # Fallback for window management issues
            self.is_standalone = True
            self.lift()
            self.focus_force()
        
        self.completed = False
        self.source_type = tk.StringVar(value="google_sheets")
        
        self._create_widgets()
        self._load_existing_config()
        
        # Show window after everything is created
        self.deiconify()
        self.update()
        self.lift()  # Bring to front
        
        print("DEBUG: Setup wizard initialization complete!")
        
    def _create_widgets(self):
        """Create the setup wizard UI."""
        print("DEBUG: Creating setup wizard widgets...")
        
        # Header
        header = tk.Frame(self, bg='#2C5F8D', height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="TrackNote Setup",
                font=('Arial', 20, 'bold'), bg='#2C5F8D', fg='white').pack(pady=20)
        
        print("DEBUG: Header created")
        
        # Content
        self.content = tk.Frame(self, bg='#f5f5f5')
        self.content.pack(fill='both', expand=True, padx=25, pady=20)
        
        print("DEBUG: Content frame created")
        
        # === SELECTION BUTTONS ===
        self.selection_frame = tk.Frame(self.content, bg='#f5f5f5')
        self.selection_frame.pack(fill='both', expand=True)
        
        # Instructions (for selection screen)
        tk.Label(self.selection_frame, text="Choose your data source:",
                font=('Arial', 13, 'bold'), bg='#f5f5f5', fg='#333').pack(anchor='w', pady=(0, 20))
        
        # Button container
        button_container = tk.Frame(self.selection_frame, bg='#f5f5f5')
        button_container.pack(fill='both', expand=True)
        
        # Google Sheets Button
        sheets_btn = tk.Button(button_container,
                              text="📊\n\nGoogle Sheets\n\nSync from cloud",
                              command=lambda: self._select_source("google_sheets"),
                              bg='#4285F4', fg='white',
                              font=('Arial', 12, 'bold'),
                              relief='solid', bd=2,
                              padx=30, pady=30,
                              cursor='hand2')
        sheets_btn.pack(side='left', expand=True, fill='both', padx=10)
        
        # Excel File Button
        excel_btn = tk.Button(button_container,
                             text="📁\n\nExcel File (.xlsx)\n\nLocal file on computer",
                             command=lambda: self._select_source("file"),
                             bg='#107C41', fg='white',
                             font=('Arial', 12, 'bold'),
                             relief='solid', bd=2,
                             padx=30, pady=30,
                             cursor='hand2')
        excel_btn.pack(side='left', expand=True, fill='both', padx=10)
        
        # === CONFIG FRAME (hidden initially) ===
        self.config_frame = tk.Frame(self.content, bg='#f5f5f5')
        
        # Back button at top
        back_frame = tk.Frame(self.config_frame, bg='#f5f5f5')
        back_frame.pack(fill='x', pady=(0, 15))
        
        tk.Button(back_frame,
                 text="← Back to selection",
                 command=self._show_selection,
                 bg='#f5f5f5', fg='#007ACC',
                 font=('Arial', 12),
                 relief='flat',
                 cursor='hand2').pack(side='left')
        
        # Selected source label below back button
        self.source_label = tk.Label(self.config_frame,
                                     text="",
                                     font=('Arial', 12, 'bold'),
                                     bg='#f5f5f5', fg='#333')
        self.source_label.pack(anchor='w', pady=(0, 5))
        
        # ERROR LABEL - Added for better validation feedback
        self.error_label = tk.Label(self.config_frame,
                                   text="",
                                   font=('Arial', 10, 'bold'),
                                   bg='#f5f5f5', fg='#dc3545',
                                   wraplength=550)
        self.error_label.pack(anchor='w', pady=(0, 10))
        
        # ===== FILE INPUTS =====
        self.file_config = tk.Frame(self.config_frame, bg='white',
                                   padx=20, pady=20,
                                   relief='solid', bd=1)
        
        tk.Label(self.file_config, 
                text="Select your Excel or CSV file:",
                bg='white', fg='#666', 
                font=('Arial', 10)).pack(anchor='w', pady=(0, 15))
        
        file_input_frame = tk.Frame(self.file_config, bg='white')
        file_input_frame.pack(fill='x')
        
        tk.Label(file_input_frame, text="File:", bg='white', fg='#444',
                font=('Arial', 10)).pack(side='left', padx=(0, 10))
        
        self.file_path_var = tk.StringVar()
        self.file_entry = tk.Entry(file_input_frame, 
                                   textvariable=self.file_path_var,
                                   width=40,
                                   bg='white', fg='#000000',  # BLACK TEXT
                                   relief='solid', bd=1,
                                   font=('Arial', 10),
                                   insertbackground='#000000')  # BLACK CURSOR
        self.file_entry.pack(side='left', fill='x', expand=True, padx=5, ipady=5)
        
        self.file_browse_btn = tk.Button(file_input_frame, 
                                         text="Browse...",
                                         command=self._browse_file,
                                         bg='#e0e0e0', fg='#333',
                                         relief='solid', bd=1,
                                         font=('Arial', 9),
                                         padx=15, pady=5,
                                         cursor='hand2')
        self.file_browse_btn.pack(side='left')
        
        # ===== GOOGLE SHEETS INPUTS =====
        self.sheets_config = tk.Frame(self.config_frame, bg='white',
                                     padx=20, pady=20,
                                     relief='solid', bd=1)
        
        # Step 1: Email section
        tk.Label(self.sheets_config, 
                text="Step 1: Share your Google Sheet with this email:",
                bg='white', fg='#666', 
                font=('Arial', 10)).pack(anchor='w', pady=(0, 8))
        
        # Simple email box with border - COPYABLE
        email_frame = tk.Frame(self.sheets_config, bg='#f0f8ff',
                              relief='solid', bd=1, padx=10, pady=10)
        email_frame.pack(fill='x', pady=(0, 20))
        
        # Use Entry instead of Label so user can select and copy
        self.service_email = tk.Entry(email_frame,
                                     bg='#f0f8ff', fg='#0066cc',
                                     font=('Arial', 10, 'bold'),
                                     relief='flat',
                                     readonlybackground='#f0f8ff',
                                     state='readonly',
                                     borderwidth=0)
        self.service_email.pack(fill='x', anchor='w')
        
        # Step 2: URL section
        tk.Label(self.sheets_config, 
                text="Step 2: Paste your Google Sheets URL below:",
                bg='white', fg='#666', 
                font=('Arial', 10)).pack(anchor='w', pady=(0, 8))
        
        # URL input
        url_frame = tk.Frame(self.sheets_config, bg='white')
        url_frame.pack(fill='x', pady=(0, 0))
        
        tk.Label(url_frame, text="Sheet URL:", bg='white', fg='#444',
                font=('Arial', 10), width=10, anchor='w').pack(side='left', padx=(0, 5))
        
        self.sheet_url_var = tk.StringVar()
        self.sheet_url_entry = tk.Entry(url_frame, 
                                        textvariable=self.sheet_url_var,
                                        bg='white', fg='#000000',
                                        relief='solid', bd=1,
                                        font=('Arial', 10),
                                        insertbackground='#000000')
        self.sheet_url_entry.pack(side='left', fill='x', expand=True, ipady=5)
        self.sheet_url_entry.bind('<KeyRelease>', lambda e: self._on_url_change())
        self.sheet_url_entry.bind('<FocusOut>', lambda e: self._validate_url_field())
        
        # Step 3: Tab name section
        tk.Label(self.sheets_config, 
                text="Step 3: Enter the tab/sheet name (default: Sheet1):",
                bg='white', fg='#666', 
                font=('Arial', 10)).pack(anchor='w', pady=(20, 8))
        
        # Tab name input
        tab_frame = tk.Frame(self.sheets_config, bg='white')
        tab_frame.pack(fill='x', pady=(0, 0))
        
        tk.Label(tab_frame, text="Tab Name:", bg='white', fg='#444',
                font=('Arial', 10), width=10, anchor='w').pack(side='left', padx=(0, 5))
        
        self.tab_name_var = tk.StringVar(value="Sheet1")
        self.tab_name_entry = tk.Entry(tab_frame, 
                                       textvariable=self.tab_name_var,
                                       bg='white', fg='#000000',
                                       relief='solid', bd=1,
                                       font=('Arial', 10),
                                       insertbackground='#000000')
        self.tab_name_entry.pack(side='left', fill='x', expand=True, ipady=5)
        
        # Hidden variables for backward compatibility
        self.sheet_id_var = tk.StringVar()
        self.cred_path_var = tk.StringVar()
        
        # Status label
        self.status_label = tk.Label(self.config_frame, text="", 
                                     bg='#f5f5f5', fg='#666',
                                     font=('Arial', 9),
                                     wraplength=550)
        self.status_label.pack(pady=15)
        
        # Buttons
        btn_frame = tk.Frame(self, bg='#e8e8e8', height=60)
        btn_frame.pack(fill='x', side='bottom')
        btn_frame.pack_propagate(False)
        
        self.cancel_btn = tk.Button(btn_frame, 
                 text="Cancel", 
                 command=self._cancel,
                 bg='#d0d0d0', fg='#333',
                 font=('Arial', 10),
                 relief='solid', bd=1,
                 padx=20, pady=6,
                 cursor='hand2')
        self.cancel_btn.pack(side='left', padx=20, pady=15)
        
        self.test_btn = tk.Button(btn_frame, 
                 text="Test Connection", 
                 command=self._test_connection,
                 bg='#28a745', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='solid', bd=0,
                 padx=15, pady=6,
                 cursor='hand2')
        # Don't pack initially
        
        self.save_btn = tk.Button(btn_frame, 
                 text="Save & Continue", 
                 command=self._save,
                 bg='#007ACC', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='solid', bd=0,
                 padx=15, pady=6,
                 cursor='hand2')
        # Don't pack initially
        
        print("DEBUG: All widgets created successfully!")
    
    def _select_source(self, source):
        """Handle source selection from buttons."""
        self.source_type.set(source)
        self.status_label.config(text="")  # Clear any status messages
        self.error_label.config(text="")  # Clear any error messages
        
        # Hide selection frame, show config frame
        self.selection_frame.pack_forget()
        self.config_frame.pack(fill='both', expand=True)
        
        # Show action buttons
        self.test_btn.pack(side='right', padx=(0, 10), pady=15)
        self.save_btn.pack(side='right', padx=10, pady=15)
        
        # Show appropriate config section
        if source == "file":
            self.source_label.config(text="📁 Excel File Configuration")
            self.file_config.pack(fill='x')
            self.sheets_config.pack_forget()
        else:  # google_sheets
            self.source_label.config(text="📊 Google Sheets Configuration")
            self.sheets_config.pack(fill='x')
            self.file_config.pack_forget()
            self._load_service_email()
        
        # Force immediate UI update to show buttons
        self.update_idletasks()
        self.update()
    
    def _show_selection(self):
        """Return to source selection screen."""
        # Hide config frame, show selection frame
        self.config_frame.pack_forget()
        self.selection_frame.pack(fill='both', expand=True)
        self.status_label.config(text="")  # Clear status
        self.error_label.config(text="")  # Clear error
        
        # Hide action buttons
        self.test_btn.pack_forget()
        self.save_btn.pack_forget()
        
        # Force immediate UI update
        self.update_idletasks()
        self.update()
    
    def _load_service_email(self):
        """Load and display service account email from bundled credentials."""
        # Try multiple locations for credentials file
        import sys
        possible_paths = [
            Path('credentials.json'),  # Same directory as script
            Path('credentials/service-account.json'),  # Credentials subdirectory
            Path(__file__).parent / 'credentials.json',  # Script directory
            Path(__file__).parent / 'credentials' / 'service-account.json',  # Script credentials directory
        ]
        
        # Also check user config for custom path
        try:
            cfg = read_user_config()
            custom_path = cfg.get('credentials_path', '')
            if custom_path:
                possible_paths.insert(0, Path(custom_path))
        except:
            pass
        
        # Try to find and load credentials
        for cred_path in possible_paths:
            try:
                if cred_path.exists():
                    with open(cred_path, 'r') as f:
                        creds = json.load(f)
                        email = creds.get('client_email', 'No email found')
                        # Update Entry widget text
                        self.service_email.config(state='normal')
                        self.service_email.delete(0, tk.END)
                        self.service_email.insert(0, email)
                        self.service_email.config(state='readonly', 
                                                 fg='#0066cc', 
                                                 readonlybackground='#f0f8ff')
                        self.cred_path_var.set(str(cred_path))
                        # Save the working path to config for next time
                        try:
                            cfg = read_user_config()
                            cfg['credentials_path'] = str(cred_path)
                            write_user_config(cfg)
                        except:
                            pass
                        return
            except Exception:
                continue
        
        # If we get here, no credentials file was found
        self.service_email.config(state='normal')
        self.service_email.delete(0, tk.END)
        self.service_email.insert(0, '⚠️ credentials.json not found in app folder')
        self.service_email.config(state='readonly',
                                 fg='#856404',
                                 readonlybackground='#fff3cd')
    
    def _validate_url_field(self):
        """Validate URL field and show immediate feedback - READ FROM WIDGET."""
        url = self.sheet_url_entry.get().strip()  # READ FROM WIDGET
        if not url:
            return  # Don't show error for empty field
        
        try:
            # Clean URL
            url = url.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            
            # Look for Sheet ID
            sheet_id = None
            if '/d/' in url:
                parts = url.split('/d/')
                if len(parts) > 1:
                    id_part = parts[1]
                    for char in ['/', '?', '#']:
                        if char in id_part:
                            id_part = id_part.split(char)[0]
                    sheet_id = id_part
            
            if not sheet_id:
                match = re.search(r'([a-zA-Z0-9-_]{30,})', url)
                if match:
                    sheet_id = match.group(1)
                    for char in ['/', '?', '#', '&']:
                        if char in sheet_id:
                            sheet_id = sheet_id.split(char)[0]
            
            if sheet_id:
                self.error_label.config(text="")
                self.sheet_url_entry.config(bg='white')
            else:
                raise ValueError("Could not find Sheet ID")
        except:
            self.error_label.config(text="⚠️ Please enter a valid Google Sheets URL")
            self.sheet_url_entry.config(bg='#fff3cd')
    
    
    def _on_url_change(self):
        """Parse URL and extract sheet ID automatically - READ FROM WIDGET."""
        url = self.sheet_url_entry.get().strip()  # READ FROM WIDGET
        if not url:
            return
        
        try:
            # Clean URL
            url = url.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            
            # Method 1: Look for /d/
            sheet_id = None
            if '/d/' in url:
                parts = url.split('/d/')
                if len(parts) > 1:
                    id_part = parts[1]
                    for char in ['/', '?', '#']:
                        if char in id_part:
                            id_part = id_part.split(char)[0]
                    sheet_id = id_part
            
            # Method 2: Pattern match
            if not sheet_id:
                match = re.search(r'([a-zA-Z0-9-_]{30,})', url)
                if match:
                    sheet_id = match.group(1)
                    for char in ['/', '?', '#', '&']:
                        if char in sheet_id:
                            sheet_id = sheet_id.split(char)[0]
            
            if sheet_id:
                self.sheet_id_var.set(sheet_id)
                self.error_label.config(text="")
                self.sheet_url_entry.config(bg='white')
        except:
            pass  # Don't show errors while typing
    
    def _browse_file(self):
        """Browse for Excel/CSV file."""
        filetypes = [
            ("Excel files", "*.xlsx *.xls"),
            ("CSV files", "*.csv"),
            ("All files", "*.*")
        ]
        filename = filedialog.askopenfilename(
            title="Select data file",
            filetypes=filetypes
        )
        if filename:
            self.file_path_var.set(filename)
    
    def _browse_credentials(self):
        """Browse for service account JSON file."""
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
        filename = filedialog.askopenfilename(
            title="Select service account JSON",
            filetypes=filetypes
        )
        if filename:
            self.cred_path_var.set(filename)
    
    def _load_existing_config(self):
        """Load and display existing configuration."""
        try:
            cfg = read_user_config()
            source = cfg.get('data_source', cfg.get('source', 'google_sheets'))
            
            if source == 'file':
                self.file_path_var.set(cfg.get('file_path', ''))
            elif source == 'google_sheets':
                sheet_id = cfg.get('spreadsheet_id', '')
                self.sheet_id_var.set(sheet_id)
                self.tab_name_var.set(cfg.get('tab_name', 'Sheet1'))
                self.cred_path_var.set(cfg.get('credentials_path', ''))
                
                # Construct URL from sheet ID
                if sheet_id:
                    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
                    self.sheet_url_var.set(url)
            
            # If there's existing config, show it immediately
            if cfg.get('file_path') or cfg.get('spreadsheet_id'):
                self._select_source(source)
                # Clear any error messages when loading existing config
                self.error_label.config(text="")
                self.status_label.config(text="")
        except:
            pass
    
    def _test_connection(self):
        """Test the configured data source."""
        self.status_label.config(text="Testing connection...", fg='#666')
        self.error_label.config(text="")  # Clear any previous errors
        self.update()
        
        try:
            cfg = self._build_config()
            row_count, error = test_connection(cfg)
            
            if error:
                self.error_label.config(text=f"⚠️ Connection Error: {error}")
                self.status_label.config(text="", fg='#666')
            else:
                self.status_label.config(
                    text=f"✓ Success! Connected and found {row_count} rows.",
                    fg='#28a745'
                )
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
        
        cfg = {
            'data_source': source,
            'source': source
        }
        
        if source == 'file':
            # READ FILE PATH DIRECTLY FROM WIDGET
            file_path = self.file_entry.get().strip()
            if not file_path:
                raise ValueError("Please select a file")
            if not Path(file_path).exists():
                raise ValueError(f"File not found: {file_path}")
            
            cfg['file_path'] = file_path
            cfg['date_col'] = 'B'
            cfg['price_col'] = 'D'
            cfg['details_col'] = 'E'
            
        elif source == 'google_sheets':
            # Get and validate URL - READ DIRECTLY FROM ENTRY WIDGET
            url = self.sheet_url_entry.get().strip()  # READ FROM WIDGET NOT VARIABLE
            
            print(f"\n=== URL VALIDATION DEBUG ===")
            print(f"Original URL: '{url}'")
            print(f"URL Length: {len(url)}")
            print(f"StringVar value: '{self.sheet_url_var.get()}'")  # Debug
            
            if not url:
                raise ValueError("Please enter your Google Sheets URL")
            
            # Clean the URL - remove ALL whitespace
            url = url.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            print(f"After cleaning: '{url}'")
            
            # ULTRA SIMPLE: Just find the Sheet ID
            # Method 1: Look for /d/ANYTHING
            sheet_id = None
            if '/d/' in url:
                parts = url.split('/d/')
                if len(parts) > 1:
                    id_part = parts[1]
                    # Remove everything after /, ?, #
                    for char in ['/', '?', '#']:
                        if char in id_part:
                            id_part = id_part.split(char)[0]
                    sheet_id = id_part
                    print(f"Method 1 - Extracted from /d/: {sheet_id}")
            
            # Method 2: Look for long alphanumeric string
            if not sheet_id:
                match = re.search(r'([a-zA-Z0-9-_]{30,})', url)
                if match:
                    sheet_id = match.group(1)
                    # Clean up
                    for char in ['/', '?', '#', '&']:
                        if char in sheet_id:
                            sheet_id = sheet_id.split(char)[0]
                    print(f"Method 2 - Pattern match: {sheet_id}")
            
            if not sheet_id:
                print(f"FAILED - Could not extract ID")
                raise ValueError("Could not find Sheet ID. Please paste the complete Google Sheets URL.")
            
            print(f"SUCCESS - Final Sheet ID: {sheet_id}")
            print(f"=== VALIDATION SUCCESS ===\n")
            
            self.sheet_id_var.set(sheet_id)
            
            # READ TAB NAME DIRECTLY FROM WIDGET, NOT STRINGVAR
            tab_name = self.tab_name_entry.get().strip() or 'Sheet1'
            print(f"Tab name from widget: '{tab_name}'")
            print(f"Tab name from StringVar: '{self.tab_name_var.get()}'")  # Debug
            
            cred_path = self.cred_path_var.get().strip()
            
            if not cred_path:
                raise ValueError("Please configure Google Sheets credentials first.\nGo to Settings > Configure Credentials in the app menu.")
            if not Path(cred_path).exists():
                raise ValueError(f"Credentials file not found: {cred_path}\nPlease reconfigure credentials in Settings.")
            
            cfg['spreadsheet_id'] = sheet_id
            cfg['tab_name'] = tab_name
            cfg['credentials_path'] = cred_path
            cfg['date_col'] = 'B'
            cfg['price_col'] = 'D'
            cfg['details_col'] = 'E'
        
        return cfg
    
    def _save(self):
        """Save the configuration."""
        try:
            cfg_new = self._build_config()
            
            cfg = read_user_config()
            cfg.update(cfg_new)
            
            write_user_config(cfg)
            
            self.completed = True
            
            # Release grab only if not standalone
            if not getattr(self, 'is_standalone', False):
                try:
                    self.grab_release()
                except:
                    pass
            
            messagebox.showinfo(
                "Success",
                "Configuration saved successfully!\n\nTrackNote is ready to use.",
                parent=self
            )
            
            # Proper cleanup
            try:
                self.destroy()
            except:
                pass
            
        except ValueError as e:
            self.error_label.config(text=f"⚠️ {str(e)}")
            self.status_label.config(text="")
        except Exception as e:
            self.error_label.config(text=f"⚠️ Error: {str(e)}")
            self.status_label.config(text="")
    
    def _cancel(self):
        """Cancel setup."""
        self.completed = False
        self.destroy()
    
    def destroy(self):
        """Override destroy to ensure proper cleanup."""
        # Only release grab if we're not in standalone mode
        if not getattr(self, 'is_standalone', False):
            try:
                self.grab_release()
            except:
                pass
        
        try:
            # Call parent destroy
            super().destroy()
        except:
            pass
    
    def run(self):
        """Run the wizard and wait for completion."""
        self.wait_window()
        return self.completed


def show_setup_wizard(parent=None):
    """Show the setup wizard dialog."""
    if parent is None:
        # Standalone mode - wizard creates its own root
        root = tk.Tk()
        root.withdraw()
        try:
            wizard = SetupWizard(root)
            result = wizard.run()
        finally:
            # Don't call root.quit() in standalone mode!
            # This would interfere with creating a new Tk app later.
            # Just destroy the window - wait_window() already handles the modal loop.
            try:
                root.destroy()
            except:
                pass
        return result
    else:
        # Modal dialog mode - has a parent window
        wizard = SetupWizard(parent)
        return wizard.run()


if __name__ == "__main__":
    print("Starting setup wizard...")
    completed = show_setup_wizard()
    print(f"Setup completed: {completed}")