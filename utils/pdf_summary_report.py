"""
Comprehensive PDF Summary Report Generator
Generates a multi-page PDF report summarizing all quality checks across enumerators
"""

import pandas as pd
import sys
import re
from io import BytesIO
from datetime import datetime
from collections import Counter

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
        Image as RLImage,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def generate_summary_pdf_report(filtered_gdf, raw_data, partner_name="Partner"):
    """
    Generate a comprehensive summary PDF report with all quality checks

    Parameters:
    -----------
    filtered_gdf : GeoDataFrame
        The filtered geodataframe with subplot data
    raw_data : dict
        Dictionary containing all raw data tables
    partner_name : str
        Name of the partner organization

    Returns:
    --------
    BytesIO : PDF file buffer
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("ReportLab is required for PDF generation")

    # Create PDF buffer
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )

    # Container for PDF elements
    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#2E7D32'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#1976D2'),
        spaceAfter=12,
        spaceBefore=20,
        fontName='Helvetica-Bold',
    )

    subheading_style = ParagraphStyle(
        'CustomSubheading',
        parent=styles['Heading3'],
        fontSize=12,
        textColor=colors.HexColor('#FF6F00'),
        spaceAfter=10,
        spaceBefore=15,
        fontName='Helvetica-Bold',
    )

    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
    )

    # ============= COVER PAGE =============
    story.append(Spacer(1, 1*inch))
    story.append(Paragraph(f"Ground Truth Data Quality Report", title_style))
    story.append(Paragraph(f"{partner_name}", ParagraphStyle(
        'Partner',
        parent=styles['Normal'],
        fontSize=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#388E3C'),
    )))
    story.append(Spacer(1, 0.5*inch))

    # Report date - show data submission date range
    report_generated = datetime.now().strftime("%B %d, %Y")

    # Get date range from the data
    date_info = f"Report Generated: {report_generated}"
    if "SubmissionDate" in filtered_gdf.columns:
        submission_dates = pd.to_datetime(filtered_gdf["SubmissionDate"]).dropna()
        if len(submission_dates) > 0:
            min_date = submission_dates.min().strftime("%B %d, %Y")
            max_date = submission_dates.max().strftime("%B %d, %Y")
            if min_date == max_date:
                date_info = f"Data Submitted: {min_date}<br/>Report Generated: {report_generated}"
            else:
                date_info = f"Data Submitted: {min_date} to {max_date}<br/>Report Generated: {report_generated}"

    story.append(Paragraph(
        date_info,
        ParagraphStyle('Date', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, leading=14)
    ))

    story.append(Spacer(1, 1*inch))

    # Overall Statistics
    # Total subplots should be sum of measured_subplots, not just record count
    if "measured_subplots" in filtered_gdf.columns:
        # Sum of all measured subplots
        total_subplots = filtered_gdf["measured_subplots"].fillna(0).sum()
        total_subplots = int(total_subplots)
    else:
        total_subplots = len(filtered_gdf)

    total_valid = filtered_gdf["geom_valid"].sum() if "geom_valid" in filtered_gdf.columns else 0
    total_invalid = len(filtered_gdf) - total_valid  # Count of invalid records
    error_rate = (total_invalid / len(filtered_gdf) * 100) if len(filtered_gdf) > 0 else 0

    # Count unique enumerators and plots
    unique_enumerators = filtered_gdf["enumerator"].nunique() if "enumerator" in filtered_gdf.columns else 0

    # Count unique GT plots per data collector
    unique_plots = 0
    if "subplot_id" in filtered_gdf.columns:
        # Extract plot ID from subplot_id (format: uuid:.../sub_plot[n])
        filtered_gdf_copy = filtered_gdf.copy()
        filtered_gdf_copy["plot_id"] = filtered_gdf_copy["subplot_id"].apply(
            lambda x: str(x).split("/sub_plot")[0] if pd.notna(x) and "/sub_plot" in str(x) else str(x)
        )
        unique_plots = filtered_gdf_copy["plot_id"].nunique()

    # Summary statistics table
    summary_data = [
        ["Metric", "Value"],
        ["Total Subplots Measured", f"{total_subplots:,}"],
        ["Valid Subplots", f"{total_valid:,} ({total_valid/len(filtered_gdf)*100:.1f}%)"],
        ["Invalid Subplots", f"{total_invalid:,} ({error_rate:.1f}%)"],
        ["GT Plots", f"{unique_plots:,}"],
        ["Data Collectors", f"{unique_enumerators}"],
    ]

    story.append(Paragraph("📊 Executive Summary", heading_style))
    summary_table = Table(summary_data, colWidths=[3*inch, 2.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2E7D32')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#E8F5E9')),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('PADDING', (0, 1), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#E8F5E9'), colors.white]),
    ]))
    story.append(summary_table)

    story.append(PageBreak())

    # ============= GEOMETRY QUALITY CHECK =============
    story.append(Paragraph("📐 Geometry Quality Check Summary", heading_style))

    # Add overview map showing all subplots
    if len(filtered_gdf) > 0 and MATPLOTLIB_AVAILABLE:
        try:
            print(f"DEBUG PDF: Creating overview map with {len(filtered_gdf)} subplots", file=sys.stderr)

            fig, ax = plt.subplots(figsize=(7, 5), dpi=100)

            # Plot all subplots
            for idx, row in filtered_gdf.iterrows():
                if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                    geom = row["geometry"]
                    is_valid = row.get("geom_valid", False)
                    color = '#4CAF50' if is_valid else '#F44336'
                    alpha = 0.3 if is_valid else 0.6

                    if geom.geom_type == 'Polygon':
                        x, y = geom.exterior.xy
                        ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)
                    elif geom.geom_type == 'MultiPolygon':
                        for poly in geom.geoms:
                            x, y = poly.exterior.xy
                            ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)

            ax.set_aspect('equal')
            ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax.set_xlabel('Longitude', fontsize=10)
            ax.set_ylabel('Latitude', fontsize=10)
            ax.set_title(f'Subplot Overview - Valid (Green) vs Invalid (Red)', fontsize=12, fontweight='bold')

            # Add legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#4CAF50', alpha=0.5, label=f'Valid ({total_valid})'),
                Patch(facecolor='#F44336', alpha=0.6, label=f'Invalid ({total_invalid})'),
            ]
            ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

            plt.tight_layout()

            # Convert to image
            map_buffer = BytesIO()
            plt.savefig(map_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            map_buffer.seek(0)

            overview_img = RLImage(map_buffer, width=6*inch, height=4.3*inch)
            story.append(overview_img)
            story.append(Spacer(1, 0.3*inch))
            print(f"DEBUG PDF: Successfully created overview map", file=sys.stderr)

        except Exception as e:
            print(f"DEBUG PDF: Error creating overview map: {str(e)}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)

    # Most common errors
    if "reasons" in filtered_gdf.columns and total_invalid > 0:
        invalid_gdf = filtered_gdf[~filtered_gdf["geom_valid"]].copy()

        # Count error types
        error_reasons = []
        for reasons_str in invalid_gdf["reasons"].dropna():
            # Split by common delimiters
            reasons = str(reasons_str).split(";")
            error_reasons.extend([r.strip() for r in reasons if r.strip()])

        if error_reasons:
            error_counts = Counter(error_reasons)
            most_common = error_counts.most_common(1)[0]

            story.append(Paragraph(
                f"The most common issue noticed was: <b>{most_common[0]}</b> ({most_common[1]} occurrences)",
                normal_style
            ))
            story.append(Spacer(1, 0.3*inch))

    # Geometry errors by enumerator with GT plot count
    if "enumerator" in filtered_gdf.columns and total_invalid > 0:
        # Calculate stats per enumerator
        enum_stats_list = []
        for enum_name in filtered_gdf["enumerator"].unique():
            enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum_name]

            # Count GT plots
            enum_plot_count = 0
            if "subplot_id" in enum_data.columns:
                enum_data_copy = enum_data.copy()
                enum_data_copy["plot_id"] = enum_data_copy["subplot_id"].apply(
                    lambda x: str(x).split("/sub_plot")[0] if pd.notna(x) and "/sub_plot" in str(x) else str(x)
                )
                enum_plot_count = enum_data_copy["plot_id"].nunique()

            total_recs = len(enum_data)
            valid_recs = enum_data["geom_valid"].sum()
            invalid_recs = total_recs - valid_recs
            error_rate = (invalid_recs / total_recs * 100) if total_recs > 0 else 0

            enum_stats_list.append({
                "Enumerator": enum_name,
                "GT Plots": enum_plot_count,
                "Total Subplots": total_recs,
                "Valid Subplots": valid_recs,
                "Invalid Subplots": invalid_recs,
                "Error Rate %": error_rate,
            })

        enum_errors = pd.DataFrame(enum_stats_list)
        enum_errors = enum_errors.sort_values("Error Rate %", ascending=False)

        # Create table with GT plot count
        geom_table_data = [["Data Collector", "GT Plots", "Total", "Valid", "Invalid", "Error %"]]
        for _, row in enum_errors.head(15).iterrows():
            geom_table_data.append([
                str(row["Enumerator"]),
                str(int(row["GT Plots"])),
                str(int(row["Total Subplots"])),
                str(int(row["Valid Subplots"])),
                str(int(row["Invalid Subplots"])),
                f"{row['Error Rate %']:.1f}%",
            ])

        geom_table = Table(geom_table_data, colWidths=[1.6*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.8*inch])
        geom_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('PADDING', (0, 1), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ]))
        story.append(geom_table)

        if len(enum_errors) > 15:
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph(
                f"<i>... and {len(enum_errors) - 15} more data collectors</i>",
                ParagraphStyle('Remaining', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
            ))

    story.append(Spacer(1, 0.3*inch))

    # Detailed error breakdown
    if "reasons" in filtered_gdf.columns and total_invalid > 0 and error_reasons:
        story.append(Paragraph("Error Type Breakdown", subheading_style))
        error_counts = Counter(error_reasons)
        error_breakdown_data = [["Error Type", "Count", "Percentage"]]

        for error_type, count in error_counts.most_common(10):
            pct = (count / total_invalid * 100)
            error_breakdown_data.append([
                error_type,
                str(count),
                f"{pct:.1f}%",
            ])

        error_table = Table(error_breakdown_data, colWidths=[3.5*inch, 1*inch, 1.2*inch])
        error_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FF6F00')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF3E0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('PADDING', (0, 1), (-1, -1), 6),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFF8F0')]),
        ]))
        story.append(error_table)

        # Add explanations for common error types
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph("Common Error Explanations", subheading_style))

        explanations = {
            "Nr vertices <= 3": "The subplot polygon has 3 or fewer GPS points. A valid polygon requires at least 4 vertices (points) to form a closed shape with area.",
            "Empty geometry": "No valid GPS coordinates were collected for this subplot. This occurs when: (1) No GPS points were recorded, (2) All GPS points had zero accuracy and were filtered out, or (3) The data exceeded Excel cell limits during export.",
            "Self-intersecting polygon": "The subplot boundary crosses itself, creating an invalid shape. This happens when GPS points are collected in the wrong order or the enumerator crosses their own path.",
            "Area too small": "The subplot area is below the minimum threshold (typically < 50 m²), indicating incomplete or incorrect boundary mapping.",
            "Area too large": "The subplot area exceeds the maximum threshold (typically > 200 m²), suggesting the enumerator walked beyond the subplot boundaries.",
        }

        # Check which errors exist in the data and show relevant explanations
        explanation_items = []
        for error_type in error_counts.most_common(5):
            error_name = error_type[0]
            for key, explanation in explanations.items():
                if key.lower() in error_name.lower():
                    explanation_items.append(f"<b>{key}:</b> {explanation}")
                    break

        if explanation_items:
            explanation_text = "<br/><br/>".join(explanation_items)
            story.append(Paragraph(explanation_text, ParagraphStyle(
                "Explanations",
                parent=styles["Normal"],
                fontSize=9,
                leading=12,
                leftIndent=10,
            )))

    # Show individual subplot images for top invalid subplots
    if "reasons" in filtered_gdf.columns and total_invalid > 0 and MATPLOTLIB_AVAILABLE:
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Sample Invalid Subplots", subheading_style))

        invalid_gdf = filtered_gdf[~filtered_gdf["geom_valid"]].copy()

        # Get vegetation data for subplot comments
        veg_data = None
        if "plots_subplots_vegetation" in raw_data:
            veg_data = raw_data["plots_subplots_vegetation"]

        # Show top 5 invalid subplots
        max_subplots = min(5, len(invalid_gdf))
        for idx, (_, row) in enumerate(invalid_gdf.head(max_subplots).iterrows()):
            if idx >= max_subplots:
                break

            # Extract subplot number from subplot_id
            subplot_id_full = str(row.get("subplot_id", "N/A"))
            match = re.search(r'\[(\d+)\]', subplot_id_full)
            if match:
                subplot_display = f"Subplot {match.group(1)}"
            else:
                subplot_display = f"Subplot: {subplot_id_full[:50]}"

            # Add enumerator name if available
            if "enumerator" in row and pd.notna(row["enumerator"]):
                subplot_display += f" | {row['enumerator']}"

            subplot_header_style_inline = ParagraphStyle(
                "SubplotHeaderInline",
                parent=styles["Heading4"],
                fontSize=10,
                textColor=colors.HexColor("#E53935"),
                spaceBefore=12,
                spaceAfter=6,
                fontName="Helvetica-Bold",
            )
            story.append(Paragraph(subplot_display, subplot_header_style_inline))

            # Create polygon image
            polygon_img_rl = None
            try:
                if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                    geom = row["geometry"]
                    is_valid = row.get("geom_valid", False)

                    fig, ax = plt.subplots(figsize=(3, 2.5), dpi=100)

                    color = '#4CAF50' if is_valid else '#F44336'

                    if geom.geom_type == 'Polygon':
                        x, y = geom.exterior.xy
                        ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                        ax.plot(x, y, 'o', color=color, markersize=3)
                    elif geom.geom_type == 'MultiPolygon':
                        for poly in geom.geoms:
                            x, y = poly.exterior.xy
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

            except Exception as e:
                print(f"DEBUG PDF: Error creating subplot polygon: {str(e)}", file=sys.stderr)

            # Create details
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

                    if len(subplot_veg) > 0:
                        veg_rec = subplot_veg.iloc[0]

                        # Subplot comments
                        if "subplot_comments" in veg_rec and pd.notna(veg_rec["subplot_comments"]):
                            comments = str(veg_rec["subplot_comments"])
                            if len(comments) > 80:
                                comments = comments[:77] + "..."
                            detail_items.append(f"<b>Comments:</b> {comments}")

            # Create detail text
            detail_text = "<br/>".join(detail_items)
            detail_para = Paragraph(detail_text, ParagraphStyle(
                "DetailsInline",
                parent=styles["Normal"],
                fontSize=8,
                leading=10,
            ))

            # Create 2-column table with polygon on left, details on right
            if polygon_img_rl:
                detail_table = Table(
                    [[polygon_img_rl, detail_para]],
                    colWidths=[2.8*inch, 3.5*inch]
                )
            else:
                detail_table = Table(
                    [[detail_para]],
                    colWidths=[6.3*inch]
                )

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
            story.append(Spacer(1, 0.15*inch))

        if len(invalid_gdf) > max_subplots:
            story.append(Paragraph(
                f"<i>... and {len(invalid_gdf) - max_subplots} more invalid subplots</i>",
                ParagraphStyle('Remaining', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
            ))

    story.append(PageBreak())

    # ============= VEGETATION OUTLIERS SUMMARY =============
    story.append(Paragraph("🌿 Vegetation & Measurement Outliers", heading_style))

    # Get measurement data for outlier analysis
    has_measurements = "plots_subplots_vegetation_measurements" in raw_data

    if has_measurements:
        from utils.data_merge_utils import merge_with_enumerator, get_species_column

        meas_df = raw_data["plots_subplots_vegetation_measurements"].copy()

        # Filter to only measured subplots
        filtered_subplot_ids = filtered_gdf["subplot_id"].unique() if "subplot_id" in filtered_gdf.columns else []
        if len(filtered_subplot_ids) > 0 and "SUBPLOT_KEY" in meas_df.columns:
            meas_df = meas_df[meas_df["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()

        meas_with_enum = merge_with_enumerator(meas_df, filtered_gdf)
        species_col = get_species_column(meas_with_enum)

        # Height Outliers
        height_outliers_df = pd.DataFrame()
        if "tree_height_m" in meas_with_enum.columns and "VEGETATION_KEY" in meas_with_enum.columns:
            height_check = meas_with_enum[
                meas_with_enum["tree_height_m"].notna() & meas_with_enum["VEGETATION_KEY"].notna()
            ].copy()

            if len(height_check) > 0:
                median_check = (
                    height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                    .median()
                    .reset_index(name="median_height")
                )
                height_total = pd.merge(height_check, median_check, how="inner", on="VEGETATION_KEY")
                height_total["Upper_outliers"] = height_total.apply(
                    lambda row: "outlier" if row["tree_height_m"] > (row["median_height"] * 4) else "ok",
                    axis=1,
                )
                height_total["Lower_outliers"] = height_total.apply(
                    lambda row: "outlier" if row["tree_height_m"] < (row["median_height"] / 4) else "ok",
                    axis=1,
                )
                height_outliers_df = height_total[
                    (height_total["Upper_outliers"] == "outlier") |
                    (height_total["Lower_outliers"] == "outlier")
                ].copy()

        # Circumference Outliers
        circ_outliers_df = pd.DataFrame()
        circ_cols = [col for col in meas_with_enum.columns if "circumference" in col.lower()]
        if circ_cols and "VEGETATION_KEY" in meas_with_enum.columns:
            for circ_col in circ_cols:
                circ_check = meas_with_enum[
                    meas_with_enum[circ_col].notna() & meas_with_enum["VEGETATION_KEY"].notna()
                ].copy()

                if len(circ_check) > 0:
                    median_check = (
                        circ_check.groupby("VEGETATION_KEY")[circ_col]
                        .median()
                        .reset_index(name="median_circ")
                    )
                    circ_total = pd.merge(circ_check, median_check, how="inner", on="VEGETATION_KEY")
                    circ_total["Upper_outliers"] = circ_total.apply(
                        lambda row: "outlier" if row[circ_col] > (row["median_circ"] * 4) else "ok",
                        axis=1,
                    )
                    circ_total["Lower_outliers"] = circ_total.apply(
                        lambda row: "outlier" if row[circ_col] < (row["median_circ"] / 4) else "ok",
                        axis=1,
                    )
                    outliers = circ_total[
                        (circ_total["Upper_outliers"] == "outlier") |
                        (circ_total["Lower_outliers"] == "outlier")
                    ].copy()
                    circ_outliers_df = pd.concat([circ_outliers_df, outliers]).drop_duplicates()

        # Summary statistics
        total_height_outliers = len(height_outliers_df)
        total_circ_outliers = len(circ_outliers_df)

        outlier_summary_data = [
            ["Outlier Type", "Count"],
            ["Height Outliers", str(total_height_outliers)],
            ["Circumference Outliers", str(total_circ_outliers)],
            ["Total Vegetation Outliers", str(total_height_outliers + total_circ_outliers)],
        ]

        outlier_summary_table = Table(outlier_summary_data, colWidths=[3*inch, 2*inch])
        outlier_summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FF6F00')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FFF3E0')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('PADDING', (0, 1), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFF8F0')]),
        ]))
        story.append(outlier_summary_table)
        story.append(Spacer(1, 0.3*inch))

        # Height outliers by enumerator
        if total_height_outliers > 0 and "enumerator" in height_outliers_df.columns:
            story.append(Paragraph("Height Outliers by Data Collector", subheading_style))
            height_by_enum = height_outliers_df.groupby("enumerator").size().reset_index(name="Count")
            height_by_enum = height_by_enum.sort_values("Count", ascending=False)

            height_enum_data = [["Data Collector", "Height Outliers"]]
            for _, row in height_by_enum.head(10).iterrows():
                height_enum_data.append([str(row["enumerator"]), str(row["Count"])])

            height_enum_table = Table(height_enum_data, colWidths=[3.5*inch, 1.5*inch])
            height_enum_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('PADDING', (0, 1), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ]))
            story.append(height_enum_table)

            if len(height_by_enum) > 10:
                story.append(Paragraph(
                    f"<i>... and {len(height_by_enum) - 10} more data collectors</i>",
                    ParagraphStyle('Remaining', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
                ))

        story.append(Spacer(1, 0.3*inch))

        # Circumference outliers by enumerator
        if total_circ_outliers > 0 and "enumerator" in circ_outliers_df.columns:
            story.append(Paragraph("Circumference Outliers by Data Collector", subheading_style))
            circ_by_enum = circ_outliers_df.groupby("enumerator").size().reset_index(name="Count")
            circ_by_enum = circ_by_enum.sort_values("Count", ascending=False)

            circ_enum_data = [["Data Collector", "Circumference Outliers"]]
            for _, row in circ_by_enum.head(10).iterrows():
                circ_enum_data.append([str(row["enumerator"]), str(row["Count"])])

            circ_enum_table = Table(circ_enum_data, colWidths=[3.5*inch, 1.5*inch])
            circ_enum_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1976D2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('PADDING', (0, 1), (-1, -1), 6),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ]))
            story.append(circ_enum_table)

            if len(circ_by_enum) > 10:
                story.append(Paragraph(
                    f"<i>... and {len(circ_by_enum) - 10} more data collectors</i>",
                    ParagraphStyle('Remaining', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
                ))

        # Show sample outlier subplots with images
        if (total_height_outliers > 0 or total_circ_outliers > 0) and MATPLOTLIB_AVAILABLE:
            story.append(Spacer(1, 0.4*inch))
            story.append(Paragraph("Sample Outlier Subplots", subheading_style))

            # Combine height and circ outliers
            all_outliers = pd.concat([height_outliers_df, circ_outliers_df]).drop_duplicates()

            # Get unique subplots with outliers
            if "SUBPLOT_KEY" in all_outliers.columns:
                outlier_subplots = all_outliers["SUBPLOT_KEY"].unique()[:3]  # Show top 3

                for subplot_key in outlier_subplots:
                    # Get subplot info from filtered_gdf
                    subplot_info = filtered_gdf[filtered_gdf["subplot_id"] == subplot_key]

                    if len(subplot_info) > 0:
                        row = subplot_info.iloc[0]

                        # Extract subplot number
                        match = re.search(r'\[(\d+)\]', str(subplot_key))
                        if match:
                            subplot_display = f"Subplot {match.group(1)}"
                        else:
                            subplot_display = f"Subplot: {str(subplot_key)[:50]}"

                        # Add enumerator name
                        if "enumerator" in row and pd.notna(row["enumerator"]):
                            subplot_display += f" | {row['enumerator']}"

                        # Get outlier details for this subplot
                        subplot_outliers = all_outliers[all_outliers["SUBPLOT_KEY"] == subplot_key]
                        outlier_types = []
                        if len(height_outliers_df[height_outliers_df["SUBPLOT_KEY"] == subplot_key]) > 0:
                            outlier_types.append(f"Height ({len(height_outliers_df[height_outliers_df['SUBPLOT_KEY'] == subplot_key])})")
                        if len(circ_outliers_df[circ_outliers_df["SUBPLOT_KEY"] == subplot_key]) > 0:
                            outlier_types.append(f"Circumference ({len(circ_outliers_df[circ_outliers_df['SUBPLOT_KEY'] == subplot_key])})")

                        if outlier_types:
                            subplot_display += f" | Outliers: {', '.join(outlier_types)}"

                        subplot_header_outlier = ParagraphStyle(
                            "SubplotHeaderOutlier",
                            parent=styles["Heading4"],
                            fontSize=10,
                            textColor=colors.HexColor("#FF6F00"),
                            spaceBefore=12,
                            spaceAfter=6,
                            fontName="Helvetica-Bold",
                        )
                        story.append(Paragraph(subplot_display, subplot_header_outlier))

                        # Create polygon image
                        polygon_img_rl = None
                        try:
                            if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                geom = row["geometry"]

                                fig, ax = plt.subplots(figsize=(3, 2.5), dpi=100)

                                color = '#FF9800'  # Orange for outliers

                                if geom.geom_type == 'Polygon':
                                    x, y = geom.exterior.xy
                                    ax.fill(x, y, color=color, alpha=0.4, edgecolor=color, linewidth=2)
                                    ax.plot(x, y, 'o', color=color, markersize=3)
                                elif geom.geom_type == 'MultiPolygon':
                                    for poly in geom.geoms:
                                        x, y = poly.exterior.xy
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

                                area_text = f"{row.get('area_m2', 0):.1f} m²"
                                ax.set_title(f"{area_text} - OUTLIERS", fontsize=8, fontweight='bold')

                                plt.tight_layout()

                                poly_buffer = BytesIO()
                                plt.savefig(poly_buffer, format='png', dpi=100, bbox_inches='tight', facecolor='white')
                                plt.close(fig)
                                poly_buffer.seek(0)

                                polygon_img_rl = RLImage(poly_buffer, width=2.5*inch, height=2.08*inch)

                        except Exception as e:
                            print(f"DEBUG PDF: Error creating outlier polygon: {str(e)}", file=sys.stderr)

                        # Create details from outlier data with median comparisons
                        detail_items = []

                        # Show sample outliers with detailed explanations
                        for _, outlier_row in subplot_outliers.head(3).iterrows():
                            # Height outlier with median comparison
                            if "tree_height_m" in outlier_row and pd.notna(outlier_row["tree_height_m"]):
                                height_val = outlier_row["tree_height_m"]
                                if "median_height" in outlier_row and pd.notna(outlier_row["median_height"]):
                                    median_val = outlier_row["median_height"]
                                    ratio = height_val / median_val if median_val > 0 else 0
                                    if ratio >= 4:
                                        detail_items.append(
                                            f"<b>Height Outlier:</b> {height_val:.1f}m is {ratio:.1f}x the median ({median_val:.1f}m) for this tree group"
                                        )
                                    elif ratio <= 0.25:
                                        detail_items.append(
                                            f"<b>Height Outlier:</b> {height_val:.1f}m is {ratio:.2f}x the median ({median_val:.1f}m) for this tree group"
                                        )
                                    else:
                                        detail_items.append(f"<b>Height Outlier:</b> {height_val:.1f}m")
                                else:
                                    detail_items.append(f"<b>Height Outlier:</b> {height_val:.1f}m")

                            # Circumference outlier with median comparison
                            circ_cols = [col for col in outlier_row.index if "circumference" in col.lower() and col != "median_circ"]
                            for circ_col in circ_cols:
                                if pd.notna(outlier_row.get(circ_col)):
                                    circ_val = outlier_row[circ_col]
                                    if "median_circ" in outlier_row and pd.notna(outlier_row["median_circ"]):
                                        median_val = outlier_row["median_circ"]
                                        ratio = circ_val / median_val if median_val > 0 else 0
                                        if ratio >= 4:
                                            detail_items.append(
                                                f"<b>Circumference Outlier:</b> {circ_val:.1f}cm is {ratio:.1f}x the median ({median_val:.1f}cm) for this tree group"
                                            )
                                        elif ratio <= 0.25:
                                            detail_items.append(
                                                f"<b>Circumference Outlier:</b> {circ_val:.1f}cm is {ratio:.2f}x the median ({median_val:.1f}cm) for this tree group"
                                            )
                                        else:
                                            detail_items.append(f"<b>Circumference Outlier:</b> {circ_val:.1f}cm")
                                    else:
                                        detail_items.append(f"<b>Circumference Outlier:</b> {circ_val:.1f}cm")
                                    break

                        if len(detail_items) == 0:
                            detail_items.append(f"<b>Outliers detected:</b> {', '.join(outlier_types)}")

                        # Geometry details
                        if "area_m2" in row and pd.notna(row["area_m2"]):
                            detail_items.append(f"<b>Area:</b> {row['area_m2']:.1f} m²")

                        detail_text = "<br/>".join(detail_items)
                        detail_para = Paragraph(detail_text, ParagraphStyle(
                            "DetailsOutlier",
                            parent=styles["Normal"],
                            fontSize=8,
                            leading=10,
                        ))

                        # Create table
                        if polygon_img_rl:
                            detail_table = Table(
                                [[polygon_img_rl, detail_para]],
                                colWidths=[2.8*inch, 3.5*inch]
                            )
                        else:
                            detail_table = Table(
                                [[detail_para]],
                                colWidths=[6.3*inch]
                            )

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
                        story.append(Spacer(1, 0.15*inch))

    else:
        story.append(Paragraph(
            "Vegetation measurement data not available for outlier analysis.",
            normal_style
        ))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
