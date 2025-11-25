Here is a complete, step-by-step guide to building and deploying your free PageSpeed Insights app using Python and Streamlit.

The Plan

The Logic: We will use Google's free PageSpeed Insights API to analyze the URL.[1][2]

The Code: We will write a Python script that fetches this data and formats it into a professional Excel file.

The App: We will wrap this code in a Streamlit web interface.

Deployment: We will upload it to GitHub and connect it to Streamlit Cloud (free hosting).[3]

Step 1: Get Your Free Google API Key

While the API works without a key for a few requests, it’s safer and more reliable to have one.

Go to the Google Cloud Console Credentials page.

Click Create Credentials > API Key.

Copy the key generated (it looks like AIzaSy...).

Important: Enable the "PageSpeed Insights API" in the library for your project if it's not already enabled.

Step 2: The Full Python Code

You don't need to write this. I have written the complete, ready-to-use code for you.

Create a file on your computer named streamlit_app.py and paste this code inside:

code
Python
download
content_copy
expand_less
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
        # We only want audits that are "opportunities" or "diagnostics" (usually score < 0.9 or null score but with details)
        score = audit.get("score")
        score_display_mode = audit.get("scoreDisplayMode")
        
        # Filter: If it has a numeric score < 0.9 OR it is an 'informative' metric with display value
        if (score is not None and score < 0.9) or (score_display_mode == "informative" and "displayValue" in audit):
            
            issues.append({
                "Category": "Performance", # Simplified for this specific API endpoint
                "Issue Title": audit.get("title"),
                "Description": audit.get("description", "").split("[")[0], # Remove "Learn more" links for clean text
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
    score_bad_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'border': 1}) # Red text
    
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
Step 3: The requirements.txt File

You need one more file to tell the server which libraries to install.
Create a file named requirements.txt in the same folder and add these lines:

code
Text
download
content_copy
expand_less
streamlit
requests
pandas
xlsxwriter
openpyxl
Step 4: Upload to GitHub

Create a GitHub Account if you don’t have one (it's free).[3]

Create a New Repository:

Click the + icon in the top right > New repository.

Name it something like pagespeed-auditor.[4]

Check "Public".

Click Create repository.

Upload Files:

Click uploading an existing file (link usually shown on the new repo screen).

Drag and drop your streamlit_app.py and requirements.txt files there.

Click Commit changes.

Step 5: Deploy on Streamlit Cloud

Go to share.streamlit.io and sign in with your GitHub account.

Click New app.

Repository: Select the pagespeed-auditor repo you just created.

Branch: usually main or master.

Main file path: streamlit_app.py.

Click Deploy!

How to Use It

Once deployed (it takes about 1-2 minutes to "bake"), you will get a public URL.

Paste the website link you want to check.

(Optional) Paste your Google API Key.

Click Run Audit.

Wait ~15 seconds.

Click the Download Client-Ready Excel Report button.

The Excel file will have bold headers, text wrapping, and red highlighting for bad scores—ready to email directly to your client or tech team.

Sources
help
kinsta.com
dev.to
youtube.com
ojdo.de
medium.com
addyosmani.com
github.com
apify.com
streamlit.io
ploomber.io
medium.com
medium.com
Google Search Suggestions
Display of Search Suggestions is required when using Grounding with Google Search. Learn more
streamlit community cloud github deployment tutorial
python pandas write excel with formatting openpyxl
google pagespeed insights api python free
google pagespeed insights api extract audit details python
google pagespeed insights api json response structure lighthouse issues