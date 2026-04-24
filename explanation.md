# YOLO Annotation Tool – Code Explanation

## Overview

This script implements a desktop application in Python using **Tkinter** to annotate images in **YOLO format** (normalized bounding boxes).
It also includes optional integration with **Ultralytics YOLO** for automatic annotation generation.

---

## Code Structure

The code is organized into four main sections:

1. Imports and Constants
2. Utility Functions
3. `CanvasAnnotation` Class
4. `AnnotationApp` Class (Main Application)

---

## 1. Imports and Constants

### Libraries Used

* `tkinter`: graphical user interface
* `PIL (Pillow)`: image handling
* `os`: file system operations
* `ultralytics.YOLO` (optional): AI model for object detection

### Key Constants

* `SUPPORTED_EXTENSIONS`: supported image formats
* `COLOR_LIST`: list of colors mapped to classes
* `MAX_CANVAS_W`, `MAX_CANVAS_H`: maximum canvas dimensions

---

## 2. Utility Functions

These functions handle coordinate transformations and conversions.

### Coordinate Handling

* `adjust_coords()`: ensures proper coordinate ordering (min/max)
* `normalize_coords()`: converts pixel coordinates to [0,1]
* `denormalize_coords()`: converts normalized values back to pixels

### YOLO Format

* `convert_into_yolo()`: converts bounding box into YOLO format

  ```
  class x_center y_center width height
  ```
* `from_yolo_into_coord()`: converts YOLO format back to box coordinates

### Box Interaction

* `detect_box_zone()`: detects which part of a box is clicked (corner, edge, or center)

---

## 3. Class `CanvasAnnotation`

This is the core component responsible for drawing and editing bounding boxes.

### Internal State

* `mode`: current interaction mode (`idle`, `create`, `move`)
* `annotation_list_id`: list of bounding box IDs
* `overlay_refs`: references to semi-transparent overlays

---

### Box Creation

* Left click:

  * first click starts drawing
  * second click finalizes the box
* Very small boxes are discarded

---

### Box Modification

* Click on a box to select it
* Drag:

  * corners → resize
  * center → move

---

### Deletion

* Right click on a box removes it

---

### Class Change

* Double click on a box changes its class/color

---

### Transparent Overlay

Each box includes a semi-transparent RGBA fill:

* created using `PIL.Image`
* improves visual clarity

---

### Image Handling

* `load_image()`: loads and scales an image
* `save_annotations()`: saves annotations to a `.txt` file
* `load_annotations()`: loads existing annotations

---

## 4. Class `AnnotationApp`

This class manages the GUI and overall application logic.

---

### UI Layout

The interface is divided into three panels:

#### Left Panel

* folder selection
* image list

#### Center Panel

* annotation canvas
* image navigation

#### Right Panel

* class selection (colors)
* YOLO controls
* shortcuts

---

### Navigation

* `next_image()` / `prev_image()`
* updates the canvas accordingly

---

### Saving

* `save_current()`: saves annotations for the current image

---

## YOLO Integration

### Model Loading

* `load_yolo_model()`
* loads a `.pt` file
* updates class names in the UI

---

### Prediction

* `predict_current()`: runs detection on the current image
* `predict_all()`: batch processing on all images

---

### Workflow

1. YOLO model generates bounding boxes
2. Coordinates are converted to YOLO format
3. Results are saved into `.txt` files

---

## Keyboard Shortcuts

| Key          | Action          |
| ------------ | --------------- |
| Left / Right | Navigate images |
| Ctrl + S     | Save            |
| Left Click   | Draw box        |
| Right Click  | Delete box      |
| Double Click | Change class    |

---

## Application Exit

* `on_close()`: automatically saves annotations before closing

---

## Conclusion

This tool provides a complete annotation workflow with:

* Bounding box creation and editing
* YOLO format support
* Graphical user interface
* AI-assisted labeling via YOLO

---

Additional improvements could include zoom functionality, undo/redo support, or packaging as a standalone executable.
