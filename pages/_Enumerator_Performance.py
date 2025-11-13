"""
Enumerator Performance Analysis - Error-focused quality control
Enhanced with: Interactive maps (Folium), PDF export, GeoJSON export
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
from io import BytesIO
import config
from ui.components import show_header, show_sidebar_info

# Try to import folium (optional for maps)
try:
    import folium
    from folium.plugins import Fullscreen, MiniMap

    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

# Try to import matplotlib (optional for polygon visualizations in PDF)
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None

# Page config
st.set_page_config(
    page_title="Enumerator Performance - Ground Truth DQM",
    page_icon="👥",
    layout="wide",
)

# Refresh partner config from URL
config.refresh_partner_config()

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

# Show sidebar info
show_sidebar_info()

# Add date filter to sidebar
st.sidebar.markdown("---")
st.sidebar.markdown("## 🔍 Filters")

date_col = None
date_filtered_gdf = gdf_subplots.copy()

# Try to find date column
if "starttime" in gdf_subplots.columns:
    date_col = "starttime"
elif "SubmissionDate" in gdf_subplots.columns:
    date_col = "SubmissionDate"
elif raw_data and "plots_subplots" in raw_data:
    # Try to add date from raw_data
    plots_df = raw_data["plots_subplots"]

    # Check for date column with different case variations
    submission_date_col = None
    for col in plots_df.columns:
        if "submissiondate" in col.lower() and "subplot" in col.lower():
            submission_date_col = col
            break
    if not submission_date_col:
        for col in plots_df.columns:
            if "submissiondate" in col.lower():
                submission_date_col = col
                break
    if not submission_date_col:
        for col in plots_df.columns:
            if "starttime" in col.lower():
                submission_date_col = col
                break

    # Merge the date column if found
    if submission_date_col and "subplot_id" in gdf_subplots.columns and "SUBPLOT_KEY" in plots_df.columns:
        date_merge = plots_df[["SUBPLOT_KEY", submission_date_col]].drop_duplicates()

        # Drop SUBPLOT_KEY if it already exists to avoid duplicate column issues
        if "SUBPLOT_KEY" in gdf_subplots.columns:
            gdf_subplots = gdf_subplots.drop(columns=["SUBPLOT_KEY"])

        date_filtered_gdf = gdf_subplots.merge(
            date_merge,
            left_on="subplot_id",
            right_on="SUBPLOT_KEY",
            how="left",
            suffixes=('', '_drop')
        )

        # Drop any columns with '_drop' suffix
        drop_cols = [col for col in date_filtered_gdf.columns if col.endswith('_drop')]
        if drop_cols:
            date_filtered_gdf = date_filtered_gdf.drop(columns=drop_cols)

        date_col = submission_date_col

if date_col:
    from datetime import date as date_class

    # Convert to datetime
    date_filtered_gdf[date_col] = pd.to_datetime(date_filtered_gdf[date_col], errors='coerce')

    # Filter out rows with invalid dates
    valid_dates = date_filtered_gdf[date_col].notna()

    if valid_dates.sum() > 0:
        # Get min/max dates from valid dates only
        min_date = date_filtered_gdf.loc[valid_dates, date_col].min().date()
        max_date = date_filtered_gdf.loc[valid_dates, date_col].max().date()
        today = date_class.today()

        # Default to today if today is within range, otherwise use max_date
        default_end_date = today if min_date <= today <= max_date else max_date

        date_range = st.sidebar.date_input(
            "📅 Date Range",
            value=(min_date, default_end_date),
            min_value=min_date,
            max_value=max_date,
            help="Filter data by submission date. Defaults to today.",
            key="enumerator_perf_date_filter",
        )

        # Apply date filter if both dates selected
        if len(date_range) == 2:
            start_date, end_date = date_range
            mask = (
                (date_filtered_gdf[date_col].dt.date >= start_date) &
                (date_filtered_gdf[date_col].dt.date <= end_date)
            )
            gdf_subplots = date_filtered_gdf[mask].copy()

            # Remove the temporary date column if we added it
            if date_col not in st.session_state.data["subplots"].columns:
                if date_col in gdf_subplots.columns:
                    gdf_subplots = gdf_subplots.drop(columns=[date_col])
                if "SUBPLOT_KEY" in gdf_subplots.columns and "SUBPLOT_KEY" not in st.session_state.data["subplots"].columns:
                    gdf_subplots = gdf_subplots.drop(columns=["SUBPLOT_KEY"])
        else:
            gdf_subplots = date_filtered_gdf.copy()
    else:
        st.sidebar.info(f"ℹ️ No valid dates found in {date_col}")
else:
    st.sidebar.info("ℹ️ Date filtering not available")

# Check if vegetation data available
has_vegetation = "plots_subplots_vegetation" in raw_data
has_measurements = "plots_subplots_vegetation_measurements" in raw_data

st.markdown("---")

# ============================================
# HELPER FUNCTIONS
# ============================================


def create_enumerator_map(enum_data, enumerator_name):
    """
    Create enhanced interactive map showing all subplots for an enumerator
    Similar to Map View page - with detailed popups and styling
    """
    try:
        import folium
        from folium.plugins import Fullscreen, MiniMap

        if len(enum_data) == 0 or "geometry" not in enum_data.columns:
            return None

        # Filter out empty geometries
        map_data = enum_data[~enum_data.geometry.is_empty].copy()

        if len(map_data) == 0:
            return None

        # Calculate map center
        bounds = map_data.total_bounds
        center_lat = (bounds[1] + bounds[3]) / 2
        center_lon = (bounds[0] + bounds[2]) / 2

        # Create map
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=13,
            tiles="OpenStreetMap",
        )

        # Add additional tile layers
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri",
            name="Satellite",
        ).add_to(m)
        folium.TileLayer("CartoDB positron", name="Light").add_to(m)

        # Create feature groups
        valid_group = folium.FeatureGroup(name="✅ Valid Subplots", show=True)
        invalid_group = folium.FeatureGroup(name="❌ Invalid Subplots", show=True)

        # Add subplots to map
        for idx, row in map_data.iterrows():
            if row.geometry.is_empty:
                continue

            # Get coordinates
            coords = list(row.geometry.exterior.coords)
            coords_latlon = [(lat, lon) for lon, lat in coords]

            # Create detailed popup HTML
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
                        <td style="padding: 4px; font-weight: bold;">Enumerator:</td>
                        <td style="padding: 4px;">{row.get('enumerator', 'N/A')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px; font-weight: bold;">Area:</td>
                        <td style="padding: 4px;">{row.get('area_m2', 0):.1f} m²</td>
                    </tr>
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 4px; font-weight: bold;">Vertices:</td>
                        <td style="padding: 4px;">{row.get('nr_vertices', 0)}</td>
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
                fill_color = "#81C784"
                group = valid_group
                weight = 2
                opacity = 0.8
                fill_opacity = 0.3
            else:
                color = "#F44336"  # Red
                fill_color = "#E57373"
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
        Fullscreen(position="topleft").add_to(m)

        # Add minimap
        MiniMap(toggle_display=True, position="bottomleft").add_to(m)

        # Add statistics box
        valid_count = map_data["geom_valid"].sum()
        invalid_count = (~map_data["geom_valid"]).sum()
        valid_pct = (valid_count / len(map_data) * 100) if len(map_data) > 0 else 0

        stats_html = f"""
        <div style="position: fixed; 
                    top: 10px; right: 10px; 
                    width: 220px; 
                    background-color: white; 
                    border: 2px solid #2E7D32; 
                    border-radius: 8px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
                    z-index: 1000; 
                    padding: 15px;
                    font-family: Arial, sans-serif;">
            <h4 style="margin: 0 0 10px 0; color: #2E7D32; border-bottom: 2px solid #2E7D32; padding-bottom: 5px;">
                📊 {enumerator_name}
            </h4>
            <div style="font-size: 14px; line-height: 1.8;">
                <b>Total Subplots:</b> {len(map_data)}<br>
                <b style="color: #4CAF50;">✅ Valid:</b> {valid_count}<br>
                <b style="color: #F44336;">❌ Invalid:</b> {invalid_count}<br>
                <b>📈 Valid %:</b> {valid_pct:.1f}%
            </div>
        </div>
        """

        m.get_root().html.add_child(folium.Element(stats_html))

        return m

    except ImportError:
        # Folium not available, return None
        return None


def capture_map_as_image(enum_data, enumerator_name):
    """
    Capture Folium map as a static image for PDF
    Returns PIL Image or None
    """
    try:
        import folium
        from PIL import Image, ImageDraw, ImageFont
        from io import BytesIO
        import geopandas as gpd
        from shapely.geometry import box

        # Create the map
        map_obj = create_enumerator_map(enum_data, enumerator_name)
        if not map_obj:
            return None

        # Try different screenshot methods in order of preference
        screenshot_bytes = None

        # METHOD 1: html2image (easiest - automatically uses Chrome)
        try:
            from html2image import Html2Image
            import tempfile
            import os

            # Save map to temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                map_obj.save(f.name)
                temp_html = f.name

            # Create output directory
            temp_dir = tempfile.gettempdir()
            output_file = 'folium_map_snapshot.png'

            # Initialize Html2Image
            hti = Html2Image(output_path=temp_dir)

            # Capture screenshot
            hti.screenshot(
                html_file=temp_html,
                save_as=output_file,
                size=(1200, 800)
            )

            # Read the generated image
            output_path = os.path.join(temp_dir, output_file)
            if os.path.exists(output_path):
                img = Image.open(output_path)
                img_copy = img.copy()  # Make a copy before closing
                img.close()

                # Clean up temporary files
                os.unlink(temp_html)
                os.unlink(output_path)

                return img_copy

        except Exception as e:
            # Clean up on error
            try:
                if 'temp_html' in locals() and os.path.exists(temp_html):
                    os.unlink(temp_html)
                if 'output_path' in locals() and os.path.exists(output_path):
                    os.unlink(output_path)
            except:
                pass

        # METHOD 2: Try selenium (fallback if html2image not available)
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            import tempfile
            import time
            import os

            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1200,800")

            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                map_obj.save(f.name)
                temp_file = f.name

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(f'file://{temp_file}')
            time.sleep(2)
            screenshot_bytes = driver.get_screenshot_as_png()
            driver.quit()

            os.unlink(temp_file)

            if screenshot_bytes:
                img = Image.open(BytesIO(screenshot_bytes))
                return img

        except Exception:
            pass

        # METHOD 3: Matplotlib-based geographic visualization
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            from matplotlib.patches import Polygon
            import numpy as np

            # Filter valid geometries
            map_data = enum_data[~enum_data.geometry.is_empty].copy()
            if len(map_data) == 0:
                return None

            # Count valid/invalid
            valid_count = map_data["geom_valid"].sum()
            invalid_count = (~map_data["geom_valid"]).sum()
            total_count = len(map_data)

            # Create figure with high DPI for quality
            fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
            fig.patch.set_facecolor('white')

            # Extract coordinates for valid and invalid subplots
            valid_data = map_data[map_data["geom_valid"]]
            invalid_data = map_data[~map_data["geom_valid"]]

            # Plot subplot polygons or points
            for idx, row in valid_data.iterrows():
                geom = row['geometry']
                if geom.geom_type == 'Polygon':
                    # Plot polygon outline
                    x, y = geom.exterior.xy
                    ax.fill(x, y, color='#4CAF50', alpha=0.3, edgecolor='#2E7D32', linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(centroid.x, centroid.y, 'o', color='#2E7D32', markersize=8, markeredgecolor='white', markeredgewidth=1)
                else:
                    centroid = geom.centroid
                    ax.plot(centroid.x, centroid.y, 'o', color='#4CAF50', markersize=10, markeredgecolor='white', markeredgewidth=2)

            for idx, row in invalid_data.iterrows():
                geom = row['geometry']
                if geom.geom_type == 'Polygon':
                    # Plot polygon outline
                    x, y = geom.exterior.xy
                    ax.fill(x, y, color='#F44336', alpha=0.3, edgecolor='#C62828', linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(centroid.x, centroid.y, 'o', color='#C62828', markersize=8, markeredgecolor='white', markeredgewidth=1)
                else:
                    centroid = geom.centroid
                    ax.plot(centroid.x, centroid.y, 'o', color='#F44336', markersize=10, markeredgecolor='white', markeredgewidth=2)

            # Set title
            ax.set_title(f'Geographic Distribution - {enumerator_name}',
                        fontsize=18, fontweight='bold', color='#1565C0', pad=20)

            # Set labels
            ax.set_xlabel('Longitude', fontsize=12, fontweight='bold')
            ax.set_ylabel('Latitude', fontsize=12, fontweight='bold')

            # Add grid
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.set_axisbelow(True)

            # Equal aspect ratio for proper geographic display
            ax.set_aspect('equal', adjustable='box')

            # Add legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#4CAF50', edgecolor='#2E7D32', label=f'Valid Subplots ({valid_count})'),
                Patch(facecolor='#F44336', edgecolor='#C62828', label=f'Invalid Subplots ({invalid_count})')
            ]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=11, framealpha=0.95)

            # Add statistics text box
            success_rate = (valid_count / total_count * 100) if total_count > 0 else 0

            stats_text = f"Total Subplots: {total_count}\n"
            stats_text += f"Valid: {valid_count} ({success_rate:.1f}%)\n"
            stats_text += f"Invalid: {invalid_count} ({100-success_rate:.1f}%)"

            # Position text box in lower left
            ax.text(0.02, 0.02, stats_text,
                   transform=ax.transAxes,
                   fontsize=10,
                   verticalalignment='bottom',
                   bbox=dict(boxstyle='round', facecolor='white', edgecolor='#1565C0', linewidth=2, alpha=0.95))

            # Tight layout
            plt.tight_layout()

            # Convert to PIL Image
            buf = BytesIO()
            plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
            buf.seek(0)
            img = Image.open(buf)
            plt.close(fig)

            return img

        except Exception as e:
            # Fallback to PIL-only version if matplotlib fails
            try:
                from PIL import Image, ImageDraw, ImageFont

                # Filter valid geometries
                map_data = enum_data[~enum_data.geometry.is_empty].copy()
                if len(map_data) == 0:
                    return None

                # Count valid/invalid
                valid_count = map_data["geom_valid"].sum()
                invalid_count = (~map_data["geom_valid"]).sum()
                total_count = len(map_data)

                # Create simple statistics graphic
                width, height = 800, 600
                img = Image.new('RGB', (width, height), color='#F5F5F5')
                draw = ImageDraw.Draw(img)

                # Load fonts
                try:
                    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
                    text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
                except:
                    title_font = ImageFont.load_default()
                    text_font = ImageFont.load_default()

                # Draw title
                title = f"Subplot Distribution - {enumerator_name}"
                title_bbox = draw.textbbox((0, 0), title, font=title_font)
                title_width = title_bbox[2] - title_bbox[0]
                draw.text(((width - title_width) // 2, 40), title, fill='#1565C0', font=title_font)

                # Draw statistics box
                box_y = 120
                box_height = 350
                draw.rectangle([100, box_y, width-100, box_y+box_height], fill='white', outline='#1565C0', width=3)

                # Draw statistics
                y_pos = box_y + 60

                # Total subplots
                draw.text((width//2 - 150, y_pos), f"Total Subplots:", fill='#333333', font=text_font)
                draw.text((width//2 + 50, y_pos), f"{total_count}", fill='#1565C0', font=text_font)
                y_pos += 80

                # Valid subplots (green)
                draw.rectangle([width//2 - 180, y_pos-5, width//2 - 160, y_pos+20], fill='#4CAF50')
                draw.text((width//2 - 150, y_pos), f"Valid Subplots:", fill='#333333', font=text_font)
                draw.text((width//2 + 50, y_pos), f"{valid_count}", fill='#4CAF50', font=text_font)
                y_pos += 80

                # Invalid subplots (red)
                draw.rectangle([width//2 - 180, y_pos-5, width//2 - 160, y_pos+20], fill='#F44336')
                draw.text((width//2 - 150, y_pos), f"Invalid Subplots:", fill='#333333', font=text_font)
                draw.text((width//2 + 50, y_pos), f"{invalid_count}", fill='#F44336', font=text_font)
                y_pos += 80

                # Success rate
                success_rate = (valid_count / total_count * 100) if total_count > 0 else 0
                draw.text((width//2 - 150, y_pos), f"Success Rate:", fill='#333333', font=text_font)
                color = '#4CAF50' if success_rate >= 85 else '#F44336'
                draw.text((width//2 + 50, y_pos), f"{success_rate:.1f}%", fill=color, font=text_font)

                return img

            except Exception:
                return None

    except Exception:
        return None


def create_subplot_polygon_image(subplot_row):
    """
    Create an image of a single subplot polygon with matplotlib
    Returns PIL Image or None
    """
    import sys
    try:
        import matplotlib
        matplotlib.use('Agg')  # Use non-interactive backend
        import matplotlib.pyplot as plt
        from PIL import Image
        from io import BytesIO

        subplot_id = subplot_row.get('subplot_id', 'Unknown')
        print(f"DEBUG POLYGON: Starting for subplot {subplot_id}", file=sys.stderr)
        print(f"DEBUG POLYGON: Has geometry column: {'geometry' in subplot_row}", file=sys.stderr)

        if "geometry" not in subplot_row or subplot_row.get("geometry") is None:
            print(f"DEBUG POLYGON: No geometry column or None for subplot {subplot_id}", file=sys.stderr)
            return None

        if pd.isna(subplot_row.get("geometry")):
            print(f"DEBUG POLYGON: Geometry is NaN for subplot {subplot_id}", file=sys.stderr)
            return None

        geom = subplot_row["geometry"]

        if geom.is_empty:
            print(f"DEBUG POLYGON: Geometry is empty for subplot {subplot_id}", file=sys.stderr)
            return None

        is_valid = subplot_row.get("geom_valid", False)

        print(f"DEBUG POLYGON: Creating polygon image for subplot {subplot_id}, geom_type: {geom.geom_type}, valid: {is_valid}", file=sys.stderr)

        # Create figure
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)

        # Plot the polygon
        if geom.geom_type == 'Polygon':
            x, y = geom.exterior.xy
            color = '#F44336' if not is_valid else '#4CAF50'
            ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
            ax.plot(x, y, 'o', color=color, markersize=4)

            # Add centroid
            centroid = geom.centroid
            ax.plot(centroid.x, centroid.y, 'x', color='black', markersize=8, markeredgewidth=2)

        # Formatting
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_xlabel('Longitude', fontsize=8)
        ax.set_ylabel('Latitude', fontsize=8)
        ax.tick_params(labelsize=7)

        # Title
        subplot_id = str(subplot_row.get('subplot_id', 'Unknown'))
        if len(subplot_id) > 35:
            subplot_id = subplot_id[:32] + '...'
        status = "INVALID" if not is_valid else "VALID"
        ax.set_title(f"{subplot_id}\n{status}", fontsize=9, fontweight='bold')

        # Add area and vertices info
        info_text = []
        if 'area_m2' in subplot_row and pd.notna(subplot_row['area_m2']):
            info_text.append(f"Area: {subplot_row['area_m2']:.1f} m²")
        if 'nr_vertices' in subplot_row and pd.notna(subplot_row['nr_vertices']):
            info_text.append(f"Vertices: {int(subplot_row['nr_vertices'])}")

        if info_text:
            ax.text(0.5, -0.15, ' | '.join(info_text),
                   transform=ax.transAxes, ha='center', fontsize=7, style='italic')

        plt.tight_layout()

        # Convert to PIL Image
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        buf.seek(0)

        # Create a copy of the image before the buffer is closed
        img = Image.open(buf)
        img_copy = img.copy()
        img.close()

        print(f"DEBUG: Successfully created polygon image", file=sys.stderr)
        return img_copy

    except Exception as e:
        print(f"DEBUG: Error creating polygon image: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return None


def generate_enhanced_pdf_report(enum_data, enumerator_name, partner_name, raw_data=None):
    """
    Generate comprehensive PDF report for enumerator with charts, analysis, and map
    """
    try:
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
            PageBreak,
            Image as RLImage,
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.piecharts import Pie
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from datetime import datetime
        from io import BytesIO

        import sys

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        story = []
        styles = getSampleStyleSheet()

        # CRITICAL: Add SubmissionDate to enum_data if missing (needed for date-wise analysis)
        if "SubmissionDate" not in enum_data.columns and raw_data and "plots_subplots" in raw_data:
            print(f"DEBUG PDF: Adding SubmissionDate from raw_data", file=sys.stderr)
            plots_df = raw_data["plots_subplots"]
            print(f"DEBUG PDF: plots_df columns: {plots_df.columns.tolist()}", file=sys.stderr)
            print(f"DEBUG PDF: enum_data columns: {enum_data.columns.tolist()}", file=sys.stderr)

            # Check for SubmissionDate with different case variations (prefer subplot level)
            submission_date_col = None
            # First try to find subplot-specific date
            for col in plots_df.columns:
                if "submissiondate" in col.lower() and "subplot" in col.lower():
                    submission_date_col = col
                    break
            # If not found, try any submissiondate column
            if not submission_date_col:
                for col in plots_df.columns:
                    if "submissiondate" in col.lower():
                        submission_date_col = col
                        break

            # Check for subplot key column
            subplot_key_col = None
            for col in plots_df.columns:
                if "subplot" in col.lower() and "key" in col.lower():
                    subplot_key_col = col
                    break

            print(f"DEBUG PDF: Found submission_date_col: {submission_date_col}, subplot_key_col: {subplot_key_col}", file=sys.stderr)

            if submission_date_col and subplot_key_col:
                # Create mapping from subplot_id to SubmissionDate
                date_mapping = plots_df[[subplot_key_col, submission_date_col]].drop_duplicates()
                date_mapping = date_mapping.rename(columns={submission_date_col: "SubmissionDate"})

                # Drop subplot_key_col from enum_data if it exists to avoid duplicate column issues
                if subplot_key_col in enum_data.columns and subplot_key_col != "subplot_id":
                    enum_data = enum_data.drop(columns=[subplot_key_col])

                # Merge into enum_data
                enum_data = enum_data.merge(
                    date_mapping,
                    left_on="subplot_id",
                    right_on=subplot_key_col,
                    how="left",
                    suffixes=('', '_drop')
                )

                # Drop duplicate subplot key column if it was added
                if subplot_key_col in enum_data.columns and subplot_key_col != "subplot_id":
                    enum_data = enum_data.drop(columns=[subplot_key_col])

                # Drop any columns with '_drop' suffix that may have been created
                drop_cols = [col for col in enum_data.columns if col.endswith('_drop')]
                if drop_cols:
                    enum_data = enum_data.drop(columns=drop_cols)

                print(f"DEBUG PDF: Added SubmissionDate, now has {enum_data['SubmissionDate'].notna().sum()} dates", file=sys.stderr)
            else:
                print(f"DEBUG PDF: Could not find required columns in plots_df", file=sys.stderr)
        else:
            if "SubmissionDate" in enum_data.columns:
                print(f"DEBUG PDF: SubmissionDate already in enum_data", file=sys.stderr)
            else:
                print(f"DEBUG PDF: No raw_data or plots_subplots available to add SubmissionDate", file=sys.stderr)

        # Custom styles
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=26,
            textColor=colors.HexColor("#1565C0"),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        )

        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Heading2"],
            fontSize=16,
            textColor=colors.HexColor("#1565C0"),
            spaceBefore=20,
            spaceAfter=12,
            fontName="Helvetica-Bold",
        )

        # Cover page
        story.append(Spacer(1, 1.5 * inch))
        story.append(Paragraph("ENUMERATOR PERFORMANCE REPORT", title_style))
        story.append(Spacer(1, 0.2 * inch))

        info_data = [
            ["Enumerator:", f"<b>{enumerator_name}</b>"],
            ["Partner:", partner_name],
            ["Generated:", datetime.now().strftime("%B %d, %Y at %H:%M")],
        ]

        info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
        info_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E3F2FD")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1565C0")),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("PADDING", (0, 0), (-1, -1), 12),
                    ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#1565C0")),
                ]
            )
        )

        story.append(info_table)
        story.append(PageBreak())

        # Get vegetation and measurement data for vegetation errors (MOVED HERE for summary)
        import sys
        veg_errors_data = {}
        total_veg_errors = 0
        species_col = None  # Initialize species_col for later use
        if raw_data:
            # Get vegetation data for this enumerator
            print(f"DEBUG: raw_data keys: {raw_data.keys()}", file=sys.stderr)
            if "plots_subplots_vegetation_measurements" in raw_data:
                try:
                    from utils.vegetation_validation import (
                        detect_height_outliers,
                        detect_circumference_outliers,
                        detect_suspicious_circumference_by_age,
                    )
                    from utils.data_merge_utils import (
                        merge_with_enumerator,
                        get_species_column,
                    )

                    # Get measurements data
                    meas_df = raw_data["plots_subplots_vegetation_measurements"]
                    print(f"DEBUG: Total measurement records: {len(meas_df)}", file=sys.stderr)

                    # Filter to this enumerator's data by merging with subplot data
                    if "SUBPLOT_KEY" in meas_df.columns:
                        enum_subplot_keys = enum_data["subplot_id"].unique()
                        print(f"DEBUG: Enumerator subplot keys count: {len(enum_subplot_keys)}", file=sys.stderr)
                        meas_enum = meas_df[meas_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()
                        print(f"DEBUG: Filtered measurement records: {len(meas_enum)}", file=sys.stderr)

                        if len(meas_enum) > 0:
                            # Merge with subplot comments BEFORE other merges
                            if "plots_subplots_vegetation" in raw_data:
                                veg_data_for_comments = raw_data["plots_subplots_vegetation"]
                                if len(veg_data_for_comments) > 0 and "SUBPLOT_KEY" in veg_data_for_comments.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                    if "subplot_comments" in veg_data_for_comments.columns:
                                        veg_comments = veg_data_for_comments[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                        meas_enum = meas_enum.merge(
                                            veg_comments,
                                            on="SUBPLOT_KEY",
                                            how="left",
                                            suffixes=("", "_veg")
                                        )
                                        print(f"DEBUG: Merged subplot_comments for PDF", file=sys.stderr)

                            # Merge with enumerator info
                            meas_enum = merge_with_enumerator(meas_enum, enum_data)
                            species_col = get_species_column(meas_enum)
                            print(f"DEBUG: Species column: {species_col}", file=sys.stderr)

                            # Run validation checks
                            veg_errors = {
                                "height_outliers": pd.DataFrame(),
                                "circ_outliers": pd.DataFrame(),
                                "suspicious_circ": pd.DataFrame(),
                            }

                            # Height outliers
                            if "tree_height_m" in meas_enum.columns and species_col:
                                print(f"DEBUG: Checking height outliers...", file=sys.stderr)
                                height_check = detect_height_outliers(
                                    meas_enum,
                                    height_col="tree_height_m",
                                    species_col=species_col,
                                )
                                if "Upper_outliers" in height_check.columns or "Lower_outliers" in height_check.columns:
                                    outliers = height_check[
                                        (height_check.get("Upper_outliers", False) == True) |
                                        (height_check.get("Lower_outliers", False) == True)
                                    ]
                                    print(f"DEBUG: Found {len(outliers)} height outliers", file=sys.stderr)
                                    # Preserve subplot_comments if it exists in original data
                                    if "subplot_comments" in meas_enum.columns and "subplot_comments" not in outliers.columns:
                                        # Merge subplot_comments back based on a key
                                        if "SUBPLOT_KEY" in outliers.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                            comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                            outliers = outliers.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                        elif "subplot_id" in outliers.columns and "subplot_id" in meas_enum.columns:
                                            comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                            outliers = outliers.merge(comments_map, on="subplot_id", how="left")
                                    veg_errors["height_outliers"] = outliers
                                    total_veg_errors += len(outliers)

                            # Circumference outliers
                            circ_cols = [c for c in ["circumference_bh", "circumference_10cm"] if c in meas_enum.columns]
                            print(f"DEBUG: Circumference columns: {circ_cols}", file=sys.stderr)
                            if circ_cols and species_col:
                                for circ_col in circ_cols:
                                    print(f"DEBUG: Checking circumference outliers for {circ_col}...", file=sys.stderr)
                                    circ_check = detect_circumference_outliers(
                                        meas_enum,
                                        circumference_col=circ_col,
                                        species_col=species_col,
                                    )
                                    if "Upper_outliers" in circ_check.columns or "Lower_outliers" in circ_check.columns:
                                        outliers = circ_check[
                                            (circ_check.get("Upper_outliers", False) == True) |
                                            (circ_check.get("Lower_outliers", False) == True)
                                        ]
                                        print(f"DEBUG: Found {len(outliers)} circumference outliers for {circ_col}", file=sys.stderr)
                                        if len(outliers) > 0:
                                            # Preserve subplot_comments if it exists in original data
                                            if "subplot_comments" in meas_enum.columns and "subplot_comments" not in outliers.columns:
                                                if "SUBPLOT_KEY" in outliers.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                                    comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                                    outliers = outliers.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                                elif "subplot_id" in outliers.columns and "subplot_id" in meas_enum.columns:
                                                    comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                                    outliers = outliers.merge(comments_map, on="subplot_id", how="left")
                                            veg_errors["circ_outliers"] = pd.concat([
                                                veg_errors["circ_outliers"],
                                                outliers
                                            ]).drop_duplicates()

                                total_veg_errors += len(veg_errors["circ_outliers"])
                                print(f"DEBUG: Total circumference outliers: {len(veg_errors['circ_outliers'])}", file=sys.stderr)

                            # Suspicious circumference by age
                            if "tree_year_planted" in meas_enum.columns and circ_cols:
                                print(f"DEBUG: Checking suspicious circumference by age...", file=sys.stderr)
                                from utils.data_merge_utils import calculate_tree_age
                                meas_with_age = calculate_tree_age(meas_enum)
                                if "tree_age" in meas_with_age.columns:
                                    susp_circ = detect_suspicious_circumference_by_age(meas_with_age)
                                    if "flag" in susp_circ.columns:
                                        flagged = susp_circ[susp_circ["flag"] == True]
                                        print(f"DEBUG: Found {len(flagged)} suspicious circ/age records", file=sys.stderr)
                                        # Preserve subplot_comments if it exists in original data
                                        if "subplot_comments" in meas_enum.columns and "subplot_comments" not in flagged.columns:
                                            if "SUBPLOT_KEY" in flagged.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                                comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                                flagged = flagged.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                            elif "subplot_id" in flagged.columns and "subplot_id" in meas_enum.columns:
                                                comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                                flagged = flagged.merge(comments_map, on="subplot_id", how="left")
                                        veg_errors["suspicious_circ"] = flagged
                                        total_veg_errors += len(flagged)

                            veg_errors_data = veg_errors
                            print(f"DEBUG: Total vegetation errors: {total_veg_errors}", file=sys.stderr)
                except Exception as e:
                    # If vegetation error detection fails, continue without it
                    print(f"DEBUG: Error in vegetation error detection: {str(e)}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)

        # Statistics
        total = len(enum_data)
        invalid = (~enum_data["geom_valid"]).sum()
        valid = enum_data["geom_valid"].sum()
        error_rate = (invalid / total * 100) if total > 0 else 0

        # Calculate missing vegetation for this enumerator
        total_missing_veg = 0
        if raw_data and "plots_subplots_vegetation" in raw_data:
            veg_data_full = raw_data["plots_subplots_vegetation"]
            enum_subplot_keys = enum_data["subplot_id"].unique()
            veg_subplot_keys = veg_data_full["SUBPLOT_KEY"].unique() if "SUBPLOT_KEY" in veg_data_full.columns else []
            missing_veg_list = [k for k in enum_subplot_keys if k not in veg_subplot_keys]
            total_missing_veg = len(missing_veg_list)

        print(f"DEBUG PDF: Total missing veg for enumerator: {total_missing_veg}", file=sys.stderr)

        print(f"DEBUG PDF: Skipping Executive Summary and Performance Visualization, going straight to date-wise analysis", file=sys.stderr)

        # Date-wise error analysis (GEOMETRY + VEGETATION)
        # Note: veg_errors_data was already calculated earlier for the summary
        print(f"DEBUG PDF: Checking for date-wise analysis, SubmissionDate column exists: {'SubmissionDate' in enum_data.columns}", file=sys.stderr)
        if "SubmissionDate" in enum_data.columns:
            # Convert to date only (remove time)
            enum_data["date_only"] = pd.to_datetime(enum_data["SubmissionDate"]).dt.date

            # Group by date (sort in descending order - latest first)
            dates = sorted(enum_data["date_only"].dropna().unique(), reverse=True)
            print(f"DEBUG PDF: Found {len(dates)} unique dates (sorted latest first)", file=sys.stderr)

            if len(dates) > 0:
                print(f"DEBUG PDF: Starting date-wise error analysis for {len(dates)} dates", file=sys.stderr)
                story.append(Paragraph("Date-wise Error Analysis", section_style))

                for date_idx, date in enumerate(dates):
                    # Get data for this date
                    date_data = enum_data[enum_data["date_only"] == date].copy()
                    date_total = len(date_data)
                    date_invalid = (~date_data["geom_valid"]).sum()
                    date_valid = date_data["geom_valid"].sum()
                    date_error_rate = (date_invalid / date_total * 100) if date_total > 0 else 0

                    # Date header
                    date_header_style = ParagraphStyle(
                        "DateHeader",
                        parent=styles["Heading3"],
                        fontSize=14,
                        textColor=colors.HexColor("#1976D2"),
                        spaceBefore=16,
                        spaceAfter=10,
                        fontName="Helvetica-Bold",
                    )

                    story.append(Paragraph(
                        f"📅 {date.strftime('%B %d, %Y')} - {date_total} subplots ({date_invalid} errors)",
                        date_header_style
                    ))

                    # Date summary
                    date_summary_data = [
                        ["Total Subplots", str(date_total)],
                        ["Valid", f"{date_valid} ({date_valid/date_total*100:.1f}%)"],
                        ["Invalid", f"{date_invalid} ({date_error_rate:.1f}%)"],
                    ]

                    date_summary_table = Table(date_summary_data, colWidths=[2 * inch, 2 * inch])
                    date_summary_table.setStyle(
                        TableStyle([
                            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E3F2FD")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("PADDING", (0, 0), (-1, -1), 8),
                            ("FONTSIZE", (0, 0), (-1, -1), 10),
                        ])
                    )
                    story.append(date_summary_table)
                    story.append(Spacer(1, 0.2 * inch))

                    # Show invalid subplots with details
                    date_invalid_data = date_data[~date_data["geom_valid"]]

                    # Also check for missing vegetation records for this date
                    date_missing_veg = []
                    if raw_data and "plots_subplots_vegetation" in raw_data:
                        veg_data_full = raw_data["plots_subplots_vegetation"]
                        # Get subplot keys for this date
                        date_subplot_keys = date_data["subplot_id"].unique()
                        veg_subplot_keys = veg_data_full["SUBPLOT_KEY"].unique() if "SUBPLOT_KEY" in veg_data_full.columns else []
                        # Find subplots without vegetation
                        date_missing_veg = [k for k in date_subplot_keys if k not in veg_subplot_keys]

                    print(f"DEBUG PDF: Date {date} - Invalid: {len(date_invalid_data)}, Missing Veg: {len(date_missing_veg)}", file=sys.stderr)

                    # Create a map overview for this date showing all subplots
                    if len(date_data) > 0 and MATPLOTLIB_AVAILABLE:
                        try:
                            print(f"DEBUG PDF: Creating map overview for date {date}", file=sys.stderr)

                            fig, ax = plt.subplots(figsize=(6, 4), dpi=100)

                            # Plot all subplots for this date
                            for idx, row in date_data.iterrows():
                                if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                    geom = row["geometry"]
                                    if geom.geom_type == 'Polygon':
                                        x, y = geom.exterior.xy
                                        is_valid = row.get("geom_valid", False)
                                        color = '#4CAF50' if is_valid else '#F44336'
                                        alpha = 0.3 if is_valid else 0.6
                                        ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)

                                        # Add label for invalid ones
                                        if not is_valid:
                                            centroid = geom.centroid
                                            ax.plot(centroid.x, centroid.y, 'rx', markersize=8, markeredgewidth=2)

                            ax.set_aspect('equal')
                            ax.grid(True, alpha=0.3)
                            ax.set_xlabel('Longitude', fontsize=9)
                            ax.set_ylabel('Latitude', fontsize=9)
                            ax.tick_params(labelsize=8)
                            ax.set_title(f"Subplot Overview - {date.strftime('%B %d, %Y')}\nGreen=Valid, Red=Invalid",
                                        fontsize=10, fontweight='bold')

                            plt.tight_layout()

                            # Convert to image for PDF
                            map_buffer = BytesIO()
                            plt.savefig(map_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                            plt.close(fig)
                            map_buffer.seek(0)

                            # Add to PDF
                            map_img = RLImage(map_buffer, width=5*inch, height=3.33*inch)
                            story.append(map_img)
                            story.append(Spacer(1, 0.2 * inch))
                            print(f"DEBUG PDF: Successfully added map overview to PDF", file=sys.stderr)

                        except Exception as e:
                            print(f"DEBUG PDF: Error creating map overview: {str(e)}", file=sys.stderr)
                            import traceback
                            traceback.print_exc(file=sys.stderr)

                    if len(date_invalid_data) > 0 or len(date_missing_veg) > 0:
                        print(f"DEBUG PDF: Entered date error section, processing {len(date_invalid_data)} invalid subplots", file=sys.stderr)
                        # Error type breakdown for this date
                        error_types = {}
                        for reasons in date_invalid_data["reasons"].dropna():
                            for reason in str(reasons).split(";"):
                                reason = reason.strip()
                                if reason:
                                    error_types[reason] = error_types.get(reason, 0) + 1

                        # Get vegetation data if available
                        veg_data = None
                        if raw_data and "plots_subplots_vegetation" in raw_data:
                            veg_data = raw_data["plots_subplots_vegetation"]

                        # Individual subplot sections with polygon images and vegetation details
                        subplot_count = 0
                        max_subplots_per_date = 15  # Limit to avoid huge PDFs

                        print(f"DEBUG PDF: Starting loop through {len(date_invalid_data)} invalid subplots", file=sys.stderr)
                        for idx, row in date_invalid_data.iterrows():
                            print(f"DEBUG PDF: Processing subplot {subplot_count + 1}/{len(date_invalid_data)}", file=sys.stderr)
                            subplot_count += 1
                            if subplot_count > max_subplots_per_date:
                                # Show remaining count
                                remaining_style = ParagraphStyle(
                                    "Remaining",
                                    parent=styles["Normal"],
                                    fontSize=10,
                                    textColor=colors.grey,
                                    spaceBefore=10,
                                    spaceAfter=10,
                                    alignment=TA_CENTER,
                                    fontStyle='italic',
                                )
                                remaining = len(date_invalid_data) - max_subplots_per_date
                                story.append(Paragraph(
                                    f"... and {remaining} more invalid subplot(s) for this date",
                                    remaining_style
                                ))
                                break

                            # Subplot header
                            subplot_id = str(row.get("subplot_id", "N/A"))
                            subplot_header_style = ParagraphStyle(
                                "SubplotHeader",
                                parent=styles["Heading4"],
                                fontSize=11,
                                textColor=colors.HexColor("#E53935"),
                                spaceBefore=14,
                                spaceAfter=6,
                                fontName="Helvetica-Bold",
                            )
                            story.append(Paragraph(f"Subplot: {subplot_id}", subplot_header_style))

                            # Create a table with polygon image on left, details on right
                            print(f"DEBUG PDF: Attempting to create polygon for subplot {subplot_id}", file=sys.stderr)

                            # Create polygon image directly inline
                            polygon_img_rl = None
                            if MATPLOTLIB_AVAILABLE:
                                try:
                                    if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                        geom = row["geometry"]
                                        is_valid = row.get("geom_valid", False)

                                        fig, ax = plt.subplots(figsize=(3, 2.5), dpi=100)

                                        if geom.geom_type == 'Polygon':
                                            x, y = geom.exterior.xy
                                            color = '#4CAF50' if is_valid else '#F44336'
                                            ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                                            ax.plot(x, y, 'o', color=color, markersize=3)

                                            # Add centroid
                                            centroid = geom.centroid
                                            ax.plot(centroid.x, centroid.y, 'x', color='black', markersize=6, markeredgewidth=2)

                                        ax.set_aspect('equal')
                                        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
                                        ax.set_xlabel('Longitude', fontsize=7)
                                        ax.set_ylabel('Latitude', fontsize=7)
                                        ax.tick_params(labelsize=6)

                                        # Add area info as title
                                        area_text = f"{row.get('area_m2', 0):.1f} m²"
                                        status = "INVALID" if not is_valid else "VALID"
                                        ax.set_title(f"{area_text} - {status}", fontsize=8, fontweight='bold')

                                        plt.tight_layout()

                                        # Convert to image
                                        poly_buffer = BytesIO()
                                        plt.savefig(poly_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                                        plt.close(fig)
                                        poly_buffer.seek(0)

                                        polygon_img_rl = RLImage(poly_buffer, width=2.5*inch, height=2.08*inch)
                                        print(f"DEBUG PDF: Successfully created polygon image inline", file=sys.stderr)
                                    else:
                                        print(f"DEBUG PDF: Geometry is None or empty", file=sys.stderr)

                                except Exception as e:
                                    print(f"DEBUG PDF: Error creating polygon inline: {str(e)}", file=sys.stderr)
                                    import traceback
                                    traceback.print_exc(file=sys.stderr)
                            else:
                                print(f"DEBUG PDF: Matplotlib not available, skipping polygon creation", file=sys.stderr)

                            # Right side: Details
                            detail_items = []

                            # Error reasons
                            reasons = str(row.get("reasons", "Unknown error"))
                            detail_items.append(f"<b>Error:</b> {reasons}")

                            # Geometry details
                            if "area_m2" in row and pd.notna(row["area_m2"]):
                                detail_items.append(f"<b>Area:</b> {row['area_m2']:.1f} m²")
                            if "nr_vertices" in row and pd.notna(row["nr_vertices"]):
                                detail_items.append(f"<b>Vertices:</b> {int(row['nr_vertices'])}")

                            # Get vegetation details for this subplot
                            if veg_data is not None:
                                subplot_key = row.get("subplot_id")
                                if subplot_key:
                                    subplot_veg = veg_data[veg_data.get("SUBPLOT_KEY", pd.Series()) == subplot_key]

                                    if len(subplot_veg) == 0:
                                        detail_items.append("<b>Vegetation:</b> No vegetation records")
                                    else:
                                        # Check for vegetation type
                                        veg_rec = subplot_veg.iloc[0]

                                        # Coverage vegetation
                                        if "coverage_vegetation" in veg_rec and pd.notna(veg_rec["coverage_vegetation"]):
                                            cov = veg_rec["coverage_vegetation"]
                                            detail_items.append(f"<b>Coverage:</b> {cov}%")

                                        # Check if bare land or other coverage types
                                        if "non_woody_species" in veg_rec and pd.notna(veg_rec["non_woody_species"]):
                                            non_woody = veg_rec["non_woody_species"]
                                            if str(non_woody).lower() in ["bare land", "bareland", "bare_land"]:
                                                detail_items.append("<b>Type:</b> Bare Land")
                                            else:
                                                detail_items.append(f"<b>Non-woody:</b> {non_woody}")

                                        # Subplot comments
                                        if "subplot_comments" in veg_rec and pd.notna(veg_rec["subplot_comments"]):
                                            comments = str(veg_rec["subplot_comments"])
                                            if len(comments) > 60:
                                                comments = comments[:57] + "..."
                                            detail_items.append(f"<b>Comments:</b> {comments}")

                                        # Crop comments
                                        if "crop_comments" in veg_rec and pd.notna(veg_rec["crop_comments"]):
                                            crop = str(veg_rec["crop_comments"])
                                            if len(crop) > 60:
                                                crop = crop[:57] + "..."
                                            detail_items.append(f"<b>Crop:</b> {crop}")

                                        # Tree count if available
                                        tree_count = len(subplot_veg[subplot_veg.get("vegetation_type_number", pd.Series()).notna()])
                                        if tree_count > 0:
                                            detail_items.append(f"<b>Trees:</b> {tree_count} recorded")

                            # Create detail text
                            detail_text = "<br/>".join(detail_items)
                            detail_para = Paragraph(detail_text, ParagraphStyle(
                                "Details",
                                parent=styles["Normal"],
                                fontSize=9,
                                leading=11,
                            ))

                            # Create 2-column table with polygon on left, details on right
                            if polygon_img_rl:
                                detail_table = Table(
                                    [[polygon_img_rl, detail_para]],
                                    colWidths=[2.8*inch, 3.5*inch]
                                )
                                print(f"DEBUG PDF: Added 2-column table with polygon", file=sys.stderr)
                            else:
                                detail_table = Table(
                                    [[detail_para]],
                                    colWidths=[6.3*inch]
                                )
                                print(f"DEBUG PDF: Added 1-column table without polygon", file=sys.stderr)

                            detail_table.setStyle(
                                TableStyle([
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                    ("BOX", (0, 0), (-1, -1), 1, colors.grey),
                                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
                                ])
                            )

                            story.append(detail_table)
                            story.append(Spacer(1, 0.15 * inch))
                    else:
                        # No geometry errors for this date
                        success_note_style = ParagraphStyle(
                            "SuccessNote",
                            parent=styles["Normal"],
                            fontSize=10,
                            textColor=colors.HexColor("#4CAF50"),
                            spaceBefore=6,
                            spaceAfter=6,
                            alignment=TA_CENTER,
                        )
                        story.append(Paragraph("✓ All subplots geometrically valid for this date", success_note_style))

                    # Add missing vegetation records for this date
                    if len(date_missing_veg) > 0:
                        story.append(Spacer(1, 0.3 * inch))

                        missing_veg_header_style = ParagraphStyle(
                            "MissingVegHeader",
                            parent=styles["Heading4"],
                            fontSize=12,
                            textColor=colors.HexColor("#FF6F00"),
                            spaceBefore=10,
                            spaceAfter=8,
                            fontName="Helvetica-Bold",
                        )
                        story.append(Paragraph("❌ Missing Vegetation Records", missing_veg_header_style))

                        # Get subplot details for missing vegetation
                        missing_veg_details = []
                        if "plots_subplots" in raw_data:
                            plots_data = raw_data["plots_subplots"]
                            for subplot_key in date_missing_veg[:10]:  # Limit to 10
                                subplot_info = plots_data[plots_data.get("SUBPLOT_KEY", pd.Series()) == subplot_key]
                                if len(subplot_info) > 0:
                                    subplot_rec = subplot_info.iloc[0]
                                    comments = subplot_rec.get("subplot_comments", "—")
                                    if pd.notna(comments) and str(comments).strip():
                                        comments = str(comments)
                                        if len(comments) > 60:
                                            comments = comments[:57] + "..."
                                    else:
                                        comments = "—"
                                    missing_veg_details.append([str(subplot_key), comments])

                        if missing_veg_details:
                            # Use Paragraphs for table data to enable text wrapping
                            missing_veg_table_data = [["Subplot ID", "Comments"]]
                            for subplot_key, comments in missing_veg_details:
                                # Wrap long subplot IDs
                                subplot_para = Paragraph(subplot_key, ParagraphStyle(
                                    "SubplotID",
                                    parent=styles["Normal"],
                                    fontSize=8,
                                    leading=10,
                                    wordWrap='CJK',
                                ))
                                comments_para = Paragraph(comments, ParagraphStyle(
                                    "Comments",
                                    parent=styles["Normal"],
                                    fontSize=9,
                                    leading=11,
                                ))
                                missing_veg_table_data.append([subplot_para, comments_para])

                            missing_veg_table = Table(missing_veg_table_data, colWidths=[2.5 * inch, 3.8 * inch])
                            missing_veg_table.setStyle(
                                TableStyle([
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6F00")),
                                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFF3E0")),
                                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                                    ("PADDING", (0, 1), (-1, -1), 6),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ])
                            )
                            story.append(missing_veg_table)

                            if len(date_missing_veg) > 10:
                                remaining_text = f"... and {len(date_missing_veg) - 10} more subplots without vegetation"
                                remaining_style = ParagraphStyle(
                                    "Remaining",
                                    parent=styles["Normal"],
                                    fontSize=9,
                                    textColor=colors.grey,
                                    spaceBefore=6,
                                )
                                story.append(Paragraph(remaining_text, remaining_style))

                    # Add measurement-based vegetation errors for this date
                    if veg_errors_data:
                        print(f"DEBUG: Checking veg errors for date {date}, veg_errors_data keys: {veg_errors_data.keys()}", file=sys.stderr)
                        story.append(Spacer(1, 0.3 * inch))

                        # Header for vegetation errors
                        veg_error_header_style = ParagraphStyle(
                            "VegErrorHeader",
                            parent=styles["Heading4"],
                            fontSize=12,
                            textColor=colors.HexColor("#FF6F00"),
                            spaceBefore=10,
                            spaceAfter=8,
                            fontName="Helvetica-Bold",
                        )

                        # Collect all vegetation errors for this date
                        date_veg_errors = []

                        # Height outliers
                        if "height_outliers" in veg_errors_data and len(veg_errors_data["height_outliers"]) > 0:
                            print(f"DEBUG: Processing {len(veg_errors_data['height_outliers'])} height outliers for date filtering", file=sys.stderr)
                            height_df = veg_errors_data["height_outliers"]
                            if "SubmissionDate" in height_df.columns:
                                height_df["date_only"] = pd.to_datetime(height_df["SubmissionDate"]).dt.date
                                date_height = height_df[height_df["date_only"] == date]
                                print(f"DEBUG: Found {len(date_height)} height outliers for date {date}", file=sys.stderr)
                                for _, row in date_height.head(5).iterrows():
                                    error_type = "Height Outlier"
                                    details = []
                                    if "tree_height_m" in row and pd.notna(row["tree_height_m"]):
                                        details.append(f"{row['tree_height_m']:.1f}m")
                                    if species_col and species_col in row:
                                        details.append(str(row[species_col]))
                                    # Add subplot comments
                                    comments = str(row.get("subplot_comments", "")) if pd.notna(row.get("subplot_comments")) else "—"
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append([error_type, " | ".join(details) if details else "—", comments])

                        # Circumference outliers
                        if "circ_outliers" in veg_errors_data and len(veg_errors_data["circ_outliers"]) > 0:
                            circ_df = veg_errors_data["circ_outliers"]
                            if "SubmissionDate" in circ_df.columns:
                                circ_df["date_only"] = pd.to_datetime(circ_df["SubmissionDate"]).dt.date
                                date_circ = circ_df[circ_df["date_only"] == date]
                                for _, row in date_circ.head(5).iterrows():
                                    error_type = "Circumference Outlier"
                                    details = []
                                    for col in ["circumference_bh", "circumference_10cm"]:
                                        if col in row and pd.notna(row[col]):
                                            details.append(f"{row[col]:.1f}cm")
                                            break
                                    if species_col and species_col in row:
                                        details.append(str(row[species_col]))
                                    # Add subplot comments
                                    comments = str(row.get("subplot_comments", "")) if pd.notna(row.get("subplot_comments")) else "—"
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append([error_type, " | ".join(details) if details else "—", comments])

                        # Suspicious circumference by age
                        if "suspicious_circ" in veg_errors_data and len(veg_errors_data["suspicious_circ"]) > 0:
                            susp_df = veg_errors_data["suspicious_circ"]
                            if "SubmissionDate" in susp_df.columns:
                                susp_df["date_only"] = pd.to_datetime(susp_df["SubmissionDate"]).dt.date
                                date_susp = susp_df[susp_df["date_only"] == date]
                                for _, row in date_susp.head(5).iterrows():
                                    error_type = "Suspicious Circ/Age"
                                    details = []
                                    if "tree_age" in row and pd.notna(row["tree_age"]):
                                        details.append(f"Age: {int(row['tree_age'])}y")
                                    for col in ["circumference_bh", "circumference_10cm"]:
                                        if col in row and pd.notna(row[col]):
                                            details.append(f"Circ: {row[col]:.1f}cm")
                                            break
                                    # Add subplot comments
                                    comments = str(row.get("subplot_comments", "")) if pd.notna(row.get("subplot_comments")) else "—"
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append([error_type, " | ".join(details) if details else "—", comments])

                        # Display vegetation errors if any found for this date
                        print(f"DEBUG: Total date_veg_errors collected: {len(date_veg_errors)}", file=sys.stderr)
                        if date_veg_errors:
                            story.append(Paragraph("🌿 Vegetation & Measurement Issues", veg_error_header_style))

                            veg_error_table_data = [["Error Type", "Details", "Subplot Comments"]] + date_veg_errors[:10]

                            veg_error_table = Table(veg_error_table_data, colWidths=[1.8 * inch, 2.5 * inch, 2 * inch])
                            veg_error_table.setStyle(
                                TableStyle([
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6F00")),
                                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                                    ("PADDING", (0, 0), (-1, -1), 6),
                                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFF3E0")),
                                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FFF3E0"), colors.white]),
                                ])
                            )
                            story.append(veg_error_table)

                            if len(date_veg_errors) > 10:
                                remaining = len(date_veg_errors) - 10
                                story.append(Paragraph(
                                    f"<i>... and {remaining} more vegetation error(s)</i>",
                                    ParagraphStyle(
                                        "VegRemaining",
                                        parent=styles["Normal"],
                                        fontSize=8,
                                        textColor=colors.grey,
                                        spaceBefore=4,
                                        fontStyle='italic',
                                    )
                                ))

                    # Add spacing between dates, page break after every 2-3 dates
                    if date_idx < len(dates) - 1:
                        if (date_idx + 1) % 2 == 0:
                            story.append(PageBreak())
                        else:
                            story.append(Spacer(1, 0.4 * inch))
        else:
            # Fallback if no date column - show overall error analysis
            invalid_data = enum_data[~enum_data["geom_valid"]]

            if len(invalid_data) > 0:
                story.append(Paragraph("Error Analysis", section_style))

                subplot_details = [["Subplot ID", "Error Type", "Details"]]

                for idx, row in invalid_data.head(30).iterrows():
                    subplot_id = str(row.get("subplot_id", "N/A"))
                    if len(subplot_id) > 25:
                        subplot_id = subplot_id[:22] + "..."

                    reasons = str(row.get("reasons", "Unknown"))
                    if len(reasons) > 35:
                        reasons = reasons[:32] + "..."

                    details_parts = []
                    if "area_m2" in row and pd.notna(row["area_m2"]):
                        details_parts.append(f"Area: {row['area_m2']:.1f}m²")
                    if "nr_vertices" in row and pd.notna(row["nr_vertices"]):
                        details_parts.append(f"Vertices: {int(row['nr_vertices'])}")

                    details = " | ".join(details_parts) if details_parts else "—"
                    subplot_details.append([subplot_id, reasons, details])

                subplot_table = Table(subplot_details, colWidths=[1.8 * inch, 2.2 * inch, 2 * inch])
                subplot_table.setStyle(
                    TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D32F2F")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("PADDING", (0, 0), (-1, -1), 6),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFEBEE")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ])
                )

                story.append(subplot_table)

        print(f"DEBUG PDF: Building final PDF with {len(story)} elements", file=sys.stderr)
        doc.build(story)
        buffer.seek(0)
        print(f"DEBUG PDF: PDF generation complete, returning buffer", file=sys.stderr)
        return buffer

    except ImportError:
        return None


def export_to_geojson(enum_data, enumerator_name):
    """
    Export enumerator's data to GeoJSON format
    """
    if "geometry" not in enum_data.columns:
        return None

    # Filter out empty geometries
    export_data = enum_data[~enum_data.geometry.is_empty].copy()

    if len(export_data) == 0:
        return None

    # Select columns for export
    export_cols = ["subplot_id", "geom_valid", "geometry"]

    optional_cols = ["area_m2", "nr_vertices", "reasons", "enumerator"]
    for col in optional_cols:
        if col in export_data.columns:
            export_cols.append(col)

    # Create GeoDataFrame
    gdf_export = export_data[export_cols].copy()

    # Add metadata
    gdf_export["enumerator"] = enumerator_name
    gdf_export["export_date"] = pd.Timestamp.now().strftime("%Y-%m-%d")

    # Convert to GeoJSON
    geojson_str = gdf_export.to_json()

    return geojson_str


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
# TABS - ALWAYS DEFINED
# ============================================

# Determine which tabs to show
if has_vegetation and has_measurements:
    tab_list = [
        "📊 Error Overview",
        "📐 Geometry Errors",
        "🌿 Vegetation Errors",
        "📋 Error Details by Enumerator",
    ]
    has_veg_tab = True
else:
    tab_list = [
        "📊 Error Overview",
        "📐 Geometry Errors",
        "📋 Error Details by Enumerator",
    ]
    has_veg_tab = False

# Create tabs (ALWAYS executed)
tabs = st.tabs(tab_list)

# Calculate indices
TAB_OVERVIEW = 0
TAB_GEOMETRY = 1
TAB_VEG_ERRORS = 2 if has_veg_tab else None
TAB_ERROR_DETAILS = 3 if has_veg_tab else 2

# ============================================
# TAB 1: ERROR OVERVIEW
# ============================================

with tabs[TAB_OVERVIEW]:
    st.markdown("### 📊 Error Rate Overview")

    # Calculate error statistics
    enum_stats = []
    for enum in selected_enumerators:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum]
        total = len(enum_data)
        invalid = (~enum_data["geom_valid"]).sum()
        valid = enum_data["geom_valid"].sum()
        error_rate = (invalid / total * 100) if total > 0 else 0

        enum_stats.append(
            {
                "Enumerator": enum,
                "Total": total,
                "Valid": valid,
                "Invalid": invalid,
                "Error Rate (%)": error_rate,
            }
        )

    stats_df = pd.DataFrame(enum_stats)

    if len(stats_df) > 0:
        col1, col2 = st.columns(2)

        with col1:
            # Bar chart
            fig = px.bar(
                stats_df,
                x="Enumerator",
                y="Error Rate (%)",
                title="Error Rate by Enumerator",
                color="Error Rate (%)",
                color_continuous_scale="Reds",
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Stacked bar chart
            fig = px.bar(
                stats_df,
                x="Enumerator",
                y=["Valid", "Invalid"],
                title="Valid vs Invalid Subplots",
                labels={"value": "Count", "variable": "Status"},
                color_discrete_map={"Valid": "green", "Invalid": "red"},
            )
            st.plotly_chart(fig, use_container_width=True)

        # Data table
        st.markdown("#### Summary Table")
        st.dataframe(stats_df, use_container_width=True, height=300)

# ============================================
# TAB 2: GEOMETRY ERRORS
# ============================================

with tabs[TAB_GEOMETRY]:
    st.markdown("### 📐 Geometry Errors by Enumerator")

    invalid_subplots = filtered_gdf[~filtered_gdf["geom_valid"]]

    if len(invalid_subplots) > 0:
        # Count errors by enumerator
        error_counts = (
            invalid_subplots.groupby("enumerator")
            .size()
            .reset_index(name="Error Count")
        )
        error_counts = error_counts.sort_values("Error Count", ascending=False)

        col1, col2 = st.columns(2)

        with col1:
            fig = px.bar(
                error_counts,
                x="enumerator",
                y="Error Count",
                title="Geometry Errors by Enumerator",
                color="Error Count",
                color_continuous_scale="Oranges",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(error_counts, use_container_width=True, height=300)

        # Error types breakdown
        st.markdown("#### Error Types Breakdown")

        error_type_data = []
        for enum in selected_enumerators:
            enum_invalid = invalid_subplots[invalid_subplots["enumerator"] == enum]
            if len(enum_invalid) > 0:
                for _, row in enum_invalid.iterrows():
                    if pd.notna(row.get("reasons")):
                        for reason in str(row["reasons"]).split(";"):
                            if reason.strip():
                                error_type_data.append(
                                    {
                                        "Enumerator": enum,
                                        "Error Type": reason.strip(),
                                    }
                                )

        if error_type_data:
            error_types_df = pd.DataFrame(error_type_data)
            error_summary = (
                error_types_df.groupby(["Enumerator", "Error Type"])
                .size()
                .reset_index(name="Count")
            )

            fig = px.bar(
                error_summary,
                x="Enumerator",
                y="Count",
                color="Error Type",
                title="Error Types by Enumerator",
                barmode="stack",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(error_summary, use_container_width=True, height=300)
    else:
        st.success("✅ No geometry errors found for selected enumerators!")

# ============================================
# TAB 3: VEGETATION ERRORS (if available)
# ============================================

if has_veg_tab and TAB_VEG_ERRORS is not None:
    with tabs[TAB_VEG_ERRORS]:
        st.markdown("### 🌿 Vegetation & Measurement Errors by Enumerator")
        st.caption("Quality checks on tree measurements, heights, circumferences, and age data")

        try:
            from utils.vegetation_validation import (
                detect_height_outliers,
                detect_circumference_outliers,
                detect_suspicious_circumference_by_age,
            )
            from utils.data_merge_utils import (
                merge_with_enumerator,
                get_species_column,
                calculate_tree_age,
            )

            if "plots_subplots_vegetation_measurements" in raw_data:
                meas_df = raw_data["plots_subplots_vegetation_measurements"]

                # Calculate vegetation errors for each enumerator
                enum_veg_stats = []

                for enum in selected_enumerators:
                    enum_subplot_keys = filtered_gdf[filtered_gdf["enumerator"] == enum]["subplot_id"].unique()
                    meas_enum = meas_df[meas_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()

                    if len(meas_enum) > 0:
                        # Merge with enumerator info
                        enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum]
                        meas_enum = merge_with_enumerator(meas_enum, enum_data)
                        species_col = get_species_column(meas_enum)

                        # Count errors
                        height_outliers_count = 0
                        circ_outliers_count = 0
                        suspicious_circ_count = 0

                        # Height outliers
                        if "tree_height_m" in meas_enum.columns and species_col:
                            height_check = detect_height_outliers(
                                meas_enum,
                                height_col="tree_height_m",
                                species_col=species_col,
                            )
                            if "Upper_outliers" in height_check.columns or "Lower_outliers" in height_check.columns:
                                outliers = height_check[
                                    (height_check.get("Upper_outliers", False) == True) |
                                    (height_check.get("Lower_outliers", False) == True)
                                ]
                                height_outliers_count = len(outliers)

                        # Circumference outliers
                        circ_cols = [c for c in ["circumference_bh", "circumference_10cm"] if c in meas_enum.columns]
                        if circ_cols and species_col:
                            all_circ_outliers = pd.DataFrame()
                            for circ_col in circ_cols:
                                circ_check = detect_circumference_outliers(
                                    meas_enum,
                                    circumference_col=circ_col,
                                    species_col=species_col,
                                )
                                if "Upper_outliers" in circ_check.columns or "Lower_outliers" in circ_check.columns:
                                    outliers = circ_check[
                                        (circ_check.get("Upper_outliers", False) == True) |
                                        (circ_check.get("Lower_outliers", False) == True)
                                    ]
                                    if len(outliers) > 0:
                                        all_circ_outliers = pd.concat([all_circ_outliers, outliers]).drop_duplicates()
                            circ_outliers_count = len(all_circ_outliers)

                        # Suspicious circumference by age
                        if "tree_year_planted" in meas_enum.columns and circ_cols:
                            meas_with_age = calculate_tree_age(meas_enum)
                            if "tree_age" in meas_with_age.columns:
                                susp_circ = detect_suspicious_circumference_by_age(meas_with_age)
                                if "flag" in susp_circ.columns:
                                    flagged = susp_circ[susp_circ["flag"] == True]
                                    suspicious_circ_count = len(flagged)

                        # Calculate total errors and measurements
                        total_measurements = len(meas_enum)
                        total_veg_errors = height_outliers_count + circ_outliers_count + suspicious_circ_count
                        error_rate = (total_veg_errors / total_measurements * 100) if total_measurements > 0 else 0

                        enum_veg_stats.append({
                            "Enumerator": enum,
                            "Total Measurements": total_measurements,
                            "Height Outliers": height_outliers_count,
                            "Circ Outliers": circ_outliers_count,
                            "Suspicious Circ/Age": suspicious_circ_count,
                            "Total Errors": total_veg_errors,
                            "Error Rate (%)": error_rate,
                        })

                if enum_veg_stats:
                    veg_stats_df = pd.DataFrame(enum_veg_stats)

                    # Summary metrics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Measurements", veg_stats_df["Total Measurements"].sum())
                    with col2:
                        st.metric("Height Outliers", veg_stats_df["Height Outliers"].sum())
                    with col3:
                        st.metric("Circ Outliers", veg_stats_df["Circ Outliers"].sum())
                    with col4:
                        st.metric("Suspicious Circ/Age", veg_stats_df["Suspicious Circ/Age"].sum())

                    st.markdown("---")

                    # Charts
                    col1, col2 = st.columns(2)

                    with col1:
                        # Error rate by enumerator
                        fig = px.bar(
                            veg_stats_df,
                            x="Enumerator",
                            y="Error Rate (%)",
                            title="Vegetation Error Rate by Enumerator",
                            color="Error Rate (%)",
                            color_continuous_scale="Oranges",
                        )
                        fig.update_layout(showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        # Stacked bar chart of error types
                        fig = px.bar(
                            veg_stats_df,
                            x="Enumerator",
                            y=["Height Outliers", "Circ Outliers", "Suspicious Circ/Age"],
                            title="Vegetation Error Types by Enumerator",
                            labels={"value": "Count", "variable": "Error Type"},
                            color_discrete_map={
                                "Height Outliers": "#FF6F00",
                                "Circ Outliers": "#F44336",
                                "Suspicious Circ/Age": "#E91E63"
                            },
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Data table
                    st.markdown("#### Detailed Statistics")
                    st.dataframe(veg_stats_df, use_container_width=True, height=300)

                    # Export option
                    st.markdown("---")
                    st.markdown("#### 📥 Export Vegetation Errors")
                    csv_data = veg_stats_df.to_csv(index=False)
                    st.download_button(
                        "📊 Download Vegetation Error Summary",
                        data=csv_data,
                        file_name=f"{config.PARTNER}_vegetation_errors_summary.csv",
                        mime="text/csv",
                    )
                else:
                    st.info("No vegetation measurement data available for selected enumerators")
            else:
                st.info("No vegetation measurement data available in dataset")

        except Exception as e:
            st.error(f"Error loading vegetation data: {str(e)}")
            st.caption("Please ensure vegetation validation modules are available")

# ============================================
# TAB 4: ERROR DETAILS BY ENUMERATOR
# ============================================

with tabs[TAB_ERROR_DETAILS]:
    st.markdown("### 📋 Individual Enumerator Error Report")

    selected_enum = st.selectbox(
        "Select enumerator for detailed error report",
        options=selected_enumerators,
        key="detail_enum",
    )

    if selected_enum:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == selected_enum].copy()

        st.markdown(f"#### Error Report for: **{selected_enum}**")

        # Summary metrics
        # Calculate vegetation errors for summary
        veg_error_count = 0
        if has_vegetation and has_measurements and "plots_subplots_vegetation_measurements" in raw_data:
            try:
                from utils.vegetation_validation import (
                    detect_height_outliers,
                    detect_circumference_outliers,
                    detect_suspicious_circumference_by_age,
                )
                from utils.data_merge_utils import (
                    merge_with_enumerator,
                    get_species_column,
                    calculate_tree_age,
                )

                meas_df = raw_data["plots_subplots_vegetation_measurements"]
                veg_df = raw_data.get("plots_subplots_vegetation", pd.DataFrame())
                enum_subplot_keys = enum_data["subplot_id"].unique()
                meas_enum = meas_df[meas_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()

                # Missing vegetation
                if len(veg_df) > 0 and "SUBPLOT_KEY" in veg_df.columns:
                    veg_subplot_keys = veg_df["SUBPLOT_KEY"].unique()
                    subplots_without_veg = [k for k in enum_subplot_keys if k not in veg_subplot_keys]
                    veg_error_count += len(subplots_without_veg)

                if len(meas_enum) > 0:
                    meas_enum = merge_with_enumerator(meas_enum, enum_data)
                    species_col = get_species_column(meas_enum)

                    # Height outliers
                    if "tree_height_m" in meas_enum.columns and species_col:
                        height_check = detect_height_outliers(
                            meas_enum,
                            height_col="tree_height_m",
                            species_col=species_col,
                        )
                        if "Upper_outliers" in height_check.columns or "Lower_outliers" in height_check.columns:
                            outliers = height_check[
                                (height_check.get("Upper_outliers", False) == True) |
                                (height_check.get("Lower_outliers", False) == True)
                            ]
                            veg_error_count += len(outliers)

                    # Circumference outliers
                    circ_cols = [c for c in ["circumference_bh", "circumference_10cm"] if c in meas_enum.columns]
                    if circ_cols and species_col:
                        all_circ = pd.DataFrame()
                        for circ_col in circ_cols:
                            circ_check = detect_circumference_outliers(
                                meas_enum,
                                circumference_col=circ_col,
                                species_col=species_col,
                            )
                            if "Upper_outliers" in circ_check.columns or "Lower_outliers" in circ_check.columns:
                                outliers = circ_check[
                                    (circ_check.get("Upper_outliers", False) == True) |
                                    (circ_check.get("Lower_outliers", False) == True)
                                ]
                                if len(outliers) > 0:
                                    all_circ = pd.concat([all_circ, outliers]).drop_duplicates()
                        veg_error_count += len(all_circ)

                    # Suspicious circ/age
                    if "tree_year_planted" in meas_enum.columns and circ_cols:
                        meas_with_age = calculate_tree_age(meas_enum)
                        if "tree_age" in meas_with_age.columns:
                            susp_circ = detect_suspicious_circumference_by_age(meas_with_age)
                            if "flag" in susp_circ.columns:
                                veg_error_count += len(susp_circ[susp_circ["flag"] == True])
            except:
                pass

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Subplots", len(enum_data))

        with col2:
            invalid = (~enum_data["geom_valid"]).sum()
            st.metric("Geometry Errors", invalid)

        with col3:
            st.metric("Vegetation Errors", veg_error_count)

        with col4:
            total_errors = invalid + veg_error_count
            st.metric("Total Issues", total_errors)

        st.markdown("---")

        # ============================================
        # INTERACTIVE MAP
        # ============================================

        st.markdown("#### 🗺️ Subplot Locations Map")
        st.caption(
            "Interactive map with detailed popup information • Click subplots for details"
        )

        map_obj = create_enumerator_map(enum_data, selected_enum)

        if map_obj:
            # Display folium map
            try:
                from streamlit_folium import st_folium

                st.info(
                    "💡 **Tip:** Click on subplots to see detailed information. "
                    "Use the layer control (top-right) to toggle valid/invalid. "
                    "Change map styles using the layers menu."
                )

                st_folium(map_obj, width=None, height=600, returned_objects=[])

                # Map legend
                col_leg1, col_leg2, col_leg3 = st.columns(3)

                with col_leg1:
                    st.markdown("**🟢 Green** = Valid subplots")
                    st.markdown("**🔴 Red** = Invalid subplots")

                with col_leg2:
                    st.markdown("**🔲 Click** = View details")
                    st.markdown("**📍 Hover** = Quick info")

                with col_leg3:
                    st.markdown("**🗺️** = Change map style")
                    st.markdown("**🔍** = Zoom controls")

            except ImportError:
                st.error("📦 Install streamlit-folium: `pip install streamlit-folium`")
                st.info("📍 Map feature requires streamlit-folium package")
        else:
            st.info("📍 No geometry data available for map display")

        st.markdown("---")

        # Show invalid subplots only
        st.markdown("#### ⚠️ Geometry Errors")

        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0:
            display_cols = ["subplot_id", "reasons"]

            for col in ["area_m2", "nr_vertices", "length_width_ratio", "mrr_ratio"]:
                if col in invalid_data.columns:
                    display_cols.append(col)

            st.dataframe(
                invalid_data[display_cols], use_container_width=True, height=400
            )
        else:
            st.success(f"✅ No geometry errors for {selected_enum}")

        # ============================================
        # VEGETATION ERRORS SECTION
        # ============================================

        st.markdown("---")
        st.markdown("#### 🌿 Vegetation & Measurement Errors")

        if has_vegetation and has_measurements:
            try:
                from utils.vegetation_validation import (
                    detect_height_outliers,
                    detect_circumference_outliers,
                    detect_suspicious_circumference_by_age,
                )
                from utils.data_merge_utils import (
                    merge_with_enumerator,
                    get_species_column,
                    calculate_tree_age,
                    add_tree_name_column,
                )

                # Get measurement data for this enumerator
                if "plots_subplots_vegetation_measurements" in raw_data:
                    meas_df = raw_data["plots_subplots_vegetation_measurements"]
                    veg_df = raw_data.get("plots_subplots_vegetation", pd.DataFrame())

                    enum_subplot_keys = enum_data["subplot_id"].unique()
                    meas_enum = meas_df[meas_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()

                    # Vegetation error summary
                    col1, col2, col3, col4 = st.columns(4)

                    # Missing vegetation check
                    subplots_without_veg = []
                    if len(veg_df) > 0 and "SUBPLOT_KEY" in veg_df.columns:
                        veg_subplot_keys = veg_df["SUBPLOT_KEY"].unique()
                        subplots_without_veg = [k for k in enum_subplot_keys if k not in veg_subplot_keys]

                    with col1:
                        st.metric("Missing Vegetation", len(subplots_without_veg))

                    # Initialize error counts
                    height_outliers_df = pd.DataFrame()
                    circ_outliers_df = pd.DataFrame()
                    suspicious_circ_df = pd.DataFrame()

                    if len(meas_enum) > 0:
                        # Merge with subplot comments BEFORE other merges
                        if len(veg_df) > 0 and "SUBPLOT_KEY" in veg_df.columns and "SUBPLOT_KEY" in meas_enum.columns:
                            if "subplot_comments" in veg_df.columns:
                                veg_comments = veg_df[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                meas_enum = meas_enum.merge(
                                    veg_comments,
                                    on="SUBPLOT_KEY",
                                    how="left",
                                    suffixes=("", "_veg")
                                )

                        # Merge with enumerator info
                        meas_enum = merge_with_enumerator(meas_enum, enum_data)
                        meas_enum = add_tree_name_column(meas_enum)
                        species_col = get_species_column(meas_enum)

                        # Height outliers
                        if "tree_height_m" in meas_enum.columns and species_col:
                            height_check = detect_height_outliers(
                                meas_enum,
                                height_col="tree_height_m",
                                species_col=species_col,
                            )
                            if "Upper_outliers" in height_check.columns or "Lower_outliers" in height_check.columns:
                                height_outliers_df = height_check[
                                    (height_check.get("Upper_outliers", False) == True) |
                                    (height_check.get("Lower_outliers", False) == True)
                                ]
                                # Preserve subplot_comments
                                if "subplot_comments" in meas_enum.columns and "subplot_comments" not in height_outliers_df.columns:
                                    if "SUBPLOT_KEY" in height_outliers_df.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                        comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                        height_outliers_df = height_outliers_df.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                    elif "subplot_id" in height_outliers_df.columns and "subplot_id" in meas_enum.columns:
                                        comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                        height_outliers_df = height_outliers_df.merge(comments_map, on="subplot_id", how="left")

                        # Circumference outliers
                        circ_cols = [c for c in ["circumference_bh", "circumference_10cm"] if c in meas_enum.columns]
                        if circ_cols and species_col:
                            all_circ_outliers = pd.DataFrame()
                            for circ_col in circ_cols:
                                circ_check = detect_circumference_outliers(
                                    meas_enum,
                                    circumference_col=circ_col,
                                    species_col=species_col,
                                )
                                if "Upper_outliers" in circ_check.columns or "Lower_outliers" in circ_check.columns:
                                    outliers = circ_check[
                                        (circ_check.get("Upper_outliers", False) == True) |
                                        (circ_check.get("Lower_outliers", False) == True)
                                    ]
                                    if len(outliers) > 0:
                                        # Preserve subplot_comments
                                        if "subplot_comments" in meas_enum.columns and "subplot_comments" not in outliers.columns:
                                            if "SUBPLOT_KEY" in outliers.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                                comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                                outliers = outliers.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                            elif "subplot_id" in outliers.columns and "subplot_id" in meas_enum.columns:
                                                comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                                outliers = outliers.merge(comments_map, on="subplot_id", how="left")
                                        all_circ_outliers = pd.concat([all_circ_outliers, outliers]).drop_duplicates()
                            circ_outliers_df = all_circ_outliers

                        # Suspicious circumference by age
                        if "tree_year_planted" in meas_enum.columns and circ_cols:
                            meas_with_age = calculate_tree_age(meas_enum)
                            if "tree_age" in meas_with_age.columns:
                                susp_circ = detect_suspicious_circumference_by_age(meas_with_age)
                                if "flag" in susp_circ.columns:
                                    suspicious_circ_df = susp_circ[susp_circ["flag"] == True]
                                    # Preserve subplot_comments
                                    if "subplot_comments" in meas_enum.columns and "subplot_comments" not in suspicious_circ_df.columns:
                                        if "SUBPLOT_KEY" in suspicious_circ_df.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                            comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                            suspicious_circ_df = suspicious_circ_df.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                        elif "subplot_id" in suspicious_circ_df.columns and "subplot_id" in meas_enum.columns:
                                            comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                            suspicious_circ_df = suspicious_circ_df.merge(comments_map, on="subplot_id", how="left")

                    with col2:
                        st.metric("Height Outliers", len(height_outliers_df))
                    with col3:
                        st.metric("Circ Outliers", len(circ_outliers_df))
                    with col4:
                        st.metric("Suspicious Circ/Age", len(suspicious_circ_df))

                    st.markdown("---")

                    # Show detailed errors in expandable sections
                    if len(subplots_without_veg) > 0:
                        with st.expander(f"❌ Missing Vegetation Records ({len(subplots_without_veg)})", expanded=False):
                            st.caption("Subplots with geometry data but no vegetation records")

                            # Get subplot comments from plots_subplots (raw data)
                            missing_veg_df = pd.DataFrame({
                                "Subplot ID": subplots_without_veg,
                                "Issue": "No vegetation data recorded"
                            })

                            # Get comments from plots_subplots raw data (this is where subplot_comments are stored)
                            if "plots_subplots" in raw_data:
                                plots_df = raw_data["plots_subplots"]
                                if "SUBPLOT_KEY" in plots_df.columns and "subplot_comments" in plots_df.columns:
                                    plots_comments = plots_df[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                    missing_veg_df = missing_veg_df.merge(
                                        plots_comments,
                                        left_on="Subplot ID",
                                        right_on="SUBPLOT_KEY",
                                        how="left"
                                    )
                                    # Drop the duplicate SUBPLOT_KEY column
                                    if "SUBPLOT_KEY" in missing_veg_df.columns:
                                        missing_veg_df = missing_veg_df.drop(columns=["SUBPLOT_KEY"])
                                    # Rename for display
                                    if "subplot_comments" in missing_veg_df.columns:
                                        missing_veg_df["subplot_comments"] = missing_veg_df["subplot_comments"].fillna("—")
                                        missing_veg_df = missing_veg_df.rename(columns={"subplot_comments": "Subplot Comments"})

                            # If subplot_comments column doesn't exist, add it as empty
                            if "Subplot Comments" not in missing_veg_df.columns:
                                missing_veg_df["Subplot Comments"] = "—"

                            st.dataframe(missing_veg_df, use_container_width=True, height=300)

                            # Export option
                            csv_missing = missing_veg_df.to_csv(index=False)
                            st.download_button(
                                "📥 Download Missing Vegetation CSV",
                                data=csv_missing,
                                file_name=f"{config.PARTNER}_{selected_enum}_missing_vegetation.csv",
                                mime="text/csv",
                            )

                    if len(height_outliers_df) > 0:
                        with st.expander(f"📏 Height Outliers ({len(height_outliers_df)})", expanded=False):
                            st.caption("Trees with unusually high or low heights for their species")

                            # Prepare display dataframe
                            display_cols = ["SUBPLOT_KEY", "tree_name", "tree_height_m"]

                            # Add outlier type
                            height_outliers_display = height_outliers_df.copy()
                            height_outliers_display["Outlier_Type"] = height_outliers_display.apply(
                                lambda row: "Too Tall" if row.get("Upper_outliers", False) else "Too Short", axis=1
                            )
                            display_cols.append("Outlier_Type")

                            # Add species if available
                            if species_col and species_col in height_outliers_display.columns:
                                display_cols.append(species_col)

                            # Add subplot comments if available
                            if "subplot_comments" in height_outliers_display.columns:
                                display_cols.append("subplot_comments")

                            # Add submission date if available
                            if "SubmissionDate" in height_outliers_display.columns:
                                display_cols.append("SubmissionDate")

                            available_cols = [c for c in display_cols if c in height_outliers_display.columns]
                            st.dataframe(
                                height_outliers_display[available_cols],
                                use_container_width=True,
                                height=300
                            )

                            # Export option
                            csv_height = height_outliers_display[available_cols].to_csv(index=False)
                            st.download_button(
                                "📥 Download Height Outliers CSV",
                                data=csv_height,
                                file_name=f"{config.PARTNER}_{selected_enum}_height_outliers.csv",
                                mime="text/csv",
                            )

                    if len(circ_outliers_df) > 0:
                        with st.expander(f"📐 Circumference Outliers ({len(circ_outliers_df)})", expanded=False):
                            st.caption("Trees with unusually large or small circumferences for their species")

                            # Prepare display dataframe
                            display_cols = ["SUBPLOT_KEY", "tree_name"]

                            circ_outliers_display = circ_outliers_df.copy()

                            # Add circumference values
                            for col in ["circumference_bh", "circumference_10cm"]:
                                if col in circ_outliers_display.columns:
                                    display_cols.append(col)

                            # Add outlier type
                            circ_outliers_display["Outlier_Type"] = circ_outliers_display.apply(
                                lambda row: "Too Large" if row.get("Upper_outliers", False) else "Too Small", axis=1
                            )
                            display_cols.append("Outlier_Type")

                            # Add species if available
                            if species_col and species_col in circ_outliers_display.columns:
                                display_cols.append(species_col)

                            # Add subplot comments if available
                            if "subplot_comments" in circ_outliers_display.columns:
                                display_cols.append("subplot_comments")

                            # Add submission date if available
                            if "SubmissionDate" in circ_outliers_display.columns:
                                display_cols.append("SubmissionDate")

                            available_cols = [c for c in display_cols if c in circ_outliers_display.columns]
                            st.dataframe(
                                circ_outliers_display[available_cols],
                                use_container_width=True,
                                height=300
                            )

                            # Export option
                            csv_circ = circ_outliers_display[available_cols].to_csv(index=False)
                            st.download_button(
                                "📥 Download Circumference Outliers CSV",
                                data=csv_circ,
                                file_name=f"{config.PARTNER}_{selected_enum}_circ_outliers.csv",
                                mime="text/csv",
                            )

                    if len(suspicious_circ_df) > 0:
                        with st.expander(f"⚠️ Suspicious Circumference by Age ({len(suspicious_circ_df)})", expanded=False):
                            st.caption("Trees with circumference values inconsistent with their age")

                            # Prepare display dataframe
                            display_cols = ["SUBPLOT_KEY", "tree_name", "tree_age"]

                            suspicious_display = suspicious_circ_df.copy()

                            # Add circumference values
                            for col in ["circumference_bh", "circumference_10cm"]:
                                if col in suspicious_display.columns:
                                    display_cols.append(col)

                            # Add year planted if available
                            if "tree_year_planted" in suspicious_display.columns:
                                display_cols.append("tree_year_planted")

                            # Add species if available
                            if species_col and species_col in suspicious_display.columns:
                                display_cols.append(species_col)

                            # Add subplot comments if available
                            if "subplot_comments" in suspicious_display.columns:
                                display_cols.append("subplot_comments")

                            # Add submission date if available
                            if "SubmissionDate" in suspicious_display.columns:
                                display_cols.append("SubmissionDate")

                            available_cols = [c for c in display_cols if c in suspicious_display.columns]
                            st.dataframe(
                                suspicious_display[available_cols],
                                use_container_width=True,
                                height=300
                            )

                            # Export option
                            csv_susp = suspicious_display[available_cols].to_csv(index=False)
                            st.download_button(
                                "📥 Download Suspicious Circ/Age CSV",
                                data=csv_susp,
                                file_name=f"{config.PARTNER}_{selected_enum}_suspicious_circ_age.csv",
                                mime="text/csv",
                            )

                    # Overall summary
                    total_veg_issues = (
                        len(subplots_without_veg) +
                        len(height_outliers_df) +
                        len(circ_outliers_df) +
                        len(suspicious_circ_df)
                    )

                    if total_veg_issues == 0:
                        st.success(f"✅ No vegetation errors found for {selected_enum}")
                else:
                    st.info("No vegetation measurement data available")

            except Exception as e:
                st.error(f"Error loading vegetation error details: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.info("Vegetation data not available in this dataset")

        # ============================================
        # EXPORT OPTIONS
        # ============================================

        st.markdown("---")
        st.markdown("#### 📥 Export Options")

        col1, col2, col3 = st.columns(3)

        # CSV Export
        with col1:
            st.markdown("##### 📊 CSV Export")
            st.caption("All subplot data")

            if len(enum_data) > 0:
                csv_data = enum_data.drop(columns=["geometry"], errors="ignore").to_csv(
                    index=False
                )
                st.download_button(
                    "📊 Download CSV",
                    data=csv_data,
                    file_name=f"{config.PARTNER}_{selected_enum}_subplots.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        # PDF Export
        with col2:
            st.markdown("##### 📄 PDF Report")
            st.caption("Formatted summary report")

            if len(enum_data) > 0:
                try:
                    pdf_buffer = generate_enhanced_pdf_report(
                        enum_data, selected_enum, config.PARTNER, raw_data
                    )

                    if pdf_buffer:
                        st.download_button(
                            "📄 Download PDF",
                            data=pdf_buffer,
                            file_name=f"{config.PARTNER}_{selected_enum}_report.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                        )
                    else:
                        st.info("📦 Install reportlab:\n`pip install reportlab`")
                except Exception as e:
                    st.error(f"PDF generation error: {e}")
                    st.caption("Install: `pip install reportlab`")

        # GeoJSON Export
        with col3:
            st.markdown("##### 🗺️ GeoJSON Export")
            st.caption("Geographic data format")

            if len(enum_data) > 0:
                geojson_data = export_to_geojson(enum_data, selected_enum)

                if geojson_data:
                    st.download_button(
                        "🗺️ Download GeoJSON",
                        data=geojson_data,
                        file_name=f"{config.PARTNER}_{selected_enum}_subplots.geojson",
                        mime="application/geo+json",
                        use_container_width=True,
                    )
                else:
                    st.info("No geometry data available")

        # Export errors only
        if len(invalid_data) > 0:
            st.markdown("---")
            st.markdown("##### ⚠️ Export Errors Only")

            col1, col2 = st.columns(2)

            with col1:
                csv_errors = invalid_data.drop(
                    columns=["geometry"], errors="ignore"
                ).to_csv(index=False)
                st.download_button(
                    "📊 Download Errors CSV",
                    data=csv_errors,
                    file_name=f"{config.PARTNER}_{selected_enum}_errors.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with col2:
                geojson_errors = export_to_geojson(invalid_data, selected_enum)
                if geojson_errors:
                    st.download_button(
                        "🗺️ Download Errors GeoJSON",
                        data=geojson_errors,
                        file_name=f"{config.PARTNER}_{selected_enum}_errors.geojson",
                        mime="application/geo+json",
                        use_container_width=True,
                    )
