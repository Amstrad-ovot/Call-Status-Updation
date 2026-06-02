import time
from datetime import datetime
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# ──────────────────────────────────────────────
# Connection & UI Layer
# ──────────────────────────────────────────────

def get_gsheet_conn():
    creds_dict = {
        "type": st.secrets["connections"]["gsheets"]["type"],
        "project_id": st.secrets["connections"]["gsheets"]["project_id"],
        "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
        "private_key": st.secrets["connections"]["gsheets"]["private_key"],
        "client_email": st.secrets["connections"]["gsheets"]["client_email"],
        "client_id": st.secrets["connections"]["gsheets"]["client_id"],
        "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
        "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
    }

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client


def connect_gsheet():
    try:
        client = get_gsheet_conn()
        SPREADSHEET_ID = "1MSKQUSdBTOEI2-YNE7Z43_SfbFsZxrOkD2UIBByX_bs"
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print("Connection successful...!!!")
        return spreadsheet
    except Exception as e:
        print(f"Unable to connect google sheet: {e}")
        show_popup(f"Unable to connect google sheet: {e}", type="error")
        raise e


def show_popup(message, type="success"):
    if type == "success":
        st.toast(f"✅ {message}")
    elif type == "error":
        st.toast(f"❌ {message}")
    elif type == "warning":
        st.toast(f"⚠️ {message}")
    elif type == "info":
        st.toast(f"ℹ️ {message}")


# ──────────────────────────────────────────────
# Core Transformation (func1)
# ──────────────────────────────────────────────

def func1(raw_file):
    try:
        spreadsheet = connect_gsheet()

        try:
            detailData_worksheet = spreadsheet.worksheet("Detailed_Data")
        except gspread.WorksheetNotFound:
            detailData_worksheet = spreadsheet.add_worksheet("Detailed_Data", rows=5000, cols=30)
            
        detailData_worksheet.clear()

        data = pd.read_excel(raw_file)
        data.columns = data.columns.str.lower().str.replace(" ", "_").str.replace(".", "_").str.strip()
        
        selected_columns = [
            "register_id", "job_id", "service_id", "customer_name", "customer_type", "address1", 
            "city", "state", "customer_pincode", "producttype_code", "model_code", "product_srno", 
            "product_srno2", "company_name", "circle", "customer_type", "call_date", "updatedate", 
            "status_code", "phone1", "provider_phone1", "registration_date", "warrantytype", 
            "invoice_no", "invoice_date"
        ]
        
        # Eliminate duplicate selected columns if any exist in array config
        selected_columns = list(dict.fromkeys(selected_columns))
        data = data[selected_columns].copy()
        
        data["service_id"] = data["service_id"].astype(str).str.strip()
        data["call_date"] = pd.to_datetime(data["call_date"]).dt.normalize()
        data["updatedate"] = pd.to_datetime(data["updatedate"]).dt.normalize()

        # Fix type safety: ensure comparison uses consistent date formats
        today_date = pd.Timestamp.now().normalize()
        data["today_date"] = today_date
        data["age_from_call_reg"] = data["today_date"] - data["call_date"]

        norms_worksheet = spreadsheet.worksheet("Norms_Data")
        norms_data = norms_worksheet.get_all_records()
        status_data = pd.DataFrame(norms_data)
        status_data.columns = status_data.columns.str.lower().str.strip().str.replace(" ", "_")

        merged_data = data.merge(status_data[["status", "team", "number"]], left_on="status_code", right_on="status", how="left")

        merged_data["age_reg_days"] = merged_data["age_from_call_reg"].dt.days.fillna(0).astype(int)
        
        merged_data["7+_calls"] = (merged_data["age_reg_days"] > 7).astype(int)
        merged_data["15+_calls"] = (merged_data["age_reg_days"] > 15).astype(int)
        
        if not merged_data.empty:
            data_to_write = [merged_data.columns.tolist()] + merged_data.fillna("").astype(str).values.tolist()
            detailData_worksheet.update(data_to_write)
            show_popup("Data stored in the database", type="success")
        else:
            show_popup("No data found after filtering...!", type="info")
            
        return merged_data

    except Exception as e:
        print(f"Error in func1: {e}")
        show_popup(f"Error in function is: {e}", type="error")


# ──────────────────────────────────────────────
# Vectorized Sync Engines
# ──────────────────────────────────────────────

def update_ch_raw_data():
    try:
        print("Inside update ch raw data function...")
        spreadsheet = connect_gsheet()

        detail_ws = spreadsheet.worksheet("Detailed_Data")
        detail_data = detail_ws.get_all_values()
        if len(detail_data) <= 1:
            show_popup("Detailed_Data sheet is empty!", type="info")
            return

        df_detail = pd.DataFrame(detail_data[1:], columns=detail_data[0])
        df_detail.columns = df_detail.columns.str.lower().str.strip().str.replace(" ", "_")
        df_detail = df_detail.loc[:, ~df_detail.columns.duplicated()]
        
        df_detail["service_id"] = df_detail["service_id"].astype(str).str.strip()
        df_filtered = df_detail[df_detail["7+_calls"].astype(str) == "1"].copy()

        if df_filtered.empty:
            show_popup("No 7+ calls data found!", type="info")
            return

        all_detail_ids = set(df_detail["service_id"])
        ageing_sheet_name = "CH Raw Data"

        try:
            ageing_ws = spreadsheet.worksheet(ageing_sheet_name)
            ageing_data = ageing_ws.get_all_values()

            if ageing_data and len(ageing_data) > 1:
                df_ageing_existing = pd.DataFrame(ageing_data[1:], columns=ageing_data[0])
                df_ageing_existing.columns = df_ageing_existing.columns.str.lower().str.strip().str.replace(" ", "_")
                df_ageing_existing = df_ageing_existing.loc[:, ~df_ageing_existing.columns.duplicated()]
                df_ageing_existing["service_id"] = df_ageing_existing["service_id"].astype(str).str.strip()
            else:
                df_ageing_existing = pd.DataFrame()
        except gspread.WorksheetNotFound:
            ageing_ws = spreadsheet.add_worksheet(ageing_sheet_name, rows=5000, cols=30)
            df_ageing_existing = pd.DataFrame()

        if df_ageing_existing.empty:
            data_to_write = [df_filtered.columns.tolist()] + df_filtered.fillna("").astype(str).values.tolist()
            ageing_ws.update(data_to_write)
            show_popup(f"CH Raw Data sheet created with {len(df_filtered)} records!", type="success")
            return

        # ── Fast Vectorized Move handling ──
        existing_ageing_ids = set(df_ageing_existing["service_id"])
        moved_ids = existing_ageing_ids - all_detail_ids
        df_moved = df_ageing_existing[df_ageing_existing["service_id"].isin(moved_ids)].copy()
        df_ageing_existing = df_ageing_existing[~df_ageing_existing["service_id"].isin(moved_ids)].copy()

        if not df_moved.empty:
            cc_sheet_name = "cc_ch_data"
            try:
                cc_ws = spreadsheet.worksheet(cc_sheet_name)
                cc_data = cc_ws.get_all_values()
                if cc_data and len(cc_data) > 1:
                    df_cc_existing = pd.DataFrame(cc_data[1:], columns=cc_data[0])
                    df_cc_existing.columns = df_cc_existing.columns.str.lower().str.strip().str.replace(" ", "_")
                    df_cc_existing = df_cc_existing.loc[:, ~df_cc_existing.columns.duplicated()]
                    df_cc_existing["service_id"] = df_cc_existing["service_id"].astype(str).str.strip()
                else:
                    df_cc_existing = pd.DataFrame()
            except gspread.WorksheetNotFound:
                cc_ws = spreadsheet.add_worksheet(cc_sheet_name, rows=5000, cols=30)
                df_cc_existing = pd.DataFrame()

            df_moved_new = df_moved[~df_moved["service_id"].isin(set(df_cc_existing["service_id"])) if not df_cc_existing.empty else []].copy()
            
            if df_cc_existing.empty:
                cc_data_to_write = [df_moved_new.columns.tolist()] + df_moved_new.fillna("").astype(str).values.tolist()
                cc_ws.update(cc_data_to_write)
            elif not df_moved_new.empty:
                df_moved_new = df_moved_new.reindex(columns=df_cc_existing.columns, fill_value="")
                df_cc_existing = pd.concat([df_cc_existing, df_moved_new], ignore_index=True)
                cc_final_data = [df_cc_existing.columns.tolist()] + df_cc_existing.fillna("").astype(str).values.tolist()
                cc_ws.clear()
                cc_ws.update(cc_final_data)

        # ── Fast Vectorized Update Engine (Replaces slow loops) ──
        ageing_cols = df_ageing_existing.columns.tolist()
        remarks_cols = [col for col in ageing_cols if col.startswith("remark")]
        non_remarks_cols = [col for col in ageing_cols if col not in remarks_cols and col != "service_id"]

        # Track modifications counts securely
        updated_count = len(df_filtered[df_filtered["service_id"].isin(set(df_ageing_existing["service_id"]))])
        df_ageing_new = df_filtered[~df_filtered["service_id"].isin(set(df_ageing_existing["service_id"]))].copy()

        # Update matching IDs using a clean indexing merge approach
        df_ageing_existing.set_index("service_id", inplace=True)
        df_filtered_updates = df_filtered[df_filtered["service_id"].isin(df_ageing_existing.index)].set_index("service_id")
        
        # Overwrite all columns except remarks natively
        available_update_cols = [c for c in non_remarks_cols if c in df_filtered_updates.columns]
        df_ageing_existing.loc[df_filtered_updates.index, available_update_cols] = df_filtered_updates[available_update_cols]
        df_ageing_existing.reset_index(inplace=True)

        # Append Brand New Rows safely
        if not df_ageing_new.empty:
            df_ageing_new = df_ageing_new.reindex(columns=ageing_cols, fill_value="")
            df_ageing_existing = pd.concat([df_ageing_existing, df_ageing_new], ignore_index=True)

        # Bulk write everything to DB in exactly 1 API call
        final_data = [df_ageing_existing.columns.tolist()] + df_ageing_existing.fillna("").astype(str).values.tolist()
        ageing_ws.clear()
        ageing_ws.update(final_data)

        show_popup(
            f"CH Raw Data updated! {updated_count} rows updated, {len(df_ageing_new)} new rows added, {len(df_moved)} rows moved to cc_ch_data.",
            type="success"
        )

    except Exception as e:
        print(f"Error in update_ch_raw_data: {e}")
        show_popup(f"Error While Updating CH Raw Data: {e}", type="error")


def update_ho_raw_data():
    try:
        spreadsheet = connect_gsheet()

        detail_ws = spreadsheet.worksheet("Detailed_Data")
        detail_data = detail_ws.get_all_values()
        if len(detail_data) <= 1:
            show_popup("Detailed_Data sheet is empty!", type="info")
            return

        df_detail = pd.DataFrame(detail_data[1:], columns=detail_data[0])
        df_detail.columns = df_detail.columns.str.lower().str.strip().str.replace(" ", "_")
        df_detail = df_detail.loc[:, ~df_detail.columns.duplicated()]
        
        df_detail["service_id"] = df_detail["service_id"].astype(str).str.strip()
        df_filtered = df_detail[df_detail["15+_calls"].astype(str) == "1"].copy()

        if df_filtered.empty:
            show_popup("No 15+ calls data found!", type="info")
            return

        all_detail_ids = set(df_detail["service_id"])
        ho_sheet_name = "HO Raw Data"

        try:
            ho_ws = spreadsheet.worksheet(ho_sheet_name)
            ho_data = ho_ws.get_all_values()

            if ho_data and len(ho_data) > 1:
                df_ho_existing = pd.DataFrame(ho_data[1:], columns=ho_data[0])
                df_ho_existing.columns = df_ho_existing.columns.str.lower().str.strip().str.replace(" ", "_")
                df_ho_existing = df_ho_existing.loc[:, ~df_ho_existing.columns.duplicated()]
                df_ho_existing["service_id"] = df_ho_existing["service_id"].astype(str).str.strip()
            else:
                df_ho_existing = pd.DataFrame()
        except gspread.WorksheetNotFound:
            ho_ws = spreadsheet.add_worksheet(ho_sheet_name, rows=5000, cols=30)
            df_ho_existing = pd.DataFrame()

        if df_ho_existing.empty:
            data_to_write = [df_filtered.columns.tolist()] + df_filtered.fillna("").astype(str).values.tolist()
            ho_ws.update(data_to_write)
            show_popup(f"HO Raw Data sheet created with {len(df_filtered)} records!", type="success")
            return

        # ── Fast Vectorized Move handling ──
        existing_ho_ids = set(df_ho_existing["service_id"])
        moved_ids = existing_ho_ids - all_detail_ids
        df_moved = df_ho_existing[df_ho_existing["service_id"].isin(moved_ids)].copy()
        df_ho_existing = df_ho_existing[~df_ho_existing["service_id"].isin(moved_ids)].copy()

        if not df_moved.empty:
            cc_sheet_name = "cc_ho_data"
            try:
                cc_ws = spreadsheet.worksheet(cc_sheet_name)
                cc_data = cc_ws.get_all_values()
                if cc_data and len(cc_data) > 1:
                    df_cc_existing = pd.DataFrame(cc_data[1:], columns=cc_data[0])
                    df_cc_existing.columns = df_cc_existing.columns.str.lower().str.strip().str.replace(" ", "_")
                    df_cc_existing = df_cc_existing.loc[:, ~df_cc_existing.columns.duplicated()]
                    df_cc_existing["service_id"] = df_cc_existing["service_id"].astype(str).str.strip()
                else:
                    df_cc_existing = pd.DataFrame()
            except gspread.WorksheetNotFound:
                cc_ws = spreadsheet.add_worksheet(cc_sheet_name, rows=5000, cols=30)
                df_cc_existing = pd.DataFrame()

            df_moved_new = df_moved[~df_moved["service_id"].isin(set(df_cc_existing["service_id"])) if not df_cc_existing.empty else []].copy()
            
            if df_cc_existing.empty:
                cc_data_to_write = [df_moved_new.columns.tolist()] + df_moved_new.fillna("").astype(str).values.tolist()
                cc_ws.update(cc_data_to_write)
            elif not df_moved_new.empty:
                df_moved_new = df_moved_new.reindex(columns=df_cc_existing.columns, fill_value="")
                df_cc_existing = pd.concat([df_cc_existing, df_moved_new], ignore_index=True)
                cc_final_data = [df_cc_existing.columns.tolist()] + df_cc_existing.fillna("").astype(str).values.tolist()
                cc_ws.clear()
                cc_ws.update(cc_final_data)

        # ── Fast Vectorized Update Engine (Replaces slow loops) ──
        ho_cols = df_ho_existing.columns.tolist()
        remarks_cols = [col for col in ho_cols if col.startswith("remark")]
        non_remarks_cols = [col for col in ho_cols if col not in remarks_cols and col != "service_id"]

        updated_count = len(df_filtered[df_filtered["service_id"].isin(set(df_ho_existing["service_id"]))])
        df_ho_new = df_filtered[~df_filtered["service_id"].isin(set(df_ho_existing["service_id"]))].copy()

        df_ho_existing.set_index("service_id", inplace=True)
        df_filtered_updates = df_filtered[df_filtered["service_id"].isin(df_ho_existing.index)].set_index("service_id")
        
        available_update_cols = [c for c in non_remarks_cols if c in df_filtered_updates.columns]
        df_ho_existing.loc[df_filtered_updates.index, available_update_cols] = df_filtered_updates[available_update_cols]
        df_ho_existing.reset_index(inplace=True)

        if not df_ho_new.empty:
            df_ho_new = df_ho_new.reindex(columns=ho_cols, fill_value="")
            df_ho_existing = pd.concat([df_ho_existing, df_ho_new], ignore_index=True)

        final_data = [df_ho_existing.columns.tolist()] + df_ho_existing.fillna("").astype(str).values.tolist()
        ho_ws.clear()
        ho_ws.update(final_data)

        show_popup(
            f"HO Raw Data updated! {updated_count} rows updated, {len(df_ho_new)} new rows added, {len(df_moved)} rows moved to cc_ho_data.",
            type="success"
        )

    except Exception as e:
        print(f"Error in update_ho_raw_data function: {e}")
        show_popup(f"Error While Updating HO Data: {e}", type="error")










#Takes time to execute but working properly(gem)
# import io
# import sys
# import time
# import pandas as pd
# import streamlit as st
# from datetime import datetime
# from streamlit_gsheets import GSheetsConnection
# import gspread
# from google.oauth2.service_account import Credentials



# # To create connection
# def get_gsheet_conn():

#     creds_dict = {
#         "type": st.secrets["connections"]["gsheets"]["type"],
#         "project_id": st.secrets["connections"]["gsheets"]["project_id"],
#         "private_key_id": st.secrets["connections"]["gsheets"]["private_key_id"],
#         "private_key": st.secrets["connections"]["gsheets"]["private_key"],
#         "client_email": st.secrets["connections"]["gsheets"]["client_email"],
#         "client_id": st.secrets["connections"]["gsheets"]["client_id"],
#         "auth_uri": st.secrets["connections"]["gsheets"]["auth_uri"],
#         "token_uri": st.secrets["connections"]["gsheets"]["token_uri"],
#     }

#     scopes = [
#         "https://www.googleapis.com/auth/spreadsheets",
#         "https://www.googleapis.com/auth/drive"
#     ]

#     creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
#     client = gspread.authorize(creds)
#     return client

# def connect_gsheet():
#     try:
#         # Google sheet Connection  
#         client = get_gsheet_conn()
#         SPREADSHEET_ID = "1MSKQUSdBTOEI2-YNE7Z43_SfbFsZxrOkD2UIBByX_bs"
#         spreadsheet = client.open_by_key(SPREADSHEET_ID)
#         print("Connection successful...!!!")
#         return spreadsheet
#     except Exception as e:
#         print(f"Unable to connect google sheet: {e}")
#         show_popup(f"Unable to connect google sheet: {e}", type="error")
        

# def show_popup(message, type = "success"):
#     if type == "success":
#         st.toast(f"✅ {message}")
#     elif type == "error" :
#         st.toast(f"❌ {message}")
#     elif type == "warning":
#         st.toast(f"⚠️ {message}")
#     elif type == "info":
#         st.toast(f"ℹ️ {message}")

# def func1(raw_file):
#     try:
#         spreadsheet = connect_gsheet()

#         # Open or create the worksheet
#         try:
#             detailData_worksheet = spreadsheet.worksheet("Detailed_Data")
#         except gspread.WorksheetNotFound:
#             detailData_worksheet = spreadsheet.add_worksheet("Detailed_Data", rows=5000, cols=30)
            
#         # Clear existing data and write fresh
#         detailData_worksheet.clear()

#         data = pd.read_excel(raw_file)
#         data.columns = data.columns.str.lower().str.replace(" ","_").str.replace(".", "_").str.strip()
        
#         # To select the subset of the dataframe from the complete data
#         selected_columns = ["register_id", "job_id","service_id","customer_name","customer_type","address1", "city","state","customer_pincode","producttype_code","model_code","product_srno","product_srno2","company_name","circle", "customer_type", "call_date", "updatedate", "status_code","phone1","provider_phone1","registration_date","warrantytype","invoice_no","invoice_date"]
        
#         data = data[selected_columns]
#         data["service_id"] = data["service_id"].astype(str)
#         data["call_date"] = pd.to_datetime(data["call_date"]).dt.normalize()
#         data["updatedate"] = pd.to_datetime(data["updatedate"]).dt.normalize()

#         todayDate = pd.to_datetime('today').date()

#         data["today_date"] = pd.to_datetime(todayDate)
#         data["age_from_call_reg"] = data["today_date"] - data["call_date"]
#         # data["age_from_call_update"] = data["today_date"] - data["updatedate"]

#         # status_data = pd.read_excel(statuswise_file)
#         norms_worksheet = spreadsheet.worksheet("Norms_Data")
#         norms_data = norms_worksheet.get_all_records()
#         status_data = pd.DataFrame(norms_data)

#         status_data.columns = status_data.columns.str.lower().str.strip().str.replace(" ", "_")

#         merged_data = data.merge(status_data[["status","team", "number"]], left_on= "status_code", right_on="status", how= "left")

#         merged_data["age_reg_days"] = merged_data["age_from_call_reg"].dt.days 
#         # merged_data["age_update_days"] = merged_data["age_from_call_update"].dt.days 
        
#         merged_data["7+_calls"] = (merged_data["age_reg_days"] > 7).astype(int)
#         merged_data["15+_calls"] = (merged_data["age_reg_days"] > 15).astype(int)
        
#         # To write data in google sheet
#         if merged_data is not None and not merged_data.empty:
            
#             # Convert DataFrame to list of lists
#             data_to_write = [merged_data.columns.tolist()] + merged_data.fillna("").astype(str).values.tolist()
#             detailData_worksheet.update(data_to_write)
            
#             show_popup("Data stored in the database", type = "success")
#         else:
#             show_popup("No data found after filtering...!", type = "info")
#         return merged_data

#     except Exception as e:
#         print(f"Error in func1: {e}")
#         show_popup(f"Error in function is: {e}", type= "error")


# def update_ch_raw_data():
#     try:
#         print("Inside update ch raw data function...")
#         spreadsheet = connect_gsheet()

#         # Open Detailed_Data sheet
#         print("Fetching Raw data....")
#         detail_ws = spreadsheet.worksheet("Detailed_Data")
#         detail_data = detail_ws.get_all_values()

#         df_detail = pd.DataFrame(detail_data[1:], columns=detail_data[0])

#         if df_detail.empty:
#             show_popup("Detailed_Data sheet is empty!", type="info")
#             return

#         # Normalize columns
#         df_detail.columns = df_detail.columns.str.lower().str.strip().str.replace(" ", "_")

#         # Remove duplicate columns — keep first occurrence only
#         df_detail = df_detail.loc[:, ~df_detail.columns.duplicated()]
#         print("Columns after dedup:", df_detail.columns.tolist())

#         # Filter only 7+ calls = 1
#         df_filtered = df_detail[df_detail["7+_calls"].astype(str) == "1"].copy()

#         if df_filtered.empty:
#             show_popup("No 7+ calls data found!", type="info")
#             return

#         # Ensure service_id is string
#         df_filtered["service_id"] = df_filtered["service_id"].astype(str)

#         # All service_ids present in detail data (not just 7+ filtered)
#         all_detail_ids = set(df_detail["service_id"].astype(str))

#         print("Columns in Filtered Data are:", df_filtered.columns.tolist())

#         # =================== CH RAW DATA SHEET ===================
#         ageing_sheet_name = "CH Raw Data"

#         try:
#             ageing_ws = spreadsheet.worksheet(ageing_sheet_name)
#             ageing_data = ageing_ws.get_all_values()

#             if ageing_data and len(ageing_data) > 1:
#                 df_ageing_existing = pd.DataFrame(ageing_data[1:], columns=ageing_data[0])
#                 df_ageing_existing.columns = df_ageing_existing.columns.str.lower().str.strip().str.replace(" ", "_")

#                 # Remove duplicate columns in ageing sheet too
#                 df_ageing_existing = df_ageing_existing.loc[:, ~df_ageing_existing.columns.duplicated()]

#                 df_ageing_existing["service_id"] = df_ageing_existing["service_id"].astype(str)
#                 existing_ageing_ids = set(df_ageing_existing["service_id"])
#                 print("Columns in ageing data:", df_ageing_existing.columns.tolist())
#             else:
#                 df_ageing_existing = pd.DataFrame()
#                 existing_ageing_ids = set()

#         except gspread.WorksheetNotFound:
#             ageing_ws = spreadsheet.add_worksheet(ageing_sheet_name, rows=5000, cols=30)
#             df_ageing_existing = pd.DataFrame()
#             existing_ageing_ids = set()

#         if df_ageing_existing.empty:
#             # --- First write: write headers + all filtered data ---
#             data_to_write = [df_filtered.columns.tolist()] + df_filtered.fillna("").astype(str).values.tolist()
#             ageing_ws.update(data_to_write)
#             show_popup(f"CH Raw Data sheet created with {len(df_filtered)} records!", type="success")

#         else:
#             ageing_cols = df_ageing_existing.columns.tolist()

#             # Identify remarks columns (any col starting with "remark")
#             remarks_cols = [col for col in ageing_cols if col.startswith("remark")]

#             # --- Identify new vs existing service_ids ---
#             df_ageing_new     = df_filtered[~df_filtered["service_id"].isin(existing_ageing_ids)].copy()
#             df_ageing_updates = df_filtered[df_filtered["service_id"].isin(existing_ageing_ids)].copy()

#             # =================== MOVED OUT LOGIC ===================
#             # service_ids in CH Raw Data but NOT in Detailed_Data at all
#             # → move to cc_ch_data sheet and remove from CH Raw Data

#             moved_ids = existing_ageing_ids - all_detail_ids
#             df_moved  = df_ageing_existing[df_ageing_existing["service_id"].isin(moved_ids)].copy()
#             # Keep only rows NOT moved in CH Raw Data
#             df_ageing_existing = df_ageing_existing[~df_ageing_existing["service_id"].isin(moved_ids)].copy()

#             if not df_moved.empty:
#                 print(f"Moving {len(df_moved)} service_ids to cc_ch_data sheet...")
#                 cc_sheet_name = "cc_ch_data"

#                 try:
#                     cc_ws = spreadsheet.worksheet(cc_sheet_name)
#                     cc_data = cc_ws.get_all_values()

#                     if cc_data and len(cc_data) > 1:
#                         df_cc_existing = pd.DataFrame(cc_data[1:], columns=cc_data[0])
#                         df_cc_existing.columns = df_cc_existing.columns.str.lower().str.strip().str.replace(" ", "_")
#                         df_cc_existing = df_cc_existing.loc[:, ~df_cc_existing.columns.duplicated()]
#                         df_cc_existing["service_id"] = df_cc_existing["service_id"].astype(str)
#                         existing_cc_ids = set(df_cc_existing["service_id"])
#                     else:
#                         df_cc_existing = pd.DataFrame()
#                         existing_cc_ids = set()

#                 except gspread.WorksheetNotFound:
#                     cc_ws = spreadsheet.add_worksheet(cc_sheet_name, rows=5000, cols=30)
#                     df_cc_existing = pd.DataFrame()
#                     existing_cc_ids = set()

#                 # Only add service_ids not already in cc_ch_data
#                 df_moved_new = df_moved[~df_moved["service_id"].isin(existing_cc_ids)].copy()

#                 if df_cc_existing.empty:
#                     # First write to cc_ch_data
#                     cc_data_to_write = [df_moved_new.columns.tolist()] + df_moved_new.fillna("").astype(str).values.tolist()
#                     cc_ws.update(cc_data_to_write)
#                 else:
#                     if not df_moved_new.empty:
#                         # Align columns and append
#                         cc_cols = df_cc_existing.columns.tolist()
#                         df_moved_new = df_moved_new.reindex(columns=cc_cols, fill_value="")
#                         df_cc_existing = pd.concat([df_cc_existing, df_moved_new], ignore_index=True)

#                         cc_final_data = (
#                             [df_cc_existing.columns.tolist()]
#                             + df_cc_existing.fillna("").astype(str).values.tolist()
#                         )
#                         cc_ws.clear()
#                         cc_ws.update(cc_final_data)

#                 print(f"Moved {len(df_moved_new)} records to cc_ch_data sheet.")

#             # =================== UPDATE EXISTING ROWS ===================
#             if not df_ageing_updates.empty:
#                 # Build lookup dict: service_id -> new row as plain dict
#                 update_dict = {
#                     str(row["service_id"]): row.to_dict()
#                     for _, row in df_ageing_updates.iterrows()
#                 }

#                 for idx, existing_row in df_ageing_existing.iterrows():
#                     sid = str(existing_row["service_id"])
#                     if sid in update_dict:
#                         new_row_data = update_dict[sid]
#                         for col in ageing_cols:
#                             # Skip remarks columns — preserve existing value
#                             if col in remarks_cols:
#                                 continue
#                             # Only update columns that exist in filtered/source data
#                             if col in new_row_data:
#                                 val = new_row_data[col]
#                                 df_ageing_existing.at[idx, col] = (
#                                     str(val) if val is not None and str(val) != "nan" else ""
#                                 )

#                 print(f"Updated {len(df_ageing_updates)} existing rows in CH Raw Data.")

#             # =================== APPEND NEW ROWS ===================
#             if not df_ageing_new.empty:
#                 df_ageing_new = df_ageing_new.reindex(columns=ageing_cols, fill_value="")
#                 df_ageing_existing = pd.concat([df_ageing_existing, df_ageing_new], ignore_index=True)
#                 print(f"Appended {len(df_ageing_new)} new rows to CH Raw Data.")

#             # --- Write back full updated CH Raw Data ---
#             final_data = (
#                 [df_ageing_existing.columns.tolist()]
#                 + df_ageing_existing.fillna("").astype(str).values.tolist()
#             )
#             ageing_ws.clear()
#             ageing_ws.update(final_data)

#             new_count     = len(df_ageing_new) if not df_ageing_new.empty else 0
#             updated_count = len(df_ageing_updates) if not df_ageing_updates.empty else 0
#             moved_count   = len(df_moved) if not df_moved.empty else 0

#             show_popup(
#                 f"CH Raw Data updated! {updated_count} rows updated, {new_count} new rows added, {moved_count} rows moved to cc_ch_data.",
#                 type="success"
#             )

#     except Exception as e:
#         print(f"Error in update_ch_raw_data: {e}")
#         show_popup(f"Error While Updating CH Raw Data: {e}", type="error")

        
# def update_ho_raw_data():
#     try:
#         spreadsheet = connect_gsheet()

#         # Open Detailed_Data sheet
#         detail_ws = spreadsheet.worksheet("Detailed_Data")
#         detail_data = detail_ws.get_all_values()

#         df_detail = pd.DataFrame(detail_data[1:], columns=detail_data[0])

#         if df_detail.empty:
#             show_popup("Detailed_Data sheet is empty!", type="info")
#             return

#         # Normalize columns
#         df_detail.columns = df_detail.columns.str.lower().str.strip().str.replace(" ", "_")

#         # Remove duplicate columns — keep first occurrence only
#         df_detail = df_detail.loc[:, ~df_detail.columns.duplicated()]
#         print("Columns after dedup:", df_detail.columns.tolist())

#         # Filter only 15+ calls = 1
#         df_filtered = df_detail[df_detail["15+_calls"].astype(str) == "1"].copy()

#         if df_filtered.empty:
#             show_popup("No 15+ calls data found!", type="info")
#             return

#         # Ensure service_id is string
#         df_filtered["service_id"] = df_filtered["service_id"].astype(str)

#         # All service_ids present in detail data (not just 15+ filtered)
#         all_detail_ids = set(df_detail["service_id"].astype(str))

#         # =================== HO RAW DATA SHEET ===================
#         ho_sheet_name = "HO Raw Data"

#         try:
#             ho_ws = spreadsheet.worksheet(ho_sheet_name)
#             ho_data = ho_ws.get_all_values()

#             if ho_data and len(ho_data) > 1:
#                 df_ho_existing = pd.DataFrame(ho_data[1:], columns=ho_data[0])
#                 df_ho_existing.columns = df_ho_existing.columns.str.lower().str.strip().str.replace(" ", "_")

#                 # Remove duplicate columns
#                 df_ho_existing = df_ho_existing.loc[:, ~df_ho_existing.columns.duplicated()]

#                 df_ho_existing["service_id"] = df_ho_existing["service_id"].astype(str)
#                 existing_ho_ids = set(df_ho_existing["service_id"])
#                 print("Columns in HO Raw Data:", df_ho_existing.columns.tolist())
#             else:
#                 df_ho_existing = pd.DataFrame()
#                 existing_ho_ids = set()

#         except gspread.WorksheetNotFound:
#             ho_ws = spreadsheet.add_worksheet(ho_sheet_name, rows=5000, cols=30)
#             df_ho_existing = pd.DataFrame()
#             existing_ho_ids = set()

#         if df_ho_existing.empty:
#             # --- First write: write headers + all filtered data ---
#             data_to_write = [df_filtered.columns.tolist()] + df_filtered.fillna("").astype(str).values.tolist()
#             ho_ws.update(data_to_write)
#             show_popup(f"HO Raw Data sheet created with {len(df_filtered)} records!", type="success")
#         else:
#             ho_cols = df_ho_existing.columns.tolist()

#             # Identify remarks columns (any col starting with "remark")
#             remarks_cols = [col for col in ho_cols if col.startswith("remark")]
            
#             # --- Identify new vs existing service_ids ---
#             df_ho_new     = df_filtered[~df_filtered["service_id"].isin(existing_ho_ids)].copy()
#             df_ho_updates = df_filtered[df_filtered["service_id"].isin(existing_ho_ids)].copy()

#             # =================== MOVED OUT LOGIC ===================
#             # service_ids in HO Raw Data but NOT in Detailed_Data at all
#             # → move to cc_ho_data sheet and remove from HO Raw Data

#             moved_ids  = existing_ho_ids - all_detail_ids
#             df_moved   = df_ho_existing[df_ho_existing["service_id"].isin(moved_ids)].copy()

#             # Keep only rows NOT moved in HO Raw Data
#             df_ho_existing = df_ho_existing[~df_ho_existing["service_id"].isin(moved_ids)].copy()

#             if not df_moved.empty:
#                 print(f"Moving {len(df_moved)} service_ids to cc_ho_data sheet...")
#                 cc_sheet_name = "cc_ho_data"

#                 try:
#                     cc_ws = spreadsheet.worksheet(cc_sheet_name)
#                     cc_data = cc_ws.get_all_values()

#                     if cc_data and len(cc_data) > 1:
#                         df_cc_existing = pd.DataFrame(cc_data[1:], columns=cc_data[0])
#                         df_cc_existing.columns = df_cc_existing.columns.str.lower().str.strip().str.replace(" ", "_")
#                         df_cc_existing = df_cc_existing.loc[:, ~df_cc_existing.columns.duplicated()]
#                         df_cc_existing["service_id"] = df_cc_existing["service_id"].astype(str)
#                         existing_cc_ids = set(df_cc_existing["service_id"])
#                     else:
#                         df_cc_existing = pd.DataFrame()
#                         existing_cc_ids = set()

#                 except gspread.WorksheetNotFound:
#                     cc_ws = spreadsheet.add_worksheet(cc_sheet_name, rows=5000, cols=30)
#                     df_cc_existing = pd.DataFrame()
#                     existing_cc_ids = set()

#                 # Only add service_ids not already in cc_ho_data
#                 df_moved_new = df_moved[~df_moved["service_id"].isin(existing_cc_ids)].copy()

#                 if df_cc_existing.empty:
#                     # First write to cc_ho_data
#                     cc_data_to_write = (
#                         [df_moved_new.columns.tolist()]
#                         + df_moved_new.fillna("").astype(str).values.tolist()
#                     )
#                     cc_ws.update(cc_data_to_write)
#                 else:
#                     if not df_moved_new.empty:
#                         # Align columns and append
#                         cc_cols = df_cc_existing.columns.tolist()
#                         df_moved_new = df_moved_new.reindex(columns=cc_cols, fill_value="")
#                         df_cc_existing = pd.concat([df_cc_existing, df_moved_new], ignore_index=True)

#                         cc_final_data = (
#                             [df_cc_existing.columns.tolist()]
#                             + df_cc_existing.fillna("").astype(str).values.tolist()
#                         )
#                         cc_ws.clear()
#                         cc_ws.update(cc_final_data)

#                 print(f"Moved {len(df_moved_new)} records to cc_ho_data sheet.")

#             # =================== UPDATE EXISTING ROWS ===================
#             if not df_ho_updates.empty:
#                 # Build lookup dict: service_id -> new row as plain dict
#                 update_dict = {
#                     str(row["service_id"]): row.to_dict()
#                     for _, row in df_ho_updates.iterrows()
#                 }

#                 for idx, existing_row in df_ho_existing.iterrows():
#                     sid = str(existing_row["service_id"])
#                     if sid in update_dict:
#                         new_row_data = update_dict[sid]
#                         for col in ho_cols:
#                             # Skip remarks columns — preserve existing value
#                             if col in remarks_cols:
#                                 continue
#                             # Only update columns that exist in filtered/source data
#                             if col in new_row_data:
#                                 val = new_row_data[col]
#                                 df_ho_existing.at[idx, col] = (
#                                     str(val) if val is not None and str(val) != "nan" else ""
#                                 )

#                 print(f"Updated {len(df_ho_updates)} existing rows in HO Raw Data.")

#             # =================== APPEND NEW ROWS ===================
#             if not df_ho_new.empty:
#                 df_ho_new = df_ho_new.reindex(columns=ho_cols, fill_value="")
#                 df_ho_existing = pd.concat([df_ho_existing, df_ho_new], ignore_index=True)
#                 print(f"Appended {len(df_ho_new)} new rows to HO Raw Data.")

#             # --- Write back full updated HO Raw Data ---
#             final_data = (
#                 [df_ho_existing.columns.tolist()]
#                 + df_ho_existing.fillna("").astype(str).values.tolist()
#             )
#             ho_ws.clear()
#             ho_ws.update(final_data)

#             new_count     = len(df_ho_new) if not df_ho_new.empty else 0
#             updated_count = len(df_ho_updates) if not df_ho_updates.empty else 0
#             moved_count   = len(df_moved) if not df_moved.empty else 0

#             show_popup(
#                 f"HO Raw Data updated! {updated_count} rows updated, {new_count} new rows added, {moved_count} rows moved to cc_ho_data.",
#                 type="success")

#     except Exception as e:
#         print(f"Error in update_ho_raw_data function: {e}")
#         show_popup(f"Error While Updating HO Data: {e}", type="error")

