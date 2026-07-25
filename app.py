import io
import pytz
import pandas as pd
import streamlit as st
from datetime import datetime
from login import render_login_page
from src.sidebar import render_sidebar
from circlehead import render_dashboard

from main import (
    func1,
    update_ch_raw_data,
    update_ho_raw_data,
    checking_call_age_ch_data,
    update_call_assignment_in_ho,
    calls_data,
convert_df_to_formatted_excel,
get_missing_remarks_report)

st.set_page_config(page_title="Service Call Status App", layout="wide")

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
        "Choose the Raw Data Excel file", type=["xlsx"], key="raw_file"
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

    st.header("📤 Upload Call Assigned File")
    # user_info_caption()

    uploaded_call_assigned_file = st.file_uploader(
        "Choose the Call Assigned Data Excel file", type=["xlsx"], key="assigned_file"
    )

    if uploaded_call_assigned_file is not None:
        if st.button("Upload Call Assigned Data"):
            with st.spinner("Processing assignments and updating HO Raw Data..."):
                try:
                    # 1. Read the newly uploaded file
                    assigned_df = pd.read_excel(uploaded_call_assigned_file)
                    assigned_df.columns = assigned_df.columns.str.strip().str.lower().str.replace(" ","_")
                    
                    # Basic validation to ensure required columns exist
                    if "service_id" not in assigned_df.columns or "code" not in assigned_df.columns:
                        st.error("❌ The uploaded file must contain 'service_id' and 'code' columns.")
                    else:
                        
                        success = update_call_assignment_in_ho(assigned_df)
                        if success:
                            st.success("✅ Call Assigned data updated in HO Raw Data successfully!")
                        else:
                            st.error("❌ Failed to update HO Raw Data.")
                            
                except Exception as e:
                    st.error(f"Error during processing: {e}")

    st.divider()

    # --- Streamlit UI Block ---
    st.header("📥 Download Summary Report")

    if st.button("Generate Summary Report"):
        with st.spinner("Fetching data and creating beautifully formatted report..."):
            df = calls_data()
        
            if df is not None:
                # Convert to formatted Excel bytes
                excel_data = convert_df_to_formatted_excel(df)
            
                # Setup timezone and filenames
                IST = pytz.timezone('Asia/Kolkata')
                file_timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M')
            
                # Display download link
                st.success("Report generated successfully!")
                st.download_button(
                    label="⬇️ Click here to Download Excel",
                    data=excel_data,
                    file_name=f"summary_report_{file_timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("Could not retrieve data. Please check your connection or Google Sheet.")

    st.divider()

# ── Missing Remarks Audit Section ────────────────────────
    st.header("📋 Download Missing Remarks Audit Report")
    st.write("Identify CH & HO calls that are eligible for remarks but have missing entries across past working days.")

    col1, col2 = st.columns(2)

    with col1:
        selected_date = st.date_input(
            "Select Target Base Date (By Default :- Today Date)",
            value=pd.Timestamp.now().date(),
            format="YYYY-MM-DD",
            key="missing_remarks_target_date"
        )

    with col2:
        num_days = st.number_input(
            "Number of Working Days to Check (Excl. Sundays)",
            min_value=1,
            max_value=30,
            value=3,
            step=1,
            key="missing_remarks_num_days"
        )

    # Trigger report generation and persist state
    if st.button("Generate Missing Remarks Report", key="btn_missing_remarks"):
        target_date_str = selected_date.strftime("%Y-%m-%d")

        with st.spinner(f"Auditing remarks prior to {target_date_str} for {num_days} working day(s)..."):
            reports = get_missing_remarks_report(
                target_date_str=target_date_str, 
                num_days=int(num_days)
            )

            df_ch = reports.get("CH", pd.DataFrame())
            df_ho = reports.get("HO", pd.DataFrame())

            # Generate multi-sheet Excel workbook
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                df_ch.to_excel(writer, sheet_name="CH Pending", index=False)
                df_ho.to_excel(writer, sheet_name="HO Pending", index=False)

            IST = pytz.timezone('Asia/Kolkata')
            file_timestamp = datetime.now(IST).strftime('%Y%m%d_%H%M')
            filename = f"missing_remarks_report_{target_date_str}_{file_timestamp}.xlsx"

            # Save results into session state so they survive app reruns (downloads, interactions)
            st.session_state["missing_remarks_data"] = {
                "df_ch": df_ch,
                "df_ho": df_ho,
                "excel_bytes": excel_buffer.getvalue(),
                "filename": filename,
                "target_date_str": target_date_str
            }

    # ── Display Audit Results (Persisted via Session State) ──────────
    if "missing_remarks_data" in st.session_state:
        audit_data = st.session_state["missing_remarks_data"]
        df_ch = audit_data["df_ch"]
        df_ho = audit_data["df_ho"]
        total_records = len(df_ch) + len(df_ho)

        if total_records == 0:
            st.info("ℹ️ No eligible pending call remarks found for the selected criteria!")
        else:
            st.success(f"✅ Found {len(df_ch)} CH record(s) and {len(df_ho)} HO record(s) missing remarks.")

            st.download_button(
                label="⬇️ Download Missing Remarks Excel (CH & HO Sheets)",
                data=audit_data["excel_bytes"],
                file_name=audit_data["filename"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_missing_remarks"
            )

            # ── Summary Metrics & Tables ──────────────────────────────
            st.markdown("---")
            st.subheader("📊 Summary Breakdowns")

            col_ch, col_ho = st.columns(2)

            # 1. CH Circle-wise Summary
            with col_ch:
                st.markdown("### 🏢 CH Missing Remarks (Circle-wise)")
                circle_col = next((c for c in ['circle', 'circle_name', 'Circle', 'Circle Name'] if c in df_ch.columns), None)

                if not df_ch.empty and circle_col and 'service_id' in df_ch.columns:
                    summary_ch = (
                        df_ch.groupby(circle_col)['service_id']
                        .nunique()
                        .reset_index(name="Pending Calls Count")
                        .sort_values(by="Pending Calls Count", ascending=False)
                    )
                    total_row = pd.DataFrame({f"{circle_col}": ["Total"], "Pending Calls Count": [summary_ch["Pending Calls Count"].sum()]})
                    summary_ch = pd.concat([summary_ch,total_row], ignore_index= True)
                    st.dataframe(summary_ch, use_container_width=True, hide_index=True)
                elif df_ch.empty:
                    st.caption("No CH records pending.")
                else:
                    st.warning("Required columns (`circle` or `service_id`) missing in CH dataset.")

            # 2. HO CCO-wise Summary
            with col_ho:
                st.markdown("### 👤 HO Missing Remarks (CCO-wise)")
                cco_col = next((c for c in ['cco_name', 'cco', 'CCO Name', 'CCO'] if c in df_ho.columns), None)

                if not df_ho.empty and cco_col and 'service_id' in df_ho.columns:
                    summary_ho = (
                        df_ho.groupby(cco_col)['service_id']
                        .nunique()
                        .reset_index(name="Pending Calls Count")
                        .sort_values(by="Pending Calls Count", ascending=False)
                    )
                    toral_row_ho = pd.DataFrame({f"{cco_col}" : ["Total"], "Pending Calls Count": [summary_ho["Pending Calls Count"].sum()]})
                    summary_ho = pd.concat([summary_ho,toral_row_ho], ignore_index = True)

                    st.dataframe(summary_ho, use_container_width=True, hide_index=True)
                elif df_ho.empty:
                    st.caption("No HO records pending.")
                else:
                    st.warning("Required columns (`cco_name` or `service_id`) missing in HO dataset.")

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
        # region_filter = None,       # HO sees all rows
        region_filter = get_ch_regions(),       # HO sees all rows
    )

# ── CH Dashboard (both roles can view) ────────────────────
#
#   CH  → allow_remark=True,  region_filter = their assigned circles
#   HO  → allow_remark=False, region_filter = None (sees all rows, read-only)

elif page == "ch_dashboard":
    # To fetch the user information
    user_info_caption()
    # To render the dashboard on the page
    render_dashboard(
        sheet_name    = "CH Raw Data",
        title         = "📊 CH Dashboard",
        allow_remark  = is_ch,
        region_filter = get_ch_regions(),   # None for HO, list for CH
    )
