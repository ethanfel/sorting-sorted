import os
import math
import asyncio
import json
from nicegui import ui, app, run
from fastapi import Response
from engine import SorterEngine

# ==========================================
# 1. STATE MANAGEMENT
# ==========================================
class AppState:
    def __init__(self):
        # Profile Data
        self.profiles = SorterEngine.load_profiles()
        self.profile_name = "Default"
        if not self.profiles:
            self.profiles = {"Default": {"tab5_source": "/storage", "tab5_out": "/storage"}}
        
        # Load initial paths
        self.load_active_profile()
        
        # Navigation State
        self.page = 0
        self.page_size = 24
        self.grid_cols = 4
        
        # Tagging State
        self.active_cat = "Default"
        self.next_index = 1
        
        # Batch Settings
        self.batch_mode = "Copy"
        self.cleanup_mode = "Keep"
        
        # Data Caches
        self.all_images = []
        self.staged_data = {}
        self.green_dots = set()
        self.index_map = {} # {number: path_to_image}

    def load_active_profile(self):
        p_data = self.profiles.get(self.profile_name, {})
        self.source_dir = p_data.get("tab5_source", "/storage")
        self.output_dir = p_data.get("tab5_out", "/storage")

    def save_current_profile(self):
        # Update local dict
        if self.profile_name not in self.profiles:
            self.profiles[self.profile_name] = {}
        self.profiles[self.profile_name]["tab5_source"] = self.source_dir
        self.profiles[self.profile_name]["tab5_out"] = self.output_dir
        
        # Persist to disk via Engine
        SorterEngine.save_tab_paths(self.profile_name, t5_s=self.source_dir, t5_o=self.output_dir)
        ui.notify(f"Profile '{self.profile_name}' Saved!", type='positive')

state = AppState()

# ==========================================
# 2. IMAGE SERVING API
# ==========================================

@app.get('/thumbnail')
async def get_thumbnail(path: str, size: int = 400):
    if not os.path.exists(path): return Response(status_code=404)
    # CPU bound to prevent UI freeze
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 70, size)
    return Response(content=img_bytes, media_type="image/webp") if img_bytes else Response(status_code=500)

@app.get('/full_res')
async def get_full_res(path: str):
    if not os.path.exists(path): return Response(status_code=404)
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 90, None)
    return Response(content=img_bytes, media_type="image/webp")

# ==========================================
# 3. CORE LOGIC
# ==========================================

def load_images():
    if os.path.exists(state.source_dir):
        state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)
        # Reset page if out of bounds
        total_pages = math.ceil(len(state.all_images) / state.page_size)
        if state.page >= total_pages: state.page = 0
        
        refresh_staged_info()
        refresh_ui()
    else:
        ui.notify(f"Source not found: {state.source_dir}", type='warning')

def refresh_staged_info():
    state.staged_data = SorterEngine.get_staged_data()
    
    # 1. Update Green Dots (Pagination)
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
            
    # 2. Update Sidebar Index Map
    state.index_map.clear()
    
    # A. Check Staging (Memory)
    for orig_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            try:
                # Parse "CatName_005.jpg"
                num = int(info['name'].rsplit('_', 1)[1].split('.')[0])
                state.index_map[num] = orig_path # Point to original for preview
            except: pass
            
    # B. Check Disk (Output Folder)
    cat_path = os.path.join(state.output_dir, state.active_cat)
    if os.path.exists(cat_path):
        for f in os.listdir(cat_path):
            if f.startswith(state.active_cat) and "_" in f:
                try:
                    num = int(f.rsplit('_', 1)[1].split('.')[0])
                    # Staging takes precedence, otherwise add disk file
                    if num not in state.index_map:
                        state.index_map[num] = os.path.join(cat_path, f)
                except: pass

def get_current_batch():
    if not state.all_images: return []
    start = state.page * state.page_size
    return state.all_images[start : start + state.page_size]

# --- ACTIONS ---

def action_tag(img_path, manual_idx=None):
    idx = manual_idx if manual_idx else state.next_index
    ext = os.path.splitext(img_path)[1]
    name = f"{state.active_cat}_{idx:03d}{ext}"
    
    # Conflict Check
    final_path = os.path.join(state.output_dir, state.active_cat, name)
    staged_names = {v['name'] for v in state.staged_data.values() if v['cat'] == state.active_cat}
    
    if name in staged_names or os.path.exists(final_path):
        ui.notify(f"Conflict: {name} exists. Using suffix.", type='warning')
        name = f"{state.active_cat}_{idx:03d}_{len(staged_names)+1}{ext}"

    SorterEngine.stage_image(img_path, state.active_cat, name)
    
    # Auto-increment if we used the global counter
    if manual_idx is None or manual_idx == state.next_index:
        state.next_index = idx + 1
    
    refresh_staged_info()
    refresh_ui()

def action_untag(img_path):
    SorterEngine.clear_staged_item(img_path)
    refresh_staged_info()
    refresh_ui()

def action_delete(img_path):
    SorterEngine.delete_to_trash(img_path)
    load_images() # Rescan needed

def action_apply_page():
    batch = get_current_batch()
    if not batch: return
    SorterEngine.commit_batch(batch, state.output_dir, state.cleanup_mode, state.batch_mode)
    ui.notify(f"Page Processed ({state.batch_mode})", type='positive')
    load_images()

def action_apply_global():
    ui.notify("Starting Global Apply... This may take a moment.")
    # Run in background to keep UI responsive
    run.io_bound(SorterEngine.commit_global, state.output_dir, state.cleanup_mode, state.batch_mode, state.source_dir)
    # We reload after a short delay or assume user will click reload
    load_images()
    ui.notify("Global Apply Complete!", type='positive')


# ==========================================
# 4. UI COMPONENTS
# ==========================================

def open_zoom_dialog(path, title=None):
    """Shows full screen image modal"""
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-screen-xl p-0 gap-0 bg-black'):
        with ui.row().classes('w-full justify-between items-center p-2 bg-gray-900 text-white'):
            ui.label(title or os.path.basename(path)).classes('font-bold truncate px-2')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        
        # Full Res Image
        ui.image(f"/full_res?path={path}").classes('w-full h-auto object-contain max-h-[85vh]')
    dialog.open()

def render_sidebar():
    sidebar_container.clear()
    with sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2 text-white')
        
        # --- FEATURE 4: SIDEBAR PREVIEW GRID ---
        with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
            for i in range(1, 26):
                is_used = i in state.index_map
                color = 'green' if is_used else 'grey-9'
                
                # Closure to capture 'i' and 'is_used'
                def click_grid(num=i, used=is_used):
                    state.next_index = num
                    if used:
                        # Feature 4: Open Preview
                        open_zoom_dialog(state.index_map[num], f"{state.active_cat} #{num}")
                    render_sidebar() # Update Next # input

                ui.button(str(i), on_click=click_grid).props(f'color={color} size=sm flat').classes('w-full border border-gray-800')
        
        # --- CATEGORY SELECTOR ---
        categories = SorterEngine.get_categories() or ["Default"]
        if state.active_cat not in categories: state.active_cat = categories[0]

        def change_cat(e):
            state.active_cat = e.value
            refresh_staged_info()
            render_sidebar()

        ui.select(categories, value=state.active_cat, label="Active Category", on_change=change_cat) \
                  .classes('w-full').props('dark outlined')

        # --- ADD CATEGORY ---
        with ui.row().classes('w-full items-center no-wrap mt-2'):
            new_cat_input = ui.input(placeholder='New...').props('dense outlined dark').classes('flex-grow')
            def add_it():
                if new_cat_input.value:
                    SorterEngine.add_category(new_cat_input.value)
                    state.active_cat = new_cat_input.value
                    refresh_staged_info(); render_sidebar()
            ui.button(icon='add', on_click=add_it).props('flat color=green')

        # --- DELETE CATEGORY ---
        with ui.expansion('Danger Zone', icon='warning').classes('w-full text-red-400 mt-2'):
            ui.button('DELETE CAT', color='red', on_click=lambda: (SorterEngine.delete_category(state.active_cat), refresh_staged_info(), render_sidebar())).classes('w-full')

        ui.separator().classes('my-4 bg-gray-700')

        # --- INDEX COUNTER ---
        with ui.row().classes('w-full items-end no-wrap'):
            ui.number(label="Next Index", min=1, precision=0).bind_value(state, 'next_index').classes('flex-grow').props('dark outlined')
            def auto_detect():
                used = state.index_map.keys()
                state.next_index = max(used) + 1 if used else 1
            ui.button('🔄', on_click=lambda: (auto_detect(), render_sidebar())).props('flat color=white')

def render_gallery():
    grid_container.clear()
    batch = get_current_batch()
    # Dynamic thumbnail sizing
    thumb_size = int(1600 / state.grid_cols)
    
    with grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-3'):
            for img_path in batch:
                is_staged = img_path in state.staged_data
                
                with ui.card().classes('p-2 bg-gray-900 border border-gray-700 no-shadow'):
                    # Header
                    with ui.row().classes('w-full justify-between no-wrap mb-1'):
                        ui.label(os.path.basename(img_path)[:15]).classes('text-xs text-gray-400 truncate')
                        with ui.row().classes('gap-0'):
                            ui.button(icon='zoom_in', on_click=lambda p=img_path: open_zoom_dialog(p)).props('flat size=sm dense color=white')
                            ui.button(icon='delete', on_click=lambda p=img_path: action_delete(p)).props('flat size=sm dense color=red')

                    # Image
                    ui.image(f"/thumbnail?path={img_path}&size={thumb_size}").classes('w-full h-48 object-cover rounded').props('no-spinner')
                    
                    # Actions
                    if is_staged:
                        info = state.staged_data[img_path]
                        # Extract number for "Untag (#5)"
                        try:
                            num = info['name'].rsplit('_', 1)[1].split('.')[0]
                            label = f"Untag (#{num})"
                        except:
                            label = "Untag"
                            
                        ui.label(f"🏷️ {info['cat']}").classes('text-center text-green-400 text-xs py-1 w-full')
                        ui.button(label, on_click=lambda p=img_path: action_untag(p)).props('flat color=grey-5 dense').classes('w-full')
                    else:
                        with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                            # Local index input
                            local_idx = ui.number(value=state.next_index, precision=0).props('dense dark outlined').classes('w-1/3')
                            ui.button('Tag', on_click=lambda p=img_path, i=local_idx: action_tag(p, int(i.value))).classes('w-2/3').props('color=green dense')

def render_pagination():
    pagination_container.clear()
    if not state.all_images: return
    
    total_pages = math.ceil(len(state.all_images) / state.page_size)
    if total_pages <= 1: return

    with pagination_container:
        # --- 1. SLIDER (Restored) ---
        def on_slide(e):
            state.page = int(e.value)
            refresh_ui()
            
        ui.slider(min=0, max=total_pages-1, value=state.page, on_change=on_slide).classes('w-1/2 mb-2').props('color=green')

        # --- 2. CAROUSEL BUTTONS ---
        with ui.row().classes('items-center gap-2'):
            ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white').bind_visibility_from(state, 'page', backward=lambda x: x > 0)
            
            # Show window of 5 pages
            start = max(0, state.page - 2)
            end = min(total_pages, state.page + 3)
            
            for p in range(start, end):
                dot = " 🟢" if p in state.green_dots else ""
                color = "white" if p == state.page else "grey-6"
                ui.button(f"{p+1}{dot}", on_click=lambda p=p: set_page(p)).props(f'flat color={color}')
                
            ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat color=white').bind_visibility_from(state, 'page', backward=lambda x: x < total_pages - 1)

def set_page(p):
    state.page = p
    refresh_ui()

def refresh_ui():
    render_sidebar()
    render_pagination()
    render_gallery()

def handle_key(e):
    if not e.action.keydown: return
    if e.key.arrow_left: set_page(max(0, state.page - 1))
    if e.key.arrow_right: 
        total = math.ceil(len(state.all_images) / state.page_size)
        set_page(min(total - 1, state.page + 1))

# ==========================================
# 5. MAIN LAYOUT
# ==========================================

# HEADER
with ui.header().classes('items-center bg-slate-900 text-white border-b border-gray-700').style('height: 70px'):
    with ui.row().classes('w-full items-center gap-4 no-wrap px-4'):
        ui.label('🖼️ NiceSorter').classes('text-xl font-bold shrink-0 text-green-400')
        
        # --- FEATURE 5: PROFILE MANAGER ---
        # Profile Select
        profile_names = list(state.profiles.keys())
        def change_profile(e):
            state.profile_name = e.value
            state.load_active_profile()
            load_images()
        
        ui.select(profile_names, value=state.profile_name, on_change=change_profile).props('dark dense options-dense borderless').classes('w-32')
        
        # Paths (Flex Grow)
        with ui.row().classes('flex-grow gap-2'):
            ui.input('Source').bind_value(state, 'source_dir').classes('flex-grow').props('dark dense outlined')
            ui.input('Output').bind_value(state, 'output_dir').classes('flex-grow').props('dark dense outlined')
            
        # Save Profile Button
        ui.button(icon='save', on_click=state.save_current_profile).props('flat round color=white').tooltip('Save Paths to Profile')
        
        # Load Button
        ui.button('LOAD FILES', on_click=load_images).props('color=green flat').classes('font-bold border border-green-700')
        
        # Dark Toggle
        ui.switch('Dark', value=True, on_change=lambda e: ui.dark_mode().set_value(e.value)).props('color=green')

# SIDEBAR
with ui.left_drawer(value=True).classes('bg-gray-950 p-4 border-r border-gray-800').props('width=320'):
    sidebar_container = ui.column().classes('w-full')

# CONTENT
with ui.column().classes('w-full p-6 bg-gray-900 min-h-screen text-white'):
    pagination_container = ui.column().classes('w-full items-center mb-4')
    grid_container = ui.column().classes('w-full')
    
    # --- FOOTER: BATCH SETTINGS & GLOBAL APPLY ---
    ui.separator().classes('my-10 bg-gray-800')
    with ui.row().classes('w-full justify-around p-6 bg-gray-950 rounded-xl border border-gray-800'):
        # Settings
        with ui.column():
            ui.label('TAGGED FILES:').classes('text-gray-500 text-xs font-bold')
            ui.radio(['Copy', 'Move'], value=state.batch_mode).bind_value(state, 'batch_mode').props('inline dark color=green')
        
        with ui.column():
            ui.label('UNTAGGED FILES:').classes('text-gray-500 text-xs font-bold')
            ui.radio(['Keep', 'Move to Unused', 'Delete'], value=state.cleanup_mode).bind_value(state, 'cleanup_mode').props('inline dark color=green')
            
        # Action Buttons
        with ui.row().classes('items-center gap-6'):
            ui.button('APPLY PAGE', on_click=action_apply_page).props('outline color=white lg')
            
            # Feature 3: Global Apply
            with ui.column().classes('items-center'):
                ui.button('APPLY GLOBAL', on_click=action_apply_global).props('lg color=red-900')
                ui.label('(Process All)').classes('text-xs text-gray-500')

# STARTUP
ui.keyboard(on_key=handle_key)
ui.dark_mode().enable()
load_images()
ui.run(title="Nice Sorter", host="0.0.0.0", port=8080, reload=False)