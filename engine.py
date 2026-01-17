import os
import shutil
import sqlite3
from PIL import Image
from io import BytesIO

class SorterEngine:
    DB_PATH = "/app/sorter_database.db"

    @staticmethod
    def init_db():
        """Initializes SQLite tables for Profiles, Folder IDs, and Categories."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        # Profiles: Stores Discovery and Review paths
        cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
            (name TEXT PRIMARY KEY, disc_t TEXT, rev_t TEXT, rev_c TEXT, path_out TEXT, mode TEXT)''')
        # Folder IDs: Maps source folders to unique numeric IDs
        cursor.execute('''CREATE TABLE IF NOT EXISTS folder_ids (path TEXT PRIMARY KEY, folder_id INTEGER)''')
        # Categories: Stores the list of sorting categories from your script
        cursor.execute('''CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY)''')
        
        # Seed default categories if empty
        cursor.execute("SELECT COUNT(*) FROM categories")
        if cursor.fetchone()[0] == 0:
            for cat in ["_TRASH", "Default", "Action", "Solo"]:
                cursor.execute("INSERT INTO categories VALUES (?)", (cat,))
        
        conn.commit()
        conn.close()

    @staticmethod
    def get_folder_id(source_path):
        """Retrieves or generates a unique ID for a folder."""
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT folder_id FROM folder_ids WHERE path = ?", (source_path,))
        result = cursor.fetchone()
        if result:
            fid = result[0]
        else:
            cursor.execute("SELECT MAX(folder_id) FROM folder_ids")
            row = cursor.fetchone()
            fid = (row[0] + 1) if row[0] else 1
            cursor.execute("INSERT INTO folder_ids VALUES (?, ?)", (source_path, fid))
            conn.commit()
        conn.close()
        return fid

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
    def save_profile(name, disc_t, rev_t, rev_c, path_out, mode):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO profiles VALUES (?, ?, ?, ?, ?, ?)", 
                       (name, disc_t, rev_t, rev_c, path_out, mode))
        conn.commit()
        conn.close()

    @staticmethod
    def load_profiles():
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM profiles")
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: {"disc_t": r[1], "rev_t": r[2], "rev_c": r[3], "path_out": r[4], "mode": r[5]} for r in rows}

    @staticmethod
    def delete_profile(name):
        conn = sqlite3.connect(SorterEngine.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM profiles WHERE name = ?", (name,))
        conn.commit()
        conn.close()

    # --- Standard File Operations ---
    @staticmethod
    def get_images(path):
        exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff')
        if not path or not os.path.exists(path): return []
        return sorted([f for f in os.listdir(path) if f.lower().endswith(exts)])

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
    def compress_for_web(path, quality):
        try:
            with Image.open(path) as img:
                buf = BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=quality)
                return buf
        except: return None