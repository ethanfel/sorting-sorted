import os
import shutil
import sqlite3
from PIL import Image
from io import BytesIO

class SorterEngine:
    DB_PATH = "/app/sorter_database.db"

    @staticmethod
    def init_db():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, tab1_target TEXT, tab2_target TEXT, tab2_control TEXT, 
             tab4_source TEXT, tab4_out TEXT, mode TEXT, tab5_source TEXT, tab5_out TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS staging_area 
            (original_path TEXT PRIMARY KEY, target_category TEXT, new_name TEXT, is_marked INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()

    @staticmethod
    def save_tab_paths(profile_name, t1_t=None, t2_t=None, t2_c=None, t4_s=None, t4_o=None, mode=None, t5_s=None, t5_o=None):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles WHERE name = ?", (profile_name,))
        row = cursor.fetchone()
        if not row: row = (profile_name, "/storage", "/storage", "/storage", "/storage", "/storage", "id", "/storage", "/storage")
        new_values = (profile_name, t1_t or row[1], t2_t or row[2], t2_c or row[3], t4_s or row[4], t4_o or row[5], mode or row[6], t5_s or row[7], t5_o or row[8])
        cursor.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", new_values)
        conn.commit()
        conn.close()

    @staticmethod
    def load_profiles():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"tab1_target": r[1], "tab2_target": r[2], "tab2_control": r[3], "tab4_source": r[4], "tab4_out": r[5], "mode": r[6], "tab5_source": r[7], "tab5_out": r[8]} for r in rows}

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
    def delete_to_trash(file_path):
        if not os.path.exists(file_path): return None
        trash_dir = os.path.join(os.path.dirname(file_path), "_DELETED")
        os.makedirs(trash_dir, exist_ok=True)
        dest = os.path.join(trash_dir, os.path.basename(file_path))
        shutil.move(file_path, dest)
        return dest

    @staticmethod
    def stage_image(original_path, category, new_name):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO staging_area VALUES (?, ?, ?, 1)", (original_path, category, new_name))
        conn.commit()
        conn.close()

    @staticmethod
    def clear_staged_item(original_path):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM staging_area WHERE original_path = ?", (original_path,))
        conn.commit()
        conn.close()

    @staticmethod
    def get_staged_data():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staging_area")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"cat": r[1], "name": r[2]} for r in rows}

    @staticmethod
    def commit_staging(output_root, cleanup_mode, source_root=None):
        data = SorterEngine.get_staged_data()
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        staged_paths = set(data.keys())
        for old_p, info in data.items():
            if os.path.exists(old_p):
                dest_dir = os.path.join(output_root, info['cat'])
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(old_p, os.path.join(dest_dir, info['name']))
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

    @staticmethod
    def get_images(path, recursive=False):
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        image_list = []
        if not path or not os.path.exists(path): return []
        if recursive:
            for root, _, files in os.walk(path):
                for f in files:
                    if f.lower().endswith(exts) and "_DELETED" not in root:
                        image_list.append(os.path.join(root, f))
        else:
            image_list = [os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(exts)]
        return sorted(image_list)

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
        if action['type'] == 'move' and os.path.exists(action['t_dst']):
            shutil.move(action['t_dst'], action['t_src'])

    @staticmethod
    def get_max_id_number(path):
        max_id = 0
        if not path or not os.path.exists(path): return 0
        for f in os.listdir(path):
            if f.startswith("id") and "_" in f:
                try:
                    num = int(f[2:].split('_')[0])
                    if num > max_id: max_id = num
                except: continue
        return max_id