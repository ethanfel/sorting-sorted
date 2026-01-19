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
    def __init__(self, profile_name="Default"):
        self.profile_name = profile_name
        profiles = SorterEngine.load_profiles()
        p_data = profiles.get(profile_name, {})
        
        self.source_dir = p_data.get("tab5_source", "/storage")
        self.output_dir = p_data.get("tab5_out", "/storage")
        
        self.page = 0
        self.page_size = 24
        self.grid_cols = 4
        self.active_cat = "Default"
        self.next_index = 1
        
        self.batch_mode = "Copy"
        self.cleanup_mode = "Keep"
        
        self.all_images = []
        self.staged_data = {}
        self.green_dots = set()
        self.index_map = {} # {number: path} for previews

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
    img_bytes = await run.cpu_bound(SorterEngine.compress_for_web, path, 95, None)
    return Response(content=img_bytes, media_type="image/webp")

# ==========================================
# 3. LOGIC & ACTIONS
# ==========================================

def save_profile_settings():
    """Feature 5: Saves current paths to profiles.json"""
    SorterEngine.save_tab_paths(state.profile_name, t5_s=state.source_dir, t5_o=state.output_dir)
    ui.notify("Profile Saved!", type='positive')

def load_images():
    if os.path.exists(state.source_dir):
        state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)
        refresh_staged_info()
        refresh_ui()
    else:
        ui.notify(f"Source not found: {state.source_dir}", type='warning')

def refresh_staged_info():
    state.staged_data = SorterEngine.get_staged_data()
    
    # Calculate Pagination Dots
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
            
    # Calculate Sidebar Index Map
    state.index_map.clear()
    for orig_path, info in state.staged_data.items():
        if info['cat'] == state.active_cat:
            try:
                num = int(info['name'].rsplit('_', 1)[1].split('.')[0])
                state.index_map[num] = orig_path
            except: pass
            
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
    
    if os.path.exists(os.path.join(state.output_dir, state.active_cat, name)):
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

# ==========================================
# 4. UI COMPONENTS
# ==========================================

def open_zoom_dialog(path, title=None):
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-screen-xl p-0 gap-0 bg-black overflow-hidden'):
        with ui.row().classes('w-full justify-between items-center p-3 bg-gray-900 text-white'):
            ui.label(title or os.path.basename(path)).classes('font-bold text-lg')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense color=white')
        ui.image(f"/full_res?path={path}").classes('w-full h-auto max-h-[85vh] object-contain')
    dialog.open()

def render_sidebar():
    sidebar_container.clear()
    with sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2 text-white')
        
        # Feature 4: Grid Previews
        with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
            for i in range(1, 26):
                is_used = i in state.index_map
                color = 'green' if is_used else 'grey-9'
                
                def click_grid(num=i):
                    state.next_index = num
                    if num in state.index_map:
                        # Opens high-res preview of what's already tagged
                        open_zoom_dialog(state.index_map[num], f"Preview Index #{num}")
                    render_sidebar()

                ui.button(str(i), on_click=click_grid).props(f'color={color} size=sm flat').classes('w-full border border-gray-800')
        
        cats = SorterEngine.get_categories() or ["Default"]
        ui.select(cats, value=state.active_cat, on_change=lambda e: (setattr(state, 'active_cat', e.value), refresh_staged_info(), render_sidebar())) \
                  .classes('w-full').props('dark outlined label="Active Category"')

        with ui.row().classes('w-full items-center no-wrap mt-2'):
            new_cat = ui.input(placeholder='Add...').props('dense outlined dark').classes('flex-grow')
            ui.button(icon='add', on_click=lambda: (SorterEngine.add_category(new_cat.value), render_sidebar())).props('flat color=green')

        with ui.expansion('Danger Zone', icon='warning').classes('w-full text-red-400'):
            ui.button('DELETE CAT', color='red', on_click=lambda: (SorterEngine.delete_category(state.active_cat), render_sidebar())).classes('w-full')

        ui.separator().classes('my-4 bg-gray-800')
        with ui.row().classes('w-full items-center no-wrap'):
            ui.number(label="Next #").bind_value(state, 'next_index').classes('flex-grow').props('dark dense')
            ui.button('🔄', on_click=lambda: (setattr(state, 'next_index', (max(state.index_map.keys())+1 if state.index_map else 1)), render_sidebar())).props('flat color=white')

def render_gallery():
    grid_container.clear()
    batch = get_current_batch()
    thumb_size = int(1600 / state.grid_cols)
    
    with grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-4'):
            for img_path in batch:
                is_staged = img_path in state.staged_data
                with ui.card().classes('p-2 bg-slate-900 border border-slate-700 no-shadow'):
                    with ui.row().classes('w-full justify-between items-center no-wrap mb-1'):
                        ui.label(os.path.basename(img_path)[:15]).classes('text-xs text-slate-400 truncate')
                        with ui.row().classes('gap-0'):
                            ui.button(icon='zoom_in', on_click=lambda p=img_path: open_zoom_dialog(p)).props('flat size=sm color=white')
                            ui.button(icon='delete', on_click=lambda p=img_path: action_delete(p)).props('flat size=sm color=red')

                    ui.image(f"/thumbnail?path={img_path}&size={thumb_size}").classes('w-full h-56 object-cover rounded shadow-md').props('no-spinner')
                    
                    if is_staged:
                        info = state.staged_data[img_path]
                        ui.label(f"🏷️ {info['name']}").classes('text-center text-green-400 text-xs py-1 mt-2 bg-green-950/40 rounded')
                        ui.button('Untag', on_click=lambda p=img_path: action_untag(p)).props('flat color=grey-4 w-full')
                    else:
                        with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                            l_idx = ui.number(value=state.next_index, precision=0).props('dense dark outlined').classes('w-1/3')
                            ui.button('Tag', on_click=lambda p=img_path, i=l_idx: action_tag(p, int(i.value))).classes('flex-grow').props('color=green-7')

def render_pagination():
    pagination_container.clear()
    total_pages = math.ceil(len(state.all_images) / state.page_size)
    if total_pages <= 1: return
    
    with pagination_container:
        # Debounced Slider for rapid navigation
        ui.slider(min=0, max=total_pages-1, value=state.page, 
                  on_change=lambda e: set_page(e.value)).classes('w-96 mb-2').props('dark')
        
        with ui.row().classes('items-center gap-1'):
            ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white')
            # Responsive page window
            for p in range(max(0, state.page-2), min(total_pages, state.page+3)):
                label = f"{p+1}{' 🟢' if p in state.green_dots else ''}"
                ui.button(label, on_click=lambda p=p: set_page(p)).props(f'flat color={"green" if p==state.page else "white"}')
            ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat color=white')

def set_page(p):
    state.page = max(0, min(p, math.ceil(len(state.all_images)/state.page_size)-1))
    refresh_ui()

def refresh_ui():
    render_sidebar(); render_pagination(); render_gallery()

# ==========================================
# 5. MAIN LAYOUT
# ==========================================

with ui.header().classes('items-center bg-slate-950 text-white border-b border-slate-800 px-4').style('height: 75px'):
    with ui.row().classes('w-full items-center gap-4 no-wrap'):
        ui.label('🖼️ NiceSorter').classes('text-2xl font-black text-green-500 italic shrink-0')
        with ui.row().classes('flex-grow gap-2'):
            ui.input('Source Path').bind_value(state, 'source_dir').classes('flex-grow').props('dark dense outlined')
            ui.input('Output Path').bind_value(state, 'output_dir').classes('flex-grow').props('dark dense outlined')
        ui.button('LOAD', on_click=load_images).props('color=white flat').classes('font-bold px-4')
        ui.button(icon='save', on_click=save_profile_settings).props('flat color=white').tooltip('Save Paths to Profile')
        ui.switch(value=True, on_change=lambda e: ui.dark_mode().set_value(e.value)).props('color=green')

with ui.left_drawer(value=True).classes('bg-slate-950 p-4 border-r border-slate-900').props('width=320'):
    sidebar_container = ui.column().classes('w-full')

with ui.column().classes('w-full p-6 bg-slate-900 min-h-screen text-white'):
    pagination_container = ui.column().classes('w-full items-center mb-8')
    grid_container = ui.column().classes('w-full')
    
    # Feature 3: Global Apply Fully Integrated
    ui.separator().classes('my-12 bg-slate-800')
    with ui.row().classes('w-full justify-around p-8 bg-slate-950 rounded-2xl border border-slate-800 shadow-2xl'):
        with ui.column():
            ui.label('Tagged Action:').classes('text-slate-500 text-xs uppercase font-bold mb-2')
            ui.radio(['Copy', 'Move'], value=state.batch_mode).bind_value(state, 'batch_mode').props('inline dark color=green')
        with ui.column():
            ui.label('Cleanup Strategy:').classes('text-slate-500 text-xs uppercase font-bold mb-2')
            ui.radio(['Keep', 'Move to Unused', 'Delete'], value=state.cleanup_mode).bind_value(state, 'cleanup_mode').props('inline dark color=green')
        with ui.row().classes('items-center gap-6'):
            ui.button('APPLY PAGE', on_click=lambda: (SorterEngine.commit_batch(get_current_batch(), state.output_dir, state.cleanup_mode, state.batch_mode), load_images())).props('outline color=white lg').classes('px-8')
            ui.button('APPLY GLOBAL', on_click=lambda: (SorterEngine.commit_global(state.output_dir, state.cleanup_mode, state.batch_mode, state.source_dir), load_images())).props('lg color=red-7').classes('font-black px-12')

# Init & Hotkeys
ui.keyboard(on_key=lambda e: (set_page(state.page-1) if e.key.arrow_left and e.action.keydown else set_page(state.page+1) if e.key.arrow_right and e.action.keydown else None))
ui.dark_mode().enable()
load_images()
ui.run(title="Nice Sorter", host="0.0.0.0", port=8080, reload=False)