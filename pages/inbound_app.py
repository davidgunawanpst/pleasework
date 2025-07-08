import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
import base64

# --- CONFIGURE GOOGLE SHEET SOURCE ---
SHEET_ID = "1viV03CJxPsK42zZyKI6ZfaXlLR62IbC0O3Lbi_hfGRo"
SHEET_NAME = "Sheet2"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"

# --- WEBHOOK URLs ---
WEBHOOK_URL_PHOTO = "https://script.google.com/macros/s/AKfycbxsI5wHNRljBJ1CoqTXhbsQ8P6ESkmU-6TiL7eZRomR0FmhoJxufcUDzl8aNFHqGbxcnA/exec"
WEBHOOK_URL_DATA = "https://script.google.com/macros/s/AKfycbxsI5wHNRljBJ1CoqTXhbsQ8P6ESkmU-6TiL7eZRomR0FmhoJxufcUDzl8aNFHqGbxcnA/exec"

# --- Load PO Data from Google Sheet ---
@st.cache_data
def load_po_data():
    df = pd.read_csv(CSV_URL)

    # Build dictionary {Database: {PO Number: [Items]}}
    po_dict = {}
    for _, row in df.iterrows():
        db = row['Nama Perusahaan']
        po = str(row['PO Number'])
        item = row['Item Name Complete']
        if db not in po_dict:
            po_dict[db] = {}
        if po not in po_dict[db]:
            po_dict[db][po] = []
        po_dict[db][po].append(item)

    return df, po_dict

# --- Fixed PIC Dropdown ---
pic_list = [
    "Rikie Dwi Permana",
    "Idha Akhmad Sucahyo",
    "Rian Dinata",
    "Harimurti Krisandki",
    "Muchamad Mustofa",
    "Yogie Arie Wibowo"
]

# --- UI ---
st.title("Inbound Monitoring Form")

df_master, database_data = load_po_data()

selected_pic = st.selectbox("PIC (Submitting this form):", pic_list)
selected_db = st.selectbox("Select Database:", list(database_data.keys()))
selected_po = st.selectbox("Select PO Number:", list(database_data[selected_db].keys()))

# --- Lookup PO PIC and Vendor ---
filtered_df = df_master[
    (df_master['Nama Perusahaan'] == selected_db) &
    (df_master['PO Number'].astype(str) == selected_po)
]

selected_po_pic = filtered_df['User Created PO'].iloc[0] if not filtered_df.empty else "-"
po_vendor = filtered_df['Vendor'].iloc[0] if not filtered_df.empty else "-"

st.markdown(f"**📌 PIC PO (From Source):** {selected_po_pic}")
st.markdown(f"**🏢 Vendor:** {po_vendor}")

# --- Get Vessel Options (Cost Center Nama Kapal) ---
vessel_options = sorted(
    filtered_df['Cost Center Nama Kapal'].dropna().unique()
)

# --- Item, Quantity, and Vessel Input ---
item_options = database_data[selected_db][selected_po]
selected_items = st.multiselect("Select items received:", item_options)

entry_data = {}
for item in selected_items:
    st.markdown(f"### Entry for: `{item}`")
    col1, col2 = st.columns(2)
    with col1:
        qty = st.number_input(f"Quantity for `{item}`", min_value=0, step=1, key=f"qty_{item}")
    with col2:
        vessel = st.selectbox(f"Vessel for `{item}`", vessel_options, key=f"vessel_{item}")
    entry_data[item] = {
        "quantity": qty,
        "vessel": vessel
    }

# --- Photo Upload ---
uploaded_files = st.file_uploader("Upload photos (unlimited):", accept_multiple_files=True, type=["jpg", "jpeg", "png"])

# --- Submission ---
if st.button("Submit"):
    if not selected_items or all(values["quantity"] == 0 for values in entry_data.values()):
        st.error("Please select items and enter a non-zero quantity for at least one.")
    else:
        timestamp = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d_%H-%M-%S")
        folder_name = f"{selected_db}_{selected_po}_{timestamp}"

        # --- Step 1: Upload Photos ---
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

        drive_folder_url = "UPLOAD_FAILED"
        photo_success = False

        try:
            photo_response = requests.post(WEBHOOK_URL_PHOTO, json=photo_payload)
            if photo_response.status_code == 200:
                try:
                    json_resp = photo_response.json()
                    drive_folder_url = json_resp.get("folderUrl", "UPLOAD_FAILED")
                    st.success("✅ Photos uploaded successfully.")
                    st.markdown(f"[📂 View uploaded folder]({drive_folder_url})")
                    photo_success = True
                except Exception as e:
                    st.error(f"❌ Failed to parse photo upload response JSON: {e}")
            else:
                st.error(f"❌ Photo upload failed: {photo_response.status_code} - {photo_response.text}")
        except Exception as e:
            st.error(f"❌ Photo upload error: {e}")

        # --- Step 2: Send Metadata to Google Sheets ---
        entries = []
        for item, values in entry_data.items():
            if values["quantity"] > 0:
                entries.append({
                    "timestamp": timestamp,
                    "database": selected_db,
                    "po_number": selected_po,
                    "pic": selected_pic,
                    "po_pic": selected_po_pic,
                    "vendor": po_vendor,
                    "item": item,
                    "quantity": values["quantity"],
                    "vessel": values["vessel"]
                })

        data_payload = {
            "timestamp": timestamp,
            "database": selected_db,
            "po_number": selected_po,
            "pic": selected_pic,
            "po_pic": selected_po_pic,
            "vendor": po_vendor,
            "drive_folder_link": drive_folder_url,
            "items": entries
        }

        data_success = False
        try:
            data_response = requests.post(WEBHOOK_URL_DATA, json=data_payload)
            if data_response.status_code == 200:
                st.success("✅ Data logged successfully.")
                data_success = True
            else:
                st.error(f"❌ Data logging failed: {data_response.status_code} - {data_response.text}")
        except Exception as e:
            st.error(f"❌ Logging error: {e}")

        # --- Final Result ---
        if photo_success and data_success:
            st.success("🎉 Submission completed successfully!")
        elif not photo_success and not data_success:
            st.error("🚨 Submission failed for both photo upload and data logging.")
        elif not photo_success:
            st.warning("⚠️ Data saved, but photo upload failed.")
        elif not data_success:
            st.warning("⚠️ Photos uploaded, but data logging failed.")
