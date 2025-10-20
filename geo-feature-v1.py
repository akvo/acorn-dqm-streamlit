import streamlit as st
import pandas as pd
from pathlib import Path
import tempfile
import os
import shutil
import folium
from folium import plugins
from streamlit_folium import folium_static
import geopandas as gpd
import json
import logging
from datetime import datetime
from excel_parser import ExcelParser
from gt_check_functions import (
    add_ecoregion, calculate_area, collect_reasons_subplot, collect_reasons_plot,
    export_plots, export_subplots, fix_geometry, to_geojson, validate_country,
    validate_duplicate_id, validate_length_width_ratio, validate_nr_vertices,
    validate_overlap, validate_protruding_ratio, validate_within_radius, geom_to_utm,
    calculate_minimum_rotated_rectangle
)
from gt_config import (
    COUNTRY, CROP, MAX_GT_PLOT_AREA_SIZE, MAX_SUBPLOT_AREA_SIZE,
    MIN_GT_PLOT_AREA_SIZE, MIN_SUBPLOT_AREA_SIZE, PARTNER, YEAR
)
import plotly.express as px



# Initialize session state
if 'selected_plot_id' not in st.session_state:
    st.session_state.selected_plot_id = None
if 'selected_subplot_id' not in st.session_state:
    st.session_state.selected_subplot_id = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1
if 'plots_per_page' not in st.session_state:
    st.session_state.plots_per_page = 10
if 'selected_enumerator' not in st.session_state:
    st.session_state.selected_enumerator = "All Enumerators"
if 'selected_plot_option' not in st.session_state:
    st.session_state.selected_plot_option = "None"
if 'selected_subplot_option' not in st.session_state:
    st.session_state.selected_subplot_option = "None"
if 'processed_data' not in st.session_state:
    st.session_state.processed_data = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def clean_enumerator_name(enumerator_str):
    """Clean up enumerator name by removing ID if present"""
    if pd.isna(enumerator_str):
        return "Unknown"
    if "(" in enumerator_str and ")" in enumerator_str:
        return enumerator_str.split("(")[0].strip()
    return enumerator_str

def paginate_dataframe(df, page, per_page):
    """Return a paginated slice of the dataframe"""
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    return df.iloc[start_idx:end_idx]

def create_pagination_controls(total_items, current_page, per_page):
    """Create pagination controls"""
    total_pages = (total_items + per_page - 1) // per_page
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.write(f"Page {current_page} of {total_pages}")
        cols = st.columns(5)
        
        # Previous page button
        if cols[0].button("←", disabled=current_page == 1):
            st.session_state.current_page = max(1, current_page - 1)
            st.rerun()
        
        # Page number buttons
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, start_page + 4)
        
        for i, page_num in enumerate(range(start_page, end_page + 1), 1):
            if cols[i].button(str(page_num), disabled=page_num == current_page):
                st.session_state.current_page = page_num
                st.rerun()
        
        # Next page button
        if cols[4].button("→", disabled=current_page == total_pages):
            st.session_state.current_page = min(total_pages, current_page + 1)
            st.rerun()

st.set_page_config(page_title="Ground Truth Validation Tool", layout="wide")

st.title("Ground Truth Validation Tool")
st.write("Upload your Excel files to validate ground truth data")

def create_map(df_subplots, df_plots, df_selected_plots, selected_plot_id=None):
    """Create an interactive map with layers for valid and invalid plots/subplots"""
    # Create a base map centered on the data
    if selected_plot_id:
        # If a plot is selected, center on that plot
        if selected_plot_id in df_plots['plot_id'].values:
            plot_data = df_plots[df_plots['plot_id'] == selected_plot_id]
            if not plot_data.empty:
                try:
                    # Get the geometry and calculate centroid
                    geom = plot_data.geometry.iloc[0]
                    if geom is not None and not geom.is_empty:
                        centroid = geom.centroid
                        center_lat = centroid.y
                        center_lon = centroid.x
                        
                        zoom_start = 16  # Zoom level for individual plot view
                    else:

                        center_lat = 0.0
                        center_lon = 0.0
                        zoom_start = 14
                except Exception as e:

                    center_lat = 0.0
                    center_lon = 0.0
                    zoom_start = 14
            else:
                # Fallback to default center if plot data is empty

                center_lat = 0.0
                center_lon = 0.0
                zoom_start = 14
        elif selected_plot_id in df_selected_plots['plot_id'].values:
            # If a selected plot is selected, center on that plot
            selected_plot_data = df_selected_plots[df_selected_plots['plot_id'] == selected_plot_id]
            if not selected_plot_data.empty:
                try:
                    # Get the geometry and calculate centroid
                    geom = selected_plot_data.geometry.iloc[0]
                    if geom is not None and not geom.is_empty:
                        centroid = geom.centroid
                        center_lat = centroid.y
                        center_lon = centroid.x

                        zoom_start = 16  # Zoom level for individual selected plot view
                    else:

                        center_lat = 0.0
                        center_lon = 0.0
                        zoom_start = 14
                except Exception as e:
                    
                    center_lat = 0.0
                    center_lon = 0.0
                    zoom_start = 14
            else:
                # Fallback to default center if selected plot data is empty
                
                center_lat = 0.0
                center_lon = 0.0
                zoom_start = 14
        else:
            # If a subplot is selected, don't center on it - just use default view
            
            # Use default view - center on all data
            # Check if we have valid geometry data in either DataFrame
            valid_plots = df_plots[~df_plots.geometry.isna() & ~df_plots.geometry.is_empty] if not df_plots.empty else df_plots
            valid_selected_plots = df_selected_plots[~df_selected_plots.geometry.isna() & ~df_selected_plots.geometry.is_empty] if not df_selected_plots.empty else df_selected_plots
            valid_subplots = df_subplots[~df_subplots.geometry.isna() & ~df_subplots.geometry.is_empty] if not df_subplots.empty else df_subplots
            
            if not valid_plots.empty:
                center_lat = valid_plots.geometry.centroid.y.mean()
                center_lon = valid_plots.geometry.centroid.x.mean()
                zoom_start = 14
            elif not valid_selected_plots.empty:
                center_lat = valid_selected_plots.geometry.centroid.y.mean()
                center_lon = valid_selected_plots.geometry.centroid.x.mean()
                zoom_start = 14
            elif not valid_subplots.empty:
                center_lat = valid_subplots.geometry.centroid.y.mean()
                center_lon = valid_subplots.geometry.centroid.x.mean()
                zoom_start = 14
            else:
                # Fallback to a reasonable default location (you can change this to your study area)
                center_lat = 0.0
                center_lon = 0.0
                zoom_start = 2  # Very zoomed out to show the world
    else:
        # Default view - center on all data
        # Check if we have valid geometry data in either DataFrame
        valid_plots = df_plots[~df_plots.geometry.isna() & ~df_plots.geometry.is_empty] if not df_plots.empty else df_plots
        valid_selected_plots = df_selected_plots[~df_selected_plots.geometry.isna() & ~df_selected_plots.geometry.is_empty] if not df_selected_plots.empty else df_selected_plots
        valid_subplots = df_subplots[~df_subplots.geometry.isna() & ~df_subplots.geometry.is_empty] if not df_subplots.empty else df_subplots
        
        if not valid_plots.empty:
            center_lat = valid_plots.geometry.centroid.y.mean()
            center_lon = valid_plots.geometry.centroid.x.mean()
            zoom_start = 14
        elif not valid_selected_plots.empty:
            center_lat = valid_selected_plots.geometry.centroid.y.mean()
            center_lon = valid_selected_plots.geometry.centroid.x.mean()
            zoom_start = 14
        elif not valid_subplots.empty:
            center_lat = valid_subplots.geometry.centroid.y.mean()
            center_lon = valid_subplots.geometry.centroid.x.mean()
            zoom_start = 14
        else:
            # Fallback to a reasonable default location (you can change this to your study area)
            center_lat = 0.0
            center_lon = 0.0
            zoom_start = 2  # Very zoomed out to show the world
    
    # Create base map
    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_start)
    
    # Create feature groups for each layer
    valid_subplots_group = folium.FeatureGroup(name='Valid Subplots', show=True)
    invalid_subplots_group = folium.FeatureGroup(name='Invalid Subplots', show=True)
    valid_plots_group = folium.FeatureGroup(name='Valid Plots', show=True)
    invalid_plots_group = folium.FeatureGroup(name='Invalid Plots', show=True)
    selected_plots_group = folium.FeatureGroup(name='Selected Plots (Initial)', show=True)
    
    # Add all feature groups to the map
    valid_subplots_group.add_to(m)
    invalid_subplots_group.add_to(m)
    valid_plots_group.add_to(m)
    invalid_plots_group.add_to(m)
    selected_plots_group.add_to(m)
    
    # Add layer control
    folium.LayerControl(collapsed=False).add_to(m)
    
    # Add fullscreen option
    plugins.Fullscreen().add_to(m)
    
    # Create custom legend
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; right: 50px; 
                border:2px solid grey; z-index:9999; 
                background-color:white;
                padding: 10px;
                font-size: 14px;
                border-radius: 5px;
                box-shadow: 0 0 15px rgba(0,0,0,0.2);">
    <p style="margin: 0 0 5px 0;"><b>Map Legend</b></p>
    <p style="margin: 0 0 5px 0;"><i>Plots:</i></p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: blue; opacity: 0.2; border: 2px solid blue;"></span>
        Valid Plot
    </p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: orange; opacity: 0.2; border: 2px solid orange;"></span>
        Invalid Plot
    </p>
    <p style="margin: 0 0 5px 0;"><i>Subplots:</i></p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: green; opacity: 0.3; border: 1px solid green;"></span>
        Valid Subplot
    </p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: red; opacity: 0.3; border: 1px solid red;"></span>
        Invalid Subplot
    </p>
    <p style="margin: 0 0 5px 0;"><i>Initial Selection:</i></p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: purple; opacity: 0.4; border: 3px solid purple;"></span>
        Selected Plot (Initial)
    </p>
    <p style="margin: 0 0 5px 0;"><i>Selection:</i></p>
    <p style="margin: 0 0 2px 0;">
        <span style="display: inline-block; width: 20px; height: 20px; background-color: yellow; opacity: 0.5; border: 3px solid yellow;"></span>
        Selected Item
    </p>
    </div>
    '''
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Function to create popup content
    def create_popup_content(row):
        content = f"""
        <b>ID:</b> {row.get('plot_id', row.get('subplot_id', 'N/A'))}<br>
        <b>Enumerator:</b> {row.get('enumerator', 'N/A')}<br>
        <b>Collection Date:</b> {row.get('collection_date', 'N/A')}<br>
        """
        # Add NDVI and slope if available
        if 'mean_ndvi' in row and not pd.isna(row['mean_ndvi']):
            content += f"<b>Mean NDVI:</b> {row['mean_ndvi']:.3f}<br>"
        if 'mean_slope' in row and not pd.isna(row['mean_slope']):
            content += f"<b>Mean Slope:</b> {row['mean_slope']:.2f}<br>"
        if not row.get('valid', True):
            content += f"<b>Validation Issues:</b> {row.get('reasons', 'N/A')}<br>"
        return content
    
    # Add selected plots layer (initial polygons)
    if not df_selected_plots.empty:
        # Add a plot_id column if it doesn't exist for consistency
        if 'plot_id' not in df_selected_plots.columns:
            df_selected_plots['plot_id'] = df_selected_plots.index.astype(str)
        
        folium.GeoJson(
            df_selected_plots,
            name='Sampled plots',
            style_function=lambda x: {
                'fillColor': 'purple' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'color': 'purple' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'weight': 4 if x['properties']['plot_id'] == selected_plot_id else 3,
                'fillOpacity': 0.6 if x['properties']['plot_id'] == selected_plot_id else 0.4,
                'opacity': 1.0 if x['properties']['plot_id'] == selected_plot_id else 0.8
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['plot_id', 'area_ha'] if 'plot_id' in df_selected_plots.columns and 'area_ha' in df_selected_plots.columns else ['plot_id'] if 'plot_id' in df_selected_plots.columns else [],
                aliases=['Plot ID:', 'Area (ha):'] if 'plot_id' in df_selected_plots.columns and 'area_ha' in df_selected_plots.columns else ['Plot ID:'] if 'plot_id' in df_selected_plots.columns else [],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            ),
            popup=folium.GeoJsonPopup(
                fields=['plot_id', 'area_ha'] if 'plot_id' in df_selected_plots.columns and 'area_ha' in df_selected_plots.columns else ['plot_id'] if 'plot_id' in df_selected_plots.columns else [],
                aliases=['Plot ID:', 'Area (ha):'] if 'plot_id' in df_selected_plots.columns and 'area_ha' in df_selected_plots.columns else ['Plot ID:'] if 'plot_id' in df_selected_plots.columns else [],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            )
        ).add_to(selected_plots_group)
    
    # Add valid subplots layer with highlighting for selected plot
    valid_subplots = df_subplots[df_subplots['valid']]
    if not valid_subplots.empty:
        valid_subplots_gdf = gpd.GeoDataFrame(valid_subplots, geometry='geometry', crs="EPSG:4326")
        folium.GeoJson(
            valid_subplots_gdf,
            name='Valid Subplots',
            style_function=lambda x: {
                'fillColor': 'green' if x['properties']['subplot_id'] != selected_plot_id else 'yellow',
                'color': 'green' if x['properties']['subplot_id'] != selected_plot_id else 'yellow',
                'weight': 3 if x['properties']['subplot_id'] == selected_plot_id else 1,
                'fillOpacity': 0.5 if x['properties']['subplot_id'] == selected_plot_id else 0.3
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['subplot_id', 'enumerator'],
                aliases=['Subplot ID:', 'Enumerator:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            ),
            popup=folium.GeoJsonPopup(
                fields=['subplot_id', 'enumerator', 'collection_date'],
                aliases=['Subplot ID:', 'Enumerator:', 'Collection Date:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            )
        ).add_to(valid_subplots_group)
    
    # Add invalid subplots layer with highlighting
    invalid_subplots = df_subplots[~df_subplots['valid']]
    if not invalid_subplots.empty:
        invalid_subplots_gdf = gpd.GeoDataFrame(invalid_subplots, geometry='geometry', crs="EPSG:4326")
        folium.GeoJson(
            invalid_subplots_gdf,
            name='Invalid Subplots',
            style_function=lambda x: {
                'fillColor': 'red' if x['properties']['subplot_id'] != selected_plot_id else 'yellow',
                'color': 'red' if x['properties']['subplot_id'] != selected_plot_id else 'yellow',
                'weight': 3 if x['properties']['subplot_id'] == selected_plot_id else 1,
                'fillOpacity': 0.5 if x['properties']['subplot_id'] == selected_plot_id else 0.3
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['subplot_id', 'enumerator', 'reasons'],
                aliases=['Subplot ID:', 'Enumerator:', 'Issues:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            ),
            popup=folium.GeoJsonPopup(
                fields=['subplot_id', 'enumerator', 'collection_date', 'reasons'],
                aliases=['Subplot ID:', 'Enumerator:', 'Collection Date:', 'Validation Issues:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            )
        ).add_to(invalid_subplots_group)
    
    # Add valid plots layer with highlighting
    valid_plots = df_plots[df_plots['valid']]
    if not valid_plots.empty:
        valid_plots_gdf = gpd.GeoDataFrame(valid_plots, geometry='geometry', crs="EPSG:4326")
        folium.GeoJson(
            valid_plots_gdf,
            name='Valid Plots',
            style_function=lambda x: {
                'fillColor': 'blue' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'color': 'blue' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'weight': 3 if x['properties']['plot_id'] == selected_plot_id else 2,
                'fillOpacity': 0.4 if x['properties']['plot_id'] == selected_plot_id else 0.2
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['plot_id', 'enumerator'],
                aliases=['Plot ID:', 'Enumerator:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            ),
            popup=folium.GeoJsonPopup(
                fields=['plot_id', 'enumerator', 'collection_date'],
                aliases=['Plot ID:', 'Enumerator:', 'Collection Date:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            )
        ).add_to(valid_plots_group)
    
    # Add invalid plots layer with highlighting
    invalid_plots = df_plots[~df_plots['valid']]
    if not invalid_plots.empty:
        invalid_plots_gdf = gpd.GeoDataFrame(invalid_plots, geometry='geometry', crs="EPSG:4326")
        folium.GeoJson(
            invalid_plots_gdf,
            name='Invalid Plots',
            style_function=lambda x: {
                'fillColor': 'orange' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'color': 'orange' if x['properties']['plot_id'] != selected_plot_id else 'yellow',
                'weight': 3 if x['properties']['plot_id'] == selected_plot_id else 2,
                'fillOpacity': 0.4 if x['properties']['plot_id'] == selected_plot_id else 0.2
            },
            tooltip=folium.GeoJsonTooltip(
                fields=['plot_id', 'enumerator', 'reasons'],
                aliases=['Plot ID:', 'Enumerator:', 'Issues:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            ),
            popup=folium.GeoJsonPopup(
                fields=['plot_id', 'enumerator', 'collection_date', 'reasons'],
                aliases=['Plot ID:', 'Enumerator:', 'Collection Date:', 'Validation Issues:'],
                style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
            )
        ).add_to(invalid_plots_group)
    
    return m

def process_data(uploaded_file, selected_plot_file, output_dir):
    """Process the uploaded Excel file and generate validation outputs"""
    try:
        # Create a temporary directory to store the uploaded file
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            
            # Create the required directory structure
            ground_truth_dir = temp_dir / "ground-truth" / YEAR / "Ground Truth Collection v3"
            ground_truth_dir.mkdir(parents=True, exist_ok=True)
            
            # Save the uploaded file to the correct location
            temp_file = ground_truth_dir / uploaded_file.name
            with open(temp_file, 'wb') as f:
                f.write(uploaded_file.getvalue())
            
            # Process selected plot file if provided
            df_selected_plots = pd.DataFrame()
            if selected_plot_file is not None:
                
                try:
                    # Read the selected plot Excel file
                    df_selected_plots = pd.read_excel(selected_plot_file)
                    
                    
                    # Check if geometry column exists
                    if 'geometry' not in df_selected_plots.columns:
                        
                        st.warning("Selected plot file does not contain 'geometry' column. Skipping selected plot processing.")
                        df_selected_plots = pd.DataFrame()
                    else:
                        # Validate and filter geometry before converting to GeoDataFrame
                        valid_records = []
                        problematic_records = []
                        
                        
                        
                        for idx, row in df_selected_plots.iterrows():
                            try:
                                # Get plot ID for logging
                                plot_id = row.get('plot_id', f'Row {idx}')
                                
                                # Check if geometry is valid
                                geom = row['geometry']
                                if geom is None or pd.isna(geom):
                                    problematic_records.append({
                                        'index': idx,
                                        'id': plot_id,
                                        'error': 'Geometry is None or NaN'
                                    })
                                    
                                    continue
                                
                                # Try to validate the geometry
                                if hasattr(geom, 'is_valid') and not geom.is_valid:
                                    problematic_records.append({
                                        'index': idx,
                                        'id': plot_id,
                                        'error': 'Invalid geometry'
                                    })
                                    
                                    continue
                                
                                if hasattr(geom, 'is_empty') and geom.is_empty:
                                    problematic_records.append({
                                        'index': idx,
                                        'id': plot_id,
                                        'error': 'Empty geometry'
                                    })
                                    
                                    continue
                                
                                # If we get here, the geometry is valid
                                valid_records.append(row)
                               
                                
                            except Exception as e:
                                plot_id = row.get('plot_id', f'Row {idx}')
                                problematic_records.append({
                                    'index': idx,
                                    'id': plot_id,
                                    'error': f'Processing error: {str(e)}'
                                })
                                
                                continue
                        
                        
                        
                        # Log problematic records
                        if problematic_records:
                            # Display warning to user
                            st.warning(f"⚠️ Found {len(problematic_records)} selected plot records with invalid geometry:")
                            for record in problematic_records:
                                st.write(f"   • **ID:** {record['id']} - **Issue:** {record['error']}")
                        
                        # Create GeoDataFrame with valid records only
                        if valid_records:
                            try:
                                # Convert string geometry representations to actual Shapely objects
                                for record in valid_records:
                                    try:
                                        geom = record['geometry']
                                        if isinstance(geom, str):
                                            # Try different geometry formats
                                            try:
                                                # First try WKT (Well-Known Text) format
                                                from shapely.wkt import loads as wkt_loads
                                                record['geometry'] = wkt_loads(geom)
                                            except:
                                                try:
                                                    # Try GeoJSON format
                                                    import json
                                                    from shapely.geometry import shape
                                                    geojson_data = json.loads(geom)
                                                    record['geometry'] = shape(geojson_data)
                                                except:
                                                    # Try to parse as coordinate string
                                                    try:
                                                        from shapely.geometry import Polygon
                                                        # Remove POLYGON wrapper and parse coordinates
                                                        if geom.startswith('POLYGON ((') and geom.endswith('))'):
                                                            coord_str = geom[10:-2]  # Remove 'POLYGON ((' and '))'
                                                            # Parse coordinate pairs
                                                            coords = []
                                                            for pair in coord_str.split(','):
                                                                pair = pair.strip()
                                                                if pair:
                                                                    lon, lat = map(float, pair.split())
                                                                    coords.append((lon, lat))
                                                            if len(coords) >= 3:
                                                                record['geometry'] = Polygon(coords)
                                                                logger.debug(f"Converted coordinate string to Shapely Polygon")
                                                            else:
                                                                raise ValueError("Not enough coordinates for polygon")
                                                        else:
                                                            raise ValueError("Unknown geometry format")
                                                    except Exception as coord_error:
                                                        logger.warning(f"Could not parse geometry string: {str(coord_error)}")
                                                        raise coord_error
                                        elif hasattr(geom, 'wkt'):
                                            # Already a Shapely object, just ensure it's valid
                                            if not geom.is_valid:
                                                geom = geom.buffer(0)  # Try to fix self-intersections
                                                if geom.is_valid:
                                                    record['geometry'] = geom
                                                
                                        else:
                                            raise ValueError(f"Unknown geometry type: {type(geom)}")
                                            
                                    except Exception as e:
                                        # Remove this record from valid_records
                                        valid_records.remove(record)
                                        problematic_records.append({
                                            'index': len(problematic_records),
                                            'id': record.get('plot_id', 'Unknown'),
                                            'error': f'Geometry conversion error: {str(e)}'
                                        })
                                        continue
                                
                                
                                if valid_records:
                                    df_selected_plots = gpd.GeoDataFrame(valid_records, geometry='geometry', crs="EPSG:4326")
                                    logger.info(f"Successfully created GeoDataFrame with {len(df_selected_plots)} valid selected plots")
                                    
                                    # Calculate areas in hectares using UTM projection for accuracy
                                    logger.info("Calculating areas for selected plots using UTM projection...")
                                    
                                    # Calculate areas using UTM projection (same method as main plots/subplots)
                                    df_selected_plots['area_ha'] = df_selected_plots[~df_selected_plots.geometry.isna()].geometry.apply(
                                        lambda x: geom_to_utm(x).area / 10000  # Convert from m² to hectares
                                    )
                                    
                                    logger.info(f"Area calculation complete. Range: {df_selected_plots['area_ha'].min():.2f} - {df_selected_plots['area_ha'].max():.2f} hectares")
                                    
                                    # --- NDVI/Slope Merge ---
                                    try:
                                        ndvi_slope_path = Path('rs_data') / f'{PARTNER}_Polygons_NDVI_Slope.csv'
                                        if ndvi_slope_path.exists():
                                            df_ndvi = pd.read_csv(ndvi_slope_path)
                                            # Only keep relevant columns
                                            ndvi_cols = ['plot_id', 'mean_ndvi', 'mean_slope']
                                            df_ndvi = df_ndvi[ndvi_cols]
                                            # Merge on plot_id
                                            df_selected_plots = df_selected_plots.merge(df_ndvi, on='plot_id', how='left')
                                            logger.info(f"Merged NDVI/slope data: {df_ndvi.shape[0]} records")
                                        else:
                                            logger.warning(f"NDVI/Slope file not found: {ndvi_slope_path}")
                                    except Exception as e:
                                        logger.error(f"Error merging NDVI/Slope data: {str(e)}")
                                    # --- End NDVI/Slope Merge ---
                                    if problematic_records:
                                        st.info(f"✅ Successfully processed {len(df_selected_plots)} valid selected plots. {len(problematic_records)} records were skipped due to geometry issues.")
                                    else:
                                        st.success(f"✅ Successfully processed all {len(df_selected_plots)} selected plots.")
                                else:
                                    logger.warning("No valid records after geometry conversion")
                                    st.error("❌ No valid selected plot records found after geometry conversion.")
                                    df_selected_plots = pd.DataFrame()
                                    
                            except Exception as e:
                                logger.error(f"Error creating GeoDataFrame from valid records: {str(e)}", exc_info=True)
                                st.error(f"Error creating GeoDataFrame from valid records: {str(e)}")
                                st.info("Continuing with main data processing...")
                                df_selected_plots = pd.DataFrame()
                        else:
                            logger.warning("No valid selected plot records found")
                            st.error("❌ No valid selected plot records found. All records had geometry issues.")
                            df_selected_plots = pd.DataFrame()
                        
                except Exception as e:
                    logger.error(f"Error processing selected plot file: {str(e)}", exc_info=True)
                    st.error(f"Error processing selected plot file: {str(e)}")
                    st.info("Continuing with main data processing...")
                    df_selected_plots = pd.DataFrame()
            
            # Process subplots
            logger.info("Processing subplots...")
            try:
                logger.info("Starting subplot parsing...")
                df_subplots = ExcelParser.parse_subplots(temp_dir)
                logger.info(f"Parsed {len(df_subplots)} subplots from Excel files")
                
                logger.info("Applying geometry fixes...")
                df_subplots = df_subplots.pipe(fix_geometry)
                logger.info(f"After geometry fixes: {len(df_subplots)} subplots")
                
                logger.info("Adding ecoregion data...")
                df_subplots = df_subplots.pipe(add_ecoregion, "subplot_id")
                logger.info(f"After ecoregion: {len(df_subplots)} subplots")
                
                logger.info("Validating length-width ratio...")
                df_subplots = df_subplots.pipe(validate_length_width_ratio, 2)
                logger.info(f"After length-width validation: {len(df_subplots)} subplots")
                
                logger.info("Validating protruding ratio...")
                df_subplots = df_subplots.pipe(validate_protruding_ratio, 1.55)
                logger.info(f"After protruding validation: {len(df_subplots)} subplots")
                
                logger.info("Validating country boundaries...")
                df_subplots = df_subplots.pipe(validate_country)
                logger.info(f"After country validation: {len(df_subplots)} subplots")
                
                logger.info("Checking for duplicate IDs...")
                df_subplots = df_subplots.pipe(validate_duplicate_id, "subplot_id")
                logger.info(f"After duplicate check: {len(df_subplots)} subplots")
                
                logger.info("Calculating areas...")
                df_subplots = df_subplots.pipe(calculate_area)
                logger.info(f"After area calculation: {len(df_subplots)} subplots")
                
                logger.info("Validating number of vertices...")
                df_subplots = df_subplots.pipe(validate_nr_vertices)
                logger.info(f"After vertex validation: {len(df_subplots)} subplots")
                
                logger.info("Validating within radius...")
                df_subplots = df_subplots.pipe(validate_within_radius, radius=40)
                logger.info(f"After radius validation: {len(df_subplots)} subplots")
                
                logger.info("Validating overlaps...")
                df_subplots = df_subplots.pipe(
                    validate_overlap,
                    "subplot_id",
                    min_overlap=0.1,
                    buffer=-5,
                    filter=lambda x: x[
                        (x.in_country)
                        & (x.in_radius)
                        & (MIN_SUBPLOT_AREA_SIZE < x.area_m2)
                        & (x.area_m2 < MAX_SUBPLOT_AREA_SIZE)
                        & (~x.protruding_ratio_too_big)
                        & (~x.nr_vertices_too_small)
                    ]
                )
                logger.info(f"After overlap validation: {len(df_subplots)} subplots")
                
                logger.info("Collecting validation reasons...")
                df_subplots = df_subplots.assign(
                    reasons=lambda x: x.apply(collect_reasons_subplot, axis=1),
                    valid=lambda x: x.reasons.apply(len) == 0,
                    geojson=lambda x: x.apply(
                        lambda x: to_geojson(x.geometry, x.subplot_id), axis=1
                    ),
                )
                logger.info(f"Successfully processed {len(df_subplots)} subplots")
                logger.info(f"Valid subplots: {df_subplots['valid'].sum()}, Invalid subplots: {(~df_subplots['valid']).sum()}")
            except Exception as e:
                logger.error(f"Error processing subplots: {str(e)}", exc_info=True)
                st.error(f"Error processing subplots: {str(e)}")
                df_subplots = pd.DataFrame()  # Create empty DataFrame as fallback
            
            # Process plots
            logger.info("Processing plots...")
            try:
                logger.info("Starting plot parsing...")
                df_plots = ExcelParser.parse_plots(temp_dir)
                logger.info(f"Parsed {len(df_plots)} plots from Excel files")
                
                logger.info("Applying geometry fixes...")
                df_plots = df_plots.pipe(fix_geometry)
                logger.info(f"After geometry fixes: {len(df_plots)} plots")
                
                logger.info("Adding ecoregion data...")
                df_plots = df_plots.pipe(add_ecoregion, "plot_id")
                logger.info(f"After ecoregion: {len(df_plots)} plots")
                
                logger.info("Validating protruding ratio...")
                df_plots = df_plots.pipe(validate_protruding_ratio, 1.55)
                logger.info(f"After protruding validation: {len(df_plots)} plots")
                
                logger.info("Validating country boundaries...")
                df_plots = df_plots.pipe(validate_country)
                logger.info(f"After country validation: {len(df_plots)} plots")
                
                logger.info("Checking for duplicate IDs...")
                df_plots = df_plots.pipe(validate_duplicate_id, "plot_id")
                logger.info(f"After duplicate check: {len(df_plots)} plots")
                
                logger.info("Calculating areas...")
                df_plots = df_plots.pipe(calculate_area)
                logger.info(f"After area calculation: {len(df_plots)} plots")
                
                logger.info("Validating number of vertices...")
                df_plots = df_plots.pipe(validate_nr_vertices)
                logger.info(f"After vertex validation: {len(df_plots)} plots")
                
                logger.info("Validating within radius...")
                df_plots = df_plots.pipe(validate_within_radius, radius=200)
                logger.info(f"After radius validation: {len(df_plots)} plots")
                
                logger.info("Validating overlaps...")
                df_plots = df_plots.pipe(
                    validate_overlap,
                    "plot_id",
                    min_overlap=0.1,
                    buffer=0,
                    filter=lambda x: x[
                        (x.in_country)
                        & (x.in_radius)
                        & (MIN_GT_PLOT_AREA_SIZE < x.area_m2)
                        & (x.area_m2 < MAX_GT_PLOT_AREA_SIZE)
                        & (~x.protruding_ratio_too_big)
                        & (~x.nr_vertices_too_small)
                    ]
                )
                logger.info(f"After overlap validation: {len(df_plots)} plots")
                
                logger.info("Collecting validation reasons...")
                df_plots = df_plots.assign(
                    reasons=lambda x: x.apply(collect_reasons_plot, axis=1),
                    valid=lambda x: x.reasons.apply(len) == 0,
                    geojson=lambda x: x.apply(lambda x: to_geojson(x.geometry, x.plot_id), axis=1),
                )
                logger.info(f"Successfully processed {len(df_plots)} plots")
                logger.info(f"Valid plots: {df_plots['valid'].sum()}, Invalid plots: {(~df_plots['valid']).sum()}")
            except Exception as e:
                logger.error(f"Error processing plots: {str(e)}", exc_info=True)
                st.error(f"Error processing plots: {str(e)}")
                df_plots = pd.DataFrame()  # Create empty DataFrame as fallback
            
            # Clean up enumerator names for display
            if not df_subplots.empty:
                df_subplots['enumerator_display'] = df_subplots['enumerator'].apply(clean_enumerator_name)
            if not df_plots.empty:
                df_plots['enumerator_display'] = df_plots['enumerator'].apply(clean_enumerator_name)
            
            # Final processing summary
            logger.info("=== PROCESSING SUMMARY ===")
            logger.info(f"Selected plots processed: {len(df_selected_plots)}")
            logger.info(f"Subplots processed: {len(df_subplots)}")
            logger.info(f"Plots processed: {len(df_plots)}")
            
            if not df_subplots.empty:
                logger.info(f"Subplot validation: {df_subplots['valid'].sum()} valid, {(~df_subplots['valid']).sum()} invalid")
            if not df_plots.empty:
                logger.info(f"Plot validation: {df_plots['valid'].sum()} valid, {(~df_plots['valid']).sum()} invalid")
            
            # Display summary to user
            st.success("✅ Data processing completed!")
            st.write("### Processing Summary:")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Selected Plots", len(df_selected_plots))
            
            with col2:
                st.metric("Subplots", len(df_subplots))
                if not df_subplots.empty:
                    st.metric("Valid Subplots", df_subplots['valid'].sum())
                    st.metric("Invalid Subplots", (~df_subplots['valid']).sum())
            
            with col3:
                st.metric("Plots", len(df_plots))
                if not df_plots.empty:
                    st.metric("Valid Plots", df_plots['valid'].sum())
                    st.metric("Invalid Plots", (~df_plots['valid']).sum())
            
            # Export results
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            try:
                if not df_subplots.empty:
                    export_subplots(df_subplots, output_dir)
                    logger.info("Successfully exported subplots")
            except Exception as e:
                logger.error(f"Error exporting subplots: {str(e)}", exc_info=True)
                st.error(f"Error exporting subplots: {str(e)}")
            
            try:
                if not df_plots.empty:
                    export_plots(df_plots, output_dir)
                    logger.info("Successfully exported plots")
            except Exception as e:
                logger.error(f"Error exporting plots: {str(e)}", exc_info=True)
                st.error(f"Error exporting plots: {str(e)}")
            
            try:
                if not df_selected_plots.empty:
                    # Export selected plots to GeoJSON
                    logger.info("Exporting selected plots to GeoJSON...")
                    
                    # Create a copy for export (remove any problematic columns)
                    df_selected_plots_export = df_selected_plots.copy()
                    
                    # Ensure we have the essential columns
                    export_columns = ['plot_id', 'area_ha', 'geometry']
                    if 'enumerator' in df_selected_plots_export.columns:
                        export_columns.append('enumerator')
                    if 'collection_date' in df_selected_plots_export.columns:
                        export_columns.append('collection_date')
                    
                    # Select only the columns we want to export
                    df_selected_plots_export = df_selected_plots_export[export_columns]
                    
                    # Export to GeoJSON
                    selected_plots_geojson_path = output_dir / "selected_plots.geojson"
                    df_selected_plots_export.to_file(
                        selected_plots_geojson_path,
                        driver="GeoJSON",
                        index=False
                    )
                    logger.info(f"Successfully exported {len(df_selected_plots)} selected plots to {selected_plots_geojson_path}")
                    
                    # Also export as Excel for reference
                    selected_plots_excel_path = output_dir / "selected_plots.xlsx"
                    df_selected_plots_export.to_excel(selected_plots_excel_path, index=False)
                    logger.info(f"Successfully exported {len(df_selected_plots)} selected plots to {selected_plots_excel_path}")
                    
            except Exception as e:
                logger.error(f"Error exporting selected plots: {str(e)}", exc_info=True)
                st.error(f"Error exporting selected plots: {str(e)}")
            
            return df_subplots, df_plots, df_selected_plots
            
    except Exception as e:
        logger.error(f"Critical error in process_data: {str(e)}", exc_info=True)
        st.error(f"An error occurred during validation: {str(e)}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()  # Return empty DataFrames as fallback

# File upload section
uploaded_file = st.file_uploader("Upload Excel file", type=['xlsx', 'xls'])

# Selected plot file upload
selected_plot_file = st.file_uploader("Upload Selected Plot Excel file (optional)", type=['xlsx', 'xls'], 
                                     help="Upload an Excel file containing the initial polygons against which data was collected")

# Always use output/<PARTNER> as the output directory
output_dir = str(Path.cwd() / "output" / PARTNER)

def update_enumerator():
    """Update enumerator selection"""
    # Safely check if the key exists before accessing it
    if hasattr(st.session_state, 'enumerator_select') and st.session_state.enumerator_select != st.session_state.selected_enumerator:
        st.session_state.selected_enumerator = st.session_state.enumerator_select
        st.session_state.current_page = 1
        # Reset plot and subplot selections when enumerator changes
        st.session_state.selected_plot_id = None
        st.session_state.selected_subplot_id = None
        st.session_state.selected_plot_option = "None"
        st.session_state.selected_subplot_option = "None"

def update_plot():
    """Update plot selection"""
    # Safely check if the key exists before accessing it
    if hasattr(st.session_state, 'plot_select'):
        # Check if the selection has actually changed
        if st.session_state.plot_select != st.session_state.selected_plot_option:
            st.session_state.selected_plot_option = st.session_state.plot_select
            if st.session_state.plot_select == "None":
                st.session_state.selected_plot_id = None
                st.session_state.selected_subplot_id = None
                st.session_state.selected_subplot_option = "None"
            else:
                # Extract plot ID from the dropdown option
                plot_id_from_option = st.session_state.plot_select.split(" - ")[0]
                st.session_state.selected_plot_id = plot_id_from_option
                # Reset subplot selection when plot changes
                st.session_state.selected_subplot_id = None
                st.session_state.selected_subplot_option = "None"

def update_subplot():
    """Update subplot selection"""
    # Safely check if the key exists before accessing it
    if hasattr(st.session_state, 'subplot_select') and st.session_state.subplot_select != st.session_state.selected_subplot_option:
        st.session_state.selected_subplot_option = st.session_state.subplot_select
        if st.session_state.subplot_select == "None":
            st.session_state.selected_subplot_id = None
        else:
            st.session_state.selected_subplot_id = st.session_state.subplot_select.split(" - ")[0]

def reset_view():
    """Reset all selections to default state"""
    st.session_state.selected_plot_id = None
    st.session_state.selected_subplot_id = None
    st.session_state.selected_plot_option = "None"
    st.session_state.selected_subplot_option = "None"
    st.session_state.current_page = 1

# Process data if file is uploaded and not already processed
if uploaded_file is not None and st.button("Validate Data"):
    
    output_path = Path(output_dir)
    # Use the selected country ISO3 from the dropdown
    selected_iso3 = st.session_state.get("COUNTRY_ISO3")
    # Patch the COUNTRY_ISO3 in gt_config for this session (monkey patch)
    import sys
    import importlib
    if "gt_config" in sys.modules:
        importlib.reload(sys.modules["gt_config"])
    import gt_config
    gt_config.COUNTRY_ISO3 = selected_iso3
    # Define expected output files
    plots_valid_fp = output_path / "plots_valid.geojson"
    plots_invalid_fp = output_path / "plots_invalid.geojson"
    subplots_valid_fp = output_path / "subplots_valid.geojson"
    subplots_invalid_fp = output_path / "subplots_invalid.geojson"
    selected_plots_fp = output_path / "selected_plots.geojson"
    # Check if all required files exist
    files_exist = all(f.exists() for f in [plots_valid_fp, plots_invalid_fp, subplots_valid_fp, subplots_invalid_fp])
    selected_plots_exist = selected_plots_fp.exists()
    try:
        if files_exist:
            with st.spinner("Loading existing validation results..."):
                df_plots_valid = gpd.read_file(plots_valid_fp)
                df_plots_invalid = gpd.read_file(plots_invalid_fp)
                df_subplots_valid = gpd.read_file(subplots_valid_fp)
                df_subplots_invalid = gpd.read_file(subplots_invalid_fp)
                # Combine valid/invalid for full DataFrame
                df_plots = pd.concat([df_plots_valid.assign(valid=True), df_plots_invalid.assign(valid=False)], ignore_index=True)
                df_subplots = pd.concat([df_subplots_valid.assign(valid=True), df_subplots_invalid.assign(valid=False)], ignore_index=True)
                # Load selected plots if available
                if selected_plots_exist:
                    df_selected_plots = gpd.read_file(selected_plots_fp)
                    # Merge NDVI and slope if missing
                    if not df_selected_plots.empty and ('mean_ndvi' not in df_selected_plots.columns or 'mean_slope' not in df_selected_plots.columns):
                        try:
                            ndvi_slope_path = Path('rs_data') / f'{PARTNER}_Polygons_NDVI_Slope.csv'
                            if ndvi_slope_path.exists():
                                df_ndvi = pd.read_csv(ndvi_slope_path)
                                ndvi_cols = ['plot_id', 'mean_ndvi', 'mean_slope']
                                df_ndvi = df_ndvi[ndvi_cols]
                                df_selected_plots = df_selected_plots.merge(df_ndvi, on='plot_id', how='left')
                            else:
                                st.warning(f"NDVI/Slope file not found: {ndvi_slope_path}")
                        except Exception as e:
                            st.error(f"Error merging NDVI/Slope data after loading from file: {str(e)}")
                else:
                    df_selected_plots = pd.DataFrame()
                st.session_state.processed_data = {
                    'df_subplots': df_subplots,
                    'df_plots': df_plots,
                    'df_selected_plots': df_selected_plots
                }
                st.success(f"Loaded existing validation results from {output_dir}")
        else:
            with st.spinner("Processing data..."):
                df_subplots, df_plots, df_selected_plots = process_data(uploaded_file, selected_plot_file, output_dir)
                st.session_state.processed_data = {
                    'df_subplots': df_subplots,
                    'df_plots': df_plots,
                    'df_selected_plots': df_selected_plots
                }
    except Exception as e:
        st.error(f"An error occurred during validation: {str(e)}")
        st.exception(e)

# Display results if data has been processed
if st.session_state.processed_data is not None:
    df_subplots = st.session_state.processed_data['df_subplots']
    df_plots = st.session_state.processed_data['df_plots']
    df_selected_plots = st.session_state.processed_data['df_selected_plots']
    
    # Ensure enumerator_display column exists
    if 'enumerator_display' not in df_plots.columns and 'enumerator' in df_plots.columns:
        df_plots['enumerator_display'] = df_plots['enumerator'].apply(clean_enumerator_name)
    elif 'enumerator_display' not in df_plots.columns:
        df_plots['enumerator_display'] = 'Unknown'
    
    if 'enumerator_display' not in df_subplots.columns and 'enumerator' in df_subplots.columns:
        df_subplots['enumerator_display'] = df_subplots['enumerator'].apply(clean_enumerator_name)
    elif 'enumerator_display' not in df_subplots.columns:
        df_subplots['enumerator_display'] = 'Unknown'
    
    # Create tabs for different views
    tab_names = ["Map View", "Data Summary"]
    if not df_selected_plots.empty:
        tab_names.append("Sampled Plots Explorer")
    
    tabs = st.tabs(tab_names)
    
    with tabs[0]:
        # st.subheader("Interactive Map")
        
        # --- Plot Validation Reason Filter ---
        plot_reason_counts = {}
        for reasons in df_plots['reasons'].dropna():
            for reason in str(reasons).split(';'):
                reason = reason.strip()
                if reason:
                    plot_reason_counts[reason] = plot_reason_counts.get(reason, 0) + 1
        all_plot_reasons = sorted(plot_reason_counts.keys(), key=lambda k: plot_reason_counts[k], reverse=True)
        plot_reason_options = [f"{reason} ({plot_reason_counts[reason]})" for reason in all_plot_reasons]
        selected_plot_reason = st.selectbox(
            "Filter plots by validation reason",
            ["All"] + plot_reason_options,
            key="map_plot_reason_filter"
        )
        # Filter plots accordingly
        filtered_df_plots = df_plots.copy()
        if selected_plot_reason != "All":
            selected_reason = selected_plot_reason.split(" (")[0]
            filtered_df_plots = filtered_df_plots[filtered_df_plots['reasons'].fillna('').apply(lambda x: any(selected_reason == reason.strip() for reason in str(x).split(';')))]
        else:
            filtered_df_plots = df_plots.copy()
        
        # Create simple border styling
        st.markdown("""
        <style>
        .section-border {
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 1rem;
            margin: 1rem 0;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Enumerator and Plot Selection Section with border
        # st.markdown('<div class="section-border">', unsafe_allow_html=True)
        st.subheader("📊 Data Selection")
        
        # Create main plot selection interface
        st.subheader("Plots")
        if not filtered_df_plots.empty:
            # Prepare plots data
            # Ensure mrr_ratio and minimum_rotated_rectangle_m2 columns exist
            if 'mrr_ratio' not in filtered_df_plots.columns or 'minimum_rotated_rectangle_m2' not in filtered_df_plots.columns:
                from gt_check_functions import calculate_minimum_rotated_rectangle, calculate_area
                temp_df = filtered_df_plots.copy()
                temp_df = calculate_area(temp_df)
                temp_df = calculate_minimum_rotated_rectangle(temp_df)
                temp_df['mrr_ratio'] = temp_df['minimum_rotated_rectangle_m2'] / temp_df['area_m2']
                filtered_df_plots['mrr_ratio'] = temp_df['mrr_ratio']
                filtered_df_plots['minimum_rotated_rectangle_m2'] = temp_df['minimum_rotated_rectangle_m2']
            plots_data = filtered_df_plots[['plot_id', 'enumerator_display', 'collection_date', 'valid', 'reasons', 'area_m2', 'minimum_rotated_rectangle_m2', 'mrr_ratio']].copy()
            plots_data['valid'] = plots_data['valid'].map({True: 'Valid', False: 'Invalid'})
            
            # Create selectbox for plot selection using all plots instead of paginated ones
            plot_options = [f"{row['plot_id']} - {row['enumerator_display']} ({row['valid']})" 
                          for _, row in plots_data.iterrows()]
            
            # Find the index of the currently selected plot
            current_plot_index = 0
            if st.session_state.selected_plot_option != "None":
                try:
                    current_plot_index = plot_options.index(st.session_state.selected_plot_option) + 1
                except ValueError:
                    current_plot_index = 0
            
            selected_plot_option = st.selectbox(
                "Select a plot to view details and subplots",
                ["None"] + plot_options,
                index=current_plot_index,
                key="plot_select_display"
            )
            
            # Handle plot selection
            if selected_plot_option != "None":
                # Extract plot ID directly from the selected option
                plot_id_from_option = selected_plot_option.split(" - ")[0]
                
                # Check if this is a new selection
                if st.session_state.selected_plot_id != plot_id_from_option:
                    # Update session state directly
                    st.session_state.selected_plot_id = plot_id_from_option
                    st.session_state.selected_plot_option = selected_plot_option
                    # Force a re-render to update the UI
                    st.rerun()
                
                # Show selected plot details
                st.write("### Selected Plot Details")
                
                # Find the plot in the full dataset
                selected_plot_full = filtered_df_plots[filtered_df_plots['plot_id'] == st.session_state.selected_plot_id]
                if not selected_plot_full.empty:
                    selected_plot_data = selected_plot_full.iloc[0]
                else:
                    st.error(f"Selected plot {st.session_state.selected_plot_id} not found in dataset.")
                    # Reset the selection since it's not valid
                    st.session_state.selected_plot_id = None
                    st.session_state.selected_plot_option = "None"
                    selected_plot_data = None
                
                if selected_plot_data is not None:
                    # Display plot details in a compact box layout
                    with st.container():
                        st.markdown("""
                        <style>
                        .plot-details-box {
                            background-color: #f0f2f6;
                            padding: 1rem;
                            border-radius: 0.5rem;
                            border: 1px solid #e0e0e0;
                            margin: 0.5rem 0;
                        }
                        .plot-details-grid {
                            display: grid;
                            grid-template-columns: repeat(4, 1fr);
                            gap: 1rem;
                            font-size: 0.9rem;
                        }
                        .plot-detail-item {
                            display: flex;
                            flex-direction: column;
                        }
                        .plot-detail-label {
                            font-weight: 600;
                            color: #666;
                            font-size: 0.8rem;
                            margin-bottom: 0.25rem;
                        }
                        .plot-detail-value {
                            color: #333;
                            font-size: 0.9rem;
                        }
                        .subplot-summary-grid {
                            display: grid;
                            grid-template-columns: repeat(3, 1fr);
                            gap: 1rem;
                            font-size: 0.85rem;
                            margin-top: 1rem;
                        }
                        </style>
                        """, unsafe_allow_html=True)
                        
                        # Plot details box
                        plot_details_html = f"""
                        <div class="plot-details-box">
                            <div class="plot-details-grid">
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Plot ID</div>
                                    <div class="plot-detail-value">{selected_plot_data['plot_id']}</div>
                                </div>
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Enumerator</div>
                                    <div class="plot-detail-value">{selected_plot_data['enumerator_display']}</div>
                                </div>
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Collection Date</div>
                                    <div class="plot-detail-value">{selected_plot_data['collection_date']}</div>
                                </div>
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Status</div>
                                    <div class="plot-detail-value">{'✅ Valid' if selected_plot_data['valid'] else '❌ Invalid'}</div>
                                </div>
                            </div>
                        </div>
                        """
                        st.markdown(plot_details_html, unsafe_allow_html=True)
                    
                    # Show validation issues if any (in a separate row)
                    if not selected_plot_data['valid']:
                        st.error(f"**Validation Issues:** {selected_plot_data['reasons']}")
                    
                    # Show subplots for selected plot
                    st.write("### Subplots in this Plot")
                    plot_subplots = df_subplots[df_subplots['plot_id'] == st.session_state.selected_plot_id]
                    
                    if not plot_subplots.empty:
                        # Display subplot summary in a compact box
                        subplot_summary_html = f"""
                        <div class="plot-details-box">
                            <div class="subplot-summary-grid">
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Total Subplots</div>
                                    <div class="plot-detail-value">{len(plot_subplots)}</div>
                                </div>
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Valid Subplots</div>
                                    <div class="plot-detail-value">✅ {plot_subplots['valid'].sum()}</div>
                                </div>
                                <div class="plot-detail-item">
                                    <div class="plot-detail-label">Invalid Subplots</div>
                                    <div class="plot-detail-value">❌ {(~plot_subplots['valid']).sum()}</div>
                                </div>
                            </div>
                        </div>
                        """
                        st.markdown(subplot_summary_html, unsafe_allow_html=True)
                        
                        # Prepare subplots data
                        subplots_data = plot_subplots[['subplot_id', 'enumerator_display', 'collection_date', 'valid', 'reasons']].copy()
                        subplots_data['valid'] = subplots_data['valid'].map({True: 'Valid', False: 'Invalid'})
                        
                        # Sort by validation status (Invalid first, then Valid)
                        subplots_data = subplots_data.sort_values('valid', ascending=True)
                        
                        # Display subplots table
                        st.dataframe(
                            subplots_data,
                            column_config={
                                "subplot_id": "Subplot ID",
                                "enumerator_display": "Enumerator",
                                "collection_date": "Collection Date",
                                "valid": "Status",
                                "reasons": "Validation Issues"
                            },
                            hide_index=True,
                            use_container_width=True
                        )
                    else:
                        st.write("No subplots found for this plot.")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Add reset view button
        if st.button("Reset Map View", on_click=reset_view):
            pass  # The reset_view function handles all the state updates
        
        # Create and display the map
        st.write("### Map View")
        st.write("Explore the validation results on the map below. Use the layer control to toggle different layers.")
        try:
            # Determine which ID to use for map centering and highlighting
            selected_id = None
            if st.session_state.selected_subplot_id:
                selected_id = st.session_state.selected_subplot_id
            elif st.session_state.selected_plot_id:
                selected_id = st.session_state.selected_plot_id
            
            map_obj = create_map(
                df_subplots, 
                filtered_df_plots, 
                df_selected_plots,
                selected_id
            )
            folium_static(map_obj, width=1200, height=800)
        except Exception as e:
            st.error(f"Error displaying map: {str(e)}")
            reset_view()
    
    with tabs[1]:
        # Show summary statistics
        # st.subheader("Data Summary")
        
        # Create two columns for summary statistics
        col1, col2 = st.columns(2)
        
        with col1:
            # Add top-level switch for ignoring empty geometries
            ignore_empty_geom = st.checkbox("Ignore empty geometries", value=False, key="ignore_empty_geometries_switch")
            # Filter sub-plots if switch is on
            if ignore_empty_geom:
                df_subplots_filtered = df_subplots[~df_subplots['reasons'].fillna('').str.contains('Empty geometry')].copy()
            else:
                df_subplots_filtered = df_subplots.copy()
            st.write("### Subplots Summary")
            if df_subplots_filtered is not None and not df_subplots_filtered.empty:
                total_subplots = len(df_subplots_filtered)
                valid_subplots = df_subplots_filtered['valid'].sum()
                invalid_subplots = (~df_subplots_filtered['valid']).sum()
                valid_pct = (valid_subplots / total_subplots * 100) if total_subplots else 0
                invalid_pct = (invalid_subplots / total_subplots * 100) if total_subplots else 0
                st.write(f"Total subplots: {total_subplots}")
                st.write(f"Valid subplots: {valid_subplots} ({valid_pct:.1f}%)")
                st.write(f"Invalid subplots: {invalid_subplots} ({invalid_pct:.1f}%)")

                # --- Horizontal bar chart for sub-plot validation fail reasons ---
                subplot_reason_counts = {}
                for reasons in df_subplots_filtered['reasons'].dropna():
                    for reason in str(reasons).split(';'):
                        r = reason.strip()
                        if r:
                            subplot_reason_counts[r] = subplot_reason_counts.get(r, 0) + 1
                if subplot_reason_counts:
                    subplot_reason_df = pd.DataFrame({
                        'Reason': list(subplot_reason_counts.keys()),
                        'Count': list(subplot_reason_counts.values())
                    }).sort_values('Count', ascending=True)
                    fig = px.bar(
                        subplot_reason_df,
                        x='Count',
                        y='Reason',
                        orientation='h',
                        title='Sub-plot Validation Fail Reasons',
                        labels={'Count': 'Count', 'Reason': 'Validation Reason'},
                        height=300
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No subplots data available.")
        
        with col2:
            st.write("### Plots Summary")
            total_plots = len(df_plots)
            valid_plots = df_plots['valid'].sum()
            invalid_plots = (~df_plots['valid']).sum()
            valid_plots_pct = (valid_plots / total_plots * 100) if total_plots else 0
            invalid_plots_pct = (invalid_plots / total_plots * 100) if total_plots else 0
            st.write(f"Total plots: {total_plots}")
            st.write(f"Valid plots: {valid_plots} ({valid_plots_pct:.1f}%)")
            st.write(f"Invalid plots: {invalid_plots} ({invalid_plots_pct:.1f}%)")

            # --- Horizontal bar chart for plot validation fail reasons ---
            plot_reason_counts = {}
            for reasons in df_plots['reasons'].dropna():
                for reason in str(reasons).split(';'):
                    r = reason.strip()
                    if r:
                        plot_reason_counts[r] = plot_reason_counts.get(r, 0) + 1
            if plot_reason_counts:
                plot_reason_df = pd.DataFrame({
                    'Reason': list(plot_reason_counts.keys()),
                    'Count': list(plot_reason_counts.values())
                }).sort_values('Count', ascending=True)
                fig = px.bar(
                    plot_reason_df,
                    x='Count',
                    y='Reason',
                    orientation='h',
                    title='Plot Validation Fail Reasons',
                    labels={'Count': 'Count', 'Reason': 'Validation Reason'},
                    height=300
                )
                st.plotly_chart(fig, use_container_width=True)
        
        # Add selected plots summary if available
        # if not df_selected_plots.empty:
        #     st.write("### Selected Plots (Initial) Summary")
        #     st.write(f"Total selected plots: {len(df_selected_plots)}")
        #     st.write("These are the initial polygons against which data was collected.")
            
        #     # Show area statistics for selected plots
        #     col1, col2, col3, col4 = st.columns(4)
        #     with col1:
        #         st.metric("Total Area", f"{df_selected_plots['area_ha'].sum():.2f} ha")
        #     with col2:
        #         st.metric("Min Area", f"{df_selected_plots['area_ha'].min():.2f} ha")
        #     with col3:
        #         st.metric("Max Area", f"{df_selected_plots['area_ha'].max():.2f} ha")
        #     with col4:
        #         st.metric("Avg Area", f"{df_selected_plots['area_ha'].mean():.2f} ha")
            
        #     # Add selected plots data table
        #     st.write("### Selected Plots Data")
            
        #     # Prepare the selected plots table data
        #     selected_plots_table_data = df_selected_plots[[
        #         'plot_id',
        #         'area_ha'
        #     ]].copy()
            
        #     # Add other columns if they exist
        #     if 'enumerator' in df_selected_plots.columns:
        #         selected_plots_table_data['enumerator'] = df_selected_plots['enumerator']
        #     if 'collection_date' in df_selected_plots.columns:
        #         selected_plots_table_data['collection_date'] = df_selected_plots['collection_date']
            
        #     # Format the data for display
        #     selected_plots_table_data['area_ha'] = selected_plots_table_data['area_ha'].round(2)
        #     if 'collection_date' in selected_plots_table_data.columns:
        #         selected_plots_table_data['collection_date'] = pd.to_datetime(selected_plots_table_data['collection_date']).dt.strftime('%Y-%m-%d')
            
        #     # Display the selected plots table
        #     st.dataframe(
        #         selected_plots_table_data,
        #         column_config={
        #             "plot_id": st.column_config.TextColumn(
        #                 "Plot ID",
        #                 width="medium",
        #                 help="Unique identifier for the selected plot"
        #             ),
        #             "area_ha": st.column_config.NumberColumn(
        #                 "Area (ha)",
        #                 width="small",
        #                 help="Area of the selected plot in hectares",
        #                 format="%.2f"
        #             ),
        #             "enumerator": st.column_config.TextColumn(
        #                 "Enumerator",
        #                 width="medium",
        #                 help="Name of the enumerator (if available)"
        #             ) if 'enumerator' in selected_plots_table_data.columns else None,
        #             "collection_date": st.column_config.TextColumn(
        #                 "Collection Date",
        #                 width="small",
        #                 help="Date when the plot was collected (if available)"
        #             ) if 'collection_date' in selected_plots_table_data.columns else None
        #         },
        #         hide_index=True,
        #         use_container_width=True,
        #         height=400
        #     )
            
        #     # Add download button for the selected plots data
        #     csv_selected_plots = df_selected_plots.to_csv(index=False).encode('utf-8')
        #     st.download_button(
        #         "Download Selected Plots Data",
        #         csv_selected_plots,
        #         "selected_plots.csv",
        #         "text/csv",
        #         key='download-selected-plots-display'
        #     )
        
        # Add plots data table
        st.write("### Plots Data")
        
        # Add filters for the plots table
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "Valid", "Invalid"],
                key="plot_status_filter_display"
            )
        with filter_col2:
            enumerator_filter = st.selectbox(
                "Filter by Enumerator",
                ["All"] + sorted(df_plots['enumerator_display'].unique().tolist()),
                key="plot_enumerator_filter_display"
            )
        # Validation issues filter
        # Collect all unique issues (split by ';')
        plot_issue_counts = {}
        for issues in df_plots['reasons'].dropna():
            for issue in str(issues).split(';'):
                issue = issue.strip()
                if issue:
                    plot_issue_counts[issue] = plot_issue_counts.get(issue, 0) + 1
        all_plot_issues = sorted(plot_issue_counts.keys(), key=lambda k: plot_issue_counts[k], reverse=True)
        plot_issue_options = [f"{issue} ({plot_issue_counts[issue]})" for issue in all_plot_issues]
        with filter_col3:
            plot_issue_filter = st.selectbox(
                "Filter by Validation Issue",
                ["All"] + plot_issue_options,
                key="plot_issue_filter_display"
            )
        
        # Filter the plots data
        filtered_plots_table = df_plots.copy()
        if status_filter != "All":
            filtered_plots_table = filtered_plots_table[filtered_plots_table['valid'] == (status_filter == "Valid")]
        if enumerator_filter != "All":
            filtered_plots_table = filtered_plots_table[filtered_plots_table['enumerator_display'] == enumerator_filter]
        if plot_issue_filter != "All":
            selected_issue = plot_issue_filter.split(" (")[0]  # Extract issue name from "Issue (count)" format
            filtered_plots_table = filtered_plots_table[filtered_plots_table['reasons'].fillna('').apply(lambda x: any(selected_issue == issue.strip() for issue in str(x).split(';')))]
        
        # Prepare the table data
        # Count sub-plots for each plot
        subplot_counts = df_subplots_filtered.groupby('plot_id').size().reset_index(name='subplot_count')
        valid_subplot_counts = df_subplots_filtered[df_subplots_filtered['valid']].groupby('plot_id').size().reset_index(name='valid_subplot_count')
        # Add mrr_ratio if not present
        if 'mrr_ratio' not in filtered_plots_table.columns or 'minimum_rotated_rectangle_m2' not in filtered_plots_table.columns:
            from gt_check_functions import calculate_minimum_rotated_rectangle, calculate_area
            temp_df = filtered_plots_table.copy()
            temp_df = calculate_area(temp_df)
            temp_df = calculate_minimum_rotated_rectangle(temp_df)
            temp_df['mrr_ratio'] = temp_df['minimum_rotated_rectangle_m2'] / temp_df['area_m2']
            filtered_plots_table['mrr_ratio'] = temp_df['mrr_ratio']
            filtered_plots_table['minimum_rotated_rectangle_m2'] = temp_df['minimum_rotated_rectangle_m2']
        table_data = filtered_plots_table[[
            'plot_id', 
            'enumerator_display', 
            'collection_date', 
            'valid', 
            'reasons',
            'area_m2',
            'mrr_ratio'  # keep for formatting, do not display
        ]].copy()
        # Merge subplot counts
        table_data = table_data.merge(subplot_counts, on='plot_id', how='left')
        table_data = table_data.merge(valid_subplot_counts, on='plot_id', how='left')
        table_data['subplot_count'] = table_data['subplot_count'].fillna(0).astype(int)
        table_data['valid_subplot_count'] = table_data['valid_subplot_count'].fillna(0).astype(int)
        
        # Format the data for display
        table_data['valid'] = table_data['valid'].map({True: '✅ Valid', False: '❌ Invalid'})
        table_data['area_m2'] = table_data['area_m2'].round(2)
        table_data['collection_date'] = pd.to_datetime(table_data['collection_date']).dt.strftime('%Y-%m-%d')
        # table_data['minimum_rotated_rectangle_m2'] = table_data['minimum_rotated_rectangle_m2'].round(2)
        # table_data['mrr_ratio'] = table_data['mrr_ratio'].round(3)
        # Custom formatting for protruding reason
        def format_reasons(row):
            if pd.isna(row['reasons']):
                return row['reasons']
            reasons = str(row['reasons']).split(';')
            formatted = []
            for reason in reasons:
                r = reason.strip()
                if r == 'Plot is protruding':
                    formatted.append(f"Plot is protruding ({row['mrr_ratio']:.3f})")
                else:
                    formatted.append(r)
            return ";".join(formatted)
        table_data['reasons'] = table_data.apply(format_reasons, axis=1)
        
        # Display the table with custom column configuration
        st.dataframe(
            table_data.drop(columns=['mrr_ratio']).sort_values('reasons', ascending=False, na_position='last'),
            column_config={
                "plot_id": st.column_config.TextColumn(
                    "Plot ID",
                    width="medium",
                    help="Unique identifier for the plot"
                ),
                "enumerator_display": st.column_config.TextColumn(
                    "Enumerator",
                    width="medium",
                    help="Name of the enumerator who collected the data"
                ),
                "collection_date": st.column_config.TextColumn(
                    "Collection Date",
                    width="small",
                    help="Date when the plot was collected"
                ),
                "valid": st.column_config.TextColumn(
                    "Status",
                    width="small",
                    help="Validation status of the plot"
                ),
                "reasons": st.column_config.TextColumn(
                    "Validation Issues",
                    width="large",
                    help="Issues found during validation"
                ),
                "area_m2": st.column_config.NumberColumn(
                    "Area (m²)",
                    width="small",
                    help="Area of the plot in square meters",
                    format="%.2f"
                ),
                "subplot_count": st.column_config.NumberColumn(
                    "Sub-plots",
                    width="small",
                    help="Number of sub-plots in this plot",
                    format="%d"
                ),
                "valid_subplot_count": st.column_config.NumberColumn(
                    "Valid Sub-plots",
                    width="small",
                    help="Number of valid sub-plots in this plot",
                    format="%d"
                )
            },
            hide_index=True,
            use_container_width=True,
            height=400
        )
        
        # Add download button for the filtered data
        csv = filtered_plots_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Filtered Plots Data",
            csv,
            "filtered_plots.csv",
            "text/csv",
            key='download-filtered-plots-display'
        )
        
        # Add subplots data table
        st.write("### Subplots Data")
        
        # Add filters for the subplots table
        filter_col_status, filter_col_plot, filter_col_enum, filter_col_issue = st.columns(4)
        with filter_col_status:
            subplot_status_filter = st.selectbox(
                "Filter Subplots by Status",
                ["All", "Valid", "Invalid"],
                key="subplot_status_filter_display"
            )
        with filter_col_plot:
            subplot_plot_filter = st.selectbox(
                "Filter Subplots by Plot",
                ["All"] + sorted(df_subplots_filtered['plot_id'].unique().tolist()),
                key="subplot_plot_filter_display"
            )
        with filter_col_enum:
            subplot_enumerator_filter = st.selectbox(
                "Filter Subplots by Enumerator",
                ["All"] + sorted(df_subplots_filtered['enumerator_display'].unique().tolist()),
                key="subplot_enumerator_filter_display"
            )
        # Validation issues filter for subplots
        # Collect all unique issues (split by ';')
        subplot_issue_counts = {}
        for issues in df_subplots_filtered['reasons'].dropna():
            for issue in str(issues).split(';'):
                issue = issue.strip()
                if issue:
                    subplot_issue_counts[issue] = subplot_issue_counts.get(issue, 0) + 1
        all_subplot_issues = sorted(subplot_issue_counts.keys(), key=lambda k: subplot_issue_counts[k], reverse=True)
        subplot_issue_options = [f"{issue} ({subplot_issue_counts[issue]})" for issue in all_subplot_issues]
        with filter_col_issue:
            subplot_issue_filter = st.selectbox(
                "Filter Subplots by Validation Issue",
                ["All"] + subplot_issue_options,
                key="subplot_issue_filter_display"
            )
        
        # Filter the subplots data
        filtered_subplots_table = df_subplots_filtered.copy()
        if subplot_status_filter != "All":
            filtered_subplots_table = filtered_subplots_table[filtered_subplots_table['valid'] == (subplot_status_filter == "Valid")]
        if subplot_plot_filter != "All":
            filtered_subplots_table = filtered_subplots_table[filtered_subplots_table['plot_id'] == subplot_plot_filter]
        if subplot_enumerator_filter != "All":
            filtered_subplots_table = filtered_subplots_table[filtered_subplots_table['enumerator_display'] == subplot_enumerator_filter]
        if subplot_issue_filter != "All":
            selected_subplot_issue = subplot_issue_filter.split(" (")[0]  # Extract issue name from "Issue (count)" format
            filtered_subplots_table = filtered_subplots_table[filtered_subplots_table['reasons'].fillna('').apply(lambda x: any(selected_subplot_issue == issue.strip() for issue in str(x).split(';')))]
        
        # Prepare the subplots table data
        subplot_table_data = filtered_subplots_table[[
            'subplot_id',
            'plot_id',
            'enumerator_display',
            'collection_date',
            'valid',
            'reasons',
            'area_m2'
        ]].copy()
        
        # Format the subplots data for display
        subplot_table_data['valid'] = subplot_table_data['valid'].map({True: '✅ Valid', False: '❌ Invalid'})
        subplot_table_data['area_m2'] = subplot_table_data['area_m2'].round(2)
        subplot_table_data['collection_date'] = pd.to_datetime(subplot_table_data['collection_date']).dt.strftime('%Y-%m-%d')
        
        # Display the subplots table
        st.dataframe(
            subplot_table_data.sort_values('reasons', ascending=False, na_position='last'),
            column_config={
                "subplot_id": st.column_config.TextColumn(
                    "Subplot ID",
                    width="medium",
                    help="Unique identifier for the subplot"
                ),
                "plot_id": st.column_config.TextColumn(
                    "Plot ID",
                    width="medium",
                    help="ID of the parent plot"
                ),
                "enumerator_display": st.column_config.TextColumn(
                    "Enumerator",
                    width="medium",
                    help="Name of the enumerator who collected the data"
                ),
                "collection_date": st.column_config.TextColumn(
                    "Collection Date",
                    width="small",
                    help="Date when the subplot was collected"
                ),
                "valid": st.column_config.TextColumn(
                    "Status",
                    width="small",
                    help="Validation status of the subplot"
                ),
                "reasons": st.column_config.TextColumn(
                    "Validation Issues",
                    width="large",
                    help="Issues found during validation"
                ),
                "area_m2": st.column_config.NumberColumn(
                    "Area (m²)",
                    width="small",
                    help="Area of the subplot in square meters",
                    format="%.2f"
                )
            },
            hide_index=True,
            use_container_width=True,
            height=400
        )
        
        # Add download button for the filtered subplots data
        csv_subplots = filtered_subplots_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download Filtered Subplots Data",
            csv_subplots,
            "filtered_subplots.csv",
            "text/csv",
            key='download-filtered-subplots-display'
        )
        
        st.write(f"\nResults have been saved to: {output_dir}")
    
    # --- Selected Plots Explorer Tab ---
    if len(tabs) > 2:
        with tabs[2]:
            # st.subheader("Selected Plots Explorer")
            import requests
            # --- Plot selection dropdown ---
            selected_plot_ids = df_selected_plots['plot_id'].astype(str).tolist()
            plot_dropdown_options = [(pid, f"{pid} - {row['area_ha']:.2f} ha") for pid, row in df_selected_plots.set_index('plot_id').iterrows()]
            # Default selection logic
            if 'selected_explorer_plot_id' not in st.session_state:
                st.session_state.selected_explorer_plot_id = None
            # Build selectbox options: list of labels, with corresponding plot_id as value
            selectbox_labels = ["None"] + [label for _, label in plot_dropdown_options]
            selectbox_values = [None] + [pid for pid, _ in plot_dropdown_options]
            # Find the index of the current selection
            if st.session_state.selected_explorer_plot_id in selectbox_values:
                current_index = selectbox_values.index(st.session_state.selected_explorer_plot_id)
            else:
                current_index = 0
            selected_index = st.selectbox(
                "Select a plot to zoom and highlight",
                range(len(selectbox_labels)),
                format_func=lambda i: selectbox_labels[i],
                index=current_index,
                key="selected_explorer_plot_select"
            )
            selected_plot_id = selectbox_values[selected_index]
            st.session_state.selected_explorer_plot_id = selected_plot_id
            # Address input with suggestions
            address_query = st.text_input("Type an address (autocomplete from OSM)", key="address_query")
            suggestions = []
            if address_query and len(address_query) >= 3:
                try:
                    url = "https://nominatim.openstreetmap.org/search"
                    params = {
                        "q": address_query,
                        "format": "json",
                        "addressdetails": 1,
                        "limit": 5,
                    }
                    headers = {"User-Agent": "acorn-gt-app"}
                    resp = requests.get(url, params=params, headers=headers, timeout=5)
                    if resp.status_code == 200:
                        suggestions = resp.json()
                except Exception as e:
                    st.error(f"Error fetching address suggestions: {str(e)}")
            address_selected = None
            if suggestions:
                options = [f"{s['display_name']} ({s['lat']}, {s['lon']})" for s in suggestions]
                idx = st.selectbox("Select an address suggestion", options, key="address_suggestion")
                if options:
                    selected_idx = options.index(idx)
                    address_selected = suggestions[selected_idx]
            elif address_query:
                st.info("No suggestions found. Try a different address.")
            address_latlon = None
            if address_selected:
                address_latlon = (float(address_selected['lat']), float(address_selected['lon']))
                st.success(f"Address selected: {address_selected['display_name']} ({address_latlon[0]:.5f}, {address_latlon[1]:.5f})")
            # Compute distances if address is available
            df_selected_plots_display = df_selected_plots.copy()
            if address_latlon is not None:
                from geopy.distance import geodesic
                # Compute centroid for each plot geometry
                df_selected_plots_display['centroid'] = df_selected_plots_display.geometry.apply(lambda g: (g.centroid.y, g.centroid.x) if g is not None and not g.is_empty else (None, None))
                df_selected_plots_display['distance_km'] = df_selected_plots_display['centroid'].apply(
                    lambda c: geodesic(address_latlon, c).km if c[0] is not None and c[1] is not None else None
                )
                # --- OSMNX ROAD DISTANCE ---
                try:
                    import osmnx as ox
                    import networkx as nx
                    import pickle
                    import hashlib
                    # Determine bounding box for the network (buffer around address and plots)
                    buffer_m = 10000  # 10km
                    # Get all plot centroids
                    plot_coords = [c for c in df_selected_plots_display['centroid'] if c[0] is not None and c[1] is not None]
                    all_lats = [c[0] for c in plot_coords] + [address_latlon[0]]
                    all_lons = [c[1] for c in plot_coords] + [address_latlon[1]]
                    mean_lat = sum(all_lats) / len(all_lats)
                    mean_lon = sum(all_lons) / len(all_lons)
                    # Use a hash of the center and buffer for the filename
                    graph_dir = Path(".osmnx_graph_cache")
                    graph_dir.mkdir(exist_ok=True)
                    graph_id = hashlib.md5(f"{mean_lat:.5f}_{mean_lon:.5f}_{buffer_m}".encode()).hexdigest()
                    graph_path = graph_dir / f"road_graph_{graph_id}.graphml"
                    # Download or load the graph
                    with st.spinner("Loading road network graph (OSM)..."):
                        if graph_path.exists():
                            G = ox.load_graphml(graph_path)
                        else:
                            G = ox.graph_from_point((mean_lat, mean_lon), dist=buffer_m, network_type='drive')
                            ox.save_graphml(G, graph_path)
                    # Get the nearest node to the address
                    orig_node = ox.nearest_nodes(G, address_latlon[1], address_latlon[0])
                    # Compute road distance for each plot
                    def get_road_distance_km(lat, lon):
                        try:
                            dest_node = ox.nearest_nodes(G, lon, lat)
                            length = nx.shortest_path_length(G, orig_node, dest_node, weight='length')
                            return length / 1000  # meters to km
                        except Exception:
                            return None
                    with st.spinner("Calculating road distances to each plot..."):
                        df_selected_plots_display['road_distance_km'] = df_selected_plots_display['centroid'].apply(
                            lambda c: get_road_distance_km(c[0], c[1]) if c[0] is not None and c[1] is not None else None
                        )
                except ImportError:
                    st.error("osmnx and networkx are required for road network distance calculation. Please install them with 'pip install osmnx networkx'.")
                except Exception as e:
                    st.error(f"Error calculating road distances: {str(e)}")
            # Table display
            table_cols = ['plot_id', 'area_ha']
            # Only include NDVI, slope, and distance columns if present
            for col in ['mean_ndvi', 'mean_slope', 'distance_km', 'road_distance_km']:
                if col in df_selected_plots_display.columns and col not in table_cols:
                    table_cols.append(col)
            st.dataframe(
                df_selected_plots_display[table_cols].sort_values('road_distance_km' if 'road_distance_km' in table_cols else 'distance_km' if 'distance_km' in table_cols else 'plot_id'),
                column_config={
                    "plot_id": st.column_config.TextColumn("Plot ID", width="medium"),
                    "area_ha": st.column_config.NumberColumn("Area (ha)", width="small", format="%.2f"),
                    **({"mean_ndvi": st.column_config.NumberColumn("Mean NDVI", width="small", format="%.3f")} if 'mean_ndvi' in table_cols else {}),
                    **({"mean_slope": st.column_config.NumberColumn("Mean Slope", width="small", format="%.2f")} if 'mean_slope' in table_cols else {}),
                    **({"distance_km": st.column_config.NumberColumn("Crow Flies (km)", width="small", format="%.2f")} if 'distance_km' in table_cols else {}),
                    **({"road_distance_km": st.column_config.NumberColumn("Road Distance (km)", width="small", format="%.2f")} if 'road_distance_km' in table_cols else {})
                },
                hide_index=True,
                use_container_width=True,
                height=400
            )
            # Map display
            st.write("### Map of Sampled Plots")
            import folium
            from streamlit_folium import folium_static
            # Add radio button for NDVI/Slope layer selection
            layer_choice = None
            if 'mean_ndvi' in df_selected_plots_display.columns and 'mean_slope' in df_selected_plots_display.columns:
                layer_choice = st.radio("Select map layer:", ["NDVI", "Slope"], horizontal=True)
            elif 'mean_ndvi' in df_selected_plots_display.columns:
                layer_choice = "NDVI"
            elif 'mean_slope' in df_selected_plots_display.columns:
                layer_choice = "Slope"
            else:
                layer_choice = None
            # Center map on address if available, else on selected plot, else on selected plots
            if address_latlon is not None:
                map_center = address_latlon
                zoom_start = 14
            elif selected_plot_id is not None:
                # Center on selected plot
                selected_plot_row = df_selected_plots_display[df_selected_plots_display['plot_id'].astype(str) == str(selected_plot_id)]
                if not selected_plot_row.empty:
                    geom = selected_plot_row.iloc[0].geometry
                    try:
                        centroid = geom.centroid
                        map_center = (centroid.y, centroid.x)
                        zoom_start = 16
                    except Exception as e:
                        map_center = (0, 0)
                        zoom_start = 2
                else:
                    map_center = (0, 0)
                    zoom_start = 2
            else:
                # Use centroid of all selected plots
                if not df_selected_plots_display.empty:
                    try:
                        valid_geoms = df_selected_plots_display[~df_selected_plots_display.geometry.isna() & ~df_selected_plots_display.geometry.is_empty]
                        if not valid_geoms.empty:
                            mean_lat = valid_geoms.geometry.centroid.y.mean()
                            mean_lon = valid_geoms.geometry.centroid.x.mean()
                            map_center = (mean_lat, mean_lon)
                            zoom_start = 14
                        else:
                            map_center = (0, 0)
                            zoom_start = 2
                    except Exception:
                        map_center = (0, 0)
                        zoom_start = 2
                else:
                    map_center = (0, 0)
                    zoom_start = 2
            m = folium.Map(location=map_center, zoom_start=zoom_start, tiles=None)
            # Add address marker if available
            if address_latlon is not None:
                folium.Marker(address_latlon, popup="Input Address", icon=folium.Icon(color='red', icon='home')).add_to(m)
            # Add selected plots (default layer, always visible)
            if not df_selected_plots_display.empty:
                def style_function(x):
                    pid = str(x['properties'].get('plot_id', ''))
                    if selected_plot_id is not None and pid == str(selected_plot_id):
                        return {
                            'fillColor': 'yellow',
                            'color': 'yellow',
                            'weight': 5,
                            'fillOpacity': 0.7,
                            'opacity': 1.0
                        }
                    else:
                        return {
                            'fillColor': 'purple',
                            'color': 'purple',
                            'weight': 3,
                            'fillOpacity': 0.4,
                            'opacity': 0.8
                        }
                folium.GeoJson(
                    df_selected_plots_display,
                    name='Selected Plots',
                    style_function=style_function,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_ndvi', 'mean_slope'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_ndvi', 'mean_slope'], ['Plot ID:', 'Area (ha):', 'Mean NDVI:', 'Mean Slope:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_ndvi', 'mean_slope'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_ndvi', 'mean_slope'], ['Plot ID:', 'Area (ha):', 'Mean NDVI:', 'Mean Slope:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    )
                ).add_to(m)
            # Add only the selected layer (NDVI or Slope)
            import numpy as np
            legend_html = '''
             <div style="
             position: absolute; 
             z-index:9999; 
             background-color:white; 
             padding: 10px; 
             border-radius: 5px; 
             border: 1px solid #888; 
             box-shadow: 0 0 15px rgba(0,0,0,0.2); 
             font-size: 14px;
             left: 10px; 
             bottom: 40px;
             ">
             <b>{title} Legend</b><br>
             <div style="height: 20px; width: 120px; background: linear-gradient(to right, {gradient});"></div>
             <span style="float:left;">Low</span><span style="float:right;">High</span>
             </div>
            '''
            if layer_choice == "NDVI" and 'mean_ndvi' in df_selected_plots_display.columns:
                ndvi_min = df_selected_plots_display['mean_ndvi'].min()
                ndvi_max = df_selected_plots_display['mean_ndvi'].max()
                def ndvi_color(val):
                    if np.isnan(val):
                        return '#cccccc'
                    t = 0 if ndvi_max == ndvi_min else (val - ndvi_min) / (ndvi_max - ndvi_min)
                    r = int(229 + (0-229)*t)
                    g = int(245 + (109-245)*t)
                    b = int(224 + (44-224)*t)
                    return f'#{r:02x}{g:02x}{b:02x}'
                folium.GeoJson(
                    df_selected_plots_display,
                    name='NDVI',
                    style_function=lambda x: {
                        'fillColor': ndvi_color(x['properties'].get('mean_ndvi', np.nan)),
                        'color': ndvi_color(x['properties'].get('mean_ndvi', np.nan)),
                        'weight': 3,
                        'fillOpacity': 0.7,
                        'opacity': 0.9
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_ndvi'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_ndvi'], ['Plot ID:', 'Area (ha):', 'Mean NDVI:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_ndvi'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_ndvi'], ['Plot ID:', 'Area (ha):', 'Mean NDVI:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    )
                ).add_to(m)
                # Add NDVI legend (robust)
                m.get_root().html.add_child(folium.Element(
                    legend_html.format(title="NDVI", gradient="#e5f5e0, #006d2c")
                ))
            elif layer_choice == "Slope" and 'mean_slope' in df_selected_plots_display.columns:
                slope_min = df_selected_plots_display['mean_slope'].min()
                slope_max = df_selected_plots_display['mean_slope'].max()
                def slope_color(val):
                    if np.isnan(val):
                        return '#cccccc'
                    t = 0 if slope_max == slope_min else (val - slope_min) / (slope_max - slope_min)
                    r = int(247 + (128-247)*t)
                    g = int(230 + (0-230)*t)
                    b = int(230 + (0-230)*t)
                    return f'#{r:02x}{g:02x}{b:02x}'
                folium.GeoJson(
                    df_selected_plots_display,
                    name='Slope',
                    style_function=lambda x: {
                        'fillColor': slope_color(x['properties'].get('mean_slope', np.nan)),
                        'color': slope_color(x['properties'].get('mean_slope', np.nan)),
                        'weight': 3,
                        'fillOpacity': 0.7,
                        'opacity': 0.9
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_slope'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_slope'], ['Plot ID:', 'Area (ha):', 'Mean Slope:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    ),
                    popup=folium.GeoJsonPopup(
                        fields=[f for f in ['plot_id', 'area_ha', 'mean_slope'] if f in df_selected_plots_display.columns],
                        aliases=[a for f, a in zip(['plot_id', 'area_ha', 'mean_slope'], ['Plot ID:', 'Area (ha):', 'Mean Slope:']) if f in df_selected_plots_display.columns],
                        style=("background-color: white; color: #333333; font-family: arial; font-size: 12px; padding: 10px;")
                    )
                ).add_to(m)
                # Add Slope legend (robust)
                m.get_root().html.add_child(folium.Element(
                    legend_html.format(title="Slope", gradient="#f7e6e6, #800000")
                ))
            # Add OSM, Esri Terrain, Esri Satellite, and Hybrid (labels overlay) basemap layers
            folium.TileLayer('OpenStreetMap', name='OSM').add_to(m)
            # Esri Terrain (Hillshade)
            folium.TileLayer(
                tiles='https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}',
                name='Terrain (Esri)',
                attr='Tiles © Esri — Source: Esri, USGS, NOAA'
            ).add_to(m)
            # Esri Satellite Imagery
            folium.TileLayer(
                tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                name='Satellite',
                attr='Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community'
            ).add_to(m)
            # Esri Labels overlay (Hybrid)
            folium.TileLayer(
                tiles='https://services.arcgisonline.com/arcgis/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
                name='Labels (Hybrid)',
                attr='Labels © Esri',
                overlay=True,
                control=True
            ).add_to(m)
            folium.LayerControl().add_to(m)
            folium_static(m, width=1000, height=600)

# --- Country ISO3 Dropdown (at the top of the app) ---
country_json_path = "country_dropdown_options.json"
if os.path.exists(country_json_path):
    with open(country_json_path, "r", encoding="utf-8") as f:
        country_options = json.load(f)
    country_options = sorted(country_options, key=lambda x: x["name"])
    name_to_iso3 = {item["name"]: item["iso3"] for item in country_options}
    country_names = [item["name"] for item in country_options]
    # selected_country_name = st.selectbox(
    #     "Select country (sets COUNTRY_ISO3 for this session)",
    #     country_names,
    #     key="country_select_dropdown"
    # )
    # selected_iso3 = name_to_iso3[selected_country_name]
    # st.session_state["COUNTRY_ISO3"] = selected_iso3
    # st.info(f"Selected country: {selected_country_name} (ISO3: {selected_iso3})")
else:
    st.warning("country_dropdown_options.json not found. Please generate it first.")