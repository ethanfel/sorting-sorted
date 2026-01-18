import streamlit as st
import os
import math
from engine import SorterEngine

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Setup Session State for Pagination
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    # 2. Load Profile & Paths
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

    # 3. Sidebar: Categories
    cats = SorterEngine.get_categories()
    if not cats:
        st.warning("No categories found. Please add some in the Sidebar.")
        return
    selected_cat = st.sidebar.radio("Active Tag", cats, key="t5_cat_radio")

    # 4. Data Loading
    if not os.path.exists(path_s):
        st.info("Enter a valid source path.")
        return

    all_images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    if not all_images:
        st.info("No images found in this folder.")
        return

    # --- VIEW SETTINGS ---
    # New Slider for Grid Size
    with st.expander("👀 View Settings", expanded=False):
        page_size = st.slider("Images per Page", min_value=12, max_value=100, value=24, step=4)

    # --- PAGINATION LOGIC ---
    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    
    # Bounds Check
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    current_batch = all_images[start_idx:end_idx]

    # --- HELPER: Pagination Controls ---
    def show_pagination_controls(key_suffix):
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

    # 1. TOP CONTROLS
    show_pagination_controls("top")
    st.divider()

    # --- GRID DISPLAY ---
    cols = st.columns(4)
    for idx, img_path in enumerate(current_batch):
        # Unique key combines page number and index to avoid conflicts
        unique_key = f"{st.session_state.t5_page}_{idx}"
        
        with cols[idx % 4]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                # Header
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15] + "...")
                
                # Delete Button
                if c_head2.button("❌", key=f"del_{unique_key}", help="Move to Trash"):
                    SorterEngine.delete_to_trash(img_path)
                    st.rerun()

                # Status Banner
                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                
                # Image
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data:
                    st.image(img_data, use_container_width=True)

                # Action Buttons
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
    
    # 2. BOTTOM CONTROLS
    show_pagination_controls("bottom")
    
    st.divider()

    # --- APPLY SECTION ---
    c_act1, c_act2 = st.columns([3, 1])
    cleanup = c_act1.radio("Action for Unmarked Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    
    if c_act2.button("🚀 APPLY TO DISK", type="primary", use_container_width=True):
        with st.spinner("Moving files..."):
            SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
        st.success("Batch Complete!")
        st.session_state.t5_page = 0 
        st.rerun()