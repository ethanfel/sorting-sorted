import streamlit as st
import os
import math
import concurrent.futures
from engine import SorterEngine

# ==========================================
# 1. CALLBACKS & STATE MANAGEMENT
# ==========================================

def trigger_refresh():
    """Forces the file cache to invalidate."""
    if 't5_file_id' not in st.session_state: st.session_state.t5_file_id = 0
    st.session_state.t5_file_id += 1

def cb_tag_image(img_path, selected_cat, index_val, path_o):
    """Tags image with manual index and collision handling."""
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return

    ext = os.path.splitext(img_path)[1]
    base_name = f"{selected_cat}_{index_val:03d}"
    new_name = f"{base_name}{ext}"
    
    # Collision Detection
    staged = SorterEngine.get_staged_data()
    staged_names = {v['name'] for v in staged.values() if v['cat'] == selected_cat}
    
    dest_path = os.path.join(path_o, selected_cat, new_name)
    collision = False
    suffix = 1
    
    while new_name in staged_names or os.path.exists(dest_path):
        collision = True
        new_name = f"{base_name}_{suffix}{ext}"
        dest_path = os.path.join(path_o, selected_cat, new_name)
        suffix += 1
    
    SorterEngine.stage_image(img_path, selected_cat, new_name)
    
    if collision:
        st.toast(f"⚠️ Conflict! Saved as: {new_name}", icon="🔀")

def cb_untag_image(img_path):
    SorterEngine.clear_staged_item(img_path)

def cb_delete_image(img_path):
    SorterEngine.delete_to_trash(img_path)
    trigger_refresh()

def cb_apply_batch(current_batch, path_o, cleanup_mode, operation):
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode, operation)
    trigger_refresh()

def cb_apply_global(path_o, cleanup_mode, operation, path_s):
    SorterEngine.commit_global(path_o, cleanup_mode, operation, source_root=path_s)
    trigger_refresh()

def cb_change_page(delta):
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    st.session_state.t5_page += delta

def cb_set_page(page_idx):
    st.session_state.t5_page = page_idx

def cb_slider_change(key):
    val = st.session_state[key]
    st.session_state.t5_page = val - 1


# ==========================================
# 2. CACHING & DATA LOADING
# ==========================================

@st.cache_data(show_spinner=False)
def get_cached_images(path, mutation_id):
    """Scans folder. mutation_id forces refresh."""
    return SorterEngine.get_images(path, recursive=True)

@st.cache_data(show_spinner=False, max_entries=2000)
def get_cached_thumbnail(path, quality, target_size, mtime):
    """Loads and compresses thumbnail."""
    return SorterEngine.compress_for_web(path, quality, target_size)

@st.dialog("🔍 High-Res Inspection", width="large")
def view_high_res(img_path):
    """Modal for full resolution inspection."""
    img_data = SorterEngine.compress_for_web(img_path, quality=90, target_size=None)
    if img_data:
        st.image(img_data, use_container_width=True)
        st.caption(f"Filename: {os.path.basename(img_path)}")

@st.dialog("🖼️ Tag Preview", width="large")
def view_tag_preview(img_path, title):
    """Shows the image associated with a number in the grid."""
    st.subheader(title)
    
    # Load image (Fast WebP)
    # We use target_size=800 for a good quality preview
    img_data = SorterEngine.compress_for_web(img_path, quality=80, target_size=800)
    
    if img_data:
        st.image(img_data, use_container_width=True)
        st.caption(f"Source: {img_path}")
    else:
        st.error(f"Could not load image: {img_path}")

@st.cache_data(show_spinner=False)
def get_cached_green_dots(all_images, page_size, staged_keys):
    """
    Calculates which pages have tags. 
    Cached based on the specific keys in the staging area.
    """
    # We reconstruct the set of staged keys from the frozenset
    staged_set = set(staged_keys)
    tagged_pages = set()
    
    # Efficient O(N) scan ONLY when tagging changes
    for idx, img_path in enumerate(all_images):
        if img_path in staged_set:
            tagged_pages.add(idx // page_size)
            
    return tagged_pages
# ==========================================
# 3. FRAGMENTS
# ==========================================

@st.fragment
def render_sidebar_content(path_o):
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # --- 1. PREPARE CATEGORIES ---
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

    # --- 2. INSTANT STATE SYNC (The Fix) ---
    # We check the radio widget's state ('t5_radio_select') BEFORE rendering the grid.
    # This ensures the grid sees the new selection immediately.
    if "t5_radio_select" in st.session_state:
        new_selection = st.session_state.t5_radio_select
        # Only update if it's a valid category (ignore separators)
        if not new_selection.startswith("---"):
            st.session_state.t5_active_cat = new_selection

    # Ensure default exists
    if "t5_active_cat" not in st.session_state: 
        st.session_state.t5_active_cat = cats[0] if cats else "Default"
    
    current_cat = st.session_state.t5_active_cat
    
    # --- 3. VISUAL NUMBER GRID (1-25) ---
    if current_cat and not current_cat.startswith("---"):
        st.caption(f"Map: **{current_cat}**")
        
        # A. Build Index Map: { number: image_path }
        index_map = {}
        
        # Check Staging
        staged = SorterEngine.get_staged_data()
        for orig_path, info in staged.items():
            if info['cat'] == current_cat:
                try:
                    parts = info['name'].rsplit('_', 1)
                    num_part = parts[1].split('.')[0]
                    index_map[int(num_part)] = orig_path
                except: pass

        # Check Disk
        cat_path = os.path.join(path_o, current_cat)
        if os.path.exists(cat_path):
            for f in os.listdir(cat_path):
                if f.startswith(current_cat) and "_" in f:
                    try:
                        parts = f.rsplit('_', 1)
                        num_part = parts[1].split('.')[0]
                        idx = int(num_part)
                        if idx not in index_map:
                            index_map[idx] = os.path.join(cat_path, f)
                    except: pass
        
        # B. Render Grid
        grid_cols = st.columns(5, gap="small")
        for i in range(1, 26):
            is_used = i in index_map
            btn_type = "primary" if is_used else "secondary"
            
            with grid_cols[(i-1) % 5]:
                if st.button(f"{i}", key=f"grid_{i}", type=btn_type, use_container_width=True):
                    st.session_state.t5_next_index = i
                    if is_used:
                        file_path = index_map[i]
                        view_tag_preview(file_path, f"{current_cat} #{i}")
                    else:
                        st.toast(f"Next Index set to #{i}")
        st.divider()

    # --- 4. RADIO SELECTION ---
    # We render the radio here, but its value was already used above!
    st.radio("Active Tag", processed_cats, key="t5_radio_select")

    # --- 5. MANUAL INPUT ---
    st.caption("Tagging Settings")
    c_num1, c_num2 = st.columns([3, 1], vertical_alignment="bottom")
    if "t5_next_index" not in st.session_state: st.session_state.t5_next_index = 1
    
    c_num1.number_input("Next Number #", min_value=1, step=1, key="t5_next_index")
    
    if c_num2.button("🔄", help="Auto-detect next number"):
        used_indices = index_map.keys()
        next_val = max(used_indices) + 1 if used_indices else 1
        st.session_state.t5_next_index = next_val
        st.rerun()

    st.divider()
    
    # ... (Add/Edit Tabs - Keep existing code) ...
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

# NOTE: Do NOT use @st.fragment here. 
# Navigation controls must trigger a full app rerun to load the new batch of images.
# CHANGED: Added 'tagged_pages_set' to arguments
def render_pagination_carousel(key_suffix, total_pages, current_page, tagged_pages_set):
    """
    Renders pagination. No calculation here—just pure UI rendering.
    """
    if total_pages <= 1: return

    # 1. Rapid Seeker Slider (1-BASED)
    st.slider(
        "Rapid Navigation", 
        min_value=1, max_value=total_pages, value=current_page + 1, step=1,
        key=f"slider_{key_suffix}", label_visibility="collapsed",
        on_change=cb_slider_change, args=(f"slider_{key_suffix}",)
    )

    # 2. Window Logic (Calculate range of buttons to show)
    window_radius = 2 
    start_p = max(0, current_page - window_radius)
    end_p = min(total_pages, current_page + window_radius + 1)
    
    # Adjust window near edges to keep width constant
    if current_page < window_radius: 
        end_p = min(total_pages, 5)
    elif current_page > total_pages - window_radius - 1: 
        start_p = max(0, total_pages - 5)

    num_page_buttons = end_p - start_p
    # Safety check if page count is small
    if num_page_buttons < 1: 
        start_p = 0
        end_p = total_pages
        num_page_buttons = total_pages

    # 3. Render Buttons
    # We create columns: [Prev] + [1] [2] [3] ... + [Next]
    cols = st.columns([1] + [1] * num_page_buttons + [1])
    
    # --- PREV BUTTON ---
    with cols[0]:
        st.button("◀", disabled=(current_page == 0), 
                  on_click=cb_change_page, args=(-1,), 
                  key=f"prev_{key_suffix}", use_container_width=True)
    
    # --- NUMBERED BUTTONS ---
    for i, p_idx in enumerate(range(start_p, end_p)):
        with cols[i + 1]:
            label = str(p_idx + 1)
            # Add Green Dot if this page has tagged items
            if p_idx in tagged_pages_set: 
                label += " 🟢"
            
            # Highlight Current Page
            btn_type = "primary" if p_idx == current_page else "secondary"
            
            st.button(label, type=btn_type, 
                      key=f"btn_p{p_idx}_{key_suffix}", 
                      use_container_width=True, 
                      on_click=cb_set_page, args=(p_idx,))

    # --- NEXT BUTTON ---
    with cols[-1]:
        st.button("▶", disabled=(current_page >= total_pages - 1), 
                  on_click=cb_change_page, args=(1,), 
                  key=f"next_{key_suffix}", use_container_width=True)

@st.fragment
def render_gallery_grid(current_batch, quality, grid_cols, path_o):
    """Grid with Zoom, Parallel Load, and Manual Indexing."""
    staged = SorterEngine.get_staged_data()
    history = SorterEngine.get_processed_log()
    selected_cat = st.session_state.get("t5_active_cat", "Default")
    tagging_disabled = selected_cat.startswith("---")
    
    if "t5_next_index" not in st.session_state: st.session_state.t5_next_index = 1
    target_size = int(2400 / grid_cols)

    # Parallel Load
    batch_cache = {}
    def fetch_one(p):
        try:
            mtime = os.path.getmtime(p)
            return p, get_cached_thumbnail(p, quality, target_size, mtime)
        except: return p, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_to_path = {executor.submit(fetch_one, p): p for p in current_batch}
        for future in concurrent.futures.as_completed(future_to_path):
            p, data = future.result()
            batch_cache[p] = data

    cols = st.columns(grid_cols)
    for idx, img_path in enumerate(current_batch):
        unique_key = f"frag_{os.path.basename(img_path)}"
        with cols[idx % grid_cols]:
            is_staged = img_path in staged
            is_processed = img_path in history
            
            with st.container(border=True):
                # Header
                c_name, c_zoom, c_del = st.columns([4, 1, 1])
                c_name.caption(os.path.basename(img_path)[:10])
                if c_zoom.button("🔍", key=f"zoom_{unique_key}"): view_high_res(img_path)
                c_del.button("❌", key=f"del_{unique_key}", on_click=cb_delete_image, args=(img_path,))

                # Status
                if is_staged: st.success(f"🏷️ {staged[img_path]['cat']}")
                elif is_processed: st.info(f"✅ {history[img_path]['action']}")

                # Image
                img_data = batch_cache.get(img_path)
                if img_data: st.image(img_data, use_container_width=True)

                # Actions
                if not is_staged:
                    c_idx, c_tag = st.columns([1, 2], vertical_alignment="bottom")
                    card_index = c_idx.number_input("Idx", min_value=1, step=1, 
                        value=st.session_state.t5_next_index, label_visibility="collapsed", key=f"idx_{unique_key}")
                    
                    c_tag.button("Tag", key=f"tag_{unique_key}", disabled=tagging_disabled, 
                        use_container_width=True, on_click=cb_tag_image, 
                        args=(img_path, selected_cat, card_index, path_o))
                else:
                    # CASE: Image is STAGED
                    # We want to show "Untag (#5)"
                    
                    # 1. Get the current filename from staging data
                    staged_name = staged[img_path]['name'] # e.g., "Category_005.jpg"
                    
                    # 2. Extract the number
                    untag_label = "Untag"
                    try:
                        # Split by underscore, grab the last part, remove extension
                        parts = staged_name.rsplit('_', 1)
                        if len(parts) > 1:
                            num_str = parts[1].split('.')[0] # "005"
                            untag_label = f"Untag (#{int(num_str)})"
                    except:
                        pass

                    st.button(untag_label, key=f"untag_{unique_key}", use_container_width=True,
                              on_click=cb_untag_image, args=(img_path,))


@st.fragment
def render_batch_actions(current_batch, path_o, page_num, path_s):
    st.write(f"### 🚀 Processing Actions")
    st.caption("Settings apply to both Page and Global actions.")
    c_set1, c_set2 = st.columns(2)
    # Default is Copy
    op_mode = c_set1.radio("Tagged Files:", ["Copy", "Move"], horizontal=True, key="t5_op_mode")
    cleanup = c_set2.radio("Untagged Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True, key="t5_cleanup_mode")
    
    st.divider()
    c_btn1, c_btn2 = st.columns(2)
    
    if c_btn1.button(f"APPLY PAGE {page_num}", type="secondary", use_container_width=True,
                     on_click=cb_apply_batch, args=(current_batch, path_o, cleanup, op_mode)):
        st.toast(f"Page {page_num} Applied!")
        st.rerun()

    if c_btn2.button("APPLY ALL (GLOBAL)", type="primary", use_container_width=True,
                     help="Process ALL tagged files.",
                     on_click=cb_apply_global, args=(path_o, cleanup, op_mode, path_s)):
        st.toast("Global Apply Complete!")
        st.rerun()


# ==========================================
# 4. MAIN RENDER
# ==========================================

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # Init State
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
            trigger_refresh()
            st.rerun()

    if not os.path.exists(path_s): return

    with st.sidebar:
        render_sidebar_content(path_o)

    with st.expander("👀 View Settings"):
        c_v1, c_v2 = st.columns(2)
        page_size = c_v1.slider("Images per Page", 12, 100, 24, 4)
        grid_cols = c_v2.slider("Grid Columns", 2, 8, 4)

    # Load Files (Cached)
    all_images = get_cached_images(path_s, st.session_state.t5_file_id)
    if not all_images:
        st.info("No images found.")
        return

   # Pagination Math
    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    if st.session_state.t5_page < 0: st.session_state.t5_page = 0
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    current_batch = all_images[start_idx:end_idx]

    # --- 1. CALCULATE GREEN DOTS ONCE (Optimized) ---
    staged_data = SorterEngine.get_staged_data()
    # We pass 'frozenset' so the cache works efficiently
    green_dots_set = get_cached_green_dots(all_images, page_size, frozenset(staged_data.keys()))

    # --- 2. RENDER UI ---
    st.divider()
    
    # CORRECTED CALL: Pass 'current_page' and 'green_dots_set'
    render_pagination_carousel("top", total_pages, st.session_state.t5_page, green_dots_set)
    
    render_gallery_grid(current_batch, quality, grid_cols, path_o)
    
    st.divider()
    
    # CORRECTED CALL
    render_pagination_carousel("bot", total_pages, st.session_state.t5_page, green_dots_set)
    
    st.divider()
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1, path_s)
    
    st.divider()
    render_batch_actions(current_batch, path_o, st.session_state.t5_page + 1, path_s)