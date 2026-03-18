import streamlit as st
import pandas as pd
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
import unicodedata as _ud

load_dotenv()

# ── PDF: fpdf2 (proper Indic/Unicode shaping, replaces reportlab) ─────────────
# pip install fpdf2
from fpdf import FPDF

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

# ── Font paths — NotoSans covers Gujarati + Devanagari (Hindi) ───────────────
# fpdf2 uses a SINGLE font file that supports ALL Unicode — NotoSans covers both
FONT_PATH            = "NotoSansGujarati-Regular.ttf"
DEVANAGARI_FONT_PATH = "NotoSansDevanagari-Regular.ttf"
# Best single font for mixed Gujarati+Hindi+Latin: NotoSans (full Unicode)
NOTO_FULL_PATH       = "NotoSans-Regular.ttf"

def download_font():
    """Download fonts. fpdf2 uses font files directly — no registration needed."""
    ok = False

    # 1. Try NotoSans full (covers Latin+Gujarati+Devanagari in one file)
    if os.path.exists(NOTO_FULL_PATH) and os.path.getsize(NOTO_FULL_PATH) > 10000:
        ok = True
    else:
        for url in [
            "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans-Regular.ttf",
            "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
        ]:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(NOTO_FULL_PATH, "wb") as f:
                        f.write(r.content)
                    ok = True
                    break
            except:
                continue

    # 2. Gujarati fallback
    if not os.path.exists(FONT_PATH) or os.path.getsize(FONT_PATH) < 10000:
        for url in [
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansgujarati/NotoSansGujarati-Regular.ttf",
        ]:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(FONT_PATH, "wb") as f:
                        f.write(r.content)
                    ok = True
                    break
            except:
                continue

    # 3. Devanagari fallback
    if not os.path.exists(DEVANAGARI_FONT_PATH) or os.path.getsize(DEVANAGARI_FONT_PATH) < 10000:
        for url in [
            "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
            "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari-Regular.ttf",
        ]:
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code == 200 and len(r.content) > 10000:
                    with open(DEVANAGARI_FONT_PATH, "wb") as f:
                        f.write(r.content)
                    ok = True
                    break
            except:
                continue

    return ok

FONT_AVAILABLE = download_font()

def _best_font_path():
    """Return path to best available font file for fpdf2."""
    if os.path.exists(NOTO_FULL_PATH) and os.path.getsize(NOTO_FULL_PATH) > 10000:
        return NOTO_FULL_PATH
    if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 10000:
        return FONT_PATH
    if os.path.exists(DEVANAGARI_FONT_PATH) and os.path.getsize(DEVANAGARI_FONT_PATH) > 10000:
        return DEVANAGARI_FONT_PATH
    return None

def normalize_unicode(text):
    import unicodedata
    result = []
    for ch in text:
        cp = ord(ch)
        if 0x1D400 <= cp <= 0x1D419:
            result.append(chr(cp - 0x1D400 + ord('A')))
        elif 0x1D41A <= cp <= 0x1D433:
            result.append(chr(cp - 0x1D41A + ord('a')))
        elif 0x1D7CE <= cp <= 0x1D7D7:
            result.append(chr(cp - 0x1D7CE + ord('0')))
        elif 0x1D434 <= cp <= 0x1D503:
            offset = cp - 0x1D434
            if offset < 26:
                result.append(chr(offset + ord('A')))
            elif offset < 52:
                result.append(chr(offset - 26 + ord('a')))
            else:
                result.append(unicodedata.normalize('NFKC', ch) or ch)
        else:
            normalized = unicodedata.normalize('NFKC', ch)
            result.append(normalized)
    return ''.join(result)

def clean_html(text):
    text = str(text)
    text = normalize_unicode(text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
    text = text.strip()
    if text in ('nan', 'None', 'NaT', 'none', 'NaN', '_', "'_'", "'-'", '-', "''", '""'):
        return ''
    if re.match(r"^['\"]?[-_]+['\"]?$", text):
        return ''
    return text

def clean_col_name(col):
    col = str(col)
    col = col.replace('_', ' ').strip()
    return col

def generate_pdf(df, report_date, title="Leads Report"):
    """
    Generate PDF using fpdf2 — proper Unicode/Indic shaping.
    fpdf2 uses the font file's built-in shaping, so Gujarati & Hindi render correctly.
    pip install fpdf2
    """
    # Page: A4 landscape
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=10)

    # Load font — fpdf2 handles Unicode shaping natively via the TTF file
    font_path = _best_font_path()
    if font_path:
        pdf.add_font("NotoSans", style="", fname=font_path)
        font_name = "NotoSans"
    else:
        font_name = "Helvetica"

    PAGE_W = 277  # A4 landscape width mm (297 - 10 margin each side)
    L_MARGIN = 10
    pdf.set_left_margin(L_MARGIN)
    pdf.set_right_margin(L_MARGIN)

    # ── Title ──────────────────────────────────────────────────────────────────
    pdf.set_font(font_name, size=16)
    pdf.set_text_color(26, 26, 46)      # #1a1a2e
    title_clean = clean_html(title)
    pdf.cell(PAGE_W, 10, title_clean, align='C', new_x="LMARGIN", new_y="NEXT")

    # ── Subtitle ───────────────────────────────────────────────────────────────
    pdf.set_font(font_name, size=11)
    pdf.set_text_color(85, 85, 85)
    pdf.cell(PAGE_W, 7, f"Date: {report_date}   |   Total Leads: {len(df)}",
             align='C', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    if df.empty:
        return bytes(pdf.output())

    # ── Column widths ──────────────────────────────────────────────────────────
    raw_widths = []
    for col in df.columns:
        c = col.lower()
        if any(x in c for x in ['date', 'time']):      raw_widths.append(22)
        elif any(x in c for x in ['phone', 'mobile']): raw_widths.append(32)
        elif 'name' in c:                               raw_widths.append(35)
        elif not col.isascii():                         raw_widths.append(40)
        else:                                           raw_widths.append(26)
    total = sum(raw_widths)
    col_widths = [w * PAGE_W / total for w in raw_widths]

    ROW_H = 8   # mm per row

    # ── Header row ─────────────────────────────────────────────────────────────
    pdf.set_fill_color(52, 73, 94)      # #34495e
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font_name, size=9)
    for col, w in zip(df.columns, col_widths):
        pdf.cell(w, ROW_H + 2, clean_col_name(col), border=0,
                 align='C', fill=True)
    pdf.ln()

    # ── Data rows ──────────────────────────────────────────────────────────────
    pdf.set_font(font_name, size=8)
    fill_colors = [(245, 245, 245), (255, 255, 255)]   # alternating rows
    for i, (_, row) in enumerate(df.iterrows()):
        r, g, b = fill_colors[i % 2]
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(34, 34, 34)

        # Calculate max lines needed for this row (for multi-line cells)
        row_values = [clean_html(str(v)) for v in row]

        for val, w in zip(row_values, col_widths):
            x_before = pdf.get_x()
            y_before = pdf.get_y()
            # multi_cell handles text wrapping; move back to same y after
            pdf.multi_cell(w, ROW_H, val, border='LR',
                           align='C', fill=True, new_x="RIGHT", new_y="TOP")
            pdf.set_xy(x_before + w, y_before)

        pdf.ln(ROW_H)

        # Bottom border for each row
        pdf.set_draw_color(204, 204, 204)
        pdf.line(L_MARGIN, pdf.get_y(), L_MARGIN + PAGE_W, pdf.get_y())

    return bytes(pdf.output())



# FIX 2: Multi-format date parser — original parse_to_ist logic unchanged,
# sirf _try_formats() helper add karyu che jo explicit formats try kare che
_DATE_FMTS = [
    '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d',
    '%d-%m-%Y %H:%M:%S',    '%d-%m-%Y',
    '%d/%m/%Y %H:%M:%S',    '%d/%m/%Y',
    '%m/%d/%Y %H:%M:%S',    '%m/%d/%Y',
    '%d %b %Y',             '%d %B %Y',
    '%b %d, %Y',            '%B %d, %Y',
]

def _try_formats(s):
    """Try explicit date formats before falling back to dateutil."""
    for fmt in _DATE_FMTS:
        try:
            return pd.Timestamp(datetime.strptime(s.strip(), fmt))
        except:
            continue
    return None

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
            # FIX 2: Try explicit formats first (prevents silent parse failures)
            explicit = _try_formats(s)
            if explicit is not None:
                parsed = explicit
            if pd.isnull(parsed):
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
    if pd.isna(val):
        return ''
    s = str(val).strip()
    s = normalize_unicode(s)
    if s in ('nan', 'None', 'NaT', 'none', 'NaN', '_', "'_'", "'-'", '-', 'false', 'FALSE', 'null', 'NULL'):
        return ''
    if re.match(r"^[\'\"]?[-_]+[\'\"]?$", s):
        return ''
    if s.lower().startswith('<test lead') or 'dummy data' in s.lower():
        return '__TEST_ROW__'
    s = re.sub(r'_+$', '', s)
    s = re.sub(r'_+', ' ', s)
    return s.strip()


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
                for col in df.columns:
                    df[col] = df[col].apply(lambda x: clean_cell_value(x) if pd.notna(x) else x)
                    df[col] = df[col].replace('', pd.NA)
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

# ── Sidebar ──────────────────────────────────────────────
st.sidebar.image("enacle-logo.png", width=150)
st.sidebar.markdown("## ⚙️ Settings")
saved_names, saved_auto = load_sheet_names()
auto_fetch = saved_auto
st.sidebar.divider()
st.sidebar.markdown("### 📋 Manual Sheet Names")

if "sheet_names" not in st.session_state:
    st.session_state.sheet_names = saved_names if saved_names else ["Gopinathji Grp"]

if "sheet_ids" not in st.session_state or len(st.session_state.sheet_ids) != len(st.session_state.sheet_names):
    import uuid
    st.session_state.sheet_ids = [str(uuid.uuid4())[:8] for _ in st.session_state.sheet_names]

delete_id = None
for uid, name in zip(st.session_state.sheet_ids, st.session_state.sheet_names):
    cols = st.sidebar.columns([5, 1])
    new_val = cols[0].text_input(
        uid,
        value=name,
        label_visibility="collapsed",
        placeholder="Spreadsheet name...",
        key=f"sheet_{uid}"
    )
    idx = st.session_state.sheet_ids.index(uid)
    st.session_state.sheet_names[idx] = new_val
    if cols[1].button("🗑️", key=f"del_{uid}"):
        delete_id = uid

if delete_id is not None:
    idx = st.session_state.sheet_ids.index(delete_id)
    st.session_state.sheet_names.pop(idx)
    st.session_state.sheet_ids.pop(idx)
    st.rerun()

if st.sidebar.button("➕ Add Sheet", use_container_width=True):
    import uuid
    st.session_state.sheet_names.append("")
    st.session_state.sheet_ids.append(str(uuid.uuid4())[:8])
    st.rerun()

st.sidebar.divider()

if st.sidebar.button("💾 Save Settings", use_container_width=True, type="primary"):
    clean_names = [n.strip() for n in st.session_state.sheet_names if n.strip()]
    st.session_state.sheet_names = clean_names
    st.session_state.sheet_ids = [st.session_state.sheet_ids[i] for i, n in enumerate(st.session_state.sheet_names) if n.strip()]
    save_sheet_names(clean_names, auto_fetch)
    st.sidebar.success(f"✅ Saved! {len(clean_names)} sheets")
    st.rerun()

current_names, current_auto = load_sheet_names()
if current_names:
    st.sidebar.divider()
    st.sidebar.markdown("**📌 Currently Saved:**")
    for n in current_names:
        st.sidebar.markdown(f"• {n}")

# ── Main ──────────────────────────────────────────────────
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
                # FIX 2: Show sample dates to help debug missing leads
                sample_dates = df['created_time'].dropna().unique()[:8].tolist()
                st.error(
                    f"❌ No Leads Found for {date_label}.\n\n"
                    f"Sample dates found in sheets: `{sample_dates}`"
                )
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

            try:
                month_folder = target_date.strftime('%B_%Y')
                final_save_dir = os.path.join(save_folder, month_folder, date_label)
                os.makedirs(final_save_dir, exist_ok=True)
            except:
                final_save_dir = None

            master_zip = io.BytesIO()
            with zipfile.ZipFile(master_zip, "a", zipfile.ZIP_DEFLATED, False) as zf:
                for sname in found_spreadsheets:
                    sheet_projects = {k: v for k, v in project_dfs.items()
                                      if filtered[filtered['_spreadsheet'] == sname]['Project'].isin([k]).any()}
                    if not sheet_projects:
                        continue

                    for project_name, sdf in sheet_projects.items():
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
                            lead_count = len(sdf)
                            # FIX 3: Filename → ProjectName-(DD-MM-YYYY)_(N leads).pdf
                            fname = f"{safe_name}-({date_label})_({lead_count} leads).pdf"
                            if final_save_dir:
                                try:
                                    with open(os.path.join(final_save_dir, fname), 'wb') as f:
                                        f.write(pdf_bytes)
                                except:
                                    pass
                            zf.writestr(fname, pdf_bytes)

            st.session_state["master_zip"] = master_zip.getvalue()
            st.session_state["zip_date_label"] = date_label

            if final_save_dir:
                try:
                    os.startfile(final_save_dir)
                except:
                    pass

        except Exception as e:
            st.error(f"Error: {e}")
            st.exception(e)

# Download button — session_state માંથી show કરો
if "master_zip" in st.session_state:
    date_label_dl = st.session_state.get("zip_date_label", "")
    st.download_button(
        label=f"📥 Download All Reports ({date_label_dl})",
        data=st.session_state["master_zip"],
        file_name=f"All-Reports-{date_label_dl}.zip",
        mime="application/zip",
        use_container_width=True,
        key="dl_all"
    )