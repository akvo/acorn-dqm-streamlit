"""
Map View Page - Enhanced (Folium Only)
Removed Plotly fallback as it causes hanging
"""

import streamlit as st
import pandas as pd
import config
from ui.components import show_header, create_sidebar_filters, show_sidebar_info
from utils.data_processor import get_validation_summary

# Import folium
try:
    import folium
    from streamlit_folium import folium_static
    from folium.plugins import Fullscreen, MiniMap

    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

# Page config
st.set_page_config(
    page_title="Map View - Ground Truth DQM",
    page_icon="🗺️",
    layout="wide",
)

# Refresh partner config from URL
config.refresh_partner_config()

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Check if folium available
if not FOLIUM_AVAILABLE:
    st.error("📦 **Folium not installed!**")
    st.markdown(
        """
    This map feature requires the Folium library.
    
    **To install:**
    ```bash
    pip install folium streamlit-folium
    ```
    
    Then restart the application.
    """
    )
    st.stop()

# Header
show_header()

st.markdown("## 🗺️ Interactive Map View")
st.caption("Visual geospatial validation of subplot boundaries. Green polygons are valid, red polygons have validation issues. Click any subplot to see details including area, vertices, enumerator, and specific validation errors.")

# Get data
gdf_subplots = st.session_state.data["subplots"]

# Sidebar filters
with st.sidebar:
    # Apply filters first (shows date filter at top)
    filtered_gdf = create_sidebar_filters(gdf_subplots)

    # Show common sidebar info (partner, data status)
    show_sidebar_info()

    st.markdown("## 🎨 Map Options")

    show_valid = st.checkbox("Show Valid Subplots", value=True)
    show_invalid = st.checkbox("Show Invalid Subplots", value=True)

    st.caption("💡 Use layer control on map to switch styles")

    st.markdown("---")

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
    avg_area = filtered_gdf["area_m2"].mean() if "area_m2" in filtered_gdf.columns else 0
    st.metric("Avg Area", f"{avg_area:.0f} m²")

st.markdown("---")

# ============================================
# PLOT SELECTION DROPDOWN
# ============================================

st.markdown("### 🎯 Plot Selection")
st.caption("Select a specific plot to zoom in and inspect its subplots in detail. Useful for investigating clusters of errors or verifying field team data collection patterns.")

# Get unique plot keys from the filtered data
if "PLOT_KEY" in filtered_gdf.columns:
    plot_keys = filtered_gdf["PLOT_KEY"].dropna().unique().tolist()
    plot_keys_sorted = sorted(plot_keys)

    # Create two columns for plot selection
    col_select1, col_select2 = st.columns([2, 1])

    with col_select1:
        # Create display options with subplot count
        plot_options = ["All Plots - Show entire dataset"]
        for pk in plot_keys_sorted:
            count = len(filtered_gdf[filtered_gdf["PLOT_KEY"] == pk])
            plot_options.append(f"{pk} ({count} subplots)")

        selected_plot_display = st.selectbox(
            "Select a plot to zoom into",
            options=plot_options,
            index=0,
            help="Select a specific plot to zoom into and highlight its subplots",
        )

    # Extract the actual plot key from selection
    if selected_plot_display != "All Plots - Show entire dataset":
        # Find the matching plot key
        selected_idx = plot_options.index(selected_plot_display) - 1  # -1 for "All Plots"
        selected_plot_key = plot_keys_sorted[selected_idx]
    else:
        selected_plot_key = None

    with col_select2:
        if selected_plot_key:
            st.info(
                f"📍 Showing **1** plot with **{len(filtered_gdf[filtered_gdf['PLOT_KEY'] == selected_plot_key])}** subplots"
            )
        else:
            st.info(f"📍 Showing **{len(plot_keys_sorted)}** plots")
else:
    selected_plot_key = None
    st.caption("No PLOT_KEY column available for plot selection")

st.markdown("---")

# Calculate map center based on selection
if selected_plot_key:
    # Zoom to selected plot
    plot_gdf = filtered_gdf[filtered_gdf["PLOT_KEY"] == selected_plot_key]
    bounds = plot_gdf.total_bounds
    # Use higher zoom for single plot
    zoom_level = 17
else:
    # Show all data
    bounds = filtered_gdf.total_bounds
    zoom_level = config.DEFAULT_ZOOM

center_lat = (bounds[1] + bounds[3]) / 2
center_lon = (bounds[0] + bounds[2]) / 2

# ============================================
# CREATE FOLIUM MAP
# ============================================

try:
    # Create map with Satellite as default (no base tiles, we add them manually)
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_level,
        tiles=None,
    )

    # Add tile layers - Satellite as default (show=True), OpenStreetMap as option
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        show=True,
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)

    # Create feature groups
    valid_group = folium.FeatureGroup(name="✅ Valid Subplots", show=show_valid)
    invalid_group = folium.FeatureGroup(name="❌ Invalid Subplots", show=show_invalid)

    # Count for progress
    total_to_plot = len(filtered_gdf)
    if total_to_plot > 1000:
        with st.spinner(f"📍 Loading {total_to_plot} subplots on map..."):
            pass

    # Add subplots to map
    for idx, row in filtered_gdf.iterrows():
        if row.geometry.is_empty:
            continue

        # Handle both Polygon and MultiPolygon geometries
        geom = row.geometry
        polygons_to_plot = []

        if geom.geom_type == "Polygon":
            polygons_to_plot = [geom]
        elif geom.geom_type == "MultiPolygon":
            polygons_to_plot = list(geom.geoms)
        else:
            # Skip other geometry types (Point, LineString, etc.)
            continue

        # Check if this subplot belongs to the selected plot
        is_selected_plot = selected_plot_key is not None and row.get("PLOT_KEY") == selected_plot_key

        # Create detailed popup
        plot_key_display = row.get("PLOT_KEY", "N/A")

        # Get submission date
        submission_date = row.get("SubmissionDate") or row.get("starttime") or row.get("date", "N/A")
        if pd.notna(submission_date) and submission_date != "N/A":
            try:
                submission_date = pd.to_datetime(submission_date).strftime("%Y-%m-%d")
            except:
                submission_date = str(submission_date)

        popup_html = f"""
        <div style="font-family: Arial, sans-serif; min-width: 250px; max-width: 300px;">
            <div style="background: {"#4CAF50" if row["geom_valid"] else "#F44336"};
                        color: white; padding: 8px; margin: -10px -10px 10px -10px;
                        border-radius: 3px 3px 0 0;">
                <h3 style="margin: 0; font-size: 16px;">
                    {"✅ VALID" if row["geom_valid"] else "❌ INVALID"}
                </h3>
            </div>

            <table style="width: 100%; font-size: 13px; border-collapse: collapse;">
                <tr style="background-color: #e3f2fd;">
                    <td style="padding: 4px; font-weight: bold; width: 40%;">Plot Key:</td>
                    <td style="padding: 4px; font-size: 11px; word-break: break-all;">{plot_key_display}</td>
                </tr>
                <tr>
                    <td style="padding: 4px; font-weight: bold; width: 40%;">Subplot ID:</td>
                    <td style="padding: 4px;">{row.get("subplot_id", "N/A")}</td>
                </tr>
                <tr style="background-color: #f5f5f5;">
                    <td style="padding: 4px; font-weight: bold;">Date:</td>
                    <td style="padding: 4px;">{submission_date}</td>
                </tr>
                <tr>
                    <td style="padding: 4px; font-weight: bold;">Area:</td>
                    <td style="padding: 4px;">{row.get("area_m2", 0):.1f} m²</td>
                </tr>
                <tr style="background-color: #f5f5f5;">
                    <td style="padding: 4px; font-weight: bold;">Vertices:</td>
                    <td style="padding: 4px;">{row.get("nr_vertices", 0)}</td>
                </tr>
                <tr>
                    <td style="padding: 4px; font-weight: bold;">Enumerator:</td>
                    <td style="padding: 4px;">{row.get("enumerator", "N/A")}</td>
                </tr>
        """

        # Add area status
        if "area_m2" in row.index and row.get("area_m2", 0) > 0:
            area = row["area_m2"]
            if area < config.MIN_SUBPLOT_AREA_SIZE:
                area_status = "<span style='color: red;'>⚠️ Too small</span>"
            elif area > config.MAX_SUBPLOT_AREA_SIZE:
                area_status = "<span style='color: red;'>⚠️ Too large</span>"
            else:
                area_status = "<span style='color: green;'>✓ Within range</span>"

            popup_html += f"""
                <tr>
                    <td style="padding: 4px; font-weight: bold;">Area Status:</td>
                    <td style="padding: 4px;">{area_status}</td>
                </tr>
            """

        # Add overlap information if present
        if "overlap_ids" in row.index and row.get("overlap_ids"):
            overlap_ids = str(row["overlap_ids"])
            if overlap_ids and overlap_ids != "nan":
                popup_html += f"""
                <tr style="background-color: #fff3e0;">
                    <td style="padding: 4px; font-weight: bold;">Overlaps With:</td>
                    <td style="padding: 4px; color: #e65100; font-size: 11px;">{overlap_ids}</td>
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

        # Create tooltip with plot key info
        plot_short = str(row.get("PLOT_KEY", ""))[-12:] if row.get("PLOT_KEY") else "N/A"
        tooltip_text = f"Plot: ...{plot_short} | Subplot: {row.get('subplot_id', 'N/A')}"
        if "area_m2" in row.index:
            tooltip_text += f" • {row.get('area_m2', 0):.0f}m²"
        if not row["geom_valid"]:
            tooltip_text = "❌ " + tooltip_text
        else:
            tooltip_text = "✅ " + tooltip_text

        # Add each polygon (handles both Polygon and MultiPolygon)
        for poly in polygons_to_plot:
            # Get coordinates for this polygon
            coords = list(poly.exterior.coords)
            coords_latlon = [(lat, lon) for lon, lat in coords]

            # Add polygon to map
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
    Fullscreen(position="topleft").add_to(m)

    # Add minimap
    MiniMap(toggle_display=True, position="bottomleft").add_to(m)

    # Add statistics box
    stats_html = f"""
    <div style="position: fixed; 
                bottom: 10px; right: 10px; 
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
            <b style="color: #4CAF50;">✅ Valid:</b> {summary["valid"]}<br>
            <b style="color: #F44336;">❌ Invalid:</b> {summary["invalid"]}<br>
            <b>📈 Valid %:</b> {summary["valid_pct"]:.1f}%
        </div>
    </div>
    """

    m.get_root().html.add_child(folium.Element(stats_html))

    # Display map
    st.info(
        "💡 **Tip:** Click on subplots to see detailed information. "
        "Use the layer control (top-right) to toggle between valid/invalid and change map styles."
    )

    folium_static(m, width=1200, height=700)

    # Show subplot table for selected plot (below map)
    if selected_plot_key and len(plot_gdf) > 0 and "nr_vertices" in plot_gdf.columns:
        st.markdown("#### Subplots in Selected Plot")
        st.caption("GPS points per subplot. Standard plots should have 4 vertices (quadrilateral). More or fewer vertices may indicate GPS collection issues or complex boundary shapes.")

        # Extract subplot number from subplot_id
        import re
        table_data = plot_gdf[["subplot_id", "nr_vertices"]].copy()
        table_data["Subplot #"] = table_data["subplot_id"].apply(
            lambda x: re.search(r"\[(\d+)\]", str(x)).group(1)
            if re.search(r"\[(\d+)\]", str(x)) else "?"
        )

        # Display table
        display_df = table_data[["Subplot #", "nr_vertices"]].rename(
            columns={"nr_vertices": "GPS Points"}
        ).sort_values("Subplot #", key=lambda x: x.astype(int))
        st.dataframe(display_df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"⚠️ **Map failed to load:** {str(e)}")
    st.markdown(
        """
    **Possible solutions:**
    
    1. **Refresh the page** (Ctrl+R or Cmd+R)
    2. **Check your internet connection** (map tiles load from CDN)
    3. **Try a different map style** from the sidebar
    4. **If on a server**, ensure firewall allows:
       - Access to unpkg.com
       - Access to cdnjs.com
       - Access to tile servers
    
    **Alternative:** Export the data as GeoJSON and view in QGIS or other GIS software.
    """
    )

    # Still show export options even if map fails
    st.markdown("---")
    st.markdown("### 📥 Export Data (Map not required)")

# Legend and summary below map
st.markdown("---")

# ============================================
# TREE COUNT MAP
# ============================================

st.markdown("## 🌳 Tree Count Map")
st.caption("Visualizes tree density per subplot using a green color gradient (darker = more trees, grey = no trees). Filter by vegetation type to see distribution of specific species categories. Use this to identify under-planted subplots or verify expected planting patterns.")

# Get vegetation data
raw_data = st.session_state.data.get("raw_data", {})
veg_df = raw_data.get("plots_subplots_vegetation")

if veg_df is not None and len(veg_df) > 0:
    # Get unique vegetation types
    veg_types = ["All"]
    if "vegetation_species_type" in veg_df.columns:
        unique_types = veg_df["vegetation_species_type"].dropna().unique().tolist()
        # Clean and sort
        unique_types = sorted([str(t).strip() for t in unique_types if str(t).strip() and str(t).lower() != "nan"])
        veg_types.extend(unique_types)

    # Vegetation type filter and plot selector
    col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 2])
    with col_filter1:
        selected_veg_type = st.selectbox(
            "Filter by Vegetation Type", options=veg_types, index=0, key="tree_count_veg_filter"
        )

    # Filter vegetation data by type
    if selected_veg_type == "All":
        filtered_veg = veg_df.copy()
    else:
        filtered_veg = veg_df[veg_df["vegetation_species_type"] == selected_veg_type].copy()

    # Plot selector for tree count map - filtered by vegetation type
    with col_filter2:
        tree_map_plot_keys = ["All Plots"]
        if "SUBPLOT_KEY" in filtered_veg.columns and "PLOT_KEY" in filtered_gdf.columns:
            # Get plots that have subplots with the selected vegetation type
            veg_subplot_keys = filtered_veg["SUBPLOT_KEY"].dropna().unique().tolist()
            # Extract PLOT_KEY from SUBPLOT_KEY (format: uuid:xxx/sub_plot[n])
            veg_plot_keys = set()
            for sk in veg_subplot_keys:
                if "/" in str(sk):
                    plot_key = str(sk).split("/")[0]
                    veg_plot_keys.add(plot_key)

            # Filter to only plots that exist in our geometry data
            available_plot_keys = set(filtered_gdf["PLOT_KEY"].dropna().unique().tolist())
            filtered_plot_keys = sorted(veg_plot_keys.intersection(available_plot_keys))
            tree_map_plot_keys.extend(filtered_plot_keys)
        elif "PLOT_KEY" in filtered_gdf.columns:
            # Fallback to all plots if we can't filter
            plot_keys_list = sorted(filtered_gdf["PLOT_KEY"].dropna().unique().tolist())
            tree_map_plot_keys.extend(plot_keys_list)

        selected_tree_map_plot = st.selectbox(
            f"Zoom to Plot ({len(tree_map_plot_keys) - 1} plots with {selected_veg_type})",
            options=tree_map_plot_keys,
            index=0,
            key="tree_count_plot_filter",
        )

    # Calculate tree count per subplot
    if "SUBPLOT_KEY" in filtered_veg.columns and "vegetation_type_number" in filtered_veg.columns:
        # Sum tree counts per subplot
        tree_counts = (
            filtered_veg.groupby("SUBPLOT_KEY")["vegetation_type_number"]
            .sum()
            .reset_index()
            .rename(columns={"vegetation_type_number": "tree_count"})
        )

        # Merge with subplot geometry
        tree_count_gdf = filtered_gdf.copy()

        # Create SUBPLOT_KEY from subplot_id if not present
        if "SUBPLOT_KEY" not in tree_count_gdf.columns and "subplot_id" in tree_count_gdf.columns:
            # subplot_id format: subplots[0]-gt_subplot_gps -> need to match with SUBPLOT_KEY
            # SUBPLOT_KEY format: uuid:xxx/sub_plot[0]
            if "PLOT_KEY" in tree_count_gdf.columns:
                tree_count_gdf["SUBPLOT_KEY"] = tree_count_gdf.apply(
                    lambda row: f"{row['PLOT_KEY']}/sub_plot[{row['subplot_id'].split('[')[1].split(']')[0] if '[' in str(row['subplot_id']) else '0'}]"
                    if pd.notna(row.get("subplot_id")) and pd.notna(row.get("PLOT_KEY"))
                    else None,
                    axis=1,
                )

        # Merge tree counts
        if "SUBPLOT_KEY" in tree_count_gdf.columns:
            tree_count_gdf = tree_count_gdf.merge(tree_counts, on="SUBPLOT_KEY", how="left")
            tree_count_gdf["tree_count"] = tree_count_gdf["tree_count"].fillna(0).astype(int)
        else:
            tree_count_gdf["tree_count"] = 0

        # Show stats
        with col_filter3:
            total_trees = int(tree_count_gdf["tree_count"].sum())
            subplots_with_trees = int((tree_count_gdf["tree_count"] > 0).sum())
            st.metric(f"Total Trees ({selected_veg_type})", f"{total_trees:,}")

        # Define color scale based on tree count
        def get_tree_count_color(count):
            """Return color based on tree count (green gradient)"""
            if count == 0:
                return "#E0E0E0"  # Grey for no trees
            elif count <= 5:
                return "#C8E6C9"  # Light green
            elif count <= 10:
                return "#A5D6A7"  #
            elif count <= 20:
                return "#81C784"  #
            elif count <= 50:
                return "#66BB6A"  #
            elif count <= 100:
                return "#4CAF50"  #
            elif count <= 200:
                return "#43A047"  #
            else:
                return "#2E7D32"  # Dark green for 200+

        # Create tree count map
        try:
            # Calculate center based on selected plot
            if selected_tree_map_plot != "All Plots" and "PLOT_KEY" in tree_count_gdf.columns:
                plot_gdf = tree_count_gdf[tree_count_gdf["PLOT_KEY"] == selected_tree_map_plot]
                non_empty = plot_gdf[~plot_gdf.geometry.is_empty]
                tree_map_zoom = 17  # Zoom in close for single plot
            else:
                non_empty = tree_count_gdf[~tree_count_gdf.geometry.is_empty]
                tree_map_zoom = zoom_level

            if len(non_empty) > 0:
                bounds = non_empty.total_bounds
                center_lat = (bounds[1] + bounds[3]) / 2
                center_lon = (bounds[0] + bounds[2]) / 2
            else:
                center_lat, center_lon = config.MAP_CENTER
                tree_map_zoom = config.DEFAULT_ZOOM

            # Create map with Satellite as default
            m2 = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=tree_map_zoom,
                tiles=None,
            )

            # Add tile layers - Satellite as default (show=True), OpenStreetMap as option
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Satellite",
                show=True,
            ).add_to(m2)
            folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m2)

            # Add subplots colored by tree count
            for idx, row in tree_count_gdf.iterrows():
                if row.geometry.is_empty:
                    continue

                geom = row.geometry
                polygons_to_plot = []

                if geom.geom_type == "Polygon":
                    polygons_to_plot = [geom]
                elif geom.geom_type == "MultiPolygon":
                    polygons_to_plot = list(geom.geoms)
                else:
                    continue

                tree_count = int(row.get("tree_count", 0))
                color = get_tree_count_color(tree_count)

                # Get submission date for tree count map
                tree_submission_date = row.get("SubmissionDate") or row.get("starttime") or row.get("date", "N/A")
                if pd.notna(tree_submission_date) and tree_submission_date != "N/A":
                    try:
                        tree_submission_date = pd.to_datetime(tree_submission_date).strftime("%Y-%m-%d")
                    except:
                        tree_submission_date = str(tree_submission_date)

                # Create popup
                popup_html = f"""
                <div style="font-family: Arial; min-width: 200px;">
                    <h4 style="margin: 0 0 10px 0; color: #2E7D32;">🌳 Tree Count: {tree_count}</h4>
                    <table style="width: 100%; font-size: 12px;">
                        <tr><td><b>Plot:</b></td><td style="font-size: 10px;">{row.get("PLOT_KEY", "N/A")}</td></tr>
                        <tr><td><b>Subplot:</b></td><td>{row.get("subplot_id", "N/A")}</td></tr>
                        <tr><td><b>Date:</b></td><td>{tree_submission_date}</td></tr>
                        <tr><td><b>Vegetation Type:</b></td><td>{selected_veg_type}</td></tr>
                        <tr><td><b>Enumerator:</b></td><td>{row.get("enumerator", "N/A")}</td></tr>
                    </table>
                </div>
                """

                tooltip_text = f"Trees: {tree_count} | {row.get('subplot_id', 'N/A')} | {tree_submission_date}"

                for polygon in polygons_to_plot:
                    coords = list(polygon.exterior.coords)
                    coords_latlon = [[lat, lon] for lon, lat in coords]

                    folium.Polygon(
                        locations=coords_latlon,
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=tooltip_text,
                        color="#000000",
                        fill=True,
                        fillColor=color,
                        fillOpacity=0.8,
                        weight=3,
                        opacity=1.0,
                    ).add_to(m2)

            # Add layer control and plugins
            folium.LayerControl(position="topright").add_to(m2)
            Fullscreen(position="topleft").add_to(m2)
            MiniMap(toggle_display=True, position="bottomleft").add_to(m2)

            # Add legend
            legend_html = """
            <div style="position: fixed;
                        bottom: 50px; right: 10px;
                        width: 150px;
                        background-color: white;
                        border: 2px solid #2E7D32;
                        border-radius: 8px;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                        z-index: 1000;
                        padding: 10px;
                        font-family: Arial, sans-serif;
                        font-size: 11px;">
                <h4 style="margin: 0 0 8px 0; color: #2E7D32;">🌳 Tree Count</h4>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <span style="background: #E0E0E0; width: 20px; height: 12px; display: inline-block; margin-right: 5px; border: 1px solid #999;"></span> 0
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <span style="background: #C8E6C9; width: 20px; height: 12px; display: inline-block; margin-right: 5px; border: 1px solid #999;"></span> 1-5
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <span style="background: #81C784; width: 20px; height: 12px; display: inline-block; margin-right: 5px; border: 1px solid #999;"></span> 6-20
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <span style="background: #4CAF50; width: 20px; height: 12px; display: inline-block; margin-right: 5px; border: 1px solid #999;"></span> 21-100
                </div>
                <div style="display: flex; align-items: center; margin: 3px 0;">
                    <span style="background: #2E7D32; width: 20px; height: 12px; display: inline-block; margin-right: 5px; border: 1px solid #999;"></span> 100+
                </div>
            </div>
            """
            m2.get_root().html.add_child(folium.Element(legend_html))

            # Display map
            st.info(
                f"💡 Showing tree counts for **{selected_veg_type}** vegetation type. Click subplots to see details."
            )
            folium_static(m2, width=1200, height=600)

        except Exception as e:
            st.error(f"⚠️ Tree count map failed to load: {str(e)}")

    else:
        st.warning("⚠️ Required columns (SUBPLOT_KEY, vegetation_type_number) not found in vegetation data")
else:
    st.info("ℹ️ No vegetation data available for tree count map")

# Download visible subplots
st.markdown("---")
st.markdown("### 📥 Export Map Data")
st.caption("Download the currently filtered data for use in GIS software (QGIS, ArcGIS) or spreadsheets. GeoJSON preserves geometry for mapping. CSV is for tabular analysis. 'Errors Only' exports just invalid subplots for targeted field revisits.")

col1, col2, col3 = st.columns(3)

# GeoJSON Export (Full data)
with col1:
    st.markdown("##### 🗺️ GeoJSON Export")
    st.caption("Geographic data format")

    export_gdf = filtered_gdf.copy()

    # Convert datetime columns to strings
    for col in export_gdf.columns:
        if pd.api.types.is_datetime64_any_dtype(export_gdf[col]):
            export_gdf[col] = export_gdf[col].astype(str)

    geojson_data = export_gdf.to_json()

    st.download_button(
        label="🗺️ Download GeoJSON",
        data=geojson_data,
        file_name=f"{config.PARTNER}_map_subplots.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )

# CSV Export
with col2:
    st.markdown("##### 📊 CSV Export")
    st.caption("Spreadsheet format")

    try:
        from utils.export_helpers import create_csv_export

        csv_data = create_csv_export(filtered_gdf, valid_only=False)
    except ImportError:
        # Fallback if export_helpers not available
        csv_df = filtered_gdf.drop(columns=["geometry"], errors="ignore")
        csv_data = csv_df.to_csv(index=False)

    st.download_button(
        label="📊 Download CSV",
        data=csv_data,
        file_name=f"{config.PARTNER}_map_subplots.csv",
        mime="text/csv",
        use_container_width=True,
    )

# Errors Only GeoJSON
with col3:
    st.markdown("##### ⚠️ Errors Only")
    st.caption("Invalid subplots GeoJSON")

    invalid_gdf = filtered_gdf[~filtered_gdf["geom_valid"]].copy()

    if len(invalid_gdf) > 0:
        # Convert datetime columns
        for col in invalid_gdf.columns:
            if pd.api.types.is_datetime64_any_dtype(invalid_gdf[col]):
                invalid_gdf[col] = invalid_gdf[col].astype(str)

        invalid_geojson = invalid_gdf.to_json()

        st.download_button(
            label="🗺️ Download Errors GeoJSON",
            data=invalid_geojson,
            file_name=f"{config.PARTNER}_map_errors.geojson",
            mime="application/geo+json",
            use_container_width=True,
        )
    else:
        st.success("✅ No errors to export!")

# Additional info
st.markdown("---")
st.markdown("### 💡 Tips")

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
    **Using the Map:**
    - Click polygons to see full details
    - Use layer control (top-right) to toggle layers
    - Switch map styles instantly with layer control
    - Go fullscreen for better view
    - Use minimap to navigate large areas
    """
    )

with col2:
    st.markdown(
        """
    **Exporting Data:**
    - GeoJSON: Load in QGIS, ArcGIS, or web maps
    - CSV: Open in Excel or analysis tools
    - Errors only: Focus on problems for field teams
    - All exports respect current filters
    """
    )
