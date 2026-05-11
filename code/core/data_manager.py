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
    

    #------------------------------------------------------------------
    def get_captured_images(self):
        
        if not self.folder_path:
            return []
            
        color_path = os.path.join(self.folder_path, "color")
        if not os.path.exists(color_path):
            return []
        
        files = [f for f in os.listdir(color_path) if f.endswith('.png')]
        return sorted(files)

    def get_subfolders(self):
        if not self.folder_path or not os.path.exists(self.folder_path):
            return []
        return [f for f in os.listdir(self.folder_path) if os.path.isdir(os.path.join(self.folder_path, f))]

    def delete_image_group(self, filename):
        for subfolder in ["color", "depth", "ir"]:
            file_path = os.path.join(self.folder_path, subfolder, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        return True
    
    #------------------------------------------------------------------
    def create_new_project(self, project_name):
        
        base_path = DEFAULT_DATASET_FOLDER
        full_path = os.path.join(base_path, project_name)

        os.makedirs(full_path, exist_ok=True)

        os.makedirs(os.path.join(full_path, "color"), exist_ok=True)
        os.makedirs(os.path.join(full_path, "depth"),exist_ok=True)
        os.makedirs(os.path.join(full_path, "ir"),exist_ok=True)

        self.current_folder = full_path

        print(f"Project will be saved at: {os.path.abspath(full_path)}")

        return full_path


    
