import streamlit as st
import os
from PIL import Image
import shutil
from io import BytesIO

st.set_page_config(layout="wide", page_title="Unraid Image Sorter")

# --- UI Sidebar ---
st.sidebar.header("📁 Folder Configuration")
# These paths should match your Unraid Container Path mappings
path_a = st.sidebar.text_input("Folder A (Internal Path)", value="/media/folder1")
path_b = st.sidebar.text_input("Folder B (Internal Path)", value="/media/folder2")
quality = st.sidebar.slider("Bandwidth Compression (Quality)", 5, 100, 40)

def get_valid_files(path):
    if not os.path.exists(path): return []
    return [f for f in os.listdir(path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

files_a = get_valid_files(path_a)
files_b = get_valid_files(path_b)
common = sorted(list(set(files_a) & set(files_b)))

if 'idx' not in st.session_state:
    st.session_state.idx = 0

# --- Action Logic ---
def process_files(action, filename):
    if action == "move":
        for base_path in [path_a, path_b]:
            target_dir = os.path.join(base_path, "unused")
            os.makedirs(target_dir, exist_ok=True)
            shutil.move(os.path.join(base_path, filename), os.path.join(target_dir, filename))
        st.toast(f"Moved {filename} to unused")
    else:
        st.toast(f"Kept {filename}")
    
    st.session_state.idx += 1

# --- Display Logic ---
if st.session_state.idx < len(common):
    fname = common[st.session_state.idx]
    st.subheader(f"Comparing: {fname} ({st.session_state.idx + 1} of {len(common)})")

    col1, col2 = st.columns(2)
    for i, base in enumerate([path_a, path_b]):
        img_path = os.path.join(base, fname)
        with Image.open(img_path) as img:
            # Compression for Web UI
            buf = BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=quality)
            (col1 if i==0 else col2).image(buf, use_container_width=True)

    st.divider()
    btn1, btn2 = st.columns(2)
    btn1.button("🗑️ Move to Unused", on_click=process_files, args=("move", fname), use_container_width=True)
    btn2.button("⭐ Keep Both", on_click=process_files, args=("keep", fname), use_container_width=True)
else:
    st.success("Comparison complete! No more matching files found.")