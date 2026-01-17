import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery, tab_id_review, tab_unused_review, tab_category_sorter

# Start Database
SorterEngine.init_db()

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro DB")

# --- GLOBAL SESSION INITIALIZATION ---
# All indexes must be initialized here to avoid AttributeErrors
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0      # Fix for Tab 1
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0          # Fix for Tab 2
if 'idx_unused' not in st.session_state: st.session_state.idx_unused = 0  # Fix for Tab 3
if 'idx_cat' not in st.session_state: st.session_state.idx_cat = 0        # Fix for Tab 4

# --- Sidebar ---
profiles = SorterEngine.load_profiles()
selected = st.sidebar.selectbox("⭐ Profiles", ["None"] + list(profiles.keys()))
p_data = profiles.get(selected, {})

path_t = st.sidebar.text_input("Discovery/Category Target", value=p_data.get("disc_t", "/storage"))
path_out = st.sidebar.text_input("Category Output", value=p_data.get("path_out", "/storage"))
naming_mode = st.sidebar.radio("Naming Mode", ["id", "original"], index=0 if p_data.get("mode") == "id" else 1)

# Review Paths
path_rv_t = st.sidebar.text_input("Review Target", value=p_data.get("rev_t", os.path.join(path_t, "selected_target")))
path_rv_c = st.sidebar.text_input("Review Control", value=p_data.get("rev_c", os.path.join(path_t, "selected_control")))

if st.sidebar.button("💾 Save Profile"):
    prof_name = st.sidebar.text_input("Profile Name", key="save_prof_input")
    if prof_name: 
        SorterEngine.save_profile(prof_name, path_t, path_rv_t, path_rv_c, path_out, naming_mode)
        st.sidebar.success(f"Profile {prof_name} Saved!")
        st.rerun()

if st.sidebar.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
    SorterEngine.revert_action(st.session_state.history.pop())
    st.rerun()

# --- Tabs ---
t1, t2, t3, t4 = st.tabs(["🕒 1. Discovery", "🆔 2. ID Review", "♻️ 3. Unused", "📂 4. Category Sorter"])

with t1: tab_time_discovery.render(path_t, 40, 50, "id001_")
with t2: tab_id_review.render(path_rv_t, path_rv_c, 40)
with t3: tab_unused_review.render(path_rv_t, path_rv_c, 40)
with t4: tab_category_sorter.render(path_t, path_out, 40, naming_mode)