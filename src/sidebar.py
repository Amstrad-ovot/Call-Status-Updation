import streamlit as st


def apply_sidebar_styles():
    st.markdown("""
        <style>
        [data-testid="stSidebar"] {
            background: linear-gradient(160deg, #1e3a5f 0%, #16213e 100%);
        }

        [data-testid="stSidebarCollapseButton"] button {
            color: white !important;
        }
        [data-testid="stSidebarCollapseButton"] button svg {
            fill: white !important;
            stroke: white !important;
        }

        [data-testid="stSidebarCollapsedControl"] button {
            color: white !important;
            background-color: #1e3a5f !important;
            border-radius: 50% !important;
        }
        [data-testid="stSidebarCollapsedControl"] button svg {
            fill: white !important;
            stroke: white !important;
        }

        .sidebar-title {
            color: #ffffff;
            font-size: 20px;
            font-weight: 700;
            padding: 10px 0 6px 0;
            letter-spacing: 0.5px;
        }

        .sidebar-subtitle {
            color: #7f9fbf;
            font-size: 11px;
            letter-spacing: 1.5px;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        /* User info badge */
        .sidebar-user {
            background: rgba(99,179,237,0.1);
            border: 1px solid rgba(99,179,237,0.2);
            border-radius: 10px;
            padding: 10px 14px;
            margin-bottom: 10px;
        }
        .sidebar-user-name {
            color: #ffffff;
            font-size: 14px;
            font-weight: 600;
            margin: 0;
        }
        .sidebar-user-role {
            color: #63b3ed;
            font-size: 11px;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin: 2px 0 0 0;
        }

        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            background-color: rgba(255,255,255,0.05);
            color: #c8d8e8;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 11px 16px;
            font-size: 13px;
            font-weight: 500;
            text-align: left;
            margin-bottom: 6px;
            transition: all 0.2s ease;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background-color: rgba(99, 179, 237, 0.15) !important;
            color: #63b3ed !important;
            border-color: #63b3ed !important;
        }

        [data-testid="stSidebar"] .stButton > button:focus {
            background-color: rgba(99, 179, 237, 0.2) !important;
            color: #63b3ed !important;
            border-color: #63b3ed !important;
        }

        [data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.1);
            margin: 12px 0;
        }

        [data-testid="stSidebar"] .stCaption {
            color: #4a6a8a !important;
            font-size: 11px;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)


def render_sidebar():
    apply_sidebar_styles()

    # Read role from session (set during login)
    role = st.session_state.get("user_role", "").strip().lower()
    user_name = st.session_state.get("user_name", "User")

    with st.sidebar:
        st.markdown('<p class="sidebar-title">⚙️ Service App</p>', unsafe_allow_html=True)
        st.markdown('<p class="sidebar-subtitle">Report Management</p>', unsafe_allow_html=True)

        # User info badge
        role_label = role.upper() if role else "USER"
        st.markdown(
            f'<div class="sidebar-user">'
            f'<p class="sidebar-user-name"> Hello, {user_name} ({role_label})</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── Role-based navigation ──────────────────
        if role == "ch":
            # CH users: only CH Dashboard
            btn_ch_dashboard = st.button("📊  View CH Dashboard")
            btn_upload        = False
            btn_ho_dashboard  = False
        else:
            # Admin / default: all tabs
            btn_upload       = st.button("📤  Upload & Create Report")
            btn_ho_dashboard = st.button("📌  View HO Dashboard")
            btn_ch_dashboard = st.button("📊  View CH Dashboard")

        st.divider()

        # Logout always visible
        if st.button("🚪  Logout"):
            from login import logout
            logout() 
        st.caption("© 2025 Service App v1.0")

    # ── Page state resolution ──────────────────
    # Set default page based on role
    if "page" not in st.session_state:
        st.session_state["page"] = "ch_dashboard" if role == "ch" else "upload"

    if btn_upload:
        st.session_state["page"] = "upload"
    if btn_ho_dashboard:
        st.session_state["page"] = "ho_dashboard"
    if btn_ch_dashboard:
        st.session_state["page"] = "ch_dashboard"

    # Guard: CH user should never land on upload/ho pages
    if role == "ch" and st.session_state["page"] not in ("ch_dashboard",):
        st.session_state["page"] = "ch_dashboard"

    return st.session_state["page"]