"""
Subplot Details Page - Enhanced with issue type badges and species information
"""

import streamlit as st
import pandas as pd
import json
from utils.download_helpers import *
import config
import numpy as np
from datetime import datetime


st.set_page_config(page_title="Subplot Details", page_icon="🌳", layout="wide")

st.title("🌳 Subplot Details")


def make_json_serializable(obj):
    """Convert non-serializable objects to serializable format"""
    if hasattr(obj, "__geo_interface__"):
        return obj.__geo_interface__
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    return obj


def clean_for_json(data):
    """Recursively clean data structure for JSON serialization"""
    if isinstance(data, dict):
        return {k: clean_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_for_json(item) for item in data]
    else:
        return make_json_serializable(data)


def get_issue_badge(issue_type):
    """Return badge HTML for issue type"""
    badges = {
        "geometry": ("📐 GEOMETRY", "#1976D2"),
        "measurement": ("📏 MEASUREMENT", "#F57C00"),
        "species": ("🌿 SPECIES", "#388E3C"),
        "coverage": ("📊 COVERAGE", "#9C27B0"),
        "missing_data": ("⚠️ MISSING DATA", "#D32F2F"),
    }

    for key, (label, color) in badges.items():
        if key in issue_type.lower():
            return f"<span style='background-color: {color}; color: white; padding: 3px 10px; border-radius: 4px; font-size: 0.85em; font-weight: bold; margin-right: 5px;'>{label}</span>"

    return f"<span style='background-color: #757575; color: white; padding: 3px 10px; border-radius: 4px; font-size: 0.85em; margin-right: 5px;'>OTHER</span>"


if not st.session_state.get("data_loaded", False):
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("Go to Home"):
        st.switch_page("pages/1_📊_Overview.py")
    st.stop()

# Get data
plots_subplots = st.session_state.merged_data["plots_subplots"]
validation_results = st.session_state.validation_results

# Plot selection
available_plots = plots_subplots["PLOT_KEY"].unique().tolist()

# Check if plot was selected from previous page
selected_plot = st.session_state.get(
    "selected_plot", available_plots[0] if available_plots else None
)

selected_plot = st.selectbox(
    "Select Plot",
    options=available_plots,
    index=(
        available_plots.index(selected_plot) if selected_plot in available_plots else 0
    ),
)

if selected_plot:
    # Get plot data
    plot_data = plots_subplots[plots_subplots["PLOT_KEY"] == selected_plot]

    if len(plot_data) > 0:
        # Display plot info
        st.subheader(f"Plot: {selected_plot}")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            enumerator = (
                plot_data["enumerator"].iloc[0]
                if "enumerator" in plot_data.columns
                else "Unknown"
            )
            st.write(f"**Enumerator:** {enumerator}")

        with col2:
            date = (
                plot_data["SubmissionDate"].iloc[0]
                if "SubmissionDate" in plot_data.columns
                else "Unknown"
            )
            st.write(f"**Date:** {date}")

        with col3:
            total_subplots = len(plot_data)
            st.write(f"**Total Subplots:** {total_subplots}")

        with col4:
            # Count invalid subplots
            invalid_count = 0
            for idx, row in plot_data.iterrows():
                subplot_id = row.get("SUBPLOT_KEY")
                if subplot_id in validation_results["subplots"]:
                    if not validation_results["subplots"][subplot_id]["valid"]:
                        invalid_count += 1

            st.write(f"**Invalid:** {invalid_count}/{total_subplots}")

        st.markdown("---")

        # Tabs for different types of issues
        tab1, tab2, tab3 = st.tabs(
            ["📐 Geometry Issues", "🌿 Vegetation Issues", "📏 Measurement Issues"]
        )

        with tab1:
            st.subheader("Geometry Validation")

            # Filter subplots with geometry issues
            geometry_issues = []

            for idx, row in plot_data.iterrows():
                subplot_id = row.get("SUBPLOT_KEY")
                if subplot_id in validation_results["subplots"]:
                    validation = validation_results["subplots"][subplot_id]
                    geom_issues = [
                        i
                        for i in validation["issues"]
                        if "geometry" in i["type"].lower()
                    ]

                    if geom_issues:
                        geometry_issues.append(
                            {
                                "subplot_id": subplot_id,
                                "issues": geom_issues,
                                "geometry": row.get("geometry"),
                            }
                        )

            if len(geometry_issues) == 0:
                st.success("✅ No geometry issues found!")
            else:
                st.warning(
                    f"⚠️ Found {len(geometry_issues)} subplot(s) with geometry issues"
                )

                for subplot_data in geometry_issues:
                    with st.container():
                        st.markdown(f"### Subplot: {subplot_data['subplot_id']}")

                        for issue in subplot_data["issues"]:
                            severity = issue.get("severity", "info")
                            issue_type = issue.get("type", "unknown")
                            color = config.SEVERITY_COLORS.get(severity, "#999999")
                            badge = get_issue_badge(issue_type)

                            st.markdown(
                                f"<div style='padding: 0.75rem; margin: 0.5rem 0; border-left: 4px solid {color}; background-color: {color}15;'>"
                                f"{badge}"
                                f"<strong style='color: {color};'>{severity.upper()}:</strong> {issue['message']}<br>"
                                f"<small><b>Field:</b> {issue.get('field', 'N/A')} | "
                                f"<b>Value:</b> {issue.get('value', 'N/A')} | "
                                f"<b>Threshold:</b> {issue.get('threshold', 'N/A')}</small>"
                                f"</div>",
                                unsafe_allow_html=True,
                            )

                        st.markdown("---")

        with tab2:
            st.subheader("Vegetation Validation")

            # Get vegetation data for this plot
            plots_vegetation = st.session_state.merged_data.get(
                "plots_vegetation", pd.DataFrame()
            )

            if plots_vegetation.empty:
                st.info("No vegetation data available for this plot.")
            else:
                plot_veg = plots_vegetation[
                    plots_vegetation["PLOT_KEY"] == selected_plot
                ]

                # Filter vegetation with issues
                veg_issues = []

                for idx, row in plot_veg.iterrows():
                    veg_id = row.get("VEGETATION_KEY")
                    subplot_id = row.get("SUBPLOT_KEY")

                    if veg_id and veg_id in validation_results.get("vegetation", {}):
                        validation = validation_results["vegetation"][veg_id]

                        if validation.get("issues"):
                            species_name = (
                                row.get("woody_species")
                                or row.get("other_species")
                                or row.get("non_woody_species")
                                or "Unknown species"
                            )

                            veg_issues.append(
                                {
                                    "subplot_id": subplot_id,
                                    "vegetation_id": veg_id,
                                    "species": species_name,
                                    "species_type": row.get(
                                        "vegetation_species_type", "Unknown"
                                    ),
                                    "issues": validation["issues"],
                                }
                            )

                if len(veg_issues) == 0:
                    st.success("✅ No vegetation issues found!")
                else:
                    st.warning(
                        f"⚠️ Found {len(veg_issues)} vegetation record(s) with issues"
                    )

                    for veg_data in veg_issues:
                        with st.container():
                            st.markdown(f"### Subplot: {veg_data['subplot_id']}")
                            st.markdown(
                                f"🌿 **Species:** {veg_data['species']} ({veg_data['species_type']})"
                            )

                            for issue in veg_data["issues"]:
                                severity = issue.get("severity", "info")
                                issue_type = issue.get("type", "unknown")
                                color = config.SEVERITY_COLORS.get(severity, "#999999")
                                badge = get_issue_badge(issue_type)

                                st.markdown(
                                    f"<div style='padding: 0.75rem; margin: 0.5rem 0; border-left: 4px solid {color}; background-color: {color}15;'>"
                                    f"{badge}"
                                    f"<strong style='color: {color};'>{severity.upper()}:</strong> {issue['message']}"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                            st.markdown("---")

        with tab3:
            st.subheader("Measurement Validation")

            # Get measurement data for this plot
            plots_measurements = st.session_state.merged_data.get(
                "plots_measurements", pd.DataFrame()
            )

            if plots_measurements.empty:
                st.info("No measurement data available for this plot.")
            else:
                plot_meas = plots_measurements[
                    plots_measurements["PLOT_KEY"] == selected_plot
                ]

                # Filter measurements with issues
                meas_issues = []

                for idx, row in plot_meas.iterrows():
                    meas_id = row.get("MEASUREMENT_KEY")
                    subplot_id = row.get("SUBPLOT_KEY")
                    veg_id = row.get("VEGETATION_KEY")

                    if meas_id and meas_id in validation_results.get(
                        "measurements", {}
                    ):
                        validation = validation_results["measurements"][meas_id]

                        if validation.get("issues"):
                            # Get species name if available
                            species_name = "Unknown"
                            if not plots_vegetation.empty and veg_id:
                                veg_row = plots_vegetation[
                                    plots_vegetation["VEGETATION_KEY"] == veg_id
                                ]
                                if not veg_row.empty:
                                    species_name = (
                                        veg_row.iloc[0].get("woody_species")
                                        or veg_row.iloc[0].get("other_species")
                                        or veg_row.iloc[0].get("non_woody_species")
                                        or "Unknown"
                                    )

                            meas_issues.append(
                                {
                                    "subplot_id": subplot_id,
                                    "vegetation_id": veg_id,
                                    "measurement_id": meas_id,
                                    "species": species_name,
                                    "height": row.get("tree_height_m"),
                                    "circumference": row.get("circumference_bh"),
                                    "year_planted": row.get("tree_year_planted"),
                                    "issues": validation["issues"],
                                }
                            )

                if len(meas_issues) == 0:
                    st.success("✅ No measurement issues found!")
                else:
                    st.warning(f"⚠️ Found {len(meas_issues)} measurement(s) with issues")

                    for meas_data in meas_issues:
                        with st.container():
                            st.markdown(f"### Subplot: {meas_data['subplot_id']}")
                            st.markdown(f"🌿 **Species:** {meas_data['species']}")

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric(
                                    "Height",
                                    (
                                        f"{meas_data['height']}m"
                                        if meas_data["height"]
                                        else "N/A"
                                    ),
                                )
                            with col2:
                                st.metric(
                                    "Circumference",
                                    (
                                        f"{meas_data['circumference']}cm"
                                        if meas_data["circumference"]
                                        else "N/A"
                                    ),
                                )
                            with col3:
                                st.metric(
                                    "Year Planted",
                                    (
                                        meas_data["year_planted"]
                                        if meas_data["year_planted"]
                                        else "N/A"
                                    ),
                                )

                            for issue in meas_data["issues"]:
                                severity = issue.get("severity", "info")
                                issue_type = issue.get("type", "unknown")
                                color = config.SEVERITY_COLORS.get(severity, "#999999")
                                badge = get_issue_badge(issue_type)

                                st.markdown(
                                    f"<div style='padding: 0.75rem; margin: 0.5rem 0; border-left: 4px solid {color}; background-color: {color}15;'>"
                                    f"{badge}"
                                    f"<strong style='color: {color};'>{severity.upper()}:</strong> {issue['message']}"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                            st.markdown("---")

        st.markdown("---")

        # Download section
        st.subheader("📥 Download This Plot")

        # Prepare plot data for download
        plot_download_data = {
            "plot_id": selected_plot,
            "enumerator": enumerator,
            "collection_date": str(date),
            "validation_status": "invalid" if invalid_count > 0 else "valid",
            "issues_summary": {"invalid_subplots": invalid_count},
            "subplots": [],
        }

        for idx, row in plot_data.iterrows():
            subplot_id = row.get("SUBPLOT_KEY")
            if subplot_id in validation_results["subplots"]:
                validation = validation_results["subplots"][subplot_id]
                plot_download_data["subplots"].append(
                    {
                        "subplot_id": subplot_id,
                        "valid": validation["valid"],
                        "issues": validation["issues"],
                        "area_m2": validation.get("area_m2"),
                        "geometry": row.get("geometry"),
                    }
                )

        col1, col2, col3 = st.columns(3)

        with col1:
            json_hier = create_hierarchical_json(plot_download_data)
            st.download_button(
                label="📥 Download JSON (Detailed)",
                data=json.dumps(clean_for_json(json_hier), indent=2),
                file_name=f"{selected_plot}_detailed.json",
                mime="application/json",
                use_container_width=True,
            )

        with col2:
            json_flat = create_flat_json(plot_download_data)
            st.download_button(
                label="📥 Download JSON (Issues Only)",
                data=json.dumps(clean_for_json(json_flat), indent=2),
                file_name=f"{selected_plot}_issues.json",
                mime="application/json",
                use_container_width=True,
            )

        with col3:
            geojson = create_geojson(plot_download_data)
            st.download_button(
                label="🗺️ Download GeoJSON",
                data=json.dumps(clean_for_json(geojson), indent=2),
                file_name=f"{selected_plot}_geometry.geojson",
                mime="application/geo+json",
                use_container_width=True,
            )
