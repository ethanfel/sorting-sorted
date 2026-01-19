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
        self.profiles = SorterEngine.load_profiles()
        self.current_profile = "Default"
        p_data = self.profiles.get(self.current_profile, {})
        
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
        self.index_map = {} 

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
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
            
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

def save_profile_settings():
    SorterEngine.save_tab_paths(state.current_profile, t5_s=state.source_dir, t5_o=state.output_dir)
    ui.notify(f"Settings saved to profile: {state.current_profile}")

def action_tag(img_path, manual_idx=None):
    idx = manual_idx if manual_idx else state.next_index
    ext = os.path.splitext(img_path)[1]
    name = f"{state.active_cat}_{idx:03d}{ext}"
    final_path = os.path.join(state.output_dir, state.active_cat, name)
    if os.path.exists(final_path):
        name = f"{state.active_cat}_{idx:03d}_{idx}{ext}"
    SorterEngine.stage_image(img_path, state.active_cat, name)
    if manual_idx is None or manual_idx == state.next_index:
        state.next_index = idx + 1
    refresh_staged_info(); refresh_ui()

def action_untag(img_path):
    SorterEngine.clear_staged_item(img_path)
    refresh_staged_info(); refresh_ui()

# ==========================================
# 4. UI COMPONENTS
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
        with ui.grid(columns=5).classes('gap-1 mb-4 w-full'):
            for i in range(1, 26):
                is_used = i in state.index_map
                color = 'green' if is_used else 'grey-9'
                ui.button(str(i), on_click=lambda i=i: (setattr(state, 'next_index', i), (open_zoom_dialog(state.index_map[i], f"Index #{i}") if i in state.index_map else ui.notify(f"Index set to #{i}")), render_sidebar())) \
                    .props(f'color={color} size=sm flat').classes('w-full border border-gray-700')
        
        categories = SorterEngine.get_categories() or ["Default"]
        ui.select(categories, value=state.active_cat, label="Active Category", 
                  on_change=lambda e: (setattr(state, 'active_cat', e.value), refresh_staged_info(), render_sidebar())) \
                  .classes('w-full').props('dark outlined')

        with ui.expansion('Manage Categories', icon='settings').classes('w-full text-gray-400 mt-2'):
            new_cat_input = ui.input(placeholder='New...').props('dense outlined dark').classes('w-full mb-2')
            ui.button('ADD', on_click=lambda: (SorterEngine.add_category(new_cat_input.value), render_sidebar())).classes('w-full mb-4').props('color=green')
            
            rename_input = ui.input(label='Rename current to:').props('dense outlined dark').classes('w-full mb-2')
            ui.button('RENAME', on_click=lambda: (SorterEngine.rename_category(state.active_cat, rename_input.value), setattr(state, 'active_cat', rename_input.value), render_sidebar())).classes('w-full mb-4')
            
            ui.button('DELETE CURRENT', color='red', on_click=lambda: (SorterEngine.delete_category(state.active_cat), render_sidebar())).classes('w-full')

        ui.separator().classes('my-4 bg-gray-700')
        with ui.row().classes('w-full items-end no-wrap'):
            ui.number(label="Next #", min=1).bind_value(state, 'next_index').classes('flex-grow').props('dark')
            ui.button('🔄', on_click=lambda: (setattr(state, 'next_index', (max(state.index_map.keys())+1 if state.index_map else 1)), render_sidebar())).props('flat color=white')

def render_pagination():
    pagination_container.clear()
    total_pages = math.ceil(len(state.all_images) / state.page_size)
    if total_pages <= 1: return
    with pagination_container:
        ui.slider(min=0, max=total_pages-1, step=1, value=state.page, on_change=lambda e: set_page(e.value)).classes('w-64')
        with ui.row().classes('items-center gap-2'):
            ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat color=white')
            for p in range(max(0, state.page-2), min(total_pages, state.page+3)):
                dot = " 🟢" if p in state.green_dots else ""
                ui.button(f"{p+1}{dot}", on_click=lambda p=p: set_page(p)).props(f'flat color={"white" if p==state.page else "grey-6"}')
            ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat color=white')

def render_gallery():
    grid_container.clear()
    batch = state.all_images[state.page * state.page_size : (state.page+1) * state.page_size]
    thumb_size = int(1600 / state.grid_cols)
    with grid_container:
        with ui.grid(columns=state.grid_cols).classes('w-full gap-3'):
            for img_path in batch:
                is_staged = img_path in state.staged_data
                with ui.card().classes('p-2 bg-gray-900 border border-gray-700 no-shadow'):
                    with ui.row().classes('w-full justify-between no-wrap'):
                        ui.label(os.path.basename(img_path)[:12]).classes('text-xs text-gray-400 truncate')
                        with ui.row().classes('gap-1'):
                            ui.button(icon='zoom_in', on_click=lambda p=img_path: open_zoom_dialog(p)).props('flat size=sm dense color=white')
                            ui.button(icon='delete', on_click=lambda p=img_path: SorterEngine.delete_to_trash(p) or load_images()).props('flat size=sm dense color=red')
                    ui.image(f"/thumbnail?path={img_path}&size={thumb_size}").classes('w-full h-48 object-cover rounded shadow-lg')
                    if is_staged:
                        info = state.staged_data[img_path]
                        ui.label(f"🏷️ {info['cat']}").classes('text-center text-green-400 text-xs py-1 bg-green-900/30 rounded mt-2')
                        ui.button('Untag', on_click=lambda p=img_path: action_untag(p)).props('flat color=grey-5').classes('w-full')
                    else:
                        with ui.row().classes('w-full no-wrap mt-2 gap-1'):
                            li = ui.number(value=state.next_index, precision=0).props('dense dark outlined').classes('w-1/3')
                            ui.button('Tag', on_click=lambda p=img_path, i=li: action_tag(p, int(i.value))).classes('w-2/3').props('color=green')

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
with ui.header().classes('items-center bg-slate-900 text-white border-b border-gray-700').style('height: 70px'):
    with ui.row().classes('w-full items-center gap-4 no-wrap px-4'):
        ui.label('🖼️ NiceSorter').classes('text-xl font-bold shrink-0 text-green-400')
        with ui.row().classes('flex-grow gap-2'):
            ui.input('Source').bind_value(state, 'source_dir').classes('flex-grow').props('dark dense outlined')
            ui.input('Output').bind_value(state, 'output_dir').classes('flex-grow').props('dark dense outlined')
        ui.button('SAVE', on_click=save_profile_settings).props('color=blue flat')
        ui.button('LOAD', on_click=load_images).props('color=white flat').classes('font-bold')

with ui.left_drawer(value=True).classes('bg-gray-950 p-4 border-r border-gray-800').props('width=320'):
    sidebar_container = ui.column().classes('w-full')

with ui.column().classes('w-full p-6 bg-gray-900 min-h-screen text-white'):
    pagination_container = ui.column().classes('w-full items-center mb-6')
    grid_container = ui.column().classes('w-full')
    ui.separator().classes('my-10 bg-gray-800')
    with ui.row().classes('w-full justify-around p-6 bg-gray-950 rounded-xl border border-gray-800'):
        with ui.column():
            ui.radio(['Copy', 'Move'], value=state.batch_mode).bind_value(state, 'batch_mode').props('inline dark color=green')
        with ui.column():
            ui.radio(['Keep', 'Move to Unused', 'Delete'], value=state.cleanup_mode).bind_value(state, 'cleanup_mode').props('inline dark color=green')
        with ui.row().classes('items-center gap-4'):
            ui.button('APPLY PAGE', on_click=action_apply_page).props('outline color=white lg')
            ui.button('APPLY GLOBAL', on_click=lambda: (SorterEngine.commit_global(state.output_dir, state.cleanup_mode, state.batch_mode, state.source_dir), load_images())).props('lg').classes('bg-red-700')

ui.keyboard(on_key=handle_key)
ui.dark_mode().enable()
load_images()
ui.run(title="Nice Sorter", host="0.0.0.0", port=8080, reload=False)