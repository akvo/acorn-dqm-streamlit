"""
Plot Issues Page - Enhanced with quick summary and better issue distinction
"""

import streamlit as st
import pandas as pd
import json
import numpy as np
from datetime import datetime
from utils.download_helpers import *
from utils.validators import aggregate_validation_results
import config

st.set_page_config(page_title="Plot Issues", page_icon="🔍", layout="wide")

st.title("🔍 Plot Issues")


# Helper functions for JSON serialization
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
            return f"<span style='background-color: {color}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.85em; font-weight: bold;'>{label}</span>"

    return f"<span style='background-color: #757575; color: white; padding: 2px 8px; border-radius: 3px; font-size: 0.85em;'>OTHER</span>"


if not st.session_state.get("data_loaded", False):
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("Go to Home"):
        st.switch_page("pages/1_📊_Overview.py")
    st.stop()

# Get data
plots_subplots = st.session_state.merged_data["plots_subplots"]
validation_results = st.session_state.validation_results

# Get vegetation and measurement data if available
plots_vegetation = st.session_state.merged_data.get("plots_vegetation", pd.DataFrame())
plots_measurements = st.session_state.merged_data.get(
    "plots_measurements", pd.DataFrame()
)

# Group by plot
plot_groups = plots_subplots.groupby("PLOT_KEY")

# Calculate plot-level validation with enhanced details
plot_issues = []

for plot_id, group in plot_groups:
    plot_info = {
        "plot_id": plot_id,
        "enumerator": (
            group["enumerator"].iloc[0] if "enumerator" in group.columns else "Unknown"
        ),
        "collection_date": (
            str(group["SubmissionDate"].iloc[0])
            if "SubmissionDate" in group.columns
            else "Unknown"
        ),
        "total_subplots": len(group),
        "invalid_subplots": 0,
        "issue_count": 0,
        "issues_summary": {},
        "issue_types_detail": {
            "geometry": 0,
            "measurement": 0,
            "species": 0,
            "coverage": 0,
            "missing_data": 0,
        },
        "species_problems": [],
        "subplots": [],
    }

    # Check each subplot
    for idx, subplot_row in group.iterrows():
        subplot_id = subplot_row.get("SUBPLOT_KEY")
        if subplot_id and subplot_id in validation_results["subplots"]:
            validation = validation_results["subplots"][subplot_id]

            subplot_data = {
                "subplot_id": subplot_id,
                "valid": validation["valid"],
                "issues": validation["issues"],
                "area_m2": (
                    float(validation.get("area_m2"))
                    if validation.get("area_m2")
                    else None
                ),
                "geometry": subplot_row.get("geometry"),
            }

            plot_info["subplots"].append(subplot_data)

            if not validation["valid"]:
                plot_info["invalid_subplots"] += 1

            plot_info["issue_count"] += len(validation["issues"])

            # Categorize issues with detail
            for issue in validation["issues"]:
                issue_type = issue.get("type", "unknown")
                plot_info["issues_summary"][issue_type] = (
                    plot_info["issues_summary"].get(issue_type, 0) + 1
                )

                # Count by detailed type
                if "geometry" in issue_type.lower():
                    plot_info["issue_types_detail"]["geometry"] += 1
                elif "measurement" in issue_type.lower():
                    plot_info["issue_types_detail"]["measurement"] += 1
                elif "species" in issue_type.lower():
                    plot_info["issue_types_detail"]["species"] += 1
                elif "coverage" in issue_type.lower():
                    plot_info["issue_types_detail"]["coverage"] += 1
                elif "missing" in issue_type.lower():
                    plot_info["issue_types_detail"]["missing_data"] += 1

    # Get species information for this plot
    if not plots_vegetation.empty:
        plot_veg = plots_vegetation[plots_vegetation["PLOT_KEY"] == plot_id]
        for idx, veg_row in plot_veg.iterrows():
            veg_id = veg_row.get("VEGETATION_KEY")
            if veg_id and veg_id in validation_results.get("vegetation", {}):
                validation = validation_results["vegetation"][veg_id]
                if validation.get("issues"):
                    species_name = (
                        veg_row.get("woody_species")
                        or veg_row.get("other_species")
                        or veg_row.get("non_woody_species")
                        or "Unknown species"
                    )
                    plot_info["species_problems"].append(
                        {
                            "species": species_name,
                            "subplot": veg_row.get("SUBPLOT_KEY"),
                            "issues": validation["issues"],
                        }
                    )

    plot_info["validation_status"] = (
        "valid" if plot_info["invalid_subplots"] == 0 else "invalid"
    )

    # Determine primary issue type
    if plot_info["issue_types_detail"]["geometry"] > 0:
        plot_info["primary_issue"] = "Geometry"
    elif plot_info["issue_types_detail"]["measurement"] > 0:
        plot_info["primary_issue"] = "Measurement"
    elif plot_info["issue_types_detail"]["species"] > 0:
        plot_info["primary_issue"] = "Species"
    elif plot_info["issue_types_detail"]["coverage"] > 0:
        plot_info["primary_issue"] = "Coverage"
    else:
        plot_info["primary_issue"] = "Other"

    plot_issues.append(plot_info)

# Filter to invalid plots
invalid_plots = [p for p in plot_issues if p["validation_status"] == "invalid"]

# Display summary
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total Plots", len(plot_issues))

with col2:
    st.metric("Invalid Plots", len(invalid_plots))

with col3:
    if len(plot_issues) > 0:
        invalid_pct = (len(invalid_plots) / len(plot_issues)) * 100
        st.metric("Invalid %", f"{invalid_pct:.1f}%")

st.markdown("---")

# Bulk download section
st.subheader("📦 Bulk Download")

col1, col2, col3 = st.columns(3)

with col1:
    format_type = st.selectbox(
        "JSON Format",
        ["Hierarchical (Complete)", "Flat (Issues Only)", "GeoJSON (For GIS)"],
        help="Choose format based on your use case",
    )

with col2:
    st.write("")  # Spacer

with col3:
    if st.button("📥 Download All Invalid Plots", use_container_width=True):
        format_map = {
            "Hierarchical (Complete)": "hierarchical",
            "Flat (Issues Only)": "flat",
            "GeoJSON (For GIS)": "geojson",
        }

        selected_format = format_map[format_type]
        zip_data = create_bulk_download(invalid_plots, selected_format)

        st.download_button(
            label="⬇️ Download ZIP File",
            data=zip_data,
            file_name=f"invalid_plots_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            use_container_width=True,
        )

st.markdown("---")

# Filters
st.subheader("🔍 Filters")

col1, col2, col3, col4 = st.columns(4)

with col1:
    search_plot = st.text_input("🔍 Search Plot ID", "")

with col2:
    filter_enumerator = st.multiselect(
        "Filter by Enumerator",
        options=list(set([p["enumerator"] for p in invalid_plots])),
    )

with col3:
    filter_issue_type = st.multiselect(
        "Filter by Issue Type",
        options=["Geometry", "Measurement", "Species", "Coverage", "Missing Data"],
    )

with col4:
    sort_by = st.selectbox(
        "Sort by",
        ["Most Issues", "Date (Recent)", "Date (Oldest)", "Enumerator", "Plot ID"],
    )

# Apply filters
filtered_plots = invalid_plots

if search_plot:
    filtered_plots = [
        p for p in filtered_plots if search_plot.lower() in str(p["plot_id"]).lower()
    ]

if filter_enumerator:
    filtered_plots = [p for p in filtered_plots if p["enumerator"] in filter_enumerator]

if filter_issue_type:
    filtered_plots = [
        p for p in filtered_plots if p["primary_issue"] in filter_issue_type
    ]

# Sort
if sort_by == "Most Issues":
    filtered_plots = sorted(
        filtered_plots, key=lambda x: x["issue_count"], reverse=True
    )
elif sort_by == "Date (Recent)":
    filtered_plots = sorted(
        filtered_plots, key=lambda x: x["collection_date"], reverse=True
    )
elif sort_by == "Date (Oldest)":
    filtered_plots = sorted(filtered_plots, key=lambda x: x["collection_date"])
elif sort_by == "Enumerator":
    filtered_plots = sorted(filtered_plots, key=lambda x: x["enumerator"])
elif sort_by == "Plot ID":
    filtered_plots = sorted(filtered_plots, key=lambda x: x["plot_id"])

st.markdown("---")

# QUICK SUMMARY TABLE - NEW FEATURE
st.subheader(f"📋 Quick Summary ({len(filtered_plots)} plots)")

if len(filtered_plots) == 0:
    st.info("No invalid plots found with current filters.")
else:
    # Create summary table
    summary_data = []
    for plot in filtered_plots:
        summary_data.append(
            {
                "Plot ID": plot["plot_id"],
                "Enumerator": plot["enumerator"],
                "Date": plot["collection_date"],
                "Invalid Subplots": f"{plot['invalid_subplots']}/{plot['total_subplots']}",
                "Total Issues": plot["issue_count"],
                "Primary Issue": plot["primary_issue"],
                "Geometry": "✓" if plot["issue_types_detail"]["geometry"] > 0 else "✗",
                "Measurement": (
                    "✓" if plot["issue_types_detail"]["measurement"] > 0 else "✗"
                ),
                "Species": "✓" if plot["issue_types_detail"]["species"] > 0 else "✗",
            }
        )

    df_summary = pd.DataFrame(summary_data)

    # Display with styling
    st.dataframe(
        df_summary,
        use_container_width=True,
        height=400,
        hide_index=True,
    )

    # Export summary table
    csv = df_summary.to_csv(index=False)
    st.download_button(
        label="📊 Export Summary as CSV",
        data=csv,
        file_name=f"plot_issues_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )

    st.markdown("---")

    # Detailed view with expandable sections
    st.subheader("📖 Detailed Issues")

    for idx, plot in enumerate(filtered_plots):
        with st.expander(
            f"**{plot['plot_id']}** - {plot['enumerator']} - {plot['primary_issue']} Issues ({plot['invalid_subplots']}/{plot['total_subplots']} invalid)",
            expanded=False,
        ):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.write(f"**Collection Date:** {plot['collection_date']}")
                st.write(f"**Total Issues:** {plot['issue_count']}")

                # Issue breakdown with badges
                st.write("**Issues Breakdown:**")
                col_a, col_b, col_c = st.columns(3)

                with col_a:
                    if plot["issue_types_detail"]["geometry"] > 0:
                        st.markdown(
                            f"{get_issue_badge('geometry')}: {plot['issue_types_detail']['geometry']}",
                            unsafe_allow_html=True,
                        )
                    if plot["issue_types_detail"]["measurement"] > 0:
                        st.markdown(
                            f"{get_issue_badge('measurement')}: {plot['issue_types_detail']['measurement']}",
                            unsafe_allow_html=True,
                        )

                with col_b:
                    if plot["issue_types_detail"]["species"] > 0:
                        st.markdown(
                            f"{get_issue_badge('species')}: {plot['issue_types_detail']['species']}",
                            unsafe_allow_html=True,
                        )
                    if plot["issue_types_detail"]["coverage"] > 0:
                        st.markdown(
                            f"{get_issue_badge('coverage')}: {plot['issue_types_detail']['coverage']}",
                            unsafe_allow_html=True,
                        )

                with col_c:
                    if plot["issue_types_detail"]["missing_data"] > 0:
                        st.markdown(
                            f"{get_issue_badge('missing_data')}: {plot['issue_types_detail']['missing_data']}",
                            unsafe_allow_html=True,
                        )

                # Species problems if any
                if plot["species_problems"]:
                    st.write("**Species Problems:**")
                    for sp_issue in plot["species_problems"]:
                        st.markdown(
                            f"🌿 **{sp_issue['species']}** (Subplot: {sp_issue['subplot']})"
                        )
                        for issue in sp_issue["issues"][:2]:  # Show first 2
                            st.markdown(f"  - {issue['message']}")

                st.markdown("---")

                # List invalid subplots with issue type badges
                st.write("**Invalid Subplots Details:**")
                invalid_subs = [s for s in plot["subplots"] if not s["valid"]]

                for subplot in invalid_subs:
                    st.markdown(f"**📍 {subplot['subplot_id']}**")
                    for issue in subplot["issues"]:
                        severity = issue.get("severity", "info")
                        issue_type = issue.get("type", "unknown")
                        color = config.SEVERITY_COLORS.get(severity, "#999999")
                        badge = get_issue_badge(issue_type)

                        st.markdown(
                            f"<div style='padding: 0.5rem; margin: 0.25rem 0; border-left: 4px solid {color}; background-color: {color}15;'>"
                            f"{badge} <strong>{severity.upper()}:</strong> {issue['message']}"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

            with col2:
                # Download buttons
                st.write("**Download:**")

                # Hierarchical JSON
                json_hier = create_hierarchical_json(plot)
                json_hier_clean = clean_for_json(json_hier)
                st.download_button(
                    label="📥 JSON (Detailed)",
                    data=json.dumps(json_hier_clean, indent=2),
                    file_name=f"{plot['plot_id']}_detailed.json",
                    mime="application/json",
                    key=f"hier_{idx}",
                    use_container_width=True,
                )

                # Flat JSON
                json_flat = create_flat_json(plot)
                json_flat_clean = clean_for_json(json_flat)
                st.download_button(
                    label="📥 JSON (Issues)",
                    data=json.dumps(json_flat_clean, indent=2),
                    file_name=f"{plot['plot_id']}_issues.json",
                    mime="application/json",
                    key=f"flat_{idx}",
                    use_container_width=True,
                )

                # GeoJSON
                geojson = create_geojson(plot)
                geojson_clean = clean_for_json(geojson)
                st.download_button(
                    label="🗺️ GeoJSON",
                    data=json.dumps(geojson_clean, indent=2),
                    file_name=f"{plot['plot_id']}_geometry.geojson",
                    mime="application/geo+json",
                    key=f"geo_{idx}",
                    use_container_width=True,
                )

                # View details button
                if st.button(
                    "👁️ View Details", key=f"view_{idx}", use_container_width=True
                ):
                    st.session_state.selected_plot = plot["plot_id"]
                    st.switch_page("pages/3_🌳_Subplot_Details.py")
