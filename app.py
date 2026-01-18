import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review
import tab_unused_review
import tab_category_sorter
import tab_gallery_sorter

# 1. Initialize Database and Schema
try:
    SorterEngine.init_db()
except Exception as e:
    st.error(f"Database Error: {e}")

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v12.5")

# 2. Global Session State Initialization
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0
if 'idx_unused' not in st.session_state: st.session_state.idx_unused = 0
if 'idx_cat' not in st.session_state: st.session_state.idx_cat = 0

# 3. Load Workspace Profiles
try:
    profiles = SorterEngine.load_profiles()
except Exception as e:
    st.warning("Database schema mismatch. Please delete /app/sorter_database.db and refresh.")
    st.stop()

# Ensure at least one workspace exists
if not profiles:
    SorterEngine.save_tab_paths("Default")
    profiles = SorterEngine.load_profiles()

# --- SIDEBAR: Workspace & Global Tools ---
with st.sidebar:
    st.title("⭐ Workspaces")
    selected_profile = st.selectbox("Active Workspace", list(profiles.keys()), key="active_profile")
    p_data = profiles.get(selected_profile, {})

    st.divider()
    quality = st.slider("Display Quality", 5, 100, 40)
    
    # Calculate ID based on Tab 1 Target
    t1_target = p_data.get("tab1_target") or "/storage"
    id_val = st.number_input("Next ID Number", value=SorterEngine.get_max_id_number(t1_target) + 1)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO LAST MOVE", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

    with st.expander("🔍 Workspace Path Debugger"):
        st.json(p_data)

# --- MAIN TAB SYSTEM ---


t1, t2, t3, t4, t5 = st.tabs([
    "🕒 1. Discovery", 
    "🆔 2. ID Review", 
    "♻️ 3. Unused", 
    "📂 4. Category Sorter", 
    "🖼️ 5. Gallery Staged"
])

with t1:
    st.header("Time-Sync Matcher")
    t1_p = st.text_input("Discovery Target", value=p_data.get("tab1_target") or "/storage", key="t1_in")
    if t1_p != p_data.get("tab1_target"):
        SorterEngine.save_tab_paths(selected_profile, t1_t=t1_p)
    tab_time_discovery.render(t1_p, quality, 50, prefix)

with t2:
    st.header("Collision Review")
    c1, c2 = st.columns(2)
    t2_t = c1.text_input("Review Target", value=p_data.get("tab2_target") or "/storage", key="t2_t_in")
    t2_c = c2.text_input("Review Control", value=p_data.get("tab2_control") or "/storage", key="t2_c_in")
    if t2_t != p_data.get("tab2_target") or t2_c != p_data.get("tab2_control"):
        SorterEngine.save_tab_paths(selected_profile, t2_t=t2_t, t2_c=t2_c)
    tab_id_review.render(t2_t, t2_c, quality, prefix)

with t3:
    st.header("Unused Archive")
    # Uses paths from Tab 2
    tab_unused_review.render(t2_t, t2_c, quality)

with t4:
    st.header("One-to-Many Categorizer")
    c1, c2 = st.columns(2)
    t4_s = c1.text_input("Source Folder", value=p_data.get("tab4_source") or "/storage", key="t4_s_in")
    t4_o = c2.text_input("Output Folder", value=p_data.get("tab4_out") or "/storage", key="t4_o_in")
    mode = st.radio("Naming Mode", ["id", "original"], index=0 if p_data.get("mode") == "id" else 1, horizontal=True)
    if t4_s != p_data.get("tab4_source") or t4_o != p_data.get("tab4_out") or mode != p_data.get("mode"):
        SorterEngine.save_tab_paths(selected_profile, t4_s=t4_s, t4_o=t4_o, mode=mode)
    tab_category_sorter.render(t4_s, t4_o, quality, mode)

with t5:
    # Gallery Sorter handles its own path saving internally to prevent refresh loops
    tab_gallery_sorter.render(quality, selected_profile)