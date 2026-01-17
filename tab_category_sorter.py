import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_s, path_o, quality, naming_mode):
    if not path_s or not os.path.exists(path_s):
        st.warning("Please provide a valid Source Folder path.")
        return
    if not path_o:
        st.warning("Please provide a Category Output folder.")
        return

    # --- 1. Category Management Tools (Expander) ---
    with st.expander("🛠️ Bulk Sync & Folder Renaming"):
        if st.button("🔄 Import Subfolders from Disk as Categories"):
            added = SorterEngine.sync_categories_from_disk(path_o)
            st.success(f"Added {added} new categories!")
            st.rerun()
        
        st.divider()
        
        categories = SorterEngine.get_categories()
        col_ren1, col_ren2 = st.columns(2)
        old_cat = col_ren1.selectbox("Folder to Rename", ["Select..."] + categories)
        new_cat_name = col_ren2.text_input("New Name")
        
        if st.button("Apply Rename on Disk & Database"):
            if old_cat != "Select..." and new_cat_name:
                SorterEngine.rename_category(old_cat, new_cat_name, path_o)
                st.rerun()

    st.divider()

    # --- 2. Image Discovery ---
    recursive = st.toggle("🔍 Recursive Mode (Search all subfolders)", value=True)
    images = SorterEngine.get_images(path_s, recursive=recursive)
    categories = SorterEngine.get_categories()

    if st.session_state.idx_cat < len(images):
        curr_p = images[st.session_state.idx_cat]
        curr_file = os.path.basename(curr_p)
        
        st.write("### 🎞️ Filmstrip")
        fs_cols = st.columns(7)
        for i, img_full_path in enumerate(images[st.session_state.idx_cat : st.session_state.idx_cat + 7]):
            fs_cols[i].image(SorterEngine.compress_for_web(img_full_path, 10))

        st.divider()

        col_img, col_btns = st.columns([2, 1])
        
        with col_img:
            st.image(SorterEngine.compress_for_web(curr_p, quality), caption=f"File: {curr_file}")
        
        with col_btns:
            # --- NEW CATEGORY ADDITION (Restored) ---
            new_cat_input = st.text_input("➕ Quick Add Category", key="quick_add_cat")
            if st.button("Add Category", use_container_width=True):
                if new_cat_input:
                    SorterEngine.add_category(new_cat_input)
                    st.rerun()
            
            st.divider()

            fid = SorterEngine.get_folder_id(os.path.dirname(curr_p))
            st.write(f"**Folder ID:** `{fid}`")
            
            # Dynamic Buttons
            for cat in categories:
                if st.button(cat, use_container_width=True, key=f"move_{cat}"):
                    _, ext = os.path.splitext(curr_p)
                    name = curr_file if naming_mode == "original" else f"{fid}{ext}"
                    dst_dir = os.path.join(path_o, cat)
                    os.makedirs(dst_dir, exist_ok=True)
                    
                    final_dst = os.path.join(dst_dir, name)
                    count = 2
                    while os.path.exists(final_dst):
                        root, ext = os.path.splitext(name)
                        final_dst = os.path.join(dst_dir, f"{root}_{count}{ext}")
                        count += 1
                        
                    shutil.move(curr_p, final_dst)
                    st.session_state.history.append({'type': 'cat_move', 't_src': curr_p, 't_dst': final_dst})
                    st.rerun()
            
            st.divider()
            if st.button("⏭️ SKIP IMAGE", use_container_width=True):
                st.session_state.idx_cat += 1
                st.rerun()
    else:
        st.success("Categorization complete.")