import io
import time
import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from main import connect_gsheet, show_popup
import pytz

# ── Cache TTL ─────────────────────────────────────────────

CACHE_TTL_SECONDS = 60
ROWS_PER_PAGE     = 10

FIXED_COLS = ["service_id", "customer_name", "circle", "call_date", "age_from_call_reg"]

HEADER_LABELS = {
    "service_id":        "Service ID",
    "customer_name":     "Customer Name",
    "circle":            "Circle",
    "call_date":         "Call Date",
    "age_from_call_reg": "Call Age",
}

IST = pytz.timezone('Asia/Kolkata')

# ── Styling ───────────────────────────────────────────────

def inject_table_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

    [data-testid="stAppViewContainer"], .main { font-family: 'DM Sans', sans-serif; }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e3a5f 0%, #16304f 100%);
        border: 1px solid rgba(99,179,237,0.18);
        border-radius: 14px;
        padding: 18px 22px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.18);
    }
    [data-testid="stMetricLabel"] {
        color: #7f9fbf !important; font-size: 11px !important;
        letter-spacing: 1.2px; text-transform: uppercase; font-weight: 600;
    }
    [data-testid="stMetricValue"] {
        color: #e8f4ff !important; font-size: 28px !important;
        font-weight: 700 !important; font-family: 'DM Mono', monospace !important;
    }

    .ro-banner {
        background:rgba(255,193,7,0.10); border:1px solid rgba(255,193,7,0.28);
        border-radius:8px; padding:7px 14px; color:#ffc107; font-size:12px;
        display:inline-block; margin-bottom:10px;
    }
    .region-banner {
        background:rgba(99,179,237,0.08); border:1px solid rgba(99,179,237,0.25);
        border-radius:8px; padding:7px 14px; color:#63b3ed; font-size:12px;
        display:inline-block; margin-bottom:10px;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Cached Data Fetching ───────────────────────────────────

def fetch_sheet_data(spreadsheet, sheet_name: str):
    cache_key   = f"cache_df_{sheet_name}"
    ws_key      = f"cache_ws_{sheet_name}"
    time_key    = f"cache_time_{sheet_name}"
    headers_key = f"cache_headers_{sheet_name}"

    now      = time.time()
    age      = now - st.session_state.get(time_key, 0)
    is_stale = cache_key not in st.session_state or age > CACHE_TTL_SECONDS

    if is_stale:
        try:
            ws         = spreadsheet.worksheet(sheet_name)
            all_values = ws.get_all_values()
            headers    = all_values[0] if all_values else []
            rows       = all_values[1:] if len(all_values) > 1 else []
            records    = [dict(zip(headers, row)) for row in rows]
            df         = pd.DataFrame(records)
            df["_sheet_row"] = range(2, len(df) + 2)

            st.session_state[cache_key]   = df
            st.session_state[ws_key]      = ws
            st.session_state[time_key]    = now
            st.session_state[headers_key] = headers

        except gspread.WorksheetNotFound:
            show_popup(f"Sheet '{sheet_name}' not found!", type="error")
            return pd.DataFrame(), None, []

    return (
        st.session_state[cache_key],
        st.session_state[ws_key],
        st.session_state.get(headers_key, []),
    )


def invalidate_cache(sheet_name: str):
    for suffix in ("cache_df", "cache_ws", "cache_time", "cache_headers"):
        st.session_state.pop(f"{suffix}_{sheet_name}", None)


def render_cache_controls(sheet_name: str):
    time_key = f"cache_time_{sheet_name}"
    col_info, col_btn = st.columns([5, 1])
    with col_info:
        if time_key in st.session_state:
            age = int(time.time() - st.session_state[time_key])
            st.caption(f"Data cached {age}s ago · auto-refreshes every {CACHE_TTL_SECONDS}s")
    with col_btn:
        if st.button("Refresh", key=f"refresh_{sheet_name}", use_container_width=True):
            invalidate_cache(sheet_name)
            st.rerun()


# ── Dual Remark Dialog Component ──────────────────────────

@st.dialog("Update Remarks", width="medium", dismissible=False)
def remark_dialog(ws, row_index, cache_row_idx, service_id,
                  sheet_name, headers, pending_key):
    
    # 1. Generate column labels for today's entry
    # today_str = datetime.now(IST).strftime("%d_%m_%Y")
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    cust_col  = f"cust_remark_{today_str}"
    asp_col   = f"asp_remark_{today_str}"
    
    # 2. Extract history safely directly from memory cache
    ck = f"cache_df_{sheet_name}"
    existing_cust = ""
    existing_asp  = ""
    
    if ck in st.session_state and cache_row_idx is not None:
        master_df = st.session_state[ck]
        if cust_col in master_df.columns:
            val_c = master_df.at[cache_row_idx, cust_col]
            existing_cust = "" if pd.isna(val_c) or str(val_c).strip() in ("", "nan") else str(val_c).strip()
        if asp_col in master_df.columns:
            val_a = master_df.at[cache_row_idx, asp_col]
            existing_asp = "" if pd.isna(val_a) or str(val_a).strip() in ("", "nan") else str(val_a).strip()

    st.markdown(f"**Service ID:** `{service_id}`")
    st.divider()

    # 3. Customer Input Section
    st.markdown("**💬 Customer Remark History**")
    if existing_cust:
        st.info(existing_cust)
    new_cust = st.text_area("Customer Remark Input", placeholder="Type customer remark here...", 
                            height=100, label_visibility="collapsed", key="dialog_cust_input")

    st.divider()

    # 4. ASP Input Section
    st.markdown("**🛠️ ASP Remark History**")
    if existing_asp:
        st.info(existing_asp)
    new_asp = st.text_area("ASP Remark Input", placeholder="Type ASP remark here...", 
                           height=100, label_visibility="collapsed", key="dialog_asp_input")

    # 5. Overwrite Checkbox
    if existing_cust or existing_asp:
        overwrite = st.checkbox("Append entries to existing history tracker", value=True)
    else:
        overwrite = True

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save Remarks", use_container_width=True, type="primary"):
            if not new_cust.strip() and not new_asp.strip():
                st.warning("Both remark entries cannot be empty.")
            elif (existing_cust or existing_asp) and not overwrite:
                st.warning("Please toggle the append validation checkbox.")
            else:
                uname = st.session_state.get("user_name", "UnknownUser")
                timestamp = datetime.now(IST).strftime("%H:%M:%S")
                
                # Update Customer Column
                if new_cust.strip():
                    payload_cust = f"{uname}_{timestamp} -- {new_cust.strip()}"
                    final_cust = f"{existing_cust}\n{payload_cust}" if (existing_cust and overwrite) else payload_cust
                    
                    c_idx = headers.index(cust_col) + 1 if cust_col in headers else None
                    _save_remark(ws=ws, row_index=row_index, remark_col=cust_col, col_idx=c_idx,
                                 remark_text=final_cust, sheet_name=sheet_name, headers=headers, cache_row_idx=cache_row_idx)

                # Update ASP Column
                if new_asp.strip():
                    payload_asp = f"{uname}_{timestamp} -- {new_asp.strip()}"
                    final_asp = f"{existing_asp}\n{payload_asp}" if (existing_asp and overwrite) else payload_asp
                    
                    a_idx = headers.index(asp_col) + 1 if asp_col in headers else None
                    _save_remark(ws=ws, row_index=row_index, remark_col=asp_col, col_idx=a_idx,
                                 remark_text=final_asp, sheet_name=sheet_name, headers=headers, cache_row_idx=cache_row_idx)

                st.session_state.pop(pending_key, None)
                st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop(pending_key, None)
            st.rerun()


def _save_remark(ws, row_index, remark_col, col_idx, remark_text,
                 sheet_name, headers, cache_row_idx=None):
    hk = f"cache_headers_{sheet_name}"
    current_headers = st.session_state.get(hk, headers)

    if col_idx is None or remark_col not in current_headers:
        col_idx = len(current_headers) + 1
        sheet_meta        = ws.spreadsheet.fetch_sheet_metadata()
        current_col_count = 0
        for s in sheet_meta["sheets"]:
            if s["properties"]["title"] == ws.title:
                current_col_count = s["properties"]["gridProperties"]["columnCount"]
                break
        if col_idx > current_col_count:
            ws.spreadsheet.batch_update({"requests": [{"updateSheetProperties": {
                "properties": {"sheetId": ws.id, "gridProperties": {"columnCount": col_idx + 10}},
                "fields": "gridProperties.columnCount"}}]})
        
        ws.update_cell(1, col_idx, remark_col)
        if hk in st.session_state:
            st.session_state[hk].append(remark_col)

    ws.update_cell(row_index, col_idx, remark_text)

    ck = f"cache_df_{sheet_name}"
    if ck in st.session_state and cache_row_idx is not None:
        master = st.session_state[ck]
        if remark_col not in master.columns:
            master[remark_col] = ""
        master.at[cache_row_idx, remark_col] = remark_text
        st.session_state[ck] = master

    show_popup(f"Saved to {remark_col}", type="success")


# ── Pagination ────────────────────────────────────────────

def get_page_key(sheet_name):
    return f"page_num_{sheet_name}"


def render_pagination(sheet_name, total_rows, position="top"):
    page_key = get_page_key(sheet_name)
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    total_pages = max(1, (total_rows + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages

    current_page = st.session_state[page_key]
    sfx = f"{sheet_name}_{position}"

    _, col_info, __, col_jump = st.columns([1, 2, 1, 2])
    with col_info:
        st.markdown(
            f"<div style='text-align:center;color:#7f9fbf;font-family:DM Mono,monospace;"
            f"font-size:13px;padding-top:6px;'>"
            f"Page <b style='color:#63b3ed'>{current_page}</b> of <b>{total_pages}</b>"
            f" &nbsp;·&nbsp; {total_rows} records</div>",
            unsafe_allow_html=True,
        )
    with col_jump:
        jump = st.number_input(
            "Go to page", min_value=1, max_value=total_pages,
            value=current_page, step=1,
            key=f"jump_{sfx}", label_visibility="collapsed",
        )
        if int(jump) != current_page:
            st.session_state[page_key] = int(jump)
            st.rerun()

    start = (current_page - 1) * ROWS_PER_PAGE
    end   = min(start + ROWS_PER_PAGE, total_rows)
    return start, end


# ── Excel Export ───────────────────────────────────────────

def convert_df_to_excel(df_to_download):
    output   = io.BytesIO()
    clean_df = df_to_download.copy()
    for c in ["index", "_sheet_row"]:
        if c in clean_df.columns:
            clean_df = clean_df.drop(columns=[c])
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        clean_df.to_excel(writer, index=False, sheet_name="Call Status Data")
    return output.getvalue()


# ── Main renderer ─────────────────────────────────────────

def render_dashboard(
    sheet_name: str,
    title: str,
    allow_remark: bool = True,
    region_filter: list[str] | None = None,
):
    inject_table_styles()
    st.header(title)

    if not allow_remark:
        st.markdown("<div class='ro-banner'>View-only · Cannot add or edit remarks.</div>", unsafe_allow_html=True)

    spreadsheet = connect_gsheet()
    if not spreadsheet:
        st.error("Could not connect to Google Sheets.")
        return

    master_df, ws, headers = fetch_sheet_data(spreadsheet, sheet_name)
    if master_df is None or master_df.empty:
        st.info("No data available in this sheet yet.")
        return

    # ── Region filter ─────────────────────────────────────
    if region_filter is not None:
        if len(region_filter) == 0:
            st.warning("No regions are assigned to your account.")
            return
        if "circle" not in master_df.columns:
            st.error("Column 'circle' not found.")
            return
        allowed_lower = [r.lower() for r in region_filter]
        df_view = master_df[
            master_df["circle"].astype(str).str.strip().str.lower().isin(allowed_lower)
        ]
        if df_view.empty:
            st.info("No records found for your assigned regions.")
            return
        st.markdown(
            f"<div class='region-banner'>Showing data for: "
            f"<strong>{', '.join(region_filter)}</strong></div>",
            unsafe_allow_html=True,
        )
    else:
        df_view = master_df

    pending_key = f"pending_remark_{sheet_name}"

    # ── Process dynamic popup triggers safely via standard session_state ──
    if pending_key in st.session_state:
        p = st.session_state[pending_key]
        if "cache_row_idx" not in p or "sheet_row" not in p:
            st.session_state.pop(pending_key, None)
            st.rerun()
        remark_dialog(
            ws=ws, row_index=p["sheet_row"], cache_row_idx=p["cache_row_idx"],
            service_id=p["sid_val"], sheet_name=sheet_name, headers=headers, pending_key=pending_key,
        )

    render_cache_controls(sheet_name)

    # ── Metrics ───────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Records", len(df_view))
    if "7+_calls" in df_view.columns:
        m2.metric("7+ Day Calls", int(df_view["7+_calls"].astype(str).eq("1").sum()))
    if "15+_calls" in df_view.columns:
        m3.metric("15+ Day Calls", int(df_view["15+_calls"].astype(str).eq("1").sum()))

    st.divider()

    # ── Search & filter controls ──────────────────────────
    search_backing_key = f"search_val_{sheet_name}"
    circle_backing_key = f"circle_val_{sheet_name}"

    if search_backing_key not in st.session_state:
        st.session_state[search_backing_key] = ""
    if circle_backing_key not in st.session_state:
        st.session_state[circle_backing_key] = "All"

    col_search, col_circle, col_reset = st.columns([3, 2, 1])
    with col_search:
        st.text_input(
            "Search Service ID / Customer",
            value=st.session_state[search_backing_key],
            key=f"search_{sheet_name}",
            on_change=lambda: st.session_state.update({
                search_backing_key: st.session_state.get(f"search_{sheet_name}", ""),
                get_page_key(sheet_name): 1,
            }),
        )
    with col_circle:
        unique_circles = (["All"] + sorted(df_view["circle"].dropna().unique().tolist())
                          if "circle" in df_view.columns else ["All"])
        try:
            default_idx = unique_circles.index(st.session_state[circle_backing_key])
        except ValueError:
            default_idx = 0
        st.selectbox(
            "Filter by Circle", options=unique_circles, index=default_idx,
            key=f"circle_select_{sheet_name}",
            on_change=lambda: st.session_state.update({
                circle_backing_key: st.session_state.get(f"circle_select_{sheet_name}", "All"),
                get_page_key(sheet_name): 1,
            }),
        )
    with col_reset:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        if st.button("Clear", key=f"clear_{sheet_name}", use_container_width=True):
            st.session_state[search_backing_key] = ""
            st.session_state[circle_backing_key] = "All"
            st.session_state[get_page_key(sheet_name)] = 1
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    search          = st.session_state[search_backing_key]
    selected_circle = st.session_state[circle_backing_key]

    # ── Build df_filtered ─────────────────────────────────
    df_filtered = df_view.reset_index(drop=False)
    if search:
        mask = (
            df_filtered["service_id"].astype(str).str.contains(search, case=False, na=False)
            | df_filtered["customer_name"].astype(str).str.contains(search, case=False, na=False)
        )
        df_filtered = df_filtered[mask]
    if selected_circle != "All" and "circle" in df_filtered.columns:
        df_filtered = df_filtered[df_filtered["circle"].astype(str) == selected_circle]
    df_filtered = df_filtered.reset_index(drop=True)

    if df_filtered.empty:
        st.warning("No matching records found for the combined filters.")
        return

    # ── Download ──────────────────────────────────────────
    _, col_dl = st.columns([4, 2])
    with col_dl:
        excel_data = convert_df_to_excel(df_filtered)
        st.download_button(
            label="Download Filtered Data (Excel)", data=excel_data,
            file_name=f"Call_Status_{sheet_name}_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # ── Parse historical remark columns sequentially ──
    all_remark_cols = sorted(
        [c for c in master_df.columns if c.startswith("cust_remark_") or c.startswith("asp_remark_")],
        key=lambda x: x.split("_")[-1] + x.split("_")[-2] + x.split("_")[-3] if len(x.split("_")) >= 4 else x
    )

    start, end = render_pagination(sheet_name, len(df_filtered), position="top")
    df_page = df_filtered.iloc[start:end].copy()

    hint = " · Click a row anywhere to add/edit customer or ASP remarks" if allow_remark else ""
    st.caption(
        f"Showing rows {start + 1}–{end} of {len(df_filtered)}"
        + (f" (filtered from {len(df_view)} total)" if (search or selected_circle != "All") else "")
        + hint
    )

    # ── Native Table Rendering Framework ──────────────────
    columns_order = FIXED_COLS + all_remark_cols

    for col in all_remark_cols:
        if col in df_page.columns:
            df_page[col] = df_page[col].fillna("-").replace("nan", "-")

    column_config = {
        "service_id": st.column_config.TextColumn("Service ID 📌", width="None", pinned=True),
        "customer_name": st.column_config.TextColumn("Customer Name", width="None"),
        "circle": st.column_config.TextColumn("Circle", width="None"),
        "call_date": st.column_config.TextColumn("Call Date", width="None"),
        "age_from_call_reg": st.column_config.TextColumn("Call Age", width="None"),
    }

    for col in all_remark_cols:
        clean_lbl = col.replace("cust_remark_", "Cust Remark ").replace("asp_remark_", "ASP Remark ")
        column_config[col] = st.column_config.TextColumn(clean_lbl, width="Medium")

    popup_state_suffix = "active" if pending_key in st.session_state else "cleared"

    event = st.dataframe(
        df_page[columns_order],
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"data_table_{sheet_name}_{popup_state_suffix}"
    )

    # ── Row Click Trigger Interception Logic ────────────────
    if allow_remark and event and event.get("selection", {}).get("rows"):
        selected_row_idx = event["selection"]["rows"][0]
        clicked_row = df_page.iloc[selected_row_idx]
        
        target_sheet_row = int(clicked_row["_sheet_row"])
        cache_row_idx = int(clicked_row["index"])
        sid_val = str(clicked_row.get("service_id", ""))

        if pending_key not in st.session_state:
            st.session_state[pending_key] = {
                "cache_row_idx": cache_row_idx,
                "sheet_row":     target_sheet_row,
                "sid_val":       sid_val,
                "page":          st.session_state.get(get_page_key(sheet_name), 1),
            }
            st.rerun()

    st.caption("Remarks are separated by category and cataloged daily by date structural headers.")
