import streamlit as st
import requests
import pandas as pd
import numpy as np
import re

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION (Strict Dejan Academic Theme)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PageSpeed Forensic Lab", 
    layout="wide", 
    page_icon="🔬",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* --- FORCE LIGHT MODE & ACADEMIC TYPOGRAPHY --- */
    :root {
        --primary-color: #1a7f37; /* GitHub Green */
        --background-color: #ffffff;
        --secondary-background-color: #f6f8fa; /* Light Gray Sidebar */
        --text-color: #24292e;
        --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }

    .stApp {
        background-color: #ffffff;
        color: #24292e;
    }
    
    /* --- HEADINGS --- */
    h1, h2, h3, h4 {
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 600;
        letter-spacing: -0.3px;
        color: #111;
    }
    
    /* --- METRIC CARDS (Clean & Boxed) --- */
    .metric-container {
        background-color: #ffffff;
        border: 1px solid #e1e4e8;
        border-radius: 6px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .metric-val {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 5px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #586069;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
    }
    .good { color: #1a7f37; }
    .needs-improvement { color: #d29922; }
    .poor { color: #d73a49; }

    /* --- PROTOCOL BOX (The Fix Guide) --- */
    .protocol-box {
        background-color: #f6f8fa;
        border-left: 4px solid #0969da;
        padding: 15px;
        margin: 10px 0;
        font-size: 0.9rem;
        border-radius: 0 4px 4px 0;
    }
    .protocol-header {
        font-weight: 700;
        color: #0969da;
        margin-bottom: 5px;
        display: block;
    }

    /* --- INPUT FIELDS --- */
    .stTextInput input {
        background-color: #f6f8fa !important;
        border: 1px solid #d0d7de !important;
        color: #24292e !important;
        border-radius: 6px;
    }
    .stTextInput input:focus {
        border-color: #0969da !important;
        box-shadow: 0 0 0 3px rgba(9, 105, 218, 0.1) !important;
    }

    /* --- SIDEBAR --- */
    section[data-testid="stSidebar"] {
        background-color: #f6f8fa;
        border-right: 1px solid #d0d7de;
    }
    section[data-testid="stSidebar"] * {
        color: #24292e !important;
    }

    /* Hide Streamlit Bloat */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    
    /* Table borders */
    [data-testid="stDataFrame"] { border: 1px solid #e1e4e8; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. THE FIX PROTOCOL DATABASE (Expert Knowledge Injection)
# -----------------------------------------------------------------------------
FIX_PROTOCOLS = {
    "unused-javascript": """
    **Protocol:** Code Splitting & Tree Shaking
    1.  **Identification:** The files listed below contain code that is downloaded but never executed.
    2.  **Action:** Use `React.lazy()` or Webpack's `SplitChunksPlugin` to break these bundles.
    3.  **Target:** Move non-critical JS (e.g., chat widgets, heavy footer logic) to load only on interaction/scroll.
    """,
    "unused-css-rules": """
    **Protocol:** Critical CSS Extraction
    1.  **Action:** Extract the CSS required for "Above the Fold" content and inline it in the `<head>`.
    2.  **Defer:** Load the rest of the CSS asynchronously using `<link rel="preload" as="style" onload="this.rel='stylesheet'">`.
    3.  **Tooling:** Use `PurgeCSS` to remove unused classes from frameworks like Bootstrap or Tailwind.
    """,
    "render-blocking-resources": """
    **Protocol:** Elimination of Render Blockers
    1.  **Concept:** The browser pauses painting to read these files.
    2.  **JS Fix:** Add `defer` or `async` attributes to these script tags.
    3.  **CSS Fix:** Inline critical CSS and lazy-load the rest.
    """,
    "modern-image-formats": """
    **Protocol:** Next-Gen Formats
    1.  **Action:** Convert PNG/JPEG to **WebP** or **AVIF**.
    2.  **Impact:** WebP is typically 26% smaller than PNGs.
    3.  **Implementation:** Use the `<picture>` tag with fallback or a CDN auto-optimizer (Cloudflare/ImageKit).
    """,
    "properly-size-images": """
    **Protocol:** Responsive Sizing
    1.  **Problem:** Serving a 4000px wide image into a 300px wide mobile container.
    2.  **Action:** Use `srcset` and `sizes` attributes to serve the correct dimension for the device viewport.
    """,
    "server-response-time": """
    **Protocol:** TTFB Optimization
    1.  **Backend:** Database queries are likely slow. Check slow query logs.
    2.  **Caching:** Implement server-side caching (Redis/Memcached) or Page Caching.
    3.  **CDN:** Ensure the HTML doc itself is cached at the edge if static.
    """,
    "third-party-summary": """
    **Protocol:** Vendor Governance
    1.  **Action:** These external scripts are blocking the main thread.
    2.  **Mitigation:** Self-host the scripts if possible, or use a "Facade" (load a fake image first, load the heavy script only on mouseover).
    """
}

# -----------------------------------------------------------------------------
# 3. CORE LOGIC ENGINE
# -----------------------------------------------------------------------------

def run_pagespeed(url, strategy, api_key=None):
    if not url.startswith("http"): url = "https://" + url
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}&category=performance&category=seo"
    if api_key: api_url += f"&key={api_key}"
    
    try:
        response = requests.get(api_url, timeout=60)
        if response.status_code == 200:
            return response.json(), None
        else:
            try: err = response.json().get('error', {}).get('message', 'Unknown')
            except: err = f"Status {response.status_code}"
            return None, f"Google API Error: {err}"
    except Exception as e:
        return None, f"Connection Error: {str(e)}"

def parse_crux(data):
    # Extract Real User Data (The Source of Truth)
    metrics = data.get("loadingExperience", {}).get("metrics", {})
    if not metrics: return None
    return {
        "LCP": metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
        "INP": metrics.get("INTERACTION_TO_NEXT_PAINT", {}).get("percentile", 0),
        "CLS": metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile", 0) / 100,
        "FCP": metrics.get("FIRST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
    }

def clean_value(val):
    """Recursively unpacks Lighthouse JSON objects."""
    if val is None: return ""
    if isinstance(val, dict):
        if 'url' in val: return val['url']
        if 'snippet' in val: return val['snippet']
        if 'value' in val: return str(val['value'])
        if 'source' in val: return clean_value(val['source'])
        return str(val)
    if isinstance(val, list):
        return ", ".join([clean_value(v) for v in val])
    return val

def format_col(key, val):
    """Auto-detects bytes/ms and formats human-readably."""
    try:
        if isinstance(val, (int, float)):
            k = str(key).lower()
            if 'byte' in k or 'size' in k or 'transfer' in k:
                return f"{val / 1024:.1f} KB"
            if 'time' in k or 'ms' in k or 'dur' in k:
                if val > 1000: return f"{val/1000:.2f} s"
                return f"{val:.0f} ms"
    except: pass
    return clean_value(val)

def extract_details(audit):
    """Extracts granular file lists from audits."""
    details = audit.get("details", {})
    
    # 1. Standard Items Table
    if 'items' in details:
        items = details['items']
        if not items: return None
        
        # Get Headers
        headers = details.get('headings', [])
        # If no headers, guess from keys
        if not headers: 
            headers = [{"key": k, "text": k} for k in items[0].keys()]
            
        rows = []
        for item in items:
            row = {}
            for h in headers:
                key = h.get('key')
                label = h.get('text', h.get('label', key))
                val = item.get(key)
                row[label] = format_col(key, val)
            
            # Handle Sub-items (Groups)
            if 'subItems' in item and item['subItems'].get('items'):
                rows.append(row) # Parent
                for sub in item['subItems']['items']:
                    sub_row = {}
                    for h in headers:
                        k = h.get('key')
                        l = h.get('text', k)
                        # Indent first col
                        v = format_col(k, sub.get(k))
                        if k == headers[0].get('key'): sub_row[l] = f"↳ {v}"
                        else: sub_row[l] = v
                    rows.append(sub_row)
            else:
                rows.append(row)
        return pd.DataFrame(rows)

    return None

def get_grouped_audits(lighthouse):
    """Groups audits into Engineering Verticals."""
    audits = lighthouse.get("audits", {})
    
    # Definitions
    groups = {
        "JavaScript & CPU": ["unused-javascript", "long-tasks", "mainthread-work-breakdown", "bootup-time", "script-treemap-data", "third-party-summary"],
        "CSS & Design": ["unused-css-rules", "render-blocking-resources", "cls", "non-composited-animations", "layout-shift-elements"],
        "Assets (Images/Fonts)": ["modern-image-formats", "properly-size-images", "efficient-animated-content", "offscreen-images", "uses-optimized-images"],
        "Server & Network": ["server-response-time", "uses-text-compression", "redirects", "uses-http2", "total-byte-weight"]
    }
    
    output = {k: [] for k in groups.keys()}
    output["Other"] = [] # Fallback
    
    for key, audit in audits.items():
        score = audit.get("score")
        # Filter: Only failures (<0.9) or Informative with data
        has_data = bool(audit.get("details", {}).get("items"))
        is_relevant = (score is not None and score < 0.9) or (score is None and has_data)
        
        if is_relevant:
            # Clean description
            desc = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', audit.get("description", ""))
            
            # Estimate Savings
            savings = audit.get("details", {}).get("overallSavingsMs", 0)
            
            item = {
                "id": key,
                "title": audit.get("title"),
                "score": score,
                "displayValue": audit.get("displayValue"),
                "description": desc,
                "savings": savings,
                "data": extract_details(audit)
            }
            
            # Place in group
            found = False
            for g_name, keys in groups.items():
                if key in keys:
                    output[g_name].append(item)
                    found = True
                    break
            if not found:
                output["Other"].append(item)
                
    # Sort each group by score
    for g in output:
        output[g] = sorted(output[g], key=lambda x: (x['score'] if x['score'] is not None else 1))
        
    return output

# -----------------------------------------------------------------------------
# 4. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Engine Config")
    strategy = st.selectbox("Device Emulation", ["mobile", "desktop"], index=0)
    
    st.markdown("""
    <div style="margin-bottom: 5px;">
        <a href="https://developers.google.com/speed/docs/insights/v5/get-started" target="_blank" style="font-size: 0.85rem; color: #0969da; text-decoration: none;">
            🔑 Get Free API Key
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input("Google API Key", type="password", help="Required to avoid 429 Errors.")
    
    st.markdown("---")
    st.markdown("### 🧪 Methodology")
    st.markdown("""
    **Forensic Analysis v2**
    <div class="tech-note">
    <b>Categorization:</b> We segment issues by tech stack (JS vs CSS vs Server).
    <br><b>Protocols:</b> We inject specific engineering instructions for each failure type.
    <br><b>Extraction:</b> Deep JSON parsing identifies the specific lines of code causing lag.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. MAIN INTERFACE
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensic Lab")
st.markdown("### Technical Performance Audit & Remediation Plan")

url_input = st.text_input("Target URL Endpoint", placeholder="https://example.com")
run_btn = st.button("Initialize Forensic Scan", type="primary")

if run_btn and url_input:
    
    with st.spinner("Connecting to Lighthouse... Extracting Traces... Analyzing Critical Path..."):
        data, err = run_pagespeed(url_input, strategy, api_key)
        
        if err:
            st.error(err)
        else:
            lh = data.get("lighthouseResult", {})
            crux = parse_crux(data)
            
            # --- SECTION 1: EXECUTIVE VITALS ---
            st.markdown("---")
            st.markdown("### 1. Executive Vitals (Real User Experience)")
            
            if crux:
                c1, c2, c3, c4 = st.columns(4)
                
                def render_metric(col, label, val, unit, thresholds):
                    # thresholds = (good, poor)
                    status_color = "good"
                    if val > thresholds[1]: status_color = "poor"
                    elif val > thresholds[0]: status_color = "needs-improvement"
                    
                    col.markdown(f"""
                    <div class="metric-container" style="border-top: 4px solid var(--{status_color}-color, #586069);">
                        <div class="metric-val {status_color}">{val}{unit}</div>
                        <div class="metric-label">{label}</div>
                    </div>
                    """, unsafe_allow_html=True)

                render_metric(c1, "LCP (Loading)", crux['LCP'], "s", (2.5, 4.0))
                render_metric(c2, "INP (Lag)", crux['INP'], "ms", (200, 500))
                render_metric(c3, "CLS (Shift)", crux['CLS'], "", (0.1, 0.25))
                render_metric(c4, "FCP (First Paint)", crux['FCP'], "s", (1.8, 3.0))
            else:
                st.info("No CrUX data available. Showing Lab Simulation only.")

            # --- SECTION 2: FORENSIC DEEP DIVE (GROUPED) ---
            st.markdown("---")
            st.markdown("### 2. Technical Remediation Plan")
            st.markdown("Issues are categorized by engineering vertical for easier assignment.")
            
            grouped_findings = get_grouped_audits(lh)
            
            # Create Tabs for Verticals
            tabs = st.tabs([
                "📜 JavaScript & CPU", 
                "🎨 CSS & Design", 
                "🖼️ Assets (Images)", 
                "🖥️ Server / Network",
                "📎 Other"
            ])
            
            # Map tabs to dictionary keys
            tab_map = {
                0: "JavaScript & CPU",
                1: "CSS & Design",
                2: "Assets (Images)",
                3: "Server & Network",
                4: "Other"
            }
            
            # Iterate through tabs and populate
            for i, tab in enumerate(tabs):
                category = tab_map[i]
                findings = grouped_findings.get(category, [])
                
                with tab:
                    if not findings:
                        st.success(f"✅ Clean! No issues detected in {category}.")
                    
                    for item in findings:
                        # Icon
                        icon = "🔴" if (item['score'] is not None and item['score'] < 0.5) else "🟡"
                        if item['score'] is None: icon = "ℹ️"
                        
                        # Title construction
                        title = f"{icon} {item['title']}"
                        if item.get('displayValue'): title += f" — {item['displayValue']}"
                        
                        with st.expander(title):
                            # 1. Description
                            st.markdown(f"**Impact:** {item['description']}")
                            
                            # 2. THE PROTOCOL (Fix Guide)
                            if item['id'] in FIX_PROTOCOLS:
                                st.markdown(f"""
                                <div class="protocol-box">
                                <span class="protocol-header">⚡ ENGINEERING PROTOCOL</span>
                                {FIX_PROTOCOLS[item['id']]}
                                </div>
                                """, unsafe_allow_html=True)
                            
                            # 3. Granular Data Table
                            if item['data'] is not None and not item['data'].empty:
                                st.markdown("**Forensic Evidence:**")
                                st.dataframe(
                                    item['data'],
                                    use_container_width=True,
                                    hide_index=True
                                )
                            else:
                                st.caption("No specific file trace available.")
