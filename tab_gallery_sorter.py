import streamlit as st
import os
import math
from engine import SorterEngine

# --- CALLBACKS ---
def cb_tag_image(img_path, selected_cat):
    # Guard against tagging with a separator
    if selected_cat.startswith("---") or selected_cat == "":
        st.toast("⚠️ Select a valid category first!", icon="🚫")
        return

    staged = SorterEngine.get_staged_data()
    ext = os.path.splitext(img_path)[1]
    count = len([v for v in staged.values() if v['cat'] == selected_cat]) + 1
    new_name = f"{selected_cat}_{count:03d}{ext}"
    SorterEngine.stage_image(img_path, selected_cat, new_name)

def cb_untag_image(img_path):
    SorterEngine.clear_staged_item(img_path)

def cb_delete_image(img_path):
    SorterEngine.delete_to_trash(img_path)

def cb_apply_batch(current_batch, path_o, cleanup_mode):
    SorterEngine.commit_batch(current_batch, path_o, cleanup_mode)


# --- FRAGMENT 1: SIDEBAR (Manager) ---
@st.fragment
def render_sidebar_content():
    st.divider()
    st.subheader("🏷️ Category Manager")
    
    # 1. GET CATEGORIES & PROCESS SEPARATORS
    cats = SorterEngine.get_categories()
    
    # Setup List with Separators
    processed_cats = []
    last_char = ""
    if cats:
        for cat in cats:
            current_char = cat[0].upper()
            if last_char and current_char != last_char:
                processed_cats.append(f"--- {current_char} ---")
            processed_cats.append(cat)
            last_char = current_char

    # 2. RADIO SELECTION
    # We default to the first real category if nothing is selected
    if "t5_active_cat" not in st.session_state:
        st.session_state.t5_active_cat = cats[0] if cats else "Default"

    # Handle case where previously selected cat was deleted
    if st.session_state.t5_active_cat not in processed_cats:
        st.session_state.t5_active_cat = cats[0] if cats else "Default"

    selection = st.radio("Active Tag", processed_cats, key="t5_radio_select")

    # Update global state (but ignore separators)
    if not selection.startswith("---"):
        st.session_state.t5_active_cat = selection

    st.divider()

    # 3. TABS: ADD / EDIT
    tab_add, tab_edit = st.tabs(["➕ Add", "✏️ Edit"])
    
    # --- ADD TAB ---
    with tab_add:
        c1, c2 = st.columns([3, 1])
        new_cat = c1.text_input("New Name", label_visibility="collapsed", placeholder="New...", key="t5_new_cat")
        if c2.button("Add", key="btn_add_cat"):
            if new_cat:
                SorterEngine.add_category(new_cat)
                st.rerun()

    # --- EDIT TAB (Rename & Delete) ---
    with tab_edit:
        # Determine target (block separators)
        target_cat = st.session_state.t5_active_cat
        is_valid = target_cat and not target_cat.startswith("---") and target_cat in cats

        if is_valid:
            st.caption(f"Editing: **{target_cat}**")
            
            # RENAME SECTION
            # TRICK: We use the category name in the key. 
            # This forces Streamlit to reset the input box when you switch categories.
            rename_val = st.text_input("Rename to:", value=target_cat, key=f"ren_{target_cat}")
            
            if st.button("💾 Save Name", key=f"save_{target_cat}", use_container_width=True):
                if rename_val and rename_val != target_cat:
                    SorterEngine.rename_category(target_cat, rename_val)
                    st.session_state.t5_active_cat = rename_val # Update selection
                    st.rerun()
            
            st.markdown("---")
            
            # DELETE SECTION
            if st.button("🗑️ Delete Category", key=f"del_cat_{target_cat}", type="primary", use_container_width=True):
                SorterEngine.delete_category(target_cat)
                # Fallback to first available category after delete
                remaining = SorterEngine.get_categories()
                st.session_state.t5_active_cat = remaining[0] if remaining else "Default"
                st.rerun()

        else:
            st.info("Select a valid category above to edit.")