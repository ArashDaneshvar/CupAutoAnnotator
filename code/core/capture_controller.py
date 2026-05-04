# core/capture_controller.py

import time
from config import DEFAULT_CAPTURE_INTERVAL, DEFAULT_DATASET_FOLDER


class CaptureController:
    """
    Step 3 — owns ALL capture logic so CollectionTab only handles UI.

    Responsibilities:
      - manual capture
      - auto-capture timing
      - counting saved frames
      - reporting results back via a callback
    """

    def __init__(self, camera_service, data_manager, on_saved=None):
        """
        Args:
            camera_service  : RealsenseService instance
            data_manager    : DataManager instance
            on_saved        : optional callback(filename, save_count)
                              called after every successful save
        """
        self.camera       = camera_service
        self.data_manager = data_manager
        self.on_saved     = on_saved   # UI can hook in here for status updates

        self.save_count      = 0
        self.last_save_time  = 0.0
        self.last_frames     = None

    # ------------------------------------------------------------------
    # Called every UI tick (from update_frame) to cache the latest frames
    # ------------------------------------------------------------------
    def update_frames(self, frames):
        """Store the most recent frame set so capture() can use them."""
        self.last_frames = frames

    # ------------------------------------------------------------------
    # Manual capture
    # ------------------------------------------------------------------
    def capture(self):
        """Save the last captured frame set immediately."""
        if self.last_frames is None:
            print("CaptureController: no frames available yet.")
            return False

        base_path = self.data_manager.get_folder_path() or DEFAULT_DATASET_FOLDER
        filename  = self.camera.save_data(self.last_frames, base_path, self.save_count)

        if filename:
            self.save_count += 1
            print(f"Saved [{self.save_count}] → {base_path}/{filename}")

            # Notify UI (status bar, counter label, etc.)
            if self.on_saved:
                self.on_saved(filename, self.save_count)

            return True
        else:
            print("CaptureController: save failed.")
            return False

    # ------------------------------------------------------------------
    # Auto-capture tick — call this every UI frame
    # ------------------------------------------------------------------
    def auto_capture_tick(self, interval: float = DEFAULT_CAPTURE_INTERVAL):
        """
        Should be called on every UI update when auto mode is enabled.
        Saves a frame only when enough time has elapsed since the last save.
        """
        now = time.time()
        if now - self.last_save_time >= interval:
            if self.capture():
                self.last_save_time = now

    # ------------------------------------------------------------------
    def reset_count(self):
        """Reset the save counter (e.g. when a new project is created)."""
        self.save_count = 0
        self.last_save_time = 0.0