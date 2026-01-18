import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery, tab_id_review, tab_unused_review, tab_category_sorter, tab_gallery_sorter

# 1. Initialize DB FIRST
try:
    SorterEngine.init_db()
except Exception as e:
    st.error(f"Database Initialization Error: {e}")

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v12.1")

# 2. Session State Defaults
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0
if 'idx_unused' not in st.session_state: st.session_state.idx_unused = 0
if 'idx_cat' not in st.session_state: st.session_state.idx_cat = 0

# 3. Load Profiles with Safety Fallback
try:
    profiles = SorterEngine.load_profiles()
except Exception as e:
    st.warning("Database schema mismatch detected. Please delete /app/sorter_database.db and refresh.")
    st.stop()

# Ensure at least one profile exists
if not profiles:
    SorterEngine.save_tab_paths("Default")
    profiles = SorterEngine.load_profiles()

# --- SIDEBAR ---
with st.sidebar:
    st.divider()
    with st.expander("🔍 Path Debugger"):
        st.write(f"**Active Workspace:** {selected_profile}")
        st.json(p_data) # Shows exactly what the DB sees for this profile

    st.divider()
    quality = st.slider("Display Quality", 5, 100, 40)
    
    # Prefix Logic
    disc_target = p_data.get("tab1_target", "/storage")
    next_id_num = SorterEngine.get_max_id_number(disc_target) + 1
    id_val = st.number_input("Next ID Number", value=next_id_num)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

# --- TABS ---
t1, t2, t3, t4, t5 = st.tabs(["🕒 Discovery", "🆔 ID Review", "♻️ Unused", "📂 Categorizer", "🖼️ Gallery Staging"])

with t1:
    path_t1 = st.text_input("Discovery Target", value=p_data.get("tab1_target", "/storage"), key="t1_in")
    if path_t1 != p_data.get("tab1_target"):
        SorterEngine.save_tab_paths(selected_profile, t1_t=path_t1)
    tab_time_discovery.render(path_t1, quality, 50, prefix)

with t2:
    c1, c2 = st.columns(2)
    path_t2_t = c1.text_input("Review Target", value=p_data.get("tab2_target", "/storage"), key="t2_t_in")
    path_t2_c = c2.text_input("Review Control", value=p_data.get("tab2_control", "/storage"), key="t2_c_in")
    if path_t2_t != p_data.get("tab2_target") or path_t2_c != p_data.get("tab2_control"):
        SorterEngine.save_tab_paths(selected_profile, t2_t=path_t2_t, t2_c=path_t2_c)
    tab_id_review.render(path_t2_t, path_t2_c, quality, prefix)

with t3:
    tab_unused_review.render(path_t2_t, path_t2_c, quality)

# Inside your app.py tabs section
with t4:
    # Ensure variables exist even if DB row is fresh
    p4_s = p_data.get("tab4_source") or "/storage"
    p4_o = p_data.get("tab4_out") or "/storage"
    mode = p_data.get("mode") or "id"
    tab_category_sorter.render(p4_s, p4_o, quality, mode)

with t5:
    # Tab 5 should not depend on Tab 4 paths at all
    tab_gallery_sorter.render(quality, selected_profile)