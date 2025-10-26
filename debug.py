#!/usr/bin/env python3
"""
Simple Tkinter Window Test
If this window doesn't appear, you have a Tkinter/Python issue, not a TrackNote issue.
"""
import tkinter as tk
import platform

print("="*60)
print("Tkinter Window Test")
print("="*60)
print(f"Python version: {platform.python_version()}")
print(f"Platform: {platform.system()}")
print()

root = tk.Tk()
root.title("Tkinter Test Window")
root.geometry("500x400")
root.configure(bg='white')

# Header
header = tk.Label(
    root, 
    text="Tkinter Test Window",
    font=("Arial", 20, "bold"),
    bg='#2C5F8D',
    fg='white',
    pady=20
)
header.pack(fill='x')

# Content
frame = tk.Frame(root, bg='white')
frame.pack(fill='both', expand=True, padx=30, pady=30)

label1 = tk.Label(
    frame,
    text="✅ If you can see this window, Tkinter works!",
    font=("Arial", 14),
    bg='white',
    fg='#28a745'
)
label1.pack(pady=20)

label2 = tk.Label(
    frame,
    text="This confirms:\n"
         "• Python has Tkinter support\n"
         "• Windows can be created and displayed\n"
         "• The event loop functions properly",
    font=("Arial", 12),
    bg='white',
    fg='#333',
    justify='left'
)
label2.pack(pady=20)

label3 = tk.Label(
    frame,
    text="Close this window to continue testing TrackNote.",
    font=("Arial", 11, "italic"),
    bg='white',
    fg='#666'
)
label3.pack(pady=20)

# Close button
def close_window():
    print("✓ Window closed by user")
    root.destroy()

btn = tk.Button(
    frame,
    text="Close Window",
    command=close_window,
    bg='#2C5F8D',
    fg='white',
    font=("Arial", 12, "bold"),
    padx=30,
    pady=10,
    cursor='hand2'
)
btn.pack(pady=20)

# Terminal output
print("Test window created...")
print(f"Window state: {root.state()}")
print(f"Window geometry: {root.geometry()}")
print()
print("👀 DO YOU SEE A WINDOW ON YOUR SCREEN?")
print()
print("If YES:")
print("  ✓ Tkinter works properly")
print("  ✓ Issue is specific to TrackNote")
print("  ✓ Proceed with TrackNote debugging")
print()
print("If NO:")
print("  ✗ Basic Tkinter has issues")
print("  ✗ Need to fix Python/Tkinter installation first")
print("  ✗ Try: brew reinstall python-tk")
print()
print("Waiting for window to be closed...")
print("="*60)

try:
    root.mainloop()
    print()
    print("="*60)
    print("✓ Window test completed successfully")
    print("✓ Tkinter event loop worked properly")
    print("="*60)
except Exception as e:
    print()
    print("="*60)
    print("✗ ERROR in mainloop:")
    print(f"  {e}")
    print("="*60)
    import traceback
    traceback.print_exc()