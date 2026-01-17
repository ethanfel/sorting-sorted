import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review

# Page Configuration
st.set_page_config(layout="wide", page_title="Advanced Sorter v8.0")

# --- Session State Initialization ---
if 'history' not in st.session_state: 
    st.session_state.history = []
if 'idx_time' not in st.session_state: 
    st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: 
    st.session_state.idx_id = 0

# --- Status Bar ---
# Calculates stats based on the history stack
matches_created = len([h for h in st.session_state.history if 'link' in h['type']])
unused_count = len([h for h in st.session_state.history if h['type'] == 'unused'])

st.info(f"📊 **Session Stats:** {matches_created} Matches Linked | {unused_count} Moved to Unused")

# --- Sidebar: Configuration & Profiles ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()

with st.sidebar:
    st.title("⭐ Profiles")
    selected_fav = st.selectbox("Load Favorite", ["None"] + list(favs.keys()))
    
    # Delete Profile Logic
    if selected_fav != "None":
        if st.button("🗑️ Delete Selected Profile", type="secondary"):
            SorterEngine.delete_favorite(selected_fav)
            st.rerun()

    st.divider()
    st.title("📁 Paths")
    # Sets default path from favorites or base storage
    def_t = favs[selected_fav]['target'] if selected_fav != "None" else BASE_PATH

    # User inputs for target folder
    path_t = st.text_input("Target Folder Path (Folder 1)", value=def_t)
    
    # Automatic Sibling Detection for UI feedback
    siblings = SorterEngine.get_sibling_controls(path_t)
    st.caption(f"Found {len(siblings)} sibling control folders at this level.")

    # Create New Profile
    with st.expander("💾 Create New Profile"):
        new_fav_name = st.text_input("Profile Name")
        if st.button("Save Profile"):
            if new_fav_name:
                SorterEngine.save_favorite(new_fav_name, path_t, path_t) # Control follows target sibling logic
                st.success(f"Saved {new_fav_name}")
                st.rerun()

    st.divider()
    # Global Settings matched to original script logic
    quality = st.slider("Bandwidth Quality", 5, 100, 40)
    threshold = st.number_input("Time Threshold (s)", value=50)
    
    # ID Logic: Finds next ID based on existing files
    id_val = st.number_input("Next ID Number", value=SorterEngine.get_max_id_number(path_t) + 1)
    prefix = f"id{int(id_val):03d}_"

    # Undo Action (Z shortcut logic)
    if st.button("↶ UNDO", use_container_width=True, disabled=not st.session_state.history):
        SorterEngine.revert_action(st.session_state.history.pop())
        # Revert indices based on the type of action undone
        if st.session_state.idx_id > 0: st.session_state.idx_id -= 1
        st.rerun()

# --- Main Tab Navigation ---
# Reordered: Discovery first, then Review
t1, t2 = st.tabs(["🕒 1. Time Discovery", "🆔 2. ID Match Review"])

with t1:
    # Tab 1: Discovery uses sibling-scan logic
    tab_time_discovery.render(path_t, quality, threshold, prefix)

with t2:
    # Tab 2: Review matches across all siblings
    tab_id_review.render(path_t, quality)