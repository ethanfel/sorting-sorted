import streamlit as st
import os
from engine import SorterEngine

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Load data for THIS specific tab
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})

    # Path Inputs with explicit string fallbacks
    c1, c2 = st.columns(2)
    t5_s = p_data.get("tab5_source") or "/storage"
    t5_o = p_data.get("tab5_out") or "/storage"
    
    path_s = c1.text_input("📁 Source Gallery Folder", value=t5_s, key="t5_s_path")
    path_o = c2.text_input("🎯 Final Output Root", value=t5_o, key="t5_o_path")
    
    # Save button only appears if paths changed
    if path_s != t5_s or path_o != t5_o:
        if st.button("💾 Update Workspace Paths"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    # --- 2. CATEGORY MANAGEMENT (Sorted Sidebar) ---
    with st.sidebar:
        st.divider()
        st.subheader("🏷️ Category Manager")
        
        new_cat = st.text_input("Quick Add Category", key="t5_add_cat")
        if st.button("➕ Add", use_container_width=True):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

        st.divider()
        # Categories are now automatically sorted A-Z by the engine
        cats = SorterEngine.get_categories()
        if not cats:
            st.warning("No categories found.")
            return
        
        selected_cat = st.radio("Active Tag:", cats, key="t5_active_tag")

    # --- 3. GALLERY ---
    if not os.path.exists(path_s):
        st.info("Please enter a valid Source Path to load images.")
        return

    images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    st.write(f"Images Found: **{len(images)}** | Tagged: **{len(staged)}**")

    cols = st.columns(4)
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_staged = img_path in staged
            
            # Labeling logic
            if is_staged:
                info = staged[img_path]
                st.success(f"TAGGED: {info['cat']}")
                label = f"Renaming to: {info['name']}"
            else:
                label = os.path.basename(img_path)
            
            st.image(SorterEngine.compress_for_web(img_path, quality), caption=label)
            
            # Action logic
            if not is_staged:
                if st.button(f"Tag: {selected_cat}", key=f"tag_{idx}"):
                    ext = os.path.splitext(img_path)[1]
                    # Logic to ensure numbering starts at 001 for each category session
                    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                    new_name = f"{selected_cat}_{count:03d}{ext}"
                    SorterEngine.stage_image(img_path, selected_cat, new_name)
                    st.rerun()
            else:
                if st.button("❌ Remove Tag", key=f"clear_{idx}"):
                    SorterEngine.clear_staged_item(img_path)
                    st.rerun()

    st.divider()
    
    # --- 4. APPLY ---
    cleanup = st.radio("Unmarked Files Action:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        if staged:
            SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
            st.success("Successfully processed images!")
            st.rerun()