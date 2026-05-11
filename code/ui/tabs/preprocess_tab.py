import tkinter as tk
from tkinter import filedialog
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import os

class PreprocessTab(ttk.Frame):
    def __init__(self, parent, shared_data):
        super().__init__(parent)
        self.shared_data = shared_data
        self.image_list = []
        self._setup_ui()


    def _setup_ui(self):

        # Define paned window
        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Left side ---
        self.left_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.left_frame, weight=1)

        self.path_frame = ttk.Frame(self.left_frame)
        self.path_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(self.path_frame, text="📁 Open Project", command=self.browse_folder).pack(side=tk.LEFT, fill=tk.X, expand=True) 

        ttk.Label(self.left_frame, text="Project Explorer", font=('Arial', 10, 'bold')).pack(pady=5)
        
        # Treeview 
        self.tree = ttk.Treeview(self.left_frame, show="tree", selectmode="browse")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Scrollbar
        self.scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        ttk.Button(self.left_frame, text="🔄 Refresh", command=self.refresh_tree).pack(fill=tk.X)

        # --- Right side---
        self.right_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.right_frame, weight=4)

        self.nav_frame = ttk.Frame(self.right_frame)
        self.nav_frame.pack(fill=tk.X, pady=5)
        
        self.prev_btn = ttk.Button(self.nav_frame, text="◀ Previous", command=lambda: self.navigate(-1))
        self.prev_btn.pack(side=tk.LEFT, padx=20)

        self.next_btn = ttk.Button(self.nav_frame, text="Next ▶", command=lambda: self.navigate(1))
        self.next_btn.pack(side=tk.RIGHT, padx=20)
        
        self.preview_label = ttk.Label(self.right_frame, text="No Image Selected")
        self.preview_label.pack(expand=True)
        
        # Delete
        self.delete_btn = ttk.Button(self.right_frame, text="❌ Delete Image", command=self.delete_selected)
        self.delete_btn.pack(side=tk.BOTTOM, anchor=tk.SE, padx=20, pady=20)


    # def refresh_list(self):
    #     self.file_listbox.delete(0, tk.END)
    #     self.image_list = self.shared_data.get_captured_images()
    #     for img in self.image_list:
    #         self.file_listbox.insert(tk.END, img)

    def on_image_select(self, event):
        selection = self.file_listbox.curselection()
        if not selection:
            return
        
        filename = self.file_listbox.get(selection[0])
        img_path = os.path.join(self.shared_data.get_folder_path(), "color", filename)
        
        # Show image
        img = Image.open(img_path)
        img.thumbnail((800, 600)) 
        self.photo = ImageTk.PhotoImage(img)
        self.preview_label.config(image=self.photo, text="")

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        base_path = self.shared_data.get_folder_path()
        if not base_path or not os.path.exists(base_path):
            return

        # for subfolder in ["color", "depth", "ir"]:
        #     folder_node = self.tree.insert("", "end", text=subfolder, open=True)

        actual_subfolders = [f.name for f in os.scandir(base_path) if f.is_dir()]
        
        for subfolder in actual_subfolders:
            folder_node = self.tree.insert("", "end", text=subfolder, open=True)
            
            sub_path = os.path.join(base_path, subfolder)
            if os.path.exists(sub_path):
                files = [f for f in os.listdir(sub_path) if f.endswith('.png')]
                for f in sorted(files):  
                    self.tree.insert(folder_node, "end", text=f)
                    

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
            
        item_id = selected_items[0]
        filename = self.tree.item(item_id, "text")
        parent_id = self.tree.parent(item_id)
        
        
        if parent_id:
            folder_name = self.tree.item(parent_id, "text")
            full_path = os.path.join(self.shared_data.get_folder_path(), folder_name, filename)
            
            try:
                img = Image.open(full_path)
                img.thumbnail((800, 600))
                self.photo = ImageTk.PhotoImage(img)
                self.preview_label.config(image=self.photo, text="")
            except Exception as e:
                print(f"Error loading image: {e}")


    def delete_selected(self):
        selected_items = self.tree.selection()

        if not selected_items:
            messagebox.showwarning("Warning", "Please select an image to delete.")
            return
        
        item_id = selected_items[0]
        filename = self.tree.item(item_id, "text")
        parent_id = self.tree.parent(item_id)

        if not parent_id:
            messagebox.showwarning("Warning", "You cannot delete a folder. Please select a specific image.")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{filename}' from all folders?"):
            try:
                self.shared_data.delete_image_group(filename)
                
                self.refresh_tree()
                
                self.preview_label.config(image='', text="Image Deleted")
                
                messagebox.showinfo("Success", "Image group deleted successfully.")
            
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete: {e}")
            

    def browse_folder(self):
        
        selected_path = filedialog.askdirectory(title="Select Project Folder")    
        if selected_path:  
            self.shared_data.set_folder_path(selected_path)
            self.refresh_tree()
            print(f"Project path updated to: {selected_path}")


    def navigate(self, direction):
        
        current_item = self.tree.selection()
        if not current_item:
            return

        parent = self.tree.parent(current_item[0])
        if not parent:
            return
            
        children = self.tree.get_children(parent)
        current_index = children.index(current_item[0])
      
        new_index = current_index + direction
        
        if 0 <= new_index < len(children):
            target_item = children[new_index]
            
            self.tree.selection_set(target_item)
            self.tree.see(target_item)


