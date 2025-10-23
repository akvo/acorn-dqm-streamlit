"""
Enumerator Performance Analysis - Error-focused quality control
Uses centralized utility functions for clean, maintainable code
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import config
from ui.components import show_header
from utils.data_merge_utils import (
    merge_with_enumerator,
    calculate_tree_age,
    get_species_column,
)
from utils.vegetation_validation import (
    detect_height_outliers,
    detect_circumference_outliers,
    detect_suspicious_circumference_by_age,
)

# Page config
st.set_page_config(
    page_title="Enumerator Performance - " + config.APP_TITLE,
    page_icon="👥",
    layout="wide",
)

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Header
show_header()

st.markdown("## 👥 Enumerator Performance - Error Analysis")
st.markdown("Track validation errors and quality issues by enumerator")

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# Check if vegetation data available
has_vegetation = "plots_subplots_vegetation" in raw_data
has_measurements = "plots_subplots_vegetation_measurements" in raw_data

st.markdown("---")

# ============================================
# ENUMERATOR SELECTION
# ============================================

enumerators = (
    sorted(gdf_subplots["enumerator"].unique().tolist())
    if "enumerator" in gdf_subplots.columns
    else []
)

if not enumerators:
    st.error("No enumerator data found in the dataset")
    st.stop()

col1, col2 = st.columns([3, 1])

with col1:
    selected_enumerators = st.multiselect(
        "Select enumerators to analyze",
        options=enumerators,
        default=enumerators,
    )

with col2:
    st.metric("Total Enumerators", len(enumerators))

if not selected_enumerators:
    st.info("Please select at least one enumerator to analyze")
    st.stop()

# Filter data
filtered_gdf = gdf_subplots[gdf_subplots["enumerator"].isin(selected_enumerators)]

st.markdown("---")

# ============================================
# TABS
# ============================================

if has_vegetation:
    tabs = st.tabs(
        [
            "📊 Error Overview",
            "📐 Geometry Errors",
            "⚠️ Vegetation Errors",
            "📏 Measurement Outliers",
            "📋 Error Details by Enumerator",
        ]
    )
else:
    tabs = st.tabs(["📊 Error Overview", "📐 Geometry Errors", "📋 Error Details"])

# ============================================
# TAB 1: ERROR OVERVIEW
# ============================================

with tabs[0]:
    st.markdown("### 📊 Error Rate Overview")

    # Calculate error stats by enumerator
    enum_stats = []

    for enum in selected_enumerators:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum]

        stats = {
            "Enumerator": enum,
            "Total Subplots": len(enum_data),
            "Valid Subplots": enum_data["geom_valid"].sum(),
            "Invalid Subplots": (~enum_data["geom_valid"]).sum(),
            "Error Rate %": (
                (~enum_data["geom_valid"]).sum() / len(enum_data) * 100
                if len(enum_data) > 0
                else 0
            ),
        }

        enum_stats.append(stats)

    stats_df = pd.DataFrame(enum_stats)

    # Display summary table
    st.dataframe(
        stats_df,
        use_container_width=True,
        height=min(500, len(stats_df) * 35 + 38),
    )

    st.markdown("---")

    # Error visualizations
    col1, col2 = st.columns(2)

    with col1:
        fig = px.bar(
            stats_df,
            x="Enumerator",
            y="Error Rate %",
            title="Error Rate by Enumerator",
            color="Error Rate %",
            color_continuous_scale=["green", "yellow", "red"],
            range_color=[0, 100],
        )
        fig.add_hline(
            y=10,
            line_dash="dash",
            line_color="red",
            annotation_text="10% Warning Threshold",
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = px.bar(
            stats_df,
            x="Enumerator",
            y=["Valid Subplots", "Invalid Subplots"],
            title="Valid vs Invalid Subplots by Enumerator",
            barmode="stack",
            color_discrete_map={
                "Valid Subplots": "#28a745",
                "Invalid Subplots": "#dc3545",
            },
        )
        fig.update_layout(legend_title_text="Status")
        st.plotly_chart(fig, use_container_width=True)

# ============================================
# TAB 2: GEOMETRY ERRORS
# ============================================

with tabs[1]:
    st.markdown("### 📐 Geometry Validation Errors")

    # Parse error reasons
    error_data = []

    for _, row in filtered_gdf[~filtered_gdf["geom_valid"]].iterrows():
        if pd.notna(row.get("reasons")):
            reasons = row["reasons"].split(";")
            for reason in reasons:
                reason = reason.strip()
                if reason:
                    error_data.append(
                        {
                            "enumerator": row["enumerator"],
                            "subplot_id": row["subplot_id"],
                            "error": reason,
                        }
                    )

    if error_data:
        errors_df = pd.DataFrame(error_data)

        # Error counts by type
        error_counts = errors_df.groupby("error").size().reset_index(name="count")
        error_counts = error_counts.sort_values("count", ascending=False)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                error_counts,
                x="count",
                y="error",
                orientation="h",
                title="Most Common Geometry Errors",
                color="count",
                color_continuous_scale="Reds",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(error_counts, use_container_width=True, height=400)

        st.markdown("---")
        st.markdown("### Errors by Enumerator")

        enum_errors = (
            errors_df.groupby(["enumerator", "error"]).size().reset_index(name="count")
        )

        fig = px.bar(
            enum_errors,
            x="enumerator",
            y="count",
            color="error",
            title="Geometry Errors Distribution by Enumerator",
            barmode="stack",
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("🔍 View all geometry errors"):
            st.dataframe(errors_df, use_container_width=True, height=400)
    else:
        st.success("✅ No geometry errors found!")

# ============================================
# TAB 3: VEGETATION ERRORS (if available)
# ============================================

if has_vegetation:
    with tabs[2]:
        st.markdown("### ⚠️ Vegetation Data Quality Issues")

        veg_df = raw_data["plots_subplots_vegetation"].copy()

        # Use utility function to merge with enumerator
        veg_with_enum = merge_with_enumerator(veg_df, filtered_gdf)

        # ERROR 1: Missing Subplots
        st.markdown("#### 🚫 Missing Vegetation Records")

        all_subplots = set(filtered_gdf["subplot_id"].unique())
        subplots_with_veg = set(veg_df["SUBPLOT_KEY"].unique())
        missing_subplots = all_subplots - subplots_with_veg

        if len(missing_subplots) > 0:
            missing_df = filtered_gdf[filtered_gdf["subplot_id"].isin(missing_subplots)]

            st.warning(f"⚠️ {len(missing_subplots)} subplots have NO vegetation records")

            missing_by_enum = (
                missing_df.groupby("enumerator").size().reset_index(name="count")
            )

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    missing_by_enum,
                    x="enumerator",
                    y="count",
                    title="Missing Vegetation Records by Enumerator",
                    color="count",
                    color_continuous_scale="Reds",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(missing_by_enum, use_container_width=True, height=300)
        else:
            st.success("✅ All subplots have vegetation records")

        # ERROR 2: Unidentified Species ('other')
        st.markdown("---")
        st.markdown("#### 🔍 Unidentified Species Requiring Botanical Verification")

        other_conditions = []
        for col in [
            "vegetation_species_type",
            "other_species",
            "woody_species",
            "non_woody_species",
        ]:
            if col in veg_with_enum.columns:
                other_conditions.append(veg_with_enum[col].str.lower() == "other")

        if other_conditions:
            combined_condition = other_conditions[0]
            for condition in other_conditions[1:]:
                combined_condition = combined_condition | condition

            other_species = veg_with_enum[combined_condition].copy()

            if len(other_species) > 0:
                st.warning(
                    f"⚠️ {len(other_species)} vegetation records with unidentified species ('other')"
                )

                other_by_enum = (
                    other_species.groupby("enumerator").size().reset_index(name="count")
                )

                col1, col2 = st.columns([2, 1])

                with col1:
                    fig = px.bar(
                        other_by_enum,
                        x="enumerator",
                        y="count",
                        title="Unidentified Species ('other') by Enumerator",
                        color="count",
                        color_continuous_scale="Oranges",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    st.dataframe(other_by_enum, use_container_width=True, height=300)
            else:
                st.success("✅ All species properly identified")
        else:
            st.success("✅ All species properly identified")

        # ERROR 3: Missing Measurements
        if has_measurements:
            st.markdown("---")
            st.markdown("#### 📏 Missing or Incomplete Measurements")

            measurements_df = raw_data["plots_subplots_vegetation_measurements"].copy()

            # Use utility function to merge with enumerator
            meas_with_enum = merge_with_enumerator(measurements_df, filtered_gdf)

            # Check missing height
            no_height = meas_with_enum[meas_with_enum["tree_height_m"].isna()]

            # Check missing circumference
            has_circ_bh = "circumference_bh" in meas_with_enum.columns
            has_circ_10 = "circumference_10cm" in meas_with_enum.columns

            if has_circ_bh and has_circ_10:
                no_circumference = meas_with_enum[
                    meas_with_enum["circumference_bh"].isna()
                    & meas_with_enum["circumference_10cm"].isna()
                ]
            elif has_circ_bh:
                no_circumference = meas_with_enum[
                    meas_with_enum["circumference_bh"].isna()
                ]
            elif has_circ_10:
                no_circumference = meas_with_enum[
                    meas_with_enum["circumference_10cm"].isna()
                ]
            else:
                no_circumference = pd.DataFrame()

            col1, col2 = st.columns(2)

            with col1:
                if len(no_height) > 0:
                    height_errors = (
                        no_height.groupby("enumerator").size().reset_index(name="count")
                    )

                    st.warning(f"⚠️ {len(no_height)} trees missing height")

                    fig = px.bar(
                        height_errors,
                        x="enumerator",
                        y="count",
                        title="Missing Height Measurements",
                        color="count",
                        color_continuous_scale="Reds",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.success("✅ No missing heights")

            with col2:
                if len(no_circumference) > 0:
                    circ_errors = (
                        no_circumference.groupby("enumerator")
                        .size()
                        .reset_index(name="count")
                    )

                    st.warning(f"⚠️ {len(no_circumference)} trees missing circumference")

                    fig = px.bar(
                        circ_errors,
                        x="enumerator",
                        y="count",
                        title="Missing Circumference Measurements",
                        color="count",
                        color_continuous_scale="Oranges",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.success("✅ No missing circumferences")

# ============================================
# TAB 4: MEASUREMENT OUTLIERS (if available)
# ============================================

if has_vegetation and has_measurements:
    with tabs[3]:
        st.markdown("### 📏 Measurement Outliers & Suspicious Values")

        measurements_df = raw_data["plots_subplots_vegetation_measurements"].copy()

        # Use utility function to merge with enumerator
        combined = merge_with_enumerator(measurements_df, filtered_gdf)

        # Get species column
        species_col = get_species_column(combined)

        # OUTLIER 1: Height Outliers
        st.markdown("#### 📐 Height Outliers")
        st.caption(
            "Detecting trees with heights >3x or <0.33x the median for their species"
        )

        if species_col and "tree_height_m" in combined.columns:
            # Use utility function to detect outliers
            combined_with_height = detect_height_outliers(
                combined, height_col="tree_height_m", species_col=species_col
            )

            outliers = combined_with_height[
                (combined_with_height["Upper_outliers"] == "outlier")
                | (combined_with_height["Lower_outliers"] == "outlier")
            ]

            if len(outliers) > 0:
                st.warning(f"⚠️ {len(outliers)} height outliers detected")

                outliers_by_enum = (
                    outliers.groupby("enumerator").size().reset_index(name="count")
                )

                col1, col2 = st.columns([2, 1])

                with col1:
                    fig = px.bar(
                        outliers_by_enum,
                        x="enumerator",
                        y="count",
                        title="Height Outliers by Enumerator",
                        color="count",
                        color_continuous_scale="Reds",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    st.dataframe(outliers_by_enum, use_container_width=True, height=300)

                with st.expander("🔍 View height outliers"):
                    display_cols = [
                        "VEGETATION_KEY",
                        "enumerator",
                        species_col,
                        "tree_height_m",
                        "median_height",
                        "Upper_outliers",
                        "Lower_outliers",
                    ]
                    st.dataframe(
                        outliers[display_cols], use_container_width=True, height=300
                    )
            else:
                st.success("✅ No height outliers detected")
        else:
            st.info("ℹ️ No height data available for outlier detection")

        # OUTLIER 2: Circumference vs Age Validation
        st.markdown("---")
        st.markdown("#### 🌳 Circumference vs Tree Age Validation")
        st.caption("Detecting unrealistic circumferences given tree planting year")

        if "complete" in raw_data:
            circ_df = raw_data["complete"].copy()

            # Determine which circumference column to use
            if "circumference_bh" in circ_df.columns:
                circ_data = circ_df[circ_df["circumference_bh"].notna()].copy()
                circ_col = "circumference_bh"
            elif "circumference_10cm" in circ_df.columns:
                circ_data = circ_df[circ_df["circumference_10cm"].notna()].copy()
                circ_col = "circumference_10cm"
            else:
                circ_data = pd.DataFrame()

            if len(circ_data) > 0 and "tree_year_planted" in circ_data.columns:
                # Use utility functions
                circ_data = merge_with_enumerator(circ_data, filtered_gdf)

                if len(circ_data) > 0:
                    circ_data = calculate_tree_age(circ_data)

                    if circ_data["tree_age"].notna().any():
                        circ_data = detect_suspicious_circumference_by_age(
                            circ_data, circ_col=circ_col
                        )

                        suspicious = circ_data[circ_data["suspicious"]]

                        if len(suspicious) > 0:
                            st.warning(
                                f"⚠️ {len(suspicious)} suspicious circumference values detected"
                            )

                            susp_by_enum = (
                                suspicious.groupby("enumerator")
                                .size()
                                .reset_index(name="count")
                            )

                            col1, col2 = st.columns([2, 1])

                            with col1:
                                fig = px.bar(
                                    susp_by_enum,
                                    x="enumerator",
                                    y="count",
                                    title="Suspicious Circumferences by Enumerator",
                                    color="count",
                                    color_continuous_scale="Oranges",
                                )
                                st.plotly_chart(fig, use_container_width=True)

                            with col2:
                                st.dataframe(
                                    susp_by_enum, use_container_width=True, height=300
                                )
                        else:
                            st.success("✅ No suspicious circumference values detected")
                    else:
                        st.info("ℹ️ Tree age data not available for validation")

        # OUTLIER 3: Circumference Outliers using median
        st.markdown("---")
        st.markdown("#### 📊 Circumference Outliers (Median Comparison)")
        st.caption("Detecting circumferences >4x or <0.25x the median")

        if "complete" in raw_data and species_col:
            circ_df = raw_data["complete"].copy()

            if "circumference_bh" in circ_df.columns:
                circ_check = circ_df[circ_df["circumference_bh"].notna()].copy()
                circ_col = "circumference_bh"

                if len(circ_check) > 0:
                    # Use utility functions
                    circ_check = merge_with_enumerator(circ_check, filtered_gdf)

                    if len(circ_check) > 0:
                        circ_check = detect_circumference_outliers(
                            circ_check, circ_col=circ_col, species_col=species_col
                        )

                        circ_outliers = circ_check[
                            (circ_check["Upper_outliers"] == "outlier")
                            | (circ_check["Lower_outliers"] == "outlier")
                        ]

                        if len(circ_outliers) > 0:
                            st.warning(
                                f"⚠️ {len(circ_outliers)} circumference outliers detected"
                            )

                            circ_out_by_enum = (
                                circ_outliers.groupby("enumerator")
                                .size()
                                .reset_index(name="count")
                            )

                            col1, col2 = st.columns([2, 1])

                            with col1:
                                fig = px.bar(
                                    circ_out_by_enum,
                                    x="enumerator",
                                    y="count",
                                    title="Circumference Outliers by Enumerator",
                                    color="count",
                                    color_continuous_scale="Purples",
                                )
                                st.plotly_chart(fig, use_container_width=True)

                            with col2:
                                st.dataframe(
                                    circ_out_by_enum,
                                    use_container_width=True,
                                    height=300,
                                )
                        else:
                            st.success("✅ No circumference outliers detected")

# ============================================
# LAST TAB: ERROR DETAILS BY ENUMERATOR
# ============================================

with tabs[-1]:
    st.markdown("### 📋 Individual Enumerator Error Report")

    selected_enum = st.selectbox(
        "Select enumerator for detailed error report",
        options=selected_enumerators,
        key="detail_enum",
    )

    if selected_enum:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == selected_enum]

        st.markdown(f"#### Error Report for: **{selected_enum}**")

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Subplots", len(enum_data))

        with col2:
            invalid = (~enum_data["geom_valid"]).sum()
            error_rate = (invalid / len(enum_data) * 100) if len(enum_data) > 0 else 0
            st.metric(
                "Invalid Subplots", invalid, f"{error_rate:.1f}%", delta_color="inverse"
            )

        with col3:
            valid = enum_data["geom_valid"].sum()
            st.metric("Valid Subplots", valid, f"{valid/len(enum_data)*100:.1f}%")

        with col4:
            error_types = set()
            for reasons in enum_data[~enum_data["geom_valid"]]["reasons"].dropna():
                error_types.update(r.strip() for r in reasons.split(";") if r.strip())
            st.metric("Unique Error Types", len(error_types))

        st.markdown("---")

        # Show invalid subplots only
        st.markdown("#### ⚠️ Invalid Subplots")

        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0:
            display_cols = ["subplot_id", "reasons"]

            for col in ["area_m2", "nr_vertices"]:
                if col in invalid_data.columns:
                    display_cols.append(col)

            st.dataframe(
                invalid_data[display_cols], use_container_width=True, height=400
            )
        else:
            st.success(f"✅ No invalid subplots for {selected_enum}")

        # Export error report
        st.markdown("---")
        st.markdown("#### 📥 Export Error Report")

        if len(invalid_data) > 0:
            csv_data = invalid_data.drop(columns=["geometry"], errors="ignore").to_csv(
                index=False
            )
            st.download_button(
                f"📊 Download {selected_enum}'s Error Report (CSV)",
                data=csv_data,
                file_name=f"{config.PARTNER}_{selected_enum}_errors.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No errors to export for this enumerator")
