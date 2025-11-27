import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION (Dejan Style - Light Mode Forced)
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
    
    /* Typography */
    h1, h2, h3, h4, .markdown-text-container { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #000000 !important; letter-spacing: -0.3px; }
    p, li, span, div { color: #24292e; }
    a { color: #0969da; text-decoration: none; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #f6f8fa; border-right: 1px solid #d0d7de; }
    section[data-testid="stSidebar"] * { color: #24292e !important; }
    
    /* Inputs */
    .stTextInput input { background-color: #f6f8fa !important; border: 1px solid #d0d7de !important; color: #24292e !important; }
    .stTextInput input:focus { border-color: #1a7f37 !important; box-shadow: 0 0 0 1px #1a7f37 !important; }
    
    /* Metrics & Tables */
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1a7f37 !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #586069 !important; }
    [data-testid="stDataFrame"] { border: 1px solid #e1e4e8; }
    
    /* Tech Note */
    .tech-note { font-size: 0.85rem; color: #57606a; background-color: #f3f4f6; border-left: 3px solid #0969da; padding: 12px; margin-top: 8px; margin-bottom: 15px; border-radius: 0 4px 4px 0; line-height: 1.5; }

    /* Clean UI */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} 
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. LOGIC ENGINE
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
                err_msg = response.json().get('error', {}).get('message', 'Unknown error')
            except:
                err_msg = str(response.status_code)
            return None, f"API Error {response.status_code}: {err_msg}"
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

def clean_lighthouse_value(val):
    """
    Recursively extracts readable text from Lighthouse's complex object structures.
    Handles: nodes, source-locations, urls, and numerical values.
    """
    if val is None:
        return ""
    
    # 1. If it's a Dictionary, assume it's a Lighthouse Object (Node, URL, Source)
    if isinstance(val, dict):
        # Type: URL or Link
        if 'url' in val: 
            return val['url']
        # Type: Node (HTML Element) -> Get snippet or selector
        if 'snippet' in val:
            return val['snippet']
        if 'selector' in val:
            return val['selector']
        # Type: Source Location (File + Line)
        if 'source' in val: # sometimes nested
            return clean_lighthouse_value(val['source'])
        if 'file' in val:
            return f"{val['file']} (L{val.get('line',0)})"
        # Generic Value wrapper
        if 'value' in val:
            return str(val['value'])
        
        # If unknown dict, try to convert to string representation
        return str(val)

    # 2. If it's a List, join them
    if isinstance(val, list):
        return ", ".join([clean_lighthouse_value(v) for v in val])

    return val

def format_metric_value(key, val):
    """Formats numbers into KB/ms based on column name."""
    try:
        if isinstance(val, (int, float)):
            # Bytes -> KB
            if any(x in str(key).lower() for x in ['bytes', 'size', 'transfer']):
                return f"{val / 1024:.1f} KB"
            # Milliseconds -> ms
            if any(x in str(key).lower() for x in ['ms', 'time', 'duration']):
                return f"{val:.0f} ms"
    except:
        pass
    return val

def process_audit_details(audit):
    details = audit.get("details", {})
    
    # --- CASE A: TABLE (Standard lists of files) ---
    if details.get("items"):
        items = details.get("items", [])
        headings = details.get("headings", [])
        
        # Fallback headers if missing
        if not headings and items:
            headings = [{"key": k, "text": k} for k in items[0].keys()]
            
        processed_rows = []
        for item in items:
            row = {}
            for h in headings:
                key = h.get("key")
                label = h.get("text")
                
                # Get raw value
                raw_val = item.get(key)
                
                # Clean Objects (remove [object Object])
                clean_val = clean_lighthouse_value(raw_val)
                
                # Format Numbers (KB/ms)
                final_val = format_metric_value(key, clean_val)
                
                row[label] = final_val
            
            if row: processed_rows.append(row)
            
        if processed_rows:
            return pd.DataFrame(processed_rows)

    # --- CASE B: CRITICAL REQUEST CHAINS (Tree Structure) ---
    if details.get("type") == "criticalrequestchain":
        chains = details.get("chains", {})
        flat_chain = []
        
        def traverse(chain, depth=0):
            for key, node in chain.items():
                req = node.get("request", {})
                flat_chain.append({
                    "Depth": depth,
                    "Resource URL": req.get("url"),
                    "Size": f"{req.get('transferSize', 0)/1024:.1f} KB",
                    "Time": f"{req.get('startTime', 0)*1000:.0f} ms" # Often in seconds
                })
                if "children" in node:
                    traverse(node["children"], depth+1)
        
        traverse(chains)
        if flat_chain: return pd.DataFrame(flat_chain)

    return None

def get_failed_audits(lighthouse):
    audits = lighthouse.get("audits", {})
    failed = []
    
    for key, audit in audits.items():
        score = audit.get("score")
        
        # Logic: Fail if Score < 0.9 OR it's a Manual/Diagnostic item with data
        is_fail = (score is not None and score < 0.9)
        is_diagnostic = (audit.get("scoreDisplayMode") in ["informative", "manual"])
        has_table_data = bool(audit.get("details", {}).get("items") or audit.get("details", {}).get("chains"))
        
        if is_fail or (is_diagnostic and has_table_data):
            desc = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', audit.get("description", ""))
            
            failed.append({
                "id": key,
                "title": audit.get("title"),
                "score": score,
                "displayValue": audit.get("displayValue"),
                "description": desc,
                "details_df": process_audit_details(audit)
            })
            
    return sorted(failed, key=lambda x: (x['score'] if x['score'] is not None else 1.0))

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
    <b>Forensic Deep Dive:</b> We unwrap Google's nested JSON objects (Chains, Nodes, Source Locations) to show you the exact filenames causing lag.
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
    **2. Deep Extraction:** We unpack nested JSON trees (like Dependency Chains) into readable tables.
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
            
            # --- SECTION 1: FIELD DATA ---
            st.markdown("### 1. Real User Experience (CrUX)")
            if crux:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("LCP (Loading)", f"{crux['LCP']}s", delta_color="off" if crux['LCP']>2.5 else "normal", delta="Target < 2.5s" if crux['LCP']>2.5 else "Good")
                c2.metric("INP (Responsiveness)", f"{crux['INP']}ms", delta_color="off" if crux['INP']>200 else "normal", delta="Target < 200ms" if crux['INP']>200 else "Good")
                c3.metric("CLS (Visual Stability)", f"{crux['CLS']}", delta_color="off" if crux['CLS']>0.1 else "normal", delta="Target < 0.1" if crux['CLS']>0.1 else "Good")
                c4.metric("FCP (First Paint)", f"{crux['FCP']}s")
            else:
                st.info("No Field Data available. The report will rely on Lab Simulation below.")

            st.markdown("---")
            st.markdown("### 2. Lab Simulation Diagnostics")
            
            perf_score = lh.get("categories", {}).get("performance", {}).get("score", 0) * 100
            
            col_gauge, col_main_metrics = st.columns([1, 3])
            
            with col_gauge:
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number", value = perf_score, title = {'text': "Performance"},
                    gauge = {'axis': {'range': [None, 100]}, 'bar': {'color': "#1a7f37" if perf_score >= 90 else "#d93025"}, 'steps': [{'range': [0, 90], 'color': "#f6f8fa"}]}
                ))
                fig.update_layout(height=200, margin=dict(l=20,r=20,t=30,b=20))
                st.plotly_chart(fig, use_container_width=True)
            
            with col_main_metrics:
                st.markdown("#### Resource Weight")
                items = lh.get("audits", {}).get("resource-summary", {}).get("details", {}).get("items", [])
                if items:
                    res_df = pd.DataFrame(items)
                    if 'label' in res_df.columns:
                        res_df = res_df[res_df['resourceType'] != 'total']
                        res_df['Size (KB)'] = (res_df['transferSize'] / 1024).round(1)
                        fig_bar = px.bar(res_df, x='Size (KB)', y='label', orientation='h', text='Size (KB)', color_discrete_sequence=['#24292e'])
                        fig_bar.update_layout(yaxis={'title': None}, plot_bgcolor='white')
                        st.plotly_chart(fig_bar, use_container_width=True)

            # --- SECTION 3: FORENSICS ---
            st.markdown("### 3. Forensic Findings (Actionable)")
            st.markdown("""<div class="tech-note">Below are the specific technical failures. 
            Expand each row to see the exact <b>URLs</b> and <b>File Sizes</b> causing the issue.</div>""", unsafe_allow_html=True)
            
            failures = get_failed_audits(lh)
            
            if not failures:
                st.success("✅ Incredible! No major issues found in the Lab Audit.")
            
            for fail in failures:
                icon = "🔴" if (fail['score'] is not None and fail['score'] < 0.5) else "🟡"
                if fail['score'] is None: icon = "ℹ️"
                
                label = f"{icon} {fail['title']}"
                if fail.get('displayValue'):
                    label += f" — {fail['displayValue']}"
                
                with st.expander(label):
                    st.markdown(f"**Impact:** {fail['description']}")
                    
                    if fail['details_df'] is not None:
                        st.dataframe(
                            fail['details_df'], 
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.caption("No specific file breakdown available via API.")

            # --- THIRD PARTY SUMMARY ---
            st.markdown("### 4. Third-Party Code Impact")
            tp_audit = lh.get("audits", {}).get("third-party-summary", {})
            if tp_audit.get("details", {}).get("items"):
                tp_df = process_audit_details(tp_audit)
                if tp_df is not None:
                    st.dataframe(tp_df, use_container_width=True, hide_index=True)
            else:
                st.info("No significant third-party code detected.")
