import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import base64

# --- CONFIGURE GOOGLE SHEET SOURCE ---
SHEET_ID = "1viV03CJxPsK42zZyKI6ZfaXlLR62IbC0O3Lbi_hfGRo"
SHEET_NAME = "Master"
CSV_URL = f"https://docs.google.com/spreadsheets/d/1viV03CJxPsK42zZyKI6ZfaXlLR62IbC0O3Lbi_hfGRo/gviz/tq?tqx=out:csv&sheet=Master"

# --- YOUR WEBHOOK URLs ---
WEBHOOK_URL_PHOTO = "https://script.google.com/macros/s/AKfycbyMWdK_ES0UN_NscSlwemocz1N3quY1W4oQZTLD9Be2slj1g_YuDGAVtmMrsFaHIUGf9Q/exec"
WEBHOOK_URL_DATA = "https://script.google.com/macros/s/AKfycby7JYyqaDQD3Ov95bFNCcelbCzoVRUELitQ8p0TpbosKB3xVPrxutya3EkGzdGBapq_-w/exec"

# --- Load PO Data from Google Sheet ---
@st.cache_data
def load_po_data():
    df = pd.read_csv(CSV_URL)
    po_dict = {}
    for _, row in df.iterrows():
        db = row['Database']
        po = str(row['Nomor PO'])
        item = row['Item']
        if db not in po_dict:
            po_dict[db] = {}
        if po not in po_dict[db]:
            po_dict[db][po] = []
        po_dict[db][po].append(item)
    return po_dict

# --- UI ---
st.title("Inbound Monitoring Form")

database_data = load_po_data()
selected_db = st.selectbox("Select Database:", list(database_data.keys()))
selected_po = st.selectbox("Select PO Number:", list(database_data[selected_db].keys()))
item_options = database_data[selected_db][selected_po]

selected_items = st.multiselect("Select items received:", item_options)

qty_dict = {}
for item in selected_items:
    qty = st.number_input(f"Qty received for {item}", min_value=0, step=1, key=f"qty_{item}")
    qty_dict[item] = qty

uploaded_files = st.file_uploader("Upload photos (unlimited):", accept_multiple_files=True, type=["jpg", "jpeg", "png"])

# --- Submission ---
if st.button("Submit"):
    if not selected_items or all(qty == 0 for qty in qty_dict.values()):
        st.error("Please select items and enter a non-zero quantity for at least one.")
    else:
        timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"{selected_db}_{selected_po}_{timestamp}"

        # --- Step 1: Send photos to Drive Webhook ---
        photo_payload = {
            "folder_name": folder_name,
            "images": [
                {
                    "filename": file.name,
                    "content": base64.b64encode(file.read()).decode("utf-8")
                }
                for file in uploaded_files
            ]
        }

        photo_success = False

        try:
            photo_response = requests.post(WEBHOOK_URL_PHOTO, json=photo_payload)
            if photo_response.status_code == 200:
                st.success("✅ Photos uploaded successfully.")
                photo_success = True
            else:
                st.error(f"❌ Photo upload failed: {photo_response.status_code} - {photo_response.text}")
        except Exception as e:
            st.error(f"❌ Photo upload error: {e}")

        # --- Step 2: Log data to Sheet Webhook ---
        entries = []
        for item, qty in qty_dict.items():
            if qty > 0:
                entries.append({
                    "timestamp": timestamp,
                    "database": selected_db,
                    "po_number": selected_po,
                    "item": item,
                    "quantity": qty
                })

        data_success = False

        if entries:
            data_payload = {
                "timestamp": timestamp,
                "database": selected_db,
                "po_number": selected_po,
                "items": entries
            }

            try:
                data_response = requests.post(WEBHOOK_URL_DATA, json=data_payload)
                if data_response.status_code == 200:
                    st.success("✅ Data logged successfully.")
                    data_success = True
                else:
                    st.error(f"❌ Data logging failed: {data_response.status_code} - {data_response.text}")
            except Exception as e:
                st.error(f"❌ Logging error: {e}")

        # --- Final Feedback ---
        if photo_success and data_success:
            st.success("🎉 Submission completed successfully!")
        elif not photo_success and not data_success:
            st.error("🚨 Submission failed for both photo upload and data logging.")
        elif not photo_success:
            st.warning("⚠️ Data saved, but photo upload failed.")
        elif not data_success:
            st.warning("⚠️ Photos uploaded, but data logging failed.")
