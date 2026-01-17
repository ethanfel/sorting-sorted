import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, quality):
    # 1. Detect all sibling folders (just like the original script)
    control_folders = SorterEngine.get_sibling_controls(path_t)
    
    # 2. Get ID mapping for Target
    # We check the root and the 'selected_target' subfolder
    target_search_paths = [path_t, os.path.join(path_t, "selected_target")]
    map_t = {}
    for p in target_search_paths:
        map_t.update(SorterEngine.get_id_mapping(p))
    
    # 3. Get ID mapping for all Sibling Controls
    map_c = {}
    for folder in control_folders:
        control_search_paths = [folder, os.path.join(path_t, "selected_control")]
        for p in control_search_paths:
            if os.path.exists(p):
                # Update map_c with found IDs, keeping track of their full paths
                images = SorterEngine.get_images(p)
                for f in images:
                    if f.startswith("id") and "_" in f:
                        prefix = f.split('_')[0]
                        map_c[prefix] = os.path.join(p, f)
    
    # 4. Find Common IDs
    common_ids = sorted(list(set(map_t.keys()) & set(map_c.keys())))
    
    if st.session_state.idx_id < len(common_ids):
        curr_id = common_ids[st.session_state.idx_id]
        
        # Determine full paths for display
        # map_t stores just the filename, map_c stores the full path
        t_filename = map_t[curr_id]
        # Find which target path the file is actually in
        t_p = ""
        for p in target_search_paths:
            potential_p = os.path.join(p, t_filename)
            if os.path.exists(potential_p):
                t_p = potential_p
                break
        
        c_p = map_c[curr_id]
        
        st.subheader(f"Reviewing Match: {curr_id} ({st.session_state.idx_id + 1}/{len(common_ids)})")
        
        col1, col2 = st.columns(2)
        img1 = SorterEngine.compress_for_web(t_p, quality)
        img2 = SorterEngine.compress_for_web(c_p, quality)
        
        if img1: col1.image(img1, caption=f"Target: {os.path.basename(t_p)}")
        if img2: col2.image(img2, caption=f"Control: {os.path.basename(c_p)}")
        
        # Actions
        btn1, btn2 = st.columns(2)
        if btn1.button("❌ Move Pair to Unused", use_container_width=True, type="primary"):
            # Use the synced renaming logic from engine.py
            t_un, c_un = SorterEngine.move_to_unused_synced(t_p, c_p, path_t, os.path.dirname(c_p))
            st.session_state.history.append({
                'type': 'unused', 
                't_src': t_p, 't_dst': t_un, 
                'c_src': c_p, 'c_dst': c_un
            })
            st.session_state.idx_id += 1
            st.rerun()

        if btn2.button("✅ Keep Both / Next", use_container_width=True):
            st.session_state.idx_id += 1
            st.rerun()
    else:
        st.info("No more matching ID pairs found in the target or sibling folders.")
        if st.button("Reset Review Progress"):
            st.session_state.idx_id = 0
            st.rerun()