import streamlit as st
import os
from engine import SorterEngine
import tab_id_review, tab_time_discovery

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro")

# --- Session State ---
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0

# --- Status Bar ---
matches_this_session = len([h for h in st.session_state.history if 'link' in h['type']])
moves_to_unused = len([h for h in st.session_state.history if h['type'] == 'unused'])

st.info(f"📊 **Session Stats:** {matches_this_session} Matches Created | {moves_to_unused} Sent to Unused")

# --- Sidebar ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()
selected_fav = st.sidebar.selectbox("⭐ Favorites", ["None"] + list(favs.keys()))

path_t = st.sidebar.text_input("Path 1 (Target)", value=favs[selected_fav]['target'] if selected_fav != "None" else BASE_PATH)
path_c = st.sidebar.text_input("Path 2 (Control)", value=favs[selected_fav]['control'] if selected_fav != "None" else BASE_PATH)

quality = st.sidebar.slider("Bandwidth Compression", 5, 100, 40)
threshold = st.sidebar.number_input("Time Threshold (s)", value=50)
next_id_val = st.sidebar.number_input("Next ID Number", value=SorterEngine.get_max_id_number(path_t) + 1)
id_prefix = f"id{next_id_val:03d}_"

if st.sidebar.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
    SorterEngine.revert_action(st.session_state.history.pop())
    st.rerun()

# --- Tabs ---
t1, t2 = st.tabs(["🆔 ID Match Review", "🕒 Time Discovery"])
with t1: tab_id_review.render(path_t, path_c, quality)
with t2: tab_time_discovery.render(path_t, path_c, quality, threshold, id_prefix)