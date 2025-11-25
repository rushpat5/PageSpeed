import streamlit as st
import requests
import pandas as pd
import io
import xlsxwriter

# --- Page Config ---
st.set_page_config(page_title="PageSpeed Auditor", page_icon="⚡")

# --- Function to get Data ---
def get_pagespeed_data(url, api_key, strategy="mobile"):
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}"
    if api_key:
        api_url += f"&key={api_key}"
    
    response = requests.get(api_url)
    if response.status_code == 200:
        return response.json()
    else:
        st.error(f"Error {response.status_code}: {response.text}")
        return None

# --- Function to Process Data ---
def process_lighthouse_data(json_data):
    audits = json_data.get("lighthouseResult", {}).get("audits", {})
    issues = []

    for audit_id, audit in audits.items():
        # We only want audits that are "opportunities" or "diagnostics" 
        score = audit.get("score")
        score_display_mode = audit.get("scoreDisplayMode")
        
        # Filter: If it has a numeric score < 0.9 OR it is an 'informative' metric with display value
        if (score is not None and score < 0.9) or (score_display_mode == "informative" and "displayValue" in audit):
            
            issues.append({
                "Category": "Performance", 
                "Issue Title": audit.get("title"),
                "Description": audit.get("description", "").split("[")[0], # Remove links for clean text
                "Score (0-1)": score if score is not None else "N/A",
                "Display Value": audit.get("displayValue", ""),
            })
            
    return pd.DataFrame(issues)

# --- Function to Create Excel ---
def to_excel(df):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("PageSpeed Issues")

    # Formats
    header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#4F81BD', 'border': 1})
    text_wrap_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
    score_bad_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1}) 
    
    # Write Headers
    headers = list(df.columns)
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_fmt)

    # Write Data
    for row_num, row_data in enumerate(df.values, 1):
        for col_num, cell_value in enumerate(row_data):
            cell_fmt = text_wrap_fmt
            
            # Apply color format to the 'Score' column if low
            if headers[col_num] == "Score (0-1)" and isinstance(cell_value, (int, float)):
                if cell_value < 0.5:
                    cell_fmt = score_bad_fmt
            
            worksheet.write(row_num, col_num, cell_value, cell_fmt)

    # Adjust Column Widths
    worksheet.set_column('A:A', 15) # Category
    worksheet.set_column('B:B', 30) # Title
    worksheet.set_column('C:C', 50) # Description
    worksheet.set_column('D:D', 10) # Score
    worksheet.set_column('E:E', 20) # Value

    workbook.close()
    return output.getvalue()

# --- Streamlit UI ---
st.title("⚡ Client-Ready PageSpeed Auditor")
st.markdown("""
This tool runs a Google Lighthouse audit and generates a **ready-to-send Excel report** for your tech team.
""")

# Input
with st.form("audit_form"):
    url_input = st.text_input("Enter Website URL (e.g., https://example.com)")
    api_key_input = st.text_input("Google API Key (Optional but Recommended)", type="password")
    device_type = st.selectbox("Device Strategy", ["mobile", "desktop"])
    submitted = st.form_submit_button("Run Audit")

if submitted and url_input:
    with st.spinner("Running Lighthouse Audit... This may take 15-30 seconds."):
        data = get_pagespeed_data(url_input, api_key_input, device_type)
        
        if data:
            # Extract Metrics
            lighthouse = data.get("lighthouseResult", {})
            categories = lighthouse.get("categories", {})
            perf_score = categories.get("performance", {}).get("score", 0) * 100
            
            # Show Score
            col1, col2, col3 = st.columns(3)
            col1.metric("Performance Score", f"{perf_score:.0f}/100")
            
            # Process Details
            df_issues = process_lighthouse_data(data)
            
            if not df_issues.empty:
                st.success(f"Found {len(df_issues)} issues/opportunities!")
                st.dataframe(df_issues.head()) # Show preview
                
                # Generate Excel
                excel_data = to_excel(df_issues)
                
                st.download_button(
                    label="📥 Download Client-Ready Excel Report",
                    data=excel_data,
                    file_name="pagespeed_audit_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.balloons()
                st.success("No significant issues found! Great job.")
