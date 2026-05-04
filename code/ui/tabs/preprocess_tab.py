import tkinter as tk
from tkinter import ttk

class PreprocessTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        label = tk.Label(self, text="Preprocess")
        label.pack(expand=True)