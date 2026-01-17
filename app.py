import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review
import tab_unused_review
import tab_category_sorter

# Initialize Database and Tables
SorterEngine.init_db()

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v11.0 (Independent Path Mode)")

# --- GLOBAL SESSION INITIALIZATION ---
if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0      # Discovery Tab
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0          # Review Tab
if 'idx_unused' not in st.session_state: st.session_state.idx_unused = 0  # Unused Tab
if 'idx_cat' not in st.session_state: st.session_state.idx_cat = 0        # Category Tab

# --- SIDEBAR: Workspace Management ---
with st.sidebar:
    st.title("⭐ Workspaces")
    profiles = SorterEngine.load_profiles()
    profile_list = list(profiles.keys())
    
    selected_profile = st.selectbox("Select Workspace Profile", ["Default"] + profile_list)
    p_data = profiles.get(selected_profile, {})

    st.divider()
    st.title("⚙️ Global Settings")
    quality = st.slider("Bandwidth Quality", 5, 100, 40)
    
    # Calculate global ID across known project paths
    id_val = st.number_input("Global Next ID", value=SorterEngine.get_max_id_number(p_data.get("tab1_target", "/storage")) + 1)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO LAST ACTION", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

    with st.expander("💾 Create New Workspace"):
        new_prof_name = st.text_input("New Profile Name")
        if st.button("Save Current Setup"):
            if new_prof_name:
                # Saves a snapshot of all current tab paths
                SorterEngine.save_tab_paths(
                    new_prof_name,
                    t1_t=st.session_state.get('t1_path_val'),
                    t2_t=st.session_state.get('t2_target_val'),
                    t2_c=st.session_state.get('t2_control_val'),
                    t4_s=st.session_state.get('t4_source_val'),
                    t4_o=st.session_state.get('t4_out_val'),
                    mode=st.session_state.get('naming_mode_val')
                )
                st.rerun()

# --- MAIN TABS (Independent Logic) ---
t1, t2, t3, t4 = st.tabs(["🕒 1. Discovery", "🆔 2. ID Review", "♻️ 3. Unused", "📂 4. Category Sorter"])

with t1:
    st.header("Time-Sync Matcher")
    # Independent Path Logic for Tab 1
    path_t1 = st.text_input("Discovery Target Path", value=p_data.get("tab1_target", "/storage"), key="t1_path_input")
    st.session_state.t1_path_val = path_t1
    
    # Auto-save path change to the active profile
    if path_t1 != p_data.get("tab1_target"):
        SorterEngine.save_tab_paths(selected_profile, t1_t=path_t1)
    
    tab_time_discovery.render(path_t1, quality, 50, prefix)

with t2:
    st.header("ID Verification")
    c1, c2 = st.columns(2)
    # Independent Path Logic for Tab 2
    path_t2_t = c1.text_input("Review Target Folder", value=p_data.get("tab2_target", "/storage"), key="t2_target_input")
    path_t2_c = c2.text_input("Review Control Folder", value=p_data.get("tab2_control", "/storage"), key="t2_control_input")
    
    st.session_state.t2_target_val = path_t2_t
    st.session_state.t2_control_val = path_t2_c

    if path_t2_t != p_data.get("tab2_target") or path_t2_c != p_data.get("tab2_control"):
        SorterEngine.save_tab_paths(selected_profile, t2_t=path_t2_t, t2_c=path_t2_c)
    
    tab_id_review.render(path_t2_t, path_t2_c, quality, prefix)

with t3:
    st.header("Restore from Unused")
    # Tab 3 shares the Review paths but operates on the /unused subfolder
    tab_unused_review.render(path_t2_t, path_t2_c, quality)

with t4:
    st.header("One-to-Many Categorizer")
    # Independent Path Logic for Tab 4
    c1, c2 = st.columns(2)
    path_t4_s = c1.text_input("Source Images Folder", value=p_data.get("tab4_source", "/storage"), key="t4_source_input")
    path_t4_o = c2.text_input("Categorized Output Folder", value=p_data.get("tab4_out", "/storage"), key="t4_out_input")
    naming_mode = st.radio("Naming Preference", ["id", "original"], index=0 if p_data.get("mode") == "id" else 1, horizontal=True)
    
    st.session_state.t4_source_val = path_t4_s
    st.session_state.t4_out_val = path_t4_o
    st.session_state.naming_mode_val = naming_mode

    if path_t4_s != p_data.get("tab4_source") or path_t4_o != p_data.get("tab4_out") or naming_mode != p_data.get("mode"):
        SorterEngine.save_tab_paths(selected_profile, t4_s=path_t4_s, t4_o=path_t4_o, mode=naming_mode)
    
    tab_category_sorter.render(path_t4_s, path_t4_o, quality, naming_mode)