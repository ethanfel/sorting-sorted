import streamlit as st
import os
import math
from engine import SorterEngine

# --- CALLBACKS ---
def cb_tag_image(img_path, selected_cat):
    # Guard against tagging with a separator
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return

    staged = SorterEngine.get_staged_data()
    ext = os.path.splitext(img_path)[1]
    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
    new_name = f"{selected_cat}_{count:03d}{ext}"
    SorterEngine.stage_image(img_path, selected_cat, new_name)

def cb_untag_image(img_path):
    SorterEngine.clear_staged_item(img_path)

def cb_delete_image(img_path):
    SorterEngine.delete_to_trash(img_path)

def cb_apply_batch(current_batch, path_o, cleanup_mode):
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode)


# --- FRAGMENT 1: SIDEBAR (Manager) ---
@st.fragment
def render_sidebar_content():
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # Tabs for different actions
    tab_add, tab_edit = st.tabs(["➕ Add", "✏️ Rename"])
    
    with tab_add:
        c1, c2 = st.columns([3, 1])
        new_cat = c1.text_input("New Cat", label_visibility="collapsed", placeholder="New...", key="t5_new_cat")
        if c2.button("Add", key="btn_add_cat"):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

    # --- CATEGORY LIST LOGIC ---
    cats = SorterEngine.get_categories()
    if not cats:
        st.warning("No categories.")
        return

    # 1. Insert Visual Separators
    processed_cats = []
    last_char = ""
    
    for cat in cats:
        current_char = cat[0].upper()
        # If letter changes (and it's not the very first one), add separator
        if last_char and current_char != last_char:
            processed_cats.append(f"--- {current_char} ---")
        elif not last_char:
            # Optional: Add header for the first group
            # processed_cats.append(f"--- {current_char} ---")
            pass
            
        processed_cats.append(cat)
        last_char = current_char

    # 2. State Management
    if "t5_active_cat" not in st.session_state:
        st.session_state.t5_active_cat = cats[0]

    # Ensure current selection is valid in the new list (handle edge cases)
    if st.session_state.t5_active_cat not in processed_cats:
        if cats[0] in processed_cats:
            st.session_state.t5_active_cat = cats[0]

    # 3. The Radio List
    selection = st.radio("Active Tag", processed_cats, key="t5_radio_select")

    # 4. Handle Separator Selection (Auto-revert)
    if selection.startswith("---"):
        # If user clicks separator, we revert to previous valid or just show warning
        st.warning("Please select a category, not the divider.")
        # We don't update the official session state 't5_active_cat' used by the grid
    else:
        st.session_state.t5_active_cat = selection

    # --- RENAME LOGIC (Inside Edit Tab) ---
    with tab_edit:
        # Defaults to currently selected valid category
        target_cat = st.session_state.t5_active_cat if not st.session_state.t5_active_cat.startswith("---") else ""
        
        st.caption(f"Editing: **{target_cat}**")
        rename_val = st.text_input("New Name", value=target_cat, key="t5_rename_input")
        
        if st.button("Update Name", key="btn_rename"):
            if target_cat and rename_val and rename_val != target_cat:
                SorterEngine.rename_category(target_cat, rename_val)
                # Force update session state to new name so we don't lose selection
                st.session_state.t5_active_cat = rename_val
                st.rerun()


# --- FRAGMENT 2: GALLERY GRID ---
@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols):
    staged = SorterEngine.get_staged_data()
    # Safely get category, falling back if it's a separator
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    if selected_cat.startswith("---"): selected_cat = "" # Disable tagging if separator selected

    cols = st.columns(grid_cols)
    
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                c_head2.button("❌", key=f"del_{unique_key}", on_click=cb_delete_image, args=(img_path,))

                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data:
                    st.image(img_data, use_container_width=True)

                if not is_staged:
                    # Disable button if separator is selected
                    btn_disabled = (selected_cat == "")
                    st.button("Tag", key=f"tag_{unique_key}", disabled=btn_disabled, use_container_width=True,
                              on_click=cb_tag_image, args=(img_path, selected_cat))
                else:
                    st.button("Untag", key=f"untag_{unique_key}", use_container_width=True,
                              on_click=cb_untag_image, args=(img_path,))


# --- MAIN PAGE RENDERER ---
def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
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

    # 1. Sidebar Fragment
    with st.sidebar:
        render_sidebar_content()

    # 2. View Settings
    with st.expander("👀 View Settings"):
        c_v1, c_v2 = st.columns(2)
        page_size = c_v1.slider("Images per Page", 12, 100, 24, 4)
        grid_cols = c_v2.slider("Grid Columns", 2, 8, 4)

    # 3. Pagination Logic
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

    # Nav Helpers
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

    # 5. Batch Apply
    st.write(f"### 🚀 Batch Actions (Page {st.session_state.t5_page + 1})")
    c_act1, c_act2 = st.columns([3, 1])
    cleanup = c_act1.radio("Untagged Action:", ["Keep", "Move to Unused", "Delete"], horizontal=True, key="t5_cleanup_mode")
    
    c_act2.button("APPLY PAGE", type="primary", use_container_width=True,
                  on_click=cb_apply_batch, args=(current_batch, path_o, cleanup))