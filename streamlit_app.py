import streamlit as st
import requests
import pandas as pd
import io
import xlsxwriter
import re

# --- Page Config ---
st.set_page_config(page_title="Lighthouse Professional Auditor", page_icon="⚡", layout="wide")

# --- Helper: Clean Markdown Links ---
def clean_markdown(text):
    if not text: return ""
    # Remove [Learn more](url) patterns entirely
    text = re.sub(r'\[Learn more\]\(.*?\)', '', text)
    # Remove other markdown links but keep text: [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    return text.strip()

# --- Helper: Extract Google Doc Link ---
def extract_link(text):
    if not text: return "N/A"
    match = re.search(r'\((https://.*?)\)', text)
    return match.group(1) if match else "N/A"

# --- Helper: Format Technical Details (The "Messy" Part) ---
def format_details(audit):
    details = audit.get("details", {})
    if not details: return "No specific assets listed."
    
    output_lines = []
    
    # Lighthouse often returns a "table" of items
    if details.get("type") == "table" and "items" in details:
        headings = details.get("headings", [])
        items = details.get("items", [])
        
        if not items: return "No specific assets listed."

        # Create a readable line for each item
        for item in items:
            row_parts = []
            
            # Try to find standard columns like URL, Size, Time
            for heading in headings:
                key = heading.get("key")
                label = heading.get("text")
                value = item.get(key)
                
                # Format values based on type
                if value is not None:
                    # If it's a URL, just show the value
                    if "url" in str(key).lower() and isinstance(value, str):
                        # Truncate very long URLs for readability if needed, or keep full
                        row_parts.append(f"🔗 {value}")
                    # If it's bytes, convert to KB
                    elif "bytes" in str(key).lower() and isinstance(value, (int, float)):
                        row_parts.append(f"{label}: {value/1024:.1f} KB")
                    # If it's milliseconds
                    elif "ms" in str(key).lower() and isinstance(value, (int, float)):
                        row_parts.append(f"{label}: {value} ms")
                    # Text values
                    else:
                        row_parts.append(f"{label}: {value}")
            
            if row_parts:
                output_lines.append(" | ".join(row_parts))
    
    # Fallback for other types
    elif "items" in details:
        for item in details["items"]:
            output_lines.append(str(item))

    return "\n".join(output_lines) if output_lines else "Check detailed report online for visuals."

# --- Main Logic: Replicate Lighthouse Structure ---
def run_audit_and_process(url, api_key, strategy):
    # Auto-fix URL
    if not url.startswith("http"): url = "https://" + url
    
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}"
    if api_key: api_url += f"&key={api_key}"
    
    try:
        response = requests.get(api_url, timeout=90)
        if response.status_code != 200:
            return None, f"Error {response.status_code}: {response.text}"
        
        data = response.json()
        lighthouse = data.get("lighthouseResult", {})
        
        # 1. Capture Overall Category Scores
        summary_data = []
        for cat_id, cat_data in lighthouse.get("categories", {}).items():
            summary_data.append({
                "Category": cat_data.get("title"),
                "Score": f"{cat_data.get('score', 0) * 100:.0f}"
            })
            
        # 2. Process ALL Issues (Grouped by Category)
        all_issues = []
        
        # We iterate Categories first to get the grouping (Perf, SEO, etc)
        for cat_id, cat_data in lighthouse.get("categories", {}).items():
            category_name = cat_data.get("title")
            audit_refs = cat_data.get("auditRefs", [])
            
            for ref in audit_refs:
                audit_id = ref.get("id")
                audit = lighthouse.get("audits", {}).get(audit_id, {})
                
                score = audit.get("score")
                score_mode = audit.get("scoreDisplayMode")
                
                # DEFINITION OF AN ISSUE:
                # 1. Score < 0.9 (Not perfect)
                # 2. OR score is None but it's "informative" (Diagnostics)
                # 3. Exclude "notApplicable" or "manual" unless relevant
                is_issue = False
                priority = "Info"
                
                if score is not None:
                    if score < 0.5: 
                        priority = "High (Urgent)"
                        is_issue = True
                    elif score < 0.9: 
                        priority = "Medium (Improve)"
                        is_issue = True
                    else:
                        priority = "Passed" # We can skip these or include if requested
                else:
                    if score_mode == "informative":
                        priority = "Diagnostic"
                        is_issue = True
                    elif score_mode == "notApplicable":
                        priority = "N/A"
                
                # Add to list if it's an issue (Exclude 'Passed' and 'N/A' to keep excel clean, 
                # OR remove this check to include literally everything)
                if is_issue: 
                    clean_desc = clean_markdown(audit.get("description", ""))
                    ref_link = extract_link(audit.get("description", ""))
                    tech_details = format_details(audit)

                    all_issues.append({
                        "Category": category_name,
                        "Priority": priority,
                        "Issue Name": audit.get("title"),
                        "Description": clean_desc,
                        "Technical Breakdown (URLs & Stats)": tech_details,
                        "Google Help Link": ref_link
                    })
                    
        return summary_data, pd.DataFrame(all_issues), None

    except Exception as e:
        return None, None, str(e)

# --- Excel Generator ---
def create_client_excel(summary_list, df_issues):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # STYLES
    header_fmt = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#202124', 'border': 1, 'valign': 'vcenter'})
    wrap_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
    code_fmt = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1, 'font_name': 'Consolas', 'font_size': 9, 'bg_color': '#F8F9FA'})
    
    # Priority Colors
    prio_high = workbook.add_format({'bg_color': '#FFCDD2', 'font_color': '#B71C1C', 'border': 1, 'bold': True, 'align': 'center'})
    prio_med = workbook.add_format({'bg_color': '#FFF9C4', 'font_color': '#F57F17', 'border': 1, 'bold': True, 'align': 'center'})
    prio_info = workbook.add_format({'bg_color': '#E3F2FD', 'font_color': '#0D47A1', 'border': 1, 'align': 'center'})

    # --- SHEET 1: SUMMARY ---
    ws_sum = workbook.add_worksheet("Executive Summary")
    ws_sum.write(0, 0, "Category", header_fmt)
    ws_sum.write(0, 1, "Overall Score (0-100)", header_fmt)
    for i, item in enumerate(summary_list, 1):
        ws_sum.write(i, 0, item['Category'], wrap_fmt)
        ws_sum.write(i, 1, item['Score'], wrap_fmt)
    ws_sum.set_column('A:B', 30)

    # --- SHEET 2: DETAILED ISSUES ---
    ws = workbook.add_worksheet("Detailed Audit")
    headers = list(df_issues.columns)
    
    # Write Headers
    for col, h in enumerate(headers):
        ws.write(0, col, h, header_fmt)
        
    # Write Rows
    for row_idx, row_data in enumerate(df_issues.values, 1):
        for col_idx, cell_value in enumerate(row_data):
            cell_format = wrap_fmt
            
            # Special formatting for Priority Column
            if headers[col_idx] == "Priority":
                if "High" in str(cell_value): cell_format = prio_high
                elif "Medium" in str(cell_value): cell_format = prio_med
                else: cell_format = prio_info
            
            # Special formatting for Technical Details (Code font)
            elif headers[col_idx] == "Technical Breakdown (URLs & Stats)":
                cell_format = code_fmt
                
            ws.write(row_idx, col_idx, cell_value, cell_format)

    # Column Widths
    ws.set_column('A:A', 15) # Category
    ws.set_column('B:B', 15) # Priority
    ws.set_column('C:C', 30) # Issue Name
    ws.set_column('D:D', 40) # Description
    ws.set_column('E:E', 80) # Technical Details (Very Wide)
    ws.set_column('F:F', 40) # Help Link

    workbook.close()
    return output.getvalue()

# --- UI ---
st.title("🚀 Lighthouse Audit Pro")
st.markdown("Generates a **clean, categorized, and prioritized** Excel report identical to Lighthouse findings.")

with st.form("main_form"):
    col1, col2 = st.columns([3,1])
    url_input = col1.text_input("Website URL", "https://example.com")
    device_type = col2.selectbox("Device", ["mobile", "desktop"])
    api_key = st.text_input("Google API Key (Optional)", type="password")
    
    submitted = st.form_submit_button("Run Professional Audit")

if submitted:
    with st.spinner("Connecting to Google Lighthouse... parsing categories... formatting data..."):
        summary, df, err = run_audit_and_process(url_input, api_key, device_type)
        
        if err:
            st.error(err)
        else:
            # Metrics Display
            st.subheader("📊 Executive Scores")
            cols = st.columns(len(summary))
            for idx, item in enumerate(summary):
                cols[idx].metric(item['Category'], item['Score'])
            
            # Preview
            st.subheader("🚩 Top Priority Issues")
            st.dataframe(df[df['Priority'].str.contains("High")].head(5), use_container_width=True)
            
            # Download
            excel_file = create_client_excel(summary, df)
            st.download_button(
                "📥 Download Client-Ready Excel Report",
                data=excel_file,
                file_name=f"Lighthouse_Audit_{device_type}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
