import tkinter as tk
from tkinter import ttk


class AnalysisTab(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        label = tk.Label(self, text="Analysis")
        label.pack(expand=True)