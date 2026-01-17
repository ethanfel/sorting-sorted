import streamlit as st
import os, shutil
from engine import SorterEngine

st.set_page_config(layout="wide", page_title="Advanced Image Sorter Web")

# --- Session State Initialization ---
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'history' not in st.session_state: st.session_state.history = []

# --- Sidebar Configuration ---
st.sidebar.title("🛠️ Global Settings")
BASE_PATH = "/storage"

def get_dirs(p):
    try:
        return sorted([d for d in os.listdir(p) if os.path.isdir(os.path.join(p, d))])
    except: return []

dirs = get_dirs(BASE_PATH)
target_sub = st.sidebar.selectbox("Target Folder (Folder 1)", dirs)
control_sub = st.sidebar.selectbox("Control Folder (Folder 2)", dirs)
quality = st.sidebar.slider("Compression Quality", 5, 100, 40)
threshold = st.sidebar.number_input("Time Match Threshold (s)", value=50)

path_t = os.path.join(BASE_PATH, target_sub) if target_sub else ""
path_c = os.path.join(BASE_PATH, control_sub) if control_sub else ""

# ID Management
auto_id = SorterEngine.get_max_id_number(path_t) + 1
next_id_val = st.sidebar.number_input("Next ID Number", value=auto_id)
id_prefix = f"id{next_id_val:03d}_"

# Undo Button
st.sidebar.divider()
if st.sidebar.button("↶ UNDO LAST ACTION", use_container_width=True, disabled=not st.session_state.history):
    last = st.session_state.history.pop()
    SorterEngine.revert_action(last)
    st.sidebar.success("Last action reverted.")
    st.rerun()

tab1, tab2 = st.tabs(["🆔 Tab 1: ID Match Review", "🕒 Tab 2: Time Discovery & Rename"])

# --- TAB 1: ID MATCH REVIEW ---
with tab1:
    map_t = SorterEngine.get_id_mapping(path_t)
    map_c = SorterEngine.get_id_mapping(path_c)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))

    if st.session_state.idx_id < len(common_ids):
        curr_id = common_ids[st.session_state.idx_id]
        t_f, c_f = map_t[curr_id], map_c[curr_id]
        t_p, c_p = os.path.join(path_t, t_f), os.path.join(path_c, c_f)

        st.subheader(f"Reviewing Match: {curr_id} ({st.session_state.idx_id + 1}/{len(common_ids)})")
        col1, col2 = st.columns(2)
        col1.image(SorterEngine.compress_for_web(t_p, quality), caption=f"Target: {t_f}")
        col2.image(SorterEngine.compress_for_web(c_p, quality), caption=f"Control: {c_f}")

        if st.button("❌ Move Pair to Unused", use_container_width=True, type="primary"):
            t_un = os.path.join(path_t, "unused", t_f)
            c_un = os.path.join(path_c, "unused", c_f)
            os.makedirs(os.path.dirname(t_un), exist_ok=True)
            os.makedirs(os.path.dirname(c_un), exist_ok=True)
            shutil.move(t_p, t_un)
            shutil.move(c_p, c_un)
            st.session_state.history.append({'type': 'unused', 't_src': t_p, 't_dst': t_un, 'c_src': c_p, 'c_dst': c_un})
            st.rerun()
    else:
        st.info("No more ID matches found.")

# --- TAB 2: TIME DISCOVERY ---
with tab2:
    target_imgs = SorterEngine.get_images(path_t)
    unmatched_t = [f for f in target_imgs if not f.startswith("id")]

    if st.session_state.idx_time < len(unmatched_t):
        t_file = unmatched_t[st.session_state.idx_time]
        t_path = os.path.join(path_t, t_file)
        t_time = os.path.getmtime(t_path)
        
        best_c_path, min_delta = None, threshold
        for c_file in SorterEngine.get_images(path_c):
            c_path = os.path.join(path_c, c_file)
            delta = abs(t_time - os.path.getmtime(c_path))
            if delta < min_delta:
                min_delta, best_c_path = delta, c_path
        
        if best_c_path:
            st.subheader(f"Suggested Match (Δ {min_delta:.1f}s)")
            col1, col2 = st.columns(2)
            col1.image(SorterEngine.compress_for_web(t_path, quality), caption=t_file)
            col2.image(SorterEngine.compress_for_web(best_c_path, quality), caption=os.path.basename(best_c_path))
            
            b1, b2, b3 = st.columns(3)
            if b1.button("MATCH (Standard)", type="primary", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "standard")
                st.session_state.history.append({'type': 'link_standard', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b2.button("SOLO (Woman)", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "solo")
                st.session_state.history.append({'type': 'link_solo', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b3.button("SKIP", use_container_width=True):
                st.session_state.idx_time += 1
                st.rerun()
        else:
            st.warning(f"No file found within {threshold}s for {t_file}")
            if st.button("SKIP NEXT"):
                st.session_state.idx_time += 1
                st.rerun()
    else:
        st.success("All unmatched files reviewed.")