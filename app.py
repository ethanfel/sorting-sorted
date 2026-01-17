import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v8.5")

if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0

# --- Sidebar ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()

with st.sidebar:
    st.title("⭐ Profiles")
    selected_fav = st.selectbox("Load Profile", ["None"] + list(favs.keys()))
    
    if selected_fav != "None" and st.button("🗑️ Delete Profile"):
        SorterEngine.delete_favorite(selected_fav)
        st.rerun()

    st.divider()
    st.title("📁 Paths")
    f_data = favs.get(selected_fav, {})
    
    path_t = st.text_input("Discovery Target", value=f_data.get("disc_t", BASE_PATH))
    path_rv_t = st.text_input("Review Target Folder", value=f_data.get("rev_t", os.path.join(path_t, "selected_target")))
    path_rv_c = st.text_input("Review Control Folder", value=f_data.get("rev_c", os.path.join(path_t, "selected_control")))

    with st.expander("💾 Save Current Paths"):
        name = st.text_input("Profile Name")
        if st.button("Confirm Save"):
            if name: 
                SorterEngine.save_favorite(name, path_t, path_rv_t, path_rv_c)
                st.rerun()

    st.divider()
    quality = st.slider("Quality", 5, 100, 40)
    threshold = st.number_input("Threshold (s)", value=50)
    id_val = st.number_input("Next ID", value=SorterEngine.get_max_id_number(path_t) + 1)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

# --- Tabs ---
t1, t2 = st.tabs(["🕒 1. Time Discovery", "🆔 2. ID Match Review"])
with t1: tab_time_discovery.render(path_t, quality, threshold, prefix)
with t2: tab_id_review.render(path_rv_t, path_rv_c, quality)