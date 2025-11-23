import tkinter as tk
from tkinter import ttk

root = tk.Tk()
style = ttk.Style()

print(f"Current Theme: {style.theme_use()}")
print(f"Available Themes: {style.theme_names()}")

try:
    style.theme_use('clam')
    print("Switched to 'clam'")
except:
    print("Could not switch to 'clam'")

print("Treeview.Item Layout:")
print(style.layout("Treeview.Item"))

print("Treeview.Item Options:")
print(style.element_options("Treeview.Item"))
