import streamlit as st
import pandas as pd

from src.sidebar import render_sidebar
from login import render_login_page
from circlehead import render_dashboard

from main import (
    func1,
    update_ch_raw_data,
    update_ho_raw_data,
    checking_call_age_ch_data,
)

st.set_page_config(page_title="Service Report Generator", layout="wide")

# ── 1. Login gate ─────────────────────────────────────────
if not render_login_page():
    st.stop()

# ── 2. Sidebar ────────────────────────────────────────────
page = render_sidebar()

# ── 3. Role shortcuts ─────────────────────────────────────
role      = st.session_state.get("user_role", "").strip().lower()
user_name = st.session_state.get("user_name", "")

is_ho = role == "ho"
is_ch = role == "ch"


def user_info_caption():
    parts = [f"Logged in as **{user_name}**"]
    if st.session_state.get("user_role"):
        parts.append(f"Role: {st.session_state['user_role']}")
    if st.session_state.get("user_regions"):
        parts.append(f"Regions: {st.session_state['user_regions']}")
    st.caption("  |  ".join(parts))


def access_denied():
    st.warning("⚠️ You don't have permission to access this page.")
    st.stop()


def get_ch_regions() -> list[str] | None:
    if is_ho:
        return None                     # HO sees all rows
    raw = st.session_state.get("user_regions", "")
    if not raw:
        return []                       # CH with nothing assigned → sees nothing
    return [r.strip() for r in str(raw).split(",") if r.strip()]


# ── 4. Pages ──────────────────────────────────────────────

# ── Upload (HO only) ──────────────────────────────────────
if page == "upload":
    if is_ch:
        access_denied()

    st.header("📤 Upload File & Create Report")
    user_info_caption()

    uploaded_raw_file = st.file_uploader(
        "Choose the Raw Data Excel file", type=["xlsx"]
    )

    if uploaded_raw_file is not None:
        if st.button("Upload Data"):
            with st.spinner("Processing data and pushing to Database..."):
                try:
                    checking_call_age_ch_data()
                    final_df = func1(uploaded_raw_file)
                    if isinstance(final_df, pd.DataFrame):
                        update_ch_raw_data()
                        update_ho_raw_data()
                        st.success("✅ Data updated in Database!")
                except Exception as e:
                    st.error(f"Error during processing: {e}")

    st.divider()


# ── HO Dashboard (HO only) ────────────────────────────────
elif page == "ho_dashboard":
    if is_ch:
        access_denied()

    user_info_caption()
    render_dashboard(
        sheet_name    = "HO Raw Data",
        title         = "📌 HO Dashboard",
        allow_remark  = True,
        region_filter = None,       # HO sees all rows
    )


# ── CH Dashboard (both roles can view) ────────────────────
#
#   CH  → allow_remark=True,  region_filter = their assigned circles
#   HO  → allow_remark=False, region_filter = None (sees all rows, read-only)
#
elif page == "ch_dashboard":
    user_info_caption()
    render_dashboard(
        sheet_name    = "CH Raw Data",
        title         = "📊 CH Dashboard",
        allow_remark  = is_ch,
        region_filter = get_ch_regions(),   # None for HO, list for CH
    )
