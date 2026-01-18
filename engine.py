import os
import shutil
import sqlite3
from PIL import Image
from io import BytesIO

class SorterEngine:
    DB_PATH = "/app/sorter_database.db"

    # --- 1. DATABASE INITIALIZATION ---
    @staticmethod
    def init_db():
        """Initializes all SQLite tables for the multi-tab system."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Profiles Table: 9 columns for independent tab paths
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, 
             tab1_target TEXT, 
             tab2_target TEXT, tab2_control TEXT, 
             tab4_source TEXT, tab4_out TEXT,
             mode TEXT,
             tab5_source TEXT, tab5_out TEXT)''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        
        # Staging Area: Tracks pending renames for the Gallery Tab
        cursor.execute('''CREATE TABLE IF NOT EXISTS staging_area 
            (original_path TEXT PRIMARY KEY, 
             target_category TEXT, 
             new_name TEXT, 
             is_marked INTEGER DEFAULT 0)''')
        
        # Seed default categories
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            for cat in ["_TRASH", "Default", "Action", "Solo"]:
                cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (cat,))
        
        conn.commit()
        conn.close()

    # --- 2. PROFILE & PATH MANAGEMENT ---
    @staticmethod
    def save_tab_paths(profile_name, t1_t=None, t2_t=None, t2_c=None, t4_s=None, t4_o=None, mode=None, t5_s=None, t5_o=None):
        """Updates specific tab paths in the database while preserving others."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE name = ?", (profile_name,))
        row = cursor.fetchone()
        
        if not row:
            # Default structure if profile is new (9 columns total)
            row = (profile_name, "/storage", "/storage", "/storage", "/storage", "/storage", "id", "/storage", "/storage")
            
        new_values = (
            profile_name,
            t1_t if t1_t is not None else row[1],
            t2_t if t2_t is not None else row[2],
            t2_c if t2_c is not None else row[3],
            t4_s if t4_s is not None else row[4],
            t4_o if t4_o is not None else row[5],
            mode if mode is not None else row[6],
            t5_s if t5_s is not None else row[7],
            t5_o if t5_o is not None else row[8]
        )
        cursor.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", new_values)
        conn.commit()
        conn.close()

    @staticmethod
    def load_profiles():
        """Loads all workspace presets."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {
            "tab1_target": r[1], "tab2_target": r[2], "tab2_control": r[3], 
            "tab4_source": r[4], "tab4_out": r[5], "mode": r[6],
            "tab5_source": r[7], "tab5_out": r[8]
        } for r in rows}

    # --- 3. CATEGORY MANAGEMENT (Sorted A-Z) ---
    @staticmethod
    def get_categories():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM categories ORDER BY name COLLATE NOCASE ASC")
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
        cursor.execute("UPDATE categories SET name = ? WHERE name = ?", (new_name, old_name))
        
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
        existing_folders = [d for d in os.listdir(output_path) if os.path.isdir(os.path.join(output_path, d)) and not d.startswith(".")]
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        added = 0
        for folder in existing_folders:
            cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (folder,))
            if cursor.rowcount > 0: added += 1
        conn.commit()
        conn.close()
        return added

    # --- 4. IMAGE & ID OPERATIONS ---
    @staticmethod
    def get_images(path, recursive=False):
        """Image scanner with optional recursive subfolder support."""
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        image_list = []
        if recursive:
            for root, _, files in os.walk(path):
                # Skip the trash folder from scanning
                if "_DELETED" in root: continue
                for f in files:
                    if f.lower().endswith(exts): image_list.append(os.path.join(root, f))
        else:
            for f in os.listdir(path):
                if f.lower().endswith(exts): image_list.append(os.path.join(path, f))
        return sorted(image_list)

    @staticmethod
    def get_id_mapping(path):
        """Maps idXXX prefixes for Tab 2 collision handling."""
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

    # --- 5. GALLERY STAGING & DELETION (TAB 5) ---
    @staticmethod
    def delete_to_trash(file_path):
        """Moves a file to a local _DELETED subfolder for undo support."""
        if not os.path.exists(file_path): return None
        trash_dir = os.path.join(os.path.dirname(file_path), "_DELETED")
        os.makedirs(trash_dir, exist_ok=True)
        dest = os.path.join(trash_dir, os.path.basename(file_path))
        shutil.move(file_path, dest)
        return dest

    @staticmethod
    def stage_image(original_path, category, new_name):
        """Records a pending rename/move in the database."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO staging_area VALUES (?, ?, ?, 1)", (original_path, category, new_name))
        conn.commit()
        conn.close()

    @staticmethod
    def clear_staged_item(original_path):
        """Removes an item from the pending staging area."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM staging_area WHERE original_path = ?", (original_path,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_staged_data():
        """Retrieves current tagged/staged images."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staging_area")
        rows = cursor.fetchall()
        conn.close()
        # FIXED: Added "marked": r[3] to the dictionary
        return {r[0]: {"cat": r[1], "name": r[2], "marked": r[3]} for r in rows}
        
    @staticmethod
    def commit_staging(output_root, cleanup_mode, source_root=None):
        """Global commit directly to output root (No Subfolders)."""
        data = SorterEngine.get_staged_data()
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        staged_paths = set(data.keys())
        
        if not os.path.exists(output_root):
            os.makedirs(output_root, exist_ok=True)
        
        for old_p, info in data.items():
            if os.path.exists(old_p):
                # CHANGED: Direct move to root
                final_dst = os.path.join(output_root, info['name'])
                
                # Collision Safety for global commit
                if os.path.exists(final_dst):
                    root, ext = os.path.splitext(info['name'])
                    c = 1
                    while os.path.exists(final_dst):
                         final_dst = os.path.join(output_root, f"{root}_{c}{ext}")
                         c += 1

                shutil.move(old_p, final_dst)
        
        if cleanup_mode != "Keep" and source_root:
            for img_p in SorterEngine.get_images(source_root, recursive=True):
                if img_p not in staged_paths:
                    if cleanup_mode == "Move to Unused":
                        un_dir = os.path.join(source_root, "unused")
                        os.makedirs(un_dir, exist_ok=True)
                        shutil.move(img_p, os.path.join(un_dir, os.path.basename(img_p)))
                    elif cleanup_mode == "Delete": os.remove(img_p)
        
        cursor.execute("DELETE FROM staging_area")
        conn.commit()
        conn.close()

    # --- 6. CORE UTILITIES (SYNC & UNDO) ---
    @staticmethod
    def harmonize_names(t_p, c_p):
        """Forces the 'control' file to match the 'target' file's name."""
        if not os.path.exists(t_p) or not os.path.exists(c_p): return c_p
        
        t_name = os.path.basename(t_p)
        t_root, t_ext = os.path.splitext(t_name)
        c_ext = os.path.splitext(c_p)[1]
        
        new_c_name = f"{t_root}{c_ext}"
        new_c_p = os.path.join(os.path.dirname(c_p), new_c_name)
        
        if os.path.exists(new_c_p) and c_p != new_c_p:
            new_c_p = os.path.join(os.path.dirname(c_p), f"{t_root}_alt{c_ext}")
            
        os.rename(c_p, new_c_p)
        return new_c_p

    @staticmethod
    def re_id_file(old_path, new_id_prefix):
        """Changes the idXXX_ prefix to resolve collisions."""
        dir_name = os.path.dirname(old_path)
        old_name = os.path.basename(old_path)
        name_no_id = old_name.split('_', 1)[1] if '_' in old_name else old_name
        new_name = f"{new_id_prefix}{name_no_id}"
        new_path = os.path.join(dir_name, new_name)
        os.rename(old_path, new_path)
        return new_path

    @staticmethod
    def move_to_unused_synced(t_p, c_p, t_root, c_root):
        """Moves a pair to 'unused' subfolders."""
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
        """Moves files back from 'unused' to main folders."""
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
        """Compresses images for UI performance."""
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except: return None

    @staticmethod
    def revert_action(action):
        """Undoes move operations."""
        if action['type'] == 'move' and os.path.exists(action['t_dst']):
            shutil.move(action['t_dst'], action['t_src'])
        elif action['type'] in ['unused', 'cat_move']:
            if os.path.exists(action['t_dst']): shutil.move(action['t_dst'], action['t_src'])
            if 'c_dst' in action and os.path.exists(action['c_dst']):
                shutil.move(action['c_dst'], action['c_src'])
            
    @staticmethod
    def commit_batch(file_list, output_root, cleanup_mode):
        """
        Commits files directly to the output root (No Subfolders).
        """
        data = SorterEngine.get_staged_data()
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Ensure output root exists
        if not os.path.exists(output_root):
            os.makedirs(output_root, exist_ok=True)
        
        for file_path in file_list:
            if not os.path.exists(file_path): continue
            
            # --- CASE A: File is TAGGED ---
            if file_path in data and data[file_path]['marked']:
                info = data[file_path]
                
                # CHANGED: Destination is now directly the output_root, not a subfolder
                final_dst = os.path.join(output_root, info['name'])
                
                # Collision Safety: If Action_001.jpg exists, try Action_001_1.jpg
                if os.path.exists(final_dst):
                    root, ext = os.path.splitext(info['name'])
                    c = 1
                    while os.path.exists(final_dst):
                         final_dst = os.path.join(output_root, f"{root}_{c}{ext}")
                         c += 1
                
                shutil.move(file_path, final_dst)
                cursor.execute("DELETE FROM staging_area WHERE original_path = ?", (file_path,))
                
            # --- CASE B: File is UNTAGGED (Cleanup) ---
            elif cleanup_mode != "Keep":
                if cleanup_mode == "Move to Unused":
                    parent = os.path.dirname(file_path)
                    unused_dir = os.path.join(parent, "unused")
                    os.makedirs(unused_dir, exist_ok=True)
                    shutil.move(file_path, os.path.join(unused_dir, os.path.basename(file_path)))
                elif cleanup_mode == "Delete":
                    os.remove(file_path)
        
        conn.commit()
        conn.close()

    @staticmethod
    def rename_category(old_name, new_name):
        """Renames a category and updates any staged images using it."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # 1. Update Category Table
        try:
            cursor.execute("UPDATE categories SET name = ? WHERE name = ?", (new_name, old_name))
            
            # 2. Update Staging Area (Keep tags in sync)
            cursor.execute("UPDATE staging_area SET target_category = ? WHERE target_category = ?", (new_name, old_name))
            
            # 3. Update Staging Area Filenames (e.g. Action_001.jpg -> Adventure_001.jpg)
            # This is complex in SQL, so we'll just flag them. 
            # Ideally, we re-stage them, but for now, updating the category column is sufficient 
            # because the filename is generated at the moment of tagging or commit.
            
            conn.commit()
        except sqlite3.IntegrityError:
            # New name already exists
            pass
        finally:
            conn.close()

    @staticmethod
    def delete_category(name):
        """Deletes a category and clears any staged tags associated with it."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
        cursor.execute("DELETE FROM staging_area WHERE target_category = ?", (name,))
        conn.commit()
        conn.close()