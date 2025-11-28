import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# -----------------------------------------------------------------------------
# 1. VISUAL CONFIGURATION (Strict "Dejan" Academic Minimalist)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="PageSpeed Forensics", 
    layout="wide", 
    page_icon="🔬",
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
    .stTextInput input { background-color: #ffffff !important; border: 1px solid #d0d7de !important; color: #24292e !important; border-radius: 6px; }
    .stTextInput input:focus { border-color: #1a7f37 !important; box-shadow: 0 0 0 2px rgba(26,127,55,0.1) !important; }
    
    /* Custom Metric Cards */
    .metric-card {
        background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.02); margin-bottom: 10px;
    }
    .metric-val { font-size: 1.8rem; font-weight: 700; color: #1a7f37; }
    .metric-lbl { font-size: 0.85rem; color: #586069; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-bad { color: #d73a49; }
    
    /* Tables */
    [data-testid="stDataFrame"] { border: 1px solid #e1e4e8; border-radius: 6px; }
    
    /* Tech Note */
    .tech-note { font-size: 0.85rem; color: #57606a; background-color: #f6f8fa; border-left: 3px solid #0969da; padding: 12px; border-radius: 0 4px 4px 0; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} 
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. ENGINE: DATA EXTRACTION & PROCESSING
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
            return None, f"Google API Error: {err}"
    except Exception as e:
        return None, f"Connection Error: {str(e)}"

def get_treemap_data(lighthouse):
    """Extracts resource data for the Treemap visualization."""
    items = lighthouse.get("audits", {}).get("network-requests", {}).get("details", {}).get("items", [])
    if not items: return None
    
    df = pd.DataFrame(items)
    # Categorize by resource type
    def categorize(mime, url):
        if 'image' in mime: return "Images"
        if 'script' in mime or '.js' in url: return "JavaScript"
        if 'css' in mime: return "CSS"
        if 'font' in mime: return "Fonts"
        if 'html' in mime: return "HTML"
        if 'json' in mime: return "Data/XHR"
        return "Other"

    df['Category'] = df.apply(lambda x: categorize(str(x.get('mimeType', '')), x.get('url', '')), axis=1)
    df['Size'] = df['transferSize']
    df['Label'] = df['url'].apply(lambda x: x.split('/')[-1].split('?')[0] if x else 'Unknown')
    
    # Filter out 0 byte requests
    df = df[df['Size'] > 0]
    return df

def get_js_execution(lighthouse):
    """Parses Main Thread Work breakdown."""
    items = lighthouse.get("audits", {}).get("mainthread-work-breakdown", {}).get("details", {}).get("items", [])
    if not items: return None
    df = pd.DataFrame(items)
    df['duration'] = df['duration'].round(0)
    return df.sort_values('duration', ascending=False)

def get_third_party(lighthouse):
    """Aggregates Third Party usage."""
    items = lighthouse.get("audits", {}).get("third-party-summary", {}).get("details", {}).get("items", [])
    if not items: return None
    
    data = []
    for item in items:
        # Extract subItems (specific URLs) to count them
        count = len(item.get('subItems', {}).get('items', []))
        data.append({
            "Entity": item.get('entity', {}).get('text', 'Unknown'),
            "Transfer Size (KB)": item.get('transferSize', 0) / 1024,
            "Blocking Time (ms)": item.get('blockingTime', 0),
            "Request Count": count
        })
    return pd.DataFrame(data).sort_values('Blocking Time (ms)', ascending=False)

def get_opportunities(lighthouse):
    """Filters only the audits that show BYTE savings."""
    audits = lighthouse.get("audits", {})
    opps = []
    for key, val in audits.items():
        if val.get('details', {}).get('type') == 'opportunity' and val.get('score', 1) < 0.9:
            savings = val.get('details', {}).get('overallSavingsBytes', 0)
            if savings > 0:
                opps.append({
                    "Optimization": val.get('title'),
                    "Potential Savings (KB)": savings / 1024,
                    "Description": val.get('description').split('[')[0] # Remove links
                })
    return pd.DataFrame(opps).sort_values('Potential Savings (KB)', ascending=False)

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
    st.markdown("### 📚 Methodology")
    st.markdown("""
    **1. Payload Anatomy:** We use Treemaps to visualize asset weight distribution.
    
    **2. Thread Blocking:** We analyze the JS Execution timeline to find CPU hogs.
    
    **3. Third-Party Cost:** We sum up the latency tax paid to vendors (Meta, Google, etc).
    """)

# -----------------------------------------------------------------------------
# 4. MAIN DASHBOARD
# -----------------------------------------------------------------------------

st.title("PageSpeed Forensics")
st.markdown("### The Developer's Performance Audit")

# Input Section
col_in1, col_in2 = st.columns([3, 1])
with col_in1:
    url_input = st.text_input("Target URL", placeholder="https://example.com", label_visibility="collapsed")
with col_in2:
    run_btn = st.button("Start Forensic Audit", type="primary", use_container_width=True)

if run_btn and url_input:
    with st.spinner("Connecting to Lighthouse Infrastructure..."):
        data, err = run_pagespeed(url_input, strategy, api_key)
        
    if err:
        st.error(err)
    else:
        lh = data.get("lighthouseResult", {})
        
        # --- PART 1: CORE VITALS HUD ---
        st.markdown("### 1. Vitals HUD (Real User Data)")
        
        crux = data.get("loadingExperience", {}).get("metrics", {})
        if crux:
            c1, c2, c3, c4 = st.columns(4)
            
            # Helper to render cards
            def render_card(col, label, val, unit, threshold):
                is_bad = val > threshold
                color_class = "metric-bad" if is_bad else "metric-val"
                col.markdown(f"""
                <div class="metric-card">
                    <div class="{color_class}">{val}{unit}</div>
                    <div class="metric-lbl">{label}</div>
                </div>
                """, unsafe_allow_html=True)

            lcp = crux.get('LARGEST_CONTENTFUL_PAINT_MS', {}).get('percentile', 0) / 1000
            inp = crux.get('INTERACTION_TO_NEXT_PAINT', {}).get('percentile', 0)
            cls = crux.get('CUMULATIVE_LAYOUT_SHIFT_SCORE', {}).get('percentile', 0) / 100
            fcp = crux.get('FIRST_CONTENTFUL_PAINT_MS', {}).get('percentile', 0) / 1000
            
            render_card(c1, "LCP (Load)", lcp, "s", 2.5)
            render_card(c2, "INP (Lag)", inp, "ms", 200)
            render_card(c3, "CLS (Shift)", cls, "", 0.1)
            render_card(c4, "FCP (Paint)", fcp, "s", 1.8)
        else:
            st.info("No Field Data (CrUX) available. Showing Lab Data only.")

        # --- PART 2: PAYLOAD TREEMAP (The Killer Feature) ---
        st.markdown("---")
        st.subheader("2. Payload Anatomy (Treemap)")
        st.markdown("This visualization answers: **'What is taking up all the space?'** Click headers to zoom in.")
        
        network_df = get_treemap_data(lh)
        
        if network_df is not None and not network_df.empty:
            fig = px.treemap(
                network_df, 
                path=[px.Constant("Total Page Size"), 'Category', 'Label'], 
                values='Size',
                color='Category',
                color_discrete_map={
                    'Images': '#e3f2fd', 'JavaScript': '#fff9c4', 'CSS': '#e8f5e9', 
                    'Fonts': '#f3e5f5', 'HTML': '#ffebee', 'Other': '#f5f5f5'
                },
                hover_data=['url']
            )
            fig.update_layout(margin=dict(t=0, l=0, r=0, b=0))
            fig.update_traces(textinfo="label+value+percent entry")
            st.plotly_chart(fig, use_container_width=True)
            
            # Stats Table
            with st.expander("View Raw Asset List (Searchable)"):
                st.dataframe(
                    network_df[['Category', 'Label', 'Size', 'startTime', 'url']].sort_values('Size', ascending=False),
                    column_config={
                        "Size": st.column_config.NumberColumn("Size (Bytes)", format="%d"),
                        "startTime": st.column_config.NumberColumn("Start Time (ms)", format="%d"),
                        "url": st.column_config.LinkColumn("Full URL")
                    },
                    use_container_width=True
                )

        # --- PART 3: MAIN THREAD BLOCKERS ---
        st.markdown("---")
        col_js, col_3rd = st.columns(2)
        
        with col_js:
            st.subheader("3. JavaScript Execution Cost")
            js_df = get_js_execution(lh)
            if js_df is not None:
                fig_js = px.bar(
                    js_df, x='duration', y='group', orientation='h',
                    text='duration', color='duration',
                    color_continuous_scale=['#a5d6a7', '#ef5350'],
                    labels={'duration': 'Time (ms)', 'group': 'Task Type'}
                )
                fig_js.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor='white')
                st.plotly_chart(fig_js, use_container_width=True)
                st.caption("This shows *what* the browser CPU is doing. 'Script Evaluation' usually means heavy JS frameworks.")

        with col_3rd:
            st.subheader("4. Third-Party Wall of Shame")
            tp_df = get_third_party(lh)
            if tp_df is not None:
                st.dataframe(
                    tp_df,
                    column_config={
                        "Blocking Time (ms)": st.column_config.ProgressColumn(
                            "Blocking Impact", 
                            format="%d ms", 
                            min_value=0, 
                            max_value=int(tp_df['Blocking Time (ms)'].max() + 100)
                        ),
                        "Transfer Size (KB)": st.column_config.NumberColumn("Size (KB)", format="%.1f")
                    },
                    use_container_width=True,
                    height=400
                )
            else:
                st.success("Clean! No blocking third-party scripts detected.")

        # --- PART 5: DEVELOPER ACTION PLAN ---
        st.markdown("---")
        st.subheader("5. Developer Action Plan")
        
        opps_df = get_opportunities(lh)
        
        if not opps_df.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                st.dataframe(
                    opps_df,
                    column_config={
                        "Potential Savings (KB)": st.column_config.ProgressColumn(
                            "Projected Savings",
                            format="%.1f KB",
                            min_value=0,
                            max_value=int(opps_df['Potential Savings (KB)'].max())
                        )
                    },
                    use_container_width=True,
                    hide_index=True
                )
            with col2:
                # Calculate Total Savings
                total_save = opps_df['Potential Savings (KB)'].sum()
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-val">{total_save:.1f} KB</div>
                    <div class="metric-lbl">Total Waste Identified</div>
                </div>
                <div style="font-size:0.9rem; color:#586069; margin-top:10px;">
                <b>Strategy:</b><br>
                1. Compress Images (WebP)<br>
                2. Defer off-screen images<br>
                3. Minify CSS/JS
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No major resource optimizations found. Good job!")
