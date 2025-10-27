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
from ui.components import show_header

# Try to import folium (optional for maps)
try:
    import folium
    from folium.plugins import Fullscreen, MiniMap

    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

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


def generate_enhanced_pdf_report(enum_data, enumerator_name, partner_name):
    """
    Generate comprehensive PDF report for enumerator with charts and analysis
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle,
            Paragraph,
            Spacer,
            PageBreak,
        )
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics.charts.piecharts import Pie
        from datetime import datetime

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

        # Statistics
        total = len(enum_data)
        invalid = (~enum_data["geom_valid"]).sum()
        valid = enum_data["geom_valid"].sum()
        error_rate = (invalid / total * 100) if total > 0 else 0

        # Performance rating
        if error_rate <= 5:
            rating, rating_color = "EXCELLENT", colors.green
        elif error_rate <= 15:
            rating, rating_color = "GOOD", colors.orange
        elif error_rate <= 30:
            rating, rating_color = "NEEDS IMPROVEMENT", colors.orange
        else:
            rating, rating_color = "CRITICAL", colors.red

        story.append(Paragraph("Executive Summary", section_style))

        summary_data = [
            ["METRIC", "VALUE", "STATUS"],
            ["Total Subplots", str(total), "—"],
            [
                "Valid Subplots",
                f"{valid} ({valid/total*100:.1f}%)",
                "✓" if valid / total > 0.85 else "⚠",
            ],
            [
                "Invalid Subplots",
                f"{invalid} ({error_rate:.1f}%)",
                "✓" if error_rate < 15 else "✗",
            ],
            ["Performance Rating", rating, ""],
        ]

        summary_table = Table(
            summary_data, colWidths=[2.5 * inch, 2.5 * inch, 1 * inch]
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565C0")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("PADDING", (0, 0), (-1, 0), 10),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(summary_table)
        story.append(Spacer(1, 0.3 * inch))

        # Pie chart
        story.append(Paragraph("Performance Visualization", section_style))
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 150, 50, 100, 100
        pie.data = [valid, invalid]
        pie.labels = ["Valid", "Invalid"]
        pie.slices[0].fillColor = colors.green
        pie.slices[1].fillColor = colors.red
        pie.slices[0].popout = 5
        drawing.add(pie)
        story.append(drawing)
        story.append(Spacer(1, 0.3 * inch))

        # Error analysis
        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0:
            story.append(Paragraph("Error Details", section_style))

            error_types = {}
            for reasons in invalid_data["reasons"].dropna():
                for reason in str(reasons).split(";"):
                    reason = reason.strip()
                    if reason:
                        error_types[reason] = error_types.get(reason, 0) + 1

            if error_types:
                sorted_errors = sorted(
                    error_types.items(), key=lambda x: x[1], reverse=True
                )
                error_breakdown = [["Error Type", "Count", "% of Errors"]]
                for error_type, count in sorted_errors[:10]:
                    pct = count / len(invalid_data) * 100
                    error_breakdown.append([error_type[:50], str(count), f"{pct:.1f}%"])

                error_table = Table(
                    error_breakdown, colWidths=[3.5 * inch, 1 * inch, 1.5 * inch]
                )
                error_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D32F2F")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("PADDING", (0, 0), (-1, 0), 10),
                            (
                                "BACKGROUND",
                                (0, 1),
                                (-1, -1),
                                colors.HexColor("#FFEBEE"),
                            ),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ]
                    )
                )

                story.append(error_table)

        doc.build(story)
        buffer.seek(0)
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
if has_vegetation:
    tab_list = [
        "📊 Error Overview",
        "📐 Geometry Errors",
        "📋 Error Details by Enumerator",
    ]
else:
    tab_list = [
        "📊 Error Overview",
        "📐 Geometry Errors",
        "📋 Error Details by Enumerator",
    ]

# Create tabs (ALWAYS executed)
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
# TAB 3: ERROR DETAILS BY ENUMERATOR
# ============================================

with tabs[TAB_ERROR_DETAILS]:
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
        st.markdown("#### ⚠️ Invalid Subplots")

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
            st.success(f"✅ No invalid subplots for {selected_enum}")

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
                        enum_data, selected_enum, config.PARTNER
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
