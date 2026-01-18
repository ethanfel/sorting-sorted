import streamlit as st
import os
from engine import SorterEngine

@st.fragment
def gallery_grid(images, staged, quality, selected_cat):
    cols = st.columns(4)
    for idx, img_path in enumerate(images):
        with cols[idx % 4]:
            is_staged = img_path in staged
            
            with st.container(border=True):
                # Header: Name and Delete X
                c_name, c_del = st.columns([5, 1])
                c_name.caption(os.path.basename(img_path)[:20])
                if c_del.button("❌", key=f"del_{idx}"):
                    trash_p = SorterEngine.delete_to_trash(img_path)
                    st.session_state.history.append({'type': 'move', 't_src': img_path, 't_dst': trash_p})
                    st.rerun()

                # Visual tag indicator
                if is_staged:
                    st.success(f"Tagged: {staged[img_path]['cat']}")

                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data:
                    st.image(img_data, use_container_width=True)
                
                # Simplified Button
                if not is_staged:
                    if st.button("Tag", key=f"tg_{idx}", use_container_width=True):
                        ext = os.path.splitext(img_path)[1]
                        count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                        new_name = f"{selected_cat}_{count:03d}{ext}"
                        SorterEngine.stage_image(img_path, selected_cat, new_name)
                        st.rerun()
                else:
                    if st.button("Untag", key=f"utg_{idx}", use_container_width=True):
                        SorterEngine.clear_staged_item(img_path)
                        st.rerun()

def render(quality, profile_name):
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("Save Paths"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    cats = SorterEngine.get_categories()
    selected_cat = st.sidebar.radio("Active Tag", cats)
    
    if not os.path.exists(path_s): return

    images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    gallery_grid(images, staged, quality, selected_cat)

    st.divider()
    cleanup = st.radio("Unmarked Files:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    if st.button("APPLY CHANGES", type="primary", use_container_width=True):
        SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
        st.rerun()