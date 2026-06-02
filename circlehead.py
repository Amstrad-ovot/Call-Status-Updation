import io
import time
import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from main import connect_gsheet, show_popup


# ── Cache TTL ─────────────────────────────────────────────

CACHE_TTL_SECONDS = 60
ROWS_PER_PAGE     = 10


# ── Styling ───────────────────────────────────────────────

def inject_table_styles():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght=300;400;500;600&family=DM+Mono:wght=400;500&display=swap');

    [data-testid="stAppViewContainer"], .main {
        font-family: 'DM Sans', sans-serif;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e3a5f 0%, #16304f 100%);
        border: 1px solid rgba(99,179,237,0.18);
        border-radius: 14px;
        padding: 18px 22px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.18);
    }
    [data-testid="stMetricLabel"] {
        color: #7f9fbf !important;
        font-size: 11px !important;
        letter-spacing: 1.2px;
        text-transform: uppercase;
        font-weight: 600;
    }
    [data-testid="stMetricValue"] {
        color: #e8f4ff !important;
        font-size: 28px !important;
        font-weight: 700 !important;
        font-family: 'DM Mono', monospace !important;
    }

    .tbl-wrapper {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(99,179,237,0.15);
        border-radius: 12px;
        overflow-x: auto !important;
        overflow-y: hidden !important;
        box-shadow: 0 4px 30px rgba(0,0,0,0.25);
        margin-top: 8px;
        padding-bottom: 12px;
        width: 100% !important;
        display: block !important;
    }
    .tbl-content-container {
        padding: 0 8px;
        width: max-content !important;
        display: block !important;
    }
    .tbl-content-container div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        width: max-content !important;
        gap: 0 !important;
        padding: 0 !important;
    }
    .tbl-content-container div[data-testid="column"] {
        width: max-content !important;
        min-width: 180px !important;
        flex: 1 0 auto !important;
        padding: 0 16px !important;
        box-sizing: border-box !important;
    }
    .tbl-content-container div[data-testid="column"]:first-child {
        min-width: 70px !important;
        max-width: 70px !important;
    }

    .tbl-cell       { color:#000000; font-size:13px; white-space:nowrap !important; text-align:left; }
    .tbl-cell-mono  { font-family:'DM Mono',monospace; font-size:12px; color:#000000; white-space:nowrap !important; text-align:left; }
    .tbl-cell-num   { font-family:'DM Mono',monospace; font-size:12px; color:#4a6a8a; white-space:nowrap !important; text-align:left; }
    .tbl-cell-empty { color:rgba(255,255,255,0.18); font-size:12px; }

    .tbl-badge-remark {
        background:rgba(129,199,132,0.15); border:1px solid rgba(129,199,132,0.3);
        border-radius:6px; padding:2px 8px; color:#81c784; font-size:11px;
        display:inline-block; white-space:nowrap !important;
    }
    .tbl-badge-empty {
        background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1);
        border-radius:6px; padding:2px 8px; color:rgba(255,255,255,0.2);
        font-size:11px; display:inline-block;
    }

    .sid-btn > div[data-testid="stButton"] > button {
        background:transparent !important; border:none !important;
        color:#63b3ed !important; font-family:'DM Mono',monospace !important;
        font-size:12px !important; font-weight:500 !important;
        padding:0 !important; margin:0 !important; text-align:left !important;
        width:auto !important; box-shadow:none !important;
        text-decoration:underline; text-underline-offset:3px;
    }
    .sid-btn > div[data-testid="stButton"] > button:hover {
        color:#90cdf4 !important; background:transparent !important;
        border:none !important; box-shadow:none !important;
    }

    .sid-readonly { font-family:'DM Mono',monospace; font-size:12px; color:#7f9fbf; padding:4px 0; cursor:default; }

    .ro-banner {
        background:rgba(255,193,7,0.10); border:1px solid rgba(255,193,7,0.28);
        border-radius:8px; padding:7px 14px; color:#ffc107;
        font-size:12px; display:inline-block; margin-bottom:10px;
    }

    /* ── NEW: region info banner shown to CH users ── */
    .region-banner {
        background: rgba(99,179,237,0.08);
        border: 1px solid rgba(99,179,237,0.25);
        border-radius: 8px;
        padding: 7px 14px;
        color: #63b3ed;
        font-size: 12px;
        display: inline-block;
        margin-bottom: 10px;
    }

    [data-testid="stTextInput"] input {
        background:rgba(255,255,255,0.05) !important; border:1px solid rgba(99,179,237,0.2) !important;
        border-radius:10px !important; color:#000000 !important; font-family:'DM Sans',sans-serif !important;
    }
    [data-testid="stTextInput"] input:focus {
        border-color:#000000 !important; box-shadow:0 0 0 3px rgba(99,179,237,0.12) !important;
    }
    [data-testid="stDialog"] {
        background:#0f2035 !important; border:1px solid rgba(99,179,237,0.2) !important;
        border-radius:16px !important;
    }

    .tbl-wrapper::-webkit-scrollbar { height:8px; }
    .tbl-wrapper::-webkit-scrollbar-track { background:rgba(255,255,255,0.02); border-radius:4px; }
    .tbl-wrapper::-webkit-scrollbar-thumb { background:rgba(99,179,237,0.3); border-radius:4px; }
    .tbl-wrapper::-webkit-scrollbar-thumb:hover { background:rgba(99,179,237,0.5); }
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


# ── Cache Controls ────────────────────────────────────────

def render_cache_controls(sheet_name: str):
    time_key = f"cache_time_{sheet_name}"
    col_info, col_btn = st.columns([5, 1])
    with col_info:
        if time_key in st.session_state:
            age = int(time.time() - st.session_state[time_key])
            st.caption(f"⏱ Data cached {age}s ago · auto-refreshes every {CACHE_TTL_SECONDS}s")
    with col_btn:
        if st.button("🔄 Refresh", key=f"refresh_{sheet_name}", use_container_width=True):
            invalidate_cache(sheet_name)
            st.rerun()


# ── Remark Dialog (only opened by CH role) ────────────────

@st.dialog("📝 Update Remark", width="large")
def remark_dialog(
    ws,
    row_index: int,
    service_id: str,
    existing_remark: str,
    remark_col: str,
    col_idx,
    sheet_name: str,
    headers: list,
    pending_key: str,
):
    st.markdown(f"**Service ID:** `{service_id}`")
    st.markdown(
        f"<span style='color:#7f9fbf;font-size:12px;'>Remark column: "
        f"<code style='color:#63b3ed'>{remark_col}</code></span>",
        unsafe_allow_html=True,
    )
    st.divider()

    if existing_remark:
        st.info(f"📌 Existing remark: **{existing_remark}**")
        overwrite = st.checkbox("✏️ Overwrite existing remark")
    else:
        overwrite = True

    new_remark = st.text_area(
        "Remark", placeholder="Type your remark here…",
        height=120, label_visibility="collapsed",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save Remark", use_container_width=True, type="primary"):
            if not new_remark.strip():
                st.warning("Remark cannot be empty.")
            elif existing_remark and not overwrite:
                st.warning("Check the overwrite box to update.")
            else:
                _save_remark(
                    ws, row_index, remark_col, col_idx,
                    new_remark.strip(), sheet_name, headers,
                )
                st.session_state.pop(pending_key, None)
                st.rerun()
    with c2:
        if st.button("✖ Cancel", use_container_width=True):
            st.session_state.pop(pending_key, None)
            st.rerun()


def _save_remark(ws, row_index, remark_col, col_idx, remark_text, sheet_name, headers):
    if col_idx is None:
        col_idx = len(headers) + 1
        ws.update_cell(1, col_idx, remark_col)
        headers_key = f"cache_headers_{sheet_name}"
        if headers_key in st.session_state:
            st.session_state[headers_key].append(remark_col)

    ws.update_cell(row_index, col_idx, remark_text)

    cache_key = f"cache_df_{sheet_name}"
    if cache_key in st.session_state:
        df = st.session_state[cache_key]
        if remark_col not in df.columns:
            df[remark_col] = ""
        df.at[row_index - 2, remark_col] = remark_text
        st.session_state[cache_key] = df

    show_popup(f"Remark saved in '{remark_col}'", type="success")


# ── Pagination ────────────────────────────────────────────

def get_page_key(sheet_name: str) -> str:
    return f"page_num_{sheet_name}"


def render_pagination(sheet_name: str, total_rows: int, position: str = "top") -> tuple[int, int]:
    page_key = get_page_key(sheet_name)
    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    total_pages = max(1, (total_rows + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE)
    if st.session_state[page_key] > total_pages:
        st.session_state[page_key] = total_pages

    current_page = st.session_state[page_key]
    sfx = f"{sheet_name}_{position}"

    col_prev, col_info, col_next, col_jump = st.columns([1, 2, 1, 2])
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


# ── Dynamic Configuration Array Generation ─────────────────

FIXED_COLS = ["service_id", "customer_name", "circle", "call_date", "age_from_call_reg"]

def get_col_names_list(df: pd.DataFrame, all_remark_cols: list) -> list:
    fixed = [c for c in FIXED_COLS if c in df.columns]
    return ["_row_num"] + fixed + all_remark_cols


# ── Excel Export Generation Helper ────────────────────────

def convert_df_to_excel(df_to_download: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    clean_df = df_to_download.copy()
    if "index" in clean_df.columns:
        clean_df = clean_df.drop(columns=["index"])
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        clean_df.to_excel(writer, index=False, sheet_name='Call Status Data')
    return output.getvalue()


# ── Main renderer ─────────────────────────────────────────

# ── CHANGE 1: added `region_filter` parameter ─────────────
#
#   region_filter = None        → HO: no restriction, show all rows
#   region_filter = ["Rajkot"]  → CH: show only rows where the 'circle'
#                                    column matches one of these values
#                                    (case-insensitive)
#   region_filter = []          → CH with no regions assigned: show nothing

def render_dashboard(
    sheet_name: str,
    title: str,
    allow_remark: bool = True,
    region_filter: list[str] | None = None,   # ← NEW
):
    inject_table_styles()
    st.header(title)

    if not allow_remark:
        st.markdown(
            "<div class='ro-banner'>👁️ View-only &nbsp;·&nbsp; You can view CH data but cannot add or edit remarks.</div>",
            unsafe_allow_html=True,
        )

    spreadsheet = connect_gsheet()
    if not spreadsheet:
        st.error("Could not connect to Google Sheets.")
        return

    df, ws, headers = fetch_sheet_data(spreadsheet, sheet_name)
    if df is None or df.empty:
        st.info("No data available in this sheet yet.")
        return

    # ── CHANGE 2: apply region filter right after data load ──
    #
    # This runs before pending-dialog, metrics, search, pagination —
    # so everything downstream (counts, dropdowns, downloads) reflects
    # only the CH user's own circles. No other logic is touched.
    if region_filter is not None:
        if len(region_filter) == 0:
            # CH user exists but has no regions assigned
            st.warning("⚠️ No regions are assigned to your account. Please contact your administrator.")
            return

        if "circle" not in df.columns:
            st.error("Column 'circle' not found in the sheet. Cannot apply region filter.")
            return

        # Case-insensitive match against the 'circle' column
        allowed_lower = [r.lower() for r in region_filter]
        df = df[
            df["circle"].astype(str).str.strip().str.lower().isin(allowed_lower)
        ].reset_index(drop=True)

        if df.empty:
            st.info("No records found for your assigned regions.")
            return

        # Show CH user which regions they are seeing
        st.markdown(
            f"<div class='region-banner'>📍 Showing data for your regions: "
            f"<strong>{', '.join(region_filter)}</strong></div>",
            unsafe_allow_html=True,
        )

    # ── Everything below is UNCHANGED from your original code ──

    # Handle context pagination index lock
    pending_key = f"pending_remark_{sheet_name}"
    if pending_key in st.session_state:
        st.session_state[get_page_key(sheet_name)] = st.session_state[pending_key]["page"]

    today_str = datetime.now().strftime("%Y-%m-%d")
    remark_col = f"remark_{today_str}"
    remark_col_idx = (headers.index(remark_col) + 1) if remark_col in headers else None

    if pending_key in st.session_state:
        p = st.session_state[pending_key]
        remark_dialog(
            ws=ws,
            row_index=p["sheet_row"],
            service_id=p["sid_val"],
            existing_remark=p["existing_remark"],
            remark_col=remark_col,
            col_idx=remark_col_idx,
            sheet_name=sheet_name,
            headers=headers,
            pending_key=pending_key,
        )

    render_cache_controls(sheet_name)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Records", len(df))
    if "7+_calls" in df.columns:
        m2.metric("7+ Day Calls", int(df["7+_calls"].astype(str).eq("1").sum()))
    if "15+_calls" in df.columns:
        m3.metric("15+ Day Calls", int(df["15+_calls"].astype(str).eq("1").sum()))

    st.divider()

    search_backing_key = f"search_val_{sheet_name}"
    circle_backing_key = f"circle_val_{sheet_name}"

    if search_backing_key not in st.session_state:
        st.session_state[search_backing_key] = ""
    if circle_backing_key not in st.session_state:
        st.session_state[circle_backing_key] = "All"

    col_search, col_circle, col_reset = st.columns([3, 2, 1])

    with col_search:
        st.text_input(
            "🔍 Search Service ID / Customer",
            value=st.session_state[search_backing_key],
            key=f"search_{sheet_name}",
            on_change=lambda: st.session_state.update({
                search_backing_key: st.session_state[f"search_{sheet_name}"],
                get_page_key(sheet_name): 1,
            }),
        )

    with col_circle:
        if "circle" in df.columns:
            unique_circles = ["All"] + sorted(df["circle"].dropna().unique().tolist())
        else:
            unique_circles = ["All"]

        try:
            default_circle_idx = unique_circles.index(st.session_state[circle_backing_key])
        except ValueError:
            default_circle_idx = 0

        st.selectbox(
            "📍 Filter by Circle",
            options=unique_circles,
            index=default_circle_idx,
            key=f"circle_select_{sheet_name}",
            on_change=lambda: st.session_state.update({
                circle_backing_key: st.session_state[f"circle_select_{sheet_name}"],
                get_page_key(sheet_name): 1,
            }),
        )

    with col_reset:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        if st.button("✕ Clear", key=f"clear_{sheet_name}", use_container_width=True):
            st.session_state[search_backing_key] = ""
            st.session_state[circle_backing_key] = "All"
            st.session_state[get_page_key(sheet_name)] = 1
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    search = st.session_state[search_backing_key]
    selected_circle = st.session_state[circle_backing_key]

    df_filtered = df.copy().reset_index(drop=False)

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

    col_download_lbl, col_download_btn = st.columns([4, 2])
    with col_download_btn:
        excel_data = convert_df_to_excel(df_filtered)
        st.download_button(
            label="📥 Download Filtered Data (Excel)",
            data=excel_data,
            file_name=f"Call_Status_{sheet_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    all_remark_cols = sorted(
        [c for c in df.columns if c.startswith("remark_")],
        key=lambda x: x.replace("remark_", ""),
    )

    col_names = get_col_names_list(df, all_remark_cols)

    start, end = render_pagination(sheet_name, len(df_filtered), position="top")
    df_page    = df_filtered.iloc[start:end]

    hint = " · Click a Service ID to add/edit today's remark" if allow_remark else ""
    st.caption(
        f"Showing rows {start + 1}–{end} of {len(df_filtered)}"
        + (f" (filtered from {len(df)} total)" if (search or selected_circle != "All") else "")
        + hint
    )

    st.markdown('<div class="tbl-wrapper"><div class="tbl-content-container">', unsafe_allow_html=True)

    header_labels = {
        "_row_num":          "Sr. No.",
        "service_id":        "🖊 Service ID" if allow_remark else "Service ID",
        "customer_name":     "Customer Name",
        "circle":            "Circle",
        "call_date":         "Call Date",
        "age_from_call_reg": "Call Age",
    }

    h_cols = st.columns([1] * len(col_names))
    for i, col_name in enumerate(col_names):
        label = header_labels.get(col_name, col_name.replace("remark_", "Remark "))
        h_cols[i].markdown(
            f"<div style='color:#000000;font-size:11px;font-weight:600;"
            f"text-transform:uppercase;"
            f"padding:8px 0 0 0;border-bottom:2px solid #000000;'>"
            f"{label}</div>",
            unsafe_allow_html=True,
        )

    for row_pos, (_, row) in enumerate(df_page.iterrows()):
        orig_idx   = int(row["index"])
        global_row = start + row_pos + 1

        bg = "rgba(99,179,237,0.03)" if row_pos % 2 == 0 else "transparent"
        st.markdown(
            f"<div style='border-bottom:1px solid rgba(255,255,255,0.05);background:{bg};'></div>",
            unsafe_allow_html=True,
        )

        row_cols = st.columns([1] * len(col_names))

        for i, col_name in enumerate(col_names):
            if col_name == "_row_num":
                row_cols[i].markdown(
                    f"<div class='tbl-cell-num' style='padding:10px 0'>{global_row}</div>",
                    unsafe_allow_html=True,
                )

            elif col_name == "service_id":
                sid_val = str(row.get("service_id", ""))
                if allow_remark:
                    with row_cols[i]:
                        st.markdown("<div class='sid-btn' style='padding:5px 0'>", unsafe_allow_html=True)
                        if st.button(
                            sid_val,
                            key=f"sid_{sheet_name}_{orig_idx}",
                            help="Click to add/edit today's remark",
                            use_container_width=False,
                        ):
                            existing_remark = ""
                            if remark_col in df.columns:
                                existing_remark = str(df.at[orig_idx, remark_col]).strip()
                                existing_remark = (
                                    "" if existing_remark in ("", "nan") else existing_remark
                                )
                            current_page = st.session_state.get(get_page_key(sheet_name), 1)
                            st.session_state[pending_key] = {
                                "orig_idx":        orig_idx,
                                "sheet_row":       orig_idx + 2,
                                "sid_val":         sid_val,
                                "existing_remark": existing_remark,
                                "page":            current_page,
                            }
                            st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    row_cols[i].markdown(
                        f"<div class='sid-readonly'>{sid_val}</div>",
                        unsafe_allow_html=True,
                    )

            elif col_name in all_remark_cols:
                val = str(row.get(col_name, "")) if pd.notna(row.get(col_name, "")) else ""
                val = "" if val == "nan" else val
                badge = f'<span class="tbl-badge-remark">{val}</span>' if val else '<span class="tbl-badge-empty">—</span>'
                row_cols[i].markdown(
                    f"<div style='padding:8px 0'>{badge}</div>",
                    unsafe_allow_html=True,
                )

            elif col_name == "call_date":
                val = str(row.get(col_name, "")) if pd.notna(row.get(col_name, "")) else ""
                val = "" if val == "nan" else val
                row_cols[i].markdown(
                    f"<div class='tbl-cell-mono' style='padding:10px 0'>{val or '<span class=\"tbl-cell-empty\">—</span>'}</div>",
                    unsafe_allow_html=True,
                )

            else:
                val = str(row.get(col_name, "")) if pd.notna(row.get(col_name, "")) else ""
                val = "" if val == "nan" else val
                row_cols[i].markdown(
                    f"<div class='tbl-cell' style='padding:10px 0'>{val or '<span class=\"tbl-cell-empty\">—</span>'}</div>",
                    unsafe_allow_html=True,
                )

    st.markdown('</div></div>', unsafe_allow_html=True)

    st.caption(f"💡 Column **{remark_col}** stores today's remarks · New column created daily automatically")