import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_s, path_o, quality, naming_mode):
    # Validation of paths
    if not path_s or not os.path.exists(path_s):
        st.warning("Please provide a valid Source Folder path.")
        return
    if not path_o:
        st.warning("Please provide a Category Output folder.")
        return

    # --- 1. Category Management Tools ---
    with st.expander("🛠️ Category & Folder Management"):
        # Bulk Sync Tool
        st.write("### Sync Existing Folders")
        if st.button("🔄 Import Subfolders from Disk as Categories"):
            added = SorterEngine.sync_categories_from_disk(path_o)
            st.success(f"Added {added} new category buttons based on your folders!")
            st.rerun()
        
        st.divider()
        
        # Physical Rename Tool
        st.write("### Rename Category & Folder")
        categories = SorterEngine.get_categories()
        col_ren1, col_ren2 = st.columns(2)
        old_cat = col_ren1.selectbox("Folder to Rename", ["Select..."] + categories)
        new_cat_name = col_ren2.text_input("New Name")
        
        if st.button("Apply Rename on Disk & Database"):
            if old_cat != "Select..." and new_cat_name:
                SorterEngine.rename_category(old_cat, new_cat_name, path_o)
                st.success(f"Successfully moved folder and updated buttons: {old_cat} -> {new_cat_name}")
                st.rerun()

    st.divider()

    # --- 2. Image Discovery ---
    # Toggle for Recursive Scanning
    recursive = st.toggle("🔍 Recursive Mode (Search all subfolders)", value=True)
    images = SorterEngine.get_images(path_s, recursive=recursive) #
    categories = SorterEngine.get_categories()

    if st.session_state.idx_cat < len(images):
        curr_p = images[st.session_state.idx_cat] # Full system path
        curr_file = os.path.basename(curr_p)
        
        # 🎞️ Filmstrip Preview
        st.write("### 🎞️ Filmstrip")
        fs_cols = st.columns(7)
        for i, img_full_path in enumerate(images[st.session_state.idx_cat : st.session_state.idx_cat + 7]):
            fs_cols[i].image(SorterEngine.compress_for_web(img_full_path, 10))

        st.divider()

        # --- 3. Main Sorting UI ---
        col_img, col_btns = st.columns([2, 1])
        
        with col_img:
            st.image(SorterEngine.compress_for_web(curr_p, quality), caption=f"Processing: {curr_file}")
            st.caption(f"Source Path: {curr_p}")
        
        with col_btns:
            # Generate ID based on the folder specifically containing this image
            folder_of_image = os.path.dirname(curr_p)
            fid = SorterEngine.get_folder_id(folder_of_image) #
            st.write(f"**Folder ID:** `{fid}`")
            
            # Dynamic Category Buttons
            for cat in categories:
                if st.button(cat, use_container_width=True, key=f"move_{cat}"):
                    _, ext = os.path.splitext(curr_p)
                    
                    # Naming logic: Original vs ID
                    name = curr_file if naming_mode == "original" else f"{fid}{ext}"
                    
                    dst_dir = os.path.join(path_o, cat)
                    os.makedirs(dst_dir, exist_ok=True)
                    
                    # Collision protection
                    count = 2
                    final_dst = os.path.join(dst_dir, name)
                    while os.path.exists(final_dst):
                        root, ext = os.path.splitext(name)
                        final_dst = os.path.join(dst_dir, f"{root}_{count}{ext}")
                        count += 1
                        
                    shutil.move(curr_p, final_dst)
                    
                    # Log history for the Undo button in app.py
                    st.session_state.history.append({
                        'type': 'cat_move', 
                        't_src': curr_p, 
                        't_dst': final_dst
                    })
                    st.toast(f"Moved to {cat}")
                    st.rerun()
            
            st.divider()
            
            if st.button("⏭️ SKIP IMAGE", use_container_width=True):
                st.session_state.idx_cat += 1
                st.rerun()
                
            if st.button("🗑️ QUICK TRASH", type="primary", use_container_width=True):
                # Uses the default _TRASH category from DB seed
                dst_dir = os.path.join(path_o, "_TRASH")
                os.makedirs(dst_dir, exist_ok=True)
                final_dst = os.path.join(dst_dir, curr_file)
                shutil.move(curr_p, final_dst)
                st.rerun()
    else:
        st.success("All images in this workspace have been categorized!")
        if st.button("Restart from Beginning"):
            st.session_state.idx_cat = 0
            st.rerun()