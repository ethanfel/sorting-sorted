import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro")

# --- Session State ---
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0

# --- Status Bar ---
matches = len([h for h in st.session_state.history if 'link' in h['type']])
st.info(f"📊 **Session Stats:** {matches} Matches Created")

# --- Sidebar ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()

with st.sidebar:
    st.title("⭐ Profiles")
    selected_fav = st.selectbox("Load Favorite", ["None"] + list(favs.keys()))
    
    if selected_fav != "None":
        if st.button("🗑️ Delete Selected Profile"):
            SorterEngine.delete_favorite(selected_fav)
            st.rerun()

    st.divider()
    st.title("📁 Paths")
    def_t = favs[selected_fav]['target'] if selected_fav != "None" else BASE_PATH
    def_c = favs[selected_fav]['control'] if selected_fav != "None" else BASE_PATH

    path_t = st.text_input("Path 1 (Target)", value=def_t)
    path_c = st.text_input("Path 2 (Control)", value=def_c)

    with st.expander("💾 Create New Profile"):
        new_fav_name = st.text_input("Profile Name")
        if st.button("Save Profile"):
            if new_fav_name:
                SorterEngine.save_favorite(new_fav_name, path_t, path_c)
                st.success(f"Saved {new_fav_name}")
                st.rerun()

    st.divider()
    quality = st.slider("Quality", 5, 100, 40)
    threshold = st.number_input("Threshold (s)", value=50)
    id_val = st.number_input("Next ID", value=SorterEngine.get_max_id_number(path_t) + 1)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

# --- Reordered Tabs ---
t1, t2 = st.tabs(["🕒 Tab 1: Time Discovery", "🆔 Tab 2: ID Match Review"])
with t1:
    tab_time_discovery.render(path_t, path_c, quality, threshold, prefix)
with t2:
    tab_id_review.render(path_t, path_c, quality)