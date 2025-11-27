import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import re

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION (Dejan Style - Light Mode Forced)
# -----------------------------------------------------------------------------
st.set_page_config(page_title="PageSpeed Forensics", layout="wide", page_icon="⚡")

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
    
    /* Tech Note */
    .tech-note { font-size: 0.85rem; color: #57606a; background-color: #f3f4f6; border-left: 3px solid #0969da; padding: 12px; margin-top: 8px; margin-bottom: 15px; border-radius: 0 4px 4px 0; line-height: 1.5; }
    
    /* Metrics */
    div[data-testid="stMetricValue"] { font-size: 1.8rem !important; color: #1a7f37 !important; font-weight: 700; }
    div[data-testid="stMetricLabel"] { font-size: 0.9rem !important; color: #586069 !important; }

    /* Clean UI */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. LOGIC ENGINE
# -----------------------------------------------------------------------------

def run_pagespeed(url, strategy, api_key=None):
    if not url.startswith("http"): url = "https://" + url
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&strategy={strategy}"
    if api_key: api_url += f"&key={api_key}"
    
    try:
        response = requests.get(api_url, timeout=60)
        if response.status_code == 200:
            return response.json(), None
        else:
            return None, f"API Error {response.status_code}: {response.json().get('error', {}).get('message', 'Unknown error')}"
    except Exception as e:
        return None, str(e)

def parse_crux(data):
    """Extracts Real User Experience (Field Data)"""
    loading = data.get("loadingExperience", {})
    metrics = loading.get("metrics", {})
    
    if not metrics: return None
    
    # Core Web Vitals
    crux = {
        "LCP": metrics.get("LARGEST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
        "INP": metrics.get("INTERACTION_TO_NEXT_PAINT", {}).get("percentile", 0),
        "CLS": metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE", {}).get("percentile", 0) / 100,
        "FCP": metrics.get("FIRST_CONTENTFUL_PAINT_MS", {}).get("percentile", 0) / 1000,
    }
    return crux

def parse_lab_audit(lighthouse):
    """Extracts actionable audits from Lighthouse"""
    audits = lighthouse.get("audits", {})
    findings = []
    
    for key, audit in audits.items():
        # We only want failing audits with high impact
        score = audit.get("score")
        if score is not None and score < 0.9:
            # Estimate savings
            savings = audit.get("details", {}).get("overallSavingsMs", 0)
            
            findings.append({
                "Audit": audit.get("title"),
                "Score": round(score * 100, 0),
                "Impact": "High" if score < 0.5 else "Medium",
                "Estimated Lag (ms)": savings if savings > 0 else "N/A",
                "Description": re.sub(r'\[(.*?)\]\(.*?\)', r'\1', audit.get("description", "")) # Strip links
            })
            
    return pd.DataFrame(findings).sort_values(by="Score", ascending=True)

def get_resource_breakdown(lighthouse):
    """Extracts network request types"""
    items = lighthouse.get("audits", {}).get("resource-summary", {}).get("details", {}).get("items", [])
    if not items: return pd.DataFrame()
    return pd.DataFrame(items)

# -----------------------------------------------------------------------------
# 3. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Audit Config")
    
    strategy = st.selectbox("Device Emulation", ["mobile", "desktop"], index=0)
    api_key = st.text_input("Google API Key (Optional)", type="password", help="Recommended to avoid rate limits.")
    
    st.markdown("---")
    st.markdown("""
    **Engine:** Google Lighthouse v12 + CrUX
    <div class="tech-note">
    <b>Real User vs. Lab Data:</b>
    This tool separates <b>Field Data</b> (what real users see) from <b>Lab Data</b> (simulation). Most tools mix them up, leading to false optimization strategies.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 4. MAIN INTERFACE
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensics")
st.markdown("### Core Web Vitals & Critical Path Analysis")

with st.expander("Technical Methodology (Read First)", expanded=False):
    st.markdown("""
    **Why is this better than standard PageSpeed Insights?**
    
    1.  **Forensic Separation:** We strictly separate **CrUX** (Ranking Factor) from **Lighthouse** (Diagnostic). 
    2.  **Resource Bloat Analysis:** We visualize exactly how much JavaScript/CSS weight is being sent compared to the budget.
    3.  **Third-Party Attribution:** Identifies if the slowdown is caused by your code or external scripts (Analytics, Chatbots, Ads).
    
    **Key Metrics:**
    *   **LCP (Largest Contentful Paint):** Loading speed of the main visual.
    *   **INP (Interaction to Next Paint):** Responsiveness (Lag on clicks).
    *   **CLS (Cumulative Layout Shift):** Visual stability.
    """)

st.write("")
url_input = st.text_input("Target URL", placeholder="https://example.com")
run_btn = st.button("Run Forensic Audit", type="primary")

if run_btn and url_input:
    
    with st.spinner(f"Contacting Google PSI API ({strategy})..."):
        data, err = run_pagespeed(url_input, strategy, api_key)
        
        if err:
            st.error(err)
        else:
            lh = data.get("lighthouseResult", {})
            crux = parse_crux(data)
            
            # --- SECTION 1: REAL USER EXPERIENCE (CrUX) ---
            st.markdown("---")
            st.subheader("1. Real User Experience (CrUX)")
            st.markdown("""<div class="tech-note"><b>This is what Google uses for Ranking.</b> It is aggregated from Chrome users over the last 28 days. If this is Green, you are safe, even if Lab scores are low.</div>""", unsafe_allow_html=True)
            
            if crux:
                c1, c2, c3, c4 = st.columns(4)
                
                # Dynamic Coloring
                lcp_color = "off" if crux['LCP'] > 2.5 else "normal"
                inp_color = "off" if crux['INP'] > 200 else "normal"
                cls_color = "off" if crux['CLS'] > 0.1 else "normal"
                
                c1.metric("LCP (Load)", f"{crux['LCP']}s", delta_color=lcp_color, delta="Poor > 2.5s" if crux['LCP']>2.5 else "Good")
                c2.metric("INP (Lag)", f"{crux['INP']}ms", delta_color=inp_color, delta="Poor > 200ms" if crux['INP']>200 else "Good")
                c3.metric("CLS (Shift)", f"{crux['CLS']}", delta_color=cls_color, delta="Poor > 0.1" if crux['CLS']>0.1 else "Good")
                c4.metric("FCP (First Paint)", f"{crux['FCP']}s")
            else:
                st.warning("No Real User Data (CrUX) available for this URL. It may be too new or low traffic. Rely on Lab Data below.")

            # --- SECTION 2: LAB DIAGNOSTICS ---
            st.markdown("---")
            st.subheader("2. Lab Simulation (Lighthouse)")
            
            # Overall Performance Score
            perf_score = lh.get("categories", {}).get("performance", {}).get("score", 0) * 100
            
            col_gauge, col_stats = st.columns([1, 2])
            
            with col_gauge:
                fig = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = perf_score,
                    domain = {'x': [0, 1], 'y': [0, 1]},
                    title = {'text': "Performance Score"},
                    gauge = {
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "#1a7f37" if perf_score >= 90 else "#d93025"},
                        'steps': [
                            {'range': [0, 50], 'color': "#f4f6f8"},
                            {'range': [50, 90], 'color': "#e6f4ea"}
                        ]
                    }
                ))
                fig.update_layout(height=250, margin=dict(t=30,b=10))
                st.plotly_chart(fig, use_container_width=True)
            
            with col_stats:
                st.markdown("#### Resource Composition")
                res_df = get_resource_breakdown(lh)
                if not res_df.empty:
                    # Filter out 'total' row and tiny items
                    res_df = res_df[res_df['resourceType'] != 'total']
                    res_df = res_df[res_df['transferSize'] > 0]
                    
                    fig_bar = px.bar(res_df, x='transferSize', y='resourceType', orientation='h',
                                     title="Transfer Size by Asset Type (Bytes)",
                                     labels={'transferSize': 'Bytes', 'resourceType': 'Type'},
                                     color_discrete_sequence=['#1a7f37'])
                    st.plotly_chart(fig_bar, use_container_width=True)

            # --- SECTION 3: ACTIONABLE FORENSICS ---
            st.subheader("3. Forensic Findings")
            
            audit_df = parse_lab_audit(lh)
            
            tab1, tab2 = st.tabs(["🔴 Critical Issues", "📋 All Diagnostics"])
            
            with tab1:
                critical = audit_df[audit_df['Impact'] == "High"]
                if not critical.empty:
                    st.markdown("""<div class="tech-note">These issues are actively damaging your LCP/INP scores. Fix these first.</div>""", unsafe_allow_html=True)
                    st.dataframe(
                        critical[['Audit', 'Estimated Lag (ms)', 'Description']],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.success("No Critical (High Impact) issues found in Lab tests.")
            
            with tab2:
                st.dataframe(
                    audit_df[['Score', 'Audit', 'Impact', 'Description']],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Score": st.column_config.ProgressColumn(
                            "Health",
                            format="%d",
                            min_value=0,
                            max_value=100,
                        )
                    }
                )
            
            # Export
            csv = audit_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Forensic Report (CSV)", csv, "pagespeed_forensics.csv", "text/csv")
