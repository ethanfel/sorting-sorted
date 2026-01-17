import streamlit as st
import os
from engine import SorterEngine

def render(path_rv_t, path_rv_c, quality, next_prefix):
    # Mapping IDs to lists to handle collisions
    map_t = SorterEngine.get_id_mapping(path_rv_t)
    map_c = SorterEngine.get_id_mapping(path_rv_c)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if st.session_state.idx_id < len(common_ids):
        curr_id = common_ids[st.session_state.idx_id]
        t_files, c_files = map_t.get(curr_id, []), map_c.get(curr_id, [])

        st.subheader(f"Reviewing ID: {curr_id} ({st.session_state.idx_id + 1}/{len(common_ids)})")
        
        # Radio buttons allow selection between colliding files
        t_idx = st.radio("Target File", range(len(t_files)), format_func=lambda x: t_files[x], horizontal=True) if len(t_files) > 1 else 0
        c_idx = st.radio("Control File", range(len(c_files)), format_func=lambda x: c_files[x], horizontal=True) if len(c_files) > 1 else 0

        t_p = os.path.join(path_rv_t, t_files[t_idx])
        c_p = os.path.join(path_rv_c, c_files[c_idx])

        col1, col2 = st.columns(2)
        col1.image(SorterEngine.compress_for_web(t_p, quality), caption=f"Target: {t_files[t_idx]}")
        col2.image(SorterEngine.compress_for_web(c_p, quality), caption=f"Control: {c_files[c_idx]}")
        
        # Actions
        b1, b2, b3 = st.columns(3)
        if b1.button("❌ Move Pair to Unused", use_container_width=True, type="primary"):
            SorterEngine.move_to_unused_synced(t_p, c_p, path_rv_t, path_rv_c)
            st.rerun()

        if b2.button("✅ Keep & Harmonize", use_container_width=True):
            SorterEngine.harmonize_names(t_p, c_p)
            if len(t_files) <= 1 and len(c_files) <= 1:
                st.session_state.idx_id += 1
            st.rerun()

        if b3.button("➡️ Next ID", use_container_width=True):
            st.session_state.idx_id += 1
            st.rerun()

        # Re-ID Tool for splitting collisions
        with st.expander("🛠️ Re-ID Tool"):
            st.write("Assign a new unique ID to this specific pair to resolve the collision.")
            if st.button(f"Assign to {next_prefix}"):
                SorterEngine.re_id_file(t_p, next_prefix)
                SorterEngine.re_id_file(c_p, next_prefix)
                st.success(f"Files reassigned to {next_prefix}")
                st.rerun()
    else:
        st.info("Review complete.")
        if st.button("Reset Review Progress"): 
            st.session_state.idx_id = 0
            st.rerun()