import tkinter as tk
from tkinter import ttk

class TrainingTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        label = tk.Label(self, text="Traning")
        label.pack(expand=True)