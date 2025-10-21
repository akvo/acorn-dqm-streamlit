"""
Main Streamlit App - Data Quality Management Dashboard
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import config
from utils.data_loader import *
from utils.validators import *
from utils.visualization import *

# Page configuration
st.set_page_config(
    page_title="Forestry DQM Dashboard",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #2E7D32;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #2E7D32;
    }
    .issue-critical {
        background-color: #ffebee;
        padding: 0.5rem;
        border-left: 4px solid #D32F2F;
        margin: 0.5rem 0;
    }
    .issue-warning {
        background-color: #fff3e0;
        padding: 0.5rem;
        border-left: 4px solid #F57C00;
        margin: 0.5rem 0;
    }
    .issue-valid {
        background-color: #e8f5e9;
        padding: 0.5rem;
        border-left: 4px solid #388E3C;
        margin: 0.5rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.raw_data = None
    st.session_state.merged_data = None
    st.session_state.validation_results = None

# Sidebar
st.sidebar.title("🌳 Forestry DQM")
st.sidebar.markdown("---")

# File uploader
st.sidebar.subheader("📤 Upload Data")
uploaded_file = st.sidebar.file_uploader(
    "Upload Excel file",
    type=config.ALLOWED_EXTENSIONS,
    help="Upload the ground truth collection Excel file",
)

if uploaded_file:
    with st.spinner("Loading data..."):
        raw_data = load_excel_data(uploaded_file)

        if raw_data:
            st.session_state.raw_data = raw_data
            st.session_state.merged_data = merge_data(raw_data)

            # Add geometry to subplots
            if "gt_subplot" in st.session_state.merged_data["plots_subplots"].columns:
                st.session_state.merged_data["plots_subplots"] = (
                    add_geometry_to_subplots(
                        st.session_state.merged_data["plots_subplots"],
                        accuracy_m=10,
                        apply_fixes=True,
                    )
                )

            # Run validation
            with st.spinner("Validating data..."):
                st.session_state.validation_results = validate_dataset(
                    st.session_state.merged_data
                )

            st.session_state.data_loaded = True
            st.sidebar.success("✅ Data loaded successfully!")

# Main content
if not st.session_state.data_loaded:
    st.markdown(
        '<div class="main-header">🌳 Forestry Data Quality Management</div>',
        unsafe_allow_html=True,
    )

    st.info("👈 Please upload an Excel file to begin")

    st.markdown(
        """
    ### Welcome to the DQM Dashboard
    
    This tool helps you validate ground truth forestry data collection with:
    
    - 📊 **Overview Dashboard** - Summary statistics and validation status
    - 🔍 **Plot Issues** - Detailed view of invalid plots
    - 🌳 **Subplot Details** - Drill down to subplot-level issues
    - 👤 **Enumerator Performance** - Track data quality by collector
    - 🗺️ **Map View** - Visualize plots and issues geographically
    
    #### Getting Started
    1. Upload your Excel file using the sidebar
    2. Review the overview dashboard
    3. Navigate to specific issues using the pages in the sidebar
    4. Download JSON files for manual verification
    """
    )

    # Sample data structure
    with st.expander("📋 Expected Excel File Structure"):
        st.markdown(
            """
        Your Excel file should contain these sheets:
        
        1. **Sheet 0 - Plots**: Plot-level data with columns like:
           - `KEY` (Plot ID)
           - `enumerator`
           - `SubmissionDate`
           - `gt_plot` (Plot geometry)
           
        2. **Sheet 1 - Subplots**: Subplot-level data with columns like:
           - `PARENT_KEY` (Plot ID)
           - `KEY` (Subplot ID)
           - `gt_subplot` (Subplot geometry)
           
        3. **Sheet 2 - Vegetation**: Species/vegetation data
           - `PARENT_KEY` (Subplot ID)
           - `KEY` (Vegetation ID)
           - `vegetation_species_type`
           - `woody_species`, `other_species`, etc.
           
        4. **Sheet 3 - Measurements**: Tree measurements
           - `PARENT_KEY` (Vegetation ID)
           - `tree_height_m`
           - `circumference_bh`
           - `tree_year_planted`
           
        5. **Sheet 4 - Circumferences** (optional): Additional circumference data
        """
        )

else:
    # Data loaded - show overview
    st.markdown(
        '<div class="main-header">📊 Overview Dashboard</div>', unsafe_allow_html=True
    )

    # Filters in sidebar
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Filters")

    plots_subplots = st.session_state.merged_data["plots_subplots"]

    # Date filter
    if "SubmissionDate" in plots_subplots.columns:
        plots_subplots["SubmissionDate"] = pd.to_datetime(
            plots_subplots["SubmissionDate"]
        )
        min_date = plots_subplots["SubmissionDate"].min().date()
        max_date = plots_subplots["SubmissionDate"].max().date()

        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if len(date_range) == 2:
            plots_subplots = filter_by_date(
                plots_subplots, date_range[0], date_range[1]
            )

    # Enumerator filter
    enumerators = get_unique_enumerators(plots_subplots)
    selected_enumerators = st.sidebar.multiselect(
        "Enumerator", options=enumerators, default=enumerators
    )

    if selected_enumerators:
        plots_subplots = plots_subplots[
            plots_subplots["enumerator"].isin(selected_enumerators)
        ]

    # Aggregate validation results
    validation_summary = aggregate_validation_results(
        st.session_state.validation_results
    )

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Plots",
            (
                plots_subplots["PLOT_KEY"].nunique()
                if "PLOT_KEY" in plots_subplots.columns
                else 0
            ),
            help="Number of unique plots in the dataset",
        )

    with col2:
        total_subplots = validation_summary["total_subplots"]
        valid_subplots = validation_summary["valid_subplots"]
        valid_pct = (valid_subplots / total_subplots * 100) if total_subplots > 0 else 0

        st.metric(
            "Valid Subplots",
            f"{valid_subplots}/{total_subplots}",
            f"{valid_pct:.1f}%",
            delta_color="normal" if valid_pct > 80 else "inverse",
        )

    with col3:
        invalid_subplots = validation_summary["invalid_subplots"]
        st.metric(
            "Invalid Subplots",
            invalid_subplots,
            delta_color="inverse" if invalid_subplots > 0 else "off",
        )

    with col4:
        total_issues = validation_summary["total_issues"]
        st.metric(
            "Total Issues",
            total_issues,
            delta_color="inverse" if total_issues > 0 else "off",
        )

    st.markdown("---")

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        # Validation status pie chart
        fig_status = plot_validation_summary(validation_summary)
        if fig_status:
            st.plotly_chart(fig_status, use_container_width=True)

    with col2:
        # Issues by type
        fig_issues = plot_issues_by_type(validation_summary)
        if fig_issues:
            st.plotly_chart(fig_issues, use_container_width=True)

    # Timeline
    fig_timeline = plot_collection_timeline(plots_subplots)
    if fig_timeline:
        st.plotly_chart(fig_timeline, use_container_width=True)

    # Issues by severity
    fig_severity = plot_issues_by_severity(validation_summary)
    if fig_severity:
        st.plotly_chart(fig_severity, use_container_width=True)

    st.markdown("---")

    # Quick actions
    st.subheader("Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📋 View Invalid Plots", use_container_width=True):
            st.switch_page("pages/_Plot_Issues.py")

    with col2:
        if st.button("🗺️ View Map", use_container_width=True):
            st.switch_page("pages/_Map_View.py")

    with col3:
        if st.button("👤 Enumerator Performance", use_container_width=True):
            st.switch_page("pages/_Enumerator_Performance.py")
