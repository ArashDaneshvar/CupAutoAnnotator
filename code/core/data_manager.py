# core/data_manager.py
 
import os
from config import IMAGE_EXTENSIONS, DEFAULT_DATASET_FOLDER
 
 
class DataManager:
 
    def __init__(self):
        self.folder_path = ""
        self.images = []
 
    # ------------------------------------------------------------------
    def set_folder_path(self, path: str):
        self.folder_path = path
 
    def get_folder_path(self) -> str:
        return self.folder_path
 
    # ------------------------------------------------------------------
    def get_image_list(self) -> list:
        """Return sorted list of image filenames in the current folder."""
        if not self.folder_path or not os.path.exists(self.folder_path):
            return []
 
        self.images = sorted([
            f for f in os.listdir(self.folder_path)
            if f.lower().endswith(IMAGE_EXTENSIONS)
        ])
        return self.images
 
    def get_full_path(self, filename: str) -> str:
        return os.path.join(self.folder_path, filename)