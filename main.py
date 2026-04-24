import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os

# Optional Ultralytics integration
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# =============================================================================
# CONSTANTS
# =============================================================================

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

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

MAX_CANVAS_W = 1100
MAX_CANVAS_H = 750






# =============================================================================
# UTILS
# =============================================================================

def detect_box_zone(xm, ym, x1, y1, x2, y2, tol=8):
    """Identifies which part of the bounding box was clicked (corners, edges, or center)."""
    if abs(xm - x1) <= tol and abs(ym - y1) <= tol: return (1,1,0,0)
    elif abs(xm - x2) <= tol and abs(ym - y1) <= tol: return (0,1,1,0)
    elif abs(xm - x1) <= tol and abs(ym - y2) <= tol: return (1,0,0,1)
    elif abs(xm - x2) <= tol and abs(ym - y2) <= tol: return (0,0,1,1)
    elif abs(xm - x1) <= tol and y1 <= ym <= y2:       return (1,0,0,0)
    elif abs(xm - x2) <= tol and y1 <= ym <= y2:       return (0,0,1,0)
    elif abs(ym - y1) <= tol and x1 <= xm <= x2:       return (0,1,0,0)
    elif abs(ym - y2) <= tol and x1 <= xm <= x2:       return (0,0,0,1)
    elif x1 < xm < x2 and y1 < ym < y2:               return (1,1,1,1)
    return None

def adjust_coords(xm, ym, x1, y1):
    return min(xm, x1), min(ym, y1), max(xm, x1), max(ym, y1)

def normalize_coords(x1, y1, x2, y2, w, h):
    return x1/w, y1/h, x2/w, y2/h

def denormalize_coords(x1, y1, x2, y2, w, h):
    return x1*w, y1*h, x2*w, y2*h

def convert_into_yolo(c, x1, y1, x2, y2):
    xc = (x2 + x1) / 2
    yc = (y2 + y1) / 2
    w  = x2 - x1
    h  = y2 - y1
    return f"{c:d} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}"

def from_yolo_into_coord(values_string):
    values = values_string.strip().split()
    if len(values) < 5:
        return None
    c  = int(values[0])
    xc, yc, w, h = float(values[1]), float(values[2]), float(values[3]), float(values[4])
    x1 = xc - w/2
    x2 = xc + w/2
    y1 = yc - h/2
    y2 = yc + h/2
    return c, x1, y1, x2, y2

def annotation_file_for(img_path):
    base, _ = os.path.splitext(img_path)
    return base + ".txt"

def hex_to_rgba(hex_color: str, alpha: int) -> tuple:
    """Converts '#rrggbb' + alpha (0-255) into (r, g, b, a)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)









# =============================================================================
# ANNOTATION CANVAS
# =============================================================================

class CanvasAnnotation(tk.Canvas):

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        # state
        self.mode = "idle"

        # crosshair axes
        self.axis_x = None
        self.axis_y = None

        # creation state
        self.temp_rect   = None
        self.start_point = None

        # modification state
        self.selected_rect  = None
        self.start_rect     = None
        self.anchor_point   = None
        self.mov_direction  = None
        self.temp_click     = None

        # background image
        self.img_path          = None
        self.img_ref           = None
        self.background_img_id = None
        self.img_draw_w        = 1
        self.img_draw_h        = 1

        # annotations
        self.annotation_list_id = []

        # semi-transparent overlays: dict[rect_id -> (overlay_img_id, PhotoImage)]
        self.overlay_refs = {}

        # current color/class
        self.id_color        = 0
        self.default_outline = "black"
        self.fill_alpha      = 80   # 0-255 opacity

        # bindings
        self.bind("<Enter>",          self.on_enter)
        self.bind("<Leave>",          self.on_exit)
        self.bind("<Button-1>",       self.on_left_click)
        self.bind("<Button-3>",       self.on_right_click)
        self.bind("<Motion>",         self.on_move)
        self.bind("<Double-Button-1>",self.on_double_click)

    # ------------------------------------------------------------------ reset
    def reset_state(self):
        if self.temp_rect:
            self.delete(self.temp_rect)
        if self.selected_rect is not None:
            self.itemconfigure(self.selected_rect, state="normal")
        self.mode          = "idle"
        self.temp_rect     = None
        self.start_point   = None
        self.selected_rect = None
        self.start_rect    = None
        self.anchor_point  = None
        self.mov_direction = None
        self.temp_click    = None

    # ------------------------------------------------------------------ crosshair
    def create_axes(self, x, y):
        w, h = self.winfo_width(), self.winfo_height()
        self.axis_x = self.create_line(0, y, w, y, fill="red", dash=(4,2))
        self.axis_y = self.create_line(x, 0, x, h, fill="red", dash=(4,2))

    def destroy_axes(self):
        if self.axis_x: self.delete(self.axis_x)
        if self.axis_y: self.delete(self.axis_y)
        self.axis_x = self.axis_y = None

    def move_axes(self, x, y):
        if not self.axis_x: return
        w, h = self.winfo_width(), self.winfo_height()
        self.coords(self.axis_x, 0, y, w, y)
        self.coords(self.axis_y, x, 0, x, h)

    # ------------------------------------------------------------------ creation
    def create_rectangle_start(self, x, y):
        self.mode        = "create"
        self.start_point = (x, y)
        self.temp_rect   = self.create_rectangle(
            x, y, x, y,
            fill=COLOR_LIST[self.id_color],
            outline=self.default_outline,
            width=2,
            stipple="gray50"
        )

    def preview_rectangle(self, x, y):
        x0, y0 = self.start_point
        x1, y1, x2, y2 = adjust_coords(x, y, x0, y0)
        self.coords(self.temp_rect, x1, y1, x2, y2)

    def finish_rectangle(self):
        if self.temp_rect is None:
            return
        x1, y1, x2, y2 = self.coords(self.temp_rect)
        if abs(x2 - x1) < 4 or abs(y2 - y1) < 4:
            self.delete(self.temp_rect)
        else:
            self.itemconfigure(self.temp_rect, stipple="gray50", fill=COLOR_LIST[self.id_color])
            self.annotation_list_id.append(self.temp_rect)
            self._create_transparent_fill(self.temp_rect)
        self.temp_rect   = None
        self.start_point = None
        self.mode        = "idle"

    # ------------------------------------------------------------------ selection/edit
    def select_rectangle(self, obj, x, y):
        x1, y1, x2, y2 = self.coords(obj)
        direction = detect_box_zone(x, y, x1, y1, x2, y2)
        if direction is None:
            return
        self.mode          = "move"
        self.selected_rect = obj
        self.itemconfigure(obj, state="hidden")
        self.start_rect    = (x1, y1, x2, y2)
        self.mov_direction = direction
        self.temp_click    = (x, y)
        color = self.itemcget(obj, "fill")
        self.temp_rect = self.create_rectangle(
            x1, y1, x2, y2,
            fill=color, outline=self.default_outline, width=2, stipple="gray50"
        )
        if   direction == (1,1,0,0): self.anchor_point = (x2, y2)
        elif direction == (0,1,1,0): self.anchor_point = (x1, y2)
        elif direction == (1,0,0,1): self.anchor_point = (x2, y1)
        elif direction == (0,0,1,1): self.anchor_point = (x1, y1)
        elif direction == (1,0,0,0): self.anchor_point = (x2, None)
        elif direction == (0,0,1,0): self.anchor_point = (x1, None)
        elif direction == (0,1,0,0): self.anchor_point = (None, y2)
        elif direction == (0,0,0,1): self.anchor_point = (None, y1)
        else:                        self.anchor_point = None

    def modify_rectangle(self, x, y):
        if sum(self.mov_direction) < 4:
            ax, ay = self.anchor_point
            if ax is not None and ay is not None:
                x1, y1, x2, y2 = adjust_coords(x, y, ax, ay)
            elif ax is not None:
                x1, x2 = sorted([x, ax])
                y1, y2 = self.start_rect[1], self.start_rect[3]
            elif ay is not None:
                y1, y2 = sorted([y, ay])
                x1, x2 = self.start_rect[0], self.start_rect[2]
            else:
                return
        else:
            xo, yo = self.temp_click
            dx, dy = x - xo, y - yo
            self.temp_click = (x, y)
            x1, y1, x2, y2 = self.coords(self.temp_rect)
            x1 += dx; y1 += dy; x2 += dx; y2 += dy
        self.coords(self.temp_rect, x1, y1, x2, y2)

    def finish_modification(self):
        self.annotation_list_id.remove(self.selected_rect)
        self._remove_overlay(self.selected_rect)
        self.delete(self.selected_rect)
        self.itemconfigure(self.temp_rect, state="normal", stipple="gray50")
        self.annotation_list_id.append(self.temp_rect)
        self._create_transparent_fill(self.temp_rect)
        self.temp_rect = self.selected_rect = self.mov_direction = None
        self.anchor_point = self.temp_click = None
        self.mode = "idle"

    # ------------------------------------------------------------------ callbacks
    def on_enter(self, event):
        self.focus_set()
        self.create_axes(event.x, event.y)

    def on_exit(self, event):
        self.destroy_axes()

    def on_left_click(self, event):
        x, y = event.x, event.y
        obj  = self.get_top_object(x, y)
        if obj is None and self.mode == "idle":
            self.create_rectangle_start(x, y)
        elif self.mode == "create":
            self.finish_rectangle()
        elif obj is not None and self.mode == "idle":
            self.select_rectangle(obj, x, y)
        elif self.mode == "move":
            self.finish_modification()

    def on_right_click(self, event):
        x, y = event.x, event.y
        obj  = self.get_top_object(x, y)
        if self.mode in ("create", "move"):
            self.reset_state()
            return
        if self.mode == "idle" and obj:
            if obj in self.annotation_list_id:
                self.annotation_list_id.remove(obj)
            self._remove_overlay(obj)
            self.delete(obj)

    def on_move(self, event):
        x, y = event.x, event.y
        self.move_axes(x, y)
        if   self.mode == "create": self.preview_rectangle(x, y)
        elif self.mode == "move":   self.modify_rectangle(x, y)

    def on_double_click(self, event):
        obj = self.get_top_object(event.x, event.y)
        if obj and 0 <= self.id_color < len(COLOR_LIST):
            self._remove_overlay(obj)
            self.itemconfigure(obj, fill=COLOR_LIST[self.id_color])
            self._create_transparent_fill(obj)

    # ------------------------------------------------------------------ helper
    def get_top_object(self, x, y):
        objs = list(self.find_overlapping(x, y, x, y))
        for excl in (self.background_img_id, self.axis_x, self.axis_y):
            if excl in objs: objs.remove(excl)
        return objs[-1] if objs else None

    # ------------------------------------------------------------------ image
    def load_image(self, img_path):
        if self.img_path:
            self.save_annotations()
        self._clear_canvas_annotations()
        self.img_path = img_path
        if not img_path or not os.path.exists(img_path):
            return
        img   = Image.open(img_path)
        w, h  = img.size
        scale = min(MAX_CANVAS_W / w, MAX_CANVAS_H / h, 1.0)
        nw, nh = int(w * scale), int(h * scale)
        img_resized = img.resize((nw, nh), Image.LANCZOS)
        self.img_ref    = ImageTk.PhotoImage(img_resized)
        self.img_draw_w = nw
        self.img_draw_h = nh
        self.config(width=nw, height=nh)
        if self.background_img_id:
            self.delete(self.background_img_id)
        self.background_img_id = self.create_image(0, 0, image=self.img_ref, anchor="nw")
        self.load_annotations()

    def _clear_canvas_annotations(self):
        for rid in self.annotation_list_id:
            self._remove_overlay(rid)
            self.delete(rid)
        self.annotation_list_id.clear()
        self.reset_state()

    # ------------------------------------------------------------------ I/O
    def save_annotations(self):
        if not self.img_path:
            return
        file_ann = annotation_file_for(self.img_path)
        w, h = self.img_draw_w, self.img_draw_h
        skipped = 0
        with open(file_ann, "w") as f:
            for rid in self.annotation_list_id:
                x1, y1, x2, y2 = self.coords(rid)
                x1 = max(0.0, min(x1, w))
                y1 = max(0.0, min(y1, h))
                x2 = max(0.0, min(x2, w))
                y2 = max(0.0, min(y2, h))
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, w, h)
                if nx2 - nx1 < 1e-4 or ny2 - ny1 < 1e-4:
                    skipped += 1
                    continue
                c = COLOR_LIST.index(self.itemcget(rid, "fill"))
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")
        return skipped

    def load_annotations(self):
        if not self.img_path:
            return
        file_ann = annotation_file_for(self.img_path)
        if not os.path.exists(file_ann):
            return
        w, h = self.img_draw_w, self.img_draw_h
        with open(file_ann, "r") as f:
            for line in f:
                result = from_yolo_into_coord(line)
                if result is None:
                    continue
                c, x1, y1, x2, y2 = result
                if not (0.0 <= x1 <= 1.0 and 0.0 <= x2 <= 1.0 and
                        0.0 <= y1 <= 1.0 and 0.0 <= y2 <= 1.0):
                    continue
                ax1, ay1, ax2, ay2 = denormalize_coords(x1, y1, x2, y2, w, h)
                color = COLOR_LIST[c] if 0 <= c < len(COLOR_LIST) else COLOR_LIST[0]
                rid = self.create_rectangle(
                    ax1, ay1, ax2, ay2,
                    fill=color, outline=self.default_outline, width=2, stipple="gray50"
                )
                self.annotation_list_id.append(rid)
                self._create_transparent_fill(rid)

    def change_color_id(self, color_id):
        if 0 <= color_id < len(COLOR_LIST):
            self.id_color = color_id

    # ------------------------------------------------------------------ alpha overlay
    def _create_transparent_fill(self, rid):
        """Creates a semi-transparent RGBA overlay inside the box."""
        coords = self.coords(rid)
        if not coords: return
        x1, y1, x2, y2 = (int(v) for v in coords)
        w = max(x2 - x1, 1)
        h = max(y2 - y1, 1)
        hex_color = self.itemcget(rid, "fill")
        rgba = hex_to_rgba(hex_color, self.fill_alpha)
        img = Image.new("RGBA", (w, h), rgba)
        photo = ImageTk.PhotoImage(img)
        oid = self.create_image(x1, y1, image=photo, anchor="nw")
        self.tag_raise(rid, oid)
        self.overlay_refs[rid] = (oid, photo)

    def _remove_overlay(self, rid):
        if rid in self.overlay_refs:
            oid, _ = self.overlay_refs.pop(rid)
            self.delete(oid)










# =============================================================================
# MAIN APP
# =============================================================================

class AnnotationApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("YOLO Annotation Tool")
        self.resizable(True, True)
        self.configure(bg="#1e1e2e")

        # state
        self.folder_path  = None
        self.image_list   = []
        self.current_idx  = -1
        self.yolo_model   = None

        self._build_ui()
        self._bind_keys()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",           background="#1e1e2e")
        style.configure("TLabel",           background="#1e1e2e", foreground="#cdd6f4", font=("Segoe UI", 10))
        style.configure("TButton",          background="#313244", foreground="#cdd6f4", font=("Segoe UI", 9), borderwidth=0)
        style.map("TButton",                background=[("active","#45475a")])
        style.configure("Accent.TButton",   background="#89b4fa", foreground="#1e1e2e", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",         background=[("active","#74c7ec")])

        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # panels
        left = ttk.Frame(self, width=220)
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        left.columnconfigure(0, weight=1)

        center = ttk.Frame(self)
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)

        right = ttk.Frame(self, width=200)
        right.grid(row=0, column=2, sticky="nsew", padx=(4,8), pady=8)
        right.columnconfigure(0, weight=1)

        # LEFT PANEL: Folder + List
        ttk.Label(left, text="📁 Folder", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
        ttk.Button(left, text="Open Folder", style="Accent.TButton", command=self.open_folder).grid(row=1, column=0, sticky="ew", pady=(0,6))
        
        self.folder_label = ttk.Label(left, text="No folder selected", wraplength=200, foreground="#6c7086", font=("Segoe UI", 8))
        self.folder_label.grid(row=2, column=0, sticky="w", pady=(0,8))

        ttk.Label(left, text="🖼 Images", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,4))
        
        list_frame = ttk.Frame(left)
        list_frame.grid(row=4, column=0, sticky="nsew", pady=(0,8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        self.img_listbox = tk.Listbox(list_frame, bg="#181825", fg="#cdd6f4", selectbackground="#89b4fa", selectforeground="#1e1e2e", borderwidth=0, font=("Segoe UI", 9))
        self.img_listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.img_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.img_listbox.configure(yscrollcommand=sb.set)
        self.img_listbox.bind("<<ListboxSelect>>", self.on_list_select)

        self.img_count_label = ttk.Label(left, text="0 images", foreground="#6c7086", font=("Segoe UI", 8))
        self.img_count_label.grid(row=5, column=0, sticky="w")

        # CENTER PANEL: Nav + Canvas
        nav = ttk.Frame(center)
        nav.grid(row=0, column=0, sticky="ew", pady=(0,6))

        ttk.Button(nav, text="◀ Previous", command=self.prev_image).pack(side="left", padx=(0,4))
        self.nav_label = ttk.Label(nav, text="—", font=("Segoe UI", 9, "bold"))
        self.nav_label.pack(side="left", padx=8)
        ttk.Button(nav, text="Next ▶", command=self.next_image).pack(side="left")

        ttk.Button(nav, text="💾 Save", style="Accent.TButton", command=self.save_current).pack(side="right", padx=(4,0))

        self.canvas = CanvasAnnotation(center, bg="#11111b", cursor="crosshair", width=MAX_CANVAS_W, height=MAX_CANVAS_H)
        self.canvas.grid(row=1, column=0, sticky="nsew")

        # RIGHT PANEL: Classes + YOLO
        ttk.Label(right, text="🎨 Active Class", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,6))

        self.class_var = tk.IntVar(value=0)
        classes_frame = ttk.Frame(right)
        classes_frame.grid(row=1, column=0, sticky="ew", pady=(0,12))

        self.class_name_labels = []
        for i, color in enumerate(COLOR_LIST):
            rb = tk.Radiobutton(classes_frame, text=f" {i:02d}", variable=self.class_var, value=i, bg="#1e1e2e", fg="#cdd6f4", selectcolor=color, font=("Consolas", 9), command=lambda v=i: self.canvas.change_color_id(v))
            rb.grid(row=i, column=0, sticky="w")
            name_lbl = ttk.Label(classes_frame, text="", font=("Segoe UI", 8), foreground="#6c7086")
            name_lbl.grid(row=i, column=1, sticky="w", padx=(4,0))
            self.class_name_labels.append(name_lbl)

        ttk.Separator(right, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=10)
        ttk.Label(right, text="🤖 YOLO", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,6))
        ttk.Button(right, text="Load .pt Model", command=self.load_yolo_model).grid(row=4, column=0, sticky="ew", pady=(0,4))
        
        self.model_label = ttk.Label(right, text="No model", foreground="#6c7086", font=("Segoe UI", 8), wraplength=180)
        self.model_label.grid(row=5, column=0, sticky="w", pady=(0,8))

        ttk.Button(right, text="Predict Current", command=self.predict_current).grid(row=6, column=0, sticky="ew", pady=(0,4))
        ttk.Button(right, text="Predict All", command=self.predict_all).grid(row=7, column=0, sticky="ew")

        # Shortcuts
        ttk.Separator(right, orient="horizontal").grid(row=8, column=0, sticky="ew", pady=10)
        ttk.Label(right, text="⌨ Shortcuts", font=("Segoe UI", 10, "bold")).grid(row=9, column=0, sticky="w", pady=(0,4))
        
        shortcuts = [("← / →", "Navigate"), ("Ctrl+S", "Save"), ("Left Cl.", "Draw Box"), ("Right Cl.", "Delete"), ("Double Cl.", "Change Class")]
        for i, (k, d) in enumerate(shortcuts):
            ttk.Label(right, text=k, foreground="#89b4fa", font=("Consolas", 8)).grid(row=10+i, column=0, sticky="w")
            ttk.Label(right, text=d, foreground="#a6adc8", font=("Segoe UI", 8)).grid(row=10+i, column=1, sticky="w")

        # Status Bar
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, foreground="#6c7086", font=("Segoe UI", 8)).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0,4))

    def _bind_keys(self):
        self.bind("<Left>",      lambda e: self.prev_image())
        self.bind("<Right>",     lambda e: self.next_image())
        self.bind("<Control-s>", lambda e: self.save_current())

    # ------------------------------------------------------------------ Logic
    def open_folder(self):
        path = filedialog.askdirectory()
        if not path: return
        self.folder_path = path
        self.folder_label.config(text=os.path.basename(path))
        self.image_list = sorted([os.path.join(path, f) for f in os.listdir(path) if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS])
        self.img_listbox.delete(0, tk.END)
        for p in self.image_list: self.img_listbox.insert(tk.END, os.path.basename(p))
        self.img_count_label.config(text=f"{len(self.image_list)} images")
        if self.image_list: self._load_index(0)

    def _load_index(self, idx):
        if not self.image_list: return
        idx = max(0, min(idx, len(self.image_list) - 1))
        self.current_idx = idx
        path = self.image_list[idx]
        self.canvas.load_image(path)
        self.img_listbox.selection_clear(0, tk.END)
        self.img_listbox.selection_set(idx)
        self.img_listbox.see(idx)
        self.nav_label.config(text=f"{idx+1}/{len(self.image_list)} - {os.path.basename(path)}")
        self.status_var.set(f"Loaded {os.path.basename(path)}")

    def on_list_select(self, event):
        sel = self.img_listbox.curselection()
        if sel: self._load_index(sel[0])

    def next_image(self): self._load_index(self.current_idx + 1)
    def prev_image(self): self._load_index(self.current_idx - 1)

    def save_current(self):
        skipped = self.canvas.save_annotations()
        msg = f"Saved {os.path.basename(self.canvas.img_path)}"
        if skipped: msg += f" (Skipped {skipped} invalid boxes)"
        self.status_var.set(msg)

    # ------------------------------------------------------------------ YOLO Logic
    def load_yolo_model(self):
        if not YOLO_AVAILABLE:
            messagebox.showerror("Error", "Ultralytics not installed. Run: pip install ultralytics")
            return
        path = filedialog.askopenfilename(filetypes=[("YOLO model", "*.pt")])
        if not path: return
        try:
            self.yolo_model = YOLO(path)
            self.model_label.config(text=f"✅ {os.path.basename(path)}", foreground="#a6e3a1")
            names = self.yolo_model.names
            for i, lbl in enumerate(self.class_name_labels):
                name = names.get(i, "")
                lbl.config(text=name, foreground="#cdd6f4" if name else "#6c7086")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _run_prediction(self, img_path):
        results = self.yolo_model(img_path, verbose=False)
        img = Image.open(img_path)
        iw, ih = img.size
        txt_path = annotation_file_for(img_path)
        with open(txt_path, "w") as f:
            for box in results[0].boxes:
                c = int(box.cls[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, iw, ih)
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")

    def predict_current(self):
        if not self.yolo_model or self.current_idx < 0: return
        self._run_prediction(self.image_list[self.current_idx])
        self.canvas.load_annotations()
        self.status_var.set("Prediction finished.")

    def predict_all(self):
        if not self.yolo_model or not self.image_list: return
        if not messagebox.askyesno("Confirm", "Predict all images? Existing labels will be overwritten."): return
        for i, path in enumerate(self.image_list):
            self._run_prediction(path)
            self.status_var.set(f"Predicting {i+1}/{len(self.image_list)}...")
            self.update_idletasks()
        self.canvas.load_annotations()
        self.status_var.set("Batch prediction complete.")

    def on_close(self):
        if self.canvas.img_path: self.canvas.save_annotations()
        self.destroy()

if __name__ == "__main__":
    app = AnnotationApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()