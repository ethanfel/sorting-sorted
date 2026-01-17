import streamlit as st
import os
from engine import SorterEngine

def render(path_rv_t, path_rv_c, quality):
    # Target and Control specific 'unused' folders
    unused_t_path = os.path.join(path_rv_t, "unused")
    unused_c_path = os.path.join(path_rv_c, "unused")
    
    if not os.path.exists(unused_t_path) or not os.path.exists(unused_c_path):
        st.info("No 'unused' folders found in the current paths.")
        return

    map_t = SorterEngine.get_id_mapping(unused_t_path)
    map_c = SorterEngine.get_id_mapping(unused_c_path)
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if not common_ids:
        st.success("The 'unused' folders are empty or have no matching IDs.")
        return

    # Use a separate session state index for this tab
    if 'idx_unused' not in st.session_state: st.session_state.idx_unused = 0
    
    if st.session_state.idx_unused < len(common_ids):
        curr_id = common_ids[st.session_state.idx_unused]
        t_files, c_files = map_t.get(curr_id, []), map_c.get(curr_id, [])

        st.subheader(f"Reviewing Unused ID: {curr_id} ({st.session_state.idx_unused + 1}/{len(common_ids)})")
        
        t_idx = st.radio("Unused Target", range(len(t_files)), format_func=lambda x: t_files[x], horizontal=True, key=f"ut_{curr_id}") if len(t_files) > 1 else 0
        c_idx = st.radio("Unused Control", range(len(c_files)), format_func=lambda x: c_files[x], horizontal=True, key=f"uc_{curr_id}") if len(c_files) > 1 else 0

        t_p = os.path.join(unused_t_path, t_files[t_idx])
        c_p = os.path.join(unused_c_path, c_files[c_idx])

        col1, col2 = st.columns(2)
        col1.image(SorterEngine.compress_for_web(t_p, quality), caption=f"Unused Target: {t_files[t_idx]}")
        col2.image(SorterEngine.compress_for_web(c_p, quality), caption=f"Unused Control: {c_files[c_idx]}")
        
        b1, b2 = st.columns(2)
        if b1.button("✅ RESTORE (Move back to Selected)", use_container_width=True, type="primary"):
            SorterEngine.restore_from_unused(t_p, c_p, path_rv_t, path_rv_c)
            st.toast(f"Restored {curr_id} to selected folders.")
            st.rerun()

        if b2.button("➡️ Ignore / Next", use_container_width=True):
            st.session_state.idx_unused += 1
            st.rerun()
    else:
        st.info("Finished reviewing unused files.")
        if st.button("Reset Unused View"): 
            st.session_state.idx_unused = 0
            st.rerun()