import io
import time
import re
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from main import connect_gsheet, show_popup
import pytz

# ── Cache TTL ─────────────────────────────────────────────

CACHE_TTL_SECONDS = 60
ROWS_PER_PAGE     = 10

FIXED_COLS = ["service_id", "customer_name", "circle", "call_date", "status_code", "status_updated_date", "age_from_call_reg"]

HEADER_LABELS = {
    "service_id":        "Service ID",
    "customer_name":     "Customer Name",
    "circle":            "Circle",
    "call_date":         "Call Date",
    "age_from_call_reg": "Call Age",
    "status_code":       "Status Code",
    "status_updated_date": "Status Updated Date",
    "call_category":     "Call Category",
    "cco_name" : "CCO Name"
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


# ── Dynamic Remark Highlighting Helper ───────────────────────

def highlight_eligible_remarks(df: pd.DataFrame, is_ch_sheet: bool) -> pd.DataFrame:
    style_df = pd.DataFrame("", index=df.index, columns=df.columns)
    
    remark_cols = [c for c in df.columns if re.match(r"^remark_(cust|asp|internalteam)_\d{4}-\d{2}-\d{2}$", c)]
    col_dates = {}
    for col in remark_cols:
        try:
            date_part = col.split("_")[-1]
            col_dates[col] = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue

    highlight_style = "background-color: #AFEEEE; color: #000000; font-weight: 600;"

    for idx, row in df.iterrows():
        raw_call_date = row.get("call_date")
        if pd.isna(raw_call_date) or not str(raw_call_date).strip():
            continue

        try:
            c_date_str = str(raw_call_date).strip()
            if " " in c_date_str:
                c_date_str = c_date_str.split(" ")[0]
            
            if "-" in c_date_str:
                parts = c_date_str.split("-")
                if len(parts[0]) == 4:
                    c_date = datetime.strptime(c_date_str, "%Y-%m-%d").date()
                else:
                    c_date = datetime.strptime(c_date_str, "%d-%m-%Y").date()
            elif "/" in c_date_str:
                parts = c_date_str.split("/")
                if len(parts[0]) == 4:
                    c_date = datetime.strptime(c_date_str, "%Y/%m/%d").date()
                else:
                    c_date = datetime.strptime(c_date_str, "%d/%m/%Y").date()
            else:
                continue
        except Exception:
            continue

        if is_ch_sheet:
            start_eligible = c_date + timedelta(days=8)
            end_eligible = c_date + timedelta(days=14)
        else:
            start_eligible = c_date + timedelta(days=15)
            end_eligible = datetime.max.date()

        for col, col_dt in col_dates.items():
            if start_eligible <= col_dt <= end_eligible:
                style_df.at[idx, col] = highlight_style

    return style_df


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


# ── Tri-Remark Dialog Component ──────────────────────────

@st.dialog("Update Remarks", width="medium", dismissible=False)
def remark_dialog(ws, service_id, sheet_name, headers, pending_key):
    
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    cust_col  = f"remark_cust_{today_str}"
    asp_col   = f"remark_asp_{today_str}"
    int_col   = f"remark_internalteam_{today_str}"
    
    ck = f"cache_df_{sheet_name}"
    existing_cust = ""
    existing_asp  = ""
    existing_int  = ""
    
    is_ch_sheet = "ch" in sheet_name.lower()
    
    if ck in st.session_state:
        master_df = st.session_state[ck]
        # Locate the specific row by service_id
        target_rows = master_df[master_df["service_id"].astype(str).str.strip() == str(service_id).strip()]
        
        if not target_rows.empty:
            cache_row = target_rows.iloc[0]
            if cust_col in master_df.columns:
                val_c = cache_row.get(cust_col)
                existing_cust = "" if pd.isna(val_c) or str(val_c).strip() in ("", "nan") else str(val_c).strip()
            if asp_col in master_df.columns:
                val_a = cache_row.get(asp_col)
                existing_asp = "" if pd.isna(val_a) or str(val_a).strip() in ("", "nan") else str(val_a).strip()
            if not is_ch_sheet and int_col in master_df.columns:
                val_i = cache_row.get(int_col)
                existing_int = "" if pd.isna(val_i) or str(val_i).strip() in ("", "nan") else str(val_i).strip()

    st.markdown(f"**Service ID:** `{service_id}`")
    st.divider()

    st.markdown("**💬 Customer Remark History**")
    if existing_cust:
        st.info(existing_cust)
    new_cust = st.text_area("Customer Remark Input", placeholder="Type customer remark here...", 
                            height=100, label_visibility="collapsed", key="dialog_cust_input")

    st.divider()

    st.markdown("**🛠️ ASP Remark History**")
    if existing_asp:
        st.info(existing_asp)
    new_asp = st.text_area("ASP Remark Input", placeholder="Type ASP remark here...", 
                           height=100, label_visibility="collapsed", key="dialog_asp_input")

    new_int = ""
    if not is_ch_sheet:
        st.divider()
        st.markdown("**👥 Internal Team Remark History**")
        if existing_int:
            st.info(existing_int)
        new_int = st.text_area("Internal Team Remark Input", placeholder="Type internal team remark here...", 
                               height=100, label_visibility="collapsed", key="dialog_int_input")

    if existing_cust or existing_asp or (not is_ch_sheet and existing_int):
        overwrite = st.checkbox("Append entries to existing history tracker", value=True)
    else:
        overwrite = True
     
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save Remarks", use_container_width=True, type="primary"):
            if not new_cust.strip() and not new_asp.strip() and (is_ch_sheet or not new_int.strip()):
                st.warning("All remark entries cannot be empty.")
            elif (existing_cust or existing_asp or (not is_ch_sheet and existing_int)) and not overwrite:
                st.warning("Please toggle the append validation checkbox.")
            else:
                uname = st.session_state.get("user_name", "UnknownUser")
                timestamp = datetime.now(IST).strftime("%H:%M:%S")
                
                if new_cust.strip():
                    payload_cust = f"{uname}_{timestamp} -- {new_cust.strip()}"
                    final_cust = f"{existing_cust}\n{payload_cust}" if (existing_cust and overwrite) else payload_cust
                    c_idx = headers.index(cust_col) + 1 if cust_col in headers else None
                    _save_remark(ws=ws, service_id=service_id, remark_col=cust_col, col_idx=c_idx,
                                 remark_text=final_cust, sheet_name=sheet_name, headers=headers)

                if new_asp.strip():
                    payload_asp = f"{uname}_{timestamp} -- {new_asp.strip()}"
                    final_asp = f"{existing_asp}\n{payload_asp}" if (existing_asp and overwrite) else payload_asp
                    a_idx = headers.index(asp_col) + 1 if asp_col in headers else None
                    _save_remark(ws=ws, service_id=service_id, remark_col=asp_col, col_idx=a_idx,
                                 remark_text=final_asp, sheet_name=sheet_name, headers=headers)

                if not is_ch_sheet and new_int.strip():
                    payload_int = f"{uname}_{timestamp} -- {new_int.strip()}"
                    final_int = f"{existing_int}\n{payload_int}" if (existing_int and overwrite) else payload_int
                    i_idx = headers.index(int_col) + 1 if int_col in headers else None
                    _save_remark(ws=ws, service_id=service_id, remark_col=int_col, col_idx=i_idx,
                                 remark_text=final_int, sheet_name=sheet_name, headers=headers)

                st.session_state.pop(pending_key, None)
                st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop(pending_key, None)
            st.rerun()


def _save_remark(ws, service_id, remark_col, col_idx, remark_text, sheet_name, headers):
    hk = f"cache_headers_{sheet_name}"
    current_headers = st.session_state.get(hk, headers)

    # 1. Locate column index dynamically if missing
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

    # 2. Dynamically locate the target row in Google Sheets by service_id
    try:
        # Find column number for service_id
        sid_col_idx = current_headers.index("service_id") + 1 if "service_id" in current_headers else 1
        cell = ws.find(str(service_id), in_column=sid_col_idx)
        
        if cell is None:
            show_popup(f"Error: Service ID '{service_id}' not found in sheet.", type="error")
            return
            
        target_sheet_row = cell.row
        print("Target sheet row is:", target_sheet_row)
        ws.update_cell(target_sheet_row, col_idx, remark_text)
    except Exception as e:
        show_popup(f"Failed to save remark: {str(e)}", type="error")
        return

    # 3. Update the session state DataFrame using service_id
    ck = f"cache_df_{sheet_name}"
    if ck in st.session_state:
        master = st.session_state[ck]
        if remark_col not in master.columns:
            master[remark_col] = ""
            
        mask = master["service_id"].astype(str).str.strip() == str(service_id).strip()
        master.loc[mask, remark_col] = remark_text
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
    for c in ["index"]:
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

    user_role = st.session_state.get("user_role", "").strip().lower()
    if user_role == "sales":
        allow_remark = False

    if not allow_remark:
        st.markdown("<div class='ro-banner'>⚠️ View-only · Cannot add or edit remarks.</div>", unsafe_allow_html=True)

    spreadsheet = connect_gsheet()
    if not spreadsheet:
        st.error("Could not connect to Google Sheets.")
        return

    master_df, ws, headers = fetch_sheet_data(spreadsheet, sheet_name)
    if master_df is None or master_df.empty:
        st.info("No data available in this sheet yet.")
        return

    # ── CCO Role Handling Logic ─────────────────────────────────
    if user_role == "cco":
        if sheet_name.lower() == "ho raw data":
            code_col_match = [c for c in master_df.columns if c.strip().lower() == "code"]
            
            if not code_col_match:
                st.error("Column 'Code' not found in data sheet to filter for CCO role.")
                return
            
            actual_code_column = code_col_match[0]
            
            user_code_raw = (
                st.session_state.get("user_code") 
                if st.session_state.get("user_code") is not None 
                else st.session_state.get("code", "")
            )
            
            if isinstance(user_code_raw, pd.Series):
                user_code_raw = user_code_raw.iloc[0] if not user_code_raw.empty else ""

            if user_code_raw or user_code_raw == 0:
                def clean_code_string(val):
                    val_str = str(val).strip().lower()
                    if val_str.endswith('.0'):
                        return val_str[:-2]
                    return val_str

                if isinstance(user_code_raw, list):
                    allowed_codes = [clean_code_string(c) for c in user_code_raw]
                elif isinstance(user_code_raw, (int, float)):
                    allowed_codes = [clean_code_string(int(user_code_raw))]
                else:
                    allowed_codes = [clean_code_string(c) for c in str(user_code_raw).split(",") if c.strip()]
                
                master_df = master_df[
                    master_df[actual_code_column].astype(str).apply(clean_code_string).isin(allowed_codes)
                ]
            else:
                st.warning("No tracking code assigned to your CCO profile account.")
                st.write("Debug Info — Session State keys available:", list(st.session_state.keys()))
                return

    is_all_india = False
    if region_filter is not None:
        clean_regions = [str(r).strip().lower() for r in region_filter]
        if "all india" in clean_regions:
            is_all_india = True

    if region_filter is not None and not is_all_india:
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
        if is_all_india:
            st.markdown(
                "<div class='region-banner'>🌍 Scope: <strong>All India</strong></div>", 
                unsafe_allow_html=True
            )

    pending_key = f"pending_remark_{sheet_name}"

    if allow_remark and pending_key in st.session_state:
        p = st.session_state[pending_key]
        if "sid_val" not in p:
            st.session_state.pop(pending_key, None)
            st.rerun()
        remark_dialog(
            ws=ws, service_id=p["sid_val"], sheet_name=sheet_name, 
            headers=headers, pending_key=pending_key
        )
    elif not allow_remark:
        st.session_state.pop(pending_key, None)

    render_cache_controls(sheet_name)

    # ── Metrics ───────────────────────────────────────────
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Records", len(df_view))
    if "call_category" in df_view.columns:
        m2.metric("15th Day Calls", (df_view["call_category"].str.strip().str.lower() == "encroaching").sum())
        m3.metric("15+ Calls", (df_view["call_category"].str.strip().str.lower() == "red call").sum())
        
    # if "7+_calls" in df_view.columns:
    #     m2.metric("7+ Day Calls", int(df_view["7+_calls"].astype(str).eq("1").sum()))
    # if "15+_calls" in df_view.columns:
    #     m3.metric("14+ Day Calls", int(df_view["15+_calls"].astype(str).eq("1").sum()))

    st.divider()
    # ── Search & filter controls ──────────────────────────
    search_backing_key = f"search_val_{sheet_name}"
    circle_backing_key = f"circle_val_{sheet_name}"
    cco_backing_key    = f"cco_val_{sheet_name}"

    if search_backing_key not in st.session_state:
        st.session_state[search_backing_key] = ""
    if circle_backing_key not in st.session_state:
        st.session_state[circle_backing_key] = "All"
    if cco_backing_key not in st.session_state:
        st.session_state[cco_backing_key] = "All"

    has_cco_col = "cco_name" in df_view.columns

    # Adjust layout grid based on whether CCO Name column exists
    if has_cco_col:
        col_search, col_circle, col_cco, col_reset = st.columns([3, 2, 2, 1])
    else:
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
            default_circle_idx = unique_circles.index(st.session_state[circle_backing_key])
        except ValueError:
            default_circle_idx = 0
        st.selectbox(
            "Filter by Circle", options=unique_circles, index=default_circle_idx,
            key=f"circle_select_{sheet_name}",
            on_change=lambda: st.session_state.update({
                circle_backing_key: st.session_state.get(f"circle_select_{sheet_name}", "All"),
                get_page_key(sheet_name): 1,
            }),
        )

    if has_cco_col:
        with col_cco:
            # Clean and retrieve unique non-empty CCO Names
            cco_options = df_view["cco_name"].fillna("-").replace("nan", "-").astype(str).str.strip()
            unique_ccos = ["All"] + sorted([c for c in cco_options.unique().tolist() if c and c != "-"] )
            try:
                default_cco_idx = unique_ccos.index(st.session_state[cco_backing_key])
            except ValueError:
                default_cco_idx = 0
            st.selectbox(
                "Filter by CCO Name", options=unique_ccos, index=default_cco_idx,
                key=f"cco_select_{sheet_name}",
                on_change=lambda: st.session_state.update({
                    cco_backing_key: st.session_state.get(f"cco_select_{sheet_name}", "All"),
                    get_page_key(sheet_name): 1,
                }),
            )

    with col_reset:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        if st.button("Clear", key=f"clear_{sheet_name}", use_container_width=True):
            st.session_state[search_backing_key] = ""
            st.session_state[circle_backing_key] = "All"
            st.session_state[cco_backing_key] = "All"
            st.session_state[get_page_key(sheet_name)] = 1
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    search          = st.session_state[search_backing_key]
    selected_circle = st.session_state[circle_backing_key]
    selected_cco    = st.session_state[cco_backing_key]

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

    if selected_cco != "All" and has_cco_col:
        df_filtered = df_filtered[
            df_filtered["cco_name"].fillna("-").replace("nan", "-").astype(str).str.strip() == selected_cco]

    df_filtered = df_filtered.reset_index(drop=True)


    # # ── Search & filter controls ──────────────────────────
    # search_backing_key = f"search_val_{sheet_name}"
    # circle_backing_key = f"circle_val_{sheet_name}"

    # if search_backing_key not in st.session_state:
    #     st.session_state[search_backing_key] = ""
    # if circle_backing_key not in st.session_state:
    #     st.session_state[circle_backing_key] = "All"

    # col_search, col_circle, col_reset = st.columns([3, 2, 1])
    # with col_search:
    #     st.text_input(
    #         "Search Service ID / Customer",
    #         value=st.session_state[search_backing_key],
    #         key=f"search_{sheet_name}",
    #         on_change=lambda: st.session_state.update({
    #             search_backing_key: st.session_state.get(f"search_{sheet_name}", ""),
    #             get_page_key(sheet_name): 1,
    #         }),
    #     )
    # with col_circle:
    #     unique_circles = (["All"] + sorted(df_view["circle"].dropna().unique().tolist())
    #                       if "circle" in df_view.columns else ["All"])
    #     try:
    #         default_idx = unique_circles.index(st.session_state[circle_backing_key])
    #     except ValueError:
    #         default_idx = 0
    #     st.selectbox(
    #         "Filter by Circle", options=unique_circles, index=default_idx,
    #         key=f"circle_select_{sheet_name}",
    #         on_change=lambda: st.session_state.update({
    #             circle_backing_key: st.session_state.get(f"circle_select_{sheet_name}", "All"),
    #             get_page_key(sheet_name): 1,
    #         }),
    #     )
    # with col_reset:
    #     st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
    #     if st.button("Clear", key=f"clear_{sheet_name}", use_container_width=True):
    #         st.session_state[search_backing_key] = ""
    #         st.session_state[circle_backing_key] = "All"
    #         st.session_state[get_page_key(sheet_name)] = 1
    #         st.rerun()
    #     st.markdown("</div>", unsafe_allow_html=True)

    # search          = st.session_state[search_backing_key]
    # selected_circle = st.session_state[circle_backing_key]

    # # ── Build df_filtered ─────────────────────────────────
    # df_filtered = df_view.reset_index(drop=False)
    # if search:
    #     mask = (
    #         df_filtered["service_id"].astype(str).str.contains(search, case=False, na=False)
    #         | df_filtered["customer_name"].astype(str).str.contains(search, case=False, na=False)
    #     )
    #     df_filtered = df_filtered[mask]
    # if selected_circle != "All" and "circle" in df_filtered.columns:
    #     df_filtered = df_filtered[df_filtered["circle"].astype(str) == selected_circle]
    # df_filtered = df_filtered.reset_index(drop=True)

    # if df_filtered.empty:
    #     st.warning("No matching records found for the combined filters.")
    #     return

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

    all_remark_cols = [c for c in master_df.columns if c.startswith("remark_cust") or c.startswith("remark_asp") or c.startswith("remark_internalteam")]
    
    start, end = render_pagination(sheet_name, len(df_filtered), position="top")
    df_page = df_filtered.iloc[start:end].copy()

    hint = " · Click a row anywhere to add/edit customer, ASP or internal Team remarks" if allow_remark else ""
    st.caption(
        f"Showing rows {start + 1}–{end} of {len(df_filtered)}"
        + (f" (filtered from {len(df_view)} total)" if (search or selected_circle != "All") else "")
        + hint
    )

    # ── Native Table Rendering Framework ──────────────────
    columns_order = list(FIXED_COLS)
    
    is_ho_sheet = sheet_name.lower() == "ho raw data"
    is_ch_sheet = "ch" in sheet_name.lower()

    if is_ho_sheet and "call_category" in df_page.columns:
        df_page["call_category"] = df_page["call_category"].fillna("-").replace("nan", "-")
        if "age_from_call_reg" in columns_order:
            idx = columns_order.index("age_from_call_reg") + 1
            columns_order.insert(idx, "call_category")
        else:
            columns_order.append("call_category")

    if is_ho_sheet and "cco_name" in df_page.columns:
            df_page["cco_name"] = df_page["cco_name"].fillna("-").replace("nan", "-")
            if "age_from_call_reg" in columns_order:
                idx = columns_order.index("age_from_call_reg") + 1
                columns_order.insert(idx, "cco_name")
            else:
                columns_order.append("cco_name")

    columns_order.extend(all_remark_cols)

    for col in all_remark_cols:
        if col in df_page.columns:
            df_page[col] = df_page[col].fillna("-").replace("nan", "-")

    column_config = {
        "service_id": st.column_config.TextColumn("Service ID 📌", width="None", pinned=True),
        "customer_name": st.column_config.TextColumn("Customer Name", width="None"),
        "circle": st.column_config.TextColumn("Circle", width="None"),
        "call_date": st.column_config.TextColumn("Call Date", width="None"),
        "age_from_call_reg": st.column_config.TextColumn("Call Age", width="None"),
        "status_code": st.column_config.TextColumn("Status Code", width="None"),
        "status_updated_date": st.column_config.TextColumn("Status Updated Date", width="None"),
        "call_category": st.column_config.TextColumn("Call Category", width="None"),
        "cco_name": st.column_config.TextColumn("CCO Name", width="None"),
    }

    for col in all_remark_cols:
        clean_lbl = col.replace("remark_cust", "Cust Remark ").replace("remark_asp", "ASP Remark ").replace("remark_internalteam", "Internal Team Remark ")
        column_config[col] = st.column_config.TextColumn(clean_lbl, width="Medium")

    popup_state_suffix = "active" if pending_key in st.session_state else "cleared"

    table_selection_mode = "single-row" if allow_remark else "disabled"
    table_on_select      = "rerun" if allow_remark else "ignore"

    # ── APPLY DYNAMIC STYLING HIGHLIGHTS ───────────────────
    styled_df_page = df_page[columns_order].style.apply(
        lambda df: highlight_eligible_remarks(df, is_ch_sheet),
        axis=None
    )

    event = st.dataframe(
        styled_df_page,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        on_select=table_on_select,
        selection_mode=table_selection_mode,
        key=f"data_table_{sheet_name}_{popup_state_suffix}"
    )

    # ── Row Click Trigger Interception Logic ────────────────
    if allow_remark and event and event.get("selection", {}).get("rows"):
        selected_row_idx = event["selection"]["rows"][0]
        clicked_row = df_page.iloc[selected_row_idx]
        sid_val = str(clicked_row.get("service_id", ""))

        if pending_key not in st.session_state:
            st.session_state[pending_key] = {
                "sid_val": sid_val,
                "page":    st.session_state.get(get_page_key(sheet_name), 1),
            }
            st.rerun()

    st.caption("Remarks are separated by category and cataloged daily by date structural headers.")
