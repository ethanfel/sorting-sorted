import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, path_c, quality, threshold, id_prefix):
    target_imgs = SorterEngine.get_images(path_t)
    unmatched_t = [f for f in target_imgs if not f.startswith("id")]
    
    if st.session_state.idx_time < len(unmatched_t):
        t_file = unmatched_t[st.session_state.idx_time]
        t_path = os.path.join(path_t, t_file)
        t_time = os.path.getmtime(t_path)
        
        best_c_path, min_delta = None, threshold
        for c_file in SorterEngine.get_images(path_c):
            c_p = os.path.join(path_c, c_file)
            delta = abs(t_time - os.path.getmtime(c_p))
            if delta < min_delta:
                min_delta, best_c_path = delta, c_p
            
        if best_c_path:
            st.subheader(f"Time Match Found (Δ {min_delta:.1f}s)")
            col1, col2 = st.columns(2)
            col1.image(SorterEngine.compress_for_web(t_path, quality), caption=t_file)
            col2.image(SorterEngine.compress_for_web(best_c_path, quality), caption=os.path.basename(best_c_path))
            
            b1, b2, b3 = st.columns(3)
            if b1.button("MATCH", type="primary", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "standard")
                st.session_state.history.append({'type': 'link_standard', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b2.button("SOLO", use_container_width=True):
                t_dst, c_dst = SorterEngine.execute_move(t_path, best_c_path, path_t, path_c, id_prefix, "solo")
                st.session_state.history.append({'type': 'link_solo', 't_src': t_path, 't_dst': t_dst, 'c_src': best_c_path, 'c_dst': c_dst})
                st.rerun()
            if b3.button("SKIP", use_container_width=True):
                st.session_state.idx_time += 1
                st.rerun()
        else:
            st.warning("No time matches found within threshold.")
            if st.button("SKIP"):
                st.session_state.idx_time += 1
                st.rerun()
    else:
        st.success("All unmatched images in target folder have been reviewed.")