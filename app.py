import streamlit as st
import os
import shutil
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide", page_title="ID-Based Image Sorter")

BASE_PATH = "/storage"

# --- Sidebar ---
st.sidebar.header("📁 Folder Selection")
def get_subfolders(directory):
    try:
        return sorted([d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))])
    except: return []

subfolders = get_subfolders(BASE_PATH)
folder_a_name = st.sidebar.selectbox("Select Folder 1", subfolders)
folder_b_name = st.sidebar.selectbox("Select Folder 2", subfolders)
comp_level = st.sidebar.slider("Compression (Quality)", 5, 100, 40)

path_a = os.path.join(BASE_PATH, folder_a_name) if folder_a_name else ""
path_b = os.path.join(BASE_PATH, folder_b_name) if folder_b_name else ""

# --- ID Matching Logic ---
def get_id_map(path):
    mapping = {}
    if not path or not os.path.exists(path): return mapping
    for f in os.listdir(path):
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            # Extracts 'id001' from 'id001_example.jpg'
            prefix = f.split('_')[0]
            mapping[prefix] = f
    return mapping

map_a = get_id_map(path_a)
map_b = get_id_map(path_b)
common_ids = sorted(list(set(map_a.keys()) & set(map_b.keys())))

if 'idx' not in st.session_state:
    st.session_state.idx = 0

def move_files(prefix):
    for path, mapping in [(path_a, map_a), (path_b, map_b)]:
        filename = mapping[prefix]
        target_dir = os.path.join(path, "unused")
        os.makedirs(target_dir, exist_ok=True)
        shutil.move(os.path.join(path, filename), os.path.join(target_dir, filename))
    st.session_state.idx += 1

# --- Main UI ---
if not common_ids:
    st.info("No matching IDs found (e.g., 'id001_') between these folders.")
elif st.session_state.idx >= len(common_ids):
    st.success("All matched IDs processed!")
    if st.button("Reset"): st.session_state.idx = 0
else:
    current_id = common_ids[st.session_state.idx]
    file_a = map_a[current_id]
    file_b = map_b[current_id]

    st.write(f"### Current ID: `{current_id}`")
    st.caption(f"Progress: {st.session_state.idx + 1} / {len(common_ids)}")

    col1, col2 = st.columns(2)
    for i, (p, f) in enumerate([(path_a, file_a), (path_b, file_b)]):
        with Image.open(os.path.join(p, f)) as img:
            buf = BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=comp_level)
            (col1 if i==0 else col2).image(buf, use_container_width=True, caption=f)

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 1])
    if c1.button("❌ Move ID to Unused", use_container_width=True):
        move_files(current_id)
        st.rerun()
    if c3.button("✅ Keep Both", use_container_width=True):
        st.session_state.idx += 1
        st.rerun()