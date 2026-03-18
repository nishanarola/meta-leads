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
    HTML → PDF via weasyprint — full browser-level Unicode/Gujarati/Hindi shaping.
    pip install weasyprint
    Font files (NotoSans*.ttf) must exist in the working directory.
    """
    import base64

    # ── Build font CSS (@font-face) ────────────────────────────────────────────
    font_css = ""
    font_family = "Arial, sans-serif"

    def font_b64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    noto_paths = [
        ("NotoSansGujarati", FONT_PATH),
        ("NotoSansDevanagari", DEVANAGARI_FONT_PATH),
        ("NotoSans", NOTO_FULL_PATH),
    ]
    loaded = []
    for fname, fpath in noto_paths:
        if os.path.exists(fpath) and os.path.getsize(fpath) > 10000:
            b64 = font_b64(fpath)
            font_css += f"""
@font-face {{
    font-family: '{fname}';
    src: url('data:font/truetype;base64,{b64}') format('truetype');
}}"""
            loaded.append(fname)

    if loaded:
        font_family = ", ".join(f"'{f}'" for f in loaded) + ", Arial, sans-serif"

    # ── Column width percentages ───────────────────────────────────────────────
    raw_widths = []
    for col in df.columns:
        c = col.lower()
        if any(x in c for x in ['date', 'time']):       raw_widths.append(22)
        elif any(x in c for x in ['phone', 'mobile']):  raw_widths.append(32)
        elif 'name' in c:                                raw_widths.append(35)
        elif not col.isascii():                          raw_widths.append(40)
        else:                                            raw_widths.append(26)
    total = sum(raw_widths)
    col_pcts = [f"{w*100/total:.2f}%" for w in raw_widths]

    # ── Build HTML table ───────────────────────────────────────────────────────
    # Header
    header_cells = "".join(
        f'<th style="width:{pct}">{clean_col_name(col)}</th>'
        for col, pct in zip(df.columns, col_pcts)
    )

    # Rows
    row_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        bg = "#f5f5f5" if i % 2 == 0 else "#ffffff"
        cells = "".join(
            f'<td>{clean_html(str(v))}</td>' for v in row
        )
        row_html += f'<tr style="background:{bg}">{cells}</tr>\n'

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{font_css}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

@page {{
    size: A4 landscape;
    margin: 10mm 10mm 10mm 10mm;
}}

body {{
    font-family: {font_family};
    font-size: 9pt;
    color: #222;
}}

.title {{
    text-align: center;
    font-size: 16pt;
    color: #1a1a2e;
    margin-bottom: 3mm;
    font-family: {font_family};
}}

.subtitle {{
    text-align: center;
    font-size: 11pt;
    color: #555555;
    margin-bottom: 5mm;
    font-family: {font_family};
}}

table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
    font-family: {font_family};
}}

thead tr {{
    background: #34495e;
    color: #ffffff;
}}

thead th {{
    padding: 4pt 3pt;
    font-size: 9pt;
    text-align: center;
    font-weight: bold;
    word-break: break-word;
    font-family: {font_family};
}}

tbody td {{
    padding: 4pt 3pt;
    font-size: 8pt;
    text-align: center;
    border-bottom: 0.4pt solid #cccccc;
    word-break: break-word;
    font-family: {font_family};
}}
</style>
</head>
<body>
<div class="title">{clean_html(title)}</div>
<div class="subtitle">Date: {report_date} &nbsp;|&nbsp; Total Leads: {len(df)}</div>
<table>
<thead><tr>{header_cells}</tr></thead>
<tbody>{row_html}</tbody>
</table>
</body>
</html>"""

    # ── HTML → PDF ─────────────────────────────────────────────────────────────
    try:
        from weasyprint import HTML as WP_HTML
        buf = io.BytesIO()
        WP_HTML(string=html).write_pdf(buf)
        return buf.getvalue()
    except ImportError:
        # Fallback: return HTML as-is (for debugging if weasyprint not installed)
        return html.encode('utf-8')


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