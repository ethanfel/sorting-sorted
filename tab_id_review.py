import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, path_c, quality):
    map_t = SorterEngine.get_id_mapping(path_t)
    map_c = SorterEngine.get_id_mapping(path_c)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if st.session_state.idx_id < len(common_ids):
        curr_id = common_ids[st.session_state.idx_id]
        t_f, c_f = map_t[curr_id], map_c[curr_id]
        t_p, c_p = os.path.join(path_t, t_f), os.path.join(path_c, c_f)
        
        st.subheader(f"Reviewing ID: {curr_id}")
        col1, col2 = st.columns(2)
        
        img1 = SorterEngine.compress_for_web(t_p, quality)
        img2 = SorterEngine.compress_for_web(c_p, quality)
        
        if img1: col1.image(img1, caption=f"Target: {t_f}")
        if img2: col2.image(img2, caption=f"Control: {c_f}")
        
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("❌ Move Pair to Unused (Synced Name)", use_container_width=True, type="primary"):
            # Use the new engine method to ensure names match in 'unused'
            t_un, c_un = SorterEngine.move_to_unused_synced(t_p, c_p, path_t, path_c)
            
            st.session_state.history.append({
                'type': 'unused', 
                't_src': t_p, 't_dst': t_un, 
                'c_src': c_p, 'c_dst': c_un
            })
            st.session_state.idx_id += 1
            st.rerun()

        if btn_col2.button("✅ Keep Both / Next", use_container_width=True):
            st.session_state.idx_id += 1
            st.rerun()
    else:
        st.info("No matching IDs found.")