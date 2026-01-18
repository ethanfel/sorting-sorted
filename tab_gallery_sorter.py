import streamlit as st
import os
from engine import SorterEngine

def render(quality, profile_name):
    st.subheader("🖼️ Gallery Staging Sorter")
    
    # 1. Load Workspace Settings
    profiles = SorterEngine.load_profiles()
    p_data = profiles.get(profile_name, {})

    c1, c2 = st.columns(2)
    path_s = c1.text_input("📁 Source Gallery Folder", value=p_data.get("tab5_source") or "/storage", key="t5_s_path")
    path_o = c2.text_input("🎯 Final Output Root", value=p_data.get("tab5_out") or "/storage", key="t5_o_path")
    
    if path_s != p_data.get("tab5_source") or path_o != p_data.get("tab5_out"):
        if st.button("💾 Save Gallery Paths"):
            SorterEngine.save_tab_paths(profile_name, t5_s=path_s, t5_o=path_o)
            st.rerun()

    # --- 2. SIDEBAR CATEGORIES ---
    with st.sidebar:
        st.divider()
        st.subheader("🏷️ Category Manager")
        new_cat = st.text_input("Quick Add Category", key="t5_add_cat")
        if st.button("➕ Add", use_container_width=True):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

        st.divider()
        cats = SorterEngine.get_categories()
        if not cats:
            st.warning("No categories found.")
            return
        selected_cat = st.radio("Active Tag:", cats, key="t5_active_tag")

    if not os.path.exists(path_s):
        st.info("Please enter a valid Source Path.")
        return

    # --- 3. THE FRAGMENTED GALLERY ---
    # This decorator prevents the whole app from rerunning when tagging
    @st.fragment
    def render_gallery():
        images = SorterEngine.get_images(path_s, recursive=True)
        staged = SorterEngine.get_staged_data()
        
        st.write(f"Images: **{len(images)}** | Tagged: **{len(staged)}**")
        
        cols = st.columns(4)
        for idx, img_path in enumerate(images):
            with cols[idx % 4]:
                is_staged = img_path in staged
                
                # Visual Tag Indicators
                if is_staged:
                    info = staged[img_path]
                    st.markdown(f"**✅ {info['cat']}**")
                    label = info['name']
                else:
                    label = os.path.basename(img_path)
                
                st.image(SorterEngine.compress_for_web(img_path, quality), caption=label)
                
                # Action Buttons inside Fragment
                if not is_staged:
                    if st.button(f"Tag: {selected_cat}", key=f"tag_{idx}"):
                        ext = os.path.splitext(img_path)[1]
                        count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
                        new_name = f"{selected_cat}_{count:03d}{ext}"
                        SorterEngine.stage_image(img_path, selected_cat, new_name)
                        st.rerun(scope="fragment") # Reruns ONLY the gallery
                else:
                    if st.button("❌ Remove", key=f"clear_{idx}"):
                        SorterEngine.clear_staged_item(img_path)
                        st.rerun(scope="fragment")

    # Call the fragmented gallery
    render_gallery()

    st.divider()
    
    # --- 4. APPLY (Outside fragment to ensure full refresh after disk move) ---
    cleanup = st.radio("Unmarked Files Action:", ["Keep", "Move to Unused", "Delete"], horizontal=True)
    if st.button("🚀 APPLY ALL CHANGES TO DISK", type="primary", use_container_width=True):
        if staged := SorterEngine.get_staged_data():
            SorterEngine.commit_staging(path_o, cleanup, source_root=path_s)
            st.success("Successfully processed images!")
            st.rerun()

render_gallery = render # Mapping for the tab loader