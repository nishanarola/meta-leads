import streamlit as st
import pandas as pd
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
import re

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
        urls = [
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati-Regular.ttf",
            "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansGujarati/NotoSansGujarati-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansgujarati/NotoSansGujarati-Regular.ttf",
        ]
        for url in urls:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(FONT_PATH, "wb") as f:
                        f.write(r.content)
                    return True
            except:
                continue
    except:
        pass
    return False

FONT_AVAILABLE = download_font()

def normalize_unicode(text):
    """𝟑_𝐁𝐇𝐊 જેવા mathematical bold/italic unicode ને normal ASCII માં convert કરો"""
    import unicodedata
    # Mathematical bold/italic/script chars ને normal chars map કરો
    result = []
    for ch in text:
        cp = ord(ch)
        # Mathematical Bold Capital A-Z: U+1D400–U+1D419
        if 0x1D400 <= cp <= 0x1D419:
            result.append(chr(cp - 0x1D400 + ord('A')))
        # Mathematical Bold Small a-z: U+1D41A–U+1D433
        elif 0x1D41A <= cp <= 0x1D433:
            result.append(chr(cp - 0x1D41A + ord('a')))
        # Mathematical Bold Digits 0-9: U+1D7CE–U+1D7D7
        elif 0x1D7CE <= cp <= 0x1D7D7:
            result.append(chr(cp - 0x1D7CE + ord('0')))
        # Mathematical Bold Italic / Script variants (common ranges)
        elif 0x1D434 <= cp <= 0x1D503:
            # Italic/bold-italic A-Z and a-z
            offset = cp - 0x1D434
            if offset < 26:
                result.append(chr(offset + ord('A')))
            elif offset < 52:
                result.append(chr(offset - 26 + ord('a')))
            else:
                result.append(unicodedata.normalize('NFKC', ch) or ch)
        else:
            # NFKC normalization — rest of fancy unicode handle કરો
            normalized = unicodedata.normalize('NFKC', ch)
            result.append(normalized)
    return ''.join(result)

def clean_html(text):
    """HTML tags remove કરો, plain text રાખો"""
    text = str(text)
    # Mathematical bold/fancy unicode normalize કરો
    text = normalize_unicode(text)
    text = re.sub(r'<[^>]+>', '', text)   # HTML tags remove
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    text = text.strip()
    # Empty/placeholder values
    if text in ('nan', 'None', 'NaT', 'none', 'NaN', '_', "'_'", "'-'", '-', "''", '""'):
        return ''
    # Single quotes around underscore or dash — Google Sheets placeholder
    if re.match(r"^['\"]?[-_]+['\"]?$", text):
        return ''
    return text

def clean_col_name(col):
    """Column name clean કરો — underscore ને space માં"""
    col = str(col)
    col = col.replace('_', ' ').strip()
    return col

def generate_pdf(df, report_date, title="Leads Report"):
    buffer = io.BytesIO()

    # Font setup
    font_name = "Helvetica"
    if FONT_AVAILABLE and os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont("GujaratiFont", FONT_PATH))
            font_name = "GujaratiFont"
        except:
            font_name = "Helvetica"

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=8*mm,
        leftMargin=8*mm,
        topMargin=10*mm,
        bottomMargin=10*mm
    )

    title_style = ParagraphStyle(
        'CustomTitle',
        fontName=font_name,
        fontSize=16,
        alignment=1,
        spaceAfter=3,
        textColor=colors.HexColor('#1a1a2e')
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        fontName=font_name,
        fontSize=11,
        alignment=1,
        spaceAfter=8,
        textColor=colors.HexColor('#555555')
    )
    header_style = ParagraphStyle(
        'Header',
        fontName=font_name,
        fontSize=7,
        alignment=1,
        leading=9,
        textColor=colors.white
    )
    cell_style = ParagraphStyle(
        'Cell',
        fontName=font_name,
        fontSize=7,
        alignment=1,
        leading=9,
        textColor=colors.HexColor('#222222')
    )

    elements = []
    elements.append(Paragraph(clean_html(title), title_style))
    elements.append(Paragraph(f"Date: {report_date}   |   Total Leads: {len(df)}", subtitle_style))
    elements.append(Spacer(1, 8*mm))

    if not df.empty:
        # Clean column names
        clean_cols = [clean_col_name(c) for c in df.columns]

        # Header row
        header_row = [Paragraph(c, header_style) for c in clean_cols]

        # Data rows — HTML clean કરો
        data_rows = []
        for _, row in df.iterrows():
            data_rows.append([
                Paragraph(clean_html(v), cell_style) for v in row
            ])

        table_data = [header_row] + data_rows

        # Column widths
        page_w = landscape(A4)[0] - 16*mm
        col_count = len(df.columns)

        # Smart widths based on column type
        raw_widths = []
        for col in df.columns:
            c = col.lower()
            if any(x in c for x in ['date', 'time']):
                raw_widths.append(20)
            elif any(x in c for x in ['phone', 'mobile']):
                raw_widths.append(28)
            elif 'name' in c:
                raw_widths.append(30)
            elif not col.isascii():
                raw_widths.append(38)
            else:
                raw_widths.append(24)

        total = sum(raw_widths)
        col_widths = [w * page_w / total for w in raw_widths]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND',    (0, 0), (-1, 0),  colors.HexColor('#34495e')),
            ('TEXTCOLOR',     (0, 0), (-1, 0),  colors.white),
            # All cells
            ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME',      (0, 0), (-1, -1), font_name),
            ('FONTSIZE',      (0, 0), (-1, 0),  8),
            ('FONTSIZE',      (0, 1), (-1, -1), 7),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING',   (0, 0), (-1, -1), 3),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f5f5f5'), colors.white]),
            # Grid
            ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
            ('LINEBELOW',     (0, 0), (-1, 0),  1,   colors.HexColor('#2c3e50')),
        ]))

        elements.append(table)

    doc.build(elements)
    return buffer.getvalue()


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

def clean_cell_value(val):
    """Individual cell value clean"""
    if pd.isna(val):
        return ''
    s = str(val).strip()
    s = normalize_unicode(s)
    # pure placeholder values
    if s in ('nan', 'None', 'NaT', 'none', 'NaN', '_', "'_'", "'-'", '-', 'false', 'FALSE', 'null', 'NULL'):
        return ''
    if re.match(r"^[\'\"]?[-_]+[\'\"]?$", s):
        return ''
    # test/dummy rows mark
    if s.lower().startswith('<test lead') or 'dummy data' in s.lower():
        return '__TEST_ROW__'
    # trailing underscores remove: "3_" → "3"
    s = re.sub(r'_+$', '', s)
    # middle underscores → space: "3_BHK" → "3 BHK", "full_name" → "full name"
    s = re.sub(r'_+', ' ', s)
    return s.strip()


def clean_col_name(col):
    return str(col).replace('_', ' ').strip()



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
                data = ws.get_all_values()
                if not data or len(data) < 2:
                    continue
                headers = data[0]
                rows = data[1:]
                rows = [r for r in rows if any(str(cell).strip() for cell in r)]
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=headers)
                df = df.replace('', pd.NA)
                # બધા string columns clean કરો
                for col in df.columns:
                    df[col] = df[col].apply(lambda x: clean_cell_value(x) if pd.notna(x) else x)
                    df[col] = df[col].replace('', pd.NA)
                # Test/dummy rows filter કરો
                mask = df.apply(lambda row: row.astype(str).str.contains('__TEST_ROW__').any(), axis=1)
                df = df[~mask].reset_index(drop=True)
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

# Sidebar
st.sidebar.image("enacle-logo.png", width=150)
st.sidebar.markdown("## ⚙️ Settings")
saved_names, saved_auto = load_sheet_names()
auto_fetch = saved_auto
st.sidebar.divider()
st.sidebar.markdown("### 📋 Manual Sheet Names")
st.sidebar.markdown("_This list will be used when auto-fetch is OFF._")
if "sheet_names" not in st.session_state:
    st.session_state.sheet_names = saved_names if saved_names else ["Gopinathji Grp", "Gopinathji Grp Leads 2"]
to_delete = None
for i, name in enumerate(st.session_state.sheet_names):
    col_a, col_b = st.sidebar.columns([5, 1])
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
if st.sidebar.button("➕ Add Sheet", use_container_width=True):
    st.session_state.sheet_names.append("")
    st.rerun()
st.sidebar.divider()
if st.sidebar.button("💾 Save Settings", use_container_width=True, type="primary"):
    clean_names = [n.strip() for n in st.session_state.sheet_names if n.strip()]
    save_sheet_names(clean_names, auto_fetch)
    st.sidebar.success(f"✅ Saved! {len(clean_names)} sheets")
current_names, current_auto = load_sheet_names()
if current_names:
    st.sidebar.divider()
    st.sidebar.markdown("**📌 Currently Saved:**")
    for n in current_names:
        st.sidebar.markdown(f"• {n}")


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
        section[data-testid="stSidebar"] .stButton > button {
            background-color: hsl(217, 91%, 60%) !important;
            border-color: hsl(217, 91%, 60%) !important;
            color: white !important;
        }

    </style>
""", unsafe_allow_html=True)



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