"""
Subplot Details Page - Complete with vegetation analysis
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import config
from ui.components import show_header, create_sidebar_filters
from utils.data_processor import (
    get_validation_summary,
    get_missing_subplots_analysis,
    get_vegetation_density_analysis,
    get_species_analysis,
    get_height_outliers,
    get_circumference_outliers,
    get_coverage_quality_check,
)

# Page config
st.set_page_config(
    page_title="Subplot Details - " + config.APP_TITLE,
    page_icon="🌳",
    layout="wide",
)

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Header
show_header()

st.markdown("## 🌳 Subplot Details & Vegetation Analysis")

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# Apply filters
filtered_gdf = create_sidebar_filters(gdf_subplots)

# Summary
summary = get_validation_summary(filtered_gdf)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Subplots", f"{summary['total']:,}")

with col2:
    st.metric("Valid", f"{summary['valid']:,}", f"{summary['valid_pct']:.1f}%")

with col3:
    st.metric("Invalid", f"{summary['invalid']:,}")

with col4:
    avg_area = (
        filtered_gdf["area_m2"].mean() if "area_m2" in filtered_gdf.columns else 0
    )
    st.metric("Avg Area", f"{avg_area:.1f} m²")

st.markdown("---")

# Check if vegetation data is available
has_vegetation = "plots_subplots_vegetation" in raw_data
has_measurements = "plots_subplots_vegetation_measurements" in raw_data
has_circumference = "complete" in raw_data

if has_vegetation:
    st.success("✅ Vegetation data available - Full analysis enabled")
else:
    st.info(
        "ℹ️ Basic geometry validation only - Upload complete Excel with 5 sheets for vegetation analysis"
    )

# Tab structure
if has_vegetation:
    tabs = st.tabs(
        [
            "📊 Overview",
            "🌲 Vegetation",
            "📏 Measurements",
            "⚠️ Quality Checks",
            "🔍 Individual",
        ]
    )
else:
    tabs = st.tabs(["📊 Overview", "🔍 Individual"])

# ============================================
# TAB 1: OVERVIEW
# ============================================

with tabs[0]:
    st.markdown("### 📊 Subplot Overview")

    # Search and filter
    col1, col2 = st.columns([2, 1])

    with col1:
        search_term = st.text_input(
            "Search by Subplot ID", placeholder="Enter subplot ID..."
        )

    with col2:
        show_only = st.selectbox(
            "Show",
            ["All Subplots", "Valid Only", "Invalid Only"],
        )

    # Apply filters
    search_df = filtered_gdf.copy()

    if search_term:
        search_df = search_df[
            search_df["subplot_id"]
            .astype(str)
            .str.contains(search_term, case=False, na=False)
        ]

    if show_only == "Valid Only":
        search_df = search_df[search_df["geom_valid"]]
    elif show_only == "Invalid Only":
        search_df = search_df[~search_df["geom_valid"]]

    st.markdown(f"**Showing {len(search_df)} of {len(filtered_gdf)} subplots**")

    st.markdown("---")

    # Display table
    display_cols = ["subplot_id", "geom_valid", "enumerator"]

    # Add vegetation columns if available
    if has_vegetation:
        for col in ["total_trees", "species_count", "avg_coverage"]:
            if col in search_df.columns:
                display_cols.append(col)

    # Add geometry columns
    for col in ["area_m2", "nr_vertices", "reasons"]:
        if col in search_df.columns:
            display_cols.append(col)

    display_df = search_df[display_cols].copy()

    st.dataframe(
        display_df,
        use_container_width=True,
        height=500,
    )

    # Export
    st.markdown("---")
    csv_data = display_df.to_csv(index=False)
    st.download_button(
        "📊 Download as CSV",
        data=csv_data,
        file_name=f"{config.PARTNER}_subplots.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ============================================
# TAB 2: VEGETATION (if available)
# ============================================

if has_vegetation:
    with tabs[1]:
        st.markdown("### 🌲 Vegetation Analysis")

        # Missing subplots analysis
        missing_analysis = get_missing_subplots_analysis(raw_data)

        if missing_analysis:
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Subplots WITHOUT Vegetation", missing_analysis["count"])

            with col2:
                total_subplots = len(raw_data["plots_subplots"]["SUBPLOT_KEY"].unique())
                pct = (
                    (missing_analysis["count"] / total_subplots * 100)
                    if total_subplots > 0
                    else 0
                )
                st.metric("Percentage", f"{pct:.1f}%")

            if missing_analysis["count"] > 0:
                with st.expander(
                    f"View {missing_analysis['count']} subplots without vegetation"
                ):
                    st.dataframe(missing_analysis["subplots"], use_container_width=True)

        st.markdown("---")

        # Density analysis
        st.markdown("#### 📊 Tree Density Analysis")

        density_analysis = get_vegetation_density_analysis(raw_data)

        if density_analysis:
            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Subplots with ZERO Trees", density_analysis["zero_trees_count"]
                )

                if density_analysis["zero_trees_count"] > 0:
                    with st.expander("View subplots with zero trees"):
                        st.dataframe(
                            density_analysis["zero_trees_df"], use_container_width=True
                        )

            with col2:
                # Histogram of tree counts
                fig = px.histogram(
                    density_analysis["density_df"],
                    x="vegetation_type_number",
                    nbins=30,
                    title="Distribution of Trees per Subplot",
                    labels={"vegetation_type_number": "Number of Trees"},
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Species analysis
        st.markdown("#### 🌳 Species Analysis")

        species_tabs = st.tabs(["Primary Trees", "Young Trees", "Non-Primary Trees"])

        with species_tabs[0]:
            primary = get_species_analysis(raw_data, "primary")
            if primary:
                st.metric(
                    "Primary Tree Species (Other)",
                    primary["count"],
                    f"{primary['total_trees']:.0f} trees",
                )
                st.dataframe(
                    primary["species_df"], use_container_width=True, height=300
                )

        with species_tabs[1]:
            young = get_species_analysis(raw_data, "young")
            if young:
                st.metric(
                    "Young Tree Species (Other)",
                    young["count"],
                    f"{young['total_trees']:.0f} trees",
                )
                st.dataframe(young["species_df"], use_container_width=True, height=300)

        with species_tabs[2]:
            non_primary = get_species_analysis(raw_data, "non_primary")
            if non_primary:
                st.metric(
                    "Non-Primary Species (Other)",
                    non_primary["count"],
                    f"{non_primary['total_trees']:.0f} trees",
                )
                st.dataframe(
                    non_primary["species_df"], use_container_width=True, height=300
                )

# ============================================
# TAB 3: MEASUREMENTS (if available)
# ============================================

if has_vegetation and has_measurements:
    with tabs[2]:
        st.markdown("### 📏 Measurement Analysis")

        # Height outliers
        st.markdown("#### 📊 Height Outlier Detection")

        height_outliers = get_height_outliers(raw_data, threshold_multiplier=4)

        if height_outliers:
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Height Outliers Detected", height_outliers["count"])

            with col2:
                # Tall trees (>25m)
                tall_trees = height_outliers["all_with_flags"][
                    height_outliers["all_with_flags"]["tree_height_m"] > 25
                ]
                st.metric("Trees > 25m Height", len(tall_trees))

            if height_outliers["count"] > 0:
                with st.expander("View height outliers"):
                    st.dataframe(
                        height_outliers["outliers_df"][
                            [
                                "enumerator",
                                "VEGETATION_KEY",
                                "tree_height_m",
                                "median_height",
                                "tree_year_planted",
                                "Upper_outliers",
                                "Lower_outliers",
                            ]
                        ],
                        use_container_width=True,
                    )

        st.markdown("---")

        # Circumference outliers
        if has_circumference:
            st.markdown("#### 📊 Circumference Outlier Detection")

            circ_outliers = get_circumference_outliers(raw_data, threshold_multiplier=4)

            if circ_outliers:
                st.metric("Circumference Outliers", circ_outliers["count"])

                if circ_outliers["count"] > 0:
                    with st.expander("View circumference outliers"):
                        st.dataframe(
                            circ_outliers["outliers_df"][
                                [
                                    "enumerator",
                                    "MEASUREMENT_KEY",
                                    "circumference_bh",
                                    "median_cir",
                                    "tree_year_planted",
                                    "Upper_outliers",
                                    "Lower_outliers",
                                ]
                            ],
                            use_container_width=True,
                        )

# ============================================
# TAB 4: QUALITY CHECKS (if vegetation available)
# ============================================

if has_vegetation:
    with tabs[3]:
        st.markdown("### ⚠️ Data Quality Checks")

        # Coverage quality check
        st.markdown("#### 🌾 Coverage Quality Check")
        st.caption(
            "Coverage should only be used for non-woody species (grasses, crops)"
        )

        coverage_check = get_coverage_quality_check(raw_data, max_percentage=5)

        if coverage_check:
            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Other Species in Coverage", f"{coverage_check['percentage']:.1f}%"
                )

                if coverage_check["is_valid"]:
                    st.success("✅ Within acceptable range (<5%)")
                else:
                    st.error("❌ Exceeds 5% threshold")

            with col2:
                st.metric("Total Coverage Entries", coverage_check["total_coverage"])
                st.metric(
                    "'Other' Species Count", coverage_check["other_species_count"]
                )

            if coverage_check["other_species_count"] > 0:
                with st.expander("View other species in coverage"):
                    st.dataframe(
                        coverage_check["coverage_df"], use_container_width=True
                    )

# ============================================
# LAST TAB: INDIVIDUAL INSPECTOR
# ============================================

with tabs[-1]:
    st.markdown("### 🔬 Individual Subplot Inspector")

    if len(filtered_gdf) > 0:
        subplot_ids = filtered_gdf["subplot_id"].tolist()

        selected_subplot = st.selectbox(
            "Select subplot:",
            options=subplot_ids,
            format_func=lambda x: f"{x} {'✅' if filtered_gdf[filtered_gdf['subplot_id']==x]['geom_valid'].iloc[0] else '❌'}",
        )

        if selected_subplot:
            subplot_data = filtered_gdf[
                filtered_gdf["subplot_id"] == selected_subplot
            ].iloc[0]

            # Basic info
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("#### 📋 Basic Info")
                st.write(f"**ID:** {subplot_data['subplot_id']}")
                st.write(
                    f"**Status:** {'✅ Valid' if subplot_data['geom_valid'] else '❌ Invalid'}"
                )
                if "enumerator" in subplot_data.index:
                    st.write(f"**Enumerator:** {subplot_data['enumerator']}")

            with col2:
                st.markdown("#### 📐 Geometry")
                if "area_m2" in subplot_data.index:
                    st.write(f"**Area:** {subplot_data['area_m2']:.2f} m²")
                if "nr_vertices" in subplot_data.index:
                    st.write(f"**Vertices:** {subplot_data['nr_vertices']}")

            with col3:
                st.markdown("#### 🌲 Vegetation")
                if has_vegetation:
                    if "total_trees" in subplot_data.index:
                        st.write(f"**Trees:** {subplot_data['total_trees']:.0f}")
                    if "species_count" in subplot_data.index:
                        st.write(f"**Species:** {subplot_data['species_count']:.0f}")
                    if "avg_coverage" in subplot_data.index:
                        st.write(f"**Coverage:** {subplot_data['avg_coverage']:.0f}%")
                else:
                    st.info("Upload complete file for vegetation data")

            # Show issues if invalid
            if not subplot_data["geom_valid"] and "reasons" in subplot_data.index:
                st.markdown("---")
                st.markdown("#### ❌ Issues")
                for reason in str(subplot_data["reasons"]).split(";"):
                    if reason.strip():
                        st.error(f"• {reason.strip()}")
    else:
        st.info("No subplots to inspect")
