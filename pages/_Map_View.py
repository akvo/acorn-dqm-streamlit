"""
Map View Page - Enhanced
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import config
from ui.components import show_header, create_sidebar_filters
from utils.data_processor import get_validation_summary
import pandas as pd

# Page config
st.set_page_config(
    page_title="Map View - " + config.APP_TITLE,
    page_icon="🗺️",
    layout="wide",
)

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Header
show_header()

st.markdown("## 🗺️ Interactive Map View")

# Get data
gdf_subplots = st.session_state.data["subplots"]

# Sidebar filters
with st.sidebar:
    st.markdown("## 🎨 Map Options")

    show_valid = st.checkbox("Show Valid Subplots", value=True)
    show_invalid = st.checkbox("Show Invalid Subplots", value=True)

    st.markdown("---")
    st.markdown("### 🗺️ Map Style")

    map_style = st.radio(
        "Choose map style:",
        options=[
            "OpenStreetMap",
            "Satellite (Esri)",
            "Terrain",
            "Light (CartoDB)",
        ],
        index=0,
    )

    st.markdown("---")

filtered_gdf = create_sidebar_filters(gdf_subplots)

# Filter by validity
if not show_valid:
    filtered_gdf = filtered_gdf[~filtered_gdf["geom_valid"]]
if not show_invalid:
    filtered_gdf = filtered_gdf[filtered_gdf["geom_valid"]]

# Remove empty geometries
filtered_gdf = filtered_gdf[~filtered_gdf.geometry.is_empty]

if len(filtered_gdf) == 0:
    st.warning("No data to display with current filters")
    st.stop()

# Quick stats before map
summary = get_validation_summary(filtered_gdf)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Showing", f"{len(filtered_gdf):,}")
with col2:
    st.metric("Valid", f"{summary['valid']:,}", f"{summary['valid_pct']:.1f}%")
with col3:
    st.metric("Invalid", f"{summary['invalid']:,}")
with col4:
    avg_area = (
        filtered_gdf["area_m2"].mean() if "area_m2" in filtered_gdf.columns else 0
    )
    st.metric("Avg Area", f"{avg_area:.0f} m²")

st.markdown("---")

# Calculate map center
bounds = filtered_gdf.total_bounds
center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2

# Create map with selected style
if map_style == "OpenStreetMap":
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=config.DEFAULT_ZOOM,
        tiles="OpenStreetMap",
    )
elif map_style == "Satellite (Esri)":
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=config.DEFAULT_ZOOM,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
    )
elif map_style == "Terrain":
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=config.DEFAULT_ZOOM,
        tiles="Stamen Terrain",
    )
else:  # Light (CartoDB)
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=config.DEFAULT_ZOOM,
        tiles="CartoDB positron",
    )

# Add additional tile layer options
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite",
).add_to(m)
folium.TileLayer("CartoDB positron", name="Light").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)

# Create feature groups
valid_group = folium.FeatureGroup(name="✅ Valid Subplots", show=show_valid)
invalid_group = folium.FeatureGroup(name="❌ Invalid Subplots", show=show_invalid)

# Count for progress
total_to_plot = len(filtered_gdf)
if total_to_plot > 1000:
    st.info(f"📍 Plotting {total_to_plot} subplots... This may take a moment.")

# Add subplots to map
for idx, row in filtered_gdf.iterrows():
    if row.geometry.is_empty:
        continue

    # Get coordinates
    coords = list(row.geometry.exterior.coords)
    coords_latlon = [(lat, lon) for lon, lat in coords]

    # Create detailed popup
    popup_html = f"""
    <div style="font-family: Arial, sans-serif; min-width: 250px; max-width: 300px;">
        <div style="background: {'#4CAF50' if row['geom_valid'] else '#F44336'}; 
                    color: white; padding: 8px; margin: -10px -10px 10px -10px; 
                    border-radius: 3px 3px 0 0;">
            <h3 style="margin: 0; font-size: 16px;">
                {'✅ VALID' if row['geom_valid'] else '❌ INVALID'}
            </h3>
        </div>
        
        <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
            <tr>
                <td style="padding: 4px; font-weight: bold; width: 40%;">Subplot ID:</td>
                <td style="padding: 4px;">{row.get('subplot_id', 'N/A')}</td>
            </tr>
            <tr style="background-color: #f5f5f5;">
                <td style="padding: 4px; font-weight: bold;">Area:</td>
                <td style="padding: 4px;">{row.get('area_m2', 0):.1f} m²</td>
            </tr>
            <tr>
                <td style="padding: 4px; font-weight: bold;">Vertices:</td>
                <td style="padding: 4px;">{row.get('nr_vertices', 0)}</td>
            </tr>
            <tr style="background-color: #f5f5f5;">
                <td style="padding: 4px; font-weight: bold;">Enumerator:</td>
                <td style="padding: 4px;">{row.get('enumerator', 'N/A')}</td>
            </tr>
    """

    # Add area status
    if "area_m2" in row.index and row.get("area_m2", 0) > 0:
        area = row["area_m2"]
        if area < config.MIN_SUBPLOT_AREA_SIZE:
            area_status = f"<span style='color: red;'>⚠️ Too small</span>"
        elif area > config.MAX_SUBPLOT_AREA_SIZE:
            area_status = f"<span style='color: red;'>⚠️ Too large</span>"
        else:
            area_status = f"<span style='color: green;'>✓ Within range</span>"

        popup_html += f"""
            <tr>
                <td style="padding: 4px; font-weight: bold;">Area Status:</td>
                <td style="padding: 4px;">{area_status}</td>
            </tr>
        """

    popup_html += "</table>"

    # Add validation issues if invalid
    if not row["geom_valid"] and "reasons" in row.index:
        reasons = str(row["reasons"]).split(";")
        popup_html += """
        <div style="margin-top: 10px; padding: 8px; background-color: #ffebee; 
                    border-left: 3px solid #f44336; border-radius: 3px;">
            <b style="color: #c62828;">Validation Issues:</b>
            <ul style="margin: 5px 0; padding-left: 20px; font-size: 12px;">
        """
        for reason in reasons:
            if reason.strip():
                popup_html += f"<li>{reason.strip()}</li>"
        popup_html += "</ul></div>"

    popup_html += "</div>"

    # Choose styling based on validity
    if row["geom_valid"]:
        color = "#4CAF50"  # Green
        fill_color = "#81C784"  # Light green
        group = valid_group
        weight = 2
        opacity = 0.8
        fill_opacity = 0.3
    else:
        color = "#F44336"  # Red
        fill_color = "#E57373"  # Light red
        group = invalid_group
        weight = 2.5
        opacity = 1
        fill_opacity = 0.4

    # Create tooltip
    tooltip_text = f"{row.get('subplot_id', 'N/A')}"
    if "area_m2" in row.index:
        tooltip_text += f" • {row.get('area_m2', 0):.0f}m²"
    if not row["geom_valid"]:
        tooltip_text = "❌ " + tooltip_text
    else:
        tooltip_text = "✅ " + tooltip_text

    # Add polygon
    folium.Polygon(
        locations=coords_latlon,
        popup=folium.Popup(popup_html, max_width=350),
        tooltip=tooltip_text,
        color=color,
        fill=True,
        fillColor=fill_color,
        fillOpacity=fill_opacity,
        weight=weight,
        opacity=opacity,
    ).add_to(group)

# Add groups to map
valid_group.add_to(m)
invalid_group.add_to(m)

# Add layer control
folium.LayerControl(position="topright").add_to(m)

# Add fullscreen option
from folium.plugins import Fullscreen

Fullscreen(position="topleft").add_to(m)

# Add minimap
from folium.plugins import MiniMap

MiniMap(toggle_display=True, position="bottomleft").add_to(m)

# Add statistics box
stats_html = f"""
<div style="position: fixed; 
            top: 10px; right: 10px; 
            width: 200px; 
            background-color: white; 
            border: 2px solid #2E7D32; 
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.3);
            z-index: 1000; 
            padding: 15px;
            font-family: Arial, sans-serif;">
    <h4 style="margin: 0 0 10px 0; color: #2E7D32; border-bottom: 2px solid #2E7D32; padding-bottom: 5px;">
        📊 Statistics
    </h4>
    <div style="font-size: 14px; line-height: 1.8;">
        <b>Total Shown:</b> {len(filtered_gdf)}<br>
        <b style="color: #4CAF50;">✅ Valid:</b> {summary['valid']}<br>
        <b style="color: #F44336;">❌ Invalid:</b> {summary['invalid']}<br>
        <b>📍 Valid %:</b> {summary['valid_pct']:.1f}%
    </div>
</div>
"""

m.get_root().html.add_child(folium.Element(stats_html))

# Display map
st.info(
    "💡 **Tip:** Click on subplots to see detailed information. Use the layer control (top-right) to toggle between valid/invalid and change map styles."
)
st_folium(m, width=None, height=700, returned_objects=[])

# Legend and summary below map
st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📋 Map Legend")
    st.markdown("🟢 **Green** = Valid subplots")
    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Count: **{summary['valid']:,}**")
    st.markdown("")
    st.markdown("🔴 **Red** = Invalid subplots")
    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;Count: **{summary['invalid']:,}**")

with col2:
    st.markdown("### 📐 Area Range")
    st.markdown(f"**Min Required:** {config.MIN_SUBPLOT_AREA_SIZE} m²")
    st.markdown(f"**Max Allowed:** {config.MAX_SUBPLOT_AREA_SIZE} m²")
    if "area_m2" in filtered_gdf.columns:
        valid_areas = filtered_gdf[filtered_gdf["geom_valid"]]["area_m2"]
        if len(valid_areas) > 0:
            st.markdown(f"**Avg (Valid):** {valid_areas.mean():.1f} m²")

with col3:
    st.markdown("### 🗺️ Map Controls")
    st.markdown("**🔍** Zoom in/out")
    st.markdown("**🔲** Fullscreen (top-left)")
    st.markdown("**🗺️** Mini map (bottom-left)")
    st.markdown("**📑** Layer control (top-right)")

# Download visible subplots
st.markdown("---")
st.markdown("### 📥 Export Map Data")

col1, col2 = st.columns(2)

with col1:
    export_gdf = filtered_gdf.copy()

    for col in export_gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(export_gdf[col]):
            export_gdf[col] = export_gdf[col].astype(str)

    geojson_data = export_gdf.to_json()

    st.download_button(
        label="📄 Download Visible Subplots (GeoJSON)",
        data=geojson_data,
        file_name=f"{config.PARTNER}_map_subplots.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )

with col2:
    from utils.export_helpers import create_csv_export

    csv_data = create_csv_export(filtered_gdf, valid_only=False)
    st.download_button(
        label="📊 Download Visible Subplots (CSV)",
        data=csv_data,
        file_name=f"{config.PARTNER}_map_subplots.csv",
        mime="text/csv",
        use_container_width=True,
    )
