import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_rv_t, path_rv_c, quality):
    map_t = SorterEngine.get_id_mapping(path_rv_t)
    map_c = SorterEngine.get_id_mapping(path_rv_c)
    
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if st.session_state.idx_id < len(common_ids):
        curr_id = common_ids[st.session_state.idx_id]
        t_p = os.path.join(path_rv_t, map_t[curr_id])
        c_p = os.path.join(path_rv_c, map_c[curr_id])
        
        st.subheader(f"Reviewing ID: {curr_id} ({st.session_state.idx_id + 1}/{len(common_ids)})")
        
        # Displaying filenames to see the mismatch
        st.text(f"Target Name: {os.path.basename(t_p)}")
        st.text(f"Control Name: {os.path.basename(c_p)}")

        col1, col2 = st.columns(2)
        img1 = SorterEngine.compress_for_web(t_p, quality)
        img2 = SorterEngine.compress_for_web(c_p, quality)
        
        if img1: col1.image(img1)
        if img2: col2.image(img2)
        
        btn_col1, btn_col2 = st.columns(2)
        
        # Action 1: Move to Unused with harmonization
        if btn_col1.button("❌ Move to Unused (Match Names)", use_container_width=True, type="primary"):
            t_un, c_un = SorterEngine.move_to_unused_synced(t_p, c_p, path_rv_t, path_rv_c)
            st.session_state.history.append({
                'type': 'unused', 
                't_src': t_p, 't_dst': t_un, 
                'c_src': c_p, 'c_dst': c_un
            })
            st.session_state.idx_id += 1
            st.rerun()

        # Action 2: Keep Both with harmonization
        if btn_col2.button("✅ Keep Both & Harmonize Names", use_container_width=True):
            # Ensure the control name matches target name before moving on
            new_c_p = SorterEngine.harmonize_names(t_p, c_p)
            if new_c_p != c_p:
                st.toast(f"Renamed control to match target.")
            
            st.session_state.idx_id += 1
            st.rerun()
    else:
        st.info("Review complete.")
        if st.button("Reset Review Progress"):
            st.session_state.idx_id = 0
            st.rerun()