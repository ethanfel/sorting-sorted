import streamlit as st
import os
from engine import SorterEngine
import tab_id_review
import tab_time_discovery

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro")

if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0

# --- Status Bar ---
matches = len([h for h in st.session_state.history if 'link' in h['type']])
unused = len([h for h in st.session_state.history if h['type'] == 'unused'])
st.info(f"📊 **Session Stats:** {matches} Matches Linked | {unused} Moved to Unused")

# --- Sidebar ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()
selected_fav = st.sidebar.selectbox("⭐ Favorites", ["None"] + list(favs.keys()))

def_t = favs[selected_fav]['target'] if selected_fav != "None" else BASE_PATH
def_c = favs[selected_fav]['control'] if selected_fav != "None" else BASE_PATH

path_t = st.sidebar.text_input("Path 1 (Target)", value=def_t)
path_c = st.sidebar.text_input("Path 2 (Control)", value=def_c)

if st.sidebar.button("💾 Save as Favorite"):
    fav_name = st.sidebar.text_input("Name for favorite:")
    if fav_name: SorterEngine.save_favorite(fav_name, path_t, path_c)

quality = st.sidebar.slider("Compression Quality", 5, 100, 40)
threshold = st.sidebar.number_input("Time Threshold (s)", value=50)
id_val = st.sidebar.number_input("Next ID Number", value=SorterEngine.get_max_id_number(path_t) + 1)
prefix = f"id{int(id_val):03d}_"

if st.sidebar.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
    SorterEngine.revert_action(st.session_state.history.pop())
    st.rerun()

# --- Tab Navigation ---
t1, t2 = st.tabs(["🆔 Tab 1: ID Review", "🕒 Tab 2: Time Discovery"])
with t1:
    tab_id_review.render(path_t, path_c, quality)
with t2:
    tab_time_discovery.render(path_t, path_c, quality, threshold, prefix)