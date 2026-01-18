import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_s, path_o, quality):
    if not path_s or not os.path.exists(path_s):
        st.warning("Select a Source Folder with PNGs.")
        return

    # 1. Setup State
    if 'sorted_files' not in st.session_state: st.session_state.sorted_files = []
    
    # 2. Controls
    col_a, col_b, col_c = st.columns([2, 1, 1])
    recursive = col_a.toggle("Recursive Scan (Include Subfolders)", value=True)
    images = SorterEngine.get_images(path_s, recursive=recursive)
    categories = SorterEngine.get_categories()

    # 3. Gallery Grid
    st.write(f"### Gallery ({len(images)} images found)")
    
    # CSS to dim sorted images
    st.markdown("""
        <style>
        .sorted-img { opacity: 0.3; filter: grayscale(100%); border: 2px solid green; }
        </style>
    """, unsafe_allow_safe_html=True)

    cols = st.columns(4) # Adjust for gallery density
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_sorted = img_path in st.session_state.sorted_files
            img_class = "sorted-img" if is_sorted else ""
            
            # Display Image
            st.image(SorterEngine.compress_for_web(img_path, quality), 
                     use_container_width=True, 
                     caption="Sorted" if is_sorted else os.path.basename(img_path))
            
            # Action Button per image (Slide/Select equivalent)
            if not is_sorted:
                selected_cat = st.selectbox("Move to...", ["None"] + categories, key=f"sel_{img_path}")
                if selected_cat != "None":
                    dst = os.path.join(path_o, selected_cat, os.path.basename(img_path))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(img_path, dst)
                    st.session_state.sorted_files.append(img_path)
                    st.rerun()

    st.divider()
    
    # 4. Finish Logic
    st.write("### Finish Project")
    col_f1, col_f2 = st.columns(2)
    if col_f1.button("🔥 Delete Remaining Unsorted", type="primary"):
        unsorted = [p for p in images if p not in st.session_state.sorted_files]
        SorterEngine.bulk_cleanup(unsorted, action="delete")
        st.success("Deleted unsorted files.")
        st.rerun()
        
    if col_f2.button("📦 Move Remaining to Unused"):
        unsorted = [p for p in images if p not in st.session_state.sorted_files]
        SorterEngine.bulk_cleanup(unsorted, action="unused", root_path=path_s)
        st.success("Moved unsorted to Unused.")
        st.rerun()