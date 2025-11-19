"""
Comprehensive PDF Summary Report Generator
Generates a multi-page PDF report summarizing all quality checks across enumerators
"""

import pandas as pd
import sys
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

    # Report date
    report_date = datetime.now().strftime("%B %d, %Y")
    story.append(Paragraph(
        f"Generated on: {report_date}",
        ParagraphStyle('Date', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER)
    ))

    story.append(Spacer(1, 1*inch))

    # Overall Statistics
    total_subplots = len(filtered_gdf)
    total_valid = filtered_gdf["geom_valid"].sum() if "geom_valid" in filtered_gdf.columns else 0
    total_invalid = total_subplots - total_valid
    error_rate = (total_invalid / total_subplots * 100) if total_subplots > 0 else 0

    # Count unique enumerators
    unique_enumerators = filtered_gdf["enumerator"].nunique() if "enumerator" in filtered_gdf.columns else 0

    # Summary statistics table
    summary_data = [
        ["Metric", "Value"],
        ["Total Subplots Analyzed", f"{total_subplots:,}"],
        ["Valid Subplots", f"{total_valid:,} ({total_valid/total_subplots*100:.1f}%)"],
        ["Invalid Subplots", f"{total_invalid:,} ({error_rate:.1f}%)"],
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

    # Geometry errors by enumerator
    if "enumerator" in filtered_gdf.columns and total_invalid > 0:
        enum_errors = filtered_gdf.groupby("enumerator").agg({
            "geom_valid": ["count", "sum"]
        }).reset_index()
        enum_errors.columns = ["Enumerator", "Total Subplots", "Valid Subplots"]
        enum_errors["Invalid Subplots"] = enum_errors["Total Subplots"] - enum_errors["Valid Subplots"]
        enum_errors["Error Rate %"] = (enum_errors["Invalid Subplots"] / enum_errors["Total Subplots"] * 100).round(1)
        enum_errors = enum_errors.sort_values("Error Rate %", ascending=False)

        # Create table
        geom_table_data = [["Data Collector", "Total", "Valid", "Invalid", "Error Rate"]]
        for _, row in enum_errors.head(15).iterrows():
            geom_table_data.append([
                str(row["Enumerator"]),
                str(int(row["Total Subplots"])),
                str(int(row["Valid Subplots"])),
                str(int(row["Invalid Subplots"])),
                f"{row['Error Rate %']:.1f}%",
            ])

        geom_table = Table(geom_table_data, colWidths=[2*inch, 0.9*inch, 0.9*inch, 0.9*inch, 1*inch])
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
    else:
        story.append(Paragraph(
            "Vegetation measurement data not available for outlier analysis.",
            normal_style
        ))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
