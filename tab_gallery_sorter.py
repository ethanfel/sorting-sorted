import streamlit as st
import os
from engine import SorterEngine

def render(quality):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Fetch Profile Data with Fallbacks
    profiles = SorterEngine.load_profiles()
    # Use session state to find the right profile, fallback to 'Default'
    active_profile = st.session_state.get('active_profile', 'Default')
    p_data = profiles.get(active_profile, {})

    # 2. Path Inputs (Placed at the top)
    c1, c2 = st.columns(2)
    path_s = c1.text_input("📁 Source Gallery Folder", 
                           value=p_data.get("tab5_source", "/storage"), 
                           key="t5_path_s_input")
    path_o = c2.text_input("🎯 Final Output Root", 
                           value=p_data.get("tab5_out", "/storage"), 
                           key="t5_path_o_input")
    
    # Save logic moved to a button or specific condition to prevent "Infinite Refresh"
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Gallery Paths"):
            SorterEngine.save_tab_paths(active_profile, t5_s=path_s, t5_o=path_o)
            st.rerun()

    # --- SETTINGS ---
    col_opt1, col_opt2 = st.columns(2)
    recursive = col_opt1.toggle("🔍 Search Subfolders", value=True)
    cleanup = col_opt2.radio("Cleanup Unmarked Files:", 
                             ["Keep", "Move to Unused", "Delete"], 
                             horizontal=True)

    # Safety check: if path doesn't exist, stop here but keep the UI visible
    if not path_s or not os.path.exists(path_s):
        st.warning("Waiting for a valid Source Path...")
        return

    # --- SIDEBAR CATEGORIES ---
    cats = SorterEngine.get_categories()
    if not cats:
        st.error("No categories found in database. Please add some in Tab 4.")
        return
        
    selected_cat = st.sidebar.radio("🏷️ Current Tag", cats, key="gallery_active_cat")

    # --- GALLERY RENDERING ---
    images = SorterEngine.get_images(path_s, recursive=recursive)
    staged = SorterEngine.get_staged_data()
    
    st.write(f"Images: **{len(images)}** | Staged for Rename: **{len(staged)}**")

    # Grid Display (using 4 columns)
    if images:
        cols = st.columns(4)
        for idx, img_path in enumerate(images):
            with cols[idx % 4]:
                is_staged = img_path in staged
                
                # Show the new name if tagged
                label = f"✅ {staged[img_path]['name']}" if is_staged else os.path.basename(img_path)
                
                # Process image through engine
                img_display = SorterEngine.compress_for_web(img_path, quality)
                if img_display:
                    st.image(img_display, caption=label)
                    
                    if st.button("Tag" if not is_staged else "Untag", key=f"gal_btn_{idx}"):
                        if not is_staged:
                            ext = os.path.splitext(img_path)[1]
                            # Count items already staged for this category to determine suffix
                            cat_count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                            new_name = f"{selected_cat}_{cat_count:03d}{ext}"
                            SorterEngine.stage_image(img_path, selected_cat, new_name)
                        else:
                            # Untagging logic: simply remove from the staging table
                            # (Requires a delete_staged_image method in your engine)
                            pass
                        st.rerun()
                else:
                    st.error("Failed to load image.")

    st.divider()
    
    # --- APPLY CHANGES ---
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        if staged:
            with st.spinner("Moving and renaming files..."):
                SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
                st.success("Disk sync complete!")
                st.rerun()
        else:
            st.error("Nothing is staged. Tag some images first!")