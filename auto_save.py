import os
import sys
import pytz
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
# Jyaan PDFs save karva che ae folder path
SAVE_FOLDER = r"D:\Enacle"
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dateutil import parser as dtparser
from fpdf import FPDF
import requests
from dotenv import load_dotenv

load_dotenv()

# SPREADSHEET_NAMES = [
#     "Gopinathji Grp Leads",
#     "Gopinathji Grp Leads 2",
#     "Enacle",
#     "Enacle meta",
# ]

FONT_PATH = "NotoSansGujarati.ttf"

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
    font_name = "MainFont" if FONT_AVAILABLE else "Arial"
    if FONT_AVAILABLE:
        pdf.add_font("MainFont", "", FONT_PATH, uni=True)
    page_width = 277
    pdf.set_font(font_name, size=14)
    pdf.cell(0, 8, title, ln=True, align='C')
    pdf.set_font(font_name, size=10)
    pdf.cell(0, 6, f"Date: {report_date}  |  Total Leads: {len(df)}", ln=True, align='C')
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
        pdf.set_font(font_name, size=6)
        header_height = 14
        start_y = pdf.get_y()
        def split_2lines(text, limit=18):
            text = str(text)
            if len(text) <= limit:
                return text, ""
            mid = len(text) // 2
            return text[:mid].strip(), text[mid:mid*2].strip()
        for i, col in enumerate(df.columns):
            line1, line2 = split_2lines(col)
            x = pdf.get_x()
            y = start_y
            pdf.set_fill_color(52, 73, 94)
            pdf.rect(x, y, col_widths[i], header_height, 'FD')
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(x, y + 2)
            pdf.cell(col_widths[i], 5, line1, 0, 0, 'C')
            if line2:
                pdf.set_xy(x, y + 8)
                pdf.cell(col_widths[i], 5, line2, 0, 0, 'C')
            pdf.set_xy(x + col_widths[i], start_y)
        pdf.set_xy(pdf.l_margin, start_y + header_height)
        pdf.set_text_color(0, 0, 0)
        for row_idx in range(len(df)):
            if pdf.get_y() + 10 > pdf.page_break_trigger:
                pdf.add_page()
                pdf.set_font(font_name, size=7)
            pdf.set_fill_color(245, 245, 245) if row_idx % 2 == 0 else pdf.set_fill_color(255, 255, 255)
            for i, col in enumerate(df.columns):
                val = str(df.iloc[row_idx][col])
                max_chars = max(8, int(col_widths[i] / 2.0))
                pdf.cell(col_widths[i], 9, val[:max_chars] + ('..' if len(val) > max_chars else ''), 1, 0, 'L', fill=True)
            pdf.ln()
    output = pdf.output(dest='S')
    return bytes(output) if isinstance(output, (bytes, bytearray)) else output.encode('latin-1')

def load_all_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(os.path.join(BASE_DIR, "service_account.json"), scope)
    client = gspread.authorize(creds)
    ist = pytz.timezone('Asia/Kolkata')
    all_dfs = []
    for spreadsheet_name in SPREADSHEET_NAMES:
        try:
            spreadsheet = client.open(spreadsheet_name)
            all_worksheets = spreadsheet.worksheets()
        except Exception as e:
            print(f"Could not open '{spreadsheet_name}': {e}")
            continue
        for ws in all_worksheets:
            try:
                data = ws.get_all_records(head=1)
                if not data:
                    continue
                df = pd.DataFrame(data)
                df = df.replace('', pd.NA)
                if 'created_time' not in df.columns:
                    continue
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
                        except:
                            pass
                        results.append(parsed)
                    return pd.Series(results, index=series.index)
                df['created_dt'] = parse_to_ist(df['created_time'])
                df['created_time'] = df['created_dt'].dt.strftime('%d-%m-%Y')
                df['Project'] = ws.title
                df['_spreadsheet'] = spreadsheet_name
                if 'campaign_name' in df.columns:
                    df['campaign_name'] = df['campaign_name'].astype(str).str.split('|').str[0].str.strip()
                for col in df.columns:
                    if 'phone' in col.lower() or 'mobile' in col.lower():
                        df[col] = df[col].astype(str).str.replace(r'^p:', '', regex=True).str.strip()
                        df[col] = df[col].replace(['nan', 'NaN', 'None', ''], pd.NA)
                if 'phone' in df.columns and 'phone_number' in df.columns:
                    df['phone'] = df['phone'].fillna(df['phone_number'])
                    df = df.drop(columns=['phone_number'])
                elif 'phone_number' in df.columns and 'phone' not in df.columns:
                    df = df.rename(columns={'phone_number': 'phone'})
                if 'id' in df.columns:
                    df_with_id = df[df['id'].notna() & (df['id'].astype(str).str.strip() != '')]
                    df_without_id = df[df['id'].isna() | (df['id'].astype(str).str.strip() == '')]
                    df_with_id = df_with_id.drop_duplicates(subset=['id'], keep='last')
                    df = pd.concat([df_with_id, df_without_id], ignore_index=True)
                cols_to_drop = ['id', 'ad_id', 'ad_name', 'adset_id', 'adset_name',
                                'campaign_id', 'form_id', 'form_name', 'is_organic',
                                'platform', 'lead_status']
                df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
                all_dfs.append(df)
                print(f"  ✅ {spreadsheet_name} / {ws.title}: {len(df)} rows")
            except Exception as e:
                print(f"  ⚠️ Skipped {ws.title}: {e}")
                continue
    if not all_dfs:
        return None
    return pd.concat(all_dfs, ignore_index=True)

def main():
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)

    # ── MANUAL DATE — demo mate change karo, normally comment rakho ──
    # MANUAL_DATE = "10-03-2026"  # DD-MM-YYYY format ma lakho
    MANUAL_DATE = None            # Normal mode — yesterday auto lese
    # ────────────────────────────────────────────────────────────────

    if MANUAL_DATE:
        yesterday = datetime.strptime(MANUAL_DATE, "%d-%m-%Y").date()
        print(f"⚠️  MANUAL DATE MODE: {MANUAL_DATE}")
    else:
        yesterday = (now_ist - timedelta(1)).date()

    # ── Folder structure: SAVE_FOLDER / March_2026 / 10-03-2026 /
    month_folder = yesterday.strftime('%B_%Y')        # e.g. March_2026
    date_folder  = yesterday.strftime('%d-%m-%Y')     # e.g. 10-03-2026
    save_path = os.path.join(SAVE_FOLDER, month_folder, date_folder)
    os.makedirs(save_path, exist_ok=True)

    date_label = yesterday.strftime('%d-%m-%Y')
    print(f"\n🚀 Fetching leads for {date_label}...")
    print(f"📁 Save path: {save_path}\n")

    df = load_all_sheets()
    if df is None:
        print("❌ No data loaded.")
        return

    filtered = df[df['created_dt'].dt.date == yesterday].copy()
    if filtered.empty and 'created_time' in df.columns:
        filtered = df[df['created_time'] == date_label].copy()

    if filtered.empty:
        print(f"❌ No leads for yesterday ({date_label}).")
        return

    spreadsheet_col = filtered['_spreadsheet'].copy().reset_index(drop=True)
    display = filtered.drop(columns=['created_dt', '_spreadsheet'], errors='ignore').reset_index(drop=True)
    for col in display.columns:
        display[col] = display[col].astype(str).replace({'None': '', 'nan': '', 'NaT': '', 'none': '', 'NaN': ''})
    if 'phone' in display.columns:
        display = display.drop_duplicates(subset=['phone', 'created_time'], keep='first').reset_index(drop=True)
        spreadsheet_col = spreadsheet_col.iloc[:len(display)].reset_index(drop=True)

    print(f"✅ {len(display)} leads found\n")

    saved_files = []

    # Save per spreadsheet PDF
    for sname in SPREADSHEET_NAMES:
        mask = spreadsheet_col == sname
        sdf = display[mask.values].copy()
        if not sdf.empty:
            pdf_bytes = generate_pdf(sdf, date_label, f"{sname} - {date_label}")
            fname = f"{sname.replace(' ', '_')}_{date_label}.pdf"
            fpath = os.path.join(save_path, fname)
            with open(fpath, 'wb') as f:
                f.write(pdf_bytes)
            print(f"💾 Saved: {fpath}")
            saved_files.append(fpath)

    # Save combined PDF
    combined_pdf = generate_pdf(display, date_label, f"All Projects - {date_label}")
    combined_path = os.path.join(save_path, f"All_Projects_{date_label}.pdf")
    with open(combined_path, 'wb') as f:
        f.write(combined_pdf)
    print(f"💾 Saved: {combined_path}")
    saved_files.append(combined_path)

    print(f"\n✅ Done! {len(saved_files)} PDFs saved in:\n{save_path}")

    # Auto open folder in Windows
    os.startfile(save_path)

if __name__ == "__main__":
    main()