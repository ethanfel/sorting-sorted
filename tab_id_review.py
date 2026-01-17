import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, path_c, quality):
    map_t = SorterEngine.get_id_mapping(path_t)
    map_c = SorterEngine.get_id_mapping(path_c)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if common_ids:
        curr_id = common_ids[0]
        t_f, c_f = map_t[curr_id], map_c[curr_id]
        t_p, c_p = os.path.join(path_t, t_f), os.path.join(path_c, c_f)
        
        st.subheader(f"Reviewing ID: {curr_id}")
        col1, col2 = st.columns(2)
        
        img1 = SorterEngine.compress_for_web(t_p, quality)
        img2 = SorterEngine.compress_for_web(c_p, quality)
        
        if img1: col1.image(img1, caption=t_f)
        if img2: col2.image(img2, caption=c_f)
        
        if st.button("❌ Move Pair to Unused", use_container_width=True):
            t_un = os.path.join(path_t, "unused", t_f)
            c_un = os.path.join(path_c, "unused", c_f)
            os.makedirs(os.path.dirname(t_un), exist_ok=True)
            os.makedirs(os.path.dirname(c_un), exist_ok=True)
            shutil.move(t_p, t_un)
            shutil.move(c_p, c_un)
            st.session_state.history.append({'type': 'unused', 't_src': t_p, 't_dst': t_un, 'c_src': c_p, 'c_dst': c_un})
            st.rerun()
    else:
        st.info("No existing ID matches found.")