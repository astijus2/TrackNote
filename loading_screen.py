#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Loading screen for TrackNote
Fixed version - no animation errors
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

import tkinter as tk
from tkinter import ttk
import threading

class LoadingScreen:
    """Simple loading screen for TrackNote"""
    
    def __init__(self, title="TrackNote"):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        
        # Center window
        self.center_window()
        
        # Create UI
        self.create_ui()
        
        # Threading
        self.lock = threading.Lock()
        self._closed = False
        
    def center_window(self):
        """Center window on screen"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.root.winfo_screenheight() // 2) - (400 // 2)
        self.root.geometry(f"500x400+{x}+{y}")
    
    def create_ui(self):
        """Create the UI"""
        # Background
        self.root.configure(bg="#1a1a1a")
        
        # Main frame
        main_frame = tk.Frame(self.root, bg="#1a1a1a")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=40)
        
        # Title
        title = tk.Label(
            main_frame,
            text="TrackNote",
            font=("Helvetica", 36, "bold"),
            bg="#1a1a1a",
            fg="#ffffff"
        )
        title.pack(pady=(20, 10))
        
        # Version
        version = tk.Label(
            main_frame,
            text="v1.0",
            font=("Helvetica", 11),
            bg="#1a1a1a",
            fg="#888888"
        )
        version.pack(pady=(0, 30))
        
        # Status
        self.status_label = tk.Label(
            main_frame,
            text="Loading...",
            font=("Helvetica", 13),
            bg="#1a1a1a",
            fg="#ffffff"
        )
        self.status_label.pack(pady=(0, 20))
        
        # Progress bar - FIXED: Use determinate mode to avoid animation issues
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "TProgressbar",
            troughcolor='#333333',
            background='#4a9eff',
            bordercolor='#1a1a1a'
        )
        
        self.progress = ttk.Progressbar(
            main_frame,
            mode='determinate',  # Changed from indeterminate
            length=400,
            maximum=100
        )
        self.progress.pack(pady=(0, 20))
        self.progress['value'] = 50  # Set to middle
        
        # Detail
        self.detail_label = tk.Label(
            main_frame,
            text="",
            font=("Courier", 10),
            bg="#1a1a1a",
            fg="#888888",
            wraplength=400
        )
        self.detail_label.pack()
        
        # Step label
        self.step_label = tk.Label(
            main_frame,
            text="",
            font=("Helvetica", 9),
            bg="#1a1a1a",
            fg="#666666"
        )
        self.step_label.pack(pady=(10, 0))
    
    def update_status(self, message, detail="", progress=None, step=""):
        """Update the status message"""
        if self._closed:
            return
            
        def update():
            try:
                if not self._closed and self.root.winfo_exists():
                    self.status_label.config(text=message)
                    self.detail_label.config(text=detail)
                    if step:
                        self.step_label.config(text=step)
                    if progress is not None:
                        self.progress['value'] = progress
                    self.root.update()
            except Exception:
                pass  # Ignore tkinter errors
        
        try:
            if self.root.winfo_exists():
                self.root.after(0, update)
        except Exception:
            pass  # Ignore if window is closing
    
    def close(self):
        """Close the loading screen"""
        self._closed = True
        if self.root.winfo_exists():
            try:
                self.root.after(100, self._safe_destroy)
            except:
                pass
    
    def show_error(self, title, message):
        """Show error and close"""
        try:
            self.update_status(f"❌ {title}", message, 100, "Error")
            self.root.after(3000, self.close)
        except Exception:
            print(f"ERROR: {title} - {message}")
            self.close()
    
    def show_success(self, message):
        """Show success and close"""
        try:
            self.update_status(f"✅ {message}", "Starting application...", 100, "Complete")
            self.root.after(1500, self.close)
        except Exception:
            print(f"SUCCESS: {message}")
            self.close()
    
    def _safe_destroy(self):
        """Safely destroy the window"""
        try:
            if self.root.winfo_exists():
                self.root.quit()
                self.root.destroy()
        except:
            pass
    
    def show(self):
        """Show the loading screen"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()
        except Exception as e:
            print(f"Loading screen error: {e}")
            self.close()


# Alias for compatibility
SetupLoadingScreen = LoadingScreen


if __name__ == "__main__":
    # Test the loading screen
    import time
    
    screen = LoadingScreen()
    
    def test():
        time.sleep(1)
        screen.update_status("Testing...", "Loading components", 30)
        time.sleep(2)
        screen.update_status("Almost ready...", "Finalizing setup", 70)
        time.sleep(2)
        screen.update_status("Complete!", "Starting application", 100)
        time.sleep(1)
        screen.close()
    
    thread = threading.Thread(target=test, daemon=True)
    thread.start()
    
    screen.show()