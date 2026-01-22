import os
import mathgg
import asyncio
from typing import Optional, List, Dict, Set
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
        
        # Batch Settings
        self.batch_mode = "Copy"
        self.cleanup_mode = "Keep"
        
        # Data Caches
        self.all_images: List[str] = []
        self.staged_data: Dict = {}
        self.green_dots: Set[int] = set()
        self.index_map: Dict[int, str] = {}
        
        # UI Containers (populated later)
        self.sidebar_container = None
        self.grid_container = None
        self.pagination_container = None

    def load_active_profile(self):
        """Load paths from active profile."""
        p_data = self.profiles.get(self.profile_name, {})
        self.input_base = p_data.get("tab5_source", "/storage")
        self.output_base = p_data.get("tab5_out", "/storage")
        self.folder_name = ""

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
        self.profiles[self.profile_name]["tab5_source"] = self.input_base
        self.profiles[self.profile_name]["tab5_out"] = self.output_base
        SorterEngine.save_tab_paths(self.profile_name, t5_s=self.input_base, t5_o=self.output_base)
        ui.notify(f"Profile '{self.profile_name}' saved!", type='positive')

    def get_categories(self) -> List[str]:
        """Get list of categories, ensuring active_cat exists."""
        cats = SorterEngine.get_categories(self.profile_name) or ["control"]
        if self.active_cat not in cats:
            self.active_cat = cats[0]
        return cats

    @property
    def total_pages(self) -> int:
        """Calculate total pages."""
        return math.ceil(len(self.all_images) / self.page_size) if self.all_images else 0

    def get_current_batch(self) -> List[str]:
        """Get images for current page."""
        if not self.all_images:
            return []
        start = self.page * self.page_size
        return self.all_images[start : start + self.page_size]

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
    
    # Clear staging area when loading a new folder
    SorterEngine.clear_staging_area()
    
    state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)
    
    # Restore previously saved tags for this folder
    restored = SorterEngine.restore_folder_tags(state.source_dir, state.all_images)
    if restored > 0:
        ui.notify(f"Restored {restored} tags from previous session", type='info')
    
    # Reset page if out of bounds
    if state.page >= state.total_pages:
        state.page = 0
    
    refresh_staged_info()
    refresh_ui()

def refresh_staged_info():
    """Update staged data and index maps."""
    state.staged_data = SorterEngine.get_staged_data()
    
    # Update green dots (pages with staged images)
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
    
    # Build index map for active category
    state.index_map.clear()
    
    # Add staged images
    for orig_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            idx = _extract_index(info['name'])
            if idx is not None:
                state.index_map[idx] = orig_path
    
    # Add committed images from disk
    cat_path = os.path.join(state.output_dir, state.active_cat)
    if os.path.exists(cat_path):
        for filename in os.listdir(cat_path):
            if filename.startswith(state.active_cat):
                idx = _extract_index(filename)
                if idx is not None and idx not in state.index_map:
                    state.index_map[idx] = os.path.join(cat_path, filename)

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
    
    SorterEngine.stage_image(img_path, state.active_cat, name)
    
    # Only auto-increment if we used the default next_index (not manual)
    if manual_idx is None:
        state.next_index = idx + 1
    
    refresh_staged_info()
    refresh_ui()

def action_untag(img_path: str):
    """Remove staging from an image."""
    SorterEngine.clear_staged_item(img_path)
    refresh_staged_info()
    refresh_ui()

def action_delete(img_path: str):
    """Delete image to trash."""
    SorterEngine.delete_to_trash(img_path)
    load_images()

def action_apply_page():
    """Apply staged changes for current page only."""
    batch = state.get_current_batch()
    if not batch:
        ui.notify("No images on current page", type='warning')
        return
    
    SorterEngine.commit_batch(batch, state.output_dir, state.cleanup_mode, state.batch_mode)
    ui.notify(f"Page processed ({state.batch_mode})", type='positive')
    load_images()

async def action_apply_global():
    """Apply all staged changes globally."""
    ui.notify("Starting global apply... This may take a while.", type='info')
    await run.io_bound(
        SorterEngine.commit_global,
        state.output_dir,
        state.cleanup_mode,
        state.batch_mode,
        state.source_dir
    )
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

def render_sidebar():
    """Render category management sidebar."""
    state.sidebar_container.clear()
    
    with state.sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2 text-white')
        
        # Number grid (1-25)
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
        
        # Category selector
        categories = state.get_categories()
        
        def on_category_change(e):
            state.active_cat = e.value
            refresh_staged_info()
            render_sidebar()
        
        ui.select(
            categories,
            value=state.active_cat,
            label="Active Category",
            on_change=on_category_change
        ).classes('w-full').props('dark outlined')
        
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

def render_gallery():
    """Render image gallery grid."""
    state.grid_container.clear()
    batch = state.get_current_batch()
    
    with state.grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-3'):
            for img_path in batch:
                render_image_card(img_path)

def render_image_card(img_path: str):
    """Render individual image card."""
    is_staged = img_path in state.staged_data
    thumb_size = 800
    
    with ui.card().classes('p-2 bg-gray-900 border border-gray-700 no-shadow'):
        # Header with filename and actions
        with ui.row().classes('w-full justify-between no-wrap mb-1'):
            ui.label(os.path.basename(img_path)[:15]).classes('text-xs text-gray-400 truncate')
            with ui.row().classes('gap-0'):
                ui.button(
                    icon='zoom_in',
                    on_click=lambda p=img_path: open_zoom_dialog(p)
                ).props('flat size=sm dense color=white')
                ui.button(
                    icon='delete',
                    on_click=lambda p=img_path: action_delete(p)
                ).props('flat size=sm dense color=red')
        
        # Thumbnail
        ui.image(f"/thumbnail?path={img_path}&size={thumb_size}&q={state.preview_quality}") \
            .classes('w-full h-64 bg-black rounded') \
            .props('fit=contain no-spinner')
        
        # Tagging UI
        if is_staged:
            info = state.staged_data[img_path]
            idx = _extract_index(info['name'])
            idx_str = str(idx) if idx else "?"
            ui.label(f"🏷️ {info['cat']}").classes('text-center text-green-400 text-xs py-1 w-full')
            ui.button(
                f"Untag (#{idx_str})",
                on_click=lambda p=img_path: action_untag(p)
            ).props('flat color=grey-5 dense').classes('w-full')
        else:
            with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                local_idx = ui.number(value=state.next_index, precision=0) \
                    .props('dense dark outlined').classes('w-1/3')
                ui.button(
                    'Tag',
                    on_click=lambda p=img_path, i=local_idx: action_tag(p, int(i.value))
                ).classes('w-2/3').props('color=green dense')

def render_pagination():
    """Render pagination controls."""
    state.pagination_container.clear()
    
    if state.total_pages <= 1:
        return
    
    with state.pagination_container:
        # Page slider
        ui.slider(
            min=0,
            max=state.total_pages - 1,
            value=state.page,
            on_change=lambda e: set_page(int(e.value))
        ).classes('w-1/2 mb-2').props('color=green')
        
        # Page buttons
        with ui.row().classes('items-center gap-2'):
            # Previous button
            if state.page > 0:
                ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white')
            
            # Page numbers (show current ±2)
            start = max(0, state.page - 2)
            end = min(state.total_pages, state.page + 3)
            
            for p in range(start, end):
                dot = " 🟢" if p in state.green_dots else ""
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

def handle_keyboard(e):
    """Handle keyboard navigation."""
    if not e.action.keydown:
        return
    
    if e.key.arrow_left and state.page > 0:
        set_page(state.page - 1)
    elif e.key.arrow_right and state.page < state.total_pages - 1:
        set_page(state.page + 1)

# ==========================================
# MAIN LAYOUT
# ==========================================

def build_header():
    """Build application header."""
    with ui.header().classes('items-center bg-slate-900 text-white border-b border-gray-700').style('height: 70px'):
        with ui.row().classes('w-full items-center gap-4 no-wrap px-4'):
            ui.label('🖼️ NiceSorter').classes('text-xl font-bold shrink-0 text-green-400')
            
            # Profile selector with add/delete
            profile_select = ui.select(
                list(state.profiles.keys()), 
                value=state.profile_name,
                on_change=lambda e: (
                    setattr(state, 'profile_name', e.value),
                    state.load_active_profile(),
                    load_images()
                )
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
            
            ui.switch('Dark', value=True, on_change=lambda e: ui.dark_mode().set_value(e.value)) \
                .props('color=green')

def build_sidebar():
    """Build left sidebar."""
    with ui.left_drawer(value=True).classes('bg-gray-950 p-4 border-r border-gray-800').props('width=320'):
        state.sidebar_container = ui.column().classes('w-full')

def build_main_content():
    """Build main content area."""
    with ui.column().classes('w-full p-6 bg-gray-900 min-h-screen text-white'):
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
            
            # Action buttons
            with ui.row().classes('items-center gap-6'):
                ui.button('APPLY PAGE', on_click=action_apply_page) \
                    .props('outline color=white lg')
                
                with ui.column().classes('items-center'):
                    ui.button('APPLY GLOBAL', on_click=action_apply_global) \
                        .props('lg color=red-900')
                    ui.label('(Process All)').classes('text-xs text-gray-500')

# ==========================================
# INITIALIZATION
# ==========================================

build_header()
build_sidebar()
build_main_content()

ui.keyboard(on_key=handle_keyboard)
ui.dark_mode().enable()
load_images()

ui.run(title="NiceSorter", host="0.0.0.0", port=8080, reload=False)