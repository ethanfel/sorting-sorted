import streamlit as st
import os, shutil
from engine import SorterEngine

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro")

# --- Session State ---
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0

# --- Sidebar: Favorites & Navigation ---
st.sidebar.title("⭐ Favorites")
favs = SorterEngine.load_favorites()
selected_fav = st.sidebar.selectbox("Load a saved pair:", ["None"] + list(favs.keys()))

st.sidebar.divider()
st.sidebar.title("📁 Path Selection")
BASE_PATH = "/storage"

# Shallow Browser (Prevents Hang)
def get_subs(p):
    try: return sorted([d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))])
    except: return []

# Build path manually or from Favs
if selected_fav != "None":
    default_t = favs[selected_fav]['target']
    default_c = favs[selected_fav]['control']
else:
    default_t = BASE_PATH
    default_c = BASE_PATH

path_t = st.sidebar.text_input("Target Path (Folder 1)", value=default_t)
path_c = st.sidebar.text_input("Control Path (Folder 2)", value=default_c)

if st.sidebar.button("💾 Save as Favorite"):
    name = st.sidebar.text_input("Favorite Name")
    if name:
        SorterEngine.save_favorite(name, path_t, path_c)
        st.sidebar.success("Saved!")

# --- Global Settings ---
st.sidebar.divider()
quality = st.sidebar.slider("Compression Quality", 5, 100, 40)
threshold = st.sidebar.number_input("Time Match (s)", value=50)
auto_id = SorterEngine.get_max_id_number(path_t) + 1
next_id_val = st.sidebar.number_input("Next ID Number", value=auto_id)
id_prefix = f"id{next_id_val:03d}_"

if st.sidebar.button("↶ UNDO LAST", use_container_width=True, disabled=not st.session_state.history):
    SorterEngine.revert_action(st.session_state.history.pop())
    st.rerun()

# --- Tabs ---
tab1, tab2 = st.tabs(["🆔 Review Existing IDs", "🕒 Discover New Matches"])

with tab1:
    map_t = SorterEngine.get_id_mapping(path_t)
    map_c = SorterEngine.get_id_mapping(path_c)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if common_ids:
        curr_id = common_ids[0] # Focus on first available match
        t_f, c_f = map_t[curr_id], map_c[curr_id]
        t_p, c_p = os.path.join(path_t, t_f), os.path.join(path_c, c_f)
        
        st.subheader(f"ID Match: {curr_id}")
        col1, col2 = st.columns(2)
        col1.image(SorterEngine.compress_for_web(t_p, quality), caption=t_f)
        col2.image(SorterEngine.compress_for_web(c_p, quality), caption=c_f)
        
        if st.button("❌ Move Pair to Unused", use_container_width=True):
            t_un = os.path.join(path_t, "unused", t_f)
            c_un = os.path.join(path_c, "unused", c_f)
            os.makedirs(os.path.dirname(t_un), exist_ok=True)
            os.makedirs(os.path.dirname(c_un), exist_ok=True)
            shutil.move(t_p, t_un)
            shutil.move(c_p, c_un)
            st.session_state.history.append({'type': 'unused', 't_src': t_p, 't_dst': t_un, 'c_src': c_p, 'c_dst': c_un})
            st.rerun()
    else: st.info("No ID matches found.")

with tab2:
    target_imgs = SorterEngine.get_images(path_t)
    unmatched_t = [f for f in target_imgs if not f.startswith("id")]
    
    if st.session_state.idx_time < len(unmatched_t):
        t_file = unmatched_t[st.session_state.idx_time]
        t_path = os.path.join(path_t, t_file)
        t_time = os.path.getmtime(t_path)
        
        # Optimized non-recursive match search
        best_c_path, min_delta = None, threshold
        for c_file in SorterEngine.get_images(path_c):
            c_p = os.path.join(path_c, c_file)
            delta = abs(t_time - os.path.getmtime(c_p))
            if delta < min_delta: min_delta, best_c_path = delta, c_p
            
        if best_c_path:
            st.subheader(f"Time Match Found (Δ {min_delta:.1f}s)")
            col1, col2 = st.columns(2)
            col1.image(SorterEngine.compress_for_web(t_path, quality), caption=t_file)
            col2.image(SorterEngine.compress_for_web(best_c_path, quality), caption=os.path.basename(best_c_path))
            
            b1, b2, b3 = st.columns(3)
            if b1.button("MATCH", type="primary", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "standard")
                st.session_state.history.append({'type': 'link_standard', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b2.button("SOLO", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "solo")
                st.session_state.history.append({'type': 'link_solo', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b3.button("SKIP", use_container_width=True):
                st.session_state.idx_time += 1
                st.rerun()
        else:
            st.warning("No time matches.")
            if st.button("SKIP"):
                st.session_state.idx_time += 1
                st.rerun()