import os
import shutil
import json
from PIL import Image
from io import BytesIO

class SorterEngine:
    CONFIG_PATH = "/app/favorites.json"

    @staticmethod
    def get_images(path):
        """Returns list of image files in a directory."""
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        try:
            return sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])
        except: return []

    @staticmethod
    def get_id_mapping(path):
        """Maps idXXX prefixes to full filenames."""
        mapping = {}
        for f in SorterEngine.get_images(path):
            if f.startswith("id") and "_" in f:
                prefix = f.split('_')[0]
                mapping[prefix] = f
        return mapping

    @staticmethod
    def get_max_id_number(folder_path):
        """Finds the highest idXXX_ prefix in a folder."""
        max_id = 0
        if not folder_path or not os.path.exists(folder_path): return 0
        try:
            for f in os.listdir(folder_path):
                if f.startswith("id") and "_" in f:
                    try:
                        num = int(f[2:].split('_')[0])
                        if num > max_id: max_id = num
                    except: continue
        except: pass
        return max_id

    @staticmethod
    def compress_for_web(path, quality):
        """Compresses image to BytesIO for Streamlit display."""
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except: return None

    @staticmethod
    def execute_move(t_path, c_path, t_folder, c_folder, prefix, mode="standard"):
        """Moves target and copies control into subfolders."""
        t_fname = f"{prefix}{os.path.basename(t_path)}"
        c_fname = f"{prefix}{os.path.basename(c_path)}"
        subdirs = {
            "standard": ("selected_target", "selected_control"),
            "solo": ("selected_target_solo_woman", "control_selected_solo_woman")
        }
        t_sub, c_sub = subdirs[mode]
        t_dst, c_dst = os.path.join(t_folder, t_sub, t_fname), os.path.join(c_folder, c_sub, c_fname)
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        shutil.move(t_path, t_dst)
        shutil.copy2(c_path, c_dst)
        return t_dst, c_dst

    @staticmethod
    def revert_action(action):
        """Reverses the last filesystem action."""
        if action['type'] in ['link_standard', 'link_solo']:
            if os.path.exists(action['t_dst']): shutil.move(action['t_dst'], action['t_src'])
            if os.path.exists(action['c_dst']): os.remove(action['c_dst'])
        elif action['type'] == 'unused':
            if os.path.exists(action['t_dst']): shutil.move(action['t_dst'], action['t_src'])
            if os.path.exists(action['c_dst']): shutil.move(action['c_dst'], action['c_src'])

    @staticmethod
    def save_favorite(name, path_t, path_c):
        """Saves a path pair to the JSON config."""
        favs = SorterEngine.load_favorites()
        favs[name] = {"target": path_t, "control": path_c}
        with open(SorterEngine.CONFIG_PATH, 'w') as f:
            json.dump(favs, f)

    @staticmethod
    def load_favorites():
        """Loads path pairs from the JSON config."""
        if os.path.exists(SorterEngine.CONFIG_PATH):
            with open(SorterEngine.CONFIG_PATH, 'r') as f: return json.load(f)
        return {}