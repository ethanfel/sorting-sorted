import streamlit as st
import os
from engine import SorterEngine

def render(quality):
    # 1. Path Configuration for Tab 5
    # These paths are saved independently in the DB
    profiles = SorterEngine.load_profiles()
    active_profile = st.session_state.get('active_profile', 'Default')
    p_data = profiles.get(active_profile, {})

    st.subheader("🖼️ Gallery Staging Sorter")
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Gallery Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s_in")
    path_o = c2.text_input("Final Output Root", value=p_data.get("tab5_out", "/storage"), key="t5_o_in")
    
    # Save independent paths if they change
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        SorterEngine.save_tab_paths(active_profile, t5_s=path_s, t5_o=path_o)

    # Sorting Options
    col_opt1, col_opt2 = st.columns(2)
    recursive = col_opt1.checkbox("Include Subfolders (Recursive Scan)", value=True)
    cleanup = col_opt2.radio("Action for Unmarked Files:", ["Keep in Source", "Move to Unused", "Delete Permanent"], horizontal=True)

    if not path_s or not os.path.exists(path_s):
        st.info("Select a valid source folder to view the gallery.")
        return

    # 2. Category Selection (Sidebar logic)
    cats = SorterEngine.get_categories()
    selected_cat = st.sidebar.radio("🏷️ Target Category Tag", cats, key="t5_cat_sel")

    # 3. Gallery Display
    images = SorterEngine.get_images(path_s, recursive=recursive)
    staged = SorterEngine.get_staged_data()
    
    st.write(f"**Images Found:** {len(images)} | **Pending Renames:** {len(staged)}")

    # Display Grid (4 items wide)
    cols = st.columns(4)
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_staged = img_path in staged
            
            # Show visual status (Marked vs Unmarked)
            caption = f"✅ {staged[img_path]['name']}" if is_staged else os.path.basename(img_path)
            
            st.image(SorterEngine.compress_for_web(img_path, quality), caption=caption)
            
            # Tagging logic: Renames in DB, not yet on disk
            if st.button("Tag as " + selected_cat if not is_staged else "Remove Tag", key=f"t5_btn_{idx}"):
                if not is_staged:
                    ext = os.path.splitext(img_path)[1]
                    # Logic to count current category items for the suffix
                    cat_count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                    new_name = f"{selected_cat}_{cat_count:03d}{ext}"
                    SorterEngine.stage_image(img_path, selected_cat, new_name)
                else:
                    # To un-tag, we would add a delete_staging method (optional)
                    pass
                st.rerun()

    st.divider()
    
    # 4. Commit to Disk
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        if staged:
            SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
            st.success(f"Successfully processed {len(staged)} images and applied cleanup!")
            st.rerun()
        else:
            st.error("No images have been tagged for processing.")