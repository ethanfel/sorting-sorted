import streamlit as st
import os
import math
from engine import SorterEngine

# ==========================================
# 1. CACHED DATA LOADER (The Fix)
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_images(path, mutation_id):
    """
    Scans the folder ONLY when 'path' or 'mutation_id' changes.
    Navigating pages does NOT change these, so it remains instant.
    """
    return SorterEngine.get_images(path, recursive=True)


# ==========================================
# 2. CALLBACKS (Updated with Refresh Logic)
# ==========================================
def trigger_refresh():
    """Increments the mutation counter to force a file re-scan."""
    if 't5_file_id' not in st.session_state: st.session_state.t5_file_id = 0
    st.session_state.t5_file_id += 1

def cb_tag_image(img_path, selected_cat):
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return
    staged = SorterEngine.get_staged_data()
    ext = os.path.splitext(img_path)[1]
    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
    new_name = f"{selected_cat}_{count:03d}{ext}"
    SorterEngine.stage_image(img_path, selected_cat, new_name)
    # Note: Tagging does NOT need a file re-scan, just a grid refresh.

def cb_untag_image(img_path):
    SorterEngine.clear_staged_item(img_path)

def cb_delete_image(img_path):
    SorterEngine.delete_to_trash(img_path)
    trigger_refresh() # Force re-scan so the image disappears from the list

def cb_apply_batch(current_batch, path_o, cleanup_mode, operation):
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode, operation)
    trigger_refresh() # Force re-scan to remove moved files

def cb_apply_global(path_o, cleanup_mode, operation, path_s):
    SorterEngine.commit_global(path_o, cleanup_mode, operation, source_root=path_s)
    trigger_refresh() # Force re-scan

def cb_change_page(delta):
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    st.session_state.t5_page += delta
    # No trigger_refresh() here -> This is why page turning is now instant!

def cb_jump_page(k):
    val = st.session_state[k]
    st.session_state.t5_page = val - 1


# ==========================================
# 3. FRAGMENTS (Sidebar, Grid, Batch)
# ==========================================
# ... (Sidebar code remains exactly the same) ...
@st.fragment
def render_sidebar_content():
    st.divider()
    st.subheader("🏷️ Category Manager")
    cats = SorterEngine.get_categories()
    processed_cats = []
    last_char = ""
    if cats:
        for cat in cats:
            current_char = cat[0].upper()
            if last_char and current_char != last_char:
                processed_cats.append(f"--- {current_char} ---")
            processed_cats.append(cat)
            last_char = current_char

    if "t5_active_cat" not in st.session_state: st.session_state.t5_active_cat = cats[0] if cats else "Default"
    current_selection = st.session_state.t5_active_cat
    if not current_selection.startswith("---") and current_selection not in cats:
        st.session_state.t5_active_cat = cats[0] if cats else "Default"

    selection = st.radio("Active Tag", processed_cats, key="t5_radio_select")
    if not selection.startswith("---"): st.session_state.t5_active_cat = selection

    st.divider()
    tab_add, tab_edit = st.tabs(["➕ Add", "✏️ Edit"])
    with tab_add:
        c1, c2 = st.columns([3, 1])
        new_cat = c1.text_input("New Name", label_visibility="collapsed", placeholder="New...", key="t5_new_cat")
        if c2.button("Add", key="btn_add_cat"):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()
    with tab_edit:
        target_cat = st.session_state.t5_active_cat
        if target_cat and not target_cat.startswith("---") and target_cat in cats:
            st.caption(f"Editing: **{target_cat}**")
            rename_val = st.text_input("Rename to:", value=target_cat, key=f"ren_{target_cat}")
            if st.button("💾 Save", key=f"save_{target_cat}", use_container_width=True):
                if rename_val and rename_val != target_cat:
                    SorterEngine.rename_category(target_cat, rename_val)
                    st.session_state.t5_active_cat = rename_val
                    st.rerun()
            st.markdown("---")
            if st.button("🗑️ Delete", key=f"del_cat_{target_cat}", type="primary", use_container_width=True):
                SorterEngine.delete_category(target_cat)
                st.rerun()
        else:
            st.info("Select a valid category to edit.")


# ... (Gallery Grid code remains exactly the same) ...
# --- UPDATED CACHE FUNCTION ---
@st.cache_data(show_spinner=False, max_entries=2000)
def get_cached_thumbnail(path, quality, target_size, mtime):
    # We pass the dynamic target_size here
    return SorterEngine.compress_for_web(path, quality, target_size)

# --- UPDATED GALLERY FRAGMENT ---
@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols):
    staged = SorterEngine.get_staged_data()
    history = SorterEngine.get_processed_log()
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    tagging_disabled = selected_cat.startswith("---")

    # 1. SMART RESOLUTION CALCULATION
    # We assume a wide screen (approx 2400px wide for the container).
    # If you have 2 cols, you get 1200px images. If 8 cols, you get 300px.
    # This ensures images are always crisp but never wasteful.
    target_size = int(2400 / grid_cols)

    # 2. PARALLEL LOAD
    import concurrent.futures
    batch_cache = {}
    
    def fetch_one(p):
        try:
            mtime = os.path.getmtime(p)
            return p, get_cached_thumbnail(p, quality, target_size, mtime)
        except:
            return p, None

    # We bump threads to 16 for WebP as it can be slightly more CPU intensive,
    # but the smaller file size makes up for it in transfer speed.
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_path = {executor.submit(fetch_one, p): p for p in current_batch}
        for future in concurrent.futures.as_completed(future_to_path):
            p, data = future.result()
            batch_cache[p] = data

    # 3. RENDER GRID
    cols = st.columns(grid_cols)
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            is_processed = img_path in history
            
            with st.container(border=True):
                # Header
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                c_head2.button("❌", key=f"del_{unique_key}", on_click=cb_delete_image, args=(img_path,))

                # Status
                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                elif is_processed:
                    st.info(f"✅ {history[img_path]['action']}")

                # Image
                img_data = batch_cache.get(img_path)
                if img_data: 
                    st.image(img_data, use_container_width=True)

                # Buttons
                if not is_staged:
                    st.button("Tag", key=f"tag_{unique_key}", disabled=tagging_disabled, use_container_width=True,
                              on_click=cb_tag_image, args=(img_path, selected_cat))
                else:
                    st.button("Untag", key=f"untag_{unique_key}", use_container_width=True,
                              on_click=cb_untag_image, args=(img_path,))


# ... (Batch Actions code remains exactly the same) ...
@st.fragment
def render_batch_actions(current_batch, path_o, page_num, path_s):
    st.write(f"### 🚀 Processing Actions")
    st.caption("Settings apply to both Page and Global actions.")
    c_set1, c_set2 = st.columns(2)
    op_mode = c_set1.radio("Tagged Files:", ["Move", "Copy"], horizontal=True, key="t5_op_mode")
    cleanup = c_set2.radio("Untagged Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True, key="t5_cleanup_mode")
    st.divider()
    c_btn1, c_btn2 = st.columns(2)
    
    if c_btn1.button(f"APPLY PAGE {page_num}", type="secondary", use_container_width=True,
                     on_click=cb_apply_batch, args=(current_batch, path_o, cleanup, op_mode)):
        st.toast(f"Page {page_num} Applied!")
        st.rerun()

    if c_btn2.button("APPLY ALL (GLOBAL)", type="primary", use_container_width=True,
                     help="Process ALL tagged files across all pages.",
                     on_click=cb_apply_global, args=(path_o, cleanup, op_mode, path_s)):
        st.toast("Global Apply Complete!")
        st.rerun()


# ==========================================
# 4. MAIN RENDERER
# ==========================================
def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # Init Mutation ID (This triggers the scanner cache refresh)
    if 't5_file_id' not in st.session_state: st.session_state.t5_file_id = 0
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Settings"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            # Saving settings might mean new folder, so we trigger refresh
            trigger_refresh()
            st.rerun()

    if not os.path.exists(path_s): return

    with st.sidebar:
        render_sidebar_content()

    with st.expander("👀 View Settings"):
        c_v1, c_v2 = st.columns(2)
        page_size = c_v1.slider("Images per Page", 12, 100, 24, 4)
        grid_cols = c_v2.slider("Grid Columns", 2, 8, 4)

    # --- USING CACHED LOADER ---
    # We pass the mutation ID. If ID is same as last run, scan is SKIPPED.
    all_images = get_cached_images(path_s, st.session_state.t5_file_id)
    
    if not all_images:
        st.info("No images found.")
        return

    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    if st.session_state.t5_page < 0: st.session_state.t5_page = 0
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    current_batch = all_images[start_idx:end_idx]

    def nav_controls(key_suffix):
        c1, c2, c3, c4 = st.columns([1.5, 1, 0.5, 1.5], vertical_alignment="center")
        c1.button("⬅️ Prev", disabled=(st.session_state.t5_page == 0), on_click=cb_change_page, args=(-1,), key=f"p_{key_suffix}", use_container_width=True)
        c2.number_input("Page", min_value=1, max_value=total_pages, value=st.session_state.t5_page + 1, step=1, label_visibility="collapsed", key=f"jump_{key_suffix}", on_change=cb_jump_page, args=(f"jump_{key_suffix}",))
        c3.markdown(f"<div style='text-align: left; font-weight: bold;'>/ {total_pages}</div>", unsafe_allow_html=True)
        c4.button("Next ➡️", disabled=(st.session_state.t5_page >= total_pages - 1), on_click=cb_change_page, args=(1,), key=f"n_{key_suffix}", use_container_width=True)

    st.divider()
    nav_controls("top")
    render_gallery_grid(current_batch, quality, grid_cols)
    st.divider()
    nav_controls("bottom")
    st.divider()
    
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1, path_s)