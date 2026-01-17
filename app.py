import streamlit as st
import os
from engine import SorterEngine
import tab_time_discovery
import tab_id_review
import tab_unused_review # Import the new tab

st.set_page_config(layout="wide", page_title="Turbo Sorter Pro v9.5")

if 'history' not in st.session_state: st.session_state.history = []
if 'idx_time' not in st.session_state: st.session_state.idx_time = 0
if 'idx_id' not in st.session_state: st.session_state.idx_id = 0

# --- Sidebar ---
BASE_PATH = "/storage"
favs = SorterEngine.load_favorites()

with st.sidebar:
    st.title("⭐ Profiles")
    selected_fav = st.selectbox("Load Profile", ["None"] + list(favs.keys()))
    
    st.divider()
    st.title("📁 Paths")
    f_data = favs.get(selected_fav, {})
    path_t = st.text_input("Discovery Target", value=f_data.get("disc_t", BASE_PATH))
    path_rv_t = st.text_input("Review Target", value=f_data.get("rev_t", os.path.join(path_t, "selected_target")))
    path_rv_c = st.text_input("Review Control", value=f_data.get("rev_c", os.path.join(path_t, "selected_control")))

    # Collision Scanner
    m_t = SorterEngine.get_id_mapping(path_rv_t)
    m_c = SorterEngine.get_id_mapping(path_rv_c)
    common_ids = sorted(list(set(m_t.keys()) & set(m_c.keys())))
    
    collisions = [pid for pid in (set(m_t.keys()) | set(m_c.keys())) if len(m_t.get(pid, [])) > 1 or len(m_c.get(pid, [])) > 1]
    
    if collisions:
        st.error(f"⚠️ {len(collisions)} ID Collisions!")
        for cid in collisions:
            if st.button(f"Fix {cid}", key=f"btn_{cid}"):
                if cid in common_ids:
                    st.session_state.idx_id = common_ids.index(cid)
                    st.rerun()

    st.divider()
    quality = st.slider("Quality", 5, 100, 40)
    id_val = st.number_input("Next ID", value=SorterEngine.get_max_id_number(path_t) + 1)
    prefix = f"id{int(id_val):03d}_"

# --- Tabs ---
t1, t2, t3 = st.tabs(["🕒 1. Time Discovery", "🆔 2. ID Match Review", "♻️ 3. Compare Unused"])

with t1:
    tab_time_discovery.render(path_t, quality, 50, prefix)

with t2:
    tab_id_review.render(path_rv_t, path_rv_c, quality, prefix)

with t3:
    # This tab lets you pull files back FROM unused folders TO selected folders
    tab_unused_review.render(path_rv_t, path_rv_c, quality)