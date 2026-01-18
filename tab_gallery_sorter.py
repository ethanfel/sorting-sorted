import streamlit as st
import os
import math
from engine import SorterEngine

# ==========================================
# 1. HELPER CALLBACKS (Prevent Refreshing)
# ==========================================
def cb_tag_image(img_path, selected_cat):
    """Tags an image without reloading the whole page."""
    # Safety check: Don't tag if a separator (--- A ---) is selected
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return

    staged = SorterEngine.get_staged_data()
    ext = os.path.splitext(img_path)[1]
    
    # Auto-increment filename logic
    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
    new_name = f"{selected_cat}_{count:03d}{ext}"
    
    SorterEngine.stage_image(img_path, selected_cat, new_name)

def cb_untag_image(img_path):
    """Untags an image."""
    SorterEngine.clear_staged_item(img_path)

def cb_delete_image(img_path):
    """Moves image to trash immediately."""
    SorterEngine.delete_to_trash(img_path)

def cb_apply_batch(current_batch, path_o, cleanup_mode):
    """Commits the batch to disk."""
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode)


# ==========================================
# 2. FRAGMENT: SIDEBAR (Category Manager)
# ==========================================
@st.fragment
def render_sidebar_content():
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # --- GET CATEGORIES & FORMAT LIST ---
    cats = SorterEngine.get_categories()
    
    # Insert visual separators (e.g. "--- A ---")
    processed_cats = []
    last_char = ""
    if cats:
        for cat in cats:
            current_char = cat[0].upper()
            if last_char and current_char != last_char:
                processed_cats.append(f"--- {current_char} ---")
            processed_cats.append(cat)
            last_char = current_char

    # --- STATE MANAGEMENT ---
    # Default selection if none exists
    if "t5_active_cat" not in st.session_state:
        st.session_state.t5_active_cat = cats[0] if cats else "Default"

    # Handle case where selected category was deleted
    # We strip separators to check validity against raw 'cats' list
    current_selection = st.session_state.t5_active_cat
    if not current_selection.startswith("---") and current_selection not in cats:
        st.session_state.t5_active_cat = cats[0] if cats else "Default"

    # --- RADIO SELECTION ---
    selection = st.radio("Active Tag", processed_cats, key="t5_radio_select")

    # Update global state (Ignore separators)
    if not selection.startswith("---"):
        st.session_state.t5_active_cat = selection

    st.divider()

    # --- TABS: ADD / EDIT ---
    tab_add, tab_edit = st.tabs(["➕ Add", "✏️ Edit"])
    
    # ADD NEW
    with tab_add:
        c1, c2 = st.columns([3, 1])
        new_cat = c1.text_input("New Name", label_visibility="collapsed", placeholder="New...", key="t5_new_cat")
        if c2.button("Add", key="btn_add_cat"):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

    # EDIT / DELETE
    with tab_edit:
        target_cat = st.session_state.t5_active_cat
        is_valid = target_cat and not target_cat.startswith("---") and target_cat in cats

        if is_valid:
            st.caption(f"Editing: **{target_cat}**")
            
            # RENAME: Key includes target_cat so input resets when selection changes
            rename_val = st.text_input("Rename to:", value=target_cat, key=f"ren_{target_cat}")
            
            if st.button("💾 Save Name", key=f"save_{target_cat}", use_container_width=True):
                if rename_val and rename_val != target_cat:
                    SorterEngine.rename_category(target_cat, rename_val)
                    st.session_state.t5_active_cat = rename_val
                    st.rerun()
            
            st.markdown("---")
            
            # DELETE
            if st.button("🗑️ Delete Category", key=f"del_cat_{target_cat}", type="primary", use_container_width=True):
                SorterEngine.delete_category(target_cat)
                st.rerun() # Refresh sidebar to remove deleted item
        else:
            st.info("Select a valid category to edit.")


# ==========================================
# 3. FRAGMENT: GALLERY GRID
# ==========================================
@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols):
    """
    Renders images. Updates locally using callbacks without full page reload.
    """
    staged = SorterEngine.get_staged_data()
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    
    # Disable tagging if user selected a separator
    tagging_disabled = selected_cat.startswith("---")

    cols = st.columns(grid_cols)
    
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                # Header: Name & Delete
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                
                # DELETE BUTTON
                c_head2.button("❌", key=f"del_{unique_key}", 
                               on_click=cb_delete_image, args=(img_path,))

                # STATUS BANNER
                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                
                # IMAGE
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data:
                    st.image(img_data, use_container_width=True)

                # ACTION BUTTONS
                if not is_staged:
                    st.button("Tag", key=f"tag_{unique_key}", 
                              disabled=tagging_disabled,
                              use_container_width=True,
                              on_click=cb_tag_image, args=(img_path, selected_cat))
                else:
                    st.button("Untag", key=f"untag_{unique_key}", 
                              use_container_width=True,
                              on_click=cb_untag_image, args=(img_path,))


# ==========================================
# 4. FRAGMENT: BATCH ACTIONS (Apply)
# ==========================================
@st.fragment
def render_batch_actions(current_batch, path_o, page_num):
    """
    Isolates the 'Apply' section so radio buttons don't reload the page.
    """
    st.write(f"### 🚀 Batch Actions (Page {page_num})")
    
    c_act1, c_act2 = st.columns([3, 1])
    
    # Radio button changes stay local to this fragment
    cleanup = c_act1.radio("Untagged Action:", ["Keep", "Move to Unused", "Delete"], 
                           horizontal=True, key="t5_cleanup_mode")
    
    # The Apply button triggers disk operations
    # We allow this to rerun the fragment, but users might need to navigate 
    # to refresh the main list if files disappear.
    if c_act2.button("APPLY PAGE", type="primary", use_container_width=True):
        with st.spinner("Processing..."):
            SorterEngine.commit_batch(current_batch, path_o, cleanup)
        st.success("Batch processed!")
        # Rerun to clear the processed images from the view
        st.rerun()


# ==========================================
# 5. MAIN RENDER ENTRY POINT
# ==========================================
def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # Init Page State
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    # Load Settings
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Settings"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    if not os.path.exists(path_s): return

    # --- RENDER SIDEBAR (FRAGMENT) ---
    with st.sidebar:
        render_sidebar_content()

    # --- VIEW SETTINGS ---
    with st.expander("👀 View Settings"):
        c_v1, c_v2 = st.columns(2)
        page_size = c_v1.slider("Images per Page", 12, 100, 24, 4)
        grid_cols = c_v2.slider("Grid Columns", 2, 8, 4)

    # --- LOAD DATA & PAGINATE ---
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

    # --- NAVIGATION CONTROLS ---
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

    # --- RENDER GALLERY (FRAGMENT) ---
    render_gallery_grid(current_batch, quality, grid_cols)

    st.divider()
    nav_controls("bottom")
    st.divider()

    # --- RENDER BATCH ACTIONS (FRAGMENT) ---
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1)