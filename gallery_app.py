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
        # Load Defaults
        profiles = SorterEngine.load_profiles()
        p_data = profiles.get("Default", {})
        
        self.source_dir = p_data.get("tab5_source", ".")
        self.output_dir = p_data.get("tab5_out", ".")
        
        self.page = 0
        self.page_size = 24
        self.grid_cols = 4
        self.active_cat = "Default"
        self.next_index = 1
        
        # Caches
        self.all_images = []
        self.staged_data = {}
        self.green_dots = set()
        self.index_map = {} # For 5x5 sidebar grid

state = AppState()

# ==========================================
# 2. FAST THUMBNAIL SERVER (The Speed Secret)
# ==========================================
# Instead of embedding bytes in HTML (slow), we create a dedicated API 
# that serves WebP thumbnails. The browser loads these in parallel.

@app.get('/thumbnail')
async def get_thumbnail(path: str, size: int = 400):
    """
    Serves a resized WebP thumbnail. 
    Uses run.cpu_bound to prevent blocking the UI.
    """
    if not os.path.exists(path):
        return Response(status_code=404)
        
    # We use a lower quality (q=70) for grid speed
    img_bytes = await run.cpu_bound(
        SorterEngine.compress_for_web, path, quality=70, target_size=size
    )
    
    if img_bytes:
        return Response(content=img_bytes, media_type="image/webp")
    return Response(status_code=500)

@app.get('/full_res')
async def get_full_res(path: str):
    """Serves high-quality image for Zoom/Preview."""
    img_bytes = await run.cpu_bound(
        SorterEngine.compress_for_web, path, quality=90, target_size=None
    )
    return Response(content=img_bytes, media_type="image/webp")


# ==========================================
# 3. LOGIC & ACTIONS
# ==========================================

def load_images():
    """Scans folder and updates state."""
    if os.path.exists(state.source_dir):
        state.all_images = SorterEngine.get_images(state.source_dir, recursive=True)
        refresh_staged_info()
    else:
        ui.notify(f"Source not found: {state.source_dir}", type='warning')

def refresh_staged_info():
    """Refreshes DB data and Green Dots cache."""
    state.staged_data = SorterEngine.get_staged_data()
    
    # Calculate Green Dots (Pages with tags)
    state.green_dots.clear()
    staged_keys = set(state.staged_data.keys())
    for idx, img_path in enumerate(state.all_images):
        if img_path in staged_keys:
            state.green_dots.add(idx // state.page_size)
            
    # Calculate Sidebar Grid Map (Numbers used in current cat)
    state.index_map.clear()
    # 1. Staging
    for info in state.staged_data.values():
        if info['cat'] == state.active_cat:
            try:
                num = int(info['name'].rsplit('_', 1)[1].split('.')[0])
                state.index_map[num] = True
            except: pass
    # 2. Disk
    cat_path = os.path.join(state.output_dir, state.active_cat)
    if os.path.exists(cat_path):
        for f in os.listdir(cat_path):
            if f.startswith(state.active_cat) and "_" in f:
                try:
                    num = int(f.rsplit('_', 1)[1].split('.')[0])
                    state.index_map[num] = True
                except: pass

def get_current_batch():
    start = state.page * state.page_size
    return state.all_images[start : start + state.page_size]

async def action_tag(img_path, manual_idx=None):
    """Tags an image."""
    idx = manual_idx if manual_idx else state.next_index
    ext = os.path.splitext(img_path)[1]
    name = f"{state.active_cat}_{idx:03d}{ext}"
    
    # Check Conflicts
    final_path = os.path.join(state.output_dir, state.active_cat, name)
    staged_names = {v['name'] for v in state.staged_data.values() if v['cat'] == state.active_cat}
    
    if name in staged_names or os.path.exists(final_path):
        ui.notify(f"Conflict! {name} already exists.", type='negative')
        name = f"{state.active_cat}_{idx:03d}_copy{ext}" # Simple fallback

    SorterEngine.stage_image(img_path, state.active_cat, name)
    
    # Auto-increment global if we used the global counter
    if manual_idx is None or manual_idx == state.next_index:
        state.next_index = idx + 1
    
    ui.notify(f"Tagged: {name}", type='positive')
    refresh_staged_info()
    refresh_ui()

def action_untag(img_path):
    SorterEngine.clear_staged_item(img_path)
    refresh_staged_info()
    refresh_ui()

def action_delete(img_path):
    SorterEngine.delete_to_trash(img_path)
    load_images() # File list changed, must rescan
    refresh_ui()

def action_apply_page(mode="Copy", cleanup="Keep"):
    batch = get_current_batch()
    SorterEngine.commit_batch(batch, state.output_dir, cleanup, mode)
    ui.notify("Page Applied!")
    load_images()
    refresh_ui()


# ==========================================
# 4. UI COMPONENTS
# ==========================================

def open_zoom_dialog(path):
    with ui.dialog() as dialog, ui.card().classes('w-full max-w-4xl'):
        ui.label(os.path.basename(path)).classes('text-lg font-bold')
        # Use the /full_res route for high quality
        ui.image(f"/full_res?path={path}").classes('w-full rounded')
        ui.button('Close', on_click=dialog.close).classes('w-full')
    dialog.open()

def render_sidebar():
    sidebar_container.clear()
    with sidebar_container:
        ui.label("🏷️ Category Manager").classes('text-xl font-bold mb-2')
        
        # 1. 5x5 Visual Grid
        with ui.grid(columns=5).classes('gap-1 mb-4'):
            for i in range(1, 26):
                is_used = i in state.index_map
                # NiceGUI allows dynamic coloring easily
                color = 'green' if is_used else 'grey-3'
                
                btn = ui.button(str(i), on_click=lambda i=i: set_index(i))
                btn.props(f'color={color} size=sm flat')
                # If used, add a green dot visual (or just use button color)
        
        def set_index(i):
            state.next_index = i
            idx_input.set_value(i)

        # 2. Controls
        categories = SorterEngine.get_categories() or ["Default"]
        
        def update_cat(e):
            state.active_cat = e.value
            refresh_staged_info() # Updates the grid map
            render_sidebar()      # Redraw sidebar to show new map
            
        ui.select(categories, value=state.active_cat, on_change=update_cat, label="Active Tag").classes('w-full')
        
        with ui.row().classes('w-full items-end'):
            idx_input = ui.number(label="Next #", value=state.next_index, min=1, precision=0).bind_value(state, 'next_index').classes('w-2/3')
            ui.button('🔄', on_click=lambda: detect_next()).classes('w-1/4')

        def detect_next():
            used = state.index_map.keys()
            state.next_index = max(used) + 1 if used else 1
            idx_input.set_value(state.next_index)

def render_gallery():
    grid_container.clear()
    batch = get_current_batch()
    
    # Calculate optimal thumbnail size based on columns
    # 4 cols -> ~400px, 8 cols -> ~200px
    thumb_size = int(1600 / state.grid_cols)
    
    with grid_container:
        # Use Tailwind grid
        with ui.grid(columns=state.grid_cols).classes('w-full gap-2'):
            for img_path in batch:
                is_staged = img_path in state.staged_data
                staged_info = state.staged_data.get(img_path)
                
                # CARD
                with ui.card().classes('p-2 no-shadow border border-gray-300'):
                    
                    # Header: Name | Zoom | Del
                    with ui.row().classes('w-full justify-between items-center no-wrap'):
                        ui.label(os.path.basename(img_path)[:10]).classes('text-xs text-gray-500')
                        with ui.row().classes('gap-1'):
                            ui.button(icon='zoom_in', on_click=lambda p=img_path: open_zoom_dialog(p)).props('flat size=sm dense')
                            ui.button(icon='close', color='red', on_click=lambda p=img_path: action_delete(p)).props('flat size=sm dense')

                    # Image (WebP from Server)
                    # We encode the path to be URL safe
                    url = f"/thumbnail?path={img_path}&size={thumb_size}"
                    ui.image(url).classes('w-full h-auto rounded').props('no-spinner')
                    
                    # Status / Action
                    if is_staged:
                        ui.label(f"🏷️ {staged_info['cat']}").classes('bg-green-100 text-green-800 text-xs p-1 rounded w-full text-center my-1')
                        # Extract number for "Untag (#5)"
                        try:
                            num = int(staged_info['name'].rsplit('_', 1)[1].split('.')[0])
                            label = f"Untag (#{num})"
                        except:
                            label = "Untag"
                        ui.button(label, color='grey', on_click=lambda p=img_path: action_untag(p)).classes('w-full')
                    else:
                        # Index Input + Tag Button
                        with ui.row().classes('w-full no-wrap gap-1 mt-1'):
                            # Local input for this card
                            local_idx = ui.number(value=state.next_index, min=1, precision=0).props('dense outlined').classes('w-1/3')
                            ui.button('Tag', color='primary', 
                                      on_click=lambda p=img_path, i=local_idx: action_tag(p, int(i.value))
                                     ).classes('w-2/3')

def render_pagination():
    pagination_container.clear()
    total_pages = math.ceil(len(state.all_images) / state.page_size)
    if total_pages <= 1: return

    with pagination_container:
        with ui.row().classes('w-full justify-center items-center gap-4'):
            # Slider
            ui.slider(min=0, max=total_pages-1, value=state.page, on_change=lambda e: set_page(e.value)).classes('w-1/3')
            
            # Buttons (Window)
            start = max(0, state.page - 2)
            end = min(total_pages, state.page + 3)
            
            ui.button('◀', on_click=lambda: set_page(state.page - 1)).props('flat')
            
            for p in range(start, end):
                color = 'primary' if p == state.page else 'grey'
                label = str(p + 1)
                if p in state.green_dots: label += " 🟢"
                ui.button(label, color=color, on_click=lambda p=p: set_page(p))
            
            ui.button('▶', on_click=lambda: set_page(state.page + 1)).props('flat')

def set_page(idx):
    if 0 <= idx < math.ceil(len(state.all_images) / state.page_size):
        state.page = idx
        refresh_ui()

def refresh_ui():
    render_sidebar()
    render_pagination()
    render_gallery()

# ==========================================
# 5. KEYBOARD SHORTCUTS
# ==========================================
def handle_key(e):
    if not e.action.keydown: return
    if e.key.arrow_left: set_page(state.page - 1)
    if e.key.arrow_right: set_page(state.page + 1)
    # Add number keys 1-9 to set category or tag quickly?
    
# ==========================================
# 6. MAIN LAYOUT
# ==========================================
# Initialize Data
load_images()

with ui.header().classes('bg-white text-black border-b border-gray-200'):
    with ui.row().classes('w-full items-center justify-between'):
        ui.label('🖼️ NiceGUI Gallery Sorter').classes('text-xl font-bold')
        with ui.row().classes('gap-4'):
            ui.input('Source', value=state.source_dir).bind_value(state, 'source_dir')
            ui.input('Output', value=state.output_dir).bind_value(state, 'output_dir')
            ui.button('Load', on_click=load_images)

with ui.layout():
    # Left Sidebar
    with ui.left_drawer(fixed=True, value=True).classes('bg-gray-50 p-4') as drawer:
        sidebar_container = ui.column().classes('w-full')

    # Main Content
    with ui.column().classes('w-full p-4'):
        # Top Pagination
        pagination_container = ui.column().classes('w-full items-center mb-4')
        
        # Gallery Grid
        grid_container = ui.column().classes('w-full')
        
        # Batch Actions Footer
        ui.separator().classes('my-8')
        with ui.row().classes('w-full justify-center gap-4'):
            ui.button('APPLY PAGE', on_click=lambda: action_apply_page()).props('outline')
            ui.button('APPLY GLOBAL', color='red', on_click=lambda: ui.notify("Global not impl in demo")).classes('font-bold')

# Bind Keys
ui.keyboard(on_key=handle_key)

# Initial Render
refresh_ui()

# Start App
ui.run(
    title="Gallery Sorter", 
    host="0.0.0.0",   # <--- REQUIRED for Docker
    port=8080,        # <--- NiceGUI default
    reload=False      # Set True only for development
)