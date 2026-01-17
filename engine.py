import os
import shutil
import sqlite3
from PIL import Image
from io import BytesIO

class SorterEngine:
    DB_PATH = "/app/sorter_database.db"

    # --- DATABASE INITIALIZATION ---
    @staticmethod
    def init_db():
        """Initializes SQLite tables for Profiles, Folder IDs, and Categories."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Profile table supports 7 columns for independent paths and naming mode
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, 
             tab1_target TEXT, 
             tab2_target TEXT, tab2_control TEXT, 
             tab4_source TEXT, tab4_out TEXT,
             mode TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        
        # Seed default categories if empty
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            for cat in ["_TRASH", "Default", "Action", "Solo"]:
                cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (cat,))
        
        conn.commit()
        conn.close()

    # --- PROFILE & PATH MANAGEMENT ---
    @staticmethod
    def save_tab_paths(profile_name, t1_t=None, t2_t=None, t2_c=None, t4_s=None, t4_o=None, mode=None):
        """Updates specific tab paths while preserving others in the DB."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE name = ?", (profile_name,))
        row = cursor.fetchone()
        
        if not row:
            row = (profile_name, "/storage", "/storage", "/storage", "/storage", "/storage", "id")
            
        new_values = (
            profile_name,
            t1_t if t1_t is not None else row[1],
            t2_t if t2_t is not None else row[2],
            t2_c if t2_c is not None else row[3],
            t4_s if t4_s is not None else row[4],
            t4_o if t4_o is not None else row[5],
            mode if mode is not None else row[6]
        )
        cursor.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?)", new_values)
        conn.commit()
        conn.close()

    @staticmethod
    def load_profiles():
        """Loads all workspace presets from the database."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"tab1_target": r[1], "tab2_target": r[2], "tab2_control": r[3], 
                       "tab4_source": r[4], "tab4_out": r[5], "mode": r[6]} for r in rows}

    # --- CATEGORY MANAGEMENT (WITH DISK RENAMING) ---
    @staticmethod
    def get_categories():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories ORDER BY name ASC")
        cats = [r[0] for r in cursor.fetchall()]
        conn.close()
        return cats

    @staticmethod
    def add_category(name):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (name,))
        conn.commit()
        conn.close()

    @staticmethod
    def rename_category(old_name, new_name, output_base_path):
        """Renames category in DB and renames the physical folder on disk."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # 1. Update Database
        cursor.execute("UPDATE categories SET name = ? WHERE name = ?", (new_name, old_name))
        
        # 2. Rename on Disk
        old_path = os.path.join(output_base_path, old_name)
        new_path = os.path.join(output_base_path, new_name)
        
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)
        
        conn.commit()
        conn.close()

    @staticmethod
    def sync_categories_from_disk(output_path):
        """Scans output directory and adds subfolders as DB categories."""
        if not output_path or not os.path.exists(output_path): return 0
        existing_folders = [d for d in os.listdir(output_path) 
                            if os.path.isdir(os.path.join(output_path, d)) 
                            and not d.startswith(".")]
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        added = 0
        for folder in existing_folders:
            cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (folder,))
            if cursor.rowcount > 0: added += 1
        conn.commit()
        conn.close()
        return added

    # --- IMAGE & ID SCANNING ---
    @staticmethod
    def get_images(path, recursive=False):
        """Standard image scanner with optional subfolder support."""
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        image_list = []
        if recursive:
            for root, _, files in os.walk(path):
                for f in files:
                    if f.lower().endswith(exts): image_list.append(os.path.join(root, f))
        else:
            for f in os.listdir(path):
                if f.lower().endswith(exts): image_list.append(os.path.join(path, f))
        return sorted(image_list)

    @staticmethod
    def get_id_mapping(path):
        """Groups files by idXXX_ prefix to detect collisions."""
        mapping = {}
        images = SorterEngine.get_images(path, recursive=False)
        for f in images:
            fname = os.path.basename(f)
            if fname.startswith("id") and "_" in fname:
                prefix = fname.split('_')[0]
                if prefix not in mapping: mapping[prefix] = []
                mapping[prefix].append(fname)
        return mapping

    @staticmethod
    def get_max_id_number(target_path):
        """Finds the highest idXXX_ prefix in a directory."""
        max_id = 0
        if not target_path or not os.path.exists(target_path): return 0
        for f in os.listdir(target_path):
            if f.startswith("id") and "_" in f:
                try:
                    num = int(f[2:].split('_')[0])
                    if num > max_id: max_id = num
                except: continue
        return max_id

    @staticmethod
    def get_folder_id(source_path):
        """Retrieves or generates a persistent ID for a specific folder."""
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

    # --- FILE MANIPULATION ---
    @staticmethod
    def harmonize_names(t_p, c_p):
        t_name = os.path.basename(t_p)
        new_c_p = os.path.join(os.path.dirname(c_p), t_name)
        if os.path.exists(new_c_p) and c_p != new_c_p:
            root, ext = os.path.splitext(t_name)
            new_c_p = os.path.join(os.path.dirname(c_p), f"{root}_alt{ext}")
        os.rename(c_p, new_c_p)
        return new_c_p

    @staticmethod
    def re_id_file(old_path, new_id_prefix):
        dir_name = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)
        name_no_id = old_name.split('_', 1)[1] if '_' in old_name else old_name
        new_name = f"{new_id_prefix}{name_no_id}"
        new_path = os.path.join(dir_name, new_name)
        os.rename(old_path, new_path)
        return new_path

    @staticmethod
    def move_to_unused_synced(t_p, c_p, t_root, c_root):
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
        t_name = os.path.basename(t_p)
        t_dst = os.path.join(t_root, "selected_target", t_name)
        c_dst = os.path.join(c_root, "selected_control", t_name)
        os.makedirs(os.path.dirname(t_dst), exist_ok=True)
        os.makedirs(os.path.dirname(c_dst), exist_ok=True)
        shutil.move(t_p, t_dst)
        shutil.move(c_p, c_dst)
        return t_dst, c_dst

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
        if action['type'] in ['unused', 'cat_move', 'move']:
            if os.path.exists(action['t_dst']): shutil.move(action['t_dst'], action['t_src'])
            if 'c_dst' in action and os.path.exists(action['c_dst']):
                shutil.move(action['c_dst'], action['c_src'])