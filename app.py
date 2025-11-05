"""
Ground Truth DQM - Main Landing Page
API-powered with manual credential input
"""

import streamlit as st
import config
from ui.components import show_header
from utils.data_processor import (
    process_excel_file,
    get_validation_summary,
    process_json_data,
)
import pandas as pd
import requests
from io import BytesIO

# Page config
st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        background: linear-gradient(90deg, #2E7D32 0%, #388E3C 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #2E7D32;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "data" not in st.session_state:
    st.session_state.data = None
if "filename" not in st.session_state:
    st.session_state.filename = None

# Header
show_header()

# Sidebar - API Configuration
with st.sidebar:
    st.markdown("## 🌐 Data Source: API")
    st.markdown("### 🔐 SurveyCTO Credentials")

    # Manual credential inputs
    server_name = st.text_input(
        "Server Name",
        value="akvofoundation",
        help="Your SurveyCTO server name (e.g., akvofoundation)",
    )

    username = st.text_input("Username", help="Your SurveyCTO username")

    password = st.text_input(
        "Password", type="password", help="Your SurveyCTO password"
    )

    credentials_configured = bool(server_name and username and password)

    if credentials_configured:
        st.success(f"✅ Connected to: {server_name}")
    else:
        st.warning("⚠️ Enter credentials above")

    # Form ID input
    st.markdown("---")
    st.markdown("### 📋 Form ID")

    form_id = st.text_input(
        "Enter form ID:",
        value="data_quality_ground_truth_collection_afoco_2025",
        help="Your SurveyCTO form ID",
        placeholder="data_quality_ground_truth_collection_afoco_2025",
    )

    if form_id:
        st.caption(f"✅ Using: `{form_id}`")
    else:
        st.warning("⚠️ Form ID required")

    st.markdown("---")

    # Settings display
    st.markdown("## ⚙️ Validation Settings")
    st.caption(f"**Min Subplot Area:** {config.MIN_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**Max Subplot Area:** {config.MAX_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**GPS Accuracy:** ≤ {config.GPS_ACCURACY_THRESHOLD}m")
    st.caption(f"**Radius Check:** {config.THRESHOLD_WITHIN_RADIUS}m")

    st.markdown("---")

    # Process button
    if credentials_configured and form_id:
        process_btn = st.button(
            "🚀 Fetch & Validate", type="primary", use_container_width=True
        )
    else:
        process_btn = False
        if not credentials_configured:
            st.warning("⚠️ Configure API credentials")
        elif not form_id:
            st.warning("⚠️ Enter form ID")

# Process data (fetch from API, then process)
if process_btn and credentials_configured:
    with st.spinner("Fetching and processing data..."):
        try:
            progress_bar = st.progress(0, text="Connecting to SurveyCTO...")

            # Fetch JSON data directly
            progress_bar.progress(25, text="📡 Downloading from API...")

            url = f"https://{server_name}.surveycto.com/api/v2/forms/data/wide/json/{form_id}"
            params = {"date": "0"}

            response = requests.get(
                url, auth=(username, password), params=params, timeout=60
            )
            response.raise_for_status()
            json_data = response.json()

            st.success(f"✅ Fetched {len(json_data)} submissions")

            # Process using new JSON processor
            progress_bar.progress(50, text="📖 Processing data...")
            data = process_json_data(json_data)

            progress_bar.progress(100, text="✅ Validation complete!")

            # Store in session state
            st.session_state.data = data
            st.session_state.filename = f"API: {form_id}"

            st.success(f"✅ Processed {len(data['subplots'])} subplots successfully!")
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.exception(e)
            progress_bar.empty()

# Main content
if st.session_state.data is not None:
    # Get data
    gdf_subplots = st.session_state.data["subplots"]
    summary = get_validation_summary(gdf_subplots)

    # Show quick summary
    st.markdown("## 📊 Quick Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Subplots", f"{summary['total']:,}")

    with col2:
        st.metric(
            "Valid Subplots",
            f"{summary['valid']:,}",
            f"{summary['valid_pct']:.1f}%",
        )

    with col3:
        st.metric("Invalid Subplots", f"{summary['invalid']:,}")

    with col4:
        total_issues = sum(summary["reason_counts"].values())
        st.metric("Total Issues", f"{total_issues:,}")

    # Status message
    st.markdown("---")
    valid_pct = summary["valid_pct"]

    if valid_pct >= 95:
        st.success(f"🎉 Excellent! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 90:
        st.success(f"✅ Very good! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 80:
        st.warning(f"⚠️ Good, but {summary['invalid']} subplots need attention")
    else:
        st.error(f"❌ Critical: {summary['invalid']} subplots invalid")

    # Navigation cards
    st.markdown("---")
    st.markdown("## 🧭 Navigate to:")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
        <div class="metric-card">
            <h3>📊 Overview Dashboard</h3>
            <p>Detailed metrics, charts, and validation breakdown</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Overview →", key="nav_overview", use_container_width=True):
            st.switch_page("pages/_Overview.py")

    with col2:
        st.markdown(
            """
        <div class="metric-card">
            <h3>🗺️ Map View</h3>
            <p>Interactive map showing valid and invalid subplots</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Map →", key="nav_map", use_container_width=True):
            st.switch_page("pages/_Map_View.py")

    with col3:
        st.markdown(
            """
        <div class="metric-card">
            <h3>❌ Invalid Subplots</h3>
            <p>Detailed list of subplots requiring attention</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Issues →", key="nav_issues", use_container_width=True):
            st.switch_page("pages/_Plot_Issues.py")

    st.markdown("<br>", unsafe_allow_html=True)

    col4, col5 = st.columns(2)

    with col4:
        st.markdown(
            """
        <div class="metric-card">
            <h3>🌳 Subplot Details</h3>
            <p>Deep dive into individual subplot information</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Details →", key="nav_details", use_container_width=True):
            st.switch_page("pages/_Subplot_Details.py")

    with col5:
        st.markdown(
            """
        <div class="metric-card">
            <h3>👤 Enumerator Performance</h3>
            <p>Quality tracking by data collector</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Performance →", key="nav_enum", use_container_width=True):
            st.switch_page("pages/_Enumerator_Performance.py")

else:
    # Welcome screen
    st.markdown("## 👋 Welcome to Ground Truth DQM")

    st.info(
        "👈 Enter your SurveyCTO credentials and click 'Fetch & Validate' to load data"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
        ### 📋 How It Works
        
        This application validates ground truth forestry data:
        
        1. **Fetch** - Automatically get latest data from SurveyCTO API
        2. **Parse** - Read and structure the data
        3. **Create Geometries** - Convert GPS coordinates
        4. **Fix Geometries** - Apply 13 correction operations
        5. **Validate** - Check area, vertices, overlaps
        6. **Report** - Generate comprehensive results
        
        ### ✅ What Gets Validated
        
        - ✓ GPS accuracy (≤10m threshold)
        - ✓ Subplot area (450-750 m²)
        - ✓ Plot area (1,000-300,000 m²)
        - ✓ Geometry validity and structure
        - ✓ Vertex count (minimum 4)
        - ✓ Shape analysis (not too elongated)
        - ✓ Radius constraints
        - ✓ Overlapping boundaries
        """
        )

    with col2:
        st.markdown(
            """
        ### 🌐 API Setup
        
        Enter your credentials in the sidebar:
        
        1. **Server Name** - Your SurveyCTO server (e.g., akvofoundation)
        2. **Username** - Your SurveyCTO username
        3. **Password** - Your SurveyCTO password
        4. **Form ID** - Your form ID
        
        ### 📊 After Processing
        
        - **Overview Dashboard** - Statistics and charts
        - **Interactive Map** - Visual representation
        - **Issue List** - Invalid subplots with reasons
        - **Subplot Details** - Individual information
        - **Performance Metrics** - Quality by enumerator
        - **Export Options** - Download validated data
        
        ### 🔄 Always Fresh
        
        API automatically fetches latest submissions!
        No manual export or upload needed.
        
        ### 🔒 Security
        
        Credentials are only used for this session and not stored.
        """
        )
