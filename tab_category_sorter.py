import streamlit as st
import os, shutil
from engine import SorterEngine

def render(path_s, path_o, quality, naming_mode):
    if not path_s or not os.path.exists(path_s):
        st.warning("Please provide a valid Source Folder path.")
        return
    if not path_o:
        st.warning("Please provide a Category Output folder.")
        return

    images = SorterEngine.get_images(path_s)
    categories = SorterEngine.get_categories()

    if st.session_state.idx_cat < len(images):
        curr_file = images[st.session_state.idx_cat]
        curr_p = os.path.join(path_s, curr_file)
        
        # 🎞️ Filmstrip Preview (Source script feature)
        st.write("### 🎞️ Filmstrip")
        fs_cols = st.columns(7)
        # Show current + next 6
        for i, img_name in enumerate(images[st.session_state.idx_cat : st.session_state.idx_cat + 7]):
            fs_cols[i].image(SorterEngine.compress_for_web(os.path.join(path_s, img_name), 10))

        st.divider()

        col_img, col_btns = st.columns([2, 1])
        with col_img:
            st.image(SorterEngine.compress_for_web(curr_p, quality), caption=curr_file)
        
        with col_btns:
            fid = SorterEngine.get_folder_id(path_s)
            st.write(f"**Folder ID:** `{fid}`")
            
            # Dynamic Category Buttons from Database
            for cat in categories:
                if st.button(cat, use_container_width=True, key=f"btn_{cat}"):
                    _, ext = os.path.splitext(curr_p)
                    # Use naming mode from database profile
                    name = curr_file if naming_mode == "original" else f"{fid}{ext}"
                    
                    dst_dir = os.path.join(path_o, cat)
                    os.makedirs(dst_dir, exist_ok=True)
                    dst_p = os.path.join(dst_dir, name)
                    
                    # Prevent overwriting
                    count = 2
                    final_dst = dst_p
                    while os.path.exists(final_dst):
                        root, ext = os.path.splitext(name)
                        final_dst = os.path.join(dst_dir, f"{root}_{count}{ext}")
                        count += 1
                        
                    shutil.move(curr_p, final_dst)
                    st.session_state.history.append({'type': 'cat_move', 't_src': curr_p, 't_dst': final_dst})
                    st.toast(f"Moved to {cat}")
                    st.rerun()
            
            st.divider()
            new_cat = st.text_input("➕ Quick Add Category")
            if st.button("Add Category") and new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

            if st.button("⏭️ SKIP", use_container_width=True):
                st.session_state.idx_cat += 1
                st.rerun()
    else:
        st.success("Categorization complete for this folder.")
        if st.button("Reset Category Counter"):
            st.session_state.idx_cat = 0
            st.rerun()