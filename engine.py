import os
import shutil
import json
from PIL import Image
from io import BytesIO

class SorterEngine:
    CONFIG_PATH = "/app/favorites.json"

    # ... [get_images, get_id_mapping, get_max_id_number, compress_for_web remain the same] ...

    @staticmethod
    def execute_move(t_path, c_path, t_folder, c_folder, prefix, mode="standard"):
        """
        Moves target and copies control. 
        Renames control to match target's name exactly.
        """
        # We use the target's filename as the base for BOTH
        target_base_name = os.path.basename(t_path)
        
        t_fname = f"{prefix}{target_base_name}"
        c_fname = f"{prefix}{target_base_name}" # Now identical to target name
        
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
        shutil.copy2(c_path, c_dst)
        return t_dst, c_dst

    @staticmethod
    def move_to_unused_synced(t_p, c_p, t_folder, c_folder):
        """Moves both to unused, renaming control to match target name."""
        t_name = os.path.basename(t_p)
        
        t_un = os.path.join(t_folder, "unused", t_name)
        c_un = os.path.join(c_folder, "unused", t_name) # Renamed to match target
        
        os.makedirs(os.path.dirname(t_un), exist_ok=True)
        os.makedirs(os.path.dirname(c_un), exist_ok=True)
        
        shutil.move(t_p, t_un)
        shutil.move(c_p, c_un)
        return t_un, c_un

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