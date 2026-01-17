import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, path_out, quality, naming_mode):
    images = SorterEngine.get_images(path_t)
    categories = SorterEngine.get_categories()

    if st.session_state.idx_cat < len(images):
        curr_p = os.path.join(path_t, images[st.session_state.idx_cat])
        
        # Filmstrip (Current + Next 6)
        st.write("### 🎞️ Filmstrip")
        fs_cols = st.columns(7)
        for i, img_name in enumerate(images[st.session_state.idx_cat : st.session_state.idx_cat + 7]):
            fs_cols[i].image(SorterEngine.compress_for_web(os.path.join(path_t, img_name), 10))

        st.divider()

        col_img, col_btns = st.columns([2, 1])
        col_img.image(SorterEngine.compress_for_web(curr_p, quality), caption=images[st.session_state.idx_cat])
        
        with col_btns:
            fid = SorterEngine.get_folder_id(path_t)
            st.write(f"**Current Folder ID:** {fid}")
            
            # Category Management
            new_cat = st.text_input("➕ New Category")
            if st.button("Add"): SorterEngine.add_category(new_cat); st.rerun()

            # Dynamic Category Buttons
            for cat in categories:
                if st.button(cat, use_container_width=True):
                    # Naming Logic from script
                    _, ext = os.path.splitext(curr_p)
                    name = images[st.session_state.idx_cat] if naming_mode == "original" else f"{fid}{ext}"
                    
                    dst_dir = os.path.join(path_out, cat)
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_p = os.path.join(dst_dir, name)
                    
                    # Collision check
                    count = 2
                    while os.path.exists(dst_p):
                        root, ext = os.path.splitext(name)
                        dst_p = os.path.join(dst_dir, f"{root}_{count}{ext}")
                        count += 1
                        
                    shutil.move(curr_p, dst_p)
                    st.toast(f"Moved to {cat}")
                    st.rerun()
                    
            if st.button("⏭️ SKIP", type="secondary", use_container_width=True):
                st.session_state.idx_cat += 1; st.rerun()