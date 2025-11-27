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
# 2. THE "NUCLEAR" PARSER (Fixes all object/json issues)
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

def recursive_clean(val):
    """
    The 'Universal Unpacker'. It recursively digs into dictionaries
    to find the single string or number that matters.
    """
    if val is None: return ""
    
    if isinstance(val, dict):
        # Priority 1: URLs
        if 'url' in val: return val['url']
        # Priority 2: HTML Snippets (Nodes)
        if 'snippet' in val: return val['snippet']
        if 'selector' in val: return val['selector']
        # Priority 3: Source Locations
        if 'source' in val: return recursive_clean(val['source'])
        if 'file' in val: return f"{val.get('file','')} (L{val.get('line',0)})"
        # Priority 4: Generic Values
        if 'value' in val: return str(val['value'])
        # Priority 5: Labels
        if 'label' in val: return val['label']
        
        # Fallback: Join all string values
        return " ".join([str(v) for k,v in val.items() if isinstance(v, (str, int, float))])

    if isinstance(val, list):
        return ", ".join([str(recursive_clean(v)) for v in val])

    return val

def format_cell(key, val):
    """Auto-formats numbers based on the column key."""
    clean_val = recursive_clean(val)
    
    # Try to keep numbers as numbers for sorting, unless they need units
    try:
        num_val = float(clean_val)
        lower_key = str(key).lower()
        
        # Bytes -> KB
        if any(x in lower_key for x in ['bytes', 'size', 'transfer']):
            return f"{num_val / 1024:.1f} KB"
        
        # Milliseconds -> Sec/ms
        if any(x in lower_key for x in ['time', 'ms', 'duration', 'wasted']):
            if num_val >= 1000: return f"{num_val/1000:.2f} s"
            return f"{num_val:.0f} ms"
            
        return num_val # Return plain number if no unit detected
    except:
        return clean_val # Return text

def process_audit_details(audit):
    details = audit.get("details", {})
    
    # --- TABLE MODE ---
    if 'items' in details:
        raw_items = details['items']
        headings = details.get('headings', [])
        
        if not raw_items: return None
        
        # 1. Map Headers {key: "Human Label"}
        header_map = {}
        if headings:
            for h in headings:
                # IMPORTANT: 'text' is sometimes nested? No, usually 'text' or 'label'
                label = h.get('text', h.get('label', h.get('key')))
                header_map[h.get('key')] = str(label)
        else:
            # Auto-gen headers if missing
            for k in raw_items[0].keys():
                header_map[k] = k.replace('rtt', 'RTT').title()

        processed_rows = []
        
        for item in raw_items:
            row = {}
            # Main Item Processing
            for key, label in header_map.items():
                val = item.get(key)
                row[label] = format_cell(key, val)
            
            # SUB-ITEMS (The hidden "Grouped" data)
            if 'subItems' in item and item['subItems']:
                # Add the parent row
                processed_rows.append(row)
                # Add children rows with indentation
                for sub in item['subItems']['items']:
                    sub_row = {}
                    for key, label in header_map.items():
                        val = sub.get(key)
                        formatted = format_cell(key, val)
                        # Indent the first column to show hierarchy
                        if key == list(header_map.keys())[0]:
                            sub_row[label] = f" ↳ {formatted}"
                        else:
                            sub_row[label] = formatted
                    processed_rows.append(sub_row)
            else:
                processed_rows.append(row)
                
        return pd.DataFrame(processed_rows)

    # --- CRITICAL CHAINS MODE ---
    elif details.get("type") == "criticalrequestchain":
        chains = details.get("chains", {})
        flat = []
        def traverse(node, depth):
            for k, v in node.items():
                req = v.get("request", {})
                flat.append({
                    "Dependency": ("— " * depth) + str(req.get("url", "Unknown")),
                    "Size": f"{req.get('transferSize',0)/1024:.1f} KB",
                    "Time": f"{req.get('startTime',0)*1000:.0f} ms"
                })
                if "children" in v: traverse(v["children"], depth+1)
        traverse(chains, 0)
        return pd.DataFrame(flat)

    return None

def get_failed_audits(lighthouse):
    audits = lighthouse.get("audits", {})
    failed = []
    
    for key, audit in audits.items():
        score = audit.get("score")
        
        # FAIL CONDITION: Score < 0.9 OR (Manual/Info AND Has Data)
        is_fail = (score is not None and score < 0.9)
        has_data = bool(audit.get("details", {}).get("items") or audit.get("details", {}).get("chains"))
        
        if is_fail or (score is None and has_data):
            # Clean Links from Description
            desc = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', audit.get("description", ""))
            
            failed.append({
                "title": audit.get("title"),
                "score": score if score is not None else 0,
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
    <b>Forensic Deep Dive:</b> We parse nested Lighthouse Objects, Source Maps, and Dependency Trees to reveal the exact files causing lag.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. MAIN INTERFACE
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensics")
st.markdown("### Core Web Vitals & Critical Path Analysis")

with st.expander("How this tool differs from Google PSI", expanded=False):
    st.markdown("""
    **1. Separation of Concerns:** We strictly separate **User Data (CrUX)** from **Lab Simulation**.
    **2. Universal Unpacker:** We resolve complex JSON objects (Nodes, Source Lines) into readable text.
    **3. 3rd Party Attribution:** We highlight external scripts blocking the CPU.
    """)

st.write("")
url_input = st.text_input("Target URL", placeholder="https://example.com")
run_btn = st.button("Run Forensic Audit", type="primary")

if run_btn and url_input:
    
    with st.spinner(f"Querying Google API ({strategy})... this takes ~15-30s"):
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
                st.markdown("Issues below are sorted by impact. Click to expand technical details.")

            failures = get_failed_audits(lh)
            
            for fail in failures:
                icon = "🔴" if (fail['score'] is not None and fail['score'] < 0.5) else "🟡"
                if fail['score'] == 0 and not fail.get('displayValue'): icon = "ℹ️"
                
                label = f"{icon} {fail['title']}"
                if fail.get('displayValue'): label += f" — {fail['displayValue']}"
                
                with st.expander(label):
                    st.markdown(f"**Impact:** {fail['description']}")
                    
                    if fail['df'] is not None and not fail['df'].empty:
                        # Display clean table
                        st.dataframe(fail['df'], use_container_width=True, hide_index=True)
                    else:
                        st.caption("No granular file data available via API.")
