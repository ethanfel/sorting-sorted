import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery, tab_id_review, tab_unused_review, tab_category_sorter

# Start Database
SorterEngine.init_db()

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v11.1")

# --- INITIALIZATION ---
for key in ['history', 'idx_time', 'idx_id', 'idx_unused', 'idx_cat']:
    if key not in st.session_state: 
        st.session_state[key] = [] if key == 'history' else 0

# --- SIDEBAR ---
profiles = SorterEngine.load_profiles()
selected_profile = st.sidebar.selectbox("Workspace Profile", ["Default"] + list(profiles.keys()))
p_data = profiles.get(selected_profile, {})

with st.sidebar:
    st.title("⚙️ Global Settings")
    quality = st.slider("Bandwidth Quality", 5, 100, 40)
    
    # Calculate ID based on Tab 1 target
    t1_target = p_data.get("tab1_target", "/storage")
    id_val = st.number_input("Global Next ID", value=SorterEngine.get_max_id_number(t1_target) + 1)
    prefix = f"id{int(id_val):03d}_"

    if st.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        st.rerun()

# --- TABS ---
t1, t2, t3, t4, t5 = st.tabs(["Discovery", "Review", "Unused", "Categorizer", "🖼️ Gallery Sorter"])

with t1:
    path_t1 = st.text_input("Discovery Target", value=p_data.get("tab1_target", "/storage"), key="t1_input")
    if path_t1 != p_data.get("tab1_target"):
        SorterEngine.save_tab_paths(selected_profile, t1_t=path_t1)
    tab_time_discovery.render(path_t1, quality, 50, prefix)

with t2:
    c1, c2 = st.columns(2)
    path_t2_t = c1.text_input("Review Target", value=p_data.get("tab2_target", "/storage"), key="t2_t_input")
    path_t2_c = c2.text_input("Review Control", value=p_data.get("tab2_control", "/storage"), key="t2_c_input")
    if path_t2_t != p_data.get("tab2_target") or path_t2_c != p_data.get("tab2_control"):
        SorterEngine.save_tab_paths(selected_profile, t2_t=path_t2_t, t2_c=path_t2_c)
    tab_id_review.render(path_t2_t, path_t2_c, quality, prefix)

with t3:
    tab_unused_review.render(path_t2_t, path_t2_c, quality)

with t4:
    c1, c2 = st.columns(2)
    path_t4_s = c1.text_input("Source Images", value=p_data.get("tab4_source", "/storage"), key="t4_s_input")
    path_t4_o = c2.text_input("Category Output", value=p_data.get("tab4_out", "/storage"), key="t4_o_input")
    mode = st.radio("Naming Mode", ["id", "original"], index=0 if p_data.get("mode") == "id" else 1, horizontal=True)
    
    if path_t4_s != p_data.get("tab4_source") or path_t4_o != p_data.get("tab4_out") or mode != p_data.get("mode"):
        # This now correctly accepts the 'mode' argument
        SorterEngine.save_tab_paths(selected_profile, t4_s=path_t4_s, t4_o=path_t4_o, mode=mode)
    
    tab_category_sorter.render(path_t4_s, path_t4_o, quality, mode)

with t5:
    import tab_gallery_sorter
    tab_gallery_sorter.render(quality)