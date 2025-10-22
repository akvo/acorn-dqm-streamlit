"""
Ground Truth DQM - Main Landing Page
"""

import streamlit as st
import config
from ui.components import show_header
from utils.data_processor import process_excel_file, get_validation_summary

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

# Sidebar - File Upload
with st.sidebar:
    st.markdown("## 📤 Upload Data")

    uploaded_file = st.file_uploader(
        "Choose Excel file",
        type=["xlsx", "xls"],
        help="Upload Ground Truth Collection Excel file",
    )

    st.markdown("---")

    # Settings display
    st.markdown("## ⚙️ Validation Settings")
    st.caption(f"**Min Subplot Area:** {config.MIN_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**Max Subplot Area:** {config.MAX_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**GPS Accuracy:** ≤ {config.GPS_ACCURACY_THRESHOLD}m")
    st.caption(f"**Radius Check:** {config.THRESHOLD_WITHIN_RADIUS}m")

    st.markdown("---")

    # Process button
    if uploaded_file:
        process_btn = st.button(
            "🚀 Process & Validate", type="primary", use_container_width=True
        )
    else:
        process_btn = False
        st.info("Upload a file to begin")

# Process data
if process_btn and uploaded_file:
    with st.spinner("Processing data..."):
        try:
            progress_bar = st.progress(0, text="Starting validation...")

            # Process file
            progress_bar.progress(25, text="📖 Reading Excel file...")
            data = process_excel_file(uploaded_file)

            progress_bar.progress(100, text="✅ Validation complete!")

            # Store in session state
            st.session_state.data = data
            st.session_state.filename = uploaded_file.name

            st.success(f"✅ Processed {len(data['subplots'])} subplots successfully!")
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            st.exception(e)

# Main content
if st.session_state.data is not None:
    # Get data
    gdf_subplots = st.session_state.data["subplots"]
    summary = get_validation_summary(gdf_subplots)

    # Show quick summary
    st.markdown("## 📊 Quick Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Subplots",
            f"{summary['total']:,}",
        )

    with col2:
        st.metric(
            "Valid Subplots",
            f"{summary['valid']:,}",
            f"{summary['valid_pct']:.1f}%",
        )

    with col3:
        st.metric(
            "Invalid Subplots",
            f"{summary['invalid']:,}",
        )

    with col4:
        total_issues = sum(summary["reason_counts"].values())
        st.metric(
            "Total Issues",
            f"{total_issues:,}",
        )

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

    st.info("👈 Upload an Excel file from the sidebar to begin validation")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
        ### 📋 How It Works
        
        This application validates ground truth forestry data using the 
        **exact validation pipeline from the AKVO notebooks**:
        
        1. **Parse** - Read Excel file (Ground Truth Collection v3)
        2. **Create Geometries** - Convert GPS coordinates with accuracy filtering
        3. **Fix Geometries** - Apply 13 geometry correction operations
        4. **Validate** - Check area, vertices, overlaps, and more
        5. **Report** - Generate comprehensive validation results
        
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
        ### 📊 Expected Results
        
        After processing, you'll have access to:
        
        - **Overview Dashboard** - Summary statistics and charts
        - **Interactive Map** - Visual representation of valid/invalid subplots
        - **Detailed Issue List** - Every invalid subplot with reasons
        - **Subplot Deep Dive** - Individual subplot information
        - **Performance Metrics** - Quality by enumerator
        - **Export Options** - Download validated data in multiple formats
        
        ### 📁 Excel File Requirements
        
        Your Excel file should contain:
        
        - **Sheet 0**: Plots
          - Columns: `KEY`, `gt_plot`, `enumerator`, `starttime`
        
        - **Sheet 1**: Subplots
          - Columns: `PARENT_KEY`, `KEY`, `gt_subplot`
        
        The app automatically handles merging and validation.
        """
        )

    # Example metrics
    st.markdown("---")
    st.markdown("### 📈 Example Validation Results")

    example_col1, example_col2, example_col3, example_col4 = st.columns(4)

    with example_col1:
        st.metric("Total Subplots", "1,600")
    with example_col2:
        st.metric("Valid", "1,444", "90.2%")
    with example_col3:
        st.metric("Invalid", "156")
    with example_col4:
        st.metric("Issues", "156")
