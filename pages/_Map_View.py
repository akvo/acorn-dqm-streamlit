"""
Map View Page - Interactive map of plots
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import datetime
import json
import numpy as np
import pandas as pd
import config

st.set_page_config(page_title="Map View", page_icon="🗺️", layout="wide")

st.title("🗺️ Map View")


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


# Check if data is loaded
if not st.session_state.get("data_loaded", False):
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("🏠 Go to Home", use_container_width=True):
        st.switch_page("pages/1_📊_Overview.py")
    st.stop()

# Get data
plots_subplots = st.session_state.merged_data["plots_subplots"]
validation_results = st.session_state.validation_results

# Summary metrics
col1, col2, col3, col4 = st.columns(4)

total_subplots = len(plots_subplots)
valid_count = sum(1 for v in validation_results["subplots"].values() if v["valid"])
invalid_count = total_subplots - valid_count

with col1:
    st.metric("Total Subplots", total_subplots)

with col2:
    st.metric("Valid", valid_count, delta=f"{(valid_count/total_subplots*100):.1f}%")

with col3:
    st.metric(
        "Invalid",
        invalid_count,
        delta=f"{(invalid_count/total_subplots*100):.1f}%",
        delta_color="inverse",
    )

with col4:
    total_issues = sum(
        len(v["issues"]) for v in validation_results["subplots"].values()
    )
    st.metric("Total Issues", total_issues)

st.markdown("---")

# Map controls
st.subheader("🎛️ Map Controls")

col1, col2, col3, col4 = st.columns(4)

with col1:
    show_valid = st.checkbox("✅ Show Valid", value=True)

with col2:
    show_invalid = st.checkbox("❌ Show Invalid", value=True)

with col3:
    show_labels = st.checkbox("🏷️ Show Labels", value=False)

with col4:
    map_style = st.selectbox(
        "Map Style",
        ["OpenStreetMap", "CartoDB Positron", "CartoDB Dark_Matter"],
        index=0,
    )

# Filter by enumerator
enumerators = (
    plots_subplots["enumerator"].unique().tolist()
    if "enumerator" in plots_subplots.columns
    else []
)
if enumerators:
    selected_enumerators = st.multiselect(
        "👤 Filter by Enumerator", options=["All"] + enumerators, default=["All"]
    )

    if "All" not in selected_enumerators and selected_enumerators:
        plots_subplots = plots_subplots[
            plots_subplots["enumerator"].isin(selected_enumerators)
        ]

st.markdown("---")

# Create map
if "geometry" in plots_subplots.columns and len(plots_subplots) > 0:
    # Calculate center
    centroids = plots_subplots[plots_subplots.geometry.notna()].geometry.centroid

    if len(centroids) > 0:
        center_lat = centroids.y.mean()
        center_lon = centroids.x.mean()
    else:
        center_lat, center_lon = config.DEFAULT_MAP_CENTER

    # Create map with selected style
    tile_map = {
        "OpenStreetMap": "OpenStreetMap",
        "CartoDB Positron": "CartoDB positron",
        "CartoDB Dark_Matter": "CartoDB dark_matter",
    }

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles=tile_map.get(map_style, "OpenStreetMap"),
    )

    # Add fullscreen button
    folium.plugins.Fullscreen().add_to(m)

    # Track statistics
    valid_shown = 0
    invalid_shown = 0

    # Add subplots to map
    for idx, row in plots_subplots.iterrows():
        subplot_id = row.get("SUBPLOT_KEY")
        geom = row.get("geometry")

        if geom and not geom.is_empty and subplot_id:
            # Check validation status
            is_valid = True
            issues_text = "No issues"
            issue_count = 0

            if subplot_id in validation_results["subplots"]:
                validation = validation_results["subplots"][subplot_id]
                is_valid = validation["valid"]
                issue_count = len(validation["issues"])

                if not is_valid:
                    issues_list = [
                        f"• {issue['message']}" for issue in validation["issues"]
                    ]
                    issues_text = "<br>".join(issues_list[:5])  # Show first 5 issues
                    if len(validation["issues"]) > 5:
                        issues_text += f"<br><i>...and {len(validation['issues']) - 5} more issues</i>"

            # Skip based on filter
            if is_valid and not show_valid:
                continue
            if not is_valid and not show_invalid:
                continue

            # Count displayed subplots
            if is_valid:
                valid_shown += 1
            else:
                invalid_shown += 1

            # Determine color and icon
            color = (
                config.MARKER_COLORS["valid"]
                if is_valid
                else config.MARKER_COLORS["critical"]
            )
            status_icon = "✓" if is_valid else "✗"
            status_text = "Valid" if is_valid else "Invalid"

            # Create enhanced popup
            popup_html = f"""
            <div style="font-family: Arial, sans-serif; min-width: 280px; max-width: 350px;">
                <h3 style="margin: 0 0 10px 0; color: {color}; border-bottom: 2px solid {color}; padding-bottom: 5px;">
                    {status_icon} {subplot_id}
                </h3>
                <table style="width: 100%; font-size: 14px;">
                    <tr>
                        <td style="padding: 4px 0;"><b>Plot ID:</b></td>
                        <td style="padding: 4px 0;">{row.get('PLOT_KEY', 'Unknown')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><b>Enumerator:</b></td>
                        <td style="padding: 4px 0;">{row.get('enumerator', 'Unknown')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><b>Status:</b></td>
                        <td style="padding: 4px 0; color: {color}; font-weight: bold;">{status_text}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px 0;"><b>Issue Count:</b></td>
                        <td style="padding: 4px 0;">{issue_count}</td>
                    </tr>
                </table>
                <hr style="margin: 10px 0; border: none; border-top: 1px solid #ddd;">
                <div style="max-height: 150px; overflow-y: auto; font-size: 13px; line-height: 1.4;">
                    <b>Issues:</b><br>
                    {issues_text}
                </div>
            </div>
            """

            popup = folium.Popup(popup_html, max_width=400)

            # Add polygon to map with hover effect
            folium.GeoJson(
                geom.__geo_interface__,
                style_function=lambda x, c=color: {
                    "fillColor": c,
                    "color": c,
                    "weight": 2,
                    "fillOpacity": 0.35,
                    "opacity": 0.8,
                },
                highlight_function=lambda x: {
                    "fillOpacity": 0.65,
                    "weight": 4,
                },
                popup=popup,
                tooltip=(
                    f"<b>{subplot_id}</b><br>Click for details" if show_labels else None
                ),
            ).add_to(m)

    # Add layer control if needed
    folium.LayerControl().add_to(m)

    # Add refresh button
    if st.button("🔄 Refresh Map", use_container_width=False):
        st.rerun()

    # Display map
    st.subheader(
        f"📍 Displaying {valid_shown + invalid_shown} subplots ({valid_shown} valid, {invalid_shown} invalid)"
    )

    map_data = st_folium(m, width=None, height=650, returned_objects=[])

    st.markdown("---")

    # Legend
    st.subheader("📊 Legend")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            f"<div style='padding: 0.75rem; background-color: rgba(56, 142, 60, 0.15); border-left: 4px solid {config.MARKER_COLORS['valid']}; border-radius: 4px;'>"
            f"<b>🟢 Valid Subplots</b><br>"
            f"<small>No validation issues detected</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"<div style='padding: 0.75rem; background-color: rgba(245, 124, 0, 0.15); border-left: 4px solid {config.MARKER_COLORS['warning']}; border-radius: 4px;'>"
            f"<b>⚠️ Warnings</b><br>"
            f"<small>Minor issues requiring attention</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"<div style='padding: 0.75rem; background-color: rgba(211, 47, 47, 0.15); border-left: 4px solid {config.MARKER_COLORS['critical']}; border-radius: 4px;'>"
            f"<b>🔴 Invalid Subplots</b><br>"
            f"<small>Critical validation failures</small>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Download section
    st.subheader("📥 Export Map Data")

    col1, col2 = st.columns(2)

    with col1:
        # Filter data based on current view
        filtered_plots = plots_subplots.copy()

        if not show_valid:
            invalid_ids = [
                k for k, v in validation_results["subplots"].items() if not v["valid"]
            ]
            filtered_plots = filtered_plots[
                filtered_plots["SUBPLOT_KEY"].isin(invalid_ids)
            ]

        if not show_invalid:
            valid_ids = [
                k for k, v in validation_results["subplots"].items() if v["valid"]
            ]
            filtered_plots = filtered_plots[
                filtered_plots["SUBPLOT_KEY"].isin(valid_ids)
            ]

        # Create GeoJSON
        from utils.geometry_utils import to_geojson

        features = []
        for idx, row in filtered_plots.iterrows():
            if row.get("geometry") and not row.get("geometry").is_empty:
                subplot_id = row.get("SUBPLOT_KEY")
                is_valid = True
                issue_count = 0

                if subplot_id in validation_results["subplots"]:
                    validation = validation_results["subplots"][subplot_id]
                    is_valid = validation["valid"]
                    issue_count = len(validation["issues"])

                feature = to_geojson(
                    row.get("geometry"),
                    properties={
                        "subplot_id": subplot_id,
                        "plot_id": row.get("PLOT_KEY"),
                        "enumerator": row.get("enumerator"),
                        "status": "valid" if is_valid else "invalid",
                        "issue_count": issue_count,
                        "submission_date": (
                            str(row.get("SubmissionDate"))
                            if "SubmissionDate" in row
                            else None
                        ),
                    },
                )
                features.append(feature)

        geojson_data = {"type": "FeatureCollection", "features": features}
        geojson_clean = clean_for_json(geojson_data)

        st.download_button(
            label="🗺️ Download as GeoJSON",
            data=json.dumps(geojson_clean, indent=2),
            file_name=f"map_view_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
            mime="application/geo+json",
            use_container_width=True,
            help="Download visible subplots as GeoJSON for use in GIS applications",
        )

    with col2:
        # CSV export
        export_data = []
        for idx, row in filtered_plots.iterrows():
            subplot_id = row.get("SUBPLOT_KEY")
            if subplot_id in validation_results["subplots"]:
                validation = validation_results["subplots"][subplot_id]
                export_data.append(
                    {
                        "subplot_id": subplot_id,
                        "plot_id": row.get("PLOT_KEY"),
                        "enumerator": row.get("enumerator"),
                        "status": "valid" if validation["valid"] else "invalid",
                        "issue_count": len(validation["issues"]),
                        "submission_date": row.get("SubmissionDate"),
                    }
                )

        if export_data:
            df_export = pd.DataFrame(export_data)
            csv = df_export.to_csv(index=False)

            st.download_button(
                label="📄 Download as CSV",
                data=csv,
                file_name=f"map_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                help="Download subplot data as CSV",
            )

else:
    st.warning("⚠️ No geometry data available for mapping.")
    st.info(
        "💡 Geometry data is required to display the map. Please ensure your uploaded data contains valid geometry information."
    )
