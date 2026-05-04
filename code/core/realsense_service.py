# core/realsense_service.py
 
import pyrealsense2 as rs
import numpy as np
import os
import time
import cv2
 
from config import (
    CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS, CAMERA_TIMEOUT_MS
)
 
 
class RealsenseService:
 
    def __init__(self, width=CAMERA_WIDTH, height=CAMERA_HEIGHT, fps=CAMERA_FPS):
        self.width = width
        self.height = height
        self.fps = fps
 
        # Step 2: is_streaming now lives here, not in the UI
        self.is_streaming = False
 
        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.align = None
 
        self.config.enable_stream(rs.stream.depth, width, height, rs.format.z16, fps)
        self.config.enable_stream(rs.stream.color, width, height, rs.format.bgr8, fps)
        self.config.enable_stream(rs.stream.infrared, width, height, rs.format.y8, fps)
 
    # ------------------------------------------------------------------
    def start(self):
        """Start the RealSense pipeline."""
        try:
            self.pipeline.start(self.config)
            self.align = rs.align(rs.stream.color)
            self.is_streaming = True
            print("RealSense pipeline started.")
        except Exception as e:
            self.is_streaming = False
            print(f"Error starting pipeline: {e}")
            raise   # let the caller (UI) decide how to show the error
 
    # ------------------------------------------------------------------
    def stop(self):
        """Stop the RealSense pipeline safely."""
        if self.pipeline and self.is_streaming:
            try:
                self.pipeline.stop()
                print("RealSense pipeline stopped.")
            except Exception as e:
                print(f"Error stopping pipeline: {e}")
            finally:
                # Always mark as stopped even if stop() threw
                self.is_streaming = False
 
    # ------------------------------------------------------------------
    def get_frames(self):
        """
        Grab one aligned frame set from the camera.
        Returns a dict with 'color', 'depth', 'ir' numpy arrays,
        or None if anything goes wrong.
        """
        # Step 4: timeout + full null-check on every stream
        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=CAMERA_TIMEOUT_MS)
        except RuntimeError as e:
            print(f"Camera timeout or frame error: {e}")
            return None
 
        aligned_frames = self.align.process(frames)
 
        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()
        ir_frame    = frames.get_infrared_frame(1)   # fixed: also checked
 
        if not color_frame or not depth_frame or not ir_frame:
            print("Warning: one or more frames missing, skipping.")
            return None
 
        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())
        ir_image    = np.asanyarray(ir_frame.get_data())
 
        return {
            "color": color_image,
            "depth": depth_image,
            "ir":    ir_image,
        }
 
    # ------------------------------------------------------------------
    def save_data(self, frame_dict, base_path, count):
        """
        Save color / depth / ir frames to <base_path>/<stream>/<filename>.
        Returns the filename on success, None if any write fails.
        """
        filename = f"{int(time.time())}_{count}.png"
        all_ok = True
 
        for stream_name in ("color", "depth", "ir"):
            folder = os.path.join(base_path, stream_name)
            os.makedirs(folder, exist_ok=True)
 
            path    = os.path.join(folder, filename)
            success = cv2.imwrite(path, frame_dict[stream_name])
 
            # Step 4: verify every write
            if not success:
                print(f"Warning: failed to save {stream_name} frame → {path}")
                all_ok = False
 
        return filename if all_ok else None
 


