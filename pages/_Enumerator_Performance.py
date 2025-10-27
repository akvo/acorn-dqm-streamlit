"""
Enumerator Performance Analysis - Error-focused quality control
Enhanced with: Interactive maps, PDF export, GeoJSON export
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
from io import BytesIO
import config
from ui.components import show_header

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


def create_enumerator_map(enum_data):
    """
    Create interactive map showing all subplots for an enumerator
    Color-coded by validation status
    """
    if len(enum_data) == 0 or "geometry" not in enum_data.columns:
        return None

    # Filter out empty geometries
    map_data = enum_data[~enum_data.geometry.is_empty].copy()

    if len(map_data) == 0:
        return None

    # Get centroids for markers
    map_data["centroid"] = map_data.geometry.centroid
    map_data["lat"] = map_data["centroid"].y
    map_data["lon"] = map_data["centroid"].x

    # Create color based on validation
    map_data["color"] = map_data["geom_valid"].apply(lambda x: "green" if x else "red")
    map_data["status"] = map_data["geom_valid"].apply(
        lambda x: "✅ Valid" if x else "❌ Invalid"
    )

    # Create hover text
    map_data["hover_text"] = (
        "<b>"
        + map_data["subplot_id"].astype(str)
        + "</b><br>"
        + "Status: "
        + map_data["status"]
        + "<br>"
        + "Area: "
        + map_data["area_m2"].round(1).astype(str)
        + " m²<br>"
    )

    # Add error reasons for invalid subplots
    invalid_mask = ~map_data["geom_valid"]
    if "reasons" in map_data.columns:
        map_data.loc[invalid_mask, "hover_text"] = (
            map_data.loc[invalid_mask, "hover_text"]
            + "Issues: "
            + map_data.loc[invalid_mask, "reasons"].fillna("Unknown")
        )

    # Create figure
    fig = go.Figure()

    # Add valid subplots
    valid_data = map_data[map_data["geom_valid"]]
    if len(valid_data) > 0:
        fig.add_trace(
            go.Scattermapbox(
                lon=valid_data["lon"],
                lat=valid_data["lat"],
                mode="markers",
                marker=dict(size=12, color="green", opacity=0.7),
                text=valid_data["hover_text"],
                hovertemplate="%{text}<extra></extra>",
                name="✅ Valid",
            )
        )

    # Add invalid subplots
    invalid_data = map_data[~map_data["geom_valid"]]
    if len(invalid_data) > 0:
        fig.add_trace(
            go.Scattermapbox(
                lon=invalid_data["lon"],
                lat=invalid_data["lat"],
                mode="markers",
                marker=dict(size=14, color="red", opacity=0.8, symbol="x"),
                text=invalid_data["hover_text"],
                hovertemplate="%{text}<extra></extra>",
                name="❌ Invalid",
            )
        )

    # Calculate center
    center_lat = map_data["lat"].mean()
    center_lon = map_data["lon"].mean()

    # Update layout
    fig.update_layout(
        mapbox=dict(
            style="open-street-map",
            center=dict(lat=center_lat, lon=center_lon),
            zoom=12,
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=500,
        showlegend=True,
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.8)",
        ),
    )

    return fig


def generate_pdf_report(enum_data, enumerator_name, partner_name):
    """
    Generate PDF report for enumerator
    Using reportlab for PDF generation
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
        )
        from reportlab.lib import colors
        from datetime import datetime

        # Create buffer
        buffer = BytesIO()

        # Create PDF
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            textColor=colors.HexColor("#1f77b4"),
            spaceAfter=30,
        )

        story.append(Paragraph(f"Enumerator Performance Report", title_style))
        story.append(
            Paragraph(f"Enumerator: <b>{enumerator_name}</b>", styles["Heading2"])
        )
        story.append(Paragraph(f"Partner: {partner_name}", styles["Normal"]))
        story.append(
            Paragraph(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 0.3 * inch))

        # Summary Statistics
        story.append(Paragraph("Summary Statistics", styles["Heading2"]))

        total = len(enum_data)
        invalid = (~enum_data["geom_valid"]).sum()
        valid = enum_data["geom_valid"].sum()
        error_rate = (invalid / total * 100) if total > 0 else 0

        summary_data = [
            ["Metric", "Value"],
            ["Total Subplots", str(total)],
            ["Valid Subplots", f"{valid} ({valid/total*100:.1f}%)"],
            ["Invalid Subplots", f"{invalid} ({error_rate:.1f}%)"],
        ]

        if "area_m2" in enum_data.columns:
            avg_area = enum_data["area_m2"].mean()
            summary_data.append(["Average Area", f"{avg_area:.1f} m²"])

        summary_table = Table(summary_data)
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
            )
        )

        story.append(summary_table)
        story.append(Spacer(1, 0.3 * inch))

        # Invalid Subplots Details
        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0:
            story.append(Paragraph("Invalid Subplots Details", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * inch))

            # Create table
            table_data = [["Subplot ID", "Area (m²)", "Validation Issues"]]

            for idx, row in invalid_data.iterrows():
                subplot_id = str(row["subplot_id"])
                area = f"{row['area_m2']:.1f}" if "area_m2" in row else "N/A"
                reasons = str(row.get("reasons", "Unknown"))

                # Wrap long text
                if len(reasons) > 60:
                    reasons = reasons[:60] + "..."

                table_data.append([subplot_id, area, reasons])

            error_table = Table(table_data, colWidths=[2 * inch, 1.5 * inch, 3 * inch])
            error_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.red),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.lightgrey),
                        ("GRID", (0, 0), (-1, -1), 1, colors.black),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )

            story.append(error_table)
        else:
            story.append(Paragraph("✅ No invalid subplots found!", styles["Heading2"]))

        # Build PDF
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
        st.caption("Green markers = valid subplots | Red X markers = invalid subplots")

        map_fig = create_enumerator_map(enum_data)

        if map_fig:
            st.plotly_chart(map_fig, use_container_width=True)
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
                    pdf_buffer = generate_pdf_report(
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
