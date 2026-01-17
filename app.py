import streamlit as st
import os, shutil
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide", page_title="Deep Folder Sorter")

BASE_PATH = "/storage"

# --- Advanced Folder Discovery ---
@st.cache_data(ttl=60) # Cache for 1 minute so it doesn't lag
def get_all_subfolders(base):
    folder_list = []
    try:
        for root, dirs, files in os.walk(base):
            # Optimization: Skip hidden folders or 'unused' folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'unused']
            for name in dirs:
                full_path = os.path.join(root, name)
                # We store the path relative to BASE_PATH for a cleaner UI
                folder_list.append(os.path.relpath(full_path, base))
    except Exception as e:
        st.error(f"Error scanning storage: {e}")
    return sorted(folder_list)

st.sidebar.title("📁 Image Sorter Settings")

# Get the list of all subfolders recursively
all_folders = get_all_subfolders(BASE_PATH)

# Search/Filter functionality
search_query = st.sidebar.text_input("Search folders...", "")
filtered_folders = [f for f in all_folders if search_query.lower() in f.lower()] if search_query else all_folders

folder_a_rel = st.sidebar.selectbox("Select Folder 1", filtered_folders, key="f1")
folder_b_rel = st.sidebar.selectbox("Select Folder 2", filtered_folders, key="f2")

# Reconstruct absolute paths for the OS logic
path_a = os.path.join(BASE_PATH, folder_a_rel) if folder_a_rel else ""
path_b = os.path.join(BASE_PATH, folder_b_rel) if folder_b_rel else ""

comp_level = st.sidebar.slider("Compression (Quality)", 5, 100, 40)

# --- ID Matching Logic (unchanged from prefix logic) ---
def get_map(p):
    m = {}
    if p and os.path.exists(p):
        for f in os.listdir(p):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                prefix = f.split('_')[0]
                m[prefix] = f
    return m

map_a = get_map(path_a)
map_b = get_map(path_b)
common_ids = sorted(list(set(map_a.keys()) & set(map_b.keys())))

if 'idx' not in st.session_state: 
    st.session_state.idx = 0

# --- UI Display ---
if not common_ids:
    st.info("Select two folders to find matching prefixes (e.g., id001_...)")
elif st.session_state.idx < len(common_ids):
    curr_id = common_ids[st.session_state.idx]
    
    st.write(f"### ID: `{curr_id}`")
    st.caption(f"Progress: {st.session_state.idx + 1} / {len(common_ids)}")

    col1, col2 = st.columns(2)
    for i, (p, m) in enumerate([(path_a, map_a), (path_b, map_b)]):
        img_p = os.path.join(p, m[curr_id])
        with Image.open(img_p) as img:
            buf = BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=comp_level)
            (col1 if i==0 else col2).image(buf, use_container_width=True, caption=m[curr_id])

    st.divider()
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
    
    if btn_col1.button("❌ Move ID to Unused", use_container_width=True, type="primary"):
        for p, m in [(path_a, map_a), (path_b, map_b)]:
            dest = os.path.join(p, "unused")
            os.makedirs(dest, exist_ok=True)
            shutil.move(os.path.join(p, m[curr_id]), os.path.join(dest, m[curr_id]))
        st.session_state.idx += 1
        st.rerun()

    if btn_col3.button("✅ Keep Both", use_container_width=True):
        st.session_state.idx += 1
        st.rerun()
else:
    st.success("All items processed!")
    if st.button("Start Over"):
        st.session_state.idx = 0
        st.rerun()