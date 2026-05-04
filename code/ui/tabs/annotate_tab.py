import tkinter as tk
from tkinter import ttk


class AnnotateTab(ttk.Frame):

    def __init__(self, parent):
        super().__init__(parent)
        label = tk.Label(self, text="Annotate")
        label.pack(expand=True)