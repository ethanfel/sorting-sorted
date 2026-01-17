import os
import shutil
from PIL import Image
from io import BytesIO

class SorterEngine:
    @staticmethod
    def get_images(path):
        """Returns list of image files in a directory."""
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        return sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])

    @staticmethod
    def get_id_mapping(path):
        """Maps idXXX prefixes to full filenames for Tab 1."""
        mapping = {}
        for f in SorterEngine.get_images(path):
            if f.startswith("id") and "_" in f:
                prefix = f.split('_')[0]
                mapping[prefix] = f
        return mapping

    @staticmethod
    def get_max_id_number(folder_path):
        """Finds the highest idXXX_ prefix in a folder to calculate the next ID."""
        max_id = 0
        if not folder_path or not os.path.exists(folder_path):
            return 0
        for f in os.listdir(folder_path):
            if f.startswith("id") and "_" in f:
                try:
                    num_part = f[2:].split('_')[0]
                    num = int(num_part)
                    if num > max_id: max_id = num
                except (ValueError, IndexError):
                    continue
        return max_id

    @staticmethod
    def compress_for_web(path, quality):
        """Reduces image size for browser display to save bandwidth."""
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except Exception:
            return None

    @staticmethod
    def execute_move(t_path, c_path, t_folder, c_folder, prefix, mode="standard"):
        """
        Moves/Renames files based on the script's logic:
        - standard: selected_target / selected_control
        - solo: selected_target_solo_woman / control_selected_solo_woman
        """
        t_fname = f"{prefix}{os.path.basename(t_path)}"
        c_fname = f"{prefix}{os.path.basename(c_path)}"
        
        subdirs = {
            "standard": ("selected_target", "selected_control"),
            "solo": ("selected_target_solo_woman", "control_selected_solo_woman")
        }
        
        t_sub, c_sub = subdirs[mode]
        t_dst = os.path.join(t_folder, t_sub, t_fname)
        c_dst = os.path.join(c_folder, c_sub, c_fname)
        
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        
        shutil.move(t_path, t_dst)
        shutil.copy2(c_path, c_dst) # Copy control as per script logic
        
        return t_dst, c_dst

    @staticmethod
    def revert_action(action):
        """Reverses the last recorded action from the history stack."""
        if action['type'] in ['link_standard', 'link_solo']:
            if os.path.exists(action['t_dst']):
                shutil.move(action['t_dst'], action['t_src'])
            if os.path.exists(action['c_dst']):
                os.remove(action['c_dst'])
        elif action['type'] == 'unused':
            if os.path.exists(action['t_dst']):
                shutil.move(action['t_dst'], action['t_src'])
            if os.path.exists(action['c_dst']):
                shutil.move(action['c_dst'], action['c_src'])