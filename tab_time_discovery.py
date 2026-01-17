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
        
        # 1. Main Display: Target Image
        st.subheader(f"Target: {t_file} ({st.session_state.idx_time + 1}/{len(unmatched_t)})")
        st.image(SorterEngine.compress_for_web(t_path, quality))

        # 2. Scanning all sibling folders
        control_folders = SorterEngine.get_sibling_controls(path_t)
        all_matches = []
        
        for folder in control_folders:
            for c_file in SorterEngine.get_images(folder):
                c_p = os.path.join(folder, c_file)
                delta = abs(t_time - os.path.getmtime(c_p))
                if delta <= threshold:
                    all_matches.append({'path': c_p, 'delta': delta, 'folder': os.path.basename(folder)})
        
        all_matches = sorted(all_matches, key=lambda x: x['delta'])

        # 3. Actions for Target
        col_n, col_s = st.columns(2)
        if col_n.button("🚫 NO MATCH (N)", use_container_width=True):
            dst = os.path.join(path_t, "selected_target_no_control", t_file)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(t_path, dst)
            st.session_state.history.append({'type': 'move', 't_src': t_path, 't_dst': dst})
            st.rerun()
            
        if col_s.button("⏩ SKIP (S)", use_container_width=True):
            st.session_state.idx_time += 1
            st.rerun()

        st.divider()
        st.write("### 🕒 Time-Sync Matches")

        # 4. Result Grid (The Sidebar Logic)
        if not all_matches:
            st.info("No time-sync matches found in sibling folders.")
        else:
            for m in all_matches:
                with st.container(border=True):
                    c1, c2 = st.columns([1, 2])
                    c1.image(SorterEngine.compress_for_web(m['path'], 30))
                    with c2:
                        st.write(f"**{os.path.basename(m['path'])}**")
                        st.write(f"From: `{m['folder']}` | Δ: {m['delta']:.1f}s")
                        
                        b1, b2 = st.columns(2)
                        if b1.button("MATCH", key=f"m_{m['path']}", use_container_width=True):
                            t_dst, c_dst = SorterEngine.execute_match(t_path, m['path'], path_t, id_prefix, "standard")
                            st.session_state.history.append({'type': 'link_standard', 't_src': t_path, 't_dst': t_dst, 'c_src': m['path'], 'c_dst': c_dst})
                            st.rerun()
                        if b2.button("SOLO", key=f"s_{m['path']}", use_container_width=True):
                            t_dst, c_dst = SorterEngine.execute_match(t_path, m['path'], path_t, id_prefix, "solo")
                            st.session_state.history.append({'type': 'link_solo', 't_src': t_path, 't_dst': t_dst, 'c_src': m['path'], 'c_dst': c_dst})
                            st.rerun()
    else:
        st.success("Target folder processing complete!")