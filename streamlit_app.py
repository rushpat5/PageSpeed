import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION (Dejan Style)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PageSpeed Forensics", 
    layout="wide", 
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* Force Light Mode & Clean Typography */
    :root { --primary-color: #1a7f37; --background-color: #ffffff; --secondary-background-color: #f6f8fa; --text-color: #24292e; --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
    .stApp { background-color: #ffffff; color: #24292e; }
    
    h1, h2, h3, h4 { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #000000 !important; letter-spacing: -0.3px; }
    p, li, span, div { color: #24292e; }
    a { color: #0969da; text-decoration: none; }
    
    /* Custom Components */
    .metric-card {
        background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02); margin-bottom: 10px;
    }
    .metric-val { font-size: 1.8rem; font-weight: 700; color: #1a7f37; }
    .metric-lbl { font-size: 0.85rem; color: #586069; text-transform: uppercase; letter-spacing: 0.5px; }
    
    /* Code Snippet Box */
    .code-box {
        background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 10px;
        font-family: monospace; font-size: 0.85rem; color: #cf222e; margin: 10px 0;
    }
    
    /* Sidebar & Inputs */
    section[data-testid="stSidebar"] { background-color: #f6f8fa; border-right: 1px solid #d0d7de; }
    .stTextInput input { background-color: #ffffff !important; border: 1px solid #d0d7de !important; color: #24292e !important; }
    
    /* Hide Streamlit elements */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} 
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. KNOWLEDGE BASE (THE "HOW TO FIX" ENGINE)
# -----------------------------------------------------------------------------

AUDIT_GUIDES = {
    "unused-css-rules": """
    **🛠️ The Fix:**
    1.  **Split CSS:** Don't load one giant `style.css`. Split it into `critical.css` (header/hero) and `footer.css`.
    2.  **Remove Libraries:** Are you loading all of Bootstrap but only using the grid? Switch to Tailwind or custom Flexbox.
    3.  **Code Snippet:** Use `coverage` tool in Chrome DevTools to identify red lines (unused bytes).
    """,
    "unused-javascript": """
    **🛠️ The Fix:**
    1.  **Code Splitting:** Use Webpack/Vite to split bundles. Only load JS needed for the current route.
    2.  **Defer:** Add `defer` attribute to non-critical scripts.
    3.  **Lazy Load:** Don't load Chatbots or Analytics until the user scrolls.
    """,
    "modern-image-formats": """
    **🛠️ The Fix:**
    1.  **Convert:** Change PNG/JPG to **WebP** or **AVIF**.
    2.  **Automation:** Use a CDN (Cloudflare/Cloudinary) or a WordPress plugin (Smush/Imagify) to do this automatically.
    """,
    "render-blocking-resources": """
    **🛠️ The Fix:**
    1.  **Inlining:** Inline Critical CSS (First 1000px of page) into the `<head>`.
    2.  **Defer:** `<script src="..." defer></script>`
    3.  **Async:** `<link rel="stylesheet" href="..." media="print" onload="this.media='all'">`
    """,
    "server-response-time": """
    **🛠️ The Fix:**
    1.  **Cache:** Implement Redis/Varnish caching on the server.
    2.  **Database:** Check slow SQL queries.
    3.  **CDN:** Ensure your HTML document isn't being generated from scratch on every visit (TTFB).
    """
}

# -----------------------------------------------------------------------------
# 3. LOGIC ENGINE
# -----------------------------------------------------------------------------

def run_pagespeed(url, strategy, api_key=None):
    if not url.startswith("http"): url = "https://" + url
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}&category=performance&category=seo"
    if api_key: api_url += f"&key={api_key}"
    
    try:
        response = requests.get(api_url, timeout=90)
        if response.status_code == 200:
            return response.json(), None
        else:
            try: err = response.json().get('error', {}).get('message', 'Unknown error')
            except: err = f"Status {response.status_code}"
            return None, f"API Error: {err}"
    except Exception as e:
        return None, str(e)

def parse_crux(data):
    metrics = data.get("loadingExperience", {}).get("metrics", {})
    if not metrics: return None
    return {
        "LCP": metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
        "INP": metrics.get("INTERACTION_TO_NEXT_PAINT", {}).get("percentile", 0),
        "CLS": metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile", 0) / 100,
        "FCP": metrics.get("FIRST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
    }

def get_lcp_element(lighthouse):
    """Finds the exact HTML element causing LCP."""
    audit = lighthouse.get("audits", {}).get("largest-contentful-paint-element", {})
    details = audit.get("details", {})
    if details.get("items"):
        item = details["items"][0]
        node = item.get("node", {})
        return {
            "Score": audit.get("displayValue"),
            "Snippet": node.get("snippet", "Unknown"),
            "Selector": node.get("selector", "Unknown"),
            "NodeLabel": node.get("nodeLabel", "Unknown")
        }
    return None

def process_opportunity(audit):
    """
    Extracts the specific file table for a failed audit.
    """
    details = audit.get("details", {})
    if not details or "items" not in details:
        return None, 0

    items = details["items"]
    # Sum up potential savings if available
    total_savings = audit.get("details", {}).get("overallSavingsBytes", 0)
    
    # Process rows
    processed = []
    for item in items:
        row = {}
        # Extract URL
        if "url" in item: row["File"] = item["url"]
        elif "source" in item and "url" in item["source"]: row["File"] = item["source"]["url"]
        else: row["File"] = str(item.get("label", "Unknown resource"))
        
        # Extract Size
        if "totalBytes" in item: row["Size"] = f"{item['totalBytes']/1024:.1f} KB"
        elif "transferSize" in item: row["Size"] = f"{item['transferSize']/1024:.1f} KB"
        
        # Extract Wasted/Savings
        if "wastedBytes" in item: row["Wasted"] = f"{item['wastedBytes']/1024:.1f} KB"
        elif "wastedMs" in item: row["Delay"] = f"{item['wastedMs']:.0f} ms"
        
        processed.append(row)
        
    return pd.DataFrame(processed), total_savings

def get_actionable_audits(lighthouse):
    audits = lighthouse.get("audits", {})
    actionable = []
    
    for key, audit in audits.items():
        # Only care if it has a score < 0.9 AND has a details table
        if audit.get("score") is not None and audit.get("score") < 0.9:
            df, savings = process_opportunity(audit)
            
            # If we successfully extracted a table of files
            if df is not None and not df.empty:
                actionable.append({
                    "id": key,
                    "title": audit.get("title"),
                    "score": audit.get("score"),
                    "savings_bytes": savings,
                    "description": audit.get("description").split('[')[0], # Clean markdown
                    "data": df
                })
    
    # Sort by impact (lowest score first)
    return sorted(actionable, key=lambda x: x['score'])

# -----------------------------------------------------------------------------
# 3. SIDEBAR CONFIG
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Forensics Config")
    strategy = st.selectbox("Emulation", ["mobile", "desktop"], index=0)
    
    st.markdown("""
    <div style="margin-bottom: 5px;">
        <a href="https://developers.google.com/speed/docs/insights/v5/get-started" target="_blank" style="font-size: 0.85rem; color: #0969da; text-decoration: none;">
            🔑 Get Free API Key
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input("Google API Key", type="password", help="Prevent 429 Errors")
    
    st.markdown("---")
    st.markdown("### 📚 Guide")
    st.info("This tool provides specific file paths and coding advice. Use the 'Developer Action Plan' below to assign tasks to your engineering team.")

# -----------------------------------------------------------------------------
# 4. MAIN DASHBOARD
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensics")
st.markdown("### The Developer's Performance Audit")

col_in1, col_in2 = st.columns([3, 1])
with col_in1:
    url_input = st.text_input("Target URL", placeholder="https://example.com", label_visibility="collapsed")
with col_in2:
    run_btn = st.button("Start Forensic Audit", type="primary", use_container_width=True)

if run_btn and url_input:
    with st.spinner("Connecting to Google Lighthouse Infrastructure..."):
        data, err = run_pagespeed(url_input, strategy, api_key)
        
    if err:
        st.error(err)
    else:
        lh = data.get("lighthouseResult", {})
        crux = parse_crux(data)
        
        # --- 1. THE SCORECARD ---
        st.subheader("1. Core Vitals Scorecard")
        
        if crux:
            c1, c2, c3, c4 = st.columns(4)
            
            def metric_box(col, label, val, unit, good_limit, bad_limit):
                color = "#1a7f37" # Green
                if val > bad_limit: color = "#d73a49" # Red
                elif val > good_limit: color = "#d29922" # Orange
                
                col.markdown(f"""
                <div class="metric-card" style="border-top: 4px solid {color}">
                    <div class="metric-val" style="color: {color}">{val}{unit}</div>
                    <div class="metric-lbl">{label}</div>
                </div>
                """, unsafe_allow_html=True)

            metric_box(c1, "LCP (Loading)", crux['LCP'], "s", 2.5, 4.0)
            metric_box(c2, "INP (Lag)", crux['INP'], "ms", 200, 500)
            metric_box(c3, "CLS (Shift)", crux['CLS'], "", 0.1, 0.25)
            metric_box(c4, "FCP (First Paint)", crux['FCP'], "s", 1.8, 3.0)
        else:
            st.info("No Field Data (CrUX) available for this URL. Showing Lab Data below.")

        # --- 2. LCP FORENSICS (The specific element) ---
        lcp_data = get_lcp_element(lh)
        if lcp_data:
            st.markdown("---")
            st.subheader("2. What is slowing down your load? (LCP)")
            col_lcp1, col_lcp2 = st.columns([1, 2])
            
            with col_lcp1:
                st.markdown(f"**LCP Time:** {lcp_data['Score']}")
                st.markdown("**The Culprit:** This specific element is the last thing to paint.")
            
            with col_lcp2:
                st.markdown("##### The LCP Element Code:")
                st.code(lcp_data['Snippet'], language="html")
                st.caption(f"Selector: {lcp_data['Selector']}")

        # --- 3. DEVELOPER ACTION PLAN (The Fixes) ---
        st.markdown("---")
        st.subheader("3. Developer Action Plan")
        st.markdown("These are specific, prioritized fixes based on file analysis.")
        
        actions = get_actionable_audits(lh)
        
        if not actions:
            st.success("✅ Clean Audit! No major technical debt found.")
        
        for act in actions:
            # Determine icon color
            icon = "🔴" if act['score'] < 0.5 else "🟡"
            
            # Label
            label = f"{icon} {act['title']}"
            if act['savings_bytes'] > 0:
                label += f" (Save {act['savings_bytes']/1024:.0f} KB)"
            
            with st.expander(label):
                # 1. The Description
                st.markdown(f"**Impact:** {act['description']}")
                
                # 2. The Custom Fix Guide (If available)
                if act['id'] in AUDIT_GUIDES:
                    st.markdown(f"<div class='code-box'>{AUDIT_GUIDES[act['id']]}</div>", unsafe_allow_html=True)
                
                # 3. The Evidence Table
                st.markdown("**Files causing this issue:**")
                st.dataframe(
                    act['data'], 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "File": st.column_config.LinkColumn("Resource URL"),
                        "Size": st.column_config.TextColumn("Size"),
                        "Wasted": st.column_config.ProgressColumn(
                            "Wasted Bytes", 
                            format="%s", 
                            min_value=0, 
                            max_value=int(act['data']['Wasted'].str.replace(' KB','').astype(float).max() if 'Wasted' in act['data'] else 100)
                        )
                    }
                )
