import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import threading
import queue
import random
import math

# Matplotlib embedded — used for live training charts in the Training tab.
# Falls back gracefully if not installed.
try:
    import matplotlib
    matplotlib.use("TkAgg")          # Use the Tkinter backend so figures embed in the window
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

# Ultralytics YOLO — required for prediction and training.
# The app still runs without it; YOLO features are simply disabled.
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# =============================================================================
# CONSTANTS
# =============================================================================

# Image file extensions that the app will recognise when scanning a folder.
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

# One hex color per YOLO class index (0-20).
# The index in this list IS the class id written to .txt annotation files.
COLOR_LIST = [
    "#d3d3d3",  # 0  gray
    "#ff0000",  # 1  red
    "#00ff00",  # 2  green
    "#0000ff",  # 3  blue
    "#ffff00",  # 4  yellow
    "#ff8800",  # 5  orange
    "#8800ff",  # 6  purple
    "#ff69b4",  # 7  pink
    "#8b4513",  # 8  brown
    "#000000",  # 9  black
    "#ffffff",  # 10 white
    "#00ffff",  # 11 cyan
    "#ff00ff",  # 12 magenta
    "#32ff32",  # 13 lime
    "#008080",  # 14 teal
    "#000080",  # 15 navy
    "#808000",  # 16 olive
    "#800000",  # 17 maroon
    "#ffd700",  # 18 gold
    "#c0c0c0",  # 19 silver
    "#ff7f50",  # 20 coral
]

# Maximum canvas display size in pixels.
# Images are scaled down to fit inside this box while keeping aspect ratio.
MAX_CANVAS_W = 1100
MAX_CANVAS_H = 750

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def detect_box_zone(xm, ym, x1, y1, x2, y2, tol=8):
    """
    Given a mouse position (xm, ym) and a bounding box (x1,y1,x2,y2),
    return a 4-tuple mask (left, top, right, bottom) indicating which
    edges/corners are within `tol` pixels of the cursor.

    Possible return values:
      (1,1,0,0) top-left corner     (0,1,1,0) top-right corner
      (1,0,0,1) bottom-left corner  (0,0,1,1) bottom-right corner
      (1,0,0,0) left edge           (0,0,1,0) right edge
      (0,1,0,0) top edge            (0,0,0,1) bottom edge
      (1,1,1,1) interior → translate the whole box
      None      cursor is outside the box entirely
    """
    if abs(xm - x1) <= tol and abs(ym - y1) <= tol: return (1,1,0,0)
    elif abs(xm - x2) <= tol and abs(ym - y1) <= tol: return (0,1,1,0)
    elif abs(xm - x1) <= tol and abs(ym - y2) <= tol: return (1,0,0,1)
    elif abs(xm - x2) <= tol and abs(ym - y2) <= tol: return (0,0,1,1)
    elif abs(xm - x1) <= tol and y1 <= ym <= y2:      return (1,0,0,0)
    elif abs(xm - x2) <= tol and y1 <= ym <= y2:      return (0,0,1,0)
    elif abs(ym - y1) <= tol and x1 <= xm <= x2:      return (0,1,0,0)
    elif abs(ym - y2) <= tol and x1 <= xm <= x2:      return (0,0,0,1)
    elif x1 < xm < x2 and y1 < ym < y2:              return (1,1,1,1)
    return None

def adjust_coords(xm, ym, x1, y1):
    """
    Reorder two points so that the first is always the top-left and the
    second is always the bottom-right. This prevents rectangles with
    negative width/height when the user drags upward or leftward.
    """
    return min(xm, x1), min(ym, y1), max(xm, x1), max(ym, y1)

def normalize_coords(x1, y1, x2, y2, w, h):
    """
    Convert absolute pixel coordinates to relative [0,1] values by
    dividing by the image display width (w) and height (h).
    Used before writing coordinates to YOLO .txt files.
    """
    return x1/w, y1/h, x2/w, y2/h

def denormalize_coords(x1, y1, x2, y2, w, h):
    """
    Inverse of normalize_coords: multiply relative [0,1] values by
    the image display width (w) and height (h) to get pixel coordinates.
    Used when loading YOLO .txt files back onto the canvas.
    """
    return x1*w, y1*h, x2*w, y2*h

def convert_into_yolo(c, x1, y1, x2, y2):
    """
    Convert a bounding box from corner format (x1,y1,x2,y2) — all
    normalised [0,1] — to the YOLO label format:
      <class> <xc> <yc> <width> <height>
    Returns the formatted string ready to write to a .txt file.
    """
    xc = (x2 + x1) / 2   # horizontal center
    yc = (y2 + y1) / 2   # vertical center
    w  = x2 - x1          # box width
    h  = y2 - y1          # box height
    return f"{c:d} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"

def from_yolo_into_coord(values_string):
    """
    Parse one line of a YOLO .txt label file and convert it back to
    corner format (x1,y1,x2,y2) in normalised [0,1] space.

    Returns (class, x1, y1, x2, y2) or None if the line is malformed.
    """
    values = values_string.strip().split()
    if len(values) < 5:
        return None
    c  = int(values[0])
    xc, yc, w, h = float(values[1]), float(values[2]), float(values[3]), float(values[4])
    x1 = xc - w/2   # left edge
    x2 = xc + w/2   # right edge
    y1 = yc - h/2   # top edge
    y2 = yc + h/2   # bottom edge
    return c, x1, y1, x2, y2

def annotation_file_for(img_path):
    """
    Given an image path like '/data/img.jpg', return the corresponding
    YOLO label path '/data/img.txt' by replacing the extension.
    """
    base, _ = os.path.splitext(img_path)
    return base + ".txt"

def hex_to_rgba(hex_color, alpha):
    """
    Convert a CSS hex color string (e.g. '#ff0000') and an integer alpha
    value (0 = fully transparent, 255 = fully opaque) into an (R,G,B,A)
    tuple suitable for PIL Image.new('RGBA', ...).
    """
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)

def has_annotations(img_path):
    """
    Return True if the .txt label file corresponding to img_path exists
    AND contains at least one non-empty line. Used to filter out images
    with no annotations when building the training dataset.
    """
    txt = annotation_file_for(img_path)
    if not os.path.exists(txt):
        return False
    with open(txt) as f:
        return any(line.strip() for line in f)

def make_symlink(src, dst):
    """
    Create a symbolic link at `dst` pointing to `src`.
    If a file or broken link already exists at `dst`, it is removed first.
    On Windows systems where symlinks are restricted, falls back to a
    hard copy (shutil.copy2) so the code still works cross-platform.
    """
    if os.path.exists(dst) or os.path.islink(dst):
        os.remove(dst)
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError):
        import shutil
        shutil.copy2(src, dst)

# =============================================================================
# ANNOTATION CANVAS
# =============================================================================

class CanvasAnnotation(tk.Canvas):
    """
    A specialised tkinter Canvas that handles drawing, editing, and
    saving/loading YOLO bounding-box annotations over a background image.

    Interaction model:
      - Left-click on empty area  → start drawing a new box
      - Left-click again          → finish the box
      - Left-click on a box       → enter move/resize mode
      - Left-click again          → confirm the edit
      - Right-click               → cancel current operation OR delete a box
      - Double-click on a box     → change its class to the currently selected color
      - Mouse move                → update crosshair axes and live-preview the box
    """

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        # ── State machine ──────────────────────────────────────────────────
        # "idle"   : no operation in progress
        # "create" : user is drawing a new rectangle
        # "move"   : user is moving or resizing an existing rectangle
        self.mode = "idle"

        # ── Crosshair axes ─────────────────────────────────────────────────
        self.axis_x = None   # canvas id of the horizontal red line
        self.axis_y = None   # canvas id of the vertical red line

        # ── Creation state ─────────────────────────────────────────────────
        self.temp_rect   = None  # canvas id of the in-progress rectangle
        self.start_point = None  # (x, y) where the user first clicked

        # ── Move/resize state ──────────────────────────────────────────────
        self.selected_rect  = None  # canvas id of the rectangle being edited
                                    # (hidden during editing)
        self.start_rect     = None  # (x1,y1,x2,y2) snapshot of the rect before editing
        self.anchor_point   = None  # fixed corner/edge during a resize operation;
                                    # None on the unconstrained axis
        self.mov_direction  = None  # 4-tuple mask from detect_box_zone indicating
                                    # which edges to move; (1,1,1,1) means translate all
        self.temp_click     = None  # last mouse position, used to compute drag delta

        # ── Background image ───────────────────────────────────────────────
        self.img_path          = None  # absolute path to the currently displayed image
        self.img_ref           = None  # ImageTk.PhotoImage reference (must be kept alive
                                       # to prevent garbage collection by Python/Tk)
        self.background_img_id = None  # canvas id of the background image item

        # Padding (in pixels) added around the image so boxes near the edge
        # are easier to click. The image is drawn at (pad, pad) inside the canvas.
        self.starting_point_img = (20, 20)

        # Display dimensions of the scaled image (NOT the canvas).
        # Used as the coordinate space for normalisation/denormalisation.
        self.img_draw_w = 1
        self.img_draw_h = 1

        # ── Annotation tracking ────────────────────────────────────────────
        # List of canvas ids for all confirmed annotation rectangles.
        self.annotation_list_id = []

        # Dict mapping each rectangle id to its semi-transparent fill overlay:
        #   { rect_id : (overlay_image_id, PhotoImage) }
        # The PhotoImage must be kept here to prevent garbage collection.
        self.overlay_refs = {}

        # ── Style / color ──────────────────────────────────────────────────
        self.id_color        = 0       # index into COLOR_LIST for the active class
        self.default_outline = "black" # border color for all annotation rectangles
        self.fill_alpha      = 80      # opacity of the semi-transparent fill (0-255)

        # ── Event bindings ─────────────────────────────────────────────────
        self.bind("<Enter>",           self.on_enter)
        self.bind("<Leave>",           self.on_exit)
        self.bind("<Button-1>",        self.on_left_click)
        self.bind("<Button-3>",        self.on_right_click)
        self.bind("<Motion>",          self.on_move)
        self.bind("<Double-Button-1>", self.on_double_click)

    # ------------------------------------------------------------------ reset

    def reset_state(self):
        """
        Abort any in-progress operation and return to 'idle' mode.
        Deletes the temporary preview rectangle and, if a rectangle was
        hidden during editing, makes it visible again.
        """
        if self.temp_rect:
            self.delete(self.temp_rect)
        if self.selected_rect is not None:
            self.itemconfigure(self.selected_rect, state="normal")
        self.mode = "idle"
        # Clear all temporary state variables
        self.temp_rect = self.start_point = None
        self.selected_rect = self.start_rect = None
        self.anchor_point = self.mov_direction = self.temp_click = None

    # ------------------------------------------------------------------ crosshair

    def create_axes(self, x, y):
        """Create the two red dashed crosshair lines at position (x, y)."""
        w, h = self.winfo_width(), self.winfo_height()
        self.axis_x = self.create_line(0, y, w, y, fill="red", dash=(4,2))
        self.axis_y = self.create_line(x, 0, x, h, fill="red", dash=(4,2))

    def destroy_axes(self):
        """Remove the crosshair lines from the canvas."""
        if self.axis_x: self.delete(self.axis_x)
        if self.axis_y: self.delete(self.axis_y)
        self.axis_x = self.axis_y = None

    def move_axes(self, x, y):
        """Move the crosshair lines to follow the cursor at (x, y)."""
        if not self.axis_x: return
        w, h = self.winfo_width(), self.winfo_height()
        self.coords(self.axis_x, 0, y, w, y)
        self.coords(self.axis_y, x, 0, x, h)

    # ------------------------------------------------------------------ creation

    def create_rectangle_start(self, x, y):
        """
        Begin drawing a new annotation rectangle at (x, y).
        Creates the temporary preview rectangle with a stipple pattern
        to visually distinguish it from confirmed annotations.
        Switches state to 'create'.
        """
        self.mode        = "create"
        self.start_point = (x, y)
        self.temp_rect   = self.create_rectangle(
            x, y, x, y,
            fill=COLOR_LIST[self.id_color],
            outline=self.default_outline,
            width=2, stipple="gray12"   # hatched fill = preview indicator
        )

    def preview_rectangle(self, x, y):
        """
        Update the temporary rectangle's coordinates while the mouse moves.
        adjust_coords ensures x1 < x2 and y1 < y2 regardless of drag direction.
        """
        x0, y0 = self.start_point
        self.coords(self.temp_rect, *adjust_coords(x, y, x0, y0))

    def finish_rectangle(self):
        """
        Confirm the current rectangle and add it to the annotation list.
        Rectangles smaller than 4x4 pixels are discarded (accidental clicks).
        Removes the stipple pattern to indicate the box is confirmed.
        Returns to 'idle' state.
        """
        if self.temp_rect is None: return
        x1, y1, x2, y2 = self.coords(self.temp_rect)
        if abs(x2-x1) < 4 or abs(y2-y1) < 4:
            # Too small — treat as accidental click and discard
            self.delete(self.temp_rect)
        else:
            self.itemconfigure(self.temp_rect, stipple="gray12",
                               fill=COLOR_LIST[self.id_color])
            self.annotation_list_id.append(self.temp_rect)
            self._create_transparent_fill(self.temp_rect)  # add alpha overlay
        self.temp_rect = self.start_point = None
        self.mode = "idle"

    # ------------------------------------------------------------------ selection/edit

    def select_rectangle(self, obj, x, y):
        """
        Enter 'move' mode for an existing rectangle `obj`.

        Steps:
          1. Determine which zone of the box was clicked (corner/edge/interior).
          2. Hide the original rectangle so the user sees only the live preview.
          3. Create a temporary preview rectangle on top.
          4. Set anchor_point to the opposite corner/edge — this stays fixed
             during a resize so the box grows/shrinks in the right direction.
        """
        x1, y1, x2, y2 = self.coords(obj)
        direction = detect_box_zone(x, y, x1, y1, x2, y2)
        if direction is None: return   # click was outside — do nothing

        self.mode          = "move"
        self.selected_rect = obj
        self.itemconfigure(obj, state="hidden")  # hide original during editing
        self.start_rect    = (x1, y1, x2, y2)   # snapshot for edge-only moves
        self.mov_direction = direction
        self.temp_click    = (x, y)              # initial drag reference point
        color = self.itemcget(obj, "fill")

        # Create an identical preview rectangle to drag around
        self.temp_rect = self.create_rectangle(
            x1, y1, x2, y2,
            fill=color, outline=self.default_outline, width=2, stipple="gray12"
        )

        # Map direction to the fixed anchor point (opposite corner/edge).
        # For interior (translate), anchor is None — we use delta-based movement.
        anchor_map = {
            (1,1,0,0): (x2,y2), (0,1,1,0): (x1,y2),
            (1,0,0,1): (x2,y1), (0,0,1,1): (x1,y1),
            (1,0,0,0): (x2,None), (0,0,1,0): (x1,None),
            (0,1,0,0): (None,y2), (0,0,0,1): (None,y1),
        }
        self.anchor_point = anchor_map.get(direction, None)

    def modify_rectangle(self, x, y):
        """
        Update the temporary rectangle while dragging, implementing either:
          - Resize: one or two edges move toward the cursor while the
            anchor side stays fixed.
          - Translate: the whole box moves by the delta from the last position.
        """
        if sum(self.mov_direction) < 4:
            # ── Resize mode ───────────────────────────────────────────────
            ax, ay = self.anchor_point
            if ax is not None and ay is not None:
                # Corner resize: both axes are constrained to the anchor
                x1, y1, x2, y2 = adjust_coords(x, y, ax, ay)
            elif ax is not None:
                # Horizontal edge only: clamp X, keep original Y range
                x1, x2 = sorted([x, ax])
                y1, y2 = self.start_rect[1], self.start_rect[3]
            elif ay is not None:
                # Vertical edge only: clamp Y, keep original X range
                y1, y2 = sorted([y, ay])
                x1, x2 = self.start_rect[0], self.start_rect[2]
            else:
                return
        else:
            # ── Translate mode (interior click) ───────────────────────────
            # Move the box by the delta between the current and last mouse pos
            xo, yo = self.temp_click
            dx, dy = x - xo, y - yo
            self.temp_click = (x, y)   # update reference for next event
            x1, y1, x2, y2 = self.coords(self.temp_rect)
            x1+=dx; y1+=dy; x2+=dx; y2+=dy

        self.coords(self.temp_rect, x1, y1, x2, y2)

    def finish_modification(self):
        """
        Confirm the edit: replace the original (hidden) rectangle with the
        modified temporary one, update the annotation list and overlay,
        and return to 'idle' state.
        """
        self.annotation_list_id.remove(self.selected_rect)
        self._remove_overlay(self.selected_rect)
        self.delete(self.selected_rect)                          # delete the old rect
        self.itemconfigure(self.temp_rect, state="normal", stipple="gray12")
        self.annotation_list_id.append(self.temp_rect)
        self._create_transparent_fill(self.temp_rect)           # new overlay
        self.temp_rect = self.selected_rect = self.mov_direction = None
        self.anchor_point = self.temp_click = None
        self.mode = "idle"

    # ------------------------------------------------------------------ event callbacks

    def on_enter(self, event):
        """Called when the cursor enters the canvas. Creates the crosshair."""
        self.focus_set()   # ensure keyboard events reach this widget
        self.create_axes(event.x, event.y)

    def on_exit(self, event):
        """Called when the cursor leaves the canvas. Removes the crosshair."""
        self.destroy_axes()

    def on_left_click(self, event):
        """
        Main interaction handler for left mouse button clicks.
        Behaviour depends on the current mode and what was clicked:
          idle + empty area  → start drawing a new box
          create             → finish the box
          idle + existing box → enter edit mode
          move               → confirm the edit
        """
        x, y = event.x, event.y
        obj  = self.get_top_object(x, y)  # topmost annotation under cursor (or None)
        if obj is None and self.mode == "idle":
            self.create_rectangle_start(x, y)
        elif self.mode == "create":
            self.finish_rectangle()
        elif obj is not None and self.mode == "idle":
            self.select_rectangle(obj, x, y)
        elif self.mode == "move":
            self.finish_modification()

    def on_right_click(self, event):
        """
        Right-click handler:
          During create/move → cancel the operation (reset_state)
          Idle + click on box → delete that annotation
        """
        x, y = event.x, event.y
        obj  = self.get_top_object(x, y)
        if self.mode in ("create", "move"):
            self.reset_state(); return
        if self.mode == "idle" and obj:
            if obj in self.annotation_list_id:
                self.annotation_list_id.remove(obj)
            self._remove_overlay(obj)
            self.delete(obj)

    def on_move(self, event):
        """
        Mouse motion handler. Always moves the crosshair.
        If an operation is in progress, also updates the live preview.
        """
        x, y = event.x, event.y
        self.move_axes(x, y)
        if   self.mode == "create": self.preview_rectangle(x, y)
        elif self.mode == "move":   self.modify_rectangle(x, y)

    def on_double_click(self, event):
        """
        Double-click on an existing annotation to reassign it to the
        currently selected class (id_color). Updates the fill color and
        recreates the alpha overlay with the new color.
        """
        obj = self.get_top_object(event.x, event.y)
        if obj and 0 <= self.id_color < len(COLOR_LIST):
            self._remove_overlay(obj)
            self.itemconfigure(obj, fill=COLOR_LIST[self.id_color])
            self._create_transparent_fill(obj)

    # ------------------------------------------------------------------ helpers

    def get_top_object(self, x, y):
        """
        Return the canvas id of the topmost annotation rectangle at (x, y),
        or None if no annotation is there.
        Excludes the background image and the crosshair lines from results
        so they cannot be accidentally selected.
        """
        objs = list(self.find_overlapping(x, y, x, y))
        for excl in (self.background_img_id, self.axis_x, self.axis_y):
            if excl in objs: objs.remove(excl)
        return objs[-1] if objs else None

    # ------------------------------------------------------------------ image management

    def load_image(self, img_path):
        """
        Load a new background image onto the canvas.
          1. Save any unsaved annotations for the previous image.
          2. Clear all existing canvas annotations.
          3. Open the new image, scale it to fit MAX_CANVAS_W × MAX_CANVAS_H
             while preserving aspect ratio.
          4. Draw the image with a padding margin (starting_point_img).
          5. Load any existing .txt label file for the new image.
        """
        if self.img_path:
            self.save_annotations()       # auto-save before switching
        self._clear_canvas_annotations()
        self.img_path = img_path
        if not img_path or not os.path.exists(img_path): return

        img = Image.open(img_path)
        w, h = img.size
        # Add padding to the effective size so the scale factor accounts for it
        w, h = w + 2*self.starting_point_img[0], h + 2*self.starting_point_img[1]
        scale = min(MAX_CANVAS_W/w, MAX_CANVAS_H/h, 1.0)
        nw, nh = int(w*scale), int(h*scale)

        self.img_ref    = ImageTk.PhotoImage(img.resize((nw, nh), Image.LANCZOS))
        self.img_draw_w = nw   # store scaled width as the coordinate reference
        self.img_draw_h = nh   # store scaled height as the coordinate reference

        # Resize canvas to match image + padding
        self.config(
            width  = nw + 2*self.starting_point_img[0],
            height = nh + 2*self.starting_point_img[1]
        )
        if self.background_img_id:
            self.delete(self.background_img_id)
        # Draw image offset by the padding so annotations have room at the edges
        self.background_img_id = self.create_image(
            self.starting_point_img[0], self.starting_point_img[1],
            image=self.img_ref, anchor="nw"
        )
        self.load_annotations()

    def _clear_canvas_annotations(self):
        """
        Remove all annotation rectangles and their overlays from the canvas
        and clear the tracking list. Also resets the state machine to idle.
        """
        for rid in self.annotation_list_id:
            self._remove_overlay(rid)
            self.delete(rid)
        self.annotation_list_id.clear()
        self.reset_state()

    # ------------------------------------------------------------------ coordinate translation

    def _translate_coord_for_save(self, x1, y1, x2, y2):
        """
        Remove the canvas padding offset before saving.
        Canvas coordinates include the starting_point_img margin, but
        YOLO coordinates must be relative to the image itself, not the canvas.
        """
        px, py = self.starting_point_img
        return x1 - px, y1 - py, x2 - px, y2 - py

    def _translate_coord_for_load(self, x1, y1, x2, y2):
        """
        Add the canvas padding offset when loading saved coordinates.
        YOLO coordinates are image-relative; on the canvas the image starts
        at starting_point_img, so we shift all coordinates accordingly.
        """
        px, py = self.starting_point_img
        return x1 + px, y1 + py, x2 + px, y2 + py

    # ------------------------------------------------------------------ I/O

    def save_annotations(self):
        """
        Write all current annotations to the YOLO .txt label file for the
        current image. Each confirmed rectangle is:
          1. Shifted back to image-relative coordinates (removing canvas padding).
          2. Clamped to [0, image_size] to avoid out-of-bounds values.
          3. Normalised to [0, 1].
          4. Written as a YOLO line: <class> <xc> <yc> <w> <h>

        Boxes that are degenerate after clamping (width or height < 0.0001)
        are skipped and counted. Returns the number of skipped boxes so the
        caller can surface a warning to the user.
        """
        if not self.img_path: return 0
        w, h = self.img_draw_w, self.img_draw_h
        skipped = 0
        with open(annotation_file_for(self.img_path), "w") as f:
            for rid in self.annotation_list_id:
                x1, y1, x2, y2 = self.coords(rid)
                # Remove canvas padding to get image-relative pixel coordinates
                x1, y1, x2, y2 = self._translate_coord_for_save(x1, y1, x2, y2)
                # Clamp to image bounds (prevents negative or >1 normalised values)
                x1 = max(0.0, min(x1, w))
                y1 = max(0.0, min(y1, h))
                x2 = max(0.0, min(x2, w))
                y2 = max(0.0, min(y2, h))
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, w, h)
                if nx2-nx1 < 1e-4 or ny2-ny1 < 1e-4:
                    skipped += 1; continue    # degenerate box — skip
                c = COLOR_LIST.index(self.itemcget(rid, "fill"))
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")
        return skipped

    def load_annotations(self):
        """
        Read the YOLO .txt label file for the current image and draw each
        annotation as a rectangle on the canvas.
          - Lines with fewer than 5 values are skipped (malformed).
          - Boxes with coordinates outside [0,1] are skipped (corrupted data).
          - Valid boxes are denormalised, shifted by canvas padding, drawn,
            and added to annotation_list_id with a semi-transparent overlay.
        """
        if not self.img_path: return
        txt = annotation_file_for(self.img_path)
        if not os.path.exists(txt): return
        w, h = self.img_draw_w, self.img_draw_h
        with open(txt) as f:
            for line in f:
                result = from_yolo_into_coord(line)
                if result is None: continue
                c, x1, y1, x2, y2 = result
                # Validate — skip lines with out-of-range coordinates
                if not (0<=x1<=1 and 0<=x2<=1 and 0<=y1<=1 and 0<=y2<=1): continue
                ax1, ay1, ax2, ay2 = denormalize_coords(x1, y1, x2, y2, w, h)
                # Add canvas padding so the box aligns with the padded image
                ax1, ay1, ax2, ay2 = self._translate_coord_for_load(ax1, ay1, ax2, ay2)
                color = COLOR_LIST[c] if 0<=c<len(COLOR_LIST) else COLOR_LIST[0]
                rid = self.create_rectangle(
                    ax1, ay1, ax2, ay2,
                    fill=color, outline=self.default_outline, width=2, stipple="gray12"
                )
                self.annotation_list_id.append(rid)
                self._create_transparent_fill(rid)

    def change_color_id(self, color_id):
        """
        Set the active class index for newly drawn or reassigned annotations.
        Silently ignores invalid indices.
        """
        if 0 <= color_id < len(COLOR_LIST):
            self.id_color = color_id

    # ------------------------------------------------------------------ semi-transparent overlay

    def _create_transparent_fill(self, rid):
        """
        Create a semi-transparent colored image the same size as the rectangle
        `rid` and place it on the canvas beneath the rectangle's border.

        Why: tkinter rectangles don't support native alpha transparency, so we
        simulate it by overlaying a PIL RGBA image with fill_alpha opacity.

        The overlay PhotoImage is stored in overlay_refs[rid] to prevent
        Python's garbage collector from deleting it (Tk only keeps a weak ref).
        """
        coords = self.coords(rid)
        if not coords: return
        x1, y1, x2, y2 = (int(v) for v in coords)
        w, h = max(x2-x1, 1), max(y2-y1, 1)
        rgba  = hex_to_rgba(self.itemcget(rid, "fill"), self.fill_alpha)
        img   = Image.new("RGBA", (w, h), rgba)
        photo = ImageTk.PhotoImage(img)
        oid   = self.create_image(x1, y1, image=photo, anchor="nw")
        self.tag_raise(rid, oid)              # border on top, fill beneath
        self.overlay_refs[rid] = (oid, photo) # keep reference alive

    def _remove_overlay(self, rid):
        """
        Delete the semi-transparent overlay image associated with rectangle `rid`
        and remove it from the overlay_refs dict.
        Safe to call even if no overlay exists for that rid.
        """
        if rid in self.overlay_refs:
            oid, _ = self.overlay_refs.pop(rid)
            self.delete(oid)


# =============================================================================
# MAIN APPLICATION
# =============================================================================

class AnnotationApp(tk.Tk):
    """
    Root application window. Contains two tabs:
      🖊 Annotation — image browser, canvas, class selector, YOLO prediction
      🔧 Training   — dataset preparation, hyperparameter config, live loss charts
    """

    def __init__(self):
        super().__init__()
        self.title("YOLO Annotation Tool")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        # ── Annotation state ───────────────────────────────────────────────
        self.folder_path = None   # path to the currently open image folder
        self.image_list  = []     # sorted list of image paths in the folder
        self.current_idx = -1     # index into image_list of the displayed image
        self.yolo_model  = None   # loaded YOLO model instance (or None)

        # ── Training state ─────────────────────────────────────────────────
        self.ft_model_path  = None          # path to the .pt file used as training base
        self.ft_output_path = None          # directory where training output is saved
        self.ft_queue       = queue.Queue() # thread-safe channel: training thread → UI
        self.ft_training    = False         # True while a training job is running
        self.ft_stop_flag   = False         # set to True to request training stop
        self.ft_thread      = None          # the background training Thread object

        # Accumulated metric history for the live charts (one value per epoch)
        self.ft_metrics = {
            "epoch":[], "box_loss":[], "cls_loss":[], "dfl_loss":[],
            "precision":[], "recall":[], "mAP50":[]
        }

        self._build_ui()
        self._bind_keys()

    # ==========================================================================
    # UI CONSTRUCTION
    # ==========================================================================

    def _build_ui(self):
        """
        Build the top-level layout: a ttk.Notebook with two tabs and a
        status bar at the bottom. Delegates tab contents to helper methods.
        """
        style = ttk.Style(self)
        style.theme_use("clam")
        # Color palette (Catppuccin Mocha)
        BG, BG2, BG3 = "#1e1e2e", "#181825", "#313244"
        ACC, FG, FG2  = "#89b4fa", "#cdd6f4", "#6c7086"
        GRN, RED      = "#a6e3a1", "#f38ba8"

        style.configure("TFrame",         background=BG)
        style.configure("TLabel",         background=BG, foreground=FG, font=("Segoe UI", 9))
        style.configure("TButton",        background=BG3, foreground=FG,
                                          font=("Segoe UI", 9), borderwidth=0)
        style.map("TButton",              background=[("active","#45475a")])
        style.configure("Accent.TButton", background=ACC, foreground=BG,
                                          font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",       background=[("active","#74c7ec")])
        style.configure("Red.TButton",    background=RED, foreground=BG,
                                          font=("Segoe UI", 9, "bold"))
        style.map("Red.TButton",          background=[("active","#eba0ac")])
        style.configure("TNotebook",      background=BG, borderwidth=0)
        style.configure("TNotebook.Tab",  background=BG3, foreground=FG,
                                          padding=[14,5], font=("Segoe UI", 9))
        style.map("TNotebook.Tab",        background=[("selected", BG)],
                                          foreground=[("selected", ACC)])
        style.configure("TEntry",         fieldbackground=BG2, foreground=FG,
                                          insertcolor=FG, borderwidth=1)
        style.configure("TCheckbutton",   background=BG, foreground=FG, font=("Segoe UI", 9))
        style.map("TCheckbutton",         background=[("active", BG)])
        style.configure("TScrollbar",     background=BG3, troughcolor=BG2, borderwidth=0)
        style.configure("TSeparator",     background=BG3)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6,0))

        self._build_annotation_tab()
        self._build_training_tab()

        # Status bar shown at the bottom of the window below the notebook
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, foreground=FG2,
                  font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", padx=10, pady=(2,4))

    # --------------------------------------------------------------------------
    # Tab 1: Annotation
    # --------------------------------------------------------------------------

    def _build_annotation_tab(self):
        """
        Build the Annotation tab with three panels:
          Left   — folder selector and image list
          Center — navigation bar and annotation canvas
          Right  — class selector, YOLO controls, and keyboard shortcuts
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🖊  Annotation")
        tab.columnconfigure(1, weight=1)   # center panel expands
        tab.rowconfigure(0, weight=1)

        left   = ttk.Frame(tab, width=210)
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        left.columnconfigure(0, weight=1)

        center = ttk.Frame(tab)
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)   # canvas row expands

        right  = ttk.Frame(tab, width=190)
        right.grid(row=0, column=2, sticky="nsew", padx=(4,8), pady=8)
        right.columnconfigure(0, weight=1)

        # ── LEFT PANEL ───────────────────────────────────────────────────
        ttk.Label(left, text="📁  Folder",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
        ttk.Button(left, text="Open Folder", style="Accent.TButton",
                   command=self.open_folder).grid(row=1, column=0, sticky="ew", pady=(0,4))

        # Shows the basename of the currently open folder
        self.folder_label = ttk.Label(left, text="No folder", foreground="#6c7086",
                                      font=("Segoe UI", 8), wraplength=195)
        self.folder_label.grid(row=2, column=0, sticky="w", pady=(0,8))

        ttk.Label(left, text="🖼  Images",
                  font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,4))

        # Scrollable list of image filenames in the open folder
        lf = ttk.Frame(left)
        lf.grid(row=4, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)   # list frame expands vertically

        self.img_listbox = tk.Listbox(
            lf, bg="#181825", fg="#cdd6f4",
            selectbackground="#89b4fa", selectforeground="#1e1e2e",
            borderwidth=0, font=("Segoe UI", 9), activestyle="none",
            exportselection=False
        )
        self.img_listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.img_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.img_listbox.configure(yscrollcommand=sb.set)
        self.img_listbox.bind("<<ListboxSelect>>", self.on_list_select)

        # Shows "N images" after a folder is loaded
        self.img_count_label = ttk.Label(left, text="0 images", foreground="#6c7086",
                                          font=("Segoe UI", 8))
        self.img_count_label.grid(row=5, column=0, sticky="w", pady=(4,0))

        # ── CENTER PANEL ─────────────────────────────────────────────────
        # Navigation bar: Prev / index label / Next / Save
        nav = ttk.Frame(center)
        nav.grid(row=0, column=0, sticky="ew", pady=(0,6))
        ttk.Button(nav, text="◀  Prev", command=self.prev_image).pack(side="left", padx=(0,4))
        # Shows "current/total — filename"
        self.nav_label = ttk.Label(nav, text="—", font=("Segoe UI", 9, "bold"))
        self.nav_label.pack(side="left", padx=8)
        ttk.Button(nav, text="Next  ▶", command=self.next_image).pack(side="left")
        ttk.Button(nav, text="💾  Save", style="Accent.TButton",
                   command=self.save_current).pack(side="right")

        # The annotation canvas itself
        self.canvas = CanvasAnnotation(
            center, bg="#11111b", cursor="crosshair",
            highlightthickness=1, highlightbackground="#313244",
            width=MAX_CANVAS_W, height=MAX_CANVAS_H
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")

        # ── RIGHT PANEL ──────────────────────────────────────────────────
        ttk.Label(right, text="🎨  Active Class",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,6))

        # Radio-button class selector — one row per class, with color dot and name label
        self.class_var = tk.IntVar(value=0)   # tracks the selected class index
        cf = ttk.Frame(right)
        cf.grid(row=1, column=0, sticky="ew", pady=(0,10))
        cf.columnconfigure(2, weight=1)

        self.class_name_labels = []   # list of ttk.Label refs, updated when a model loads
        for i, color in enumerate(COLOR_LIST):
            rb = tk.Radiobutton(
                cf, text=f" {i:02d}", variable=self.class_var, value=i,
                bg="#1e1e2e", fg="#cdd6f4", selectcolor=color,
                font=("Consolas", 9), activebackground="#313244",
                activeforeground="#cdd6f4",
                command=lambda v=i: self.canvas.change_color_id(v)
            )
            rb.grid(row=i, column=0, sticky="w")
            dot = tk.Label(cf, bg=color, width=2, relief="flat")   # colored square
            dot.grid(row=i, column=1, padx=(3,0))
            nl = ttk.Label(cf, text="", font=("Segoe UI", 8), foreground="#6c7086")
            nl.grid(row=i, column=2, sticky="w", padx=(4,0))
            self.class_name_labels.append(nl)

        ttk.Separator(right, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=8)
        ttk.Label(right, text="🤖  YOLO",
                  font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,6))
        ttk.Button(right, text="Load .pt Model",
                   command=self.load_yolo_model).grid(row=4, column=0, sticky="ew", pady=(0,4))

        # Displays the loaded model filename (or "No model")
        self.model_label = ttk.Label(right, text="No model", foreground="#6c7086",
                                      font=("Segoe UI", 8), wraplength=180)
        self.model_label.grid(row=5, column=0, sticky="w", pady=(0,8))
        ttk.Button(right, text="▶  Predict Current",
                   command=self.predict_current).grid(row=6, column=0, sticky="ew", pady=(0,4))
        ttk.Button(right, text="▶▶  Predict All",
                   command=self.predict_all).grid(row=7, column=0, sticky="ew")

        ttk.Separator(right, orient="horizontal").grid(row=8, column=0, sticky="ew", pady=8)
        ttk.Label(right, text="⌨  Shortcuts",
                  font=("Segoe UI", 10, "bold")).grid(row=9, column=0, sticky="w", pady=(0,4))
        for i, (k, d) in enumerate([
            ("← / →",   "Navigate images"),
            ("Ctrl+S",  "Save annotations"),
            ("L-Click", "Draw new box"),
            ("R-Click", "Delete / Cancel"),
            ("Dbl Cl.", "Change class"),
            ("p",       "Predict current image"),
            ("d",       "Delete all annotations"),
        ]):
            ttk.Label(right, text=k, foreground="#89b4fa",
                      font=("Consolas", 8)).grid(row=10+i, column=0, sticky="w")
            ttk.Label(right, text=d, foreground="#a6adc8",
                      font=("Segoe UI", 8)).grid(row=10+i, column=1, sticky="w", padx=(4,0))

    # --------------------------------------------------------------------------
    # Tab 2: Training
    # --------------------------------------------------------------------------

    def _build_training_tab(self):
        """
        Build the Training tab with two panels:
          Left  — scrollable configuration panel (model, output, hyperparams,
                  boolean options, class names editor, start/stop controls)
          Right — matplotlib live charts (6 subplots) + scrollable text log
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🔧  Training")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # ── Scrollable left panel ─────────────────────────────────────────
        # Wraps a ttk.Frame inside a tk.Canvas + Scrollbar so the long
        # configuration list can scroll independently of the window height.
        left_outer = ttk.Frame(tab, width=280)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        left_outer.columnconfigure(0, weight=1)
        left_outer.rowconfigure(0, weight=1)

        canvas_scroll = tk.Canvas(left_outer, bg="#1e1e2e", highlightthickness=0)
        canvas_scroll.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(left_outer, orient="vertical", command=canvas_scroll.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas_scroll.configure(yscrollcommand=vsb.set)

        left = ttk.Frame(canvas_scroll)
        left.columnconfigure(1, weight=1)
        # Create a canvas window that hosts the frame; win_id is needed to resize it
        win_id = canvas_scroll.create_window((0,0), window=left, anchor="nw")

        def _on_frame_configure(e):
            # Update the scroll region whenever the inner frame changes size
            canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))

        def _on_canvas_configure(e):
            # Keep the inner frame as wide as the canvas so it fills the panel
            canvas_scroll.itemconfig(win_id, width=e.width)

        left.bind("<Configure>", _on_frame_configure)
        canvas_scroll.bind("<Configure>", _on_canvas_configure)

        # Row counter — incremented after every widget added to the left frame
        r = 0

        # ── Helper lambdas for repetitive widget creation ─────────────────
        def sep(row):
            """Add a horizontal separator line."""
            ttk.Separator(left, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=6)

        def lbl(text, row, bold=False):
            """Add a section label (optionally bold/larger for headings)."""
            font = ("Segoe UI", 10 if bold else 9, "bold" if bold else "normal")
            ttk.Label(left, text=text, font=font).grid(
                row=row, column=0, columnspan=2, sticky="w",
                pady=(0 if bold else 1, 4 if bold else 1))

        def entry(label, key, default, row):
            """
            Add a label + Entry field for a numeric hyperparameter.
            Stores the StringVar in self.ft_vars[key] for later retrieval.
            """
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0,8))
            var = tk.StringVar(value=str(default))
            self.ft_vars[key] = var
            ttk.Entry(left, textvariable=var, width=10).grid(row=row, column=1, sticky="w")

        def check(label, key, default, row):
            """
            Add a Checkbutton for a boolean training option.
            Stores the BooleanVar in self.ft_bool_vars[key].
            """
            var = tk.BooleanVar(value=default)
            self.ft_bool_vars[key] = var
            ttk.Checkbutton(left, text=label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=1)

        # Dicts populated by entry() and check() calls below
        self.ft_vars      = {}   # { param_key : tk.StringVar }
        self.ft_bool_vars = {}   # { param_key : tk.BooleanVar }

        # ── Configuration section ─────────────────────────────────────────
        lbl("⚙  Configuration", r, bold=True); r+=1

        lbl("Base model (.pt)", r); r+=1
        # Shows the filename of the selected base model
        self.ft_model_label = ttk.Label(left, text="No model selected",
                                         foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_model_label.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,2)); r+=1
        ttk.Button(left, text="Choose model…",
                   command=self.ft_pick_model).grid(row=r, column=0, columnspan=2,
                   sticky="ew", pady=(0,8)); r+=1

        lbl("Output folder", r); r+=1
        # Shows the selected output directory path
        self.ft_out_label = ttk.Label(left, text="No folder selected",
                                       foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_out_label.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,2)); r+=1
        ttk.Button(left, text="Choose output…",
                   command=self.ft_pick_output).grid(row=r, column=0, columnspan=2,
                   sticky="ew", pady=(0,8)); r+=1

        # Shows how many annotated images were found in the open folder.
        # Updated every time the Training tab is switched to.
        self.ft_data_info = ttk.Label(left, text="Open a folder in Annotation tab first.",
                                       foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_data_info.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,10)); r+=1

        # ── Hyperparameters section ───────────────────────────────────────
        sep(r); r+=1
        lbl("📊  Hyperparameters", r, bold=True); r+=1
        entry("Epochs",            "epochs",        50,    r); r+=1
        entry("Batch size",        "batch",         16,    r); r+=1
        entry("Image size",        "imgsz",         640,   r); r+=1
        entry("Val split %",       "val_split",     20,    r); r+=1
        entry("LR0 (initial)",     "lr0",           0.01,  r); r+=1
        entry("LRf (final ratio)", "lrf",           0.01,  r); r+=1
        entry("Momentum",          "momentum",      0.937, r); r+=1
        entry("Weight decay",      "weight_decay",  0.0005,r); r+=1
        entry("Warmup epochs",     "warmup_epochs", 3,     r); r+=1
        entry("Patience",          "patience",      50,    r); r+=1
        entry("Freeze layers",     "freeze",        0,     r); r+=1  # first N backbone layers to freeze

        # ── Boolean training options section ─────────────────────────────
        sep(r); r+=1
        lbl("🔀  Training Options", r, bold=True); r+=1
        check("Augmentation",       "augment",      True,  r); r+=1  # random flips, mosaic, etc.
        check("Mixed precision",    "amp",          True,  r); r+=1  # FP16 training
        check("Cache images",       "cache",        False, r); r+=1  # pre-load images to RAM/disk
        check("Use pretrained",     "pretrained",   True,  r); r+=1  # load COCO weights first
        check("Cosine LR schedule", "cos_lr",       False, r); r+=1  # cosine vs linear LR decay
        check("Close mosaic (end)", "close_mosaic", True,  r); r+=1  # disable mosaic last 10 epochs

        # ── Class names editor ────────────────────────────────────────────
        sep(r); r+=1
        lbl("🏷  Class Names", r, bold=True); r+=1
        ttk.Label(left, text="One per line — index = row position",
                  foreground="#6c7086", font=("Segoe UI", 8)).grid(
            row=r, column=0, columnspan=2, sticky="w"); r+=1
        # Multi-line text editor; pre-filled from the model when one is loaded
        self.ft_class_text = tk.Text(
            left, bg="#181825", fg="#cdd6f4", insertbackground="#cdd6f4",
            font=("Consolas", 9), height=7, relief="flat", wrap="none", width=28
        )
        self.ft_class_text.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2,8)); r+=1

        # ── Start / Stop controls ─────────────────────────────────────────
        sep(r); r+=1
        self.ft_start_btn = ttk.Button(left, text="▶  Start Training",
                                        style="Accent.TButton", command=self.ft_start)
        self.ft_start_btn.grid(row=r, column=0, columnspan=2, sticky="ew"); r+=1

        self.ft_stop_btn = ttk.Button(left, text="⏹  Stop",
                                       style="Red.TButton",
                                       command=self.ft_stop, state="disabled")
        self.ft_stop_btn.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4,0)); r+=1

        # Shows the current epoch progress or completion message
        self.ft_progress_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.ft_progress_var,
                  foreground="#a6e3a1", font=("Segoe UI", 8), wraplength=250).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(6,0)); r+=1

        # ── Right panel: live charts + log ───────────────────────────────
        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)   # charts take 3× more space than log
        right.rowconfigure(1, weight=1)

        if MPL_AVAILABLE:
            # 2×3 grid of subplots: three loss curves and three metric curves
            self.ft_fig = Figure(figsize=(7, 4), dpi=90, facecolor="#1e1e2e")
            self.ft_fig.subplots_adjust(hspace=0.55, wspace=0.38)
            self.ft_axes = {}   # { metric_key : (matplotlib_Axes, hex_color) }
            specs = [
                # (grid_row, grid_col, metric_key, subplot_title, line_color)
                (1,1,"box_loss","Box Loss","#f38ba8"),
                (1,2,"cls_loss","Cls Loss","#fab387"),
                (1,3,"dfl_loss","DFL Loss","#f9e2af"),
                (2,1,"precision","Precision","#a6e3a1"),
                (2,2,"recall","Recall","#89dceb"),
                (2,3,"mAP50","mAP@50","#89b4fa"),
            ]
            for row, col, key, title, color in specs:
                ax = self.ft_fig.add_subplot(2, 3, (row-1)*3+col)
                ax.set_facecolor("#11111b")
                ax.set_title(title, color="#cdd6f4", fontsize=7, pad=3)
                ax.tick_params(colors="#6c7086", labelsize=6)
                for sp in ax.spines.values(): sp.set_edgecolor("#313244")
                self.ft_axes[key] = (ax, color)

            cf = ttk.Frame(right)
            cf.grid(row=0, column=0, sticky="nsew")
            self.ft_chart = FigureCanvasTkAgg(self.ft_fig, master=cf)
            self.ft_chart.get_tk_widget().pack(fill="both", expand=True)
        else:
            ttk.Label(right, text="Install matplotlib for live charts\npip install matplotlib",
                      foreground="#f38ba8").grid(row=0, column=0, pady=20)

        # Scrollable text log — receives one line per epoch from the training thread
        lf = ttk.Frame(right)
        lf.grid(row=1, column=0, sticky="nsew", pady=(6,0))
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)

        self.ft_log = tk.Text(
            lf, bg="#11111b", fg="#cdd6f4", font=("Consolas", 8),
            relief="flat", state="disabled", wrap="word", height=8
        )
        self.ft_log.grid(row=0, column=0, sticky="nsew")
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.ft_log.yview)
        lsb.grid(row=0, column=1, sticky="ns")
        self.ft_log.configure(yscrollcommand=lsb.set)
        ttk.Button(lf, text="Clear log",
                   command=self._ft_clear_log).grid(row=1, column=0, sticky="e", pady=(4,0))

        # Re-calculate annotated image count whenever this tab is focused
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    # ==========================================================================
    # ANNOTATION LOGIC
    # ==========================================================================

    def _bind_keys(self):
        """Register application-level keyboard shortcuts."""
        self.bind("<Left>",      lambda e: self.prev_image())
        self.bind("<Right>",     lambda e: self.next_image())
        self.bind("<Control-s>", lambda e: self.save_current())
        self.bind("<p>",         lambda e: self.predict_current())
        self.bind("<d>",         lambda e: self.clear_current())

    def open_folder(self):
        """
        Open a folder picker dialog, then populate the image list with all
        supported image files found directly inside the chosen directory.
        Automatically loads the first image.
        """
        path = filedialog.askdirectory(title="Select images folder")
        if not path: return
        self.folder_path = path
        self.folder_label.config(text=os.path.basename(path))
        self.image_list = sorted([
            os.path.join(path, f) for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
        ])
        self.img_listbox.delete(0, tk.END)
        for p in self.image_list:
            self.img_listbox.insert(tk.END, os.path.basename(p))
        self.img_count_label.config(text=f"{len(self.image_list)} images")
        self.status_var.set(f"Folder loaded: {len(self.image_list)} images.")
        if self.image_list: self._load_index(0)

    def _load_index(self, idx):
        """
        Load the image at position `idx` in image_list onto the canvas.
        Clamps idx to valid range. Updates the list selection and nav label.
        """
        if not self.image_list: return
        idx = max(0, min(idx, len(self.image_list)-1))
        self.current_idx = idx
        path = self.image_list[idx]
        self.canvas.load_image(path)   # triggers save of previous + load of new
        self.img_listbox.selection_clear(0, tk.END)
        self.img_listbox.selection_set(idx)
        self.img_listbox.see(idx)      # scroll list so selected item is visible
        self.nav_label.config(text=f"{idx+1}/{len(self.image_list)}  —  {os.path.basename(path)}")
        self.status_var.set(f"Loaded {os.path.basename(path)}")

    def on_list_select(self, event):
        """Called when the user clicks an item in the image listbox."""
        sel = self.img_listbox.curselection()
        if sel: self._load_index(sel[0])

    def next_image(self): self._load_index(self.current_idx + 1)
    def prev_image(self):  self._load_index(self.current_idx - 1)

    def save_current(self):
        """
        Manually save annotations for the current image.
        Shows a warning in the status bar if any boxes were out of bounds.
        """
        skipped = self.canvas.save_annotations()
        msg = f"Saved {os.path.basename(self.canvas.img_path or '')}"
        if skipped: msg += f"  ⚠ {skipped} invalid boxes skipped"
        self.status_var.set(msg)

    def load_yolo_model(self):
        """
        Open a file picker to select a YOLO .pt model, load it with
        ultralytics YOLO, and populate the class name labels from model.names.
        Also pre-fills the Training tab class names editor.
        """
        if not YOLO_AVAILABLE:
            messagebox.showerror("Error", "ultralytics not installed.\npip install ultralytics")
            return
        path = filedialog.askopenfilename(filetypes=[("YOLO model", "*.pt")])
        if not path: return
        try:
            self.yolo_model = YOLO(path)
            self.model_label.config(text=f"✅ {os.path.basename(path)}", foreground="#a6e3a1")
            self._sync_class_names_from_model()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _sync_class_names_from_model(self):
        """
        Read model.names (a dict {int: str}) and update:
          - The class name labels next to the color radio buttons (Annotation tab)
          - The class names text editor (Training tab)
        """
        if not self.yolo_model: return
        names = self.yolo_model.names   # e.g. {0: 'person', 1: 'car', ...}
        for i, lbl in enumerate(self.class_name_labels):
            name = names.get(i, "")
            lbl.config(text=name, foreground="#cdd6f4" if name else "#6c7086")
        # Overwrite the class editor with model names so training uses them by default
        self.ft_class_text.delete("1.0", "end")
        for i in range(len(names)):
            self.ft_class_text.insert("end", names.get(i, f"class_{i}") + "\n")

    def _run_prediction(self, img_path):
        """
        Run the loaded YOLO model on a single image and write the results to
        the corresponding .txt label file (overwriting any existing labels).
        Prediction boxes are stored in original image pixel space and
        normalised before writing.
        """
        results = self.yolo_model(img_path, verbose=False)
        img = Image.open(img_path)
        iw, ih = img.size   # original image dimensions for normalisation
        with open(annotation_file_for(img_path), "w") as f:
            for box in results[0].boxes:
                c = int(box.cls[0])                   # class index
                x1, y1, x2, y2 = box.xyxy[0].tolist() # absolute pixel coords
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, iw, ih)
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")

    def predict_current(self):
        """Run prediction on the currently displayed image and reload annotations."""
        if not self.yolo_model or self.current_idx < 0: return
        self._run_prediction(self.image_list[self.current_idx])
        self.canvas._clear_canvas_annotations()
        self.canvas.load_annotations()
        self.status_var.set("Prediction done.")

    def predict_all(self):
        """
        Run prediction on every image in the folder after user confirmation.
        Updates the status bar with progress. Reloads annotations for the
        currently displayed image after the batch is complete.
        """
        if not self.yolo_model or not self.image_list: return
        if not messagebox.askyesno("Confirm",
                "Predict all? Existing labels will be overwritten."): return
        for i, p in enumerate(self.image_list):
            self._run_prediction(p)
            self.status_var.set(f"Predicting {i+1}/{len(self.image_list)}…")
            self.update_idletasks()   # keep UI responsive during the loop
        self.canvas._clear_canvas_annotations()
        self.canvas.load_annotations()
        self.status_var.set("Batch prediction complete.")

    def clear_current(self):
        """
        Delete all annotations from the current image after user confirmation.
        Does NOT write the empty file yet — that happens on next image switch or Save.
        """
        if not messagebox.askyesno("Confirm",
                "Clear current annotations? Labels will be removed."): return
        self.canvas._clear_canvas_annotations()

    # ==========================================================================
    # TRAINING LOGIC
    # ==========================================================================

    def _on_tab_change(self, _event=None):
        """
        Called whenever the notebook tab changes.
        Updates the data info label in the Training tab to reflect the
        current folder and how many images have non-empty annotation files.
        """
        if self.folder_path:
            annotated = [p for p in self.image_list if has_annotations(p)]
            self.ft_data_info.config(
                text=(f"Folder: {os.path.basename(self.folder_path)}\n"
                      f"{len(annotated)} / {len(self.image_list)} images annotated"),
                foreground="#cdd6f4"
            )
        else:
            self.ft_data_info.config(
                text="Open a folder in the Annotation tab first.",
                foreground="#6c7086"
            )

    def ft_pick_model(self):
        """
        Open a file picker to select the base .pt model for training.
        If ultralytics is available, also loads the model's class names into
        the class names editor so the user can review/modify them before training.
        """
        path = filedialog.askopenfilename(
            title="Base model for training", filetypes=[("YOLO model", "*.pt")])
        if not path: return
        self.ft_model_path = path
        self.ft_model_label.config(text=os.path.basename(path), foreground="#cdd6f4")
        if YOLO_AVAILABLE:
            try:
                m = YOLO(path)
                self.ft_class_text.delete("1.0", "end")
                for i in range(len(m.names)):
                    self.ft_class_text.insert("end", m.names.get(i, f"class_{i}") + "\n")
                self._ft_log_write(f"Class names loaded from {os.path.basename(path)}")
            except Exception:
                pass   # model might not have names (e.g. fresh backbone) — ignore

    def ft_pick_output(self):
        """Open a directory picker to choose where training output will be saved."""
        path = filedialog.askdirectory(title="Training output folder")
        if path:
            self.ft_output_path = path
            self.ft_out_label.config(text=path, foreground="#cdd6f4")

    def _ft_get_class_names(self):
        """
        Read the class names text editor and return a list of non-empty
        stripped strings, one per line. The list index is the YOLO class id.
        Returns [] if the editor is empty.
        """
        raw = self.ft_class_text.get("1.0", "end").strip()
        if not raw: return []
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]

    def _ft_prepare_dataset(self, src_folder, out_folder, val_pct, annotated_imgs):
        """
        Build the train/val directory structure expected by ultralytics YOLO:
          out_folder/
            train/images/  ← symlinks to training image files
            train/labels/  ← symlinks to training .txt label files
            val/images/    ← symlinks to validation image files
            val/labels/    ← symlinks to validation .txt label files

        Uses symbolic links instead of copies to save disk space.
        Only images listed in annotated_imgs (non-empty .txt) are included.
        The split is random; val_pct % goes to validation, the rest to train.

        Returns (n_train, n_val) — the count of images in each split.
        Raises ValueError if there are too few images.
        """
        imgs = list(annotated_imgs)
        if not imgs:
            raise ValueError("No annotated images found.")
        random.shuffle(imgs)   # randomise before splitting
        n_val   = max(1, math.ceil(len(imgs) * val_pct / 100))
        n_train = len(imgs) - n_val
        if n_train < 1:
            raise ValueError(f"Not enough images ({len(imgs)}) for this split.")

        splits = {"train": imgs[:n_train], "val": imgs[n_train:]}
        for split, paths in splits.items():
            img_dir = os.path.join(out_folder, split, "images")
            lbl_dir = os.path.join(out_folder, split, "labels")
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(lbl_dir, exist_ok=True)
            for p in paths:
                name      = os.path.basename(p)
                stem, _   = os.path.splitext(name)
                label_src = annotation_file_for(p)
                # Create symlinks using absolute paths so they work from any cwd
                make_symlink(os.path.abspath(p),
                             os.path.join(img_dir, name))
                make_symlink(os.path.abspath(label_src),
                             os.path.join(lbl_dir, stem + ".txt"))
        return n_train, n_val

    def _ft_write_yaml(self, out_folder, class_names):
        """
        Write the dataset.yaml file required by ultralytics YOLO.
        Format:
          path: <absolute output folder>
          train: train/images
          val:   val/images
          nc: <number of classes>
          names:
            0: class_a
            1: class_b
            ...
        Returns the absolute path to the written yaml file.
        """
        yaml_path = os.path.join(out_folder, "dataset.yaml")
        names_block = "\n".join(f"  {i}: {n}" for i, n in enumerate(class_names))
        with open(yaml_path, "w") as f:
            f.write(f"path: {os.path.abspath(out_folder)}\n"
                    f"train: train/images\n"
                    f"val:   val/images\n\n"
                    f"nc: {len(class_names)}\n"
                    f"names:\n{names_block}\n")
        return yaml_path

    def ft_start(self):
        """
        Validate all inputs, prepare the dataset, then launch YOLO training
        in a background daemon thread. A per-epoch callback pushes metrics
        and log messages onto ft_queue; _ft_poll() reads the queue from the
        main thread every 250 ms to update the UI safely.

        Pre-conditions checked:
          - ultralytics installed
          - base model selected
          - annotation folder open
          - output folder selected
          - class names provided
          - all numeric fields parseable
          - at least one annotated image found
        """
        if not YOLO_AVAILABLE:
            messagebox.showerror("Error", "ultralytics not installed."); return
        if not self.ft_model_path:
            messagebox.showwarning("Missing", "Choose a base model first."); return
        if not self.folder_path:
            messagebox.showwarning("Missing", "Open an annotated folder first."); return
        if not self.ft_output_path:
            messagebox.showwarning("Missing", "Choose an output folder first."); return
        if self.ft_training: return   # already running

        class_names = self._ft_get_class_names()
        if not class_names:
            messagebox.showwarning("Missing classes",
                "Add at least one class name in the Class Names editor."); return

        # Parse all numeric hyperparameters from the StringVar entries
        try:
            p = {k: v.get() for k, v in self.ft_vars.items()}
            epochs    = int(p["epochs"])
            batch     = int(p["batch"])
            imgsz     = int(p["imgsz"])
            val_split = float(p["val_split"])
            lr0       = float(p["lr0"])
            lrf       = float(p["lrf"])
            momentum  = float(p["momentum"])
            wd        = float(p["weight_decay"])
            warmup    = float(p["warmup_epochs"])
            patience  = int(p["patience"])
            freeze    = int(p["freeze"]) if p["freeze"].strip() else 0
        except ValueError:
            messagebox.showerror("Invalid params",
                "Check that all numeric fields are correct."); return

        # Read boolean training options from their BooleanVars
        bp = {k: v.get() for k, v in self.ft_bool_vars.items()}

        annotated = [img for img in self.image_list if has_annotations(img)]
        if not annotated:
            messagebox.showwarning("No data", "No annotated images found."); return

        # ── Reset UI to "training" state ──────────────────────────────────
        self.ft_training  = True
        self.ft_stop_flag = False
        self.ft_start_btn.config(state="disabled")
        self.ft_stop_btn.config(state="normal")
        self.ft_progress_var.set("Preparing dataset…")
        self._ft_clear_log()
        for key in self.ft_metrics: self.ft_metrics[key].clear()   # reset chart data

        dataset_dir = os.path.join(self.ft_output_path, "dataset_split")

        # Capture all values as local variables so the thread closure is safe.
        # (Accessing self.ft_vars from a thread could cause race conditions.)
        _epochs = epochs; _batch = batch; _imgsz = imgsz
        _val_split = val_split; _lr0 = lr0; _lrf = lrf
        _momentum = momentum; _wd = wd; _warmup = warmup
        _patience = patience; _freeze = freeze; _bp = bp
        _class_names = class_names; _annotated = annotated

        def _train():
            """
            Background thread: prepares dataset, runs model.train(), and
            sends progress/metric/done/error messages to ft_queue.
            """
            try:
                self.ft_queue.put(("log", f"Dataset: {len(_annotated)} annotated images"))
                n_train, n_val = self._ft_prepare_dataset(
                    self.folder_path, dataset_dir, _val_split, _annotated)
                yaml_path = self._ft_write_yaml(dataset_dir, _class_names)
                self.ft_queue.put(("log",
                    f"Split: {n_train} train / {n_val} val  |  "
                    f"{len(_class_names)} classes  |  symlinks created"))
                self.ft_queue.put(("log", f"YAML: {yaml_path}"))

                model = YOLO(self.ft_model_path)

                def on_epoch_end(trainer):
                    """
                    Ultralytics callback fired at the end of every training epoch.
                    Reads loss and metric values from the trainer object and
                    pushes them onto the queue for the UI thread to consume.
                    Setting trainer.epoch = trainer.epochs when ft_stop_flag is
                    set causes ultralytics to stop after the current epoch.
                    """
                    if self.ft_stop_flag:
                        trainer.epoch = trainer.epochs   # signal ultralytics to stop

                    ep   = trainer.epoch + 1
                    loss = trainer.loss_items   # tensor [box_loss, cls_loss, dfl_loss]
                    met  = trainer.metrics or {}

                    # Safely extract individual loss components
                    bl = float(loss[0]) if loss is not None and len(loss) > 0 else 0.0
                    cl = float(loss[1]) if loss is not None and len(loss) > 1 else 0.0
                    dl = float(loss[2]) if loss is not None and len(loss) > 2 else 0.0
                    mp = float(met.get("metrics/mAP50(B)",    0))
                    pr = float(met.get("metrics/precision(B)", 0))
                    rc = float(met.get("metrics/recall(B)",    0))

                    self.ft_queue.put(("metrics", {
                        "epoch": ep, "box_loss": bl, "cls_loss": cl,
                        "dfl_loss": dl, "precision": pr, "recall": rc, "mAP50": mp,
                    }))
                    self.ft_queue.put(("log",
                        f"Ep {ep:>3}/{_epochs}  "
                        f"box={bl:.4f}  cls={cl:.4f}  "
                        f"prec={pr:.3f}  rec={rc:.3f}  mAP50={mp:.4f}"))
                    self.ft_queue.put(("progress", f"Epoch {ep} / {_epochs}"))

                model.add_callback("on_train_epoch_end", on_epoch_end)

                # Build the kwargs dict for model.train()
                train_kwargs = dict(
                    data          = yaml_path,
                    epochs        = _epochs,
                    batch         = _batch,
                    imgsz         = _imgsz,
                    lr0           = _lr0,
                    lrf           = _lrf,       # final LR = lr0 * lrf
                    momentum      = _momentum,
                    weight_decay  = _wd,
                    warmup_epochs = _warmup,
                    patience      = _patience,  # early stopping patience
                    augment       = _bp["augment"],
                    amp           = _bp["amp"],
                    cache         = _bp["cache"],
                    pretrained    = _bp["pretrained"],
                    cos_lr        = _bp["cos_lr"],
                    close_mosaic  = 10 if _bp["close_mosaic"] else 0,  # last N epochs without mosaic
                    project       = self.ft_output_path,
                    name          = "finetune",   # creates output/finetune/ directory
                    exist_ok      = True,         # overwrite previous run's directory
                    verbose       = False,
                )
                if _freeze > 0:
                    train_kwargs["freeze"] = _freeze   # freeze first N backbone layers

                model.train(**train_kwargs)

                # Training complete — point to the best checkpoint
                best = os.path.join(self.ft_output_path, "finetune", "weights", "best.pt")
                self.ft_queue.put(("done", best))

            except Exception as e:
                self.ft_queue.put(("error", str(e)))

        self.ft_thread = threading.Thread(target=_train, daemon=True)
        self.ft_thread.start()
        self._ft_poll()   # begin polling the queue

    def ft_stop(self):
        """
        Request an early stop of the training. Sets ft_stop_flag so the
        on_epoch_end callback will signal ultralytics to halt after the
        current epoch completes.
        """
        self.ft_stop_flag = True
        self.ft_progress_var.set("Stopping after current epoch…")
        self._ft_log_write("⏹  Stop requested — finishing current epoch…")

    def _ft_poll(self):
        """
        Drain all pending messages from ft_queue and process them on the
        main thread (required for safe Tkinter updates).

        Message types:
          ("log",      str)         → append to the text log
          ("progress", str)         → update the progress label
          ("metrics",  dict)        → append to ft_metrics and redraw charts
          ("done",     best_path)   → training finished successfully
          ("error",    error_str)   → training failed with an exception

        Reschedules itself every 250 ms while training is running.
        """
        try:
            while True:
                kind, payload = self.ft_queue.get_nowait()
                if kind == "log":
                    self._ft_log_write(payload)
                elif kind == "progress":
                    self.ft_progress_var.set(payload)
                elif kind == "metrics":
                    for k, v in payload.items():
                        self.ft_metrics[k].append(v)
                    self._ft_update_charts()
                elif kind == "done":
                    self._ft_done(payload); return
                elif kind == "error":
                    self._ft_error(payload); return
        except queue.Empty:
            pass   # nothing in the queue right now — check again later

        # If stop was requested and the thread has already exited, wrap up
        if self.ft_stop_flag and self.ft_thread and not self.ft_thread.is_alive():
            self._ft_done(None); return

        self.after(250, self._ft_poll)   # reschedule

    def _ft_update_charts(self):
        """
        Redraw all 6 matplotlib subplots using the latest accumulated metrics.
        Called after every epoch's metrics are added to ft_metrics.
        Uses draw_idle() to let matplotlib batch the redraw efficiently.
        """
        if not MPL_AVAILABLE: return
        label_map = {
            "box_loss":"Box Loss", "cls_loss":"Cls Loss", "dfl_loss":"DFL Loss",
            "precision":"Precision", "recall":"Recall", "mAP50":"mAP@50"
        }
        for key, (ax, color) in self.ft_axes.items():
            data   = self.ft_metrics[key]
            epochs = self.ft_metrics["epoch"]
            ax.clear()
            ax.set_facecolor("#11111b")
            ax.set_title(label_map[key], color="#cdd6f4", fontsize=7, pad=3)
            ax.tick_params(colors="#6c7086", labelsize=6)
            for sp in ax.spines.values(): sp.set_edgecolor("#313244")
            if data:
                ax.plot(epochs, data, color=color, linewidth=1.3)
                ax.fill_between(epochs, data, alpha=0.12, color=color)  # subtle area fill
        self.ft_fig.canvas.draw_idle()

    def _ft_done(self, best_path):
        """
        Called when training finishes (normally or via stop).
        Re-enables the Start button, disables Stop.
        If a best.pt file was produced, offers to load it into the annotator
        so the user can immediately use the new model for predictions.
        """
        self.ft_training = False
        self.ft_start_btn.config(state="normal")
        self.ft_stop_btn.config(state="disabled")
        if best_path and os.path.exists(best_path):
            self.ft_progress_var.set("✅  Training complete!")
            self._ft_log_write(f"\n✅  Done. Best model: {best_path}")
            if messagebox.askyesno("Training complete",
                    f"Training finished!\n\n"
                    f"Load best.pt into the annotator?\n{best_path}"):
                try:
                    self.yolo_model = YOLO(best_path)
                    self.ft_model_path = best_path
                    self.model_label.config(
                        text=f"✅ {os.path.basename(best_path)}", foreground="#a6e3a1")
                    self._sync_class_names_from_model()
                    self.status_var.set(f"Model updated: {os.path.basename(best_path)}")
                except Exception as e:
                    messagebox.showerror("Load error", str(e))
        else:
            self.ft_progress_var.set("⏹  Training stopped.")
            self._ft_log_write("⏹  Stopped by user.")

    def _ft_error(self, msg):
        """
        Called when an unhandled exception is raised inside the training thread.
        Resets UI to idle state and shows an error dialog.
        """
        self.ft_training = False
        self.ft_start_btn.config(state="normal")
        self.ft_stop_btn.config(state="disabled")
        self.ft_progress_var.set("❌  Error")
        self._ft_log_write(f"\n❌  ERROR: {msg}")
        messagebox.showerror("Training error", msg)

    def _ft_log_write(self, msg):
        """Append a line to the training log Text widget (thread-safe via main thread only)."""
        self.ft_log.configure(state="normal")
        self.ft_log.insert("end", msg + "\n")
        self.ft_log.see("end")          # auto-scroll to the latest line
        self.ft_log.configure(state="disabled")

    def _ft_clear_log(self):
        """Clear all content from the training log Text widget."""
        self.ft_log.configure(state="normal")
        self.ft_log.delete("1.0", "end")
        self.ft_log.configure(state="disabled")

    # ==========================================================================
    # APPLICATION CLOSE
    # ==========================================================================

    def on_close(self):
        """
        Called when the user closes the window (WM_DELETE_WINDOW protocol).
        Saves any unsaved annotations for the current image before destroying
        the window to prevent data loss.
        """
        if self.canvas.img_path:
            self.canvas.save_annotations()
        self.destroy()


if __name__ == "__main__":
    app = AnnotationApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()