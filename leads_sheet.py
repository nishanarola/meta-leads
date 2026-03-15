import streamlit as st
import pandas as pd
from fpdf import FPDF
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import os
import json
import pytz
import io
import zipfile
from dateutil import parser as dtparser
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(page_title="Enacle", page_icon="🏠", layout="wide")
st.title("Enacle — Leads Report")

SHEETS_CONFIG_FILE = "sheets_config.json"

def load_sheet_names():
    if os.path.exists(SHEETS_CONFIG_FILE):
        try:
            with open(SHEETS_CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("sheets", []), data.get("auto_fetch", True)
        except:
            pass
    return [], True

def save_sheet_names(names, auto_fetch):
    with open(SHEETS_CONFIG_FILE, "w") as f:
        json.dump({"sheets": names, "auto_fetch": auto_fetch}, f, indent=2)

FONT_PATH = "NotoSansGujarati-Regular.ttf"

def download_font():
    if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 10000:
        return True
    try:
        for url in [
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf",
            "https://fonts.gstatic.com/s/notosansgujarati/v20/6xKhdSpbNNCT-vSSdB8ArxGi3dSQ.ttf",
        ]:
            r = requests.get(url, timeout=10)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(FONT_PATH, "wb") as f:
                    f.write(r.content)
                return True
    except:
        pass
    return False

FONT_AVAILABLE = download_font()

def generate_pdf(df, report_date, title="Leads Report"):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    DEJAVU_PATH = "DejaVuSans.ttf"
    if not os.path.exists(DEJAVU_PATH):
        try:
            r = requests.get(
                "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2",
                timeout=15
            )
        except:
            pass
    
    # DejaVu ને બદલે સીધું Noto Sans Gujarati વાપરો
    if FONT_AVAILABLE:
        pdf.add_font("MainFont", "", FONT_PATH, uni=True)
        font_name = "MainFont"
    elif os.path.exists(DEJAVU_PATH):
        pdf.add_font("MainFont", "", FONT_PATH)
        font_name = "MainFont"
    else:
        font_name = "Arial"

    page_width = 277
    pdf.set_font(font_name, size=18)
    pdf.cell(0, 8, str(title), ln=True, align='C')
    pdf.set_font(font_name, size=14)
    pdf.ln(4)
    if not df.empty:
        col_widths = []
        for col in df.columns:
            c = col.lower()
            if any(x in c for x in ['date', 'time']): col_widths.append(22)
            elif any(x in c for x in ['phone', 'mobile']): col_widths.append(30)
            elif 'campaign' in c: col_widths.append(32)
            elif 'project' in c: col_widths.append(28)
            elif 'name' in c: col_widths.append(32)
            elif not col.isascii(): col_widths.append(40)
            else: col_widths.append(25)
        col_widths = [w * page_width / sum(col_widths) for w in col_widths]
        header_height = 15
        start_y = pdf.get_y()

        # Header
        for i, col in enumerate(df.columns):
            x = pdf.get_x()
            y = start_y
            pdf.set_fill_color(52, 73, 94)
            pdf.rect(x, y, col_widths[i], header_height, 'FD')
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(font_name, size=8)
            pdf.set_xy(x, y + 3)
            pdf.multi_cell(col_widths[i], 4, str(col), 0, 'C')
            pdf.set_xy(x + col_widths[i], start_y)

        pdf.set_xy(pdf.l_margin, start_y + header_height)
        pdf.set_text_color(0, 0, 0)

        # Rows
        line_height = 5.5
        for row_idx in range(len(df)):
            if pdf.get_y() + 20 > pdf.page_break_trigger:
                pdf.add_page()
                pdf.set_font(font_name, size=8)

            pdf.set_fill_color(245, 245, 245) if row_idx % 2 == 0 else pdf.set_fill_color(255, 255, 255)
            pdf.set_font(font_name, size=8)
            row_y = pdf.get_y()

            max_lines = 1
            for i, col in enumerate(df.columns):
                val = str(df.iloc[row_idx][col])
                val = ''.join(c if ord(c) < 128 or '\u0A80' <= c <= '\u0AFF' else '?' for c in val)
                chars_per_line = max(1, int(col_widths[i] / 2.2))
                lines = max(1, -(-len(val) // chars_per_line))
                if lines > max_lines:
                    max_lines = lines
            row_height = max_lines * line_height

            for i, col in enumerate(df.columns):
                val = str(df.iloc[row_idx][col])
                x = pdf.l_margin + sum(col_widths[:i])
                chars_per_line = max(1, int(col_widths[i] / 2.2))
                num_lines = max(1, -(-len(val) // chars_per_line))
                cell_line_h = row_height / num_lines
                pdf.set_xy(x, row_y)
                pdf.rect(x, row_y, col_widths[i], row_height, 'FD')
                pdf.set_xy(x, row_y)
                pdf.multi_cell(col_widths[i], cell_line_h, val, 0, 'C')

            pdf.set_xy(pdf.l_margin, row_y + row_height)

    return pdf.output()

def parse_to_ist(series):
    results = []
    ist_tz = pytz.timezone('Asia/Kolkata')
    for val in series:
        parsed = pd.NaT
        try:
            s = str(val).strip()
            if not s or s in ('nan', 'None', 'NaT'):
                results.append(pd.NaT)
                continue
            try:
                dt = dtparser.parse(s)
                if dt.tzinfo is not None:
                    dt = dt.astimezone(ist_tz).replace(tzinfo=None)
                parsed = pd.Timestamp(dt)
            except:
                pass
            if pd.isnull(parsed):
                try:
                    ts = pd.to_datetime(s, utc=True)
                    parsed = ts.tz_convert(ist_tz).replace(tzinfo=None)
                except:
                    pass
            if pd.isnull(parsed):
                try:
                    parsed = pd.to_datetime(s[:10], format='%Y-%m-%d')
                except:
                    pass
            if pd.isnull(parsed):
                try:
                    parsed = pd.to_datetime(s[:10], format='%d-%m-%Y')
                except:
                    pass
        except:
            pass
        results.append(parsed)
    return pd.Series(results, index=series.index)

def load_all_sheets(sheet_names_list, auto_fetch_all):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    if auto_fetch_all:
        try:
            files = client.list_spreadsheet_files()
            all_spreadsheets = [s['title'] if isinstance(s, dict) else s.title for s in files]
        except Exception as e:
            all_spreadsheets = sheet_names_list
    else:
        all_spreadsheets = sheet_names_list

    all_dfs = []
    for spreadsheet_name in all_spreadsheets:
        try:
            spreadsheet = client.open(spreadsheet_name)
            worksheets = spreadsheet.worksheets()
        except:
            continue
        for ws in worksheets:
            try:
                # ✅ get_all_values() વાપરો — blank rows આવશે નહીં
                data = ws.get_all_values()
                if not data or len(data) < 2:
                    continue
                headers = data[0]
                rows = data[1:]
                # ✅ ફક્ત એ rows રાખો જેમાં ઓછામાં ઓછું 1 cell માં value હોય
                rows = [r for r in rows if any(str(cell).strip() for cell in r)]
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=headers)
                df = df.replace('', pd.NA)
                if 'created_time' not in df.columns:
                    continue
                df['created_dt'] = parse_to_ist(df['created_time'])
                df['created_time'] = df['created_dt'].dt.strftime('%d-%m-%Y')
                df['Project'] = ws.title
                df['_spreadsheet'] = spreadsheet_name
                df['campaign_name'] = ws.title
                for col in df.columns:
                    if 'phone' in col.lower() or 'mobile' in col.lower():
                        df[col] = df[col].astype(str).str.replace(r'^p:', '', regex=True).str.strip()
                        df[col] = df[col].replace(['nan', 'NaN', 'None', ''], pd.NA)
                if 'phone' in df.columns and 'phone_number' in df.columns:
                    df['phone'] = df['phone'].fillna(df['phone_number'])
                    df = df.drop(columns=['phone_number'])
                elif 'phone_number' in df.columns and 'phone' not in df.columns:
                    df = df.rename(columns={'phone_number': 'phone'})
                cols_to_drop = ['id', 'ad_id', 'ad_name', 'adset_id', 'adset_name',
                                'campaign_id', 'form_id', 'form_name', 'is_organic',
                                'platform', 'lead_status', 'adset']
                df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
                all_dfs.append(df)  
            except:
                continue
    if not all_dfs:
        return None
    return pd.concat(all_dfs, ignore_index=True)

with st.sidebar:
    st.image("enacle-logo.png", width=150)
    st.header("⚙️ Settings")
    saved_names, saved_auto = load_sheet_names()
    auto_fetch = saved_auto
    st.divider()
    st.subheader("📋 Manual Sheet Names")
    st.caption("This list will be used when auto-fetch is OFF.")
    if "sheet_names" not in st.session_state:
        st.session_state.sheet_names = saved_names if saved_names else ["Gopinathji Grp", "Gopinathji Grp Leads 2"]
    to_delete = None
    for i, name in enumerate(st.session_state.sheet_names):
        col_a, col_b = st.columns([5, 1])
        with col_a:
            new_val = st.text_input(f"Sheet {i+1}", value=name, key=f"sheet_input_{i}",
                label_visibility="collapsed", placeholder="Spreadsheet name...")
            st.session_state.sheet_names[i] = new_val
        with col_b:
            if st.button("🗑️", key=f"del_{i}", help="Delete"):
                to_delete = i
    if to_delete is not None:
        st.session_state.sheet_names.pop(to_delete)
        st.rerun()
    if st.button("➕ Add Sheet", use_container_width=True):
        st.session_state.sheet_names.append("")
        st.rerun()
    st.divider()
    if st.button("💾 Save Settings", use_container_width=True, type="primary"):
        clean_names = [n.strip() for n in st.session_state.sheet_names if n.strip()]
        save_sheet_names(clean_names, auto_fetch)
        st.success(f"✅ Saved! {len(clean_names)} sheets")
    current_names, current_auto = load_sheet_names()
    if current_names:
        st.divider()
        st.caption("📌 Currently Saved:")
        for n in current_names:
            st.caption(f"• {n}")

ist = pytz.timezone('Asia/Kolkata')
now_ist = datetime.now(ist)
yesterday_default = (now_ist - timedelta(1)).date()

col1, col2 = st.columns([2, 3])
with col1:
    selected_date = st.date_input("📅 Select Date", value=yesterday_default, max_value=yesterday_default)
with col2:
    save_folder = st.text_input("💾 Save Folder Path", value=r"D:\Enacle")

sheet_names_list, auto_fetch_active = load_sheet_names()

st.markdown("""
    <style>
            font-family: 'Noto Sans Gujarati', sans-serif;
          .st-emotion-cache-3pwa5w {
    display: none;}
           section[data-testid="stSidebar"] .stButton > button {
    background-color: hsl(217, 91%, 60%) !important;
    border-color: hsl(217, 91%, 60%) !important;
    color: white !important;}
        .leads-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; table-layout: auto; }
        .leads-table th { background-color: #34495e; color: white; text-align: center !important; padding: 10px 8px; border: 1px solid #2c3e50; white-space: normal !important; word-wrap: break-word; max-width: 150px; vertical-align: middle}
        .leads-table td { text-align: center !important; padding: 8px; border: 1px solid #ddd; white-space: normal !important;}
        .leads-table tr:nth-child(even) td { background-color: #f5f5f5; }
        .leads-table tr:hover td { background-color: #eaf4fb; }
    </style>
""", unsafe_allow_html=True)

def render_centered_table(df):
    html = df.to_html(index=False, classes="leads-table", border=0, escape=False)
    st.markdown(html, unsafe_allow_html=True)

if st.button("🚀 Generate & Save Leads Report", use_container_width=True):
    sheet_names_list, auto_fetch_active = load_sheet_names()
    if not auto_fetch_active and not sheet_names_list:
        st.error("❌ Add the sheet names to the sidebar and save it!")
        st.stop()

    with st.spinner(""):
        try:
            df = load_all_sheets(sheet_names_list, auto_fetch_active)
            if df is None:
                st.error("No data found.")
                st.stop()

            target_date = selected_date
            date_label = target_date.strftime('%d-%m-%Y')
            filtered = df[df['created_dt'].dt.date == target_date].copy()
            if filtered.empty:
                filtered = df[df['created_time'] == date_label].copy()
            if filtered.empty:
                st.error(f"❌ No Leads Found for {date_label}.")
                st.stop()

            found_spreadsheets = filtered['_spreadsheet'].unique().tolist()
            project_dfs = {}
            for sname in found_spreadsheets:
                sdf = filtered[filtered['_spreadsheet'] == sname].copy()
                for project_name in sdf['Project'].unique():
                    pdf_df = sdf[sdf['Project'] == project_name].copy()
                    pdf_df = pdf_df.drop(columns=['created_dt', '_spreadsheet'], errors='ignore').reset_index(drop=True)
                    for col in pdf_df.columns:
                        pdf_df[col] = pdf_df[col].astype(str).replace(
                            {'None': '', 'nan': '', 'NaT': '', 'none': '', 'NaN': ''})
                    if 'Project' in pdf_df.columns:
                        pdf_df = pdf_df[['Project'] + [c for c in pdf_df.columns if c != 'Project']]
                    if not pdf_df.empty:
                        project_dfs[project_name] = pdf_df

            all_display = pd.concat(list(project_dfs.values()), ignore_index=True) if project_dfs else pd.DataFrame()
            st.success(f"✅ {len(all_display)} leads found for {date_label}")

            # ✅ દરેક project અલગ table તરીકે show કરો
            for project_name, pdf_df in project_dfs.items():
                st.subheader(f"📁 {project_name} — {len(pdf_df)} leads")
                render_centered_table(pdf_df)

            zip_buffer = io.BytesIO()
            final_save_dir = None

            try:
                month_folder = target_date.strftime('%B_%Y')
                final_save_dir = os.path.join(save_folder, month_folder, date_label)
                os.makedirs(final_save_dir, exist_ok=True)

                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for project_name, sdf in project_dfs.items():
                        try:
                            pdf_df = sdf.drop(columns=['Project'], errors='ignore').copy()
                            non_empty_cols = [col for col in pdf_df.columns 
                                            if pdf_df[col].replace('', pd.NA).notna().any()]
                            pdf_df = pdf_df[non_empty_cols]

                            priority_cols = ['full_name', 'phone']
                            other_cols = [col for col in pdf_df.columns if col not in priority_cols]
                            existing_priority = [col for col in priority_cols if col in pdf_df.columns]
                            pdf_df = pdf_df[other_cols + existing_priority]

                            pdf_bytes = generate_pdf(pdf_df, date_label, project_name)
                        except Exception as pdf_err:
                            st.warning(f"PDF error {project_name}: {pdf_err}")
                            continue
                        if pdf_bytes and len(pdf_bytes) > 100:
                            safe_name = project_name.replace(' ', '-')
                            fname = f"{safe_name}-({date_label})_{len(sdf)}leads.pdf"
                            file_path = os.path.join(final_save_dir, fname)
                            with open(file_path, 'wb') as f:
                                f.write(pdf_bytes)
                            zip_file.writestr(fname, pdf_bytes)

                st.download_button(
                    label="📥 Download All Reports as ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"Enacle_Leads_{date_label}.zip",
                    mime="application/zip",
                    use_container_width=True
                )

                try:
                    os.startfile(final_save_dir)
                except:
                    pass

            except Exception as ex:
                st.error(f"Error during saving process: {ex}")

        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)