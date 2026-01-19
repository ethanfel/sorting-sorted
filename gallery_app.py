import os
import math
import asyncio
from nicegui import ui, app, run
from fastapi import Response
from engine import SorterEngine

# ==========================================
# 1. STATE MANAGEMENT
# ==========================================
class AppState:
    def __init__(self):
        # Load Defaults from engine
        profiles = SorterEngine.load_profiles()
        p_data = profiles.get("Default", {})
        
        self.source_dir = p_data.get("tab5_source", "/storage")
        self.output_dir = p_data.get("tab5_out", "/storage")
        
        self.page = 0
        self.page_size = 24
        self.grid_cols = 4
        self.active_cat = "Default"
        self.next_index = 1
        
        # Processing Settings
        self.batch_mode = "Copy"
        self.cleanup_mode = "Keep"
        
        # Caches
        self.all_images = []
        self.staged_data = {}
        self.green_dots = set()
        self.index_map = {} # {number: source_path} for sidebar previews

state = AppState()

# ==========================================
# 2. IMAGE SERVING API
# ==========================================

@app.get('/thumbnail')
async def get_thumbnail(path: str, size: int = 400):
    if not os.path.exists(path): return Response(status_code=404)
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 70, size)
    return Response(content=img_bytes, media_type="image/webp") if img_bytes else Response(status_code=500)

@app.get('/full_res')
async def get_full_res(path: str):
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 90, None)
    return Response(content=img_bytes, media_type="image/webp")

# ==========================================
# 3. LOGIC & ACTIONS
# ==========================================

def load_images():
    if os.path.exists(state.source_dir):
        state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)
        refresh_staged_info()
        refresh_ui()
    else:
        ui.notify(f"Source not found: {state.source_dir}", type='warning')

def refresh_staged_info():
    state.staged_data = SorterEngine.get_staged_data()
    
    # 1. Green Dots (Pagination)
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
            
    # 2. Sidebar Index Map (Used numbers for current category)
    state.index_map.clear()
    # Check Staging
    for orig_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            try:
                num = int(info['name'].rsplit('_', 1)[1].split('.')[0])
                state.index_map[num] = orig_path
            except: pass
    # Check Disk
    cat_path = os.path.join(state.output_dir, state.active_cat)
    if os.path.exists(cat_path):
        for f in os.listdir(cat_path):
            if f.startswith(state.active_cat) and "_" in f:
                try:
                    num = int(f.rsplit('_', 1)[1].split('.')[0])
                    if num not in state.index_map:
                        state.index_map[num] = os.path.join(cat_path, f)
                except: pass

def get_current_batch():
    start = state.page * state.page_size
    return state.all_images[start : start + state.page_size]

def action_tag(img_path, manual_idx=None):
    idx = manual_idx if manual_idx else state.next_index
    ext = os.path.splitext(img_path)[1]
    name = f"{state.active_cat}_{idx:03d}{ext}"
    
    final_path = os.path.join(state.output_dir, state.active_cat, name)
    staged_names = {v['name'] for v in state.staged_data.values() if v['cat'] == state.active_cat}
    
    if name in staged_names or os.path.exists(final_path):
        ui.notify(f"Conflict! Using suffix for {name}", type='warning')
        name = f"{state.active_cat}_{idx:03d}_{idx}{ext}"

    SorterEngine.stage_image(img_path, state.active_cat, name)
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
    load_images()

def action_apply_page():
    batch = get_current_batch()
    SorterEngine.commit_batch(batch, state.output_dir, state.cleanup_mode, state.batch_mode)
    ui.notify(f"Page processed ({state.batch_mode})", type='positive')
    load_images()

def action_apply_global():
    ui.notify("Starting Global Apply...")
    SorterEngine.commit_global(state.output_dir, state.cleanup_mode, state.batch_mode, state.source_dir)
    load_images()
    ui.notify("Global Apply Complete!", type='positive')

# ==========================================
# 4. UI RENDERERS
# ==========================================

def open_zoom_dialog(path, title=None):
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-screen-xl p-0 gap-0 bg-black'):
        with ui.row().classes('w-full justify-between items-center p-2 bg-gray-900 text-white'):
            ui.label(title or os.path.basename(path)).classes('font-bold truncate')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        ui.image(f"/full_res?path={path}").classes('w-full h-auto object-contain')
    dialog.open()

def render_sidebar():
    sidebar_container.clear()
    with sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2 text-white')
        
        # 1. 5x5 Grid
        with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
            for i in range(1, 26):
                is_used = i in state.index_map
                color = 'green' if is_used else 'grey-9'
                
                def click_grid(num=i):
                    state.next_index = num
                    if num in state.index_map:
                        open_zoom_dialog(state.index_map[num], f"Index #{num}")
                    else:
                        ui.notify(f"Next index set to #{num}")
                    render_sidebar()

                ui.button(str(i), on_click=click_grid).props(f'color={color} size=sm flat').classes('w-full border border-gray-700')
        
        # 2. Category Select
        categories = SorterEngine.get_categories() or ["Default"]
        if state.active_cat not in categories: state.active_cat = categories[0]

        ui.select(categories, value=state.active_cat, label="Active Category", 
                  on_change=lambda e: (setattr(state, 'active_cat', e.value), refresh_staged_info(), render_sidebar())) \
                  .classes('w-full').props('dark outlined')

        # 3. Add Category
        with ui.row().classes('w-full items-center no-wrap mt-2'):
            new_cat_input = ui.input(placeholder='New...').props('dense outlined dark').classes('flex-grow')
            def add_it():
                if new_cat_input.value:
                    SorterEngine.add_category(new_cat_input.value)
                    state.active_cat = new_cat_input.value
                    refresh_staged_info(); render_sidebar()
            ui.button(icon='add', on_click=add_it).props('flat color=green')

        # 4. Danger Zone
        with ui.expansion('Danger Zone', icon='warning').classes('w-full text-red-400 mt-2'):
            ui.button('DELETE CURRENT CATEGORY', color='red', on_click=lambda: (SorterEngine.delete_category(state.active_cat), refresh_staged_info(), render_sidebar())).classes('w-full')

        ui.separator().classes('my-4 bg-gray-700')

        # 5. Index & Counter
        with ui.row().classes('w-full items-end no-wrap'):
            ui.number(label="Next #", min=1, precision=0).bind_value(state, 'next_index').classes('flex-grow').props('dark')
            ui.button('🔄', on_click=lambda: (setattr(state, 'next_index', (max(state.index_map.keys())+1 if state.index_map else 1)), render_sidebar())).props('flat color=white')

def render_gallery():
    grid_container.clear()
    batch = get_current_batch()
    thumb_size = int(1600 / state.grid_cols)
    
    with grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-3'):
            for img_path in batch:
                is_staged = img_path in state.staged_data
                with ui.card().classes('p-2 bg-gray-900 border border-gray-700 no-shadow'):
                    # Header
                    with ui.row().classes('w-full justify-between no-wrap'):
                        ui.label(os.path.basename(img_path)[:12]).classes('text-xs text-gray-400 truncate')
                        with ui.row().classes('gap-1'):
                            ui.button(icon='zoom_in', on_click=lambda p=img_path: open_zoom_dialog(p)).props('flat size=sm dense color=white')
                            ui.button(icon='delete', on_click=lambda p=img_path: action_delete(p)).props('flat size=sm dense color=red')

                    # Image
                    ui.image(f"/thumbnail?path={img_path}&size={thumb_size}").classes('w-full h-48 object-cover rounded shadow-lg').props('no-spinner')
                    
                    # Tagging Area
                    if is_staged:
                        info = state.staged_data[img_path]
                        num = info['name'].rsplit('_', 1)[1].split('.')[0]
                        ui.label(f"🏷️ {info['cat']} (#{num})").classes('text-center text-green-400 text-xs py-1 bg-green-900/30 rounded mt-2')
                        ui.button('Untag', on_click=lambda p=img_path: action_untag(p)).props('flat color=grey-5').classes('w-full')
                    else:
                        with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                            local_idx = ui.number(value=state.next_index, precision=0).props('dense dark outlined').classes('w-1/3')
                            ui.button('Tag', on_click=lambda p=img_path, i=local_idx: action_tag(p, int(i.value))).classes('w-2/3').props('color=green')

def render_pagination():
    pagination_container.clear()
    total_pages = math.ceil(len(state.all_images) / state.page_size)
    if total_pages <= 1: return
    with pagination_container:
        with ui.row().classes('items-center gap-2'):
            ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white')
            for p in range(max(0, state.page-2), min(total_pages, state.page+3)):
                dot = " 🟢" if p in state.green_dots else ""
                ui.button(f"{p+1}{dot}", on_click=lambda p=p: set_page(p)).props(f'flat color={"white" if p==state.page else "grey-6"}')
            ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat color=white')

def set_page(p):
    state.page = p; refresh_ui()

def refresh_ui():
    render_sidebar(); render_pagination(); render_gallery()

def handle_key(e):
    if not e.action.keydown: return
    if e.key.arrow_left: set_page(state.page - 1)
    if e.key.arrow_right: set_page(state.page + 1)

# ==========================================
# 5. MAIN LAYOUT
# ==========================================

# Header
with ui.header().classes('items-center bg-slate-900 text-white border-b border-gray-700').style('height: 70px'):
    with ui.row().classes('w-full items-center gap-4 no-wrap px-4'):
        ui.label('🖼️ NiceSorter').classes('text-xl font-bold shrink-0 text-green-400')
        with ui.row().classes('flex-grow gap-2'):
            ui.input('Source').bind_value(state, 'source_dir').classes('flex-grow').props('dark dense outlined')
            ui.input('Output').bind_value(state, 'output_dir').classes('flex-grow').props('dark dense outlined')
        ui.button('LOAD', on_click=load_images).props('color=white flat').classes('font-bold')
        ui.switch('Dark', value=True, on_change=lambda e: ui.dark_mode().set_value(e.value)).props('color=green')

# Sidebar
with ui.left_drawer(value=True).classes('bg-gray-950 p-4 border-r border-gray-800').props('width=320'):
    sidebar_container = ui.column().classes('w-full')

# Content
with ui.column().classes('w-full p-6 bg-gray-900 min-h-screen text-white'):
    pagination_container = ui.column().classes('w-full items-center mb-6')
    grid_container = ui.column().classes('w-full')
    
    # Batch Settings
    ui.separator().classes('my-10 bg-gray-800')
    with ui.row().classes('w-full justify-around p-6 bg-gray-950 rounded-xl border border-gray-800'):
        with ui.column():
            ui.label('Tagged:').classes('text-gray-500 text-xs uppercase')
            ui.radio(['Copy', 'Move'], value=state.batch_mode).bind_value(state, 'batch_mode').props('inline dark color=green')
        with ui.column():
            ui.label('Untagged:').classes('text-gray-500 text-xs uppercase')
            ui.radio(['Keep', 'Move to Unused', 'Delete'], value=state.cleanup_mode).bind_value(state, 'cleanup_mode').props('inline dark color=green')
        with ui.row().classes('items-center gap-4'):
            ui.button('APPLY PAGE', on_click=action_apply_page).props('outline color=white lg')
            ui.button('APPLY GLOBAL', on_click=action_apply_global).props('lg').classes('bg-red-700 font-bold')

# Setup
ui.keyboard(on_key=handle_key)
ui.dark_mode().enable()
load_images()
ui.run(title="Nice Sorter", host="0.0.0.0", port=8080, reload=False)