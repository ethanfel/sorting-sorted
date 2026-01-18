import streamlit as st
import os
import math
from engine import SorterEngine

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    if 't5_page' not in st.session_state: st.session_state.t5_page = 0
    
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})
    
    c1, c2 = st.columns(2)
    path_s = c1.text_input("Source Folder", value=p_data.get("tab5_source", "/storage"), key="t5_s")
    path_o = c2.text_input("Output Folder", value=p_data.get("tab5_out", "/storage"), key="t5_o")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Settings"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    cats = SorterEngine.get_categories()
    if not cats:
        st.warning("No categories found.")
        return
    selected_cat = st.sidebar.radio("Active Tag", cats, key="t5_cat_radio")

    if not os.path.exists(path_s): return

    all_images = SorterEngine.get_images(path_s, recursive=True)
    staged = SorterEngine.get_staged_data()
    
    if not all_images:
        st.info("No images found.")
        return

    # --- VIEW SETTINGS ---
    with st.expander("👀 View Settings", expanded=False):
        page_size = st.slider("Images per Page", 12, 100, 24, 4)

    # --- PAGINATION ---
    total_items = len(all_images)
    total_pages = math.ceil(total_items / page_size)
    if st.session_state.t5_page >= total_pages: st.session_state.t5_page = max(0, total_pages - 1)
    
    start_idx = st.session_state.t5_page * page_size
    end_idx = start_idx + page_size
    
    # THIS IS THE BATCH WE WILL PROCESS
    current_batch = all_images[start_idx:end_idx]

    # --- HELPER: Controls ---
    def show_controls(key_suffix):
        cp1, cp2, cp3 = st.columns([1, 2, 1])
        with cp1:
            if st.button("⬅️ Previous", disabled=(st.session_state.t5_page == 0), key=f"prev_{key_suffix}"):
                st.session_state.t5_page -= 1
                st.rerun()
        with cp2:
            st.markdown(f"<h5 style='text-align: center;'>Page {st.session_state.t5_page + 1} of {total_pages}</h5>", unsafe_allow_html=True)
        with cp3:
            if st.button("Next ➡️", disabled=(st.session_state.t5_page >= total_pages - 1), key=f"next_{key_suffix}"):
                st.session_state.t5_page += 1
                st.rerun()

    show_controls("top")
    st.divider()

    # --- GRID ---
    cols = st.columns(4)
    for idx, img_path in enumerate(current_batch):
        unique_key = f"{st.session_state.t5_page}_{idx}"
        with cols[idx % 4]:
            is_staged = img_path in staged
            with st.container(border=True):
                # Header
                c_head1, c_head2 = st.columns([5, 1])
                c_head1.caption(os.path.basename(img_path)[:15])
                if c_head2.button("❌", key=f"del_{unique_key}"):
                    SorterEngine.delete_to_trash(img_path)
                    st.rerun()

                # Status
                if is_staged: st.success(f"🏷️ {staged[img_path]['cat']}")
                
                img_data = SorterEngine.compress_for_web(img_path, quality)
                if img_data: st.image(img_data, use_container_width=True)

                # Buttons
                if not is_staged:
                    if st.button("Tag", key=f"tag_{unique_key}", use_container_width=True):
                        ext = os.path.splitext(img_path)[1]
                        count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                        new_name = f"{selected_cat}_{count:03d}{ext}"
                        SorterEngine.stage_image(img_path, selected_cat, new_name)
                        st.rerun()
                else:
                    if st.button("Untag", key=f"untag_{unique_key}", use_container_width=True):
                        SorterEngine.clear_staged_item(img_path)
                        st.rerun()

    st.divider()
    show_controls("bottom")
    st.divider()

    # --- BATCH APPLY SECTION ---
    st.write(f"### 🚀 Batch Actions (Page {st.session_state.t5_page + 1} Only)")
    st.caption(f"This will process the **{len(current_batch)} images** visible above.")
    
    c_act1, c_act2 = st.columns([3, 1])
    cleanup = c_act1.radio("Action for Untagged Files on this Page:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    
    if c_act2.button("APPLY PAGE TO DISK", type="primary", use_container_width=True):
        with st.spinner("Processing current page..."):
            # Call the new BATCH method
            SorterEngine.commit_batch(current_batch, path_o, cleanup)
        
        st.success("Page processed!")
        st.rerun()