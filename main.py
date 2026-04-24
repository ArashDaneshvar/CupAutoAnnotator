import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import os
import threading
import queue
import random
import math

# Matplotlib embedded
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False

# Ultralytics
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

def hex_to_rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)

def has_annotations(img_path):
    txt = annotation_file_for(img_path)
    if not os.path.exists(txt):
        return False
    with open(txt) as f:
        return any(line.strip() for line in f)

def make_symlink(src, dst):
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

    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        self.mode = "idle"

        self.axis_x = None
        self.axis_y = None

        self.temp_rect   = None
        self.start_point = None

        self.selected_rect  = None
        self.start_rect     = None
        self.anchor_point   = None
        self.mov_direction  = None
        self.temp_click     = None

        self.img_path          = None
        self.img_ref           = None
        self.background_img_id = None
        self.starting_point_img = (20,20)
        self.img_draw_w        = 1
        self.img_draw_h        = 1

        self.annotation_list_id = []
        self.overlay_refs       = {}

        self.id_color        = 0
        self.default_outline = "black"
        self.fill_alpha      = 80

        self.bind("<Enter>",           self.on_enter)
        self.bind("<Leave>",           self.on_exit)
        self.bind("<Button-1>",        self.on_left_click)
        self.bind("<Button-3>",        self.on_right_click)
        self.bind("<Motion>",          self.on_move)
        self.bind("<Double-Button-1>", self.on_double_click)

    def reset_state(self):
        if self.temp_rect:
            self.delete(self.temp_rect)
        if self.selected_rect is not None:
            self.itemconfigure(self.selected_rect, state="normal")
        self.mode = "idle"
        self.temp_rect = self.start_point = None
        self.selected_rect = self.start_rect = None
        self.anchor_point = self.mov_direction = self.temp_click = None

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

    def create_rectangle_start(self, x, y):
        self.mode        = "create"
        self.start_point = (x, y)
        self.temp_rect   = self.create_rectangle(
            x, y, x, y,
            fill=COLOR_LIST[self.id_color],
            outline=self.default_outline,
            width=2, stipple="gray12"
        )

    def preview_rectangle(self, x, y):
        x0, y0 = self.start_point
        self.coords(self.temp_rect, *adjust_coords(x, y, x0, y0))

    def finish_rectangle(self):
        if self.temp_rect is None: return
        x1, y1, x2, y2 = self.coords(self.temp_rect)
        if abs(x2-x1) < 4 or abs(y2-y1) < 4:
            self.delete(self.temp_rect)
        else:
            self.itemconfigure(self.temp_rect, stipple="gray12",
                               fill=COLOR_LIST[self.id_color])
            self.annotation_list_id.append(self.temp_rect)
            self._create_transparent_fill(self.temp_rect)
        self.temp_rect = self.start_point = None
        self.mode = "idle"

    def select_rectangle(self, obj, x, y):
        x1, y1, x2, y2 = self.coords(obj)
        direction = detect_box_zone(x, y, x1, y1, x2, y2)
        if direction is None: return
        self.mode = "move"
        self.selected_rect = obj
        self.itemconfigure(obj, state="hidden")
        self.start_rect    = (x1, y1, x2, y2)
        self.mov_direction = direction
        self.temp_click    = (x, y)
        color = self.itemcget(obj, "fill")
        self.temp_rect = self.create_rectangle(
            x1, y1, x2, y2,
            fill=color, outline=self.default_outline, width=2, stipple="gray12"
        )
        anchor_map = {
            (1,1,0,0): (x2,y2), (0,1,1,0): (x1,y2),
            (1,0,0,1): (x2,y1), (0,0,1,1): (x1,y1),
            (1,0,0,0): (x2,None), (0,0,1,0): (x1,None),
            (0,1,0,0): (None,y2), (0,0,0,1): (None,y1),
        }
        self.anchor_point = anchor_map.get(direction, None)

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
            x1+=dx; y1+=dy; x2+=dx; y2+=dy
        self.coords(self.temp_rect, x1, y1, x2, y2)

    def finish_modification(self):
        self.annotation_list_id.remove(self.selected_rect)
        self._remove_overlay(self.selected_rect)
        self.delete(self.selected_rect)
        self.itemconfigure(self.temp_rect, state="normal", stipple="gray12")
        self.annotation_list_id.append(self.temp_rect)
        self._create_transparent_fill(self.temp_rect)
        self.temp_rect = self.selected_rect = self.mov_direction = None
        self.anchor_point = self.temp_click = None
        self.mode = "idle"

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
            self.reset_state(); return
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

    def get_top_object(self, x, y):
        objs = list(self.find_overlapping(x, y, x, y))
        for excl in (self.background_img_id, self.axis_x, self.axis_y):
            if excl in objs: objs.remove(excl)
        return objs[-1] if objs else None

    def load_image(self, img_path):
        if self.img_path:
            self.save_annotations()
        self._clear_canvas_annotations()
        self.img_path = img_path
        if not img_path or not os.path.exists(img_path): return
        img = Image.open(img_path)
        w, h= img.size
        w, h = w + 2*self.starting_point_img[0], h + 2*self.starting_point_img[1]
        scale = min(MAX_CANVAS_W/w, MAX_CANVAS_H/h, 1.0)
        nw, nh = int(w*scale), int(h*scale)
        self.img_ref    = ImageTk.PhotoImage(img.resize((nw, nh), Image.LANCZOS))
        self.img_draw_w = nw
        self.img_draw_h = nh
        self.config(width=nw + 2*self.starting_point_img[0], height=nh + 2*self.starting_point_img[1])
        if self.background_img_id:
            self.delete(self.background_img_id)
        self.background_img_id = self.create_image(self.starting_point_img[0], self.starting_point_img[1], image=self.img_ref, anchor="nw")
        self.load_annotations()

    def _clear_canvas_annotations(self):
        for rid in self.annotation_list_id:
            self._remove_overlay(rid)
            self.delete(rid)
        self.annotation_list_id.clear()
        self.reset_state()

    def _translate_coord_for_save(self,x1,y1,x2,y2):
        return x1 - self.starting_point_img[0], y1 - self.starting_point_img[1], x2 - self.starting_point_img[0], y2 - self.starting_point_img[1]
    
    def _translate_coord_for_load(self,x1,y1,x2,y2):
        return x1 + self.starting_point_img[0], y1 + self.starting_point_img[1], x2 + self.starting_point_img[0], y2 + self.starting_point_img[1]

    def save_annotations(self):
        if not self.img_path: return 0
        w, h = self.img_draw_w, self.img_draw_h
        skipped = 0
        with open(annotation_file_for(self.img_path), "w") as f:
            for rid in self.annotation_list_id:
                x1, y1, x2, y2 = self.coords(rid)
                x1, y1, x2, y2 = self._translate_coord_for_save(x1,y1,x2,y2)
                x1 = max(0.0, min(x1, w))
                y1 = max(0.0, min(y1, h))
                x2 = max(0.0, min(x2, w))
                y2 = max(0.0, min(y2, h))
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, w, h)
                if nx2-nx1 < 1e-4 or ny2-ny1 < 1e-4:
                    skipped += 1; continue
                c = COLOR_LIST.index(self.itemcget(rid, "fill"))
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")
        return skipped

    def load_annotations(self):
        if not self.img_path: return
        txt = annotation_file_for(self.img_path)
        if not os.path.exists(txt): return
        w, h = self.img_draw_w, self.img_draw_h
        with open(txt) as f:
            for line in f:
                result = from_yolo_into_coord(line)
                if result is None: continue
                c, x1, y1, x2, y2 = result
                if not (0<=x1<=1 and 0<=x2<=1 and 0<=y1<=1 and 0<=y2<=1): continue
                ax1, ay1, ax2, ay2 = denormalize_coords(x1, y1, x2, y2, w, h)
                ax1, ay1, ax2, ay2 = self._translate_coord_for_load(ax1, ay1, ax2, ay2)
                color = COLOR_LIST[c] if 0<=c<len(COLOR_LIST) else COLOR_LIST[0]
                rid = self.create_rectangle(
                    ax1, ay1, ax2, ay2,
                    fill=color, outline=self.default_outline, width=2, stipple="gray12"
                )
                self.annotation_list_id.append(rid)
                self._create_transparent_fill(rid)

    def change_color_id(self, color_id):
        if 0 <= color_id < len(COLOR_LIST):
            self.id_color = color_id

    def _create_transparent_fill(self, rid):
        coords = self.coords(rid)
        if not coords: return
        x1, y1, x2, y2 = (int(v) for v in coords)
        w, h = max(x2-x1, 1), max(y2-y1, 1)
        rgba  = hex_to_rgba(self.itemcget(rid, "fill"), self.fill_alpha)
        img   = Image.new("RGBA", (w, h), rgba)
        photo = ImageTk.PhotoImage(img)
        oid   = self.create_image(x1, y1, image=photo, anchor="nw")
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

        self.folder_path = None
        self.image_list  = []
        self.current_idx = -1
        self.yolo_model  = None

        self.ft_model_path  = None
        self.ft_output_path = None
        self.ft_queue       = queue.Queue()
        self.ft_training    = False
        self.ft_stop_flag   = False
        self.ft_thread      = None
        self.ft_metrics     = {
            "epoch":[], "box_loss":[], "cls_loss":[], "dfl_loss":[],
            "precision":[], "recall":[], "mAP50":[]
        }

        self._build_ui()
        self._bind_keys()

    # ==========================================================================
    # UI
    # ==========================================================================

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
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

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, foreground=FG2,
                  font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", padx=10, pady=(2,4))

    # --------------------------------------------------------------------------
    def _build_annotation_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🖊  Annotation")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        left   = ttk.Frame(tab, width=210)
        left.grid(row=0, column=0, sticky="nsew", padx=(8,4), pady=8)
        left.columnconfigure(0, weight=1)

        center = ttk.Frame(tab)
        center.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)

        right  = ttk.Frame(tab, width=190)
        right.grid(row=0, column=2, sticky="nsew", padx=(4,8), pady=8)
        right.columnconfigure(0, weight=1)

        # LEFT
        ttk.Label(left, text="📁  Folder",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,4))
        ttk.Button(left, text="Open Folder", style="Accent.TButton",
                   command=self.open_folder).grid(row=1, column=0, sticky="ew", pady=(0,4))
        self.folder_label = ttk.Label(left, text="No folder", foreground="#6c7086",
                                      font=("Segoe UI", 8), wraplength=195)
        self.folder_label.grid(row=2, column=0, sticky="w", pady=(0,8))

        ttk.Label(left, text="🖼  Images",
                  font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,4))

        lf = ttk.Frame(left)
        lf.grid(row=4, column=0, sticky="nsew")
        lf.columnconfigure(0, weight=1)
        lf.rowconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

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

        self.img_count_label = ttk.Label(left, text="0 images", foreground="#6c7086",
                                          font=("Segoe UI", 8))
        self.img_count_label.grid(row=5, column=0, sticky="w", pady=(4,0))

        # CENTER
        nav = ttk.Frame(center)
        nav.grid(row=0, column=0, sticky="ew", pady=(0,6))
        ttk.Button(nav, text="◀  Prev", command=self.prev_image).pack(side="left", padx=(0,4))
        self.nav_label = ttk.Label(nav, text="—", font=("Segoe UI", 9, "bold"))
        self.nav_label.pack(side="left", padx=8)
        ttk.Button(nav, text="Next  ▶", command=self.next_image).pack(side="left")
        ttk.Button(nav, text="💾  Save", style="Accent.TButton",
                   command=self.save_current).pack(side="right")

        self.canvas = CanvasAnnotation(
            center, bg="#11111b", cursor="crosshair",
            highlightthickness=1, highlightbackground="#313244",
            width=MAX_CANVAS_W, height=MAX_CANVAS_H
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")

        # RIGHT
        ttk.Label(right, text="🎨  Active Class",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0,6))

        self.class_var = tk.IntVar(value=0)
        cf = ttk.Frame(right)
        cf.grid(row=1, column=0, sticky="ew", pady=(0,10))
        cf.columnconfigure(2, weight=1)

        self.class_name_labels = []
        for i, color in enumerate(COLOR_LIST):
            rb = tk.Radiobutton(
                cf, text=f" {i:02d}", variable=self.class_var, value=i,
                bg="#1e1e2e", fg="#cdd6f4", selectcolor=color,
                font=("Consolas", 9), activebackground="#313244",
                activeforeground="#cdd6f4",
                command=lambda v=i: self.canvas.change_color_id(v)
            )
            rb.grid(row=i, column=0, sticky="w")
            dot = tk.Label(cf, bg=color, width=2, relief="flat")
            dot.grid(row=i, column=1, padx=(3,0))
            nl = ttk.Label(cf, text="", font=("Segoe UI", 8), foreground="#6c7086")
            nl.grid(row=i, column=2, sticky="w", padx=(4,0))
            self.class_name_labels.append(nl)

        ttk.Separator(right, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=8)
        ttk.Label(right, text="🤖  YOLO",
                  font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(0,6))
        ttk.Button(right, text="Load .pt Model",
                   command=self.load_yolo_model).grid(row=4, column=0, sticky="ew", pady=(0,4))
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
            ("← / →",   "Navigate"),
            ("Ctrl+S",  "Save"),
            ("L-Click", "Draw"),
            ("R-Click", "Delete/Cancel"),
            ("Dbl Cl.", "Change class"),
            ("p",       "Predict current"),
        ]):
            ttk.Label(right, text=k, foreground="#89b4fa",
                      font=("Consolas", 8)).grid(row=10+i, column=0, sticky="w")
            ttk.Label(right, text=d, foreground="#a6adc8",
                      font=("Segoe UI", 8)).grid(row=10+i, column=1, sticky="w", padx=(4,0))

    # --------------------------------------------------------------------------
    def _build_training_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="🔧  Training")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        # ── scrollable left panel ────────────────────────────────────────
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
        win_id = canvas_scroll.create_window((0,0), window=left, anchor="nw")

        def _on_frame_configure(e):
            canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        def _on_canvas_configure(e):
            canvas_scroll.itemconfig(win_id, width=e.width)

        left.bind("<Configure>", _on_frame_configure)
        canvas_scroll.bind("<Configure>", _on_canvas_configure)

        r = 0
        def sep(row):
            ttk.Separator(left, orient="horizontal").grid(
                row=row, column=0, columnspan=2, sticky="ew", pady=6)

        def lbl(text, row, bold=False):
            font = ("Segoe UI", 10 if bold else 9, "bold" if bold else "normal")
            ttk.Label(left, text=text, font=font).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(0 if bold else 1, 4 if bold else 1))

        def entry(label, key, default, row):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0,8))
            var = tk.StringVar(value=str(default))
            self.ft_vars[key] = var
            ttk.Entry(left, textvariable=var, width=10).grid(row=row, column=1, sticky="w")

        def check(label, key, default, row):
            var = tk.BooleanVar(value=default)
            self.ft_bool_vars[key] = var
            ttk.Checkbutton(left, text=label, variable=var).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=1)

        self.ft_vars = {}
        self.ft_bool_vars = {}

        lbl("⚙  Configuration", r, bold=True); r+=1

        lbl("Base model (.pt)", r); r+=1
        self.ft_model_label = ttk.Label(left, text="No model selected",
                                         foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_model_label.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,2)); r+=1
        ttk.Button(left, text="Choose model…",
                   command=self.ft_pick_model).grid(row=r, column=0, columnspan=2,
                   sticky="ew", pady=(0,8)); r+=1

        lbl("Output folder", r); r+=1
        self.ft_out_label = ttk.Label(left, text="No folder selected",
                                       foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_out_label.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,2)); r+=1
        ttk.Button(left, text="Choose output…",
                   command=self.ft_pick_output).grid(row=r, column=0, columnspan=2,
                   sticky="ew", pady=(0,8)); r+=1

        self.ft_data_info = ttk.Label(left, text="Open a folder in Annotation tab first.",
                                       foreground="#6c7086", font=("Segoe UI", 8), wraplength=250)
        self.ft_data_info.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0,10)); r+=1

        sep(r); r+=1
        lbl("📊  Hyperparameters", r, bold=True); r+=1
        entry("Epochs",           "epochs",        50,    r); r+=1
        entry("Batch size",       "batch",         16,    r); r+=1
        entry("Image size",       "imgsz",         640,   r); r+=1
        entry("Val split %",      "val_split",     20,    r); r+=1
        entry("LR0 (initial)",    "lr0",           0.01,  r); r+=1
        entry("LRf (final ratio)","lrf",           0.01,  r); r+=1
        entry("Momentum",         "momentum",      0.937, r); r+=1
        entry("Weight decay",     "weight_decay",  0.0005,r); r+=1
        entry("Warmup epochs",    "warmup_epochs", 3,     r); r+=1
        entry("Patience",         "patience",      50,    r); r+=1
        entry("Freeze layers",    "freeze",        0,     r); r+=1

        sep(r); r+=1
        lbl("🔀  Training Options", r, bold=True); r+=1
        check("Augmentation",      "augment",    True,  r); r+=1
        check("Mixed precision",   "amp",        True,  r); r+=1
        check("Cache images",      "cache",      False, r); r+=1
        check("Use pretrained",    "pretrained", True,  r); r+=1
        check("Cosine LR schedule","cos_lr",     False, r); r+=1
        check("Close mosaic (end)","close_mosaic",True, r); r+=1

        sep(r); r+=1
        lbl("🏷  Class Names", r, bold=True); r+=1
        ttk.Label(left, text="One per line — index = row position",
                  foreground="#6c7086", font=("Segoe UI", 8)).grid(
            row=r, column=0, columnspan=2, sticky="w"); r+=1
        self.ft_class_text = tk.Text(
            left, bg="#181825", fg="#cdd6f4", insertbackground="#cdd6f4",
            font=("Consolas", 9), height=7, relief="flat", wrap="none",
            width=28
        )
        self.ft_class_text.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2,8)); r+=1

        sep(r); r+=1
        self.ft_start_btn = ttk.Button(left, text="▶  Start Training",
                                        style="Accent.TButton", command=self.ft_start)
        self.ft_start_btn.grid(row=r, column=0, columnspan=2, sticky="ew"); r+=1
        self.ft_stop_btn = ttk.Button(left, text="⏹  Stop",
                                       style="Red.TButton",
                                       command=self.ft_stop, state="disabled")
        self.ft_stop_btn.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(4,0)); r+=1

        self.ft_progress_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.ft_progress_var,
                  foreground="#a6e3a1", font=("Segoe UI", 8), wraplength=250).grid(
            row=r, column=0, columnspan=2, sticky="w", pady=(6,0)); r+=1

        # ── right: charts + log ─────────────────────────────────────────
        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(4,8), pady=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=3)
        right.rowconfigure(1, weight=1)

        if MPL_AVAILABLE:
            self.ft_fig = Figure(figsize=(7, 4), dpi=90, facecolor="#1e1e2e")
            self.ft_fig.subplots_adjust(hspace=0.55, wspace=0.38)
            self.ft_axes = {}
            specs = [
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

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    # ==========================================================================
    # ANNOTATION LOGIC
    # ==========================================================================

    def _bind_keys(self):
        self.bind("<Left>",      lambda e: self.prev_image())
        self.bind("<Right>",     lambda e: self.next_image())
        self.bind("<Control-s>", lambda e: self.save_current())
        self.bind("<p>",         lambda e: self.predict_current())

    def open_folder(self):
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
        if not self.image_list: return
        idx = max(0, min(idx, len(self.image_list)-1))
        self.current_idx = idx
        path = self.image_list[idx]
        self.canvas.load_image(path)
        self.img_listbox.selection_clear(0, tk.END)
        self.img_listbox.selection_set(idx)
        self.img_listbox.see(idx)
        self.nav_label.config(text=f"{idx+1}/{len(self.image_list)}  —  {os.path.basename(path)}")
        self.status_var.set(f"Loaded {os.path.basename(path)}")

    def on_list_select(self, event):
        sel = self.img_listbox.curselection()
        if sel: self._load_index(sel[0])

    def next_image(self): self._load_index(self.current_idx + 1)
    def prev_image(self):  self._load_index(self.current_idx - 1)

    def save_current(self):
        skipped = self.canvas.save_annotations()
        msg = f"Saved {os.path.basename(self.canvas.img_path or '')}"
        if skipped: msg += f"  ⚠ {skipped} invalid boxes skipped"
        self.status_var.set(msg)

    def load_yolo_model(self):
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
        if not self.yolo_model: return
        names = self.yolo_model.names
        for i, lbl in enumerate(self.class_name_labels):
            name = names.get(i, "")
            lbl.config(text=name, foreground="#cdd6f4" if name else "#6c7086")
        self.ft_class_text.delete("1.0", "end")
        for i in range(len(names)):
            self.ft_class_text.insert("end", names.get(i, f"class_{i}") + "\n")

    def _run_prediction(self, img_path):
        results = self.yolo_model(img_path, verbose=False)
        img = Image.open(img_path)
        iw, ih = img.size
        with open(annotation_file_for(img_path), "w") as f:
            for box in results[0].boxes:
                c = int(box.cls[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                nx1, ny1, nx2, ny2 = normalize_coords(x1, y1, x2, y2, iw, ih)
                f.write(convert_into_yolo(c, nx1, ny1, nx2, ny2) + "\n")

    def predict_current(self):
        if not self.yolo_model or self.current_idx < 0: return
        self._run_prediction(self.image_list[self.current_idx])
        self.canvas._clear_canvas_annotations()
        self.canvas.load_annotations()
        self.status_var.set("Prediction done.")

    def predict_all(self):
        if not self.yolo_model or not self.image_list: return
        if not messagebox.askyesno("Confirm",
                "Predict all? Existing labels will be overwritten."): return
        for i, p in enumerate(self.image_list):
            self._run_prediction(p)
            self.status_var.set(f"Predicting {i+1}/{len(self.image_list)}…")
            self.update_idletasks()
        self.canvas._clear_canvas_annotations()
        self.canvas.load_annotations()
        self.status_var.set("Batch prediction complete.")

    # ==========================================================================
    # TRAINING LOGIC
    # ==========================================================================

    def _on_tab_change(self, _event=None):
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
                pass

    def ft_pick_output(self):
        path = filedialog.askdirectory(title="Training output folder")
        if path:
            self.ft_output_path = path
            self.ft_out_label.config(text=path, foreground="#cdd6f4")

    def _ft_get_class_names(self):
        raw = self.ft_class_text.get("1.0", "end").strip()
        if not raw: return []
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]

    def _ft_prepare_dataset(self, src_folder, out_folder, val_pct, annotated_imgs):
        imgs = list(annotated_imgs)
        if not imgs:
            raise ValueError("No annotated images found.")
        random.shuffle(imgs)
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
                make_symlink(os.path.abspath(p),
                             os.path.join(img_dir, name))
                make_symlink(os.path.abspath(label_src),
                             os.path.join(lbl_dir, stem + ".txt"))
        return n_train, n_val

    def _ft_write_yaml(self, out_folder, class_names):
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
        if not YOLO_AVAILABLE:
            messagebox.showerror("Error", "ultralytics not installed."); return
        if not self.ft_model_path:
            messagebox.showwarning("Missing", "Choose a base model first."); return
        if not self.folder_path:
            messagebox.showwarning("Missing", "Open an annotated folder first."); return
        if not self.ft_output_path:
            messagebox.showwarning("Missing", "Choose an output folder first."); return
        if self.ft_training: return

        class_names = self._ft_get_class_names()
        if not class_names:
            messagebox.showwarning("Missing classes",
                "Add at least one class name in the Class Names editor."); return

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

        bp = {k: v.get() for k, v in self.ft_bool_vars.items()}

        annotated = [img for img in self.image_list if has_annotations(img)]
        if not annotated:
            messagebox.showwarning("No data", "No annotated images found."); return

        # reset
        self.ft_training  = True
        self.ft_stop_flag = False
        self.ft_start_btn.config(state="disabled")
        self.ft_stop_btn.config(state="normal")
        self.ft_progress_var.set("Preparing dataset…")
        self._ft_clear_log()
        for key in self.ft_metrics: self.ft_metrics[key].clear()

        dataset_dir = os.path.join(self.ft_output_path, "dataset_split")

        # capture locals for thread
        _epochs   = epochs
        _batch    = batch
        _imgsz    = imgsz
        _val_split = val_split
        _lr0      = lr0
        _lrf      = lrf
        _momentum = momentum
        _wd       = wd
        _warmup   = warmup
        _patience = patience
        _freeze   = freeze
        _bp       = bp
        _class_names = class_names
        _annotated   = annotated

        def _train():
            try:
                self.ft_queue.put(("log",
                    f"Dataset: {len(_annotated)} annotated images"))
                n_train, n_val = self._ft_prepare_dataset(
                    self.folder_path, dataset_dir, _val_split, _annotated)
                yaml_path = self._ft_write_yaml(dataset_dir, _class_names)
                self.ft_queue.put(("log",
                    f"Split: {n_train} train / {n_val} val  |  "
                    f"{len(_class_names)} classes  |  symlinks created"))
                self.ft_queue.put(("log", f"YAML: {yaml_path}"))

                model = YOLO(self.ft_model_path)

                def on_epoch_end(trainer):
                    if self.ft_stop_flag:
                        trainer.epoch = trainer.epochs
                    ep   = trainer.epoch + 1
                    loss = trainer.loss_items
                    met  = trainer.metrics or {}
                    bl = float(loss[0]) if loss is not None and len(loss) > 0 else 0.0
                    cl = float(loss[1]) if loss is not None and len(loss) > 1 else 0.0
                    dl = float(loss[2]) if loss is not None and len(loss) > 2 else 0.0
                    mp = float(met.get("metrics/mAP50(B)", 0))
                    pr = float(met.get("metrics/precision(B)", 0))
                    rc = float(met.get("metrics/recall(B)", 0))
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

                train_kwargs = dict(
                    data          = yaml_path,
                    epochs        = _epochs,
                    batch         = _batch,
                    imgsz         = _imgsz,
                    lr0           = _lr0,
                    lrf           = _lrf,
                    momentum      = _momentum,
                    weight_decay  = _wd,
                    warmup_epochs = _warmup,
                    patience      = _patience,
                    augment       = _bp["augment"],
                    amp           = _bp["amp"],
                    cache         = _bp["cache"],
                    pretrained    = _bp["pretrained"],
                    cos_lr        = _bp["cos_lr"],
                    close_mosaic  = 10 if _bp["close_mosaic"] else 0,
                    project       = self.ft_output_path,
                    name          = "finetune",
                    exist_ok      = True,
                    verbose       = False,
                )
                if _freeze > 0:
                    train_kwargs["freeze"] = _freeze

                model.train(**train_kwargs)
                best = os.path.join(self.ft_output_path, "finetune", "weights", "best.pt")
                self.ft_queue.put(("done", best))

            except Exception as e:
                self.ft_queue.put(("error", str(e)))

        self.ft_thread = threading.Thread(target=_train, daemon=True)
        self.ft_thread.start()
        self._ft_poll()

    def ft_stop(self):
        self.ft_stop_flag = True
        self.ft_progress_var.set("Stopping after current epoch…")
        self._ft_log_write("⏹  Stop requested — finishing current epoch…")

    def _ft_poll(self):
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
            pass
        if self.ft_stop_flag and self.ft_thread and not self.ft_thread.is_alive():
            self._ft_done(None); return
        self.after(250, self._ft_poll)

    def _ft_update_charts(self):
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
                ax.fill_between(epochs, data, alpha=0.12, color=color)
        self.ft_fig.canvas.draw_idle()

    def _ft_done(self, best_path):
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
        self.ft_training = False
        self.ft_start_btn.config(state="normal")
        self.ft_stop_btn.config(state="disabled")
        self.ft_progress_var.set("❌  Error")
        self._ft_log_write(f"\n❌  ERROR: {msg}")
        messagebox.showerror("Training error", msg)

    def _ft_log_write(self, msg):
        self.ft_log.configure(state="normal")
        self.ft_log.insert("end", msg + "\n")
        self.ft_log.see("end")
        self.ft_log.configure(state="disabled")

    def _ft_clear_log(self):
        self.ft_log.configure(state="normal")
        self.ft_log.delete("1.0", "end")
        self.ft_log.configure(state="disabled")

    # ==========================================================================
    # CLOSE
    # ==========================================================================

    def on_close(self):
        if self.canvas.img_path:
            self.canvas.save_annotations()
        self.destroy()


if __name__ == "__main__":
    app = AnnotationApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()