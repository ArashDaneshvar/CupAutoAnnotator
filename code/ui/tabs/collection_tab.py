# ui/tabs/collection_tab.py

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2

from config import (
    PREVIEW_WIDTH, PREVIEW_HEIGHT,
    FRAME_INTERVAL_MS, DEFAULT_CAPTURE_INTERVAL
)


class CollectionTab(ttk.Frame):

    def __init__(self, parent, shared_data, camera_service, capture_controller):
        super().__init__(parent)
        self.shared_data         = shared_data
        self.camera              = camera_service
        self.capture_controller  = capture_controller   # Step 3

        # Wire up the callback so the controller can update our status bar
        self.capture_controller.on_saved = self._on_frame_saved

        self.auto_mode_var = tk.BooleanVar(value=False)

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------
    def _setup_ui(self):
        # ── Left panel ──────────────────────────────────────────────────
        self.controls_frame = ttk.Frame(self)
        self.controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)

        # ttk.Label(self.controls_frame, text="Control Panel",
        #           font=("Arial", 12, "bold")).pack(pady=10)
        # ttk.Label(self.controls_frame, text="Storage Settings",
        #           font=("Arial", 10, "bold")).pack(pady=5)

        self.path_label = ttk.Label(self.controls_frame,
                                    text="Path: Not Selected",
                                    foreground="blue")
        self.path_label.pack(pady=2)

        ttk.Button(self.controls_frame, text="Browse Folder",
                   command=self.browse_folder).pack(fill=tk.X, pady=5)

        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill="x", pady=10)

        ttk.Button(self.controls_frame, text="✨ New Project Folder",
                   command=self.on_create_project_click).pack(fill=tk.X, pady=2)

        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill="x", pady=10)

        # Camera toggle
        self.start_btn = ttk.Button(self.controls_frame,
                                    text="Start Camera",
                                    command=self.toggle_camera)
        self.start_btn.pack(fill=tk.X, pady=5)

        # Manual capture
        self.snap_btn = ttk.Button(self.controls_frame,
                                   text="Manual Capture (S)",
                                   command=self.capture_manual,
                                   state="disabled")
        self.snap_btn.pack(fill=tk.X, pady=5)

        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill="x", pady=15)

        # ── Auto-capture section ────────────────────────────────────────
        ttk.Label(self.controls_frame, text="Automatic Capture",
                  font=("Arial", 10, "bold")).pack(pady=5)

        self.auto_check = ttk.Checkbutton(self.controls_frame,
                                          text="Enable Auto Mode",
                                          variable=self.auto_mode_var)
        self.auto_check.pack(pady=5)

        ttk.Label(self.controls_frame, text="Interval (seconds):").pack()
        self.interval_entry = ttk.Entry(self.controls_frame, width=10)
        self.interval_entry.insert(0, str(DEFAULT_CAPTURE_INTERVAL))
        self.interval_entry.pack(pady=5)

        # ── Frame counter ───────────────────────────────────────────────
        ttk.Separator(self.controls_frame, orient="horizontal").pack(fill="x", pady=10)
        self.counter_label = ttk.Label(self.controls_frame,
                                       text="Saved: 0 frames",
                                       font=("Arial", 10))
        self.counter_label.pack(pady=5)

        # ── Right panel — video feed ────────────────────────────────────
        self.display_frame = ttk.Frame(self)
        self.display_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.video_label = ttk.Label(self.display_frame, text="Camera Offline")
        self.video_label.pack(expand=True)

        # Step 6 — status bar at the bottom of this tab
        self.status_var = tk.StringVar(value="Ready")
        self.status_bar = ttk.Label(self,
                                    textvariable=self.status_var,
                                    relief=tk.SUNKEN,
                                    anchor="w",
                                    padding=(6, 2))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------
    # Camera control
    # ------------------------------------------------------------------
    def toggle_camera(self):
        if not self.camera.is_streaming:   # Step 2: check the service flag
            try:
                self.camera.start()
                self.start_btn.config(text="Stop Camera")
                self.snap_btn.config(state="normal")
                self.set_status("Camera started.")
                self.update_frame()
            except Exception as e:
                self.set_status(f"Error: could not start camera — {e}", error=True)
        else:
            self.camera.stop()
            self.start_btn.config(text="Start Camera")
            self.snap_btn.config(state="disabled")
            self.video_label.config(image="", text="Camera Offline")
            self.set_status("Camera stopped.")

    # ------------------------------------------------------------------
    # Step 1 — fixed update_frame
    # ------------------------------------------------------------------
    def update_frame(self):
        if not self.camera.is_streaming:
            return

        frames = self.camera.get_frames()

        if frames is not None:
            # Convert BGR → RGB and display
            color_rgb = cv2.cvtColor(frames["color"], cv2.COLOR_BGR2RGB)
            img       = Image.fromarray(color_rgb)
            img       = img.resize((PREVIEW_WIDTH, PREVIEW_HEIGHT))
            self.photo = ImageTk.PhotoImage(image=img)   # keep reference!
            self.video_label.config(image=self.photo, text="")

            # Let the controller cache the latest frames
            self.capture_controller.update_frames(frames)

            # Auto-capture tick
            if self.auto_mode_var.get():
                try:
                    interval = float(self.interval_entry.get())
                except ValueError:
                    interval = DEFAULT_CAPTURE_INTERVAL
                self.capture_controller.auto_capture_tick(interval)

        # Schedule next frame
        self.after(FRAME_INTERVAL_MS, self.update_frame)

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def capture_manual(self):
        success = self.capture_controller.capture()
        if not success:
            self.set_status("Capture failed — is a folder selected?", error=True)

    def _on_frame_saved(self, filename: str, count: int):
        """Callback fired by CaptureController after every successful save."""
        self.counter_label.config(text=f"Saved: {count} frames")
        self.set_status(f"Saved → {filename}")

    # ------------------------------------------------------------------
    # Folder management
    # ------------------------------------------------------------------
    def browse_folder(self):
        from tkinter import filedialog
        selected_path = filedialog.askdirectory()
        if selected_path:
            self.shared_data.set_folder_path(selected_path)
            self._update_path_label(selected_path)
            self.capture_controller.reset_count()
            self.set_status(f"Folder set: {selected_path}")

    def on_create_project_click(self):
        # from tkinter import simpledialog, messagebox
        # import os

        # project_name = simpledialog.askstring("New Project", "Enter Project Name:")
        # if not project_name:
        #     return

        # import config
        # full_path = os.path.join(os.getcwd(), config.DEFAULT_DATASET_FOLDER, project_name)

        # try:
        #     # Actually create the subfolders this time
        #     for sub in ("color", "depth", "ir"):
        #         os.makedirs(os.path.join(full_path, sub), exist_ok=True)

        #     self.shared_data.set_folder_path(full_path)
        #     self._update_path_label(project_name, ok=True)
        #     self.capture_controller.reset_count()

        #     messagebox.showinfo(
        #         "Success",
        #         f"Project '{project_name}' created!\nSubfolders (color, depth, ir) are ready."
        #     )
        #     self.set_status(f"New project: {project_name}")

        # except Exception as e:
        #     messagebox.showerror("Error", f"Could not create folders: {e}")
        #     self.set_status(f"Error creating project: {e}", error=True)


        from tkinter import simpledialog, messagebox

        project_name = simpledialog.askstring("New Project", "Enter Project Name:")
        if not project_name:
            return

        try:
            full_path = self.shared_data.create_new_project(project_name)

            self._update_path_label(project_name, ok=True)
            self.capture_controller.reset_count()
            self.set_status(f"New project: {project_name}")
            
            messagebox.showinfo("Success", f"Project '{project_name}' is ready!")

        except Exception as e:
            messagebox.showerror("Error", f"Could not create project: {e}")
            self.set_status("Error creating project", error=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _update_path_label(self, path: str, ok: bool = False):
        display = ("..." + path[-20:]) if len(path) > 20 else path
        color   = "green" if ok else "blue"
        self.path_label.config(text=f"Path: {display}", foreground=color)

    def set_status(self, message: str, error: bool = False):
        """Update the status bar. Pass error=True to highlight in red."""
        self.status_var.set(message)
        self.status_bar.config(foreground="red" if error else "black")