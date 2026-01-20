import streamlit as st
import os
import math
import concurrent.futures
from typing import Dict, Set, List, Optional, Tuple
from engine import SorterEngine

# ==========================================
# STATE MANAGEMENT
# ==========================================

class StreamlitState:
    """Centralized state management with type hints."""
    
    @staticmethod
    def init():
        """Initialize all session state variables."""
        defaults = {
            't5_file_id': 0,
            't5_page': 0,
            't5_active_cat': 'Default',
            't5_next_index': 1,
            't5_op_mode': 'Copy',
            't5_cleanup_mode': 'Keep',
            't5_page_size': 24,
            't5_grid_cols': 4,
            't5_quality': 50,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    @staticmethod
    def trigger_refresh():
        """Force file cache invalidation."""
        st.session_state.t5_file_id += 1
    
    @staticmethod
    def change_page(delta: int):
        """Navigate pages by delta."""
        st.session_state.t5_page = max(0, st.session_state.t5_page + delta)
    
    @staticmethod
    def set_page(page_idx: int):
        """Jump to specific page."""
        st.session_state.t5_page = page_idx
    
    @staticmethod
    def slider_change(key: str):
        """Handle slider-based page navigation (1-based to 0-based)."""
        st.session_state.t5_page = st.session_state[key] - 1

# ==========================================
# CACHING & DATA LOADING
# ==========================================

@st.cache_data(show_spinner=False)
def get_cached_images(path: str, mutation_id: int) -> List[str]:
    """Scan folder for images. mutation_id forces refresh."""
    return SorterEngine.get_images(path, recursive=True)

@st.cache_data(show_spinner=False, max_entries=2000)
def get_cached_thumbnail(path: str, quality: int, target_size: int, mtime: float) -> Optional[bytes]:
    """Load and compress thumbnail with caching."""
    try:
        return SorterEngine.compress_for_web(path, quality, target_size)
    except Exception:
        return None

@st.cache_data(show_spinner=False)
def get_cached_green_dots(all_images: List[str], page_size: int, staged_keys: frozenset) -> Set[int]:
    """
    Calculate which pages have tagged images (cached).
    Returns set of page indices with staged images.
    """
    staged_set = set(staged_keys)
    tagged_pages = set()
    
    for idx, img_path in enumerate(all_images):
        if img_path in staged_set:
            tagged_pages.add(idx // page_size)
    
    return tagged_pages

@st.cache_data(show_spinner=False)
def build_index_map(active_cat: str, path_o: str, staged_data_frozen: frozenset) -> Dict[int, str]:
    """
    Build mapping of index numbers to file paths for active category.
    Returns: {1: '/path/to/Cat_001.jpg', 2: '/path/to/Cat_002.jpg', ...}
    """
    index_map = {}
    
    # Convert frozenset back to dict for processing
    staged_dict = {k: v for k, v in staged_data_frozen}
    
    # Check staging area
    for orig_path, info in staged_dict.items():
        if info['cat'] == active_cat:
            idx = _extract_index(info['name'])
            if idx is not None:
                index_map[idx] = orig_path
    
    # Check disk
    cat_path = os.path.join(path_o, active_cat)
    if os.path.exists(cat_path):
        for filename in os.listdir(cat_path):
            if filename.startswith(active_cat):
                idx = _extract_index(filename)
                if idx is not None and idx not in index_map:
                    index_map[idx] = os.path.join(cat_path, filename)
    
    return index_map

def _extract_index(filename: str) -> Optional[int]:
    """Extract numeric index from filename (e.g., 'Cat_042.jpg' -> 42)."""
    try:
        parts = filename.rsplit('_', 1)
        if len(parts) > 1:
            num_str = parts[1].split('.')[0]
            return int(num_str)
    except (ValueError, IndexError):
        pass
    return None

# ==========================================
# ACTIONS
# ==========================================

def action_tag(img_path: str, selected_cat: str, index_val: int, path_o: str):
    """Tag image with category and index, handling collisions."""
    if selected_cat.startswith("---") or not selected_cat:
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return
    
    ext = os.path.splitext(img_path)[1]
    base_name = f"{selected_cat}_{index_val:03d}"
    new_name = f"{base_name}{ext}"
    
    # Collision detection
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
    
    # Auto-increment index
    st.session_state.t5_next_index = index_val + 1

def action_untag(img_path: str):
    """Remove staging from image."""
    SorterEngine.clear_staged_item(img_path)

def action_delete(img_path: str):
    """Delete image to trash."""
    SorterEngine.delete_to_trash(img_path)
    StreamlitState.trigger_refresh()

def action_apply_batch(current_batch: List[str], path_o: str, cleanup_mode: str, operation: str):
    """Apply staged changes for current page."""
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode, operation)
    StreamlitState.trigger_refresh()

def action_apply_global(path_o: str, cleanup_mode: str, operation: str, path_s: str):
    """Apply all staged changes globally."""
    SorterEngine.commit_global(path_o, cleanup_mode, operation, source_root=path_s)
    StreamlitState.trigger_refresh()

def action_add_category(name: str):
    """Add new category."""
    if name:
        SorterEngine.add_category(name)
        st.session_state.t5_active_cat = name

def action_rename_category(old_name: str, new_name: str):
    """Rename category."""
    if new_name and new_name != old_name:
        SorterEngine.rename_category(old_name, new_name)
        st.session_state.t5_active_cat = new_name

def action_delete_category(cat_name: str):
    """Delete category."""
    SorterEngine.delete_category(cat_name)
    # Reset to first available category
    cats = SorterEngine.get_categories() or ["Default"]
    st.session_state.t5_active_cat = cats[0]

# ==========================================
# DIALOGS
# ==========================================

@st.dialog("🔍 Full Resolution", width="large")
def view_high_res(img_path: str):
    """Modal for full resolution inspection."""
    img_data = SorterEngine.compress_for_web(img_path, quality=90, target_size=None)
    if img_data:
        st.image(img_data, use_container_width=True)
        st.caption(f"📁 {img_path}")
    else:
        st.error(f"Could not load: {img_path}")

@st.dialog("🖼️ Tag Preview", width="large")
def view_tag_preview(img_path: str, title: str):
    """Show image associated with a numbered tag."""
    st.subheader(title)
    
    img_data = SorterEngine.compress_for_web(img_path, quality=80, target_size=800)
    if img_data:
        st.image(img_data, use_container_width=True)
        st.caption(f"📁 {img_path}")
    else:
        st.error(f"Could not load: {img_path}")

# ==========================================
# UI COMPONENTS
# ==========================================

@st.fragment
def render_sidebar_content(path_o: str):
    """Render category management sidebar."""
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # Get and process categories with separators
    cats = SorterEngine.get_categories() or ["Default"]
    processed_cats = _add_category_separators(cats)
    
    # Sync radio selection immediately
    if "t5_radio_select" in st.session_state:
        new_selection = st.session_state.t5_radio_select
        if not new_selection.startswith("---"):
            st.session_state.t5_active_cat = new_selection
    
    if "t5_active_cat" not in st.session_state:
        st.session_state.t5_active_cat = cats[0]
    
    current_cat = st.session_state.t5_active_cat
    
    # NUMBER GRID (1-25) with previews
    if current_cat and not current_cat.startswith("---"):
        st.caption(f"**{current_cat}** Index Map")
        
        # Build index map (cached)
        staged = SorterEngine.get_staged_data()
        staged_frozen = frozenset(staged.items())
        index_map = build_index_map(current_cat, path_o, staged_frozen)
        
        # Render 5x5 grid
        grid_cols = st.columns(5, gap="small")
        for i in range(1, 26):
            is_used = i in index_map
            btn_type = "primary" if is_used else "secondary"
            
            with grid_cols[(i - 1) % 5]:
                if st.button(f"{i}", key=f"grid_{i}", type=btn_type, use_container_width=True):
                    st.session_state.t5_next_index = i
                    if is_used:
                        view_tag_preview(index_map[i], f"{current_cat} #{i}")
                    else:
                        st.toast(f"Next index set to #{i}")
        
        st.divider()
    
    # CATEGORY SELECTOR
    st.radio("Active Category", processed_cats, key="t5_radio_select")
    
    # INDEX CONTROLS
    st.caption("Tagging Settings")
    c_num1, c_num2 = st.columns([3, 1], vertical_alignment="bottom")
    
    c_num1.number_input("Next Index #", min_value=1, step=1, key="t5_next_index")
    
    if c_num2.button("🔄", help="Auto-detect next index"):
        used_indices = list(index_map.keys()) if index_map else []
        st.session_state.t5_next_index = max(used_indices) + 1 if used_indices else 1
        st.rerun()
    
    st.divider()
    
    # CATEGORY MANAGEMENT TABS
    tab_add, tab_edit = st.tabs(["➕ Add", "✏️ Edit"])
    
    with tab_add:
        c1, c2 = st.columns([3, 1])
        new_cat = c1.text_input(
            "New Category", 
            label_visibility="collapsed", 
            placeholder="Enter name...",
            key="t5_new_cat"
        )
        if c2.button("Add", key="btn_add_cat"):
            action_add_category(new_cat)
            st.rerun()
    
    with tab_edit:
        if current_cat and not current_cat.startswith("---") and current_cat in cats:
            st.caption(f"Editing: **{current_cat}**")
            
            rename_val = st.text_input(
                "Rename to:",
                value=current_cat,
                key=f"ren_{current_cat}"
            )
            
            if st.button("💾 Save", key=f"save_{current_cat}", use_container_width=True):
                action_rename_category(current_cat, rename_val)
                st.rerun()
            
            st.markdown("---")
            
            if st.button(
                "🗑️ Delete Category",
                key=f"del_cat_{current_cat}",
                type="primary",
                use_container_width=True
            ):
                action_delete_category(current_cat)
                st.rerun()

def _add_category_separators(cats: List[str]) -> List[str]:
    """Add alphabetical separators between categories."""
    processed = []
    last_char = ""
    
    for cat in cats:
        current_char = cat[0].upper()
        if last_char and current_char != last_char:
            processed.append(f"--- {current_char} ---")
        processed.append(cat)
        last_char = current_char
    
    return processed

def render_pagination_carousel(key_suffix: str, total_pages: int, current_page: int, tagged_pages: Set[int]):
    """Render pagination controls with green dot indicators."""
    if total_pages <= 1:
        return
    
    # Rapid navigation slider (1-based)
    st.slider(
        "Page Navigator",
        min_value=1,
        max_value=total_pages,
        value=current_page + 1,
        step=1,
        key=f"slider_{key_suffix}",
        label_visibility="collapsed",
        on_change=StreamlitState.slider_change,
        args=(f"slider_{key_suffix}",)
    )
    
    # Calculate button window (show current ±2 pages)
    window_radius = 2
    start_p = max(0, current_page - window_radius)
    end_p = min(total_pages, current_page + window_radius + 1)
    
    # Adjust near edges to maintain consistent width
    if current_page < window_radius:
        end_p = min(total_pages, 5)
    elif current_page > total_pages - window_radius - 1:
        start_p = max(0, total_pages - 5)
    
    num_buttons = end_p - start_p
    if num_buttons < 1:
        start_p = 0
        end_p = total_pages
        num_buttons = total_pages
    
    # Render button row: [Prev] [1] [2] [3] ... [Next]
    cols = st.columns([1] + [1] * num_buttons + [1])
    
    # Previous button
    with cols[0]:
        st.button(
            "◀",
            disabled=(current_page == 0),
            on_click=StreamlitState.change_page,
            args=(-1,),
            key=f"prev_{key_suffix}",
            use_container_width=True
        )
    
    # Page number buttons
    for i, p_idx in enumerate(range(start_p, end_p)):
        with cols[i + 1]:
            label = str(p_idx + 1)
            if p_idx in tagged_pages:
                label += " 🟢"
            
            btn_type = "primary" if p_idx == current_page else "secondary"
            
            st.button(
                label,
                type=btn_type,
                key=f"btn_p{p_idx}_{key_suffix}",
                use_container_width=True,
                on_click=StreamlitState.set_page,
                args=(p_idx,)
            )
    
    # Next button
    with cols[-1]:
        st.button(
            "▶",
            disabled=(current_page >= total_pages - 1),
            on_click=StreamlitState.change_page,
            args=(1,),
            key=f"next_{key_suffix}",
            use_container_width=True
        )

@st.fragment
def render_gallery_grid(
    current_batch: List[str],
    quality: int,
    grid_cols: int,
    path_o: str
):
    """Render image gallery grid with parallel loading."""
    staged = SorterEngine.get_staged_data()
    history = SorterEngine.get_processed_log()
    selected_cat = st.session_state.t5_active_cat
    tagging_disabled = selected_cat.startswith("---")
    
    target_size = int(2400 / grid_cols)
    
    # Parallel thumbnail loading
    batch_cache = _load_thumbnails_parallel(current_batch, quality, target_size)
    
    # Render grid
    cols = st.columns(grid_cols)
    
    for idx, img_path in enumerate(current_batch):
        with cols[idx % grid_cols]:
            _render_image_card(
                img_path=img_path,
                batch_cache=batch_cache,
                staged=staged,
                history=history,
                selected_cat=selected_cat,
                tagging_disabled=tagging_disabled,
                path_o=path_o
            )

def _load_thumbnails_parallel(
    batch: List[str],
    quality: int,
    target_size: int
) -> Dict[str, Optional[bytes]]:
    """Load thumbnails in parallel using ThreadPoolExecutor."""
    batch_cache = {}
    
    def fetch_one(path: str) -> Tuple[str, Optional[bytes]]:
        try:
            mtime = os.path.getmtime(path)
            data = get_cached_thumbnail(path, quality, target_size, mtime)
            return path, data
        except Exception:
            return path, None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(fetch_one, p): p for p in batch}
        for future in concurrent.futures.as_completed(futures):
            path, data = future.result()
            batch_cache[path] = data
    
    return batch_cache

def _render_image_card(
    img_path: str,
    batch_cache: Dict[str, Optional[bytes]],
    staged: Dict,
    history: Dict,
    selected_cat: str,
    tagging_disabled: bool,
    path_o: str
):
    """Render individual image card."""
    unique_key = f"frag_{os.path.basename(img_path)}"
    is_staged = img_path in staged
    is_processed = img_path in history
    
    with st.container(border=True):
        # Header: filename + zoom + delete
        c_name, c_zoom, c_del = st.columns([4, 1, 1])
        c_name.caption(os.path.basename(img_path)[:15])
        
        if c_zoom.button("🔍", key=f"zoom_{unique_key}"):
            view_high_res(img_path)
        
        c_del.button(
            "❌",
            key=f"del_{unique_key}",
            on_click=action_delete,
            args=(img_path,)
        )
        
        # Status indicator
        if is_staged:
            staged_info = staged[img_path]
            idx = _extract_index(staged_info['name'])
            idx_str = f" #{idx}" if idx else ""
            st.success(f"🏷️ {staged_info['cat']}{idx_str}")
        elif is_processed:
            st.info(f"✅ {history[img_path]['action']}")
        
        # Thumbnail
        img_data = batch_cache.get(img_path)
        if img_data:
            st.image(img_data, use_container_width=True)
        else:
            st.error("Failed to load")
        
        # Action buttons
        if not is_staged:
            c_idx, c_tag = st.columns([1, 2], vertical_alignment="bottom")
            
            card_index = c_idx.number_input(
                "Index",
                min_value=1,
                step=1,
                value=st.session_state.t5_next_index,
                label_visibility="collapsed",
                key=f"idx_{unique_key}"
            )
            
            c_tag.button(
                "Tag",
                key=f"tag_{unique_key}",
                disabled=tagging_disabled,
                use_container_width=True,
                on_click=action_tag,
                args=(img_path, selected_cat, card_index, path_o)
            )
        else:
            # Show untag with index number
            staged_name = staged[img_path]['name']
            idx = _extract_index(staged_name)
            untag_label = f"Untag (#{idx})" if idx else "Untag"
            
            st.button(
                untag_label,
                key=f"untag_{unique_key}",
                use_container_width=True,
                on_click=action_untag,
                args=(img_path,)
            )

@st.fragment
def render_batch_actions(
    current_batch: List[str],
    path_o: str,
    page_num: int,
    path_s: str
):
    """Render batch processing controls."""
    st.write("### 🚀 Processing Actions")
    st.caption("Settings apply to both Page and Global actions")
    
    c_set1, c_set2 = st.columns(2)
    
    c_set1.radio(
        "Tagged Files:",
        ["Copy", "Move"],
        horizontal=True,
        key="t5_op_mode"
    )
    
    c_set2.radio(
        "Untagged Files:",
        ["Keep", "Move to Unused", "Delete"],
        horizontal=True,
        key="t5_cleanup_mode"
    )
    
    st.divider()
    
    c_btn1, c_btn2 = st.columns(2)
    
    # Apply Page button
    if c_btn1.button(
        f"APPLY PAGE {page_num}",
        type="secondary",
        use_container_width=True,
        on_click=action_apply_batch,
        args=(
            current_batch,
            path_o,
            st.session_state.t5_cleanup_mode,
            st.session_state.t5_op_mode
        )
    ):
        st.toast(f"Page {page_num} applied!")
        st.rerun()
    
    # Apply Global button
    if c_btn2.button(
        "APPLY ALL (GLOBAL)",
        type="primary",
        use_container_width=True,
        help="Process ALL tagged files",
        on_click=action_apply_global,
        args=(
            path_o,
            st.session_state.t5_cleanup_mode,
            st.session_state.t5_op_mode,
            path_s
        )
    ):
        st.toast("Global apply complete!")
        st.rerun()

# ==========================================
# MAIN RENDER FUNCTION
# ==========================================

def render(quality: int, profile_name: str):
    """Main render function for Streamlit app."""
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # Initialize state
    StreamlitState.init()
    
    # Load profiles and paths
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    c1, c2, c3 = st.columns([3, 3, 1])
    
    path_s = c1.text_input(
        "Source Folder",
        value=p_data.get("tab5_source", "/storage"),
        key="t5_s"
    )
    
    path_o = c2.text_input(
        "Output Folder",
        value=p_data.get("tab5_out", "/storage"),
        key="t5_o"
    )
    
    # Save settings button
    if c3.button("💾 Save", use_container_width=True):
        SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
        StreamlitState.trigger_refresh()
        st.toast("Settings saved!")
        st.rerun()
    
    # Validate source path
    if not os.path.exists(path_s):
        st.warning("⚠️ Source path does not exist")
        return
    
    # Render sidebar
    with st.sidebar:
        render_sidebar_content(path_o)
    
    # View settings
    with st.expander("👀 View Settings", expanded=False):
        c_v1, c_v2, c_v3 = st.columns(3)
        
        st.session_state.t5_page_size = c_v1.slider(
            "Images/Page",
            12, 100,
            st.session_state.t5_page_size,
            4
        )
        
        st.session_state.t5_grid_cols = c_v2.slider(
            "Grid Columns",
            2, 8,
            st.session_state.t5_grid_cols
        )
        
        st.session_state.t5_quality = c_v3.slider(
            "Preview Quality",
            10, 100,
            st.session_state.t5_quality,
            10
        )
    
    # Load images (cached)
    all_images = get_cached_images(path_s, st.session_state.t5_file_id)
    
    if not all_images:
        st.info("📂 No images found in source folder")
        return
    
    # Pagination calculations
    page_size = st.session_state.t5_page_size
    total_pages = math.ceil(len(all_images) / page_size)
    
    # Bounds checking
    if st.session_state.t5_page >= total_pages:
        st.session_state.t5_page = max(0, total_pages - 1)
    if st.session_state.t5_page < 0:
        st.session_state.t5_page = 0
    
    current_page = st.session_state.t5_page
    start_idx = current_page * page_size
    current_batch = all_images[start_idx : start_idx + page_size]
    
    # Calculate green dots (cached)
    staged = SorterEngine.get_staged_data()
    green_dots = get_cached_green_dots(
        all_images,
        page_size,
        frozenset(staged.keys())
    )
    
    # Render UI components
    st.divider()
    
    # Top pagination
    render_pagination_carousel("top", total_pages, current_page, green_dots)
    
    # Gallery grid
    render_gallery_grid(
        current_batch,
        st.session_state.t5_quality,
        st.session_state.t5_grid_cols,
        path_o
    )
    
    st.divider()
    
    # Bottom pagination
    render_pagination_carousel("bot", total_pages, current_page, green_dots)
    
    st.divider()
    
    # Batch actions
    render_batch_actions(current_batch, path_o, current_page + 1, path_s)