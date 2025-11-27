import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PageSpeed Forensics", 
    layout="wide", 
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* --- FORCE LIGHT MODE --- */
    :root { --primary-color: #1a7f37; --background-color: #ffffff; --secondary-background-color: #f6f8fa; --text-color: #24292e; --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
    .stApp { background-color: #ffffff; color: #24292e; }
    h1, h2, h3, h4, .markdown-text-container { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #000000 !important; letter-spacing: -0.3px; }
    p, li, span, div { color: #24292e; }
    a { color: #0969da; text-decoration: none; }
    section[data-testid="stSidebar"] { background-color: #f6f8fa; border-right: 1px solid #d0d7de; }
    section[data-testid="stSidebar"] * { color: #24292e !important; }
    .stTextInput input { background-color: #f6f8fa !important; border: 1px solid #d0d7de !important; color: #24292e !important; }
    .stTextInput input:focus { border-color: #1a7f37 !important; box-shadow: 0 0 0 1px #1a7f37 !important; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1a7f37 !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #586069 !important; }
    [data-testid="stDataFrame"] { border: 1px solid #e1e4e8; }
    .tech-note { font-size: 0.85rem; color: #57606a; background-color: #f3f4f6; border-left: 3px solid #0969da; padding: 12px; margin-top: 8px; margin-bottom: 15px; border-radius: 0 4px 4px 0; line-height: 1.5; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} 
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. DATA EXTRACTION ENGINE (REHAULED)
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
            try:
                err = response.json().get('error', {}).get('message', 'Unknown error')
            except:
                err = f"Status {response.status_code}"
            return None, f"API Error: {err}"
    except Exception as e:
        return None, str(e)

def parse_crux(data):
    loading = data.get("loadingExperience", {})
    metrics = loading.get("metrics", {})
    if not metrics: return None
    return {
        "LCP": metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
        "INP": metrics.get("INTERACTION_TO_NEXT_PAINT", {}).get("percentile", 0),
        "CLS": metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile", 0) / 100,
        "FCP": metrics.get("FIRST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
    }

def safe_extract_value(cell):
    """
    Smart extraction that handles Lighthouse's nested object types.
    """
    if cell is None:
        return ""
    
    # Primitive types
    if isinstance(cell, (str, int, float, bool)):
        return cell
        
    # Dictionary types (The cause of [object Object])
    if isinstance(cell, dict):
        # 1. URL Type
        if 'url' in cell:
            return cell['url']
        
        # 2. Source Location (File:Line)
        if 'source' in cell:
            # Recursive check if source is also a dict
            src = cell['source']
            if isinstance(src, dict):
                return f"{src.get('url', 'Unknown')}:{src.get('line', 0)}"
            return src
            
        # 3. Node/Element (Snippet)
        if 'snippet' in cell:
            return cell['snippet']
        if 'selector' in cell:
            return cell['selector']
            
        # 4. Numeric Value wrapper
        if 'value' in cell:
            return cell['value']
            
        # 5. Thumbnail
        if 'type' in cell and cell['type'] == 'thumbnail':
            return "(Image)"

    # Fallback
    return str(cell)

def format_column(header_key, val):
    """Formats numbers based on column headers (Bytes -> KB, Ms -> Seconds)"""
    try:
        if isinstance(val, (int, float)):
            header_lower = str(header_key).lower()
            
            # Size / Bytes -> KB
            if any(x in header_lower for x in ['size', 'bytes', 'transfer']):
                return f"{val / 1024:.1f} KB"
            
            # Time / Ms -> Seconds or Ms
            if any(x in header_lower for x in ['time', 'ms', 'duration', 'wasted']):
                if val > 1000:
                    return f"{val/1000:.2f} s"
                return f"{val:.0f} ms"
                
    except:
        pass
    return val

def process_audit_details(audit):
    details = audit.get("details", {})
    
    # --- TABLE FORMAT ---
    if 'items' in details:
        items = details['items']
        headings = details.get('headings', [])
        
        if not items: return None
        
        # If headings exist, strictly map columns
        if headings:
            processed_rows = []
            for item in items:
                row = {}
                for h in headings:
                    # Get Key and Label
                    key = h.get('key')
                    label = h.get('text', h.get('label', str(key))) # Fallback labels
                    
                    # Extract raw value using the key
                    raw_val = item.get(key)
                    
                    # Unpack Object
                    clean_val = safe_extract_value(raw_val)
                    
                    # Format Number
                    formatted_val = format_column(key, clean_val)
                    
                    row[label] = formatted_val
                processed_rows.append(row)
            return pd.DataFrame(processed_rows)
            
        # Fallback: No headings, just dump items flatten
        else:
            return pd.json_normalize(items)

    # --- CRITICAL CHAINS (Tree) ---
    elif details.get("type") == "criticalrequestchain":
        chains = details.get("chains", {})
        flat = []
        def traverse(node, depth):
            for k, v in node.items():
                req = v.get("request", {})
                flat.append({
                    "Resource": req.get("url"),
                    "Transfer": f"{req.get('transferSize',0)/1024:.1f} KB",
                    "Time": f"{req.get('startTime',0)*1000:.0f} ms"
                })
                if "children" in v: traverse(v["children"], depth+1)
        traverse(chains, 0)
        return pd.DataFrame(flat) if flat else None

    return None

def get_failed_audits(lighthouse):
    audits = lighthouse.get("audits", {})
    failed = []
    
    # Priority Order
    for key, audit in audits.items():
        score = audit.get("score")
        
        # We want to see:
        # 1. Failures (Score < 0.9)
        # 2. "Informative" items that have data tables (e.g. Diagnostics)
        # 3. Exclude things with no details
        
        has_details = bool(audit.get("details", {}).get("items") or audit.get("details", {}).get("chains"))
        is_bad = (score is not None and score < 0.9)
        
        if (is_bad or (score is None and has_details)):
            # Cleanup Description (Remove Markdown links)
            desc = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', audit.get("description", ""))
            
            failed.append({
                "title": audit.get("title"),
                "score": score if score is not None else 0, # Sort None as 0 (high priority)
                "displayValue": audit.get("displayValue"),
                "description": desc,
                "df": process_audit_details(audit)
            })
            
    return sorted(failed, key=lambda x: x['score'])

# -----------------------------------------------------------------------------
# 3. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Audit Config")
    strategy = st.selectbox("Device Emulation", ["mobile", "desktop"], index=0)
    
    st.markdown("""
    <div style="margin-bottom: 5px;">
        <a href="https://developers.google.com/speed/docs/insights/v5/get-started" target="_blank" style="font-size: 0.85rem; color: #0969da; text-decoration: none;">
            🔑 Get a Free Google API Key
        </a>
    </div>
    """, unsafe_allow_html=True)
    
    api_key = st.text_input("Google API Key", type="password", help="Required to bypass Google's 429 Quota limits.")
    
    st.markdown("---")
    st.markdown("""
    **Methodology:**
    <div class="tech-note">
    <b>Forensic Deep Dive:</b> We parse the raw Lighthouse JSON objects, unwrapping nested Source Maps and Nodes to reveal the actual file paths.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. MAIN INTERFACE
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensics")
st.markdown("### Core Web Vitals & Critical Path Analysis")

with st.expander("How this tool differs from Google PSI", expanded=False):
    st.markdown("""
    **1. Clean Data:** We strip away the confusing "Element" code blocks and give you clean URLs.
    **2. Smart Formatting:** Bytes are auto-converted to KB. Milliseconds to Seconds.
    **3. Deep Extraction:** We dig into the "Source Location" objects that standard parsers miss.
    """)

st.write("")
url_input = st.text_input("Target URL", placeholder="https://example.com")
run_btn = st.button("Run Forensic Audit", type="primary")

if run_btn and url_input:
    
    with st.spinner(f"Querying Google API ({strategy})..."):
        data, err = run_pagespeed(url_input, strategy, api_key)
        
        if err:
            st.error(err)
        else:
            lh = data.get("lighthouseResult", {})
            crux = parse_crux(data)
            
            # --- METRICS ---
            st.markdown("### 1. Real User Experience (CrUX)")
            if crux:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("LCP (Loading)", f"{crux['LCP']}s", delta_color="off" if crux['LCP']>2.5 else "normal")
                c2.metric("INP (Interaction)", f"{crux['INP']}ms", delta_color="off" if crux['INP']>200 else "normal")
                c3.metric("CLS (Visual)", f"{crux['CLS']}", delta_color="off" if crux['CLS']>0.1 else "normal")
                c4.metric("FCP (Start)", f"{crux['FCP']}s")
            else:
                st.info("No Field Data available.")

            st.markdown("---")
            st.markdown("### 2. Forensic Findings (Actionable)")
            
            # Gauge
            perf_score = lh.get("categories", {}).get("performance", {}).get("score", 0) * 100
            col_g, col_txt = st.columns([1, 4])
            with col_g:
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number", value = perf_score,
                    gauge = {'axis': {'range': [None, 100]}, 'bar': {'color': "#1a7f37" if perf_score >= 90 else "#d93025"}}
                ))
                fig.update_layout(height=150, margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig, use_container_width=True)
            with col_txt:
                st.markdown(f"**Performance Score: {perf_score:.0f}/100**")
                st.markdown("Issues listed below are sorted by impact. Fixing the top 3 usually resolves 80% of speed problems.")

            failures = get_failed_audits(lh)
            
            for fail in failures:
                # Icon
                icon = "🔴" if (fail['score'] is not None and fail['score'] < 0.5) else "🟡"
                if fail['score'] == 0 and not fail.get('displayValue'): icon = "ℹ️"
                
                label = f"{icon} {fail['title']}"
                if fail.get('displayValue'): label += f" — {fail['displayValue']}"
                
                with st.expander(label):
                    st.markdown(f"**Impact:** {fail['description']}")
                    
                    if fail['df'] is not None and not fail['df'].empty:
                        st.dataframe(fail['df'], use_container_width=True, hide_index=True)
                    else:
                        st.caption("No specific file breakdown available.")
