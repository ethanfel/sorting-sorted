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

def cb_tag_image(img_path, selected_cat, index_val, path_o):
    """
    Tags image with manual number. 
    Handles collisions by creating variants (e.g. _001_1) and warning the user.
    """
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return

    ext = os.path.splitext(img_path)[1]
    base_name = f"{selected_cat}_{index_val:03d}"
    new_name = f"{base_name}{ext}"
    
    # --- COLLISION DETECTION ---
    # 1. Check Staging DB
    staged = SorterEngine.get_staged_data()
    # Get all names currently staged for this category
    staged_names = {v['name'] for v in staged.values() if v['cat'] == selected_cat}
    
    # 2. Check Hard Drive
    dest_path = os.path.join(path_o, selected_cat, new_name)
    
    collision = False
    suffix = 1
    
    # Loop until we find a free name
    while new_name in staged_names or os.path.exists(dest_path):
        collision = True
        new_name = f"{base_name}_{suffix}{ext}"
        dest_path = os.path.join(path_o, selected_cat, new_name)
        suffix += 1
    
    # --- SAVE ---
    SorterEngine.stage_image(img_path, selected_cat, new_name)
    
    if collision:
        st.toast(f"⚠️ Conflict! Saved as variant: {new_name}", icon="🔀")
    
    # REMOVED: st.session_state.t5_next_index += 1
    # The numbers in the input boxes will now stay static.

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

@st.dialog("🔍 High-Res Inspection", width="large")
def view_high_res(img_path):
    """
    Opens a modal and loads the ORIGINAL size image on demand.
    We still compress to WebP (q=90) to ensure it sends fast, 
    but we do NOT resize the dimensions.
    """
    # Load with target_size=None to keep original dimensions
    # Quality=90 for high fidelity
    img_data = SorterEngine.compress_for_web(img_path, quality=90, target_size=None)
    
    if img_data:
        st.image(img_data, use_container_width=True)
        st.caption(f"Filename: {os.path.basename(img_path)}")
    else:
        st.error("Could not load full resolution image.")

# ... (Gallery Grid code remains exactly the same) ...
# --- UPDATED CACHE FUNCTION ---
@st.cache_data(show_spinner=False, max_entries=2000)
def get_cached_thumbnail(path, quality, target_size, mtime):
    # We pass the dynamic target_size here
    return SorterEngine.compress_for_web(path, quality, target_size)

# --- UPDATED GALLERY FRAGMENT ---
@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols, path_o): # <--- 1. Added path_o
    staged = SorterEngine.get_staged_data()
    history = SorterEngine.get_processed_log()
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    tagging_disabled = selected_cat.startswith("---")
    
    # 2. Ensure global counter exists (default to 1)
    if "t5_next_index" not in st.session_state: st.session_state.t5_next_index = 1

    # 3. Smart Resolution (Wide screen assumption)
    target_size = int(2400 / grid_cols)

    # 4. Parallel Load (16 threads for WebP)
    import concurrent.futures
    batch_cache = {}
    
    def fetch_one(p):
        try:
            mtime = os.path.getmtime(p)
            return p, get_cached_thumbnail(p, quality, target_size, mtime)
        except:
            return p, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_path = {executor.submit(fetch_one, p): p for p in current_batch}
        for future in concurrent.futures.as_completed(future_to_path):
            p, data = future.result()
            batch_cache[p] = data

    # 5. Render Grid
    cols = st.columns(grid_cols)
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            is_processed = img_path in history
            
            with st.container(border=True):
                # Header: [Name] [Zoom] [Delete]
                c_name, c_zoom, c_del = st.columns([4, 1, 1])
                c_name.caption(os.path.basename(img_path)[:10])
                
                if c_zoom.button("🔍", key=f"zoom_{unique_key}"):
                    view_high_res(img_path)
                    
                c_del.button("❌", key=f"del_{unique_key}", on_click=cb_delete_image, args=(img_path,))

                # Status Banners
                if is_staged:
                    st.success(f"🏷️ {staged[img_path]['cat']}")
                elif is_processed:
                    st.info(f"✅ {history[img_path]['action']}")

                # Image (Cached)
                img_data = batch_cache.get(img_path)
                if img_data: 
                    st.image(img_data, use_container_width=True)

                # Action Area
                if not is_staged:
                    # 6. Split Row: [Idx Input] [Tag Button]
                    c_idx, c_tag = st.columns([1, 2], vertical_alignment="bottom")
                    
                    # Manual Override Box (Defaults to global session value)
                    card_index = c_idx.number_input(
                        "Idx", 
                        min_value=1, step=1, 
                        value=st.session_state.t5_next_index, 
                        label_visibility="collapsed",
                        key=f"idx_{unique_key}"
                    )
                    
                    # Tag Button (Passes path_o for conflict check)
                    c_tag.button(
                        "Tag", 
                        key=f"tag_{unique_key}", 
                        disabled=tagging_disabled, 
                        use_container_width=True,
                        on_click=cb_tag_image, 
                        # Passing card_index + path_o is vital here
                        args=(img_path, selected_cat, card_index, path_o) 
                    )
                else:
                    st.button("Untag", key=f"untag_{unique_key}", use_container_width=True,
                              on_click=cb_untag_image, args=(img_path,))

# ... (Batch Actions code remains exactly the same) ...
@st.fragment
def render_batch_actions(current_batch, path_o, page_num, path_s):
    st.write(f"### 🚀 Processing Actions")
    st.caption("Settings apply to both Page and Global actions.")
    
    c_set1, c_set2 = st.columns(2)
    
    # CHANGED: "Copy" is now first, making it the default
    op_mode = c_set1.radio("Tagged Files:", ["Copy", "Move"], horizontal=True, key="t5_op_mode")
    
    cleanup = c_set2.radio("Untagged Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True, key="t5_cleanup_mode")
    
    st.divider()
    
    c_btn1, c_btn2 = st.columns(2)
    
    # BUTTON 1: APPLY PAGE
    if c_btn1.button(f"APPLY PAGE {page_num}", type="secondary", use_container_width=True,
                     on_click=cb_apply_batch, args=(current_batch, path_o, cleanup, op_mode)):
        st.toast(f"Page {page_num} Applied!")
        st.rerun()

    # BUTTON 2: APPLY GLOBAL
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

    # Place this helper inside tab_gallery_sorter.py (or keep it if you have the old one)
def cb_set_page(page_idx):
    st.session_state.t5_page = page_idx

def render_pagination_carousel(key_suffix, total_pages, all_images, page_size):
    """
    Renders a 'Carousel' style pagination with a slider for fast seeking
    and buttons for precise selection with status indicators.
    """
    current_page = st.session_state.t5_page
    
    # 1. CALCULATE TAGGED PAGES (For the Green Indicator)
    # We do this once per render
    tagged_pages_set = SorterEngine.get_tagged_page_indices(all_images, page_size)
    
    # --- A. RAPID SEEKER SLIDER (Debounced) ---
    # Streamlit sliders only rerun the script on mouse release. 
    # This acts as your "wait a bit" logic.
    new_page = st.slider(
        "Rapid Navigation", 
        0, total_pages - 1, current_page, 
        key=f"slider_{key_suffix}",
        label_visibility="collapsed"
    )
    
    # If slider moved, update state and rerun
    if new_page != current_page:
        st.session_state.t5_page = new_page
        st.rerun()

    # --- B. BUTTON CAROUSEL ---
    # We want to show a window of pages: [Prev] .. [p-2] [p-1] [P] [p+1] [p+2] .. [Next]
    
    # Define window size (how many numbered buttons to show)
    window_radius = 2 
    start_p = max(0, current_page - window_radius)
    end_p = min(total_pages, current_page + window_radius + 1)
    
    # Adjust window if we are near the start or end to keep number of buttons constant
    if current_page < window_radius:
        end_p = min(total_pages, 5)
    elif current_page > total_pages - window_radius - 1:
        start_p = max(0, total_pages - 5)

    # Layout: Prev + (Window Buttons) + Next
    # Total columns = (end_p - start_p) + 2 buttons
    num_page_buttons = end_p - start_p
    cols = st.columns([1] + [1] * num_page_buttons + [1])
    
    # 1. PREV BUTTON
    with cols[0]:
        st.button("◀", disabled=(current_page == 0), 
                  on_click=cb_change_page, args=(-1,), 
                  key=f"prev_{key_suffix}", use_container_width=True)

    # 2. PAGE NUMBER BUTTONS
    for i, p_idx in enumerate(range(start_p, end_p)):
        col_idx = i + 1
        with cols[col_idx]:
            # Label Logic: Add 🟢 if tagged
            label = str(p_idx + 1)
            if p_idx in tagged_pages_set:
                label += " 🟢"
            
            # Highlight current page using type="primary"
            is_active = (p_idx == current_page)
            btn_type = "primary" if is_active else "secondary"
            
            st.button(label, 
                      type=btn_type,
                      key=f"btn_p{p_idx}_{key_suffix}", 
                      use_container_width=True,
                      on_click=cb_set_page, args=(p_idx,))

    # 3. NEXT BUTTON
    with cols[-1]:
        st.button("▶", disabled=(current_page >= total_pages - 1), 
                  on_click=cb_change_page, args=(1,), 
                  key=f"next_{key_suffix}", use_container_width=True)

    st.divider()
    render_pagination_carousel("top", total_pages, all_images, page_size)
    render_gallery_grid(current_batch, quality, grid_cols, path_o)
    st.divider()
    render_pagination_carousel("bot", total_pages, all_images, page_size)
    st.divider()
    
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1, path_s)