import streamlit as st
import os
import math
from engine import SorterEngine

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Setup Session State
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    # 2. Load Profile
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    # Path Inputs
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Settings"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    # --- 3. SIDEBAR: CATEGORIES (Restored) ---
    with st.sidebar:
        st.divider()
        st.subheader("🏷️ Category Manager")
        
        # Add Category Input
        new_cat = st.text_input("New Category Name", key="t5_new_cat")
        if st.button("➕ Add Category", key="t5_add_btn", use_container_width=True):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()
        
        st.divider()
        
        # Category Selector
        cats = SorterEngine.get_categories()
        if not cats:
            st.warning("No categories found. Add one above!")
            return
        selected_cat = st.radio("Active Tag", cats, key="t5_cat_radio")

    # 4. Data Loading
    if not os.path.exists(path_s): return

    all_images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    if not all_images:
        st.info("No images found.")
        return

    # --- VIEW SETTINGS (New Size Slider) ---
    with st.expander("👀 View Settings & Grid Size", expanded=False):
        c_view1, c_view2 = st.columns(2)
        
        # Slider 1: How many items per page
        page_size = c_view1.slider("Images per Page", 12, 100, 24, 4)
        
        # Slider 2: How many columns (Controls Image Size)
        # Fewer columns = Larger images. More columns = Smaller images.
        grid_cols = c_view2.slider("Image Size (Columns)", min_value=2, max_value=8, value=4, 
                                   help="2 = Huge, 8 = Tiny")

    # --- PAGINATION LOGIC ---
    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    current_batch = all_images[start_idx:end_idx]

    # --- HELPER: Navigation Controls ---
    def show_controls(key_suffix):
        cp1, cp2, cp3 = st.columns([1, 2, 1])
        with cp1:
            if st.button("⬅️ Previous", disabled=(st.session_state.t5_page == 0), key=f"prev_{key_suffix}"):
                st.session_state.t5_page -= 1
                st.rerun()
        with cp2:
            st.markdown(f"<h5 style='text-align: center;'>Page {st.session_state.t5_page + 1} of {total_pages}</h5>", unsafe_allow_html=True)
        with cp3:
            if st.button("Next ➡️", disabled=(st.session_state.t5_page >= total_pages - 1), key=f"next_{key_suffix}"):
                st.session_state.t5_page += 1
                st.rerun()

    show_controls("top")
    st.divider()

    # --- DYNAMIC GRID DISPLAY ---
    # Use the variable 'grid_cols' from the slider instead of hardcoded 4
    cols = st.columns(grid_cols) 
    
    for idx, img_path in enumerate(current_batch):
        unique_key = f"{st.session_state.t5_page}_{idx}"
        
        # Calculate which column this image belongs to based on the slider
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                # Header
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                if c_head2.button("❌", key=f"del_{unique_key}"):
                    SorterEngine.delete_to_trash(img_path)
                    st.rerun()

                # Status Banner
                if is_staged: st.success(f"🏷️ {staged[img_path]['cat']}")
                
                # Image Render
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data: st.image(img_data, use_container_width=True)

                # Tagging Buttons
                if not is_staged:
                    if st.button("Tag", key=f"tag_{unique_key}", use_container_width=True):
                        ext = os.path.splitext(img_path)[1]
                        count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                        new_name = f"{selected_cat}_{count:03d}{ext}"
                        SorterEngine.stage_image(img_path, selected_cat, new_name)
                        st.rerun()
                else:
                    if st.button("Untag", key=f"untag_{unique_key}", use_container_width=True):
                        SorterEngine.clear_staged_item(img_path)
                        st.rerun()

    st.divider()
    show_controls("bottom")
    st.divider()

    # --- BATCH APPLY ---
    st.write(f"### 🚀 Batch Actions (Page {st.session_state.t5_page + 1} Only)")
    
    c_act1, c_act2 = st.columns([3, 1])
    cleanup = c_act1.radio("Action for Untagged Files on this Page:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    
    if c_act2.button("APPLY PAGE TO DISK", type="primary", use_container_width=True):
        with st.spinner("Processing current page..."):
            SorterEngine.commit_batch(current_batch, path_o, cleanup)
        st.success("Page processed!")
        st.rerun()