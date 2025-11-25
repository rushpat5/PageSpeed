import streamlit as st
import requests
import pandas as pd
import io
import xlsxwriter
import re

# --- Page Config ---
st.set_page_config(page_title="PageSpeed Tech Auditor", page_icon="⚡", layout="wide")

# --- Function to get Data ---
def get_pagespeed_data(url, api_key, strategy="mobile"):
    # AUTOMATIC FIX: Ensure URL starts with http:// or https://
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}"
    if api_key:
        api_url += f"&key={api_key}"
    
    try:
        response = requests.get(api_url, timeout=60)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 400:
            error_details = response.json().get('error', {}).get('message', '')
            st.error(f"❌ Analysis Failed. Reason: {error_details}")
            return None
        else:
            st.error(f"Error {response.status_code}: {response.text}")
            return None
    except Exception as e:
        st.error(f"❌ Connection Error: {str(e)}")
        return None

# --- Helper: Extract URLs from Audit Details ---
def extract_audit_details(audit):
    details = audit.get("details", {})
    items = details.get("items", [])
    detailed_text = ""

    # If there are items (like a list of URLs), format them nicely
    if items:
        for item in items:
            # Build a string for this specific row item (e.g., a specific JS file)
            parts = []
            
            # Common fields found in Lighthouse items
            if 'url' in item: 
                parts.append(f"🔗 {item['url']}")
            elif 'label' in item:
                parts.append(f"🏷️ {item['label']}")
                
            if 'wastedBytes' in item:
                kb_saved = item['wastedBytes'] / 1024
                parts.append(f"💾 Save: {kb_saved:.1f} KB")
            
            if 'totalBytes' in item:
                kb_total = item['totalBytes'] / 1024
                parts.append(f"📦 Size: {kb_total:.1f} KB")
                
            if 'wastedMs' in item:
                parts.append(f"⏱️ Delay: {item['wastedMs']} ms")

            # Only add if we found meaningful data
            if parts:
                detailed_text += " | ".join(parts) + "\n"
    
    # Fallback if no items but there is a display value
    if not detailed_text and "displayValue" in audit:
        detailed_text = audit["displayValue"]
        
    return detailed_text

# --- Function to Process Data ---
def process_lighthouse_data(json_data):
    audits = json_data.get("lighthouseResult", {}).get("audits", {})
    issues = []

    for audit_id, audit in audits.items():
        score = audit.get("score")
        score_display_mode = audit.get("scoreDisplayMode")
        
        # LOGIC: Keep if score is bad (<0.9) OR it's a manual diagnostic
        if (score is not None and score < 0.9) or (score_display_mode == "informative" and "displayValue" in audit):
            
            # 1. Clean Description & Extract Link
            raw_desc = audit.get("description", "")
            # Regex to find markdown links [Learn more](https://...)
            link_match = re.search(r'\((http.*?)\)', raw_desc)
            ref_link = link_match.group(1) if link_match else "N/A"
            # Remove the link text from description to keep it clean
            clean_desc = re.sub(r'\[Learn more\].*', '', raw_desc).strip()

            # 2. Get the Technical Details (URLs)
            tech_details = extract_audit_details(audit)

            issues.append({
                "Issue": audit.get("title"),
                "Score": score if score is not None else "Info",
                "Description": clean_desc,
                "Technical Details (Specific URLs & Assets)": tech_details,
                "Reference Link": ref_link
            })
            
    return pd.DataFrame(issues)

# --- Function to Create Professional Excel ---
def to_excel(df):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Tech Audit")

    # --- Formats ---
    header_fmt = workbook.add_format({
        'bold': True, 'font_color': 'white', 'bg_color': '#2C3E50', 
        'border': 1, 'valign': 'vcenter'
    })
    
    text_wrap_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
    
    # Detail format: Monospace font for URLs so they look like code
    details_fmt = workbook.add_format({
        'text_wrap': True, 'valign': 'top', 'border': 1, 
        'font_name': 'Consolas', 'font_size': 9, 'bg_color': '#F9F9F9'
    })
    
    score_bad_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1, 'align': 'center'})
    score_mid_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700', 'border': 1, 'align': 'center'})

    # --- Write Headers ---
    headers = list(df.columns)
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_fmt)

    # --- Write Data ---
    for row_num, row_data in enumerate(df.values, 1):
        for col_num, cell_value in enumerate(row_data):
            
            # Default Format
            cell_fmt = text_wrap_fmt
            
            # Special Formatting based on Column
            if headers[col_num] == "Technical Details (Specific URLs & Assets)":
                cell_fmt = details_fmt
            
            elif headers[col_num] == "Score":
                if isinstance(cell_value, (int, float)):
                    if cell_value < 0.5: cell_fmt = score_bad_fmt
                    elif cell_value < 0.9: cell_fmt = score_mid_fmt

            worksheet.write(row_num, col_num, cell_value, cell_fmt)

    # --- Set Column Widths ---
    worksheet.set_column('A:A', 25)  # Issue
    worksheet.set_column('B:B', 8)   # Score
    worksheet.set_column('C:C', 35)  # Description
    worksheet.set_column('D:D', 80)  # Tech Details (Wide for URLs)
    worksheet.set_column('E:E', 30)  # Reference Link

    workbook.close()
    return output.getvalue()

# --- Streamlit UI ---
st.title("⚡ Deep-Dive Tech Auditor")
st.markdown("Generates a **Developer-Level** Excel report with specific URLs, file sizes, and Google documentation links.")

with st.form("audit_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        url_input = st.text_input("Website URL", placeholder="https://example.com")
    with col2:
        device_type = st.selectbox("Device", ["mobile", "desktop"])
    
    api_key_input = st.text_input("Google API Key (Optional but faster)", type="password")
    submitted = st.form_submit_button("Start Technical Audit")

if submitted and url_input:
    with st.spinner("Analyzing assets, parsing JavaScript usage, and calculating render blocks..."):
        data = get_pagespeed_data(url_input, api_key_input, device_type)
        
        if data:
            # Scores
            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})
            perf_score = categories.get("performance", {}).get("score", 0) * 100
            
            st.metric("Performance Score", f"{perf_score:.0f}/100")
            
            # Process
            df_issues = process_lighthouse_data(data)
            
            if not df_issues.empty:
                st.success(f"Audit Complete. Found {len(df_issues)} actionable items.")
                
                # Preview
                with st.expander("👁️ Preview Issues (Click to expand)"):
                    st.dataframe(df_issues)

                # Download
                excel_data = to_excel(df_issues)
                st.download_button(
                    label="📥 Download Tech Team Report (.xlsx)",
                    data=excel_data,
                    file_name="Tech_Audit_Detailed.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.balloons()
                st.success("No issues found! Optimized.")
