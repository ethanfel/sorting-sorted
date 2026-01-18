import streamlit as st
import os
from engine import SorterEngine

def render(quality):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Profile & Path Loading
    profiles = SorterEngine.load_profiles()
    active_profile = st.session_state.get('active_profile', 'Default')
    p_data = profiles.get(active_profile, {})

    # Path Inputs
    c1, c2 = st.columns(2)
    path_s = c1.text_input("📁 Source Gallery Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s_in")
    path_o = c2.text_input("🎯 Final Output Root", value=p_data.get("tab5_out", "/storage"), key="t5_o_in")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Gallery Paths"):
            SorterEngine.save_tab_paths(active_profile, t5_s=path_s, t5_o=path_o)
            st.rerun()

    # --- 2. SIDEBAR: CATEGORY MANAGEMENT ---
    with st.sidebar:
        st.divider()
        st.subheader("🏷️ Category Manager")
        
        # Add new category
        new_cat = st.text_input("New Category Name", key="t5_new_cat")
        if st.button("➕ Add Category", use_container_width=True):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

        st.divider()
        # Selection of active tag
        cats = SorterEngine.get_categories()
        if not cats:
            st.warning("No categories found. Add one above!")
            return
        
        selected_cat = st.radio("Active Tagging Label:", cats, key="t5_active_tag")

    # --- 3. GALLERY LOGIC ---
    images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    st.write(f"Found: **{len(images)}** | Staged: **{len(staged)}**")

    # Grid Rendering
    cols = st.columns(4)
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_staged = img_path in staged
            
            # IMPROVED FEEDBACK: Show the specific tag and new filename
            if is_staged:
                info = staged[img_path]
                st.success(f"TAGGED: {info['cat']}")
                label = f"New Name: {info['name']}"
            else:
                label = os.path.basename(img_path)
            
            st.image(SorterEngine.compress_for_web(img_path, quality), caption=label)
            
            # Action Buttons
            if not is_staged:
                if st.button(f"Tag as {selected_cat}", key=f"tag_{idx}"):
                    ext = os.path.splitext(img_path)[1]
                    # Generate suffix based on existing tags for this category
                    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                    new_name = f"{selected_cat}_{count:03d}{ext}"
                    SorterEngine.stage_image(img_path, selected_cat, new_name)
                    st.rerun()
            else:
                if st.button("❌ Remove Tag", key=f"untag_{idx}"):
                    # Calls the new method we need to add to engine
                    SorterEngine.clear_staged_item(img_path)
                    st.rerun()

    st.divider()
    
    # --- 4. APPLY CHANGES ---
    cleanup = st.radio("Unmarked Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        if staged:
            SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
            st.success("Files renamed and moved!")
            st.rerun()