# ui/main_window.py

import tkinter as tk
from tkinter import ttk

from ui.tabs.collection_tab import CollectionTab
from ui.tabs.preprocess_tab  import PreprocessTab
from ui.tabs.annotate_tab    import AnnotateTab
from ui.tabs.training_tab    import TrainingTab
from ui.tabs.analysis_tab    import AnalysisTab

from config import WINDOW_SIZE


class MainWindow:

    def __init__(self, root, engines):
        self.root    = root
        self.engines = engines

        self.root.title("Detection Pipeline Pro")
        self.root.geometry(WINDOW_SIZE)

        # ── Notebook ────────────────────────────────────────────────────
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")

        # Tab 1 — Collection
        # Step 3: pass capture_controller in from engines
        self.tab1 = CollectionTab(
            self.notebook,
            shared_data         = self.engines["data"],
            camera_service      = self.engines["camera"],
            capture_controller  = self.engines["capture"],
        )
        self.notebook.add(self.tab1, text="1. Collection")

        # Remaining tabs (stubs until you implement them)
        self.tab2 = PreprocessTab(self.notebook)
        self.notebook.add(self.tab2, text="2. Preprocess")

        self.tab3 = AnnotateTab(self.notebook)
        self.notebook.add(self.tab3, text="3. Annotate")

        self.tab4 = TrainingTab(self.notebook)
        self.notebook.add(self.tab4, text="4. Training")

        self.tab5 = AnalysisTab(self.notebook)
        self.notebook.add(self.tab5, text="5. Analysis")

        # Step 2: on_closing lives only here — no duplicate in main.py
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ------------------------------------------------------------------
    def _on_closing(self):
        """Clean up the camera before destroying the window."""
        camera = self.engines["camera"]
        if camera.is_streaming:     # Step 2: use service flag
            camera.stop()
        self.root.destroy()