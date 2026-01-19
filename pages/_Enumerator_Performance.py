"""
Enumerator Performance Analysis - Error-focused quality control
Enhanced with: Interactive maps (Folium), PDF export, GeoJSON export
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import re
import config
from ui.components import show_header, show_sidebar_info, create_sidebar_filters


def get_total_measured_subplots(gdf):
    """
    Calculate total measured subplots using the measured_subplots field.
    Falls back to counting records if field is not available.

    Args:
        gdf: GeoDataFrame with subplot data

    Returns:
        int: Total measured subplots
    """
    if "measured_subplots" in gdf.columns and "PLOT_KEY" in gdf.columns:
        # Group by plot and sum measured_subplots (taking first value per plot since it's the same for all subplots)
        total = gdf.groupby("PLOT_KEY")["measured_subplots"].first().apply(lambda x: int(x) if pd.notna(x) else 0).sum()
        return int(total)
    else:
        # Fallback: count subplot records
        return len(gdf)


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

    matplotlib.use("Agg")  # Use non-interactive backend
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
st.caption("Analyzes data quality metrics by individual enumerator. Use this to identify enumerators who may need additional training, equipment checks, or supervision. Compare error rates, review specific error types, and export individual performance reports for team management.")

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# Apply filters first (shows date filter at top of sidebar)
gdf_subplots = create_sidebar_filters(gdf_subplots)

# Show sidebar info (partner and data status)
show_sidebar_info()

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

        # Create map with Satellite as default
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=13,
            tiles=None,
        )

        # Add tile layers - Google Hybrid as default (show=True), OpenStreetMap as option
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google",
            name="Satellite",
            show=True,
        ).add_to(m)
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)

        # Create feature groups
        valid_group = folium.FeatureGroup(name="✅ Valid Subplots", show=True)
        invalid_group = folium.FeatureGroup(name="❌ Invalid Subplots", show=True)

        # Add subplots to map
        for idx, row in map_data.iterrows():
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

            # Create detailed popup HTML
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
                    <tr>
                        <td style="padding: 4px; font-weight: bold; width: 40%;">Subplot ID:</td>
                        <td style="padding: 4px;">{row.get("subplot_id", "N/A")}</td>
                    </tr>
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 4px; font-weight: bold;">Enumerator:</td>
                        <td style="padding: 4px;">{row.get("enumerator", "N/A")}</td>
                    </tr>
                    <tr>
                        <td style="padding: 4px; font-weight: bold;">Area:</td>
                        <td style="padding: 4px;">{row.get("area_m2", 0):.1f} m²</td>
                    </tr>
                    <tr style="background-color: #f5f5f5;">
                        <td style="padding: 4px; font-weight: bold;">Vertices:</td>
                        <td style="padding: 4px;">{row.get("nr_vertices", 0)}</td>
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
        total_measured = get_total_measured_subplots(map_data)
        valid_count = map_data["geom_valid"].sum()
        invalid_count = (~map_data["geom_valid"]).sum()
        valid_pct = (valid_count / total_measured * 100) if total_measured > 0 else 0

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
                <b>Total Subplots:</b> {total_measured}<br>
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
        from PIL import Image, ImageDraw, ImageFont
        from io import BytesIO

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
            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                map_obj.save(f.name)
                temp_html = f.name

            # Create output directory
            temp_dir = tempfile.gettempdir()
            output_file = "folium_map_snapshot.png"

            # Initialize Html2Image
            hti = Html2Image(output_path=temp_dir)

            # Capture screenshot
            hti.screenshot(html_file=temp_html, save_as=output_file, size=(1200, 800))

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

        except Exception:
            # Clean up on error
            try:
                if "temp_html" in locals() and os.path.exists(temp_html):
                    os.unlink(temp_html)
                if "output_path" in locals() and os.path.exists(output_path):
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

            with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
                map_obj.save(f.name)
                temp_file = f.name

            driver = webdriver.Chrome(options=chrome_options)
            driver.get(f"file://{temp_file}")
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

            matplotlib.use("Agg")  # Non-interactive backend
            import matplotlib.pyplot as plt

            # Filter valid geometries
            map_data = enum_data[~enum_data.geometry.is_empty].copy()
            if len(map_data) == 0:
                return None

            # Count valid/invalid
            total_count = get_total_measured_subplots(map_data)
            valid_count = map_data["geom_valid"].sum()
            invalid_count = (~map_data["geom_valid"]).sum()

            # Create figure with high DPI for quality
            fig, ax = plt.subplots(figsize=(12, 8), dpi=100)
            fig.patch.set_facecolor("white")

            # Extract coordinates for valid and invalid subplots
            valid_data = map_data[map_data["geom_valid"]]
            invalid_data = map_data[~map_data["geom_valid"]]

            # Plot subplot polygons or points
            for idx, row in valid_data.iterrows():
                geom = row["geometry"]
                if geom.geom_type == "Polygon":
                    # Plot polygon outline
                    x, y = geom.exterior.xy
                    ax.fill(x, y, color="#4CAF50", alpha=0.3, edgecolor="#2E7D32", linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#2E7D32",
                        markersize=8,
                        markeredgecolor="white",
                        markeredgewidth=1,
                    )
                elif geom.geom_type == "MultiPolygon":
                    # Plot each polygon in the multipolygon
                    for poly in geom.geoms:
                        x, y = poly.exterior.xy
                        ax.fill(x, y, color="#4CAF50", alpha=0.3, edgecolor="#2E7D32", linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#2E7D32",
                        markersize=8,
                        markeredgecolor="white",
                        markeredgewidth=1,
                    )
                else:
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#4CAF50",
                        markersize=10,
                        markeredgecolor="white",
                        markeredgewidth=2,
                    )

            for idx, row in invalid_data.iterrows():
                geom = row["geometry"]
                if geom.geom_type == "Polygon":
                    # Plot polygon outline
                    x, y = geom.exterior.xy
                    ax.fill(x, y, color="#F44336", alpha=0.3, edgecolor="#C62828", linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#C62828",
                        markersize=8,
                        markeredgecolor="white",
                        markeredgewidth=1,
                    )
                elif geom.geom_type == "MultiPolygon":
                    # Plot each polygon in the multipolygon
                    for poly in geom.geoms:
                        x, y = poly.exterior.xy
                        ax.fill(x, y, color="#F44336", alpha=0.3, edgecolor="#C62828", linewidth=1.5)
                    # Add centroid marker
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#C62828",
                        markersize=8,
                        markeredgecolor="white",
                        markeredgewidth=1,
                    )
                else:
                    centroid = geom.centroid
                    ax.plot(
                        centroid.x,
                        centroid.y,
                        "o",
                        color="#F44336",
                        markersize=10,
                        markeredgecolor="white",
                        markeredgewidth=2,
                    )

            # Set title
            ax.set_title(
                f"Geographic Distribution - {enumerator_name}", fontsize=18, fontweight="bold", color="#1565C0", pad=20
            )

            # Set labels
            ax.set_xlabel("Longitude", fontsize=12, fontweight="bold")
            ax.set_ylabel("Latitude", fontsize=12, fontweight="bold")

            # Add grid
            ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
            ax.set_axisbelow(True)

            # Equal aspect ratio for proper geographic display
            ax.set_aspect("equal", adjustable="box")

            # Add legend
            from matplotlib.patches import Patch

            legend_elements = [
                Patch(facecolor="#4CAF50", edgecolor="#2E7D32", label=f"Valid Subplots ({valid_count})"),
                Patch(facecolor="#F44336", edgecolor="#C62828", label=f"Invalid Subplots ({invalid_count})"),
            ]
            ax.legend(handles=legend_elements, loc="upper right", fontsize=11, framealpha=0.95)

            # Add statistics text box
            success_rate = (valid_count / total_count * 100) if total_count > 0 else 0

            stats_text = f"Total Subplots: {total_count}\n"
            stats_text += f"Valid: {valid_count} ({success_rate:.1f}%)\n"
            stats_text += f"Invalid: {invalid_count} ({100 - success_rate:.1f}%)"

            # Position text box in lower left
            ax.text(
                0.02,
                0.02,
                stats_text,
                transform=ax.transAxes,
                fontsize=10,
                verticalalignment="bottom",
                bbox=dict(boxstyle="round", facecolor="white", edgecolor="#1565C0", linewidth=2, alpha=0.95),
            )

            # Tight layout
            plt.tight_layout()

            # Convert to PIL Image
            buf = BytesIO()
            plt.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="white")
            buf.seek(0)
            img = Image.open(buf)
            plt.close(fig)

            return img

        except Exception:
            # Fallback to PIL-only version if matplotlib fails
            try:
                from PIL import Image, ImageDraw, ImageFont

                # Filter valid geometries
                map_data = enum_data[~enum_data.geometry.is_empty].copy()
                if len(map_data) == 0:
                    return None

                # Count valid/invalid
                total_count = get_total_measured_subplots(map_data)
                valid_count = map_data["geom_valid"].sum()
                invalid_count = (~map_data["geom_valid"]).sum()

                # Create simple statistics graphic
                width, height = 800, 600
                img = Image.new("RGB", (width, height), color="#F5F5F5")
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
                draw.text(((width - title_width) // 2, 40), title, fill="#1565C0", font=title_font)

                # Draw statistics box
                box_y = 120
                box_height = 350
                draw.rectangle([100, box_y, width - 100, box_y + box_height], fill="white", outline="#1565C0", width=3)

                # Draw statistics
                y_pos = box_y + 60

                # Total subplots
                draw.text((width // 2 - 150, y_pos), "Total Subplots:", fill="#333333", font=text_font)
                draw.text((width // 2 + 50, y_pos), f"{total_count}", fill="#1565C0", font=text_font)
                y_pos += 80

                # Valid subplots (green)
                draw.rectangle([width // 2 - 180, y_pos - 5, width // 2 - 160, y_pos + 20], fill="#4CAF50")
                draw.text((width // 2 - 150, y_pos), "Valid Subplots:", fill="#333333", font=text_font)
                draw.text((width // 2 + 50, y_pos), f"{valid_count}", fill="#4CAF50", font=text_font)
                y_pos += 80

                # Invalid subplots (red)
                draw.rectangle([width // 2 - 180, y_pos - 5, width // 2 - 160, y_pos + 20], fill="#F44336")
                draw.text((width // 2 - 150, y_pos), "Invalid Subplots:", fill="#333333", font=text_font)
                draw.text((width // 2 + 50, y_pos), f"{invalid_count}", fill="#F44336", font=text_font)
                y_pos += 80

                # Success rate
                success_rate = (valid_count / total_count * 100) if total_count > 0 else 0
                draw.text((width // 2 - 150, y_pos), "Success Rate:", fill="#333333", font=text_font)
                color = "#4CAF50" if success_rate >= 85 else "#F44336"
                draw.text((width // 2 + 50, y_pos), f"{success_rate:.1f}%", fill=color, font=text_font)

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

        matplotlib.use("Agg")  # Use non-interactive backend
        import matplotlib.pyplot as plt
        from PIL import Image
        from io import BytesIO

        subplot_id = subplot_row.get("subplot_id", "Unknown")
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

        print(
            f"DEBUG POLYGON: Creating polygon image for subplot {subplot_id}, geom_type: {geom.geom_type}, valid: {is_valid}",
            file=sys.stderr,
        )

        # Create figure
        fig, ax = plt.subplots(figsize=(4, 3), dpi=100)

        # Plot the polygon
        if geom.geom_type == "Polygon":
            x, y = geom.exterior.xy
            color = "#F44336" if not is_valid else "#4CAF50"
            ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
            ax.plot(x, y, "o", color=color, markersize=4)

            # Add centroid
            centroid = geom.centroid
            ax.plot(centroid.x, centroid.y, "x", color="black", markersize=8, markeredgewidth=2)
        elif geom.geom_type == "MultiPolygon":
            color = "#F44336" if not is_valid else "#4CAF50"
            # Plot each polygon in the multipolygon
            for poly in geom.geoms:
                x, y = poly.exterior.xy
                ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                ax.plot(x, y, "o", color=color, markersize=4)

            # Add centroid
            centroid = geom.centroid
            ax.plot(centroid.x, centroid.y, "x", color="black", markersize=8, markeredgewidth=2)

        # Formatting
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
        ax.set_xlabel("Longitude", fontsize=8)
        ax.set_ylabel("Latitude", fontsize=8)
        ax.tick_params(labelsize=7)

        # Title
        subplot_id = str(subplot_row.get("subplot_id", "Unknown"))
        if len(subplot_id) > 35:
            subplot_id = subplot_id[:32] + "..."
        status = "INVALID" if not is_valid else "VALID"
        ax.set_title(f"{subplot_id}\n{status}", fontsize=9, fontweight="bold")

        # Add area and vertices info
        info_text = []
        if "area_m2" in subplot_row and pd.notna(subplot_row["area_m2"]):
            info_text.append(f"Area: {subplot_row['area_m2']:.1f} m²")
        if "nr_vertices" in subplot_row and pd.notna(subplot_row["nr_vertices"]):
            info_text.append(f"Vertices: {int(subplot_row['nr_vertices'])}")

        if info_text:
            ax.text(0.5, -0.15, " | ".join(info_text), transform=ax.transAxes, ha="center", fontsize=7, style="italic")

        plt.tight_layout()

        # Convert to PIL Image
        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=100, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)

        # Create a copy of the image before the buffer is closed
        img = Image.open(buf)
        img_copy = img.copy()
        img.close()

        print("DEBUG: Successfully created polygon image", file=sys.stderr)
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
            print("DEBUG PDF: Adding SubmissionDate from raw_data", file=sys.stderr)
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

            print(
                f"DEBUG PDF: Found submission_date_col: {submission_date_col}, subplot_key_col: {subplot_key_col}",
                file=sys.stderr,
            )

            if submission_date_col and subplot_key_col:
                # Create mapping from subplot_id to SubmissionDate
                date_mapping = plots_df[[subplot_key_col, submission_date_col]].drop_duplicates()
                date_mapping = date_mapping.rename(columns={submission_date_col: "SubmissionDate"})

                # Drop subplot_key_col from enum_data if it exists to avoid duplicate column issues
                if subplot_key_col in enum_data.columns and subplot_key_col != "subplot_id":
                    enum_data = enum_data.drop(columns=[subplot_key_col])

                # Merge into enum_data
                enum_data = enum_data.merge(
                    date_mapping, left_on="subplot_id", right_on=subplot_key_col, how="left", suffixes=("", "_drop")
                )

                # Drop duplicate subplot key column if it was added
                if subplot_key_col in enum_data.columns and subplot_key_col != "subplot_id":
                    enum_data = enum_data.drop(columns=[subplot_key_col])

                # Drop any columns with '_drop' suffix that may have been created
                drop_cols = [col for col in enum_data.columns if col.endswith("_drop")]
                if drop_cols:
                    enum_data = enum_data.drop(columns=drop_cols)

                print(
                    f"DEBUG PDF: Added SubmissionDate, now has {enum_data['SubmissionDate'].notna().sum()} dates",
                    file=sys.stderr,
                )
            else:
                print("DEBUG PDF: Could not find required columns in plots_df", file=sys.stderr)
        else:
            if "SubmissionDate" in enum_data.columns:
                print("DEBUG PDF: SubmissionDate already in enum_data", file=sys.stderr)
            else:
                print("DEBUG PDF: No raw_data or plots_subplots available to add SubmissionDate", file=sys.stderr)

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
                                if (
                                    len(veg_data_for_comments) > 0
                                    and "SUBPLOT_KEY" in veg_data_for_comments.columns
                                    and "SUBPLOT_KEY" in meas_enum.columns
                                ):
                                    if "subplot_comments" in veg_data_for_comments.columns:
                                        veg_comments = veg_data_for_comments[
                                            ["SUBPLOT_KEY", "subplot_comments"]
                                        ].drop_duplicates()
                                        meas_enum = meas_enum.merge(
                                            veg_comments, on="SUBPLOT_KEY", how="left", suffixes=("", "_veg")
                                        )
                                        print("DEBUG: Merged subplot_comments for PDF", file=sys.stderr)

                            # Merge with enumerator info
                            meas_enum = merge_with_enumerator(meas_enum, enum_data)
                            species_col = get_species_column(meas_enum)
                            print(f"DEBUG: Species column: {species_col}", file=sys.stderr)

                            # Run validation checks
                            veg_errors = {
                                "height_outliers": pd.DataFrame(),
                                "circ_outliers": pd.DataFrame(),
                                "suspicious_circ": pd.DataFrame(),
                                "super_tall_trees": pd.DataFrame(),
                                "high_stems": pd.DataFrame(),
                                "unknown_species": pd.DataFrame(),
                            }

                            # Height outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                            if "tree_height_m" in meas_enum.columns and "VEGETATION_KEY" in meas_enum.columns:
                                print("DEBUG: Checking height outliers...", file=sys.stderr)
                                # Filter to records with valid height and VEGETATION_KEY
                                height_check = meas_enum[
                                    meas_enum["tree_height_m"].notna() & meas_enum["VEGETATION_KEY"].notna()
                                ].copy()

                                if len(height_check) > 0:
                                    # Calculate median height per VEGETATION_KEY (tree group)
                                    median_check = (
                                        height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                                        .median()
                                        .reset_index(name="median_height")
                                    )

                                    # Merge with original data
                                    height_total = pd.merge(
                                        height_check, median_check, how="inner", on="VEGETATION_KEY"
                                    )

                                    # Apply outlier detection (4x and 1/4x median - Rabobank methodology)
                                    height_total["Upper_outliers"] = height_total.apply(
                                        lambda row: (
                                            "outlier" if row["tree_height_m"] > (row["median_height"] * 4) else "ok"
                                        ),
                                        axis=1,
                                    )
                                    height_total["Lower_outliers"] = height_total.apply(
                                        lambda row: (
                                            "outlier" if row["tree_height_m"] < (row["median_height"] / 4) else "ok"
                                        ),
                                        axis=1,
                                    )

                                    # Filter to outliers only
                                    outliers = height_total[
                                        (height_total["Upper_outliers"] == "outlier")
                                        | (height_total["Lower_outliers"] == "outlier")
                                    ].copy()

                                    print(f"DEBUG: Found {len(outliers)} height outliers", file=sys.stderr)
                                    print(
                                        f"DEBUG: Height outliers columns: {outliers.columns.tolist()}", file=sys.stderr
                                    )
                                    print(f"DEBUG: meas_enum columns: {meas_enum.columns.tolist()}", file=sys.stderr)
                                    print(
                                        f"DEBUG: Has SubmissionDate in outliers: {'SubmissionDate' in outliers.columns}",
                                        file=sys.stderr,
                                    )
                                    print(
                                        f"DEBUG: Has SubmissionDate_subplot in outliers: {'SubmissionDate_subplot' in outliers.columns}",
                                        file=sys.stderr,
                                    )

                                    # Rename SubmissionDate_subplot to SubmissionDate for consistency
                                    if (
                                        "SubmissionDate_subplot" in outliers.columns
                                        and "SubmissionDate" not in outliers.columns
                                    ):
                                        outliers = outliers.rename(columns={"SubmissionDate_subplot": "SubmissionDate"})
                                        print(
                                            "DEBUG: Renamed SubmissionDate_subplot to SubmissionDate", file=sys.stderr
                                        )

                                    # Check if SubmissionDate is missing and add it if needed
                                    if "SubmissionDate" not in outliers.columns:
                                        print("DEBUG: Adding SubmissionDate to height outliers", file=sys.stderr)
                                        # Add SubmissionDate from meas_enum based on a measurement key
                                        # Use MEASUREMENT_KEY or VEGETATION_KEY as the join key
                                        if (
                                            "MEASUREMENT_KEY" in outliers.columns
                                            and "MEASUREMENT_KEY" in meas_enum.columns
                                        ):
                                            date_map = meas_enum[["MEASUREMENT_KEY", "SubmissionDate"]].drop_duplicates(
                                                subset=["MEASUREMENT_KEY"]
                                            )
                                            outliers = outliers.merge(date_map, on="MEASUREMENT_KEY", how="left")
                                            print("DEBUG: Merged SubmissionDate using MEASUREMENT_KEY", file=sys.stderr)
                                        elif (
                                            "VEGETATION_KEY" in outliers.columns
                                            and "VEGETATION_KEY" in meas_enum.columns
                                        ):
                                            # Group by VEGETATION_KEY and take first SubmissionDate
                                            date_map = meas_enum[["VEGETATION_KEY", "SubmissionDate"]].drop_duplicates(
                                                subset=["VEGETATION_KEY"]
                                            )
                                            outliers = outliers.merge(date_map, on="VEGETATION_KEY", how="left")
                                            print("DEBUG: Merged SubmissionDate using VEGETATION_KEY", file=sys.stderr)

                                    print(
                                        f"DEBUG: After merge, has SubmissionDate: {'SubmissionDate' in outliers.columns}",
                                        file=sys.stderr,
                                    )
                                    if "SubmissionDate" in outliers.columns:
                                        print(
                                            f"DEBUG: SubmissionDate sample: {outliers['SubmissionDate'].head(2).tolist()}",
                                            file=sys.stderr,
                                        )

                                    veg_errors["height_outliers"] = outliers
                                    total_veg_errors += len(outliers)

                            # Circumference outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                            circ_cols = [
                                c for c in ["circumference_bh", "circumference_10cm"] if c in meas_enum.columns
                            ]
                            print(f"DEBUG: Circumference columns: {circ_cols}", file=sys.stderr)
                            if circ_cols and "VEGETATION_KEY" in meas_enum.columns:
                                for circ_col in circ_cols:
                                    print(f"DEBUG: Checking circumference outliers for {circ_col}...", file=sys.stderr)
                                    # Filter to records with valid circumference and VEGETATION_KEY
                                    circ_check = meas_enum[
                                        meas_enum[circ_col].notna() & meas_enum["VEGETATION_KEY"].notna()
                                    ].copy()

                                    if len(circ_check) > 0:
                                        # Calculate median circumference per VEGETATION_KEY (tree group)
                                        median_check = (
                                            circ_check.groupby("VEGETATION_KEY")[circ_col]
                                            .median()
                                            .reset_index(name="median_circ")
                                        )

                                        # Merge with original data
                                        circ_total = pd.merge(
                                            circ_check, median_check, how="inner", on="VEGETATION_KEY"
                                        )

                                        # Apply outlier detection (4x and 1/4x median - Rabobank methodology)
                                        circ_total["Upper_outliers"] = circ_total.apply(
                                            lambda row: (
                                                "outlier" if row[circ_col] > (row["median_circ"] * 4) else "ok"
                                            ),
                                            axis=1,
                                        )
                                        circ_total["Lower_outliers"] = circ_total.apply(
                                            lambda row: (
                                                "outlier" if row[circ_col] < (row["median_circ"] / 4) else "ok"
                                            ),
                                            axis=1,
                                        )

                                        # Filter to outliers only
                                        outliers = circ_total[
                                            (circ_total["Upper_outliers"] == "outlier")
                                            | (circ_total["Lower_outliers"] == "outlier")
                                        ].copy()

                                        print(
                                            f"DEBUG: Found {len(outliers)} circumference outliers for {circ_col}",
                                            file=sys.stderr,
                                        )
                                        if len(outliers) > 0:
                                            # Rename SubmissionDate_subplot to SubmissionDate for consistency
                                            if (
                                                "SubmissionDate_subplot" in outliers.columns
                                                and "SubmissionDate" not in outliers.columns
                                            ):
                                                outliers = outliers.rename(
                                                    columns={"SubmissionDate_subplot": "SubmissionDate"}
                                                )
                                                print(
                                                    "DEBUG: Renamed SubmissionDate_subplot to SubmissionDate for circ outliers",
                                                    file=sys.stderr,
                                                )

                                            # Check if SubmissionDate is missing and add it if needed
                                            if (
                                                "SubmissionDate" not in outliers.columns
                                                and "SubmissionDate" in meas_enum.columns
                                            ):
                                                print("DEBUG: Adding SubmissionDate to circ outliers", file=sys.stderr)
                                                if (
                                                    "MEASUREMENT_KEY" in outliers.columns
                                                    and "MEASUREMENT_KEY" in meas_enum.columns
                                                ):
                                                    date_map = meas_enum[
                                                        ["MEASUREMENT_KEY", "SubmissionDate"]
                                                    ].drop_duplicates(subset=["MEASUREMENT_KEY"])
                                                    outliers = outliers.merge(
                                                        date_map, on="MEASUREMENT_KEY", how="left"
                                                    )
                                                elif (
                                                    "VEGETATION_KEY" in outliers.columns
                                                    and "VEGETATION_KEY" in meas_enum.columns
                                                ):
                                                    date_map = meas_enum[
                                                        ["VEGETATION_KEY", "SubmissionDate"]
                                                    ].drop_duplicates(subset=["VEGETATION_KEY"])
                                                    outliers = outliers.merge(date_map, on="VEGETATION_KEY", how="left")

                                            veg_errors["circ_outliers"] = pd.concat(
                                                [veg_errors["circ_outliers"], outliers]
                                            ).drop_duplicates()

                                total_veg_errors += len(veg_errors["circ_outliers"])
                                print(
                                    f"DEBUG: Total circumference outliers: {len(veg_errors['circ_outliers'])}",
                                    file=sys.stderr,
                                )

                            # Suspicious circumference by age
                            if "tree_year_planted" in meas_enum.columns and circ_cols:
                                print("DEBUG: Checking suspicious circumference by age...", file=sys.stderr)
                                from utils.data_merge_utils import calculate_tree_age

                                meas_with_age = calculate_tree_age(meas_enum)
                                if "tree_age" in meas_with_age.columns:
                                    susp_circ = detect_suspicious_circumference_by_age(meas_with_age)
                                    if "flag" in susp_circ.columns:
                                        flagged = susp_circ[susp_circ["flag"] == True]
                                        print(
                                            f"DEBUG: Found {len(flagged)} suspicious circ/age records", file=sys.stderr
                                        )

                                        # Rename SubmissionDate_subplot to SubmissionDate for consistency
                                        if (
                                            "SubmissionDate_subplot" in flagged.columns
                                            and "SubmissionDate" not in flagged.columns
                                        ):
                                            flagged = flagged.rename(
                                                columns={"SubmissionDate_subplot": "SubmissionDate"}
                                            )
                                            print(
                                                "DEBUG: Renamed SubmissionDate_subplot to SubmissionDate for suspicious circ",
                                                file=sys.stderr,
                                            )

                                        # Check if SubmissionDate is missing and add it if needed
                                        if (
                                            "SubmissionDate" not in flagged.columns
                                            and "SubmissionDate" in meas_with_age.columns
                                        ):
                                            print("DEBUG: Adding SubmissionDate to suspicious circ", file=sys.stderr)
                                            if (
                                                "MEASUREMENT_KEY" in flagged.columns
                                                and "MEASUREMENT_KEY" in meas_with_age.columns
                                            ):
                                                date_map = meas_with_age[
                                                    ["MEASUREMENT_KEY", "SubmissionDate"]
                                                ].drop_duplicates(subset=["MEASUREMENT_KEY"])
                                                flagged = flagged.merge(date_map, on="MEASUREMENT_KEY", how="left")

                                        veg_errors["suspicious_circ"] = flagged
                                        total_veg_errors += len(flagged)

                            # Super Tall Trees (>25m)
                            if "tree_height_m" in meas_enum.columns:
                                print("DEBUG: Checking super tall trees...", file=sys.stderr)
                                super_tall = meas_enum[meas_enum["tree_height_m"] > 25].copy()
                                if len(super_tall) > 0:
                                    print(f"DEBUG: Found {len(super_tall)} super tall trees", file=sys.stderr)

                                    # Rename SubmissionDate_subplot to SubmissionDate for consistency
                                    if (
                                        "SubmissionDate_subplot" in super_tall.columns
                                        and "SubmissionDate" not in super_tall.columns
                                    ):
                                        super_tall = super_tall.rename(
                                            columns={"SubmissionDate_subplot": "SubmissionDate"}
                                        )
                                        print(
                                            "DEBUG: Renamed SubmissionDate_subplot to SubmissionDate for super tall trees",
                                            file=sys.stderr,
                                        )

                                    veg_errors["super_tall_trees"] = super_tall
                                    total_veg_errors += len(super_tall)

                            # High Stem Counts (>20)
                            if "nr_stems_bh" in meas_enum.columns:
                                print("DEBUG: Checking high stem counts...", file=sys.stderr)
                                high_stems = meas_enum[meas_enum["nr_stems_bh"] > 20].copy()
                                if len(high_stems) > 0:
                                    print(f"DEBUG: Found {len(high_stems)} high stem counts", file=sys.stderr)

                                    # Rename SubmissionDate_subplot to SubmissionDate for consistency
                                    if (
                                        "SubmissionDate_subplot" in high_stems.columns
                                        and "SubmissionDate" not in high_stems.columns
                                    ):
                                        high_stems = high_stems.rename(
                                            columns={"SubmissionDate_subplot": "SubmissionDate"}
                                        )
                                        print(
                                            "DEBUG: Renamed SubmissionDate_subplot to SubmissionDate for high stems",
                                            file=sys.stderr,
                                        )

                                    veg_errors["high_stems"] = high_stems
                                    total_veg_errors += len(high_stems)

                            # Unknown/Unidentified Species
                            if "plots_subplots_vegetation" in raw_data:
                                from utils.vegetation_validation import check_unidentified_species

                                veg_df = raw_data["plots_subplots_vegetation"]
                                enum_subplot_keys = enum_data["subplot_id"].unique()
                                veg_enum = (
                                    veg_df[veg_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()
                                    if "SUBPLOT_KEY" in veg_df.columns
                                    else pd.DataFrame()
                                )

                                if len(veg_enum) > 0:
                                    print("DEBUG: Checking unknown species...", file=sys.stderr)
                                    unknown_species = check_unidentified_species(veg_enum)
                                    if len(unknown_species) > 0:
                                        print(f"DEBUG: Found {len(unknown_species)} unknown species", file=sys.stderr)
                                        # Add SubmissionDate from enum_data by merging on SUBPLOT_KEY
                                        if (
                                            "SubmissionDate" in enum_data.columns
                                            and "SUBPLOT_KEY" in unknown_species.columns
                                            and "subplot_id" in enum_data.columns
                                        ):
                                            # Create a mapping of subplot_id (from enum_data) to SubmissionDate
                                            date_map = enum_data[["subplot_id", "SubmissionDate"]].drop_duplicates()
                                            date_map = date_map.rename(columns={"subplot_id": "SUBPLOT_KEY"})
                                            unknown_species = unknown_species.merge(
                                                date_map, on="SUBPLOT_KEY", how="left"
                                            )

                                        # Merge with enumerator after adding date
                                        unknown_species = merge_with_enumerator(unknown_species, enum_data)
                                        veg_errors["unknown_species"] = unknown_species
                                        total_veg_errors += len(unknown_species)

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

        print(
            "DEBUG PDF: Skipping Executive Summary and Performance Visualization, going straight to date-wise analysis",
            file=sys.stderr,
        )

        # Date-wise error analysis (GEOMETRY + VEGETATION)
        # Note: veg_errors_data was already calculated earlier for the summary
        print(
            f"DEBUG PDF: Checking for date-wise analysis, SubmissionDate column exists: {'SubmissionDate' in enum_data.columns}",
            file=sys.stderr,
        )
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

                    # CRITICAL: Filter to only subplots that have vegetation data (actual measurements)
                    # Use vegetation data as source of truth instead of measured_subplots field
                    if raw_data and "plots_subplots_vegetation" in raw_data:
                        veg_data = raw_data["plots_subplots_vegetation"]
                        if "SUBPLOT_KEY" in veg_data.columns and "subplot_id" in date_data.columns:
                            veg_subplot_ids = veg_data["SUBPLOT_KEY"].unique()
                            date_data_with_veg = date_data[date_data["subplot_id"].isin(veg_subplot_ids)].copy()

                            if len(date_data_with_veg) > 0:
                                print(
                                    f"DEBUG PDF: Date {date} - Filtered to {len(date_data_with_veg)} subplots with vegetation data",
                                    file=sys.stderr,
                                )
                                date_data = date_data_with_veg
                            else:
                                print(
                                    f"DEBUG PDF: Date {date} - No subplots with vegetation data, using all {len(date_data)}",
                                    file=sys.stderr,
                                )
                        else:
                            print(
                                f"DEBUG PDF: Date {date} - Vegetation data structure issue, using measured_subplots field",
                                file=sys.stderr,
                            )
                            # Fallback: use measured_subplots field
                            if "subplot_id" in date_data.columns and "measured_subplots" in date_data.columns:
                                date_data["subplot_number"] = date_data["subplot_id"].apply(
                                    lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                                    if re.search(r"\[(\d+)\]", str(x))
                                    else 999
                                )
                                date_data["measured_subplots_int"] = date_data["measured_subplots"].apply(
                                    lambda x: int(x) if pd.notna(x) else 999
                                )
                                date_data = date_data[
                                    date_data["subplot_number"] <= date_data["measured_subplots_int"]
                                ].copy()
                                date_data = date_data.drop(
                                    columns=["subplot_number", "measured_subplots_int"], errors="ignore"
                                )
                    else:
                        print(
                            f"DEBUG PDF: Date {date} - No vegetation data available, using measured_subplots field",
                            file=sys.stderr,
                        )
                        # Fallback: use measured_subplots field
                        if "subplot_id" in date_data.columns and "measured_subplots" in date_data.columns:
                            date_data["subplot_number"] = date_data["subplot_id"].apply(
                                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                                if re.search(r"\[(\d+)\]", str(x))
                                else 999
                            )
                            date_data["measured_subplots_int"] = date_data["measured_subplots"].apply(
                                lambda x: int(x) if pd.notna(x) else 999
                            )
                            date_data = date_data[
                                date_data["subplot_number"] <= date_data["measured_subplots_int"]
                            ].copy()
                            date_data = date_data.drop(
                                columns=["subplot_number", "measured_subplots_int"], errors="ignore"
                            )

                    date_total = get_total_measured_subplots(date_data)
                    date_invalid = (~date_data["geom_valid"]).sum()
                    date_valid = date_data["geom_valid"].sum()
                    date_error_rate = (date_invalid / date_total * 100) if date_total > 0 else 0

                    print(
                        f"DEBUG PDF: Date {date} - date_data has {len(date_data)} records after filtering, date_total={date_total}",
                        file=sys.stderr,
                    )

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

                    story.append(
                        Paragraph(
                            f"📅 {date.strftime('%B %d, %Y')} - {date_total} subplots ({date_invalid} errors)",
                            date_header_style,
                        )
                    )

                    # Date summary
                    date_summary_data = [
                        ["Total Subplots", str(date_total)],
                        ["Valid", f"{date_valid} ({date_valid / date_total * 100:.1f}%)"],
                        ["Invalid", f"{date_invalid} ({date_error_rate:.1f}%)"],
                    ]

                    date_summary_table = Table(date_summary_data, colWidths=[2 * inch, 2 * inch])
                    date_summary_table.setStyle(
                        TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E3F2FD")),
                                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                ("PADDING", (0, 0), (-1, -1), 8),
                                ("FONTSIZE", (0, 0), (-1, -1), 10),
                            ]
                        )
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
                        veg_subplot_keys = (
                            veg_data_full["SUBPLOT_KEY"].unique() if "SUBPLOT_KEY" in veg_data_full.columns else []
                        )
                        # Find subplots without vegetation
                        date_missing_veg = [k for k in date_subplot_keys if k not in veg_subplot_keys]

                    print(
                        f"DEBUG PDF: Date {date} - Invalid: {len(date_invalid_data)}, Missing Veg: {len(date_missing_veg)}",
                        file=sys.stderr,
                    )

                    # Create map overviews grouped by GT Plot for this date
                    if len(date_data) > 0 and MATPLOTLIB_AVAILABLE:
                        print(f"DEBUG PDF: date_data columns: {date_data.columns.tolist()}", file=sys.stderr)
                        print(f"DEBUG PDF: PLOT_KEY in columns: {'PLOT_KEY' in date_data.columns}", file=sys.stderr)
                        if "PLOT_KEY" in date_data.columns:
                            print(
                                f"DEBUG PDF: Number of unique GT Plots: {date_data['PLOT_KEY'].nunique()}",
                                file=sys.stderr,
                            )
                            print(f"DEBUG PDF: GT Plot keys: {date_data['PLOT_KEY'].unique()}", file=sys.stderr)

                        # Group by GT Plot (PLOT_KEY)
                        if "PLOT_KEY" in date_data.columns:
                            for plot_key in sorted(date_data["PLOT_KEY"].unique()):
                                plot_data = date_data[date_data["PLOT_KEY"] == plot_key]

                                # Extract plot number from PLOT_KEY
                                plot_display = str(plot_key).split("/")[-1] if "/" in str(plot_key) else str(plot_key)

                                # Count stats for this plot
                                plot_total = len(plot_data)
                                plot_valid = plot_data["geom_valid"].sum()
                                plot_invalid = plot_total - plot_valid

                                try:
                                    print(
                                        f"DEBUG PDF: Creating map for GT Plot {plot_display} with {len(plot_data)} subplots",
                                        file=sys.stderr,
                                    )

                                    fig, ax = plt.subplots(figsize=(5, 3.5), dpi=100)

                                    # Plot all subplots for this GT plot
                                    for idx, row in plot_data.iterrows():
                                        if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                            geom = row["geometry"]
                                            is_valid = row.get("geom_valid", False)
                                            color = "#4CAF50" if is_valid else "#F44336"
                                            alpha = 0.3 if is_valid else 0.6

                                            if geom.geom_type == "Polygon":
                                                x, y = geom.exterior.xy
                                                ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)
                                            elif geom.geom_type == "MultiPolygon":
                                                for poly in geom.geoms:
                                                    x, y = poly.exterior.xy
                                                    ax.fill(
                                                        x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5
                                                    )

                                            # Add label for invalid ones
                                            if not is_valid:
                                                centroid = geom.centroid
                                                ax.plot(centroid.x, centroid.y, "rx", markersize=8, markeredgewidth=2)

                                    ax.set_aspect("equal")
                                    ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
                                    ax.set_xlabel("Longitude", fontsize=8)
                                    ax.set_ylabel("Latitude", fontsize=8)
                                    ax.tick_params(labelsize=8)
                                    ax.set_title(
                                        f"GT Plot: {plot_display} ({date.strftime('%B %d, %Y')})\nSubplots: {plot_total} | Valid: {plot_valid}, Invalid: {plot_invalid}",
                                        fontsize=9,
                                        fontweight="bold",
                                    )

                                    # Add legend
                                    from matplotlib.patches import Patch

                                    legend_elements = [
                                        Patch(facecolor="#4CAF50", alpha=0.5, label=f"Valid ({plot_valid})"),
                                        Patch(facecolor="#F44336", alpha=0.6, label=f"Invalid ({plot_invalid})"),
                                    ]
                                    ax.legend(handles=legend_elements, loc="upper right", fontsize=7)

                                    plt.tight_layout()

                                    # Convert to image for PDF
                                    map_buffer = BytesIO()
                                    plt.savefig(
                                        map_buffer, format="png", dpi=100, bbox_inches="tight", facecolor="white"
                                    )
                                    plt.close(fig)
                                    map_buffer.seek(0)

                                    # Add to PDF
                                    map_img = RLImage(map_buffer, width=4.5 * inch, height=3.2 * inch)
                                    story.append(map_img)
                                    story.append(Spacer(1, 0.15 * inch))
                                    print(
                                        f"DEBUG PDF: Successfully added map for GT Plot {plot_display} to PDF",
                                        file=sys.stderr,
                                    )

                                except Exception as e:
                                    print(
                                        f"DEBUG PDF: Error creating map for GT Plot {plot_display}: {str(e)}",
                                        file=sys.stderr,
                                    )
                                    import traceback

                                    traceback.print_exc(file=sys.stderr)

                            story.append(Spacer(1, 0.2 * inch))
                        else:
                            # Fallback to single overview map if PLOT_KEY not available
                            try:
                                print(
                                    f"DEBUG PDF: Creating map overview for date {date} (no PLOT_KEY column)",
                                    file=sys.stderr,
                                )

                                fig, ax = plt.subplots(figsize=(6, 4), dpi=100)

                                # Plot all subplots for this date
                                for idx, row in date_data.iterrows():
                                    if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                        geom = row["geometry"]
                                        is_valid = row.get("geom_valid", False)
                                        color = "#4CAF50" if is_valid else "#F44336"
                                        alpha = 0.3 if is_valid else 0.6

                                        if geom.geom_type == "Polygon":
                                            x, y = geom.exterior.xy
                                            ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)
                                        elif geom.geom_type == "MultiPolygon":
                                            for poly in geom.geoms:
                                                x, y = poly.exterior.xy
                                                ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)

                                        # Add label for invalid ones
                                        if not is_valid:
                                            centroid = geom.centroid
                                            ax.plot(centroid.x, centroid.y, "rx", markersize=8, markeredgewidth=2)

                                ax.set_aspect("equal")
                                ax.grid(True, alpha=0.3)
                                ax.set_xlabel("Longitude", fontsize=9)
                                ax.set_ylabel("Latitude", fontsize=9)
                                ax.tick_params(labelsize=8)
                                ax.set_title(
                                    f"Subplot Overview - {date.strftime('%B %d, %Y')}\nGreen=Valid, Red=Invalid",
                                    fontsize=10,
                                    fontweight="bold",
                                )

                                plt.tight_layout()

                                # Convert to image for PDF
                                map_buffer = BytesIO()
                                plt.savefig(map_buffer, format="png", dpi=100, bbox_inches="tight", facecolor="white")
                                plt.close(fig)
                                map_buffer.seek(0)

                                # Add to PDF
                                map_img = RLImage(map_buffer, width=5 * inch, height=3.33 * inch)
                                story.append(map_img)
                                story.append(Spacer(1, 0.2 * inch))
                                print("DEBUG PDF: Successfully added map overview to PDF", file=sys.stderr)

                            except Exception as e:
                                print(f"DEBUG PDF: Error creating map overview: {str(e)}", file=sys.stderr)
                                import traceback

                                traceback.print_exc(file=sys.stderr)

                    if len(date_invalid_data) > 0 or len(date_missing_veg) > 0:
                        print(
                            f"DEBUG PDF: Entered date error section, processing {len(date_invalid_data)} invalid subplots",
                            file=sys.stderr,
                        )
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

                        print(
                            f"DEBUG PDF: Starting loop through {len(date_invalid_data)} invalid subplots",
                            file=sys.stderr,
                        )
                        for idx, row in date_invalid_data.iterrows():
                            print(
                                f"DEBUG PDF: Processing subplot {subplot_count + 1}/{len(date_invalid_data)}",
                                file=sys.stderr,
                            )
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
                                    fontStyle="italic",
                                )
                                remaining = len(date_invalid_data) - max_subplots_per_date
                                story.append(
                                    Paragraph(
                                        f"... and {remaining} more invalid subplot(s) for this date", remaining_style
                                    )
                                )
                                break

                            # Subplot header - extract subplot number from UUID
                            subplot_id_full = str(row.get("subplot_id", "N/A"))

                            # Extract subplot number from format: uuid:.../sub_plot[7]
                            match = re.search(r"\[(\d+)\]", subplot_id_full)
                            if match:
                                subplot_display = f"Subplot {match.group(1)}"
                            else:
                                subplot_display = f"Subplot: {subplot_id_full}"

                            subplot_header_style = ParagraphStyle(
                                "SubplotHeader",
                                parent=styles["Heading4"],
                                fontSize=11,
                                textColor=colors.HexColor("#E53935"),
                                spaceBefore=14,
                                spaceAfter=6,
                                fontName="Helvetica-Bold",
                            )
                            story.append(Paragraph(subplot_display, subplot_header_style))

                            # Create a table with polygon image on left, details on right
                            print(
                                f"DEBUG PDF: Attempting to create polygon for subplot {subplot_id_full}",
                                file=sys.stderr,
                            )

                            # Create polygon image directly inline
                            polygon_img_rl = None
                            if MATPLOTLIB_AVAILABLE:
                                try:
                                    if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                        geom = row["geometry"]
                                        is_valid = row.get("geom_valid", False)

                                        fig, ax = plt.subplots(figsize=(3, 2.5), dpi=100)

                                        color = "#4CAF50" if is_valid else "#F44336"

                                        if geom.geom_type == "Polygon":
                                            x, y = geom.exterior.xy
                                            ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                                            ax.plot(x, y, "o", color=color, markersize=3)
                                        elif geom.geom_type == "MultiPolygon":
                                            for poly in geom.geoms:
                                                x, y = poly.exterior.xy
                                                ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                                                ax.plot(x, y, "o", color=color, markersize=3)

                                        # Add centroid
                                        centroid = geom.centroid
                                        ax.plot(
                                            centroid.x, centroid.y, "x", color="black", markersize=6, markeredgewidth=2
                                        )

                                        ax.set_aspect("equal")
                                        ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
                                        ax.set_xlabel("Longitude", fontsize=7)
                                        ax.set_ylabel("Latitude", fontsize=7)
                                        ax.tick_params(labelsize=6)

                                        # Add area info as title
                                        area_text = f"{row.get('area_m2', 0):.1f} m²"
                                        status = "INVALID" if not is_valid else "VALID"
                                        ax.set_title(f"{area_text} - {status}", fontsize=8, fontweight="bold")

                                        plt.tight_layout()

                                        # Convert to image
                                        poly_buffer = BytesIO()
                                        plt.savefig(
                                            poly_buffer, format="png", dpi=100, bbox_inches="tight", facecolor="white"
                                        )
                                        plt.close(fig)
                                        poly_buffer.seek(0)

                                        polygon_img_rl = RLImage(poly_buffer, width=2.5 * inch, height=2.08 * inch)
                                        print("DEBUG PDF: Successfully created polygon image inline", file=sys.stderr)
                                    else:
                                        print("DEBUG PDF: Geometry is None or empty", file=sys.stderr)

                                except Exception as e:
                                    print(f"DEBUG PDF: Error creating polygon inline: {str(e)}", file=sys.stderr)
                                    import traceback

                                    traceback.print_exc(file=sys.stderr)
                            else:
                                print("DEBUG PDF: Matplotlib not available, skipping polygon creation", file=sys.stderr)

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
                                        if "coverage_vegetation" in veg_rec and pd.notna(
                                            veg_rec["coverage_vegetation"]
                                        ):
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
                                        tree_count = len(
                                            subplot_veg[subplot_veg.get("vegetation_type_number", pd.Series()).notna()]
                                        )
                                        if tree_count > 0:
                                            detail_items.append(f"<b>Trees:</b> {tree_count} recorded")

                            # Create detail text
                            detail_text = "<br/>".join(detail_items)
                            detail_para = Paragraph(
                                detail_text,
                                ParagraphStyle(
                                    "Details",
                                    parent=styles["Normal"],
                                    fontSize=9,
                                    leading=11,
                                ),
                            )

                            # Create 2-column table with polygon on left, details on right
                            if polygon_img_rl:
                                detail_table = Table(
                                    [[polygon_img_rl, detail_para]], colWidths=[2.8 * inch, 3.5 * inch]
                                )
                                print("DEBUG PDF: Added 2-column table with polygon", file=sys.stderr)
                            else:
                                detail_table = Table([[detail_para]], colWidths=[6.3 * inch])
                                print("DEBUG PDF: Added 1-column table without polygon", file=sys.stderr)

                            detail_table.setStyle(
                                TableStyle(
                                    [
                                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                                        ("BOX", (0, 0), (-1, -1), 1, colors.grey),
                                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
                                    ]
                                )
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
                                subplot_para = Paragraph(
                                    subplot_key,
                                    ParagraphStyle(
                                        "SubplotID",
                                        parent=styles["Normal"],
                                        fontSize=8,
                                        leading=10,
                                        wordWrap="CJK",
                                    ),
                                )
                                comments_para = Paragraph(
                                    comments,
                                    ParagraphStyle(
                                        "Comments",
                                        parent=styles["Normal"],
                                        fontSize=9,
                                        leading=11,
                                    ),
                                )
                                missing_veg_table_data.append([subplot_para, comments_para])

                            missing_veg_table = Table(missing_veg_table_data, colWidths=[2.5 * inch, 3.8 * inch])
                            missing_veg_table.setStyle(
                                TableStyle(
                                    [
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
                                    ]
                                )
                            )
                            story.append(missing_veg_table)

                            if len(date_missing_veg) > 10:
                                remaining_text = (
                                    f"... and {len(date_missing_veg) - 10} more subplots without vegetation"
                                )
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
                        print(
                            f"DEBUG: Checking veg errors for date {date}, veg_errors_data keys: {veg_errors_data.keys()}",
                            file=sys.stderr,
                        )
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
                            print(
                                f"DEBUG: Processing {len(veg_errors_data['height_outliers'])} height outliers for date filtering",
                                file=sys.stderr,
                            )
                            height_df = veg_errors_data["height_outliers"]
                            if "SubmissionDate" in height_df.columns:
                                height_df["date_only"] = pd.to_datetime(height_df["SubmissionDate"]).dt.date
                                date_height = height_df[height_df["date_only"] == date]
                                print(
                                    f"DEBUG: Found {len(date_height)} height outliers for date {date}", file=sys.stderr
                                )
                                for _, row in date_height.head(5).iterrows():
                                    error_type = "Height Outlier"
                                    details = []
                                    if "tree_height_m" in row and pd.notna(row["tree_height_m"]):
                                        details.append(f"{row['tree_height_m']:.1f}m")
                                    if species_col and species_col in row:
                                        details.append(str(row[species_col]))
                                    # Add subplot comments
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

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
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

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
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

                        # Super Tall Trees (>25m)
                        if "super_tall_trees" in veg_errors_data and len(veg_errors_data["super_tall_trees"]) > 0:
                            tall_df = veg_errors_data["super_tall_trees"]
                            if "SubmissionDate" in tall_df.columns:
                                tall_df["date_only"] = pd.to_datetime(tall_df["SubmissionDate"]).dt.date
                                date_tall = tall_df[tall_df["date_only"] == date]
                                for _, row in date_tall.head(5).iterrows():
                                    error_type = "Super Tall Tree (>25m)"
                                    details = []
                                    if "tree_height_m" in row and pd.notna(row["tree_height_m"]):
                                        details.append(f"{row['tree_height_m']:.1f}m")
                                    if species_col and species_col in row:
                                        details.append(str(row[species_col]))
                                    # Add subplot comments
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

                        # High Stem Counts (>20)
                        if "high_stems" in veg_errors_data and len(veg_errors_data["high_stems"]) > 0:
                            stems_df = veg_errors_data["high_stems"]
                            if "SubmissionDate" in stems_df.columns:
                                stems_df["date_only"] = pd.to_datetime(stems_df["SubmissionDate"]).dt.date
                                date_stems = stems_df[stems_df["date_only"] == date]
                                for _, row in date_stems.head(5).iterrows():
                                    error_type = "High Stem Count (>20)"
                                    details = []
                                    if "nr_stems_bh" in row and pd.notna(row["nr_stems_bh"]):
                                        details.append(f"{int(row['nr_stems_bh'])} stems")
                                    if species_col and species_col in row:
                                        details.append(str(row[species_col]))
                                    # Add subplot comments
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

                        # Unknown/Unidentified Species
                        if "unknown_species" in veg_errors_data and len(veg_errors_data["unknown_species"]) > 0:
                            unknown_df = veg_errors_data["unknown_species"]
                            if "SubmissionDate" in unknown_df.columns:
                                unknown_df["date_only"] = pd.to_datetime(unknown_df["SubmissionDate"]).dt.date
                                date_unknown = unknown_df[unknown_df["date_only"] == date]
                                for _, row in date_unknown.head(5).iterrows():
                                    error_type = "Unknown Species"
                                    details = []
                                    for col in ["other_species", "woody_species", "non_woody_species"]:
                                        if col in row and pd.notna(row[col]):
                                            details.append(f"{col}: {row[col]}")
                                    # Add subplot comments
                                    comments = (
                                        str(row.get("subplot_comments", ""))
                                        if pd.notna(row.get("subplot_comments"))
                                        else "—"
                                    )
                                    if len(comments) > 60:
                                        comments = comments[:57] + "..."
                                    date_veg_errors.append(
                                        [error_type, " | ".join(details) if details else "—", comments]
                                    )

                        # Display vegetation errors if any found for this date
                        print(f"DEBUG: Total date_veg_errors collected: {len(date_veg_errors)}", file=sys.stderr)
                        if date_veg_errors:
                            story.append(Paragraph("🌿 Vegetation & Measurement Issues", veg_error_header_style))

                            # Create a style for table cells with text wrapping
                            cell_style = ParagraphStyle(
                                "TableCell",
                                parent=styles["Normal"],
                                fontSize=8,
                                leading=10,
                                wordWrap="CJK",
                            )

                            # Wrap table content in Paragraph objects for text wrapping
                            veg_error_table_data = [["Error Type", "Details", "Subplot Comments"]]
                            for row in date_veg_errors[:10]:
                                wrapped_row = [
                                    Paragraph(str(row[0]), cell_style),  # Error Type
                                    Paragraph(str(row[1]), cell_style),  # Details
                                    Paragraph(str(row[2]), cell_style),  # Subplot Comments
                                ]
                                veg_error_table_data.append(wrapped_row)

                            veg_error_table = Table(
                                veg_error_table_data, colWidths=[1.5 * inch, 2.5 * inch, 2.3 * inch]
                            )
                            veg_error_table.setStyle(
                                TableStyle(
                                    [
                                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6F00")),
                                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                                        ("PADDING", (0, 0), (-1, -1), 6),
                                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFF3E0")),
                                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                        (
                                            "ROWBACKGROUNDS",
                                            (0, 1),
                                            (-1, -1),
                                            [colors.HexColor("#FFF3E0"), colors.white],
                                        ),
                                    ]
                                )
                            )
                            story.append(veg_error_table)

                            if len(date_veg_errors) > 10:
                                remaining = len(date_veg_errors) - 10
                                story.append(
                                    Paragraph(
                                        f"<i>... and {remaining} more vegetation error(s)</i>",
                                        ParagraphStyle(
                                            "VegRemaining",
                                            parent=styles["Normal"],
                                            fontSize=8,
                                            textColor=colors.grey,
                                            spaceBefore=4,
                                            fontStyle="italic",
                                        ),
                                    )
                                )

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
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D32F2F")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 9),
                            ("PADDING", (0, 0), (-1, -1), 6),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFEBEE")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("FONTSIZE", (0, 1), (-1, -1), 8),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )

                story.append(subplot_table)

        print(f"DEBUG PDF: Building final PDF with {len(story)} elements", file=sys.stderr)
        doc.build(story)
        buffer.seek(0)
        print("DEBUG PDF: PDF generation complete, returning buffer", file=sys.stderr)
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

enumerators = sorted(gdf_subplots["enumerator"].unique().tolist()) if "enumerator" in gdf_subplots.columns else []

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

# Define tabs (removed Vegetation Errors tab)
tab_list = [
    "📊 Error Overview",
    "📐 Geometry Errors",
    "📋 Error Details by Enumerator",
]

# Create tabs
tabs = st.tabs(tab_list)

# Calculate indices
TAB_OVERVIEW = 0
TAB_GEOMETRY = 1
TAB_ERROR_DETAILS = 2

# ============================================
# TAB 1: ERROR OVERVIEW
# ============================================

with tabs[TAB_OVERVIEW]:
    st.markdown("### 📊 Error Rate Overview")
    st.caption("Compares validation error rates across selected enumerators. Higher error rates (red) may indicate training needs, equipment issues, or challenging field conditions. The stacked chart shows absolute counts of valid vs invalid subplots per enumerator.")

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
    st.caption("Breaks down GPS/geometry validation failures by error type per enumerator. Common issues include: area too small/large, insufficient GPS accuracy, overlapping subplots. Patterns help identify whether issues are enumerator-specific (training) or equipment-specific (device problems).")

    invalid_subplots = filtered_gdf[~filtered_gdf["geom_valid"]]

    if len(invalid_subplots) > 0:
        # Count errors by enumerator
        error_counts = invalid_subplots.groupby("enumerator").size().reset_index(name="Error Count")
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
            error_summary = error_types_df.groupby(["Enumerator", "Error Type"]).size().reset_index(name="Count")

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
# TAB 3: ERROR DETAILS BY ENUMERATOR
# ============================================

with tabs[TAB_ERROR_DETAILS]:
    st.markdown("### 📋 Individual Enumerator Error Report")
    st.caption("Deep dive into a single enumerator's data quality. Shows: summary metrics, interactive map of their subplots, detailed geometry errors, and vegetation/measurement outliers. Use this for one-on-one feedback sessions or to prepare individual training plans.")

    selected_enum = st.selectbox(
        "Select enumerator for detailed error report",
        options=selected_enumerators,
        key="detail_enum",
    )

    if selected_enum:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == selected_enum].copy()

        # Filter enum_data to only include measured subplots
        if "subplot_id" in enum_data.columns and "measured_subplots" in enum_data.columns:
            import re

            # Extract subplot number from subplot_id
            enum_data["subplot_number"] = enum_data["subplot_id"].apply(
                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
            )

            # Convert measured_subplots to int
            enum_data["measured_subplots_int"] = enum_data["measured_subplots"].apply(
                lambda x: int(x) if pd.notna(x) else 999
            )

            # Only include measured subplots
            enum_data = enum_data[enum_data["subplot_number"] <= enum_data["measured_subplots_int"]].copy()

            # Drop temporary columns
            enum_data = enum_data.drop(columns=["subplot_number", "measured_subplots_int"], errors="ignore")

        st.markdown(f"#### Error Report for: **{selected_enum}**")

        # Summary metrics
        # Calculate vegetation errors for summary
        veg_error_count = 0
        if has_vegetation and has_measurements and "plots_subplots_vegetation_measurements" in raw_data:
            try:
                from utils.vegetation_validation import (
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

                # Filter to only measured subplots
                if "measured_subplots" in enum_data.columns:
                    import re

                    # Create temp df with subplot info
                    temp_enum = pd.DataFrame({"subplot_id": enum_subplot_keys})
                    temp_enum = temp_enum.merge(
                        enum_data[["subplot_id", "measured_subplots"]].drop_duplicates(), on="subplot_id", how="left"
                    )

                    # Extract subplot number from subplot_id
                    temp_enum["subplot_number"] = temp_enum["subplot_id"].apply(
                        lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                        if re.search(r"\[(\d+)\]", str(x))
                        else 999
                    )

                    # Convert measured_subplots to int
                    temp_enum["measured_subplots"] = temp_enum["measured_subplots"].apply(
                        lambda x: int(x) if pd.notna(x) else 999
                    )

                    # Only include measured subplots
                    enum_subplot_keys = temp_enum[temp_enum["subplot_number"] <= temp_enum["measured_subplots"]][
                        "subplot_id"
                    ].unique()

                meas_enum = meas_df[meas_df["SUBPLOT_KEY"].isin(enum_subplot_keys)].copy()

                # Missing vegetation
                if len(veg_df) > 0 and "SUBPLOT_KEY" in veg_df.columns:
                    veg_subplot_keys = veg_df["SUBPLOT_KEY"].unique()
                    subplots_without_veg = [k for k in enum_subplot_keys if k not in veg_subplot_keys]
                    veg_error_count += len(subplots_without_veg)

                if len(meas_enum) > 0:
                    meas_enum = merge_with_enumerator(meas_enum, enum_data)
                    species_col = get_species_column(meas_enum)

                    # Height outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                    if "tree_height_m" in meas_enum.columns and "VEGETATION_KEY" in meas_enum.columns:
                        height_check = meas_enum[
                            meas_enum["tree_height_m"].notna() & meas_enum["VEGETATION_KEY"].notna()
                        ].copy()

                        if len(height_check) > 0:
                            # Calculate median height per VEGETATION_KEY (tree group)
                            median_check = (
                                height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                                .median()
                                .reset_index(name="median_height")
                            )

                            # Merge and apply 4x/0.25x thresholds
                            height_total = pd.merge(height_check, median_check, how="inner", on="VEGETATION_KEY")
                            height_total["Upper_outliers"] = height_total.apply(
                                lambda row: "outlier" if row["tree_height_m"] > (row["median_height"] * 4) else "ok",
                                axis=1,
                            )
                            height_total["Lower_outliers"] = height_total.apply(
                                lambda row: "outlier" if row["tree_height_m"] < (row["median_height"] / 4) else "ok",
                                axis=1,
                            )

                            # Count outliers
                            outliers = height_total[
                                (height_total["Upper_outliers"] == "outlier")
                                | (height_total["Lower_outliers"] == "outlier")
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
                                    (circ_check.get("Upper_outliers") == "outlier")
                                    | (circ_check.get("Lower_outliers") == "outlier")
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
            st.metric("Total Subplots", get_total_measured_subplots(enum_data))

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
        st.caption("All subplots collected by this enumerator. Green = valid, Red = invalid. Click subplots for detailed validation info. Use this to spot geographic patterns in errors (e.g., issues concentrated in specific areas may indicate terrain challenges).")

        map_obj = create_enumerator_map(enum_data, selected_enum)

        if map_obj:
            # Display folium map
            try:
                from streamlit_folium import folium_static

                st.info(
                    "💡 **Tip:** Click on subplots to see detailed information. "
                    "Use the layer control (top-right) to toggle valid/invalid. "
                    "Change map styles using the layers menu."
                )

                folium_static(map_obj, width=1200, height=600)

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
        st.caption("List of this enumerator's subplots that failed geometry validation. Review 'reasons' column for specific issues. Area/vertices/ratios help diagnose whether the problem is GPS accuracy, plot shape, or boundary demarcation.")

        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0:
            display_cols = ["subplot_id", "reasons"]

            # Add subplot_comments if available
            if "subplot_comments" in invalid_data.columns:
                display_cols.append("subplot_comments")

            for col in ["area_m2", "nr_vertices", "length_width_ratio", "mrr_ratio"]:
                if col in invalid_data.columns:
                    display_cols.append(col)

            st.dataframe(invalid_data[display_cols], use_container_width=True, height=400)
        else:
            st.success(f"✅ No geometry errors for {selected_enum}")

        # ============================================
        # VEGETATION ERRORS SECTION
        # ============================================

        st.markdown("---")
        st.markdown("#### 🌿 Vegetation & Measurement Errors")
        st.caption("Measurement quality issues for this enumerator: missing vegetation records, height/circumference outliers, and suspicious age-circumference combinations. These may indicate measurement technique issues that need coaching.")

        if has_vegetation and has_measurements:
            try:
                from utils.vegetation_validation import (
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

                    # Filter to only measured subplots
                    if "measured_subplots" in enum_data.columns:
                        import re

                        # Create temp df with subplot info
                        temp_enum = pd.DataFrame({"subplot_id": enum_subplot_keys})
                        temp_enum = temp_enum.merge(
                            enum_data[["subplot_id", "measured_subplots"]].drop_duplicates(),
                            on="subplot_id",
                            how="left",
                        )

                        # Extract subplot number from subplot_id
                        temp_enum["subplot_number"] = temp_enum["subplot_id"].apply(
                            lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                            if re.search(r"\[(\d+)\]", str(x))
                            else 999
                        )

                        # Convert measured_subplots to int
                        temp_enum["measured_subplots"] = temp_enum["measured_subplots"].apply(
                            lambda x: int(x) if pd.notna(x) else 999
                        )

                        # Only include measured subplots
                        enum_subplot_keys = temp_enum[temp_enum["subplot_number"] <= temp_enum["measured_subplots"]][
                            "subplot_id"
                        ].unique()

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
                                    veg_comments, on="SUBPLOT_KEY", how="left", suffixes=("", "_veg")
                                )

                        # Merge with enumerator info
                        meas_enum = merge_with_enumerator(meas_enum, enum_data)
                        meas_enum = add_tree_name_column(meas_enum)
                        species_col = get_species_column(meas_enum)

                        # Height outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                        if "tree_height_m" in meas_enum.columns and "VEGETATION_KEY" in meas_enum.columns:
                            height_check = meas_enum[
                                meas_enum["tree_height_m"].notna() & meas_enum["VEGETATION_KEY"].notna()
                            ].copy()

                            if len(height_check) > 0:
                                # Calculate median height per VEGETATION_KEY (tree group)
                                median_check = (
                                    height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                                    .median()
                                    .reset_index(name="median_height")
                                )

                                # Merge and apply 4x/0.25x thresholds
                                height_total = pd.merge(height_check, median_check, how="inner", on="VEGETATION_KEY")
                                height_total["Upper_outliers"] = height_total.apply(
                                    lambda row: "outlier"
                                    if row["tree_height_m"] > (row["median_height"] * 4)
                                    else "ok",
                                    axis=1,
                                )
                                height_total["Lower_outliers"] = height_total.apply(
                                    lambda row: "outlier"
                                    if row["tree_height_m"] < (row["median_height"] / 4)
                                    else "ok",
                                    axis=1,
                                )

                                # Get outliers
                                height_outliers_df = height_total[
                                    (height_total["Upper_outliers"] == "outlier")
                                    | (height_total["Lower_outliers"] == "outlier")
                                ].copy()

                                # Preserve subplot_comments
                                if (
                                    "subplot_comments" in meas_enum.columns
                                    and "subplot_comments" not in height_outliers_df.columns
                                ):
                                    if (
                                        "SUBPLOT_KEY" in height_outliers_df.columns
                                        and "SUBPLOT_KEY" in meas_enum.columns
                                    ):
                                        comments_map = meas_enum[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                        height_outliers_df = height_outliers_df.merge(
                                            comments_map, on="SUBPLOT_KEY", how="left"
                                        )
                                    elif (
                                        "subplot_id" in height_outliers_df.columns and "subplot_id" in meas_enum.columns
                                    ):
                                        comments_map = meas_enum[["subplot_id", "subplot_comments"]].drop_duplicates()
                                        height_outliers_df = height_outliers_df.merge(
                                            comments_map, on="subplot_id", how="left"
                                        )

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
                                        (circ_check.get("Upper_outliers") == "outlier")
                                        | (circ_check.get("Lower_outliers") == "outlier")
                                    ]
                                    if len(outliers) > 0:
                                        # Preserve subplot_comments
                                        if (
                                            "subplot_comments" in meas_enum.columns
                                            and "subplot_comments" not in outliers.columns
                                        ):
                                            if "SUBPLOT_KEY" in outliers.columns and "SUBPLOT_KEY" in meas_enum.columns:
                                                comments_map = meas_enum[
                                                    ["SUBPLOT_KEY", "subplot_comments"]
                                                ].drop_duplicates()
                                                outliers = outliers.merge(comments_map, on="SUBPLOT_KEY", how="left")
                                            elif "subplot_id" in outliers.columns and "subplot_id" in meas_enum.columns:
                                                comments_map = meas_enum[
                                                    ["subplot_id", "subplot_comments"]
                                                ].drop_duplicates()
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
                                    if (
                                        "subplot_comments" in meas_enum.columns
                                        and "subplot_comments" not in suspicious_circ_df.columns
                                    ):
                                        if (
                                            "SUBPLOT_KEY" in suspicious_circ_df.columns
                                            and "SUBPLOT_KEY" in meas_enum.columns
                                        ):
                                            comments_map = meas_enum[
                                                ["SUBPLOT_KEY", "subplot_comments"]
                                            ].drop_duplicates()
                                            suspicious_circ_df = suspicious_circ_df.merge(
                                                comments_map, on="SUBPLOT_KEY", how="left"
                                            )
                                        elif (
                                            "subplot_id" in suspicious_circ_df.columns
                                            and "subplot_id" in meas_enum.columns
                                        ):
                                            comments_map = meas_enum[
                                                ["subplot_id", "subplot_comments"]
                                            ].drop_duplicates()
                                            suspicious_circ_df = suspicious_circ_df.merge(
                                                comments_map, on="subplot_id", how="left"
                                            )

                    with col2:
                        st.metric("Height Outliers", len(height_outliers_df))
                    with col3:
                        st.metric("Circ Outliers", len(circ_outliers_df))
                    with col4:
                        st.metric("Suspicious Circ/Age", len(suspicious_circ_df))

                    st.markdown("---")

                    # Show detailed errors in expandable sections
                    if len(subplots_without_veg) > 0:
                        with st.expander(
                            f"❌ Missing Vegetation Records ({len(subplots_without_veg)})", expanded=False
                        ):
                            st.caption("Subplots with geometry data but no vegetation records")

                            # Get subplot comments from plots_subplots (raw data)
                            missing_veg_df = pd.DataFrame(
                                {"Subplot ID": subplots_without_veg, "Issue": "No vegetation data recorded"}
                            )

                            # Get comments from plots_subplots raw data (this is where subplot_comments are stored)
                            if "plots_subplots" in raw_data:
                                plots_df = raw_data["plots_subplots"]
                                if "SUBPLOT_KEY" in plots_df.columns and "subplot_comments" in plots_df.columns:
                                    plots_comments = plots_df[["SUBPLOT_KEY", "subplot_comments"]].drop_duplicates()
                                    missing_veg_df = missing_veg_df.merge(
                                        plots_comments, left_on="Subplot ID", right_on="SUBPLOT_KEY", how="left"
                                    )
                                    # Drop the duplicate SUBPLOT_KEY column
                                    if "SUBPLOT_KEY" in missing_veg_df.columns:
                                        missing_veg_df = missing_veg_df.drop(columns=["SUBPLOT_KEY"])
                                    # Rename for display
                                    if "subplot_comments" in missing_veg_df.columns:
                                        missing_veg_df["subplot_comments"] = missing_veg_df["subplot_comments"].fillna(
                                            "—"
                                        )
                                        missing_veg_df = missing_veg_df.rename(
                                            columns={"subplot_comments": "Subplot Comments"}
                                        )

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

                            def get_outlier_type(row):
                                if row.get("Upper_outliers") == "outlier":
                                    return "Too Tall"
                                elif row.get("Lower_outliers") == "outlier":
                                    return "Too Short"
                                else:
                                    return "Unknown"

                            height_outliers_display["Outlier_Type"] = height_outliers_display.apply(
                                get_outlier_type, axis=1
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
                            st.dataframe(height_outliers_display[available_cols], use_container_width=True, height=300)

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
                            def get_circ_outlier_type(row):
                                if row.get("Upper_outliers") == "outlier":
                                    return "Too Large"
                                elif row.get("Lower_outliers") == "outlier":
                                    return "Too Small"
                                else:
                                    return "Unknown"

                            circ_outliers_display["Outlier_Type"] = circ_outliers_display.apply(
                                get_circ_outlier_type, axis=1
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
                            st.dataframe(circ_outliers_display[available_cols], use_container_width=True, height=300)

                            # Export option
                            csv_circ = circ_outliers_display[available_cols].to_csv(index=False)
                            st.download_button(
                                "📥 Download Circumference Outliers CSV",
                                data=csv_circ,
                                file_name=f"{config.PARTNER}_{selected_enum}_circ_outliers.csv",
                                mime="text/csv",
                            )

                    if len(suspicious_circ_df) > 0:
                        with st.expander(
                            f"⚠️ Suspicious Circumference by Age ({len(suspicious_circ_df)})", expanded=False
                        ):
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
                            st.dataframe(suspicious_display[available_cols], use_container_width=True, height=300)

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
                        len(subplots_without_veg)
                        + len(height_outliers_df)
                        + len(circ_outliers_df)
                        + len(suspicious_circ_df)
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
        st.caption("Export this enumerator's data for offline review, performance discussions, or record-keeping. CSV for spreadsheet analysis, PDF for printable reports, GeoJSON for GIS software, Errors Only for focused remediation lists.")

        col1, col2, col3 = st.columns(3)

        # CSV Export
        with col1:
            st.markdown("##### 📊 CSV Export")
            st.caption("All subplot data")

            if len(enum_data) > 0:
                csv_data = enum_data.drop(columns=["geometry"], errors="ignore").to_csv(index=False)
                st.download_button(
                    "📊 Download CSV",
                    data=csv_data,
                    file_name=f"{config.PARTNER}_{selected_enum}_subplots.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"download_csv_{selected_enum}",
                )

        # PDF Export
        with col2:
            st.markdown("##### 📄 PDF Report")
            st.caption("Formatted summary report")

            if len(enum_data) > 0:
                try:
                    pdf_buffer = generate_enhanced_pdf_report(enum_data, selected_enum, config.PARTNER, raw_data)

                    if pdf_buffer:
                        st.download_button(
                            "📄 Download PDF",
                            data=pdf_buffer.getvalue(),
                            file_name=f"{config.PARTNER}_{selected_enum}_report.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"download_pdf_{selected_enum}",
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
                        key=f"download_geojson_{selected_enum}",
                    )
                else:
                    st.info("No geometry data available")

        # Export errors only
        if len(invalid_data) > 0:
            st.markdown("---")
            st.markdown("##### ⚠️ Export Errors Only")

            col1, col2 = st.columns(2)

            with col1:
                csv_errors = invalid_data.drop(columns=["geometry"], errors="ignore").to_csv(index=False)
                st.download_button(
                    "📊 Download Errors CSV",
                    data=csv_errors,
                    file_name=f"{config.PARTNER}_{selected_enum}_errors.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"download_errors_csv_{selected_enum}",
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
                        key=f"download_errors_geojson_{selected_enum}",
                    )
