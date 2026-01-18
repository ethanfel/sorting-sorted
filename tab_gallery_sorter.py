import streamlit as st
import os
import math
from engine import SorterEngine

# --- FRAGMENT 1: SIDEBAR CONTENT ---
@st.fragment
def render_sidebar_content():
    """
    Isolates sidebar interactions.
    """
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # Add Category
    c_add1, c_add2 = st.columns([3, 1])
    new_cat = c_add1.text_input("New Category", label_visibility="collapsed", placeholder="New...", key="t5_new_cat_input")
    if c_add2.button("➕", help="Add"):
        if new_cat:
            SorterEngine.add_category(new_cat)
            st.rerun()
    
    # Select Category
    cats = SorterEngine.get_categories()
    if not cats:
        st.warning("No categories.")
        return
        
    if "t5_active_cat" not in st.session_state:
        st.session_state.t5_active_cat = cats[0]
        
    st.radio("Active Tag", cats, key="t5_active_cat")


# --- FRAGMENT 2: GALLERY GRID ---
@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols):
    """
    Isolates grid interactions (Tagging/Deleting).
    """
    staged = SorterEngine.get_staged_data()
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    
    cols = st.columns(grid_cols)
    
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                # Header
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                
                if c_head2.button("❌", key=f"del_{unique_key}"):
                    SorterEngine.delete_to_trash(img_path)
                    st.rerun()

                # Status
                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                
                # Image
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data:
                    st.image(img_data, use_container_width=True)

                # Buttons
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


# --- FRAGMENT 3: BATCH ACTIONS ---
@st.fragment
def render_batch_actions(current_batch, path_o, page_num):
    """
    Isolates the 'Apply' section.
    Changing the Radio Button here will NOT reload the page or the images.
    """
    st.write(f"### 🚀 Batch Actions (Page {page_num})")
    
    c_act1, c_act2 = st.columns([3, 1])
    
    # This radio button caused the refresh before. Now it's contained!
    cleanup = c_act1.radio("Untagged Action:", ["Keep", "Move to Unused", "Delete"], horizontal=True, key="t5_cleanup_mode")
    
    if c_act2.button("APPLY PAGE", type="primary", use_container_width=True):
        with st.spinner("Processing..."):
            SorterEngine.commit_batch(current_batch, path_o, cleanup)
        st.success("Batch Completed!")
        # We allow a full rerun here to refresh the grid (remove moved files)
        st.rerun()


# --- MAIN PAGE RENDERER ---
def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    # Settings Area (Still global, requires save)
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Settings"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    if not os.path.exists(path_s): return

    # 1. Sidebar Fragment
    with st.sidebar:
        render_sidebar_content()

    # 2. View Settings
    with st.expander("👀 View Settings"):
        c_v1, c_v2 = st.columns(2)
        page_size = c_v1.slider("Images per Page", 12, 100, 24, 4)
        grid_cols = c_v2.slider("Grid Columns", 2, 8, 4)

    # 3. Data & Pagination
    all_images = SorterEngine.get_images(path_s, recursive=True)
    if not all_images:
        st.info("No images found.")
        return

    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    current_batch = all_images[start_idx:end_idx]

    # Navigation Controls (These MUST trigger full rerun to change batch)
    def nav_controls(key):
        c1, c2, c3 = st.columns([1, 2, 1])
        if c1.button("⬅️ Prev", disabled=(st.session_state.t5_page==0), key=f"p_{key}"):
            st.session_state.t5_page -= 1
            st.rerun()
        c2.markdown(f"<div style='text-align:center'><b>Page {st.session_state.t5_page+1} / {total_pages}</b></div>", unsafe_allow_html=True)
        if c3.button("Next ➡️", disabled=(st.session_state.t5_page>=total_pages-1), key=f"n_{key}"):
            st.session_state.t5_page += 1
            st.rerun()

    nav_controls("top")
    st.divider()

    # 4. Gallery Fragment
    render_gallery_grid(current_batch, quality, grid_cols)

    st.divider()
    nav_controls("bottom")
    st.divider()

    # 5. Batch Actions Fragment
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1)