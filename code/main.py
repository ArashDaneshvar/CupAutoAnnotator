# main.py

import tkinter as tk

from core.data_manager        import DataManager
from core.realsense_service   import RealsenseService
from core.capture_controller  import CaptureController   # Step 3
from ui.main_window           import MainWindow


def main():
    root = tk.Tk()
    root.title("YOLO Data Engine")

    # ── Build the core services ─────────────────────────────────────────
    shared_data    = DataManager()
    camera_service = RealsenseService()          # uses defaults from config.py

    # Step 3: CaptureController wires camera + data together
    capture_ctrl   = CaptureController(
        camera_service = camera_service,
        data_manager   = shared_data,
        # on_saved callback is set later by CollectionTab
    )

    engines = {
        "data":    shared_data,
        "camera":  camera_service,
        "capture": capture_ctrl,       # Step 3: pass it through
    }

    # ── Build the UI ────────────────────────────────────────────────────
    # on_closing is handled inside MainWindow — no duplicate here (Step 2)
    MainWindow(root, engines)

    root.mainloop()


if __name__ == "__main__":
    main()