import os
import shutil
import json
from PIL import Image
from io import BytesIO

class SorterEngine:
    CONFIG_PATH = "/app/favorites.json"

    @staticmethod
    def get_images(path):
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        try:
            return sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])
        except: return []

    @staticmethod
    def get_sibling_controls(target_path):
        """Scans for all folders at the same level as the target."""
        parent = os.path.dirname(target_path)
        if not parent: return []
        try:
            return [os.path.join(parent, d) for d in os.listdir(parent) 
                    if os.path.isdir(os.path.join(parent, d)) and 
                    os.path.abspath(os.path.join(parent, d)) != os.path.abspath(target_path)]
        except: return []

    @staticmethod
    def get_max_id_number(target_path):
        """Finds highest ID in target and its expected subfolders."""
        max_id = 0
        search_paths = [target_path, os.path.join(target_path, "selected_target")]
        for p in search_paths:
            if not os.path.exists(p): continue
            for f in os.listdir(p):
                if f.startswith("id") and "_" in f:
                    try:
                        num = int(f[2:].split('_')[0])
                        if num > max_id: max_id = num
                    except: continue
        return max_id

    @staticmethod
    def execute_match(t_path, c_path, target_root, prefix, mode="standard"):
        """
        Moves files to subfolders inside the target folder.
        Renames control to match target filename.
        """
        target_base = os.path.basename(t_path)
        new_name = f"{prefix}{target_base}"
        
        # Folder mapping from original script
        folders = {
            "standard": ("selected_target", "selected_control"),
            "solo": ("selected_target_solo_woman", "control_selected_solo_woman")
        }
        
        t_sub, c_sub = folders[mode]
        t_dst = os.path.join(target_root, t_sub, new_name)
        c_dst = os.path.join(target_root, c_sub, new_name)
        
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        
        shutil.move(t_path, t_dst)
        shutil.copy2(c_path, c_dst)
        return t_dst, c_dst
    
    # ... [revert_action, compress_for_web, load/save_favorites as previously defined] ...

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