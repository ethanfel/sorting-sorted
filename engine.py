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
        """Maps idXXX prefixes to filenames."""
        mapping = {}
        for f in SorterEngine.get_images(path):
            if f.startswith("id") and "_" in f:
                prefix = f.split('_')[0]
                mapping[prefix] = f
        return mapping

    @staticmethod
    def get_sibling_controls(target_path):
        """Finds all folders at the same level as the target."""
        parent = os.path.dirname(target_path)
        if not parent: return []
        try:
            return [os.path.join(parent, d) for d in os.listdir(parent) 
                    if os.path.isdir(os.path.join(parent, d)) and 
                    os.path.abspath(os.path.join(parent, d)) != os.path.abspath(target_path)]
        except: return []

    @staticmethod
    def get_max_id_number(target_path):
        """Scans for highest existing ID to prevent overwriting."""
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
        """Moves target and copies control, syncing the filenames."""
        target_base = os.path.basename(t_path)
        new_name = f"{prefix}{target_base}"
        folders = {
            "standard": ("selected_target", "selected_control"),
            "solo": ("selected_target_solo_woman", "control_selected_solo_woman")
        }
        t_sub, c_sub = folders[mode]
        t_dst, c_dst = os.path.join(target_root, t_sub, new_name), os.path.join(target_root, c_sub, new_name)
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        shutil.move(t_path, t_dst)
        shutil.copy2(c_path, c_dst)
        return t_dst, c_dst

    @staticmethod
    def harmonize_names(t_p, c_p):
        """Renames the control file to match the target filename exactly."""
        t_name = os.path.basename(t_p)
        c_dir = os.path.dirname(c_p)
        new_c_p = os.path.join(c_dir, t_name)
        
        if c_p != new_c_p:
            os.rename(c_p, new_c_p)
            return new_c_p
        return c_p

    @staticmethod
    def move_to_unused_synced(t_p, c_p, t_root, c_root):
        """Moves both to 'unused' subfolders and ensures names match."""
        t_name = os.path.basename(t_p)
        t_un = os.path.join(t_root, "unused", t_name)
        c_un = os.path.join(c_root, "unused", t_name) # Forced harmonization
        
        os.makedirs(os.path.dirname(t_un), exist_ok=True)
        os.makedirs(os.path.dirname(c_un), exist_ok=True)
        
        shutil.move(t_p, t_un)
        shutil.move(c_p, c_un)
        return t_un, c_un

    @staticmethod
    def save_favorite(name, disc_t, rev_t, rev_c):
        """Saves expanded path profile to JSON."""
        favs = SorterEngine.load_favorites()
        favs[name] = {"disc_t": disc_t, "rev_t": rev_t, "rev_c": rev_c}
        with open(SorterEngine.CONFIG_PATH, 'w') as f: json.dump(favs, f, indent=4)

    @staticmethod
    def delete_favorite(name):
        """Deletes a profile from JSON."""
        favs = SorterEngine.load_favorites()
        if name in favs:
            del favs[name]
            with open(SorterEngine.CONFIG_PATH, 'w') as f: json.dump(favs, f, indent=4)

    @staticmethod
    def load_favorites():
        if os.path.exists(SorterEngine.CONFIG_PATH):
            try:
                with open(SorterEngine.CONFIG_PATH, 'r') as f: return json.load(f)
            except: return {}
        return {}

    @staticmethod
    def compress_for_web(path, quality):
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except: return None

    @staticmethod
    def revert_action(action):
        if action['type'] in ['link_standard', 'link_solo', 'unused', 'move']:
            if os.path.exists(action['t_dst']): shutil.move(action['t_dst'], action['t_src'])
            if 'c_dst' in action and os.path.exists(action['c_dst']):
                if 'link' in action['type']: os.remove(action['c_dst'])
                else: shutil.move(action['c_dst'], action['c_src'])