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
        """Initializes tables, including the new HISTORY log."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Existing tables...
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, tab1_target TEXT, tab2_target TEXT, tab2_control TEXT, 
             tab4_source TEXT, tab4_out TEXT, mode TEXT, tab5_source TEXT, tab5_out TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS staging_area 
            (original_path TEXT PRIMARY KEY, target_category TEXT, new_name TEXT, is_marked INTEGER DEFAULT 0)''')
            
        # --- NEW: HISTORY TABLE ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS processed_log 
            (source_path TEXT PRIMARY KEY, category TEXT, action_type TEXT)''')
        
        # --- NEW: FOLDER TAGS TABLE (persists tags by folder) ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_tags 
            (folder_path TEXT, filename TEXT, category TEXT, tag_index INTEGER,
             PRIMARY KEY (folder_path, filename))''')
        
        # --- NEW: PROFILE CATEGORIES TABLE (each profile has its own categories) ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS profile_categories 
            (profile TEXT, category TEXT, PRIMARY KEY (profile, category))''')
        
        # --- NEW: PAIRING SETTINGS TABLE ---
        cursor.execute('''CREATE TABLE IF NOT EXISTS pairing_settings 
            (profile TEXT PRIMARY KEY, 
             adjacent_folder TEXT, 
             main_category TEXT, 
             adj_category TEXT, 
             main_output TEXT, 
             adj_output TEXT, 
             time_window INTEGER)''')
        
        # Seed categories if empty (legacy table)
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            for cat in ["_TRASH", "control", "Default", "Action", "Solo"]:
                cursor.execute("INSERT OR IGNORE INTO categories VALUES (?)", (cat,))
        
        conn.commit()
        conn.close()

    # --- 2. PROFILE & PATH MANAGEMENT ---
    @staticmethod
    def save_tab_paths(profile_name, t1_t=None, t2_t=None, t2_c=None, t4_s=None, t4_o=None, mode=None, t5_s=None, t5_o=None,
                       pair_adjacent_folder=None, pair_main_category=None, pair_adj_category=None, 
                       pair_main_output=None, pair_adj_output=None, pair_time_window=None):
        """Updates specific tab paths in the database while preserving others."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Save main profile settings
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
        
        # Save pairing settings if any are provided
        if any(x is not None for x in [pair_adjacent_folder, pair_main_category, pair_adj_category, 
                                        pair_main_output, pair_adj_output, pair_time_window]):
            # Ensure table exists
            cursor.execute('''CREATE TABLE IF NOT EXISTS pairing_settings 
                (profile TEXT PRIMARY KEY, 
                 adjacent_folder TEXT, 
                 main_category TEXT, 
                 adj_category TEXT, 
                 main_output TEXT, 
                 adj_output TEXT, 
                 time_window INTEGER)''')
            
            # Get existing values
            cursor.execute("SELECT * FROM pairing_settings WHERE profile = ?", (profile_name,))
            pair_row = cursor.fetchone()
            
            if not pair_row:
                pair_row = (profile_name, "", "control", "control", "/storage", "/storage", 60)
            
            pair_values = (
                profile_name,
                pair_adjacent_folder if pair_adjacent_folder is not None else pair_row[1],
                pair_main_category if pair_main_category is not None else pair_row[2],
                pair_adj_category if pair_adj_category is not None else pair_row[3],
                pair_main_output if pair_main_output is not None else pair_row[4],
                pair_adj_output if pair_adj_output is not None else pair_row[5],
                pair_time_window if pair_time_window is not None else pair_row[6]
            )
            cursor.execute("INSERT OR REPLACE INTO pairing_settings VALUES (?, ?, ?, ?, ?, ?, ?)", pair_values)
        
        conn.commit()
        conn.close()
    @staticmethod
    def load_batch_parallel(image_paths, quality):
        """
        Multithreaded loader: Compresses multiple images in parallel.
        Returns a dictionary {path: bytes_io}
        """
        import concurrent.futures
        
        results = {}
        
        # Helper function to run in thread
        def process_one(path):
            return path, SorterEngine.compress_for_web(path, quality)

        # Use ThreadPool to parallelize IO-bound tasks
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            # Submit all tasks
            future_to_path = {executor.submit(process_one, p): p for p in image_paths}
            
            # Gather results as they complete
            for future in concurrent.futures.as_completed(future_to_path):
                path, data = future.result()
                results[path] = data
                
        return results

    @staticmethod
    def load_profiles():
        """Loads all workspace presets including pairing settings."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        
        # Ensure pairing_settings table exists
        cursor.execute('''CREATE TABLE IF NOT EXISTS pairing_settings 
            (profile TEXT PRIMARY KEY, 
             adjacent_folder TEXT, 
             main_category TEXT, 
             adj_category TEXT, 
             main_output TEXT, 
             adj_output TEXT, 
             time_window INTEGER)''')
        
        profiles = {}
        for r in rows:
            profile_name = r[0]
            profiles[profile_name] = {
                "tab1_target": r[1], "tab2_target": r[2], "tab2_control": r[3], 
                "tab4_source": r[4], "tab4_out": r[5], "mode": r[6],
                "tab5_source": r[7], "tab5_out": r[8]
            }
            
            # Load pairing settings for this profile
            cursor.execute("SELECT * FROM pairing_settings WHERE profile = ?", (profile_name,))
            pair_row = cursor.fetchone()
            if pair_row:
                profiles[profile_name]["pair_adjacent_folder"] = pair_row[1] or ""
                profiles[profile_name]["pair_main_category"] = pair_row[2] or "control"
                profiles[profile_name]["pair_adj_category"] = pair_row[3] or "control"
                profiles[profile_name]["pair_main_output"] = pair_row[4] or "/storage"
                profiles[profile_name]["pair_adj_output"] = pair_row[5] or "/storage"
                profiles[profile_name]["pair_time_window"] = pair_row[6] or 60
        
        conn.close()
        return profiles

    # --- 3. CATEGORY MANAGEMENT (Profile-based) ---
    @staticmethod
    def get_categories(profile=None):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Ensure table exists
        cursor.execute('''CREATE TABLE IF NOT EXISTS profile_categories 
            (profile TEXT, category TEXT, PRIMARY KEY (profile, category))''')
        
        if profile:
            cursor.execute("SELECT category FROM profile_categories WHERE profile = ? ORDER BY category COLLATE NOCASE ASC", (profile,))
            cats = [r[0] for r in cursor.fetchall()]
            # If no categories for this profile, seed with defaults
            if not cats:
                for cat in ["_TRASH", "control"]:
                    cursor.execute("INSERT OR IGNORE INTO profile_categories VALUES (?, ?)", (profile, cat))
                conn.commit()
                cats = ["_TRASH", "control"]
        else:
            # Fallback to legacy table
            cursor.execute("SELECT name FROM categories ORDER BY name COLLATE NOCASE ASC")
            cats = [r[0] for r in cursor.fetchall()]
        
        conn.close()
        return cats

    @staticmethod
    def add_category(name, profile=None):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        if profile:
            cursor.execute('''CREATE TABLE IF NOT EXISTS profile_categories 
                (profile TEXT, category TEXT, PRIMARY KEY (profile, category))''')
            cursor.execute("INSERT OR IGNORE INTO profile_categories VALUES (?, ?)", (profile, name))
        else:
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
    def clear_staging_area():
        """Clears all items from the staging area."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM staging_area")
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
    def commit_global(output_root, cleanup_mode, operation="Copy", source_root=None, profile=None):
        """Commits ALL staged files and fixes permissions."""
        data = SorterEngine.get_staged_data()
        
        # Save folder tags BEFORE processing (so we can restore them later)
        if source_root:
            SorterEngine.save_folder_tags(source_root, profile)
        
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        if not os.path.exists(output_root): os.makedirs(output_root, exist_ok=True)
        
        # 1. Process all Staged Items
        for old_p, info in data.items():
            if os.path.exists(old_p):
                final_dst = os.path.join(output_root, info['name'])
                
                if os.path.exists(final_dst):
                    root, ext = os.path.splitext(info['name'])
                    c = 1
                    while os.path.exists(final_dst):
                         final_dst = os.path.join(output_root, f"{root}_{c}{ext}")
                         c += 1

                if operation == "Copy":
                    shutil.copy2(old_p, final_dst)
                else:
                    shutil.move(old_p, final_dst)
                
                # --- FIX PERMISSIONS ---
                SorterEngine.fix_permissions(final_dst)
                
                # Log History
                cursor.execute("INSERT OR REPLACE INTO processed_log VALUES (?, ?, ?)", 
                               (old_p, info['cat'], operation))

        # 2. Global Cleanup
        if cleanup_mode != "Keep" and source_root:
            all_imgs = SorterEngine.get_images(source_root, recursive=True)
            for img_p in all_imgs:
                if img_p not in data:
                    if cleanup_mode == "Move to Unused":
                        unused_dir = os.path.join(source_root, "unused")
                        os.makedirs(unused_dir, exist_ok=True)
                        dest_unused = os.path.join(unused_dir, os.path.basename(img_p))
                        
                        shutil.move(img_p, dest_unused)
                        SorterEngine.fix_permissions(dest_unused)
                        
                    elif cleanup_mode == "Delete": 
                        os.remove(img_p)

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
    def compress_for_web(path, quality, target_size=None):
        """
        Loads image, resizes smart, and saves as WebP.
        """
        try:
            with Image.open(path) as img:
                # 1. Convert to RGB (WebP handles RGBA, but RGB is safer for consistency)
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert("RGB")
                
                # 2. Smart Resize (Only if target_size is provided)
                if target_size:
                    # Only resize if the original is actually bigger
                    if img.width > target_size or img.height > target_size:
                        img.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                
                # 3. Save as WebP
                buf = BytesIO()
                # WebP is faster to decode in browser and smaller on disk
                img.save(buf, format="WEBP", quality=quality)
                return buf.getvalue()
        except Exception: 
            return None

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
    def get_processed_log():
        """Retrieves history of processed files."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processed_log")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"cat": r[1], "action": r[2]} for r in rows}

    @staticmethod
    def fix_permissions(path):
        """Forces file to be fully accessible (rwxrwxrwx)."""
        try:
            # 0o777 gives Read, Write, and Execute access to Owner, Group, and Others.
            os.chmod(path, 0o777)
        except Exception:
            pass # Ignore errors if OS doesn't support chmod (e.g. some Windows setups)

    @staticmethod
    def commit_batch(file_list, output_root, cleanup_mode, operation="Copy"):
        """Commits files and fixes permissions."""
        data = SorterEngine.get_staged_data()
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        if not os.path.exists(output_root): os.makedirs(output_root, exist_ok=True)
        
        for file_path in file_list:
            if not os.path.exists(file_path): continue
            
            # --- CASE A: Tagged ---
            if file_path in data and data[file_path]['marked']:
                info = data[file_path]
                final_dst = os.path.join(output_root, info['name'])
                
                # Collision Check
                if os.path.exists(final_dst):
                    root, ext = os.path.splitext(info['name'])
                    c = 1
                    while os.path.exists(final_dst):
                         final_dst = os.path.join(output_root, f"{root}_{c}{ext}")
                         c += 1
                
                # Perform Action
                if operation == "Copy":
                    shutil.copy2(file_path, final_dst)
                else:
                    shutil.move(file_path, final_dst)

                # --- FIX PERMISSIONS ---
                SorterEngine.fix_permissions(final_dst)

                # Update DB
                cursor.execute("DELETE FROM staging_area WHERE original_path = ?", (file_path,))
                cursor.execute("INSERT OR REPLACE INTO processed_log VALUES (?, ?, ?)", 
                               (file_path, info['cat'], operation))
                
            # --- CASE B: Cleanup ---
            elif cleanup_mode != "Keep":
                if cleanup_mode == "Move to Unused":
                    unused_dir = os.path.join(os.path.dirname(file_path), "unused")
                    os.makedirs(unused_dir, exist_ok=True)
                    dest_unused = os.path.join(unused_dir, os.path.basename(file_path))
                    
                    shutil.move(file_path, dest_unused)
                    SorterEngine.fix_permissions(dest_unused) # Fix here too
                    
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
    def delete_category(name, profile=None):
        """Deletes a category and clears any staged tags associated with it."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        if profile:
            cursor.execute("DELETE FROM profile_categories WHERE profile = ? AND category = ?", (profile, name))
        else:
            cursor.execute("DELETE FROM categories WHERE name = ?", (name,))
        
        cursor.execute("DELETE FROM staging_area WHERE target_category = ?", (name,))
        conn.commit()
        conn.close()

    # In engine.py / SorterEngine class
    @staticmethod
    def get_tagged_page_indices(all_images, page_size):
        staged = SorterEngine.get_staged_data()
        if not staged: return set()
        tagged_pages = set()
        staged_keys = set(staged.keys())
        for idx, img_path in enumerate(all_images):
            if img_path in staged_keys:
                tagged_pages.add(idx // page_size)
        return tagged_pages

    # --- 7. FOLDER TAG PERSISTENCE ---
    @staticmethod
    def save_folder_tags(folder_path, profile=None):
        """
        Saves current staging data associated with a folder for later restoration.
        Call this BEFORE clearing the staging area.
        """
        import re
        staged = SorterEngine.get_staged_data()
        if not staged:
            return 0
        
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        
        # Ensure table exists with profile column
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_tags 
            (profile TEXT, folder_path TEXT, filename TEXT, category TEXT, tag_index INTEGER,
             PRIMARY KEY (profile, folder_path, filename))''')
        
        # Check if old schema (without profile) - migrate if needed
        cursor.execute("PRAGMA table_info(folder_tags)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'profile' not in columns:
            cursor.execute("DROP TABLE folder_tags")
            cursor.execute('''CREATE TABLE folder_tags 
                (profile TEXT, folder_path TEXT, filename TEXT, category TEXT, tag_index INTEGER,
                 PRIMARY KEY (profile, folder_path, filename))''')
            conn.commit()
        
        profile = profile or "Default"
        saved_count = 0
        for orig_path, info in staged.items():
            # Only save tags for files that are in this folder (or subfolders)
            if orig_path.startswith(folder_path):
                filename = os.path.basename(orig_path)
                category = info['cat']
                
                # Extract index from the new_name (e.g., "Action_042.jpg" -> 42)
                new_name = info['name']
                match = re.search(r'_(\d+)', new_name)
                tag_index = int(match.group(1)) if match else 0
                
                cursor.execute(
                    "INSERT OR REPLACE INTO folder_tags VALUES (?, ?, ?, ?, ?)",
                    (profile, folder_path, filename, category, tag_index)
                )
                saved_count += 1
        
        conn.commit()
        conn.close()
        return saved_count

    @staticmethod
    def restore_folder_tags(folder_path, all_images, profile=None):
        """
        Restores previously saved tags for a folder back into the staging area.
        Call this when loading/reloading a folder.
        Returns the number of tags restored.
        """
        try:
            conn = sqlite3.connect(SorterEngine.DB_PATH)
            cursor = conn.cursor()
            
            # Ensure table exists with profile column
            cursor.execute('''CREATE TABLE IF NOT EXISTS folder_tags 
                (profile TEXT, folder_path TEXT, filename TEXT, category TEXT, tag_index INTEGER,
                 PRIMARY KEY (profile, folder_path, filename))''')
            
            # Check if old schema (without profile) - migrate if needed
            cursor.execute("PRAGMA table_info(folder_tags)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'profile' not in columns:
                cursor.execute("DROP TABLE folder_tags")
                cursor.execute('''CREATE TABLE folder_tags 
                    (profile TEXT, folder_path TEXT, filename TEXT, category TEXT, tag_index INTEGER,
                     PRIMARY KEY (profile, folder_path, filename))''')
                conn.commit()
            
            profile = profile or "Default"
            
            # Get saved tags for this folder and profile
            cursor.execute(
                "SELECT filename, category, tag_index FROM folder_tags WHERE profile = ? AND folder_path = ?",
                (profile, folder_path)
            )
            saved_tags = {row[0]: {"cat": row[1], "index": row[2]} for row in cursor.fetchall()}
            
            if not saved_tags:
                conn.close()
                return 0
            
            # Build a map of filename -> full path from current images
            filename_to_path = {}
            for img_path in all_images:
                fname = os.path.basename(img_path)
                if fname not in filename_to_path:
                    filename_to_path[fname] = img_path
            
            # Restore tags to staging area
            restored = 0
            for filename, tag_info in saved_tags.items():
                if filename in filename_to_path:
                    full_path = filename_to_path[filename]
                    cursor.execute("SELECT 1 FROM staging_area WHERE original_path = ?", (full_path,))
                    if not cursor.fetchone():
                        ext = os.path.splitext(filename)[1]
                        new_name = f"{tag_info['cat']}_{tag_info['index']:03d}{ext}"
                        cursor.execute(
                            "INSERT OR REPLACE INTO staging_area VALUES (?, ?, ?, 1)",
                            (full_path, tag_info['cat'], new_name)
                        )
                        restored += 1
            
            conn.commit()
            conn.close()
            return restored
        except Exception as e:
            print(f"Error restoring folder tags: {e}")
            return 0

    @staticmethod
    def clear_folder_tags(folder_path):
        """Clears saved tags for a specific folder."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM folder_tags WHERE folder_path = ?", (folder_path,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_saved_folder_tags(folder_path):
        """Returns saved tags for a folder (for debugging/display)."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT filename, category, tag_index FROM folder_tags WHERE folder_path = ?",
            (folder_path,)
        )
        result = {row[0]: {"cat": row[1], "index": row[2]} for row in cursor.fetchall()}
        conn.close()
        return result