"""
GUI dialog for Firebase configuration.
Can be called from the app's Help menu.
"""

import tkinter as tk
from tkinter import messagebox
from user_data import read_user_config, write_user_config


class FirebaseSetupDialog(tk.Toplevel):
    """Simple dialog to configure Firebase sync."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Firebase Sync Setup")
        self.geometry("500x400")
        self.resizable(False, False)
        
        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (250)
        y = (self.winfo_screenheight() // 2) - (200)
        self.geometry(f"500x400+{x}+{y}")
        
        self.transient(parent)
        self.grab_set()
        
        self.completed = False
        self._create_widgets()
        
        # Load existing config if any
        self._load_existing_config()
        
    def _create_widgets(self):
        """Create the dialog UI."""
        # Header
        header = tk.Frame(self, bg='#f0f0f0', height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="🔥 Firebase Sync Configuration",
                font=('', 16, 'bold'), bg='#f0f0f0').pack(pady=15)
        
        # Content
        content = tk.Frame(self, bg='white')
        content.pack(fill='both', expand=True, padx=30, pady=20)
        
        # Info text
        info = tk.Label(content, 
                       text="Sync status and notes across multiple computers.\n"
                            "All computers must use the SAME Firebase configuration.",
                       bg='white', fg='#666', justify='left', wraplength=420)
        info.pack(anchor='w', pady=(0, 20))
        
        # Database URL
        tk.Label(content, text="Firebase Database URL:",
                bg='white', fg='#333', font=('', 10, 'bold')).pack(anchor='w')
        tk.Label(content, text="Example: https://tracknote-app-default-rtdb.firebaseio.com",
                bg='white', fg='#999', font=('', 8)).pack(anchor='w', pady=(0, 5))
        
        self.url_var = tk.StringVar()
        url_entry = tk.Entry(content, textvariable=self.url_var,
                            font=('', 10), bg='white', relief='solid', bd=1)
        url_entry.pack(fill='x', ipady=6, pady=(0, 15))
        
        # Project ID
        tk.Label(content, text="Firebase Project ID:",
                bg='white', fg='#333', font=('', 10, 'bold')).pack(anchor='w')
        tk.Label(content, text="Example: tracknote-app",
                bg='white', fg='#999', font=('', 8)).pack(anchor='w', pady=(0, 5))
        
        self.project_var = tk.StringVar()
        project_entry = tk.Entry(content, textvariable=self.project_var,
                                font=('', 10), bg='white', relief='solid', bd=1)
        project_entry.pack(fill='x', ipady=6, pady=(0, 15))
        
        # Status label
        self.status_label = tk.Label(content, text="",
                                     bg='white', font=('', 9))
        self.status_label.pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self, bg='#f0f0f0', height=70)
        btn_frame.pack(fill='x', side='bottom')
        btn_frame.pack_propagate(False)
        
        tk.Button(btn_frame, text="Cancel", 
                 command=self._cancel,
                 bg='#dddddd', fg='#000000',
                 font=('', 10), padx=20, pady=8).pack(side='left', padx=20, pady=15)
        
        tk.Button(btn_frame, text="Test Connection",
                 command=self._test_connection,
                 bg='#28a745', fg='#ffffff',
                 font=('', 10, 'bold'), padx=20, pady=8).pack(side='right', padx=(0, 10), pady=15)
        
        tk.Button(btn_frame, text="Save & Enable",
                 command=self._save,
                 bg='#007ACC', fg='#ffffff',
                 font=('', 10, 'bold'), padx=20, pady=8).pack(side='right', padx=10, pady=15)
        
    def _load_existing_config(self):
        """Load and display existing Firebase config if present."""
        try:
            cfg = read_user_config()
            fb = cfg.get('firebase_config', {})
            
            if fb:
                self.url_var.set(fb.get('database_url', ''))
                self.project_var.set(fb.get('project_id', ''))
                self.status_label.configure(text="✅ Firebase is currently configured",
                                          fg='#28a745')
        except:
            pass
    
    def _test_connection(self):
        """Test the Firebase connection."""
        url = self.url_var.get().strip()
        project = self.project_var.get().strip()
        
        if not url or not project:
            self.status_label.configure(text="❌ Please fill in both fields", fg='red')
            return
        
        # Clean URL
        url = url.rstrip('/')
        
        self.status_label.configure(text="Testing connection...", fg='#666')
        self.update()
        
        try:
            from firebase_sync import FirebaseSync
            import time
            
            # Try to connect
            sync = FirebaseSync(url, project)
            
            if sync.is_connected():
                # Try a test write/read
                test_key = f"_test_{int(time.time())}"
                sync.set_status(test_key, 1, 0)
                result = sync.get_all_status()
                
                if test_key in result:
                    sync.clear_status(test_key)
                    self.status_label.configure(
                        text="✅ Connection successful! Read/write working.",
                        fg='#28a745'
                    )
                else:
                    self.status_label.configure(
                        text="⚠️ Connected but read/write failed. Check security rules.",
                        fg='#ff6600'
                    )
            else:
                self.status_label.configure(
                    text="❌ Connection failed. Check URL and project ID.",
                    fg='red'
                )
                
        except Exception as e:
            self.status_label.configure(
                text=f"❌ Error: {str(e)[:50]}",
                fg='red'
            )
    
    def _save(self):
        """Save the Firebase configuration."""
        url = self.url_var.get().strip()
        project = self.project_var.get().strip()
        
        if not url or not project:
            messagebox.showerror("Error", "Please fill in both fields")
            return
        
        # Clean URL
        url = url.rstrip('/')
        
        try:
            cfg = read_user_config()
            cfg['firebase_config'] = {
                'database_url': url,
                'project_id': project
            }
            write_user_config(cfg)
            
            self.completed = True
            
            messagebox.showinfo(
                "Success",
                "Firebase sync configured!\n\n"
                "Please restart TrackNote for changes to take effect.\n\n"
                "Remember: Use the SAME configuration on all computers."
            )
            
            self.destroy()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n\n{e}")
    
    def _cancel(self):
        """Cancel and close dialog."""
        self.destroy()
    
    def run(self):
        """Run the dialog and wait for completion."""
        self.wait_window()
        return self.completed


def show_firebase_setup(parent=None):
    """Show Firebase setup dialog."""
    dialog = FirebaseSetupDialog(parent)
    return dialog.run()