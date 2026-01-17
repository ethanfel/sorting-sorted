import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_t, quality, threshold, id_prefix):
    images = SorterEngine.get_images(path_t)
    # Filter for files that haven't been matched yet
    unmatched = [f for f in images if not f.startswith("id")]

    if st.session_state.idx_time < len(unmatched):
        t_file = unmatched[st.session_state.idx_time]
        t_path = os.path.join(path_t, t_file)
        t_time = os.path.getmtime(t_path)
        
        st.subheader(f"Discovery: {t_file} ({st.session_state.idx_time + 1}/{len(unmatched)})")
        st.image(SorterEngine.compress_for_web(t_path, quality))

        # Multi-folder sibling matching
        parent = os.path.dirname(path_t)
        siblings = [os.path.join(parent, d) for d in os.listdir(parent) 
                    if os.path.isdir(os.path.join(parent, d)) and 
                    os.path.abspath(os.path.join(parent, d)) != os.path.abspath(path_t)]
        
        matches = []
        for folder in siblings:
            for c_file in SorterEngine.get_images(folder):
                c_path = os.path.join(folder, c_file)
                delta = abs(t_time - os.path.getmtime(c_path))
                if delta <= threshold:
                    matches.append({'path': c_path, 'delta': delta, 'folder': os.path.basename(folder)})

        if not matches: st.warning("No time-sync matches found in sibling folders.")
        
        for m in sorted(matches, key=lambda x: x['delta']):
            with st.container(border=True):
                col1, col2 = st.columns([1, 2])
                col1.image(SorterEngine.compress_for_web(m['path'], 20))
                with col2:
                    st.write(f"**Folder:** {m['folder']} | **Δ:** {m['delta']:.1f}s")
                    if st.button("MATCH", key=m['path']):
                        # Logic to move/rename would go here
                        st.session_state.idx_time += 1
                        st.rerun()
                        
        if st.button("SKIP", use_container_width=True):
            st.session_state.idx_time += 1
            st.rerun()
    else:
        st.success("All images in the target folder have been reviewed.")