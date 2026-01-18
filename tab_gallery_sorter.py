import streamlit as st
import os
from engine import SorterEngine

def render(quality):
    # 1. Configuration Header
    st.header("🖼️ Gallery Staging Sorter")
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Gallery Path", key="t5_src")
    path_o = c2.text_input("Final Output Root", key="t5_out")
    
    recursive = st.checkbox("Include Subfolders", value=True)
    cleanup = st.radio("Unmarked Files Action:", ["Keep in Source", "Move to Unused", "Delete Permanent"], horizontal=True)

    if not path_s or not os.path.exists(path_s):
        st.info("Select a valid source folder to begin.")
        return

    # 2. Sidebar for Categories
    with st.sidebar:
        st.divider()
        st.subheader("📁 Staging Categories")
        cats = SorterEngine.get_categories()
        selected_cat = st.radio("Active Category", cats)
        
        new_cat = st.text_input("Add Category")
        if st.button("➕ Add"):
            SorterEngine.add_category(new_cat)
            st.rerun()

    # 3. Gallery Display
    images = SorterEngine.get_images(path_s, recursive=recursive)
    staged = SorterEngine.get_staged_data()
    
    st.write(f"Total Images: {len(images)} | Staged: {len([i for i in staged.values() if i['marked']])}")

    # Display images in a grid
    cols = st.columns(4)
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_staged = img_path in staged
            border_style = "4px solid green" if is_staged else "1px solid gray"
            
            # Clickable Image logic
            st.image(SorterEngine.compress_for_web(img_path, quality), 
                     caption=os.path.basename(img_path))
            
            if st.button("Tag" if not is_staged else "Untag", key=f"tag_{idx}"):
                if not is_staged:
                    # Calculate new name based on category count
                    ext = os.path.splitext(img_path)[1]
                    cat_count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                    new_name = f"{selected_cat}_{cat_count:03d}{ext}"
                    SorterEngine.stage_image(img_path, selected_cat, new_name)
                else:
                    # Logic to remove from staging...
                    pass
                st.rerun()

    st.divider()
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        SorterEngine.commit_staging(path_o, cleanup)
        st.success("Files successfully moved and renamed on disk!")
        st.rerun()