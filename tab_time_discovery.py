import streamlit as st
import os
from engine import SorterEngine

def render(path_t, quality, threshold, id_prefix):
    target_imgs = SorterEngine.get_images(path_t)
    unmatched_t = [f for f in target_imgs if not f.startswith("id")]
    
    if st.session_state.idx_time < len(unmatched_t):
        t_file = unmatched_t[st.session_state.idx_time]
        t_path = os.path.join(path_t, t_file)
        t_time = os.path.getmtime(t_path)
        
        st.subheader(f"Target: {t_file}")
        st.image(SorterEngine.compress_for_web(t_path, quality))

        siblings = SorterEngine.get_sibling_controls(path_t)
        matches = []
        for folder in siblings:
            for c_file in SorterEngine.get_images(folder):
                c_p = os.path.join(folder, c_file)
                delta = abs(t_time - os.path.getmtime(c_p))
                if delta <= threshold:
                    matches.append({'path': c_p, 'delta': delta, 'folder': os.path.basename(folder)})
        
        matches = sorted(matches, key=lambda x: x['delta'])
        
        st.divider()
        if not matches: st.warning("No matches.")
        for m in matches:
            with st.container(border=True):
                c1, c2 = st.columns([1, 2])
                c1.image(SorterEngine.compress_for_web(m['path'], 30))
                with c2:
                    st.write(f"**{os.path.basename(m['path'])}** (Δ {m['delta']:.1f}s)")
                    if st.button("MATCH", key=m['path']):
                        SorterEngine.execute_match(t_path, m['path'], path_t, id_prefix)
                        st.rerun()
        if st.button("SKIP"): st.session_state.idx_time += 1; st.rerun()
    else: st.success("Done.")