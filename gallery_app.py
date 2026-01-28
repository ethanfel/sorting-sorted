import os
import math
import asyncio
from typing import Optional, List, Dict, Set, Tuple
from functools import partial
from nicegui import ui, app, run
from fastapi import Response
from engine import SorterEngine

# ==========================================
# STATE MANAGEMENT
# ==========================================
class AppState:
    """Centralized application state with lazy loading."""
    
    def __init__(self):
        # Profile Data
        self.profiles = SorterEngine.load_profiles()
        self.profile_name = "Default"
        if not self.profiles:
            self.profiles = {"Default": {"tab5_source": "/storage", "tab5_out": "/storage"}}
        
        self.load_active_profile()
        
        # View Settings
        self.page = 0
        self.page_size = 24
        self.grid_cols = 4
        self.preview_quality = 50 
        
        # Tagging State
        self.active_cat = "control"
        self.next_index = 1
        self.hovered_image = None  # Track currently hovered image for keyboard shortcuts
        self.category_hotkeys: Dict[str, str] = {}  # Maps hotkey -> category name
        
        # Undo Stack
        self.undo_stack: List[Dict] = []  # Stores last actions for undo
        
        # Filter Mode
        self.filter_mode = "all"  # "all", "tagged", "untagged"
        
        # Batch Settings
        self.batch_mode = "Copy"
        self.cleanup_mode = "Keep"
        
        # Data Caches
        self.all_images: List[str] = []
        self.staged_data: Dict = {}
        self.green_dots: Set[int] = set()
        self.index_map: Dict[int, str] = {}

        # Performance caches (Phase 1 optimizations)
        self._cached_tagged_count: int = 0  # Cached count for get_stats()
        self._green_dots_dirty: bool = True  # Lazy green dots calculation
        self._last_disk_scan_key: str = ""  # Track output_dir + category for lazy disk scan
        self._disk_index_map: Dict[int, str] = {}  # Cached disk scan results
        
        # UI Containers (populated later)
        self.sidebar_container = None
        self.grid_container = None
        self.pagination_container = None
        
        # === PAIRING MODE STATE ===
        self.current_mode = "gallery"  # "gallery" or "pairing"
        self.pair_time_window = 60  # seconds +/- for matching
        self.pair_current_idx = 0  # Current image index in pairing mode
        self.pair_adjacent_folder = ""  # Path to adjacent folder
        self.pair_adjacent_data: List[Tuple[str, float]] = []  # (path, timestamp) tuples for O(1) lookup
        self.pair_matches: List[str] = []  # Current matches for selected image
        self.pair_selected_match = None  # Currently selected match
        self.pairing_container = None  # UI container for pairing mode
        
        # Separate settings for main and adjacent sides
        self.pair_main_category = "control"  # Category for main folder images
        self.pair_adj_category = "control"   # Category for adjacent folder images
        self.pair_main_output = "/storage"   # Output folder for main images
        self.pair_adj_output = "/storage"    # Output folder for adjacent images
        self.pair_index = 1  # Shared index for both sides
        
        # Pairing mode index maps (index -> (main_path, adj_path))
        self.pair_index_map: Dict[int, Dict] = {}  # {idx: {"main": path, "adj": path}}

        # === CAPTION STATE ===
        self.caption_settings: Dict = {}
        self.captioning_in_progress: bool = False
        self.caption_on_apply: bool = False  # Toggle for captioning during APPLY
        self.caption_cache: Set[str] = set()  # Paths that have captions

    def load_active_profile(self):
        """Load paths from active profile."""
        p_data = self.profiles.get(self.profile_name, {})
        self.input_base = p_data.get("tab5_source", "/storage")
        self.output_base = p_data.get("tab5_out", "/storage")
        self.folder_name = ""
        
        # Load pairing mode settings
        self.pair_adjacent_folder = p_data.get("pair_adjacent_folder", "")
        self.pair_main_category = p_data.get("pair_main_category", "control")
        self.pair_adj_category = p_data.get("pair_adj_category", "control")
        self.pair_main_output = p_data.get("pair_main_output", "/storage")
        self.pair_adj_output = p_data.get("pair_adj_output", "/storage")
        self.pair_time_window = p_data.get("pair_time_window", 60)

    @property
    def source_dir(self):
        """Computed source path: input_base/folder_name or just input_base."""
        if self.folder_name:
            return os.path.join(self.input_base, self.folder_name)
        return self.input_base

    @property
    def output_dir(self):
        """Computed output path: output_base/folder_name or just output_base."""
        if self.folder_name:
            return os.path.join(self.output_base, self.folder_name)
        return self.output_base

    def save_current_profile(self):
        """Save current paths to active profile."""
        if self.profile_name not in self.profiles:
            self.profiles[self.profile_name] = {}
        
        # Save gallery mode settings
        self.profiles[self.profile_name]["tab5_source"] = self.input_base
        self.profiles[self.profile_name]["tab5_out"] = self.output_base
        
        # Save pairing mode settings
        self.profiles[self.profile_name]["pair_adjacent_folder"] = self.pair_adjacent_folder
        self.profiles[self.profile_name]["pair_main_category"] = self.pair_main_category
        self.profiles[self.profile_name]["pair_adj_category"] = self.pair_adj_category
        self.profiles[self.profile_name]["pair_main_output"] = self.pair_main_output
        self.profiles[self.profile_name]["pair_adj_output"] = self.pair_adj_output
        self.profiles[self.profile_name]["pair_time_window"] = self.pair_time_window
        
        SorterEngine.save_tab_paths(
            self.profile_name, 
            t5_s=self.input_base, 
            t5_o=self.output_base,
            pair_adjacent_folder=self.pair_adjacent_folder,
            pair_main_category=self.pair_main_category,
            pair_adj_category=self.pair_adj_category,
            pair_main_output=self.pair_main_output,
            pair_adj_output=self.pair_adj_output,
            pair_time_window=self.pair_time_window
        )
        ui.notify(f"Profile '{self.profile_name}' saved!", type='positive')

    def get_categories(self) -> List[str]:
        """Get list of categories, ensuring active_cat exists."""
        cats = SorterEngine.get_categories(self.profile_name) or ["control"]
        if self.active_cat not in cats:
            self.active_cat = cats[0]
        return cats

    def load_caption_settings(self):
        """Load caption settings for current profile."""
        self.caption_settings = SorterEngine.get_caption_settings(self.profile_name)

    def refresh_caption_cache(self, image_paths: List[str] = None):
        """Refresh the cache of which images have captions."""
        paths = image_paths or self.all_images
        if paths:
            captions = SorterEngine.get_captions_batch(paths)
            self.caption_cache = set(captions.keys())

    def get_filtered_images(self) -> List[str]:
        """Get images based on current filter mode."""
        if self.filter_mode == "all":
            return self.all_images
        elif self.filter_mode == "tagged":
            return [img for img in self.all_images if img in self.staged_data]
        elif self.filter_mode == "untagged":
            return [img for img in self.all_images if img not in self.staged_data]
        return self.all_images

    @property
    def total_pages(self) -> int:
        """Calculate total pages based on filtered images."""
        filtered = self.get_filtered_images()
        return math.ceil(len(filtered) / self.page_size) if filtered else 0

    def get_current_batch(self) -> List[str]:
        """Get images for current page based on filter."""
        filtered = self.get_filtered_images()
        if not filtered:
            return []
        start = self.page * self.page_size
        return filtered[start : start + self.page_size]
    
    def get_stats(self) -> Dict:
        """Get image statistics for display. Uses cached tagged count."""
        total = len(self.all_images)
        tagged = self._cached_tagged_count
        return {"total": total, "tagged": tagged, "untagged": total - tagged}

    def get_green_dots(self) -> Set[int]:
        """Lazily calculate green dots (pages with tagged images).
        Only recalculates when _green_dots_dirty is True."""
        if self._green_dots_dirty:
            self.green_dots.clear()
            staged_keys = set(self.staged_data.keys())
            for idx, img_path in enumerate(self.all_images):
                if img_path in staged_keys:
                    self.green_dots.add(idx // self.page_size)
            self._green_dots_dirty = False
        return self.green_dots

state = AppState()

# ==========================================
# IMAGE SERVING API
# ==========================================

@app.get('/thumbnail')
async def get_thumbnail(path: str, size: int = 400, q: int = 50):
    """Serve WebP thumbnail with dynamic quality."""
    if not os.path.exists(path):
        return Response(status_code=404)
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, q, size)
    return Response(content=img_bytes, media_type="image/webp") if img_bytes else Response(status_code=500)

@app.get('/full_res')
async def get_full_res(path: str):
    """Serve full resolution image."""
    if not os.path.exists(path):
        return Response(status_code=404)
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 90, None)
    return Response(content=img_bytes, media_type="image/webp") if img_bytes else Response(status_code=500)

# ==========================================
# CORE LOGIC
# ==========================================

def load_images():
    """Load images from source directory."""
    if not os.path.exists(state.source_dir):
        ui.notify(f"Source not found: {state.source_dir}", type='warning')
        return

    # Auto-save current tags before switching folders
    if state.all_images and state.staged_data:
        saved = SorterEngine.save_folder_tags(state.source_dir, state.profile_name)
        if saved > 0:
            ui.notify(f"Auto-saved {saved} tags", type='info')

    # Clear staging area when loading a new folder
    SorterEngine.clear_staging_area()

    state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)

    # Restore previously saved tags for this folder and profile
    restored = SorterEngine.restore_folder_tags(state.source_dir, state.all_images, state.profile_name)
    if restored > 0:
        ui.notify(f"Restored {restored} tags from previous session", type='info')

    # Reset page if out of bounds
    if state.page >= state.total_pages:
        state.page = 0

    refresh_staged_info()
    # Refresh caption cache for loaded images
    state.refresh_caption_cache()
    # Load caption settings
    state.load_caption_settings()
    refresh_ui()

# ==========================================
# PAIRING MODE FUNCTIONS
# ==========================================

def get_file_timestamp(filepath: str) -> Optional[float]:
    """Get file modification timestamp."""
    try:
        return os.path.getmtime(filepath)
    except:
        return None

def load_adjacent_folder():
    """Load images from adjacent folder for pairing, excluding main folder.
    Caches timestamps at load time to avoid repeated syscalls during navigation."""
    if not state.pair_adjacent_folder or not os.path.exists(state.pair_adjacent_folder):
        state.pair_adjacent_data = []
        ui.notify("Adjacent folder path is empty or doesn't exist", type='warning')
        return

    # Exclude the main source folder to avoid duplicates
    exclude = [state.source_dir] if state.source_dir else []

    images = SorterEngine.get_images(
        state.pair_adjacent_folder,
        recursive=True,
        exclude_paths=exclude
    )

    # Cache timestamps at load time (one-time cost instead of per-navigation)
    state.pair_adjacent_data = []
    for img_path in images:
        ts = get_file_timestamp(img_path)
        if ts is not None:
            state.pair_adjacent_data.append((img_path, ts))

    ui.notify(f"Loaded {len(state.pair_adjacent_data)} images from adjacent folder", type='info')

def find_time_matches(source_image: str) -> List[str]:
    """Find images in adjacent folder within time window of source image.
    Uses cached timestamps from pair_adjacent_data for O(n) without syscalls."""
    source_time = get_file_timestamp(source_image)
    if source_time is None:
        return []

    window = state.pair_time_window
    matches = []
    # Use pre-cached timestamps - no syscalls needed
    for adj_path, adj_time in state.pair_adjacent_data:
        time_diff = abs(source_time - adj_time)
        if time_diff <= window:
            matches.append((adj_path, time_diff))

    # Sort by time difference (closest first)
    matches.sort(key=lambda x: x[1])
    return [m[0] for m in matches]

def pair_navigate(direction: int):
    """Navigate to next/previous image in pairing mode."""
    if not state.all_images:
        render_pairing_view()  # Still render to show "no images" message
        return
    
    state.pair_current_idx = max(0, min(state.pair_current_idx + direction, len(state.all_images) - 1))
    
    # Find matches for current image
    current_img = state.all_images[state.pair_current_idx]
    state.pair_matches = find_time_matches(current_img)
    state.pair_selected_match = state.pair_matches[0] if state.pair_matches else None
    
    render_pairing_view()

def pair_tag_both():
    """Tag both the current image and selected match with same index but different categories."""
    if not state.all_images:
        return
    
    current_img = state.all_images[state.pair_current_idx]
    idx = state.pair_index
    
    # Tag the main image with main category
    ext_main = os.path.splitext(current_img)[1]
    name_main = f"{state.pair_main_category}_{idx:03d}{ext_main}"
    SorterEngine.stage_image(current_img, state.pair_main_category, name_main)
    
    # Tag the match with adjacent category if selected
    if state.pair_selected_match:
        ext_adj = os.path.splitext(state.pair_selected_match)[1]
        name_adj = f"{state.pair_adj_category}_{idx:03d}{ext_adj}"
        SorterEngine.stage_image(state.pair_selected_match, state.pair_adj_category, name_adj)
        ui.notify(f"Tagged pair #{idx}: {state.pair_main_category} + {state.pair_adj_category}", type='positive')
    else:
        ui.notify(f"Tagged main #{idx}: {state.pair_main_category}", type='positive')
    
    # Increment shared index
    state.pair_index += 1
    
    refresh_staged_info()
    render_pairing_view()

def render_pairing_view():
    """Render the pairing comparison view."""
    if state.pairing_container is None:
        return
    
    state.pairing_container.clear()
    
    categories = state.get_categories()
    
    with state.pairing_container:
        if not state.all_images:
            ui.label("No images loaded. Set paths and click LOAD in the header.").classes('text-gray-400 text-xl text-center w-full py-20')
            return
        
        current_img = state.all_images[state.pair_current_idx]
        is_main_staged = current_img in state.staged_data
        ts = get_file_timestamp(current_img)
        
        # Top control bar
        with ui.row().classes('w-full justify-center items-center gap-4 mb-4 p-4 bg-gray-800 rounded'):
            # Navigation
            ui.button(icon='arrow_back', on_click=lambda: pair_navigate(-1)) \
                .props('flat color=white size=lg').tooltip('Previous (←)')
            ui.label(f"{state.pair_current_idx + 1} / {len(state.all_images)}").classes('text-2xl font-bold')
            ui.button(icon='arrow_forward', on_click=lambda: pair_navigate(1)) \
                .props('flat color=white size=lg').tooltip('Next (→)')
            
            ui.label("|").classes('text-gray-600 mx-4')
            
            # Shared index
            ui.number(label="Index #", value=state.pair_index, min=1, precision=0,
                     on_change=lambda e: setattr(state, 'pair_index', int(e.value))) \
                .props('dense dark outlined').classes('w-24')
            
            # Tag both button
            ui.button("TAG PAIR", icon='label', on_click=pair_tag_both) \
                .props('color=green size=lg').classes('ml-4')
            
            ui.label("|").classes('text-gray-600 mx-4')
            
            # Time window setting
            ui.number(label="±sec", value=state.pair_time_window, min=1, max=300,
                     on_change=lambda e: (setattr(state, 'pair_time_window', int(e.value)), 
                                         pair_navigate(0))) \
                .props('dense dark outlined').classes('w-24')
        
        # Split view - two equal columns
        with ui.row().classes('w-full gap-4'):
            # ===== LEFT SIDE - Main image =====
            with ui.card().classes('flex-1 p-4 bg-gray-800'):
                # Header with category selector
                with ui.row().classes('w-full justify-between items-center mb-2'):
                    ui.label("📁 Main Folder").classes('text-lg font-bold text-blue-400')
                    ui.select(categories, value=state.pair_main_category,
                             on_change=lambda e: setattr(state, 'pair_main_category', e.value)) \
                        .props('dark dense outlined').classes('w-32')
                
                # Output folder
                ui.input(label='Output', value=state.pair_main_output,
                        on_change=lambda e: setattr(state, 'pair_main_output', e.value)) \
                    .props('dark dense outlined').classes('w-full mb-2')
                
                # Filename and timestamp
                ui.label(os.path.basename(current_img)).classes('text-sm text-gray-400 truncate')
                if ts:
                    from datetime import datetime
                    ui.label(f"⏱ {datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')}") \
                        .classes('text-xs text-gray-500 mb-2')
                
                # Main image - use h-96 and fit=contain like gallery mode
                ui.image(f"/thumbnail?path={current_img}&size=800&q={state.preview_quality}") \
                    .classes('w-full h-96 bg-black rounded') \
                    .props('fit=contain')
                
                # Tag status
                if is_main_staged:
                    info = state.staged_data[current_img]
                    ui.label(f"🏷️ {info['cat']} - {info['name']}").classes('text-green-400 mt-2 text-center')
                else:
                    ui.label("Not tagged").classes('text-gray-500 mt-2 text-center')
            
            # ===== RIGHT SIDE - Adjacent folder match =====
            with ui.card().classes('flex-1 p-4 bg-gray-800'):
                # Header with category selector
                with ui.row().classes('w-full justify-between items-center mb-2'):
                    ui.label("📂 Adjacent Folder").classes('text-lg font-bold text-orange-400')
                    ui.select(categories, value=state.pair_adj_category,
                             on_change=lambda e: setattr(state, 'pair_adj_category', e.value)) \
                        .props('dark dense outlined').classes('w-32')
                
                # Output folder
                ui.input(label='Output', value=state.pair_adj_output,
                        on_change=lambda e: setattr(state, 'pair_adj_output', e.value)) \
                    .props('dark dense outlined').classes('w-full mb-2')
                
                if not state.pair_adjacent_folder:
                    ui.label("Set adjacent folder path and click LOAD ADJACENT").classes('text-gray-500 text-center py-20')
                elif not state.pair_matches:
                    ui.label("No matches within time window").classes('text-gray-500 text-center py-20')
                elif state.pair_selected_match:
                    # Show selected match - LARGE (same as main)
                    match_img = state.pair_selected_match
                    is_match_staged = match_img in state.staged_data
                    match_ts = get_file_timestamp(match_img)
                    
                    # Filename and timestamp
                    ui.label(os.path.basename(match_img)).classes('text-sm text-gray-400 truncate')
                    if match_ts and ts:
                        from datetime import datetime
                        diff = match_ts - ts
                        sign = "+" if diff >= 0 else ""
                        ui.label(f"⏱ {datetime.fromtimestamp(match_ts).strftime('%Y-%m-%d %H:%M:%S')} ({sign}{diff:.1f}s)") \
                            .classes('text-xs text-gray-500 mb-2')
                    
                    # Match image - same size as main
                    ui.image(f"/thumbnail?path={match_img}&size=800&q={state.preview_quality}") \
                        .classes('w-full h-96 bg-black rounded') \
                        .props('fit=contain')
                    
                    # Tag status
                    if is_match_staged:
                        info = state.staged_data[match_img]
                        ui.label(f"🏷️ {info['cat']} - {info['name']}").classes('text-green-400 mt-2 text-center')
                    else:
                        ui.label("Not tagged").classes('text-gray-500 mt-2 text-center')
                    
                    # Match selector below
                    if len(state.pair_matches) > 1:
                        ui.separator().classes('my-2')
                        ui.label(f"Other matches ({len(state.pair_matches)} total):").classes('text-xs text-gray-400')
                        with ui.row().classes('w-full gap-2 flex-wrap'):
                            for i, m in enumerate(state.pair_matches[:10]):
                                is_sel = m == state.pair_selected_match
                                ui.button(
                                    f"#{i+1}",
                                    on_click=lambda match=m: select_match(match)
                                ).props(f'{"" if is_sel else "flat"} color={"green" if is_sel else "grey"} dense size=sm')
                else:
                    ui.label("Select a match").classes('text-gray-500 text-center py-20')

def select_match(match_path: str):
    """Select a match image."""
    state.pair_selected_match = match_path
    render_pairing_view()

def refresh_staged_info(force_disk_scan: bool = False):
    """Update staged data and index maps.

    Args:
        force_disk_scan: If True, rescan disk even if category hasn't changed.
                        Set this after APPLY operations that modify files.
    """
    state.staged_data = SorterEngine.get_staged_data()
    staged_keys = set(state.staged_data.keys())

    # Update cached tagged count (O(n) but simpler than set intersection)
    state._cached_tagged_count = sum(1 for img in state.all_images if img in staged_keys)

    # Mark green dots as dirty (lazy calculation)
    state._green_dots_dirty = True

    # Build index map for active category (gallery mode)
    state.index_map.clear()

    # Add staged images
    for orig_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            idx = _extract_index(info['name'])
            if idx is not None:
                state.index_map[idx] = orig_path

    # Lazy disk scan: only rescan when output_dir+category changes or forced
    disk_scan_key = f"{state.output_dir}:{state.active_cat}"
    cache_valid = state._last_disk_scan_key == disk_scan_key
    if not cache_valid or force_disk_scan:
        state._last_disk_scan_key = disk_scan_key
        state._disk_index_map.clear()
        cat_path = os.path.join(state.output_dir, state.active_cat)
        if os.path.exists(cat_path):
            for filename in os.listdir(cat_path):
                if filename.startswith(state.active_cat):
                    idx = _extract_index(filename)
                    if idx is not None:
                        state._disk_index_map[idx] = os.path.join(cat_path, filename)

    # Merge disk results into index_map (staged takes precedence)
    for idx, path in state._disk_index_map.items():
        if idx not in state.index_map:
            state.index_map[idx] = path

    # Build pairing mode index map (both categories)
    state.pair_index_map.clear()

    for orig_path, info in state.staged_data.items():
        idx = _extract_index(info['name'])
        if idx is None:
            continue

        if idx not in state.pair_index_map:
            state.pair_index_map[idx] = {"main": None, "adj": None}

        # Check if this is from main or adjacent category
        if info['cat'] == state.pair_main_category:
            state.pair_index_map[idx]["main"] = orig_path
        elif info['cat'] == state.pair_adj_category:
            state.pair_index_map[idx]["adj"] = orig_path

def _extract_index(filename: str) -> Optional[int]:
    """Extract numeric index from filename (e.g., 'Cat_042.jpg' -> 42)."""
    try:
        return int(filename.rsplit('_', 1)[1].split('.')[0])
    except (ValueError, IndexError):
        return None

# ==========================================
# ACTIONS
# ==========================================

def action_tag(img_path: str, manual_idx: Optional[int] = None):
    """Tag an image with category and index."""
    idx = manual_idx if manual_idx is not None else state.next_index
    ext = os.path.splitext(img_path)[1]
    name = f"{state.active_cat}_{idx:03d}{ext}"
    
    # Check for conflicts
    final_path = os.path.join(state.output_dir, state.active_cat, name)
    staged_names = {v['name'] for v in state.staged_data.values() if v['cat'] == state.active_cat}
    
    if name in staged_names or os.path.exists(final_path):
        ui.notify(f"Conflict: {name} exists. Using suffix.", type='warning')
        name = f"{state.active_cat}_{idx:03d}_{len(staged_names)+1}{ext}"
    
    # Save to undo stack
    state.undo_stack.append({
        "action": "tag",
        "path": img_path,
        "category": state.active_cat,
        "name": name,
        "index": idx
    })
    if len(state.undo_stack) > 50:  # Limit undo history
        state.undo_stack.pop(0)
    
    SorterEngine.stage_image(img_path, state.active_cat, name)

    # Only auto-increment if we used the default next_index (not manual)
    if manual_idx is None:
        state.next_index = idx + 1

    refresh_staged_info()
    # Use targeted refresh - sidebar index grid needs update, but skip heavy rebuild
    render_sidebar()  # Update index grid to show new tag
    refresh_grid_only()  # Just grid + pagination stats

def action_untag(img_path: str):
    """Remove staging from an image."""
    # Save to undo stack
    if img_path in state.staged_data:
        info = state.staged_data[img_path]
        state.undo_stack.append({
            "action": "untag",
            "path": img_path,
            "category": info['cat'],
            "name": info['name'],
            "index": _extract_index(info['name'])
        })
        if len(state.undo_stack) > 50:
            state.undo_stack.pop(0)
    
    SorterEngine.clear_staged_item(img_path)
    refresh_staged_info()
    # Use targeted refresh - sidebar index grid needs update
    render_sidebar()  # Update index grid to show removed tag
    refresh_grid_only()  # Just grid + pagination stats

def action_delete(img_path: str):
    """Delete image to trash."""
    # Save to undo stack
    state.undo_stack.append({
        "action": "delete",
        "path": img_path
    })
    if len(state.undo_stack) > 50:
        state.undo_stack.pop(0)
    
    SorterEngine.delete_to_trash(img_path)
    load_images()

def action_undo():
    """Undo the last action."""
    if not state.undo_stack:
        ui.notify("Nothing to undo", type='warning')
        return
    
    last = state.undo_stack.pop()
    
    if last["action"] == "tag":
        # Undo tag = untag
        SorterEngine.clear_staged_item(last["path"])
        ui.notify(f"Undid tag: {os.path.basename(last['path'])}", type='info')
    
    elif last["action"] == "untag":
        # Undo untag = re-tag with same settings
        SorterEngine.stage_image(last["path"], last["category"], last["name"])
        ui.notify(f"Undid untag: {os.path.basename(last['path'])}", type='info')
    
    elif last["action"] == "delete":
        # Undo delete = restore from trash
        trash_path = os.path.join(os.path.dirname(last["path"]), "_DELETED", os.path.basename(last["path"]))
        if os.path.exists(trash_path):
            import shutil
            shutil.move(trash_path, last["path"])
            ui.notify(f"Restored: {os.path.basename(last['path'])}", type='info')
        else:
            ui.notify("Cannot restore - file not in trash", type='warning')
    
    refresh_staged_info()
    refresh_ui()

def action_save_tags():
    """Save current tags to database for later restoration."""
    if not state.all_images:
        ui.notify("No folder loaded", type='warning')
        return
    
    saved = SorterEngine.save_folder_tags(state.source_dir, state.profile_name)
    if saved > 0:
        ui.notify(f"Saved {saved} tags", type='positive')
    else:
        ui.notify("No tags to save", type='info')

async def action_apply_page():
    """Apply staged changes for current page only."""
    batch = state.get_current_batch()
    if not batch:
        ui.notify("No images on current page", type='warning')
        return

    # Get tagged images and their categories before commit (they'll be moved/copied)
    tagged_batch = []
    for img_path in batch:
        if img_path in state.staged_data:
            info = state.staged_data[img_path]
            # Calculate destination path
            dest_path = os.path.join(state.output_dir, info['name'])
            tagged_batch.append((img_path, info['cat'], dest_path))

    SorterEngine.commit_batch(batch, state.output_dir, state.cleanup_mode, state.batch_mode)

    # Caption on apply if enabled
    if state.caption_on_apply and tagged_batch:
        state.load_caption_settings()
        caption_count = 0
        for orig_path, category, dest_path in tagged_batch:
            if os.path.exists(dest_path):
                prompt = SorterEngine.get_category_prompt(state.profile_name, category)
                caption, error = await run.io_bound(
                    SorterEngine.caption_image_vllm,
                    dest_path, prompt, state.caption_settings
                )
                if caption:
                    SorterEngine.save_caption(dest_path, caption, state.caption_settings.get('model_name', 'local-model'))
                    SorterEngine.write_caption_sidecar(dest_path, caption)
                    caption_count += 1
        if caption_count > 0:
            ui.notify(f"Captioned {caption_count} images", type='info')

    ui.notify(f"Page processed ({state.batch_mode})", type='positive')
    # Force disk rescan since files were committed
    state._last_disk_scan_key = ""
    load_images()

async def action_apply_global():
    """Apply all staged changes globally."""
    ui.notify("Starting global apply... This may take a while.", type='info')

    # Capture staged data before commit for captioning
    staged_before_commit = {}
    if state.caption_on_apply:
        for img_path, info in state.staged_data.items():
            dest_path = os.path.join(state.output_dir, info['name'])
            staged_before_commit[img_path] = {'cat': info['cat'], 'dest': dest_path}

    await run.io_bound(
        SorterEngine.commit_global,
        state.output_dir,
        state.cleanup_mode,
        state.batch_mode,
        state.source_dir,
        state.profile_name
    )

    # Caption on apply if enabled
    if state.caption_on_apply and staged_before_commit:
        state.load_caption_settings()
        ui.notify(f"Captioning {len(staged_before_commit)} images...", type='info')

        caption_count = 0
        for orig_path, info in staged_before_commit.items():
            dest_path = info['dest']
            if os.path.exists(dest_path):
                prompt = SorterEngine.get_category_prompt(state.profile_name, info['cat'])
                caption, error = await run.io_bound(
                    SorterEngine.caption_image_vllm,
                    dest_path, prompt, state.caption_settings
                )
                if caption:
                    SorterEngine.save_caption(dest_path, caption, state.caption_settings.get('model_name', 'local-model'))
                    SorterEngine.write_caption_sidecar(dest_path, caption)
                    caption_count += 1

        if caption_count > 0:
            ui.notify(f"Captioned {caption_count} images", type='info')

    # Force disk rescan since files were committed
    state._last_disk_scan_key = ""
    load_images()
    ui.notify("Global apply complete!", type='positive')

# ==========================================
# UI COMPONENTS
# ==========================================

def open_zoom_dialog(path: str, title: Optional[str] = None, show_untag: bool = False, show_jump: bool = False):
    """Open full-resolution image dialog with optional actions."""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-screen-xl p-0 gap-0 bg-black'):
        with ui.row().classes('w-full justify-between items-center p-2 bg-gray-900 text-white'):
            ui.label(title or os.path.basename(path)).classes('font-bold truncate px-2')
            
            with ui.row().classes('gap-2'):
                # Jump to page button
                if show_jump and path in state.all_images:
                    def jump_to_image():
                        img_idx = state.all_images.index(path)
                        target_page = img_idx // state.page_size
                        dialog.close()
                        set_page(target_page)
                        ui.notify(f"Jumped to page {target_page + 1}", type='info')
                    
                    ui.button(icon='location_searching', on_click=jump_to_image) \
                        .props('flat round dense color=blue') \
                        .tooltip('Jump to image location')
                
                # Untag button
                if show_untag:
                    def untag_and_close():
                        action_untag(path)
                        dialog.close()
                        ui.notify("Tag removed", type='positive')
                    
                    ui.button(icon='label_off', on_click=untag_and_close) \
                        .props('flat round dense color=red') \
                        .tooltip('Remove tag')
                
                ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        ui.image(f"/full_res?path={path}").classes('w-full h-auto object-contain max-h-[85vh]')
    dialog.open()

def open_pair_preview_dialog(index: int, pair_info: Dict):
    """Open dialog showing both main and adjacent images for a paired index."""
    main_path = pair_info.get("main")
    adj_path = pair_info.get("adj")
    
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-screen-xl p-4 bg-gray-900'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label(f"Pair #{index}").classes('text-xl font-bold text-white')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        with ui.row().classes('w-full gap-4'):
            # Main image
            with ui.card().classes('flex-1 p-4 bg-gray-800'):
                ui.label(f"📁 {state.pair_main_category}").classes('text-lg font-bold text-blue-400 mb-2')
                if main_path:
                    ui.label(os.path.basename(main_path)).classes('text-xs text-gray-400 truncate mb-2')
                    ui.image(f"/thumbnail?path={main_path}&size=600&q=80") \
                        .classes('w-full h-64 bg-black rounded') \
                        .props('fit=contain')
                    
                    def untag_main():
                        action_untag(main_path)
                        dialog.close()
                        render_sidebar()
                    
                    ui.button("Untag", icon='label_off', on_click=untag_main) \
                        .props('flat color=red').classes('mt-2')
                else:
                    ui.label("No image").classes('text-gray-500 text-center py-20')
            
            # Adjacent image
            with ui.card().classes('flex-1 p-4 bg-gray-800'):
                ui.label(f"📂 {state.pair_adj_category}").classes('text-lg font-bold text-orange-400 mb-2')
                if adj_path:
                    ui.label(os.path.basename(adj_path)).classes('text-xs text-gray-400 truncate mb-2')
                    ui.image(f"/thumbnail?path={adj_path}&size=600&q=80") \
                        .classes('w-full h-64 bg-black rounded') \
                        .props('fit=contain')
                    
                    def untag_adj():
                        action_untag(adj_path)
                        dialog.close()
                        render_sidebar()
                    
                    ui.button("Untag", icon='label_off', on_click=untag_adj) \
                        .props('flat color=red').classes('mt-2')
                else:
                    ui.label("No image").classes('text-gray-500 text-center py-20')
    
    dialog.open()

def open_hotkey_dialog(category: str):
    """Open dialog to set/change hotkey for a category."""
    # Find current hotkey if any
    current_hotkey = None
    for hk, cat in state.category_hotkeys.items():
        if cat == category:
            current_hotkey = hk
            break

    with ui.dialog() as dialog, ui.card().classes('p-4 bg-gray-800'):
        ui.label(f'Set Hotkey for "{category}"').classes('font-bold text-white mb-2')

        ui.label('Press a letter key (A-Z) to assign as hotkey').classes('text-gray-400 text-sm mb-4')

        if current_hotkey:
            ui.label(f'Current: {current_hotkey.upper()}').classes('text-blue-400 mb-2')

        hotkey_input = ui.input(
            placeholder='Type a letter...',
            value=current_hotkey or ''
        ).props('dark outlined dense autofocus').classes('w-full')

        def save_hotkey():
            key = hotkey_input.value.lower().strip()
            if key and len(key) == 1 and key.isalpha():
                # Remove old hotkey for this category
                to_remove = [hk for hk, c in state.category_hotkeys.items() if c == category]
                for hk in to_remove:
                    del state.category_hotkeys[hk]

                # Remove if another category had this hotkey
                if key in state.category_hotkeys:
                    del state.category_hotkeys[key]

                # Set new hotkey
                state.category_hotkeys[key] = category
                ui.notify(f'Hotkey "{key.upper()}" set for {category}', type='positive')
                dialog.close()
                render_sidebar()
            elif key == '':
                # Clear hotkey
                to_remove = [hk for hk, c in state.category_hotkeys.items() if c == category]
                for hk in to_remove:
                    del state.category_hotkeys[hk]
                ui.notify(f'Hotkey cleared for {category}', type='info')
                dialog.close()
                render_sidebar()
            else:
                ui.notify('Please enter a single letter (A-Z)', type='warning')

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Clear', on_click=lambda: (
                hotkey_input.set_value(''),
                save_hotkey()
            )).props('flat color=grey')
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=save_hotkey).props('color=green')

    dialog.open()

def open_caption_settings_dialog():
    """Open dialog to configure caption API settings."""
    state.load_caption_settings()
    settings = state.caption_settings.copy()

    with ui.dialog() as dialog, ui.card().classes('p-6 bg-gray-800 w-96'):
        ui.label('Caption API Settings').classes('text-xl font-bold text-white mb-4')

        api_endpoint = ui.input(
            label='API Endpoint',
            value=settings.get('api_endpoint', 'http://localhost:8080/v1/chat/completions')
        ).props('dark outlined dense').classes('w-full mb-2')

        model_name = ui.input(
            label='Model Name',
            value=settings.get('model_name', 'local-model')
        ).props('dark outlined dense').classes('w-full mb-2')

        max_tokens = ui.number(
            label='Max Tokens',
            value=settings.get('max_tokens', 300),
            min=50, max=2000
        ).props('dark outlined dense').classes('w-full mb-2')

        ui.label('Temperature').classes('text-gray-400 text-sm')
        temperature = ui.slider(
            min=0, max=1, step=0.1,
            value=settings.get('temperature', 0.7)
        ).props('color=purple label-always').classes('w-full mb-2')

        timeout = ui.number(
            label='Timeout (seconds)',
            value=settings.get('timeout_seconds', 60),
            min=10, max=300
        ).props('dark outlined dense').classes('w-full mb-2')

        batch_size = ui.number(
            label='Batch Size',
            value=settings.get('batch_size', 4),
            min=1, max=16
        ).props('dark outlined dense').classes('w-full mb-4')

        def save_settings():
            SorterEngine.save_caption_settings(
                state.profile_name,
                api_endpoint=api_endpoint.value,
                model_name=model_name.value,
                max_tokens=int(max_tokens.value),
                temperature=float(temperature.value),
                timeout_seconds=int(timeout.value),
                batch_size=int(batch_size.value)
            )
            state.load_caption_settings()
            ui.notify('Caption settings saved!', type='positive')
            dialog.close()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save', on_click=save_settings).props('color=purple')

    dialog.open()

def open_prompt_editor_dialog():
    """Open dialog to edit category prompts."""
    categories = state.get_categories()
    prompts = SorterEngine.get_all_category_prompts(state.profile_name)

    with ui.dialog() as dialog, ui.card().classes('p-6 bg-gray-800 w-[600px] max-h-[80vh]'):
        ui.label('Category Prompts').classes('text-xl font-bold text-white mb-2')
        ui.label('Set custom prompts for each category. Leave empty for default.').classes('text-gray-400 text-sm mb-4')

        default_prompt = "Describe this image in detail for training purposes. Include subjects, actions, setting, colors, and composition."
        ui.label(f'Default: "{default_prompt[:60]}..."').classes('text-gray-500 text-xs mb-4')

        # Store text areas for later access
        prompt_inputs = {}

        with ui.scroll_area().classes('w-full max-h-96'):
            for cat in categories:
                current_prompt = prompts.get(cat, '')
                with ui.card().classes('w-full p-3 bg-gray-700 mb-2'):
                    ui.label(cat).classes('font-bold text-purple-400 mb-1')
                    prompt_inputs[cat] = ui.textarea(
                        value=current_prompt,
                        placeholder=default_prompt
                    ).props('dark outlined dense rows=2').classes('w-full')

        def save_all_prompts():
            for cat, textarea in prompt_inputs.items():
                prompt = textarea.value.strip()
                if prompt:
                    SorterEngine.save_category_prompt(state.profile_name, cat, prompt)
                else:
                    # Clear the prompt to use default
                    SorterEngine.save_category_prompt(state.profile_name, cat, '')
            ui.notify(f'Prompts saved for {len(prompt_inputs)} categories!', type='positive')
            dialog.close()

        with ui.row().classes('w-full justify-end gap-2 mt-4'):
            ui.button('Cancel', on_click=dialog.close).props('flat')
            ui.button('Save All', on_click=save_all_prompts).props('color=purple')

    dialog.open()

def open_caption_dialog(img_path: str):
    """Open dialog to view/edit/generate caption for a single image."""
    existing = SorterEngine.get_caption(img_path)
    state.load_caption_settings()

    # Get category for this image
    staged_info = state.staged_data.get(img_path)
    category = staged_info['cat'] if staged_info else state.active_cat

    with ui.dialog() as dialog, ui.card().classes('p-6 bg-gray-800 w-[500px]'):
        ui.label('Image Caption').classes('text-xl font-bold text-white mb-2')
        ui.label(os.path.basename(img_path)).classes('text-gray-400 text-sm mb-4 truncate')

        # Thumbnail preview
        ui.image(f"/thumbnail?path={img_path}&size=300&q=60").classes('w-full h-48 bg-black rounded mb-4').props('fit=contain')

        # Caption textarea
        caption_text = ui.textarea(
            label='Caption',
            value=existing['caption'] if existing else '',
            placeholder='Caption will appear here...'
        ).props('dark outlined rows=4').classes('w-full mb-2')

        # Model info
        if existing:
            ui.label(f"Model: {existing.get('model', 'unknown')} | {existing.get('generated_at', '')}").classes('text-gray-500 text-xs mb-4')

        # Status label for progress
        status_label = ui.label('').classes('text-purple-400 text-sm mb-2')

        async def generate_caption():
            status_label.set_text('Generating caption...')
            prompt = SorterEngine.get_category_prompt(state.profile_name, category)

            caption, error = await run.io_bound(
                SorterEngine.caption_image_vllm,
                img_path, prompt, state.caption_settings
            )

            if caption:
                caption_text.set_value(caption)
                status_label.set_text('Caption generated!')
            else:
                status_label.set_text(f'Error: {error}')

        def save_caption():
            text = caption_text.value.strip()
            if text:
                SorterEngine.save_caption(img_path, text, state.caption_settings.get('model_name', 'manual'))
                state.caption_cache.add(img_path)
                ui.notify('Caption saved!', type='positive')
                dialog.close()
                refresh_grid_only()
            else:
                ui.notify('Caption is empty', type='warning')

        def save_with_sidecar():
            text = caption_text.value.strip()
            if text:
                SorterEngine.save_caption(img_path, text, state.caption_settings.get('model_name', 'manual'))
                sidecar_path = SorterEngine.write_caption_sidecar(img_path, text)
                state.caption_cache.add(img_path)
                if sidecar_path:
                    ui.notify(f'Caption saved + sidecar written!', type='positive')
                else:
                    ui.notify('Caption saved (sidecar failed)', type='warning')
                dialog.close()
                refresh_grid_only()
            else:
                ui.notify('Caption is empty', type='warning')

        with ui.row().classes('w-full justify-between gap-2'):
            ui.button('Generate', icon='auto_awesome', on_click=generate_caption).props('color=purple')
            with ui.row().classes('gap-2'):
                ui.button('Cancel', on_click=dialog.close).props('flat')
                ui.button('Save', on_click=save_caption).props('color=green')
                ui.button('Save + Sidecar', on_click=save_with_sidecar).props('color=blue').tooltip('Also write .txt file')

    dialog.open()

async def action_caption_category():
    """Caption all images tagged with the active category."""
    if state.captioning_in_progress:
        ui.notify('Captioning already in progress', type='warning')
        return

    # Find all images tagged with active category
    images_to_caption = []
    for img_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            images_to_caption.append((img_path, state.active_cat))

    if not images_to_caption:
        ui.notify(f'No images tagged with {state.active_cat}', type='warning')
        return

    state.load_caption_settings()
    state.captioning_in_progress = True

    # Create progress dialog
    with ui.dialog() as progress_dialog, ui.card().classes('p-6 bg-gray-800 w-96'):
        ui.label('Captioning Images...').classes('text-xl font-bold text-white mb-4')
        progress_bar = ui.linear_progress(value=0).props('instant-feedback color=purple').classes('w-full mb-2')
        progress_label = ui.label('0 / 0').classes('text-gray-400 text-center w-full mb-2')
        status_label = ui.label('Starting...').classes('text-purple-400 text-sm text-center w-full')

        cancel_requested = {'value': False}

        def request_cancel():
            cancel_requested['value'] = True
            status_label.set_text('Cancelling...')

        ui.button('Cancel', on_click=request_cancel).props('flat color=red').classes('w-full mt-4')

    progress_dialog.open()

    try:
        total = len(images_to_caption)
        success_count = 0
        fail_count = 0

        def get_prompt(cat):
            return SorterEngine.get_category_prompt(state.profile_name, cat)

        for i, (img_path, category) in enumerate(images_to_caption):
            if cancel_requested['value']:
                break

            progress_bar.set_value(i / total)
            progress_label.set_text(f'{i + 1} / {total}')
            status_label.set_text(f'Captioning {os.path.basename(img_path)}...')

            prompt = get_prompt(category)
            caption, error = await run.io_bound(
                SorterEngine.caption_image_vllm,
                img_path, prompt, state.caption_settings
            )

            if caption:
                SorterEngine.save_caption(img_path, caption, state.caption_settings.get('model_name', 'local-model'))
                state.caption_cache.add(img_path)
                success_count += 1
            else:
                error_caption = f"[ERROR] {error}"
                SorterEngine.save_caption(img_path, error_caption, state.caption_settings.get('model_name', 'local-model'))
                fail_count += 1

        progress_bar.set_value(1)
        progress_label.set_text(f'{total} / {total}')

        if cancel_requested['value']:
            status_label.set_text(f'Cancelled. {success_count} OK, {fail_count} failed')
        else:
            status_label.set_text(f'Done! {success_count} OK, {fail_count} failed')

        await asyncio.sleep(1.5)
        progress_dialog.close()

    finally:
        state.captioning_in_progress = False
        refresh_grid_only()

    ui.notify(f'Captioned {success_count}/{total} images', type='positive' if fail_count == 0 else 'warning')

def render_sidebar():
    """Render category management sidebar."""
    state.sidebar_container.clear()
    
    with state.sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2 text-white')
        
        # Number grid (1-25) - different view for pairing mode
        if state.current_mode == "pairing":
            # Pairing mode: show both main and adjacent in grid
            ui.label(f"Index Grid ({state.pair_main_category} + {state.pair_adj_category})").classes('text-xs text-gray-400 mb-1')
            with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
                for i in range(1, 26):
                    pair_info = state.pair_index_map.get(i, {})
                    has_main = pair_info.get("main") is not None
                    has_adj = pair_info.get("adj") is not None
                    
                    # Color coding: green=both, blue=main only, orange=adj only, grey=none
                    if has_main and has_adj:
                        color = 'green'
                    elif has_main:
                        color = 'blue'
                    elif has_adj:
                        color = 'orange'
                    else:
                        color = 'grey-9'
                    
                    def make_pair_click_handler(num: int):
                        def handler():
                            pair_info = state.pair_index_map.get(num, {})
                            if pair_info.get("main") or pair_info.get("adj"):
                                # Show dialog with both images
                                open_pair_preview_dialog(num, pair_info)
                            else:
                                # Number is free - set as next index
                                state.pair_index = num
                                render_sidebar()
                        return handler
                    
                    ui.button(str(i), on_click=make_pair_click_handler(i)) \
                      .props(f'color={color} size=sm flat') \
                      .classes('w-full border border-gray-800')
            
            # Legend
            with ui.row().classes('w-full gap-2 text-xs mb-4'):
                ui.label("🟢 Both").classes('text-green-400')
                ui.label("🔵 Main").classes('text-blue-400')
                ui.label("🟠 Adj").classes('text-orange-400')
        else:
            # Gallery mode: show single category
            with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
                for i in range(1, 26):
                    is_used = i in state.index_map
                    color = 'green' if is_used else 'grey-9'
                    
                    def make_click_handler(num: int):
                        def handler():
                            if num in state.index_map:
                                # Number is used - open preview
                                img_path = state.index_map[num]
                                is_staged = img_path in state.staged_data
                                open_zoom_dialog(
                                    img_path, 
                                    f"{state.active_cat} #{num}",
                                    show_untag=is_staged,
                                    show_jump=True
                                )
                            else:
                                # Number is free - set as next index
                                state.next_index = num
                                render_sidebar()
                        return handler
                    
                    ui.button(str(i), on_click=make_click_handler(i)) \
                      .props(f'color={color} size=sm flat') \
                      .classes('w-full border border-gray-800')
        
        # Category Manager (expanded)
        with ui.row().classes('w-full justify-between items-center mt-2'):
            ui.label("📂 Categories").classes('text-sm font-bold text-gray-400')
            ui.button(icon='edit_note', on_click=open_prompt_editor_dialog) \
                .props('flat dense color=purple size=sm').tooltip('Edit Prompts')

        categories = state.get_categories()
        
        # Category list with hotkey buttons
        for cat in categories:
            is_active = cat == state.active_cat
            hotkey = None
            # Find if this category has a hotkey
            for hk, cat_name in state.category_hotkeys.items():
                if cat_name == cat:
                    hotkey = hk
                    break
            
            with ui.row().classes('w-full items-center no-wrap gap-1'):
                # Category button
                ui.button(
                    cat,
                    on_click=lambda c=cat: (
                        setattr(state, 'active_cat', c),
                        refresh_staged_info(),
                        render_sidebar()
                    )
                ).props(f'{"" if is_active else "flat"} color={"green" if is_active else "grey"} dense') \
                 .classes('flex-grow text-left')
                
                # Hotkey badge/button
                def make_hotkey_handler(category):
                    def handler():
                        open_hotkey_dialog(category)
                    return handler
                
                if hotkey:
                    ui.button(hotkey.upper(), on_click=make_hotkey_handler(cat)) \
                        .props('flat dense color=blue size=sm').classes('w-8')
                else:
                    ui.button('+', on_click=make_hotkey_handler(cat)) \
                        .props('flat dense color=grey size=sm').classes('w-8') \
                        .tooltip('Set hotkey')
        
        # Add new category
        with ui.row().classes('w-full items-center no-wrap mt-2'):
            new_cat_input = ui.input(placeholder='New category...') \
                .props('dense outlined dark').classes('flex-grow')
            
            def add_category():
                if new_cat_input.value:
                    SorterEngine.add_category(new_cat_input.value, state.profile_name)
                    state.active_cat = new_cat_input.value
                    refresh_staged_info()
                    render_sidebar()
            
            ui.button(icon='add', on_click=add_category).props('flat color=green')
        
        # Delete category
        with ui.expansion('Danger Zone', icon='warning').classes('w-full text-red-400 mt-2'):
            def delete_category():
                # Also remove any hotkey for this category
                to_remove = [hk for hk, c in state.category_hotkeys.items() if c == state.active_cat]
                for hk in to_remove:
                    del state.category_hotkeys[hk]
                SorterEngine.delete_category(state.active_cat, state.profile_name)
                refresh_staged_info()
                render_sidebar()
            
            ui.button('DELETE CATEGORY', color='red', on_click=delete_category).classes('w-full')
        
        ui.separator().classes('my-4 bg-gray-700')
        
        # Index counter
        with ui.row().classes('w-full items-end no-wrap'):
            ui.number(label="Next Index", min=1, precision=0) \
                .bind_value(state, 'next_index') \
                .classes('flex-grow').props('dark outlined')
            
            def reset_index():
                state.next_index = (max(state.index_map.keys()) + 1) if state.index_map else 1
                render_sidebar()
            
            ui.button('🔄', on_click=reset_index).props('flat color=white')
        
        # Keyboard shortcuts help
        ui.separator().classes('my-4 bg-gray-700')
        with ui.expansion('⌨️ Keyboard Shortcuts', icon='keyboard').classes('w-full text-gray-400'):
            shortcuts = [
                ("1-9", "Tag hovered image with index"),
                ("0", "Tag with next index"),
                ("U", "Untag hovered image*"),
                ("F", "Cycle filter*"),
                ("Ctrl+S", "Save tags"),
                ("Ctrl+Z", "Undo last action"),
                ("A-Z", "Switch category (set above)"),
                ("← →", "Previous/Next page"),
                ("Dbl-click", "Tag/Untag image"),
            ]
            for key, desc in shortcuts:
                with ui.row().classes('w-full justify-between text-xs'):
                    ui.label(key).classes('text-green-400 font-mono')
                    ui.label(desc).classes('text-gray-500')
            ui.label("*unless assigned to category").classes('text-gray-600 text-xs mt-1')

def render_gallery():
    """Render image gallery grid."""
    state.grid_container.clear()
    batch = state.get_current_batch()
    
    with state.grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-3'):
            for img_path in batch:
                render_image_card(img_path)

def _set_hovered(path: str):
    """Helper for hover tracking - used with partial for memory efficiency."""
    state.hovered_image = path

def _clear_hovered():
    """Helper for hover tracking - used with partial for memory efficiency."""
    state.hovered_image = None

def render_image_card(img_path: str):
    """Render individual image card.
    Uses functools.partial instead of lambdas for better memory efficiency."""
    is_staged = img_path in state.staged_data
    has_caption = img_path in state.caption_cache
    thumb_size = 800

    card = ui.card().classes('p-2 bg-gray-900 border border-gray-700 no-shadow hover:border-green-500 transition-colors')

    with card:
        # Track hover for keyboard shortcuts - using partial instead of lambda
        card.on('mouseenter', partial(_set_hovered, img_path))
        card.on('mouseleave', _clear_hovered)

        # Header with filename and actions
        with ui.row().classes('w-full justify-between no-wrap mb-1'):
            with ui.row().classes('items-center gap-1'):
                ui.label(os.path.basename(img_path)[:15]).classes('text-xs text-gray-400 truncate')
                # Caption indicator
                if has_caption:
                    ui.icon('description', size='xs').classes('text-purple-400').tooltip('Has caption')
            with ui.row().classes('gap-0'):
                ui.button(
                    icon='auto_awesome',
                    on_click=partial(open_caption_dialog, img_path)
                ).props('flat size=sm dense color=purple').tooltip('Caption')
                ui.button(
                    icon='zoom_in',
                    on_click=partial(open_zoom_dialog, img_path)
                ).props('flat size=sm dense color=white')
                ui.button(
                    icon='delete',
                    on_click=partial(action_delete, img_path)
                ).props('flat size=sm dense color=red')

        # Thumbnail with double-click to tag
        img = ui.image(f"/thumbnail?path={img_path}&size={thumb_size}&q={state.preview_quality}") \
            .classes('w-full h-64 bg-black rounded cursor-pointer') \
            .props('fit=contain no-spinner')

        # Double-click to tag (if not already tagged) - using partial
        if not is_staged:
            img.on('dblclick', partial(action_tag, img_path))
        else:
            img.on('dblclick', partial(action_untag, img_path))

        # Tagging UI
        if is_staged:
            info = state.staged_data[img_path]
            idx = _extract_index(info['name'])
            idx_str = str(idx) if idx else "?"
            ui.label(f"🏷️ {info['cat']}").classes('text-center text-green-400 text-xs py-1 w-full')
            ui.button(
                f"Untag (#{idx_str})",
                on_click=partial(action_untag, img_path)
            ).props('flat color=grey-5 dense').classes('w-full')
        else:
            with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                local_idx = ui.number(value=state.next_index, precision=0) \
                    .props('dense dark outlined').classes('w-1/3')
                # Note: This one still needs lambda due to dynamic local_idx.value access
                ui.button(
                    'Tag',
                    on_click=lambda p=img_path, i=local_idx: action_tag(p, int(i.value))
                ).classes('w-2/3').props('color=green dense')

def render_pagination():
    """Render pagination controls."""
    state.pagination_container.clear()
    
    stats = state.get_stats()
    
    with state.pagination_container:
        # Stats bar
        with ui.row().classes('w-full justify-center items-center gap-4 mb-2'):
            ui.label(f"📁 {stats['total']} images").classes('text-gray-400')
            ui.label(f"🏷️ {stats['tagged']} tagged").classes('text-green-400')
            ui.label(f"⬜ {stats['untagged']} untagged").classes('text-gray-500')
            
            # Filter toggle
            filter_colors = {"all": "grey", "tagged": "green", "untagged": "orange"}
            filter_icons = {"all": "filter_list", "tagged": "label", "untagged": "label_off"}
            ui.button(
                f"Filter: {state.filter_mode}",
                icon=filter_icons[state.filter_mode],
                on_click=lambda: (
                    setattr(state, 'filter_mode', {"all": "untagged", "untagged": "tagged", "tagged": "all"}[state.filter_mode]),
                    setattr(state, 'page', 0),
                    refresh_ui()
                )
            ).props(f'flat color={filter_colors[state.filter_mode]}').classes('ml-4')
            
            # Save button
            ui.button(
                icon='save',
                on_click=action_save_tags
            ).props('flat color=blue').tooltip('Save tags (Ctrl+S)')
            
            # Undo button
            ui.button(
                icon='undo',
                on_click=action_undo
            ).props('flat color=white').tooltip('Undo (Ctrl+Z)')
        
        if state.total_pages <= 1:
            return
        
        # Page slider
        ui.slider(
            min=0,
            max=state.total_pages - 1,
            value=state.page,
            on_change=lambda e: set_page(int(e.value))
        ).classes('w-1/2 mb-2').props('color=green')
        
        # Page info
        ui.label(f"Page {state.page + 1} / {state.total_pages}").classes('text-gray-400 text-sm mb-2')
        
        # Page buttons
        with ui.row().classes('items-center gap-2'):
            # Previous button
            if state.page > 0:
                ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white')
            
            # Page numbers (show current ±2)
            start = max(0, state.page - 2)
            end = min(state.total_pages, state.page + 3)
            
            green_dots = state.get_green_dots()  # Lazy calculation
            for p in range(start, end):
                dot = " 🟢" if p in green_dots else ""
                color = "white" if p == state.page else "grey-6"
                ui.button(
                    f"{p+1}{dot}",
                    on_click=lambda page=p: set_page(page)
                ).props(f'flat color={color}')
            
            # Next button
            if state.page < state.total_pages - 1:
                ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat color=white')

def set_page(p: int):
    """Navigate to specific page."""
    state.page = max(0, min(p, state.total_pages - 1))
    refresh_ui()

def refresh_ui():
    """Refresh all UI components."""
    render_sidebar()
    render_pagination()
    render_gallery()

def refresh_grid_only():
    """Refresh only the grid and pagination stats - skip sidebar rebuild.
    Use for tag/untag operations where sidebar doesn't need full rebuild."""
    render_pagination()
    render_gallery()

def handle_keyboard(e):
    """Handle keyboard navigation and shortcuts (fallback)."""
    if not e.action.keydown:
        return
    
    key = e.key.name if hasattr(e.key, 'name') else str(e.key)
    ctrl = e.modifiers.ctrl if hasattr(e.modifiers, 'ctrl') else False
    key_lower = key.lower() if isinstance(key, str) else key
    
    # Mode-specific navigation
    if state.current_mode == "pairing":
        # Pairing mode navigation
        if key == 'ArrowLeft':
            pair_navigate(-1)
            return
        elif key == 'ArrowRight':
            pair_navigate(1)
            return
        elif key == 'Enter' or key == ' ':
            pair_tag_both()
            return
    else:
        # Gallery mode navigation
        if key == 'ArrowLeft' and state.page > 0:
            set_page(state.page - 1)
            return
        elif key == 'ArrowRight' and state.page < state.total_pages - 1:
            set_page(state.page + 1)
            return
    
    # Common shortcuts for both modes
    
    # Undo (Ctrl+Z)
    if key_lower == 'z' and ctrl:
        action_undo()
    
    # Save (Ctrl+S)
    elif key_lower == 's' and ctrl:
        action_save_tags()
    
    # Custom category hotkeys (single letters A-Z, not ctrl)
    elif not ctrl and len(key) == 1 and key_lower.isalpha() and key_lower in state.category_hotkeys:
        state.active_cat = state.category_hotkeys[key_lower]
        refresh_staged_info()
        if state.current_mode == "gallery":
            refresh_ui()
        else:
            render_pairing_view()
        ui.notify(f"Category: {state.active_cat}", type='info')
    
    # Gallery mode only shortcuts
    elif state.current_mode == "gallery":
        # Number keys 1-9 to tag hovered image
        if key in '123456789' and not ctrl:
            if state.hovered_image and state.hovered_image not in state.staged_data:
                action_tag(state.hovered_image, int(key))
        
        # 0 key to tag with next_index
        elif key == '0' and not ctrl and state.hovered_image and state.hovered_image not in state.staged_data:
            action_tag(state.hovered_image)
        
        # U to untag hovered image (only if not assigned as category hotkey)
        elif key_lower == 'u' and not ctrl and 'u' not in state.category_hotkeys:
            if state.hovered_image and state.hovered_image in state.staged_data:
                action_untag(state.hovered_image)
        
        # F to cycle filter modes (only if not assigned as category hotkey)
        elif key_lower == 'f' and not ctrl and 'f' not in state.category_hotkeys:
            modes = ["all", "untagged", "tagged"]
            current_idx = modes.index(state.filter_mode)
            state.filter_mode = modes[(current_idx + 1) % 3]
            state.page = 0  # Reset to first page when changing filter
            refresh_ui()
            ui.notify(f"Filter: {state.filter_mode}", type='info')

# ==========================================
# MAIN LAYOUT
# ==========================================

def build_header():
    """Build application header."""
    with ui.header().classes('items-center bg-slate-900 text-white border-b border-gray-700').style('height: 70px'):
        with ui.row().classes('w-full items-center gap-4 no-wrap px-4'):
            ui.label('🖼️ NiceSorter').classes('text-xl font-bold shrink-0 text-green-400')
            
            # Profile selector with add/delete
            def change_profile(e):
                # Auto-save before switching profile
                if state.all_images and state.staged_data:
                    SorterEngine.save_folder_tags(state.source_dir, state.profile_name)
                
                state.profile_name = e.value
                state.load_active_profile()
                
                # Reset to first available category for new profile
                cats = state.get_categories()
                state.active_cat = cats[0] if cats else "control"
                
                # Clear staging and hotkeys for new profile
                SorterEngine.clear_staging_area()
                state.category_hotkeys = {}  # Reset hotkeys when switching profile
                state.all_images = []
                state.staged_data = {}
                
                refresh_staged_info()
                refresh_ui()
            
            profile_select = ui.select(
                list(state.profiles.keys()), 
                value=state.profile_name,
                on_change=change_profile
            ).props('dark dense options-dense borderless').classes('w-32')
            
            def add_profile():
                with ui.dialog() as dialog, ui.card().classes('p-4'):
                    ui.label('New Profile Name').classes('font-bold')
                    name_input = ui.input(placeholder='Profile name').props('autofocus')
                    
                    def do_create():
                        name = name_input.value
                        if name and name not in state.profiles:
                            state.profiles[name] = {"tab5_source": "/storage", "tab5_out": "/storage"}
                            SorterEngine.save_tab_paths(name, t5_s="/storage", t5_o="/storage")
                            state.profile_name = name
                            state.load_active_profile()
                            dialog.close()
                            ui.notify(f"Profile '{name}' created", type='positive')
                            # Rebuild header to update profile list
                            ui.navigate.reload()
                        elif name in state.profiles:
                            ui.notify("Profile already exists", type='warning')
                    
                    with ui.row().classes('w-full justify-end gap-2 mt-2'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')
                        ui.button('Create', on_click=do_create).props('color=green')
                dialog.open()
            
            def delete_profile():
                if len(state.profiles) <= 1:
                    ui.notify("Cannot delete the last profile", type='warning')
                    return
                deleted_name = state.profile_name
                del state.profiles[state.profile_name]
                state.profile_name = list(state.profiles.keys())[0]
                state.load_active_profile()
                ui.notify(f"Profile '{deleted_name}' deleted", type='info')
                ui.navigate.reload()
            
            ui.button(icon='add', on_click=add_profile).props('flat round dense color=green').tooltip('New profile')
            ui.button(icon='delete', on_click=delete_profile).props('flat round dense color=red').tooltip('Delete profile')
            
            # Source and output paths
            with ui.row().classes('flex-grow gap-2'):
                ui.input('Input Base').bind_value(state, 'input_base') \
                    .classes('flex-grow').props('dark dense outlined')
                ui.input('Output Base').bind_value(state, 'output_base') \
                    .classes('flex-grow').props('dark dense outlined')
                ui.input('Folder (optional)').bind_value(state, 'folder_name') \
                    .classes('flex-grow').props('dark dense outlined')
            
            ui.button(icon='save', on_click=state.save_current_profile) \
                .props('flat round color=white')
            ui.button('LOAD', on_click=load_images) \
                .props('color=green flat').classes('font-bold border border-green-700')
            
            # View settings menu
            with ui.button(icon='tune', color='white').props('flat round'):
                with ui.menu().classes('bg-gray-800 text-white p-4'):
                    ui.label('VIEW SETTINGS').classes('text-xs font-bold mb-2')

                    ui.label('Grid Columns:')
                    ui.slider(
                        min=2, max=8, step=1,
                        value=state.grid_cols,
                        on_change=lambda e: (setattr(state, 'grid_cols', e.value), refresh_ui())
                    ).props('color=green')

                    ui.label('Preview Quality:')
                    ui.slider(
                        min=10, max=100, step=10,
                        value=state.preview_quality,
                        on_change=lambda e: (setattr(state, 'preview_quality', e.value), refresh_ui())
                    ).props('color=green label-always')

                    ui.separator().classes('my-2')
                    ui.label('CAPTION SETTINGS').classes('text-xs font-bold mb-2 text-purple-400')
                    ui.button('Configure API', icon='api', on_click=open_caption_settings_dialog) \
                        .props('flat color=purple').classes('w-full')
            
            ui.switch('Dark', value=True, on_change=lambda e: ui.dark_mode().set_value(e.value)) \
                .props('color=green')

def build_sidebar():
    """Build left sidebar."""
    with ui.left_drawer(value=True).classes('bg-gray-950 p-4 border-r border-gray-800').props('width=320'):
        state.sidebar_container = ui.column().classes('w-full')

def build_main_content():
    """Build main content area with tabs."""
    with ui.column().classes('w-full bg-gray-900 min-h-screen text-white'):
        # Mode tabs
        with ui.tabs().classes('w-full bg-gray-800') as tabs:
            gallery_tab = ui.tab('Gallery', icon='grid_view')
            pairing_tab = ui.tab('Pairing', icon='compare')
        
        with ui.tab_panels(tabs, value=gallery_tab).classes('w-full'):
            # Gallery Mode Panel
            with ui.tab_panel(gallery_tab).classes('p-6'):
                state.pagination_container = ui.column().classes('w-full items-center mb-4')
                state.grid_container = ui.column().classes('w-full')
                
                # Footer with batch controls
                ui.separator().classes('my-10 bg-gray-800')
                
                with ui.row().classes('w-full justify-around p-6 bg-gray-950 rounded-xl border border-gray-800'):
                    # Tagged files mode
                    with ui.column():
                        ui.label('TAGGED FILES:').classes('text-gray-500 text-xs font-bold')
                        ui.radio(['Copy', 'Move'], value=state.batch_mode) \
                            .bind_value(state, 'batch_mode') \
                            .props('inline dark color=green')

                    # Untagged files mode
                    with ui.column():
                        ui.label('UNTAGGED FILES:').classes('text-gray-500 text-xs font-bold')
                        ui.radio(['Keep', 'Move to Unused', 'Delete'], value=state.cleanup_mode) \
                            .bind_value(state, 'cleanup_mode') \
                            .props('inline dark color=green')

                    # Caption options
                    with ui.column():
                        ui.label('CAPTIONING:').classes('text-gray-500 text-xs font-bold')
                        ui.checkbox('Caption on Apply').bind_value(state, 'caption_on_apply') \
                            .props('color=purple dark')
                        ui.button('CAPTION CATEGORY', icon='auto_awesome', on_click=action_caption_category) \
                            .props('outline color=purple')

                    # Action buttons
                    with ui.row().classes('items-center gap-6'):
                        ui.button('APPLY PAGE', on_click=action_apply_page) \
                            .props('outline color=white lg')

                        with ui.column().classes('items-center'):
                            ui.button('APPLY GLOBAL', on_click=action_apply_global) \
                                .props('lg color=red-900')
                            ui.label('(Process All)').classes('text-xs text-gray-500')
            
            # Pairing Mode Panel
            with ui.tab_panel(pairing_tab).classes('p-6'):
                # Adjacent folder input
                with ui.row().classes('w-full items-center gap-4 mb-4'):
                    ui.label("Adjacent Folder:").classes('text-gray-400')
                    ui.input(placeholder='/path/to/adjacent/folder') \
                        .bind_value(state, 'pair_adjacent_folder') \
                        .classes('flex-grow').props('dark dense outlined')
                    ui.button('LOAD ADJACENT', on_click=lambda: (load_adjacent_folder(), pair_navigate(0))) \
                        .props('color=orange')
                
                # Pairing view container
                state.pairing_container = ui.column().classes('w-full')
                
                # Footer for pairing mode
                ui.separator().classes('my-10 bg-gray-800')
                
                with ui.row().classes('w-full justify-around p-6 bg-gray-950 rounded-xl border border-gray-800'):
                    with ui.column():
                        ui.label('PAIRED TAGGING:').classes('text-gray-500 text-xs font-bold')
                        ui.label('Each side has its own category and output folder').classes('text-gray-600 text-xs')
                        ui.label('Both images share the same index number').classes('text-gray-600 text-xs')
                    
                    with ui.row().classes('items-center gap-6'):
                        ui.button('APPLY GLOBAL', on_click=action_apply_global) \
                            .props('lg color=red-900')
                        ui.label('Files go to their respective output folders').classes('text-xs text-gray-500')
        
        # Tab change handler to switch modes
        def on_tab_change(e):
            if e.value == gallery_tab:
                state.current_mode = "gallery"
            else:
                state.current_mode = "pairing"
                pair_navigate(0)  # Initialize pairing view
        
        tabs.on('update:model-value', on_tab_change)

# ==========================================
# INITIALIZATION
# ==========================================

build_header()
build_sidebar()
build_main_content()

# JavaScript keyboard handler for Firefox compatibility
ui.add_body_html('''
<script>
document.addEventListener('keydown', function(e) {
    // Skip if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    
    const key = e.key.toLowerCase();
    const ctrl = e.ctrlKey || e.metaKey;
    
    // Prevent browser defaults for our shortcuts
    if (ctrl && (key === 's' || key === 'z')) {
        e.preventDefault();
    }
});
</script>
''')

# Use NiceGUI keyboard
ui.keyboard(on_key=handle_keyboard, ignore=[])
ui.dark_mode().enable()
load_images()

ui.run(title="NiceSorter", host="0.0.0.0", port=8080, reload=False)