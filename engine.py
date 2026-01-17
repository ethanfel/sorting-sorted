import os
import shutil
import sqlite3
import json
from PIL import Image
from io import BytesIO

class SorterEngine:
    # Path to the SQLite database file stored in the app volume
    DB_PATH = "/app/sorter_database.db"

    @staticmethod
    def init_db():
        """Initializes the SQLite database and creates all required tables."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Table for Profiles: Stores paths for Discovery, Review, and Output
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, disc_t TEXT, rev_t TEXT, rev_c TEXT, path_out TEXT, mode TEXT)''')
        
        # Table for Folder IDs: Maps source folder paths to persistent numeric IDs
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        
        # Table for Categories: Stores sorting subfolder names for Tab 4
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        
        # Seed default categories if the table is empty
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            defaults = ["_TRASH", "Default", "Action", "Solo"]
            for cat in defaults:
                cursor.execute("INSERT INTO categories VALUES (?)", (cat,))
        
        conn.commit()
        conn.close()

    @staticmethod
    def get_images(path):
        """Standard image scanner for directories."""
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path):
            return []
        return sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])

    @staticmethod
    def get_id_mapping(path):
        """Maps idXXX prefixes to lists of filenames to detect collisions."""
        mapping = {}
        for f in SorterEngine.get_images(path):
            if f.startswith("id") and "_" in f:
                prefix = f.split('_')[0]
                if prefix not in mapping:
                    mapping[prefix] = []
                mapping[prefix].append(f)
        return mapping

    @staticmethod
    def get_max_id_number(target_path):
        """Scans directories to find the highest existing ID prefix."""
        max_id = 0
        search_paths = [target_path, os.path.join(target_path, "selected_target")]
        for p in search_paths:
            if not os.path.exists(p):
                continue
            for f in os.listdir(p):
                if f.startswith("id") and "_" in f:
                    try:
                        num = int(f[2:].split('_')[0])
                        if num > max_id:
                            max_id = num
                    except:
                        continue
        return max_id

    @staticmethod
    def get_folder_id(source_path):
        """Retrieves or generates a unique, persistent ID for a specific folder."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT folder_id FROM folder_ids WHERE path = ?", (source_path,))
        result = cursor.fetchone()
        
        if result:
            fid = result[0]
        else:
            cursor.execute("SELECT MAX(folder_id) FROM folder_ids")
            row = cursor.fetchone()
            fid = (row[0] + 1) if row and row[0] else 1
            cursor.execute("INSERT INTO folder_ids VALUES (?, ?)", (source_path, fid))
            conn.commit()
            
        conn.close()
        return fid

    @staticmethod
    def harmonize_names(t_p, c_p):
        """Renames the control file to match the target filename exactly."""
        t_name = os.path.basename(t_p)
        c_dir = os.path.dirname(c_p)
        new_c_p = os.path.join(c_dir, t_name)
        
        # Handle filename collisions during harmonization
        if os.path.exists(new_c_p) and c_p != new_c_p:
            base, ext = os.path.splitext(t_name)
            new_c_p = os.path.join(c_dir, f"{base}_alt{ext}")
            
        os.rename(c_p, new_c_p)
        return new_c_p

    @staticmethod
    def re_id_file(old_path, new_id_prefix):
        """Changes the idXXX_ portion of a filename to resolve collisions."""
        dir_name = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)
        name_no_id = old_name.split('_', 1)[1] if '_' in old_name else old_name
        new_name = f"{new_id_prefix}{name_no_id}"
        new_path = os.path.join(dir_name, new_name)
        os.rename(old_path, new_path)
        return new_path

    @staticmethod
    def move_to_unused_synced(t_p, c_p, t_root, c_root):
        """Moves a pair to 'unused' folders with synchronized filenames."""
        t_name = os.path.basename(t_p)
        t_un = os.path.join(t_root, "unused", t_name)
        c_un = os.path.join(c_root, "unused", t_name)
        
        os.makedirs(os.path.dirname(t_un), exist_ok=True)
        os.makedirs(os.path.dirname(c_un), exist_ok=True)
        
        shutil.move(t_p, t_un)
        shutil.move(c_p, c_un)
        return t_un, c_un

    @staticmethod
    def restore_from_unused(t_p, c_p, t_root, c_root):
        """Restores a pair from 'unused' back to main 'selected' folders."""
        t_name = os.path.basename(t_p)
        t_dst = os.path.join(t_root, "selected_target", t_name)
        c_dst = os.path.join(c_root, "selected_control", t_name)
        
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        
        shutil.move(t_p, t_dst)
        shutil.move(c_p, c_dst)
        return t_dst, c_dst

    @staticmethod
    def execute_match(t_path, c_path, target_root, prefix, mode="standard"):
        """Standard matching: moves target and copies control with synced names."""
        target_base = os.path.basename(t_path)
        new_name = f"{prefix}{target_base}"
        
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

    @staticmethod
    def get_categories():
        """Retrieves categories from the database for Tab 4."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories ORDER BY name ASC")
        cats = [r[0] for r in cursor.fetchall()]
        conn.close()
        return cats

    @staticmethod
    def add_category(name):
        """Adds a new category button to the database."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (name,))
        conn.commit()
        conn.close()

    @staticmethod
    def save_profile(name, disc_t, rev_t, rev_c, path_out, mode):
        """Saves a multi-path preset to the database."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?)", 
                       (name, disc_t, rev_t, rev_c, path_out, mode))
        conn.commit()
        conn.close()

    @staticmethod
    def load_profiles():
        """Returns all stored profiles."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"disc_t": r[1], "rev_t": r[2], "rev_c": r[3], "path_out": r[4], "mode": r[5]} for r in rows}

    @staticmethod
    def delete_profile(name):
        """Removes a profile from the database."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profiles WHERE name = ?", (name,))
        conn.commit()
        conn.close()

    @staticmethod
    def compress_for_web(path, quality):
        """Compresses images into JPEG format for fast UI rendering."""
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except:
            return None

    @staticmethod
    def revert_action(action):
        """Undoes the previous file operation."""
        if action['type'] in ['link_standard', 'link_solo', 'unused', 'cat_move', 'move']:
            if os.path.exists(action['t_dst']):
                shutil.move(action['t_dst'], action['t_src'])
            if 'c_dst' in action and os.path.exists(action['c_dst']):
                # Remove copies created during matching, restore moves
                if 'link' in action['type']:
                    os.remove(action['c_dst'])
                else:
                    shutil.move(action['c_dst'], action['c_src'])