import streamlit as st
import os
import shutil
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide", page_title="Universal Image Sorter")

# --- UI Sidebar ---
st.sidebar.header("📁 Select Folders")
st.sidebar.info("Base path is set to /storage (your Unraid mount)")

# User types the subpath relative to the mount, or the full container path
path_a = st.sidebar.text_input("Path to Folder 1", value="/storage/Photos/FolderA")
path_b = st.sidebar.text_input("Path to Folder 2", value="/storage/Photos/FolderB")

comp_level = st.sidebar.slider("Bandwidth Compression", 5, 100, 40)

# --- Logic to find matching files ---
def get_files(p):
    if os.path.exists(p):
        return [f for f in os.listdir(p) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    return []

files_a = get_files(path_a)
files_b = get_files(path_b)
common = sorted(list(set(files_a) & set(files_b)))

if 'idx' not in st.session_state:
    st.session_state.idx = 0

# --- File Operations ---
def handle_click(action):
    current_file = common[st.session_state.idx]
    if action == "move":
        for p in [path_a, path_b]:
            target = os.path.join(p, "unused")
            os.makedirs(target, exist_ok=True)
            shutil.move(os.path.join(p, current_file), os.path.join(target, current_file))
    st.session_state.idx += 1

# --- Layout ---
if not common:
    st.warning("No matching files found. Check your paths.")
elif st.session_state.idx >= len(common):
    st.success("Finished all images!")
    if st.button("Reset"): st.session_state.idx = 0
else:
    fname = common[st.session_state.idx]
    st.write(f"**Current Image:** {fname} ({st.session_state.idx+1}/{len(common)})")
    
    col1, col2 = st.columns(2)
    for i, p in enumerate([path_a, path_b]):
        with Image.open(os.path.join(p, fname)) as img:
            buf = BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=comp_level)
            (col1 if i==0 else col2).image(buf, use_container_width=True)

    c1, c2 = st.columns(2)
    c1.button("❌ Move to Unused", on_click=handle_click, args=("move",), use_container_width=True)
    c2.button("✅ Keep Both", on_click=handle_click, args=("keep",), use_container_width=True)