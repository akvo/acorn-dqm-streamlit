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

    matplotlib.use("Agg")
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
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # Container for PDF elements
    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#2E7D32"),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#1976D2"),
        spaceAfter=12,
        spaceBefore=20,
        fontName="Helvetica-Bold",
    )

    subheading_style = ParagraphStyle(
        "CustomSubheading",
        parent=styles["Heading3"],
        fontSize=12,
        textColor=colors.HexColor("#FF6F00"),
        spaceAfter=10,
        spaceBefore=15,
        fontName="Helvetica-Bold",
    )

    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
    )

    # ============= COVER PAGE =============
    story.append(Spacer(1, 1 * inch))
    story.append(Paragraph("Ground Truth Data Quality Report", title_style))
    story.append(
        Paragraph(
            f"{partner_name}",
            ParagraphStyle(
                "Partner",
                parent=styles["Normal"],
                fontSize=14,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#388E3C"),
            ),
        )
    )
    story.append(Spacer(1, 0.5 * inch))

    # Report date - show data submission date range
    # Get date range from session state (sidebar filter)
    date_info = ""

    # Try to get date range from raw_data tables
    if "plots_subplots" in raw_data:
        plots_df = raw_data["plots_subplots"]

        # Filter to only the subplots in filtered_gdf
        if "subplot_id" in filtered_gdf.columns and "SUBPLOT_KEY" in plots_df.columns:
            subplot_ids = filtered_gdf["subplot_id"].unique()
            plots_filtered = plots_df[plots_df["SUBPLOT_KEY"].isin(subplot_ids)]

            # Try different date column names
            date_col_found = None
            for col in ["SubmissionDate_subplot", "starttime_subplot", "SubmissionDate", "starttime"]:
                if col in plots_filtered.columns:
                    date_col_found = col
                    break

            if date_col_found:
                submission_dates = pd.to_datetime(plots_filtered[date_col_found], errors="coerce").dropna()
                if len(submission_dates) > 0:
                    min_date = submission_dates.min().strftime("%B %d, %Y")
                    max_date = submission_dates.max().strftime("%B %d, %Y")
                    if min_date == max_date:
                        date_info = f"Report for: {min_date}"
                    else:
                        date_info = f"Report for: {min_date} to {max_date}"

    # Fallback if no date found
    if not date_info:
        report_generated = datetime.now().strftime("%B %d, %Y")
        date_info = f"Report Generated: {report_generated}"

    story.append(
        Paragraph(
            date_info,
            ParagraphStyle(
                "Date",
                parent=styles["Normal"],
                fontSize=11,
                alignment=TA_CENTER,
                leading=14,
                textColor=colors.HexColor("#555555"),
            ),
        )
    )

    story.append(Spacer(1, 1 * inch))

    # Overall Statistics - Filter to only measured subplots
    # Filter to only measured subplots (same as app.py and Plot Issues page)
    if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
        temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()
        temp_df["subplot_number"] = temp_df["subplot_id"].apply(
            lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
        )
        temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
        measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]]["subplot_id"].unique()
        measured_gdf = filtered_gdf[filtered_gdf["subplot_id"].isin(measured_subplot_ids)].copy()
    else:
        measured_gdf = filtered_gdf.copy()

    # Total subplots is the count of MEASURED subplot records only
    total_subplots = len(measured_gdf)

    total_valid = measured_gdf["geom_valid"].sum() if "geom_valid" in measured_gdf.columns else 0
    total_invalid = len(measured_gdf) - total_valid  # Count of invalid records
    error_rate = (total_invalid / len(measured_gdf) * 100) if len(measured_gdf) > 0 else 0

    # Count unique enumerators and plots (from measured subplots only)
    unique_enumerators = measured_gdf["enumerator"].nunique() if "enumerator" in measured_gdf.columns else 0

    # Count unique GT plots per data collector (from measured subplots only)
    unique_plots = 0
    if "subplot_id" in measured_gdf.columns:
        # Extract plot ID from subplot_id (format: uuid:.../sub_plot[n])
        measured_gdf_copy = measured_gdf.copy()
        measured_gdf_copy["plot_id"] = measured_gdf_copy["subplot_id"].apply(
            lambda x: str(x).split("/sub_plot")[0] if pd.notna(x) and "/sub_plot" in str(x) else str(x)
        )
        unique_plots = measured_gdf_copy["plot_id"].nunique()

    # Summary statistics table
    summary_data = [
        ["Metric", "Value"],
        ["Total Subplots Measured", f"{total_subplots:,}"],
        ["Valid Subplots", f"{total_valid:,} ({total_valid / len(measured_gdf) * 100:.1f}%)"],
        ["Invalid Subplots", f"{total_invalid:,} ({error_rate:.1f}%)"],
        ["GT Plots", f"{unique_plots:,}"],
        ["Data Collectors", f"{unique_enumerators}"],
    ]

    story.append(Paragraph("📊 Executive Summary", heading_style))
    summary_table = Table(summary_data, colWidths=[3 * inch, 2.5 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#E8F5E9")),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("PADDING", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#E8F5E9"), colors.white]),
            ]
        )
    )
    story.append(summary_table)

    story.append(PageBreak())

    # ============= GEOMETRY QUALITY CHECK =============
    story.append(Paragraph("📐 Geometry Quality Check Summary", heading_style))

    # Most common errors (from measured subplots only)
    if "reasons" in measured_gdf.columns and total_invalid > 0:
        invalid_gdf = measured_gdf[~measured_gdf["geom_valid"]].copy()

        # Count error types
        error_reasons = []
        for reasons_str in invalid_gdf["reasons"].dropna():
            # Split by common delimiters
            reasons = str(reasons_str).split(";")
            error_reasons.extend([r.strip() for r in reasons if r.strip()])

        if error_reasons:
            error_counts = Counter(error_reasons)
            most_common = error_counts.most_common(1)[0]

            story.append(
                Paragraph(
                    f"The most common issue noticed was: <b>{most_common[0]}</b> ({most_common[1]} occurrences)",
                    normal_style,
                )
            )
            story.append(Spacer(1, 0.3 * inch))

    # Geometry errors by enumerator with GT plot count (from measured subplots only)
    if "enumerator" in measured_gdf.columns and total_invalid > 0:
        # Calculate stats per enumerator
        enum_stats_list = []
        for enum_name in measured_gdf["enumerator"].unique():
            enum_data = measured_gdf[measured_gdf["enumerator"] == enum_name]

            # Filter to only measured subplots
            if "subplot_id" in enum_data.columns and "measured_subplots" in enum_data.columns:
                temp_df = enum_data[["subplot_id", "measured_subplots"]].copy()
                temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                    lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
                )
                temp_df["measured_subplots_int"] = temp_df["measured_subplots"].apply(
                    lambda x: int(x) if pd.notna(x) else 999
                )
                measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots_int"]][
                    "subplot_id"
                ].unique()
                enum_data_filtered = enum_data[enum_data["subplot_id"].isin(measured_subplot_ids)].copy()
            else:
                enum_data_filtered = enum_data.copy()

            # Count GT plots
            enum_plot_count = 0
            if "subplot_id" in enum_data_filtered.columns:
                enum_data_copy = enum_data_filtered.copy()
                enum_data_copy["plot_id"] = enum_data_copy["subplot_id"].apply(
                    lambda x: str(x).split("/sub_plot")[0] if pd.notna(x) and "/sub_plot" in str(x) else str(x)
                )
                enum_plot_count = enum_data_copy["plot_id"].nunique()

            total_recs = len(enum_data_filtered)
            valid_recs = enum_data_filtered["geom_valid"].sum()
            invalid_recs = total_recs - valid_recs
            error_rate = (invalid_recs / total_recs * 100) if total_recs > 0 else 0

            enum_stats_list.append(
                {
                    "Enumerator": enum_name,
                    "GT Plots": enum_plot_count,
                    "Total Subplots": total_recs,
                    "Valid Subplots": valid_recs,
                    "Invalid Subplots": invalid_recs,
                    "Error Rate %": error_rate,
                }
            )

        enum_errors = pd.DataFrame(enum_stats_list)
        enum_errors = enum_errors.sort_values("Error Rate %", ascending=False)

        # Create table with GT plot count
        geom_table_data = [["Data Collector", "GT Plots", "Sub Plots", "Valid", "Invalid", "Error %"]]
        for _, row in enum_errors.head(15).iterrows():
            geom_table_data.append(
                [
                    str(row["Enumerator"]),
                    str(int(row["GT Plots"])),
                    str(int(row["Total Subplots"])),
                    str(int(row["Valid Subplots"])),
                    str(int(row["Invalid Subplots"])),
                    f"{row['Error Rate %']:.1f}%",
                ]
            )

        geom_table = Table(
            geom_table_data, colWidths=[2.0 * inch, 0.7 * inch, 0.7 * inch, 0.7 * inch, 0.7 * inch, 0.8 * inch]
        )
        geom_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("PADDING", (0, 1), (-1, -1), 6),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                ]
            )
        )
        story.append(geom_table)

        if len(enum_errors) > 15:
            story.append(Spacer(1, 0.1 * inch))
            story.append(
                Paragraph(
                    f"<i>... and {len(enum_errors) - 15} more data collectors</i>",
                    ParagraphStyle("Remaining", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
                )
            )

    story.append(Spacer(1, 0.3 * inch))

    # Detailed error breakdown
    if "reasons" in filtered_gdf.columns and total_invalid > 0 and error_reasons:
        story.append(Paragraph("Error Type Breakdown", subheading_style))
        error_counts = Counter(error_reasons)
        error_breakdown_data = [["Error Type", "Count", "Percentage"]]

        for error_type, count in error_counts.most_common(10):
            pct = count / total_invalid * 100
            error_breakdown_data.append(
                [
                    error_type,
                    str(count),
                    f"{pct:.1f}%",
                ]
            )

        error_table = Table(error_breakdown_data, colWidths=[3.5 * inch, 1 * inch, 1.2 * inch])
        error_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6F00")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (0, -1), "LEFT"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFF3E0")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("PADDING", (0, 1), (-1, -1), 6),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF8F0")]),
                ]
            )
        )
        story.append(error_table)

        # Add explanations for common error types
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("Common Error Explanations", subheading_style))

        explanations = {
            "Empty geometry": "No valid GPS coordinates were collected for this subplot. This occurs when: (1) No GPS points were recorded, or (2) All GPS points had zero accuracy and were filtered out.",
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
            story.append(
                Paragraph(
                    explanation_text,
                    ParagraphStyle(
                        "Explanations",
                        parent=styles["Normal"],
                        fontSize=9,
                        leading=12,
                        leftIndent=10,
                    ),
                )
            )

    # ============= LIVING FENCES TABLE =============
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("🌿 Plots with Living Fences", subheading_style))

    # Get living fences data from raw_data
    veg_df = raw_data.get("plots_subplots_vegetation")

    if veg_df is not None and len(veg_df) > 0 and "vegetation_species_type" in veg_df.columns:
        # Filter to records where vegetation_species_type is "living_fences"
        living_fences_df = veg_df[veg_df["vegetation_species_type"].astype(str).str.lower() == "living_fences"].copy()

        if len(living_fences_df) > 0:
            # Extract PLOT_KEY from SUBPLOT_KEY (format: uuid:xxx/sub_plot[n])
            if "SUBPLOT_KEY" in living_fences_df.columns:
                living_fences_df["PLOT_KEY"] = living_fences_df["SUBPLOT_KEY"].apply(
                    lambda x: str(x).split("/")[0] if pd.notna(x) and "/" in str(x) else str(x)
                )

            # Count occurrences per plot
            living_fences_summary = living_fences_df.groupby("PLOT_KEY").size().reset_index(name="count")

            # Sort by count descending
            living_fences_summary = living_fences_summary.sort_values("count", ascending=False)

            story.append(Paragraph(f"{len(living_fences_summary)} plots have living fences recorded.", normal_style))
            story.append(Spacer(1, 0.1 * inch))

            # Create table data
            living_fences_table_data = [["Plot ID", "Has Living Fences", "Count"]]
            for _, row in living_fences_summary.head(20).iterrows():
                # Truncate plot ID if too long
                plot_id = str(row["PLOT_KEY"])
                if len(plot_id) > 40:
                    plot_id = plot_id[:37] + "..."

                living_fences_table_data.append([plot_id, "Yes", str(int(row["count"]))])

            living_fences_table = Table(living_fences_table_data, colWidths=[3.5 * inch, 1.5 * inch, 1.5 * inch])
            living_fences_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E7D32")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("ALIGN", (1, 0), (1, -1), "CENTER"),
                        ("ALIGN", (2, 0), (2, -1), "LEFT"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#E8F5E9")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("PADDING", (0, 1), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F8E9")]),
                    ]
                )
            )
            story.append(living_fences_table)

            if len(living_fences_summary) > 20:
                story.append(Spacer(1, 0.1 * inch))
                story.append(
                    Paragraph(
                        f"<i>... and {len(living_fences_summary) - 20} more plots with living fences</i>",
                        ParagraphStyle("Remaining", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
                    )
                )
        else:
            story.append(Paragraph("No plots with living fences recorded in this dataset.", normal_style))
    else:
        story.append(Paragraph("Living fences data not available in this dataset.", normal_style))

    # Show individual maps grouped by GT Plot, then subplots (from measured subplots only)
    if "enumerator" in measured_gdf.columns and MATPLOTLIB_AVAILABLE:
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("Maps by Data Collector and GT Plot", subheading_style))

        for enum_name in sorted(measured_gdf["enumerator"].unique()):
            enum_data = measured_gdf[measured_gdf["enumerator"] == enum_name]

            print(f"DEBUG PDF SUMMARY: {enum_name} - BEFORE filtering: {len(enum_data)} subplots", file=sys.stderr)

            # Filter to only measured subplots
            # First try: Use vegetation data to determine which subplots actually have measurements
            if raw_data and "plots_subplots_vegetation" in raw_data:
                veg_data = raw_data["plots_subplots_vegetation"]
                if "SUBPLOT_KEY" in veg_data.columns and "subplot_id" in enum_data.columns:
                    # Get subplot IDs that have vegetation data
                    veg_subplot_ids = veg_data["SUBPLOT_KEY"].unique()
                    # Filter enum_data to only subplots with vegetation
                    enum_data_with_veg = enum_data[enum_data["subplot_id"].isin(veg_subplot_ids)].copy()

                    if len(enum_data_with_veg) > 0:
                        print(
                            f"DEBUG PDF SUMMARY: {enum_name} - Filtered to {len(enum_data_with_veg)} subplots with vegetation data",
                            file=sys.stderr,
                        )
                        enum_data = enum_data_with_veg
                    else:
                        # Fallback: use measured_subplots field
                        print(
                            f"DEBUG PDF SUMMARY: {enum_name} - No vegetation data found, using measured_subplots field",
                            file=sys.stderr,
                        )
                        if "subplot_id" in enum_data.columns and "measured_subplots" in enum_data.columns:
                            temp_df = enum_data[["subplot_id", "measured_subplots"]].copy()
                            temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                                if re.search(r"\[(\d+)\]", str(x))
                                else 999
                            )
                            temp_df["measured_subplots_int"] = temp_df["measured_subplots"].apply(
                                lambda x: int(x) if pd.notna(x) else 999
                            )
                            measured_subplot_ids = temp_df[
                                temp_df["subplot_number"] <= temp_df["measured_subplots_int"]
                            ]["subplot_id"].unique()
                            enum_data = enum_data[enum_data["subplot_id"].isin(measured_subplot_ids)].copy()
                else:
                    print(f"DEBUG PDF SUMMARY: {enum_name} - SUBPLOT_KEY not in vegetation data", file=sys.stderr)
            else:
                # Fallback: use measured_subplots field if vegetation data not available
                if "subplot_id" in enum_data.columns and "measured_subplots" in enum_data.columns:
                    temp_df = enum_data[["subplot_id", "measured_subplots"]].copy()
                    temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                        lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                        if re.search(r"\[(\d+)\]", str(x))
                        else 999
                    )
                    temp_df["measured_subplots_int"] = temp_df["measured_subplots"].apply(
                        lambda x: int(x) if pd.notna(x) else 999
                    )
                    measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots_int"]][
                        "subplot_id"
                    ].unique()
                    enum_data = enum_data[enum_data["subplot_id"].isin(measured_subplot_ids)].copy()

            print(f"DEBUG PDF SUMMARY: {enum_name} - AFTER filtering: {len(enum_data)} subplots", file=sys.stderr)

            if len(enum_data) > 0:
                # Add enumerator header
                story.append(
                    Paragraph(
                        f"<b>{enum_name}</b>",
                        ParagraphStyle(
                            "EnumHeader",
                            parent=styles["Heading3"],
                            fontSize=12,
                            textColor=colors.HexColor("#1976D2"),
                            spaceAfter=10,
                        ),
                    )
                )

                print(f"DEBUG PDF SUMMARY: {enum_name} - columns: {enum_data.columns.tolist()}", file=sys.stderr)
                print(f"DEBUG PDF SUMMARY: PLOT_KEY in columns: {'PLOT_KEY' in enum_data.columns}", file=sys.stderr)
                if "PLOT_KEY" in enum_data.columns:
                    print(
                        f"DEBUG PDF SUMMARY: {enum_name} - Number of unique GT Plots: {enum_data['PLOT_KEY'].nunique()}",
                        file=sys.stderr,
                    )
                    print(
                        f"DEBUG PDF SUMMARY: {enum_name} - GT Plot keys: {enum_data['PLOT_KEY'].unique()}",
                        file=sys.stderr,
                    )

                # Group by GT Plot (PLOT_KEY)
                if "PLOT_KEY" in enum_data.columns:
                    for plot_key in sorted(enum_data["PLOT_KEY"].unique()):
                        plot_data = enum_data[enum_data["PLOT_KEY"] == plot_key]

                        # Extract plot number from PLOT_KEY
                        plot_display = str(plot_key).split("/")[-1] if "/" in str(plot_key) else str(plot_key)

                        # Debug: Check measured_subplots for this plot
                        if "measured_subplots" in plot_data.columns:
                            measured_val = plot_data["measured_subplots"].iloc[0] if len(plot_data) > 0 else "N/A"
                            print(
                                f"DEBUG PDF SUMMARY: Plot {plot_display} - has {len(plot_data)} subplots BEFORE spatial filtering, measured_subplots={measured_val}",
                                file=sys.stderr,
                            )

                        # SPATIAL FILTER: Remove subplots that are far outside the GT plot
                        # Get the GT plot polygon if available
                        if "PLOT_KEY" in plot_data.columns and len(plot_data) > 0:
                            # Try to get GT plot geometry from raw_data
                            gt_plot_geom = None
                            if raw_data and "plots" in raw_data:
                                plots_df = raw_data["plots"]
                                if "KEY" in plots_df.columns:
                                    plot_record = plots_df[plots_df["KEY"] == plot_key]
                                    if len(plot_record) > 0 and "geometry" in plot_record.columns:
                                        gt_plot_geom = plot_record.iloc[0]["geometry"]

                            # If we have the GT plot geometry, filter subplots spatially
                            if gt_plot_geom and hasattr(gt_plot_geom, "is_valid") and not gt_plot_geom.is_empty:
                                # Create a buffer around the GT plot (200m tolerance for GPS errors)
                                # Convert to meters for buffering
                                try:
                                    from shapely.ops import transform
                                    import pyproj

                                    # Create a transformer to convert to UTM (meters) for buffering
                                    # Use WGS84 to UTM for the plot's location
                                    centroid = gt_plot_geom.centroid
                                    utm_zone = int((centroid.x + 180) / 6) + 1
                                    utm_crs = pyproj.CRS(f"+proj=utm +zone={utm_zone} +datum=WGS84")
                                    wgs84 = pyproj.CRS("EPSG:4326")

                                    project_to_utm = pyproj.Transformer.from_crs(
                                        wgs84, utm_crs, always_xy=True
                                    ).transform
                                    project_to_wgs84 = pyproj.Transformer.from_crs(
                                        utm_crs, wgs84, always_xy=True
                                    ).transform

                                    # Transform to UTM, buffer, transform back
                                    gt_plot_utm = transform(project_to_utm, gt_plot_geom)
                                    buffered_utm = gt_plot_utm.buffer(200)  # 200m buffer
                                    buffered_wgs84 = transform(project_to_wgs84, buffered_utm)

                                    # Filter subplots to only those that intersect with buffered GT plot
                                    plot_data_filtered = []
                                    for idx, row in plot_data.iterrows():
                                        subplot_geom = row.get("geometry")
                                        if (
                                            subplot_geom
                                            and hasattr(subplot_geom, "is_valid")
                                            and not subplot_geom.is_empty
                                        ):
                                            # Check if subplot intersects with buffered GT plot
                                            if buffered_wgs84.intersects(subplot_geom):
                                                plot_data_filtered.append(row)
                                            else:
                                                subplot_id = row.get("subplot_id", "unknown")
                                                print(
                                                    f"DEBUG PDF SUMMARY: Excluding subplot {subplot_id} - outside GT plot boundary",
                                                    file=sys.stderr,
                                                )

                                    if len(plot_data_filtered) > 0:
                                        plot_data = pd.DataFrame(plot_data_filtered)
                                        print(
                                            f"DEBUG PDF SUMMARY: Plot {plot_display} - {len(plot_data)} subplots AFTER spatial filtering",
                                            file=sys.stderr,
                                        )
                                    else:
                                        print(
                                            f"DEBUG PDF SUMMARY: Plot {plot_display} - WARNING: All subplots filtered out by spatial check",
                                            file=sys.stderr,
                                        )

                                except Exception as e:
                                    print(
                                        f"DEBUG PDF SUMMARY: Spatial filtering failed: {str(e)}, using all subplots",
                                        file=sys.stderr,
                                    )
                            else:
                                print(
                                    f"DEBUG PDF SUMMARY: Plot {plot_display} - No GT plot geometry available, skipping spatial filter",
                                    file=sys.stderr,
                                )

                        # Count stats for this plot (after spatial filtering)
                        plot_total = len(plot_data)
                        plot_valid = plot_data["geom_valid"].sum() if len(plot_data) > 0 else 0
                        plot_invalid = plot_total - plot_valid

                        try:
                            print(
                                f"DEBUG PDF: Creating map for {enum_name} - Plot {plot_display} with {len(plot_data)} subplots",
                                file=sys.stderr,
                            )

                            fig, ax = plt.subplots(figsize=(5, 3.5), dpi=100)

                            # Count polygons plotted
                            polygons_plotted = 0

                            # Plot subplots for this GT plot
                            for idx, row in plot_data.iterrows():
                                if pd.notna(row.get("geometry")) and not row["geometry"].is_empty:
                                    geom = row["geometry"]
                                    is_valid = row.get("geom_valid", False)
                                    color = "#4CAF50" if is_valid else "#F44336"
                                    alpha = 0.3 if is_valid else 0.6

                                    if geom.geom_type == "Polygon":
                                        x, y = geom.exterior.xy
                                        ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)
                                        polygons_plotted += 1
                                    elif geom.geom_type == "MultiPolygon":
                                        for poly in geom.geoms:
                                            x, y = poly.exterior.xy
                                            ax.fill(x, y, color=color, alpha=alpha, edgecolor=color, linewidth=1.5)
                                            polygons_plotted += 1

                            print(
                                f"DEBUG PDF: Plotted {polygons_plotted} polygons for plot {plot_display}",
                                file=sys.stderr,
                            )

                            ax.set_aspect("equal")
                            ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.5)
                            ax.set_xlabel("Longitude", fontsize=8)
                            ax.set_ylabel("Latitude", fontsize=8)

                            # Get submission date for this plot
                            submission_date_str = ""
                            if "SubmissionDate" in plot_data.columns and len(plot_data) > 0:
                                sub_date = plot_data["SubmissionDate"].iloc[0]
                                if pd.notna(sub_date):
                                    try:
                                        if isinstance(sub_date, str):
                                            sub_date = pd.to_datetime(sub_date)
                                        submission_date_str = f" | Date: {sub_date.strftime('%Y-%m-%d')}"
                                    except Exception:
                                        pass

                            ax.set_title(
                                f"GT Plot: {plot_display}{submission_date_str} | Subplots: {plot_total} | Valid: {plot_valid}, Invalid: {plot_invalid}",
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

                            # Convert to image
                            map_buffer = BytesIO()
                            plt.savefig(map_buffer, format="png", dpi=100, bbox_inches="tight", facecolor="white")
                            plt.close(fig)
                            map_buffer.seek(0)

                            plot_img = RLImage(map_buffer, width=4.5 * inch, height=3.2 * inch)
                            story.append(plot_img)
                            story.append(Spacer(1, 0.15 * inch))

                        except Exception as e:
                            print(f"DEBUG PDF: Error creating map for plot {plot_display}: {str(e)}", file=sys.stderr)

                story.append(Spacer(1, 0.2 * inch))

    story.append(PageBreak())

    # ============= VEGETATION OUTLIERS SUMMARY =============
    story.append(Paragraph("🌿 Vegetation & Measurement Outliers", heading_style))

    # Add outlier explanations
    outlier_explanation = """
<b>What are outliers and measurement issues?</b><br/>
We detect measurement issues by comparing tree measurements to expected ranges and group medians:<br/><br/>

<b>Height Outliers:</b><br/>
• <b>Extremely tall trees:</b> Height is more than 4 times the group median (measurement error, wrong species, or exceptionally favorable growing conditions)<br/>
• <b>Extremely short trees:</b> Height is less than 0.25 times the group median (measurement error, damaged/stunted tree, or seedling)<br/><br/>

<b>Circumference Outliers:</b><br/>
• <b>Extremely thick trees:</b> Circumference is more than 4 times the group median (measurement error, wrong tree, or multiple stems counted as one)<br/>
• <b>Extremely thin trees:</b> Circumference is less than 0.25 times the group median (measurement error, young sapling, or damaged tree)<br/><br/>

<b>High Stem Counts:</b><br/>
• <b>Trees with >20 stems:</b> More than 20 stems counted at breast height (measurement error, incorrect counting, or coppiced/multi-stemmed tree requiring verification)<br/><br/>

<i>Note: Median calculation methodology is based on the Rabobank script.</i>
"""
    story.append(
        Paragraph(
            outlier_explanation,
            ParagraphStyle(
                "OutlierExplanation",
                parent=styles["Normal"],
                fontSize=9,
                leading=12,
                leftIndent=10,
                spaceAfter=15,
            ),
        )
    )

    # Get measurement data for outlier analysis
    has_measurements = "plots_subplots_vegetation_measurements" in raw_data

    if has_measurements:
        from utils.data_merge_utils import merge_with_enumerator, get_species_column

        meas_df = raw_data["plots_subplots_vegetation_measurements"].copy()

        # Filter to only measured subplots
        measured_subplot_ids = measured_gdf["subplot_id"].unique() if "subplot_id" in measured_gdf.columns else []
        if len(measured_subplot_ids) > 0 and "SUBPLOT_KEY" in meas_df.columns:
            meas_df = meas_df[meas_df["SUBPLOT_KEY"].isin(measured_subplot_ids)].copy()

        meas_with_enum = merge_with_enumerator(meas_df, measured_gdf)
        species_col = get_species_column(meas_with_enum)

        # Height Outliers
        height_outliers_df = pd.DataFrame()
        if "tree_height_m" in meas_with_enum.columns and "VEGETATION_KEY" in meas_with_enum.columns:
            height_check = meas_with_enum[
                meas_with_enum["tree_height_m"].notna() & meas_with_enum["VEGETATION_KEY"].notna()
            ].copy()

            if len(height_check) > 0:
                median_check = (
                    height_check.groupby("VEGETATION_KEY")["tree_height_m"].median().reset_index(name="median_height")
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
                    (height_total["Upper_outliers"] == "outlier") | (height_total["Lower_outliers"] == "outlier")
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
                        circ_check.groupby("VEGETATION_KEY")[circ_col].median().reset_index(name="median_circ")
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
                        (circ_total["Upper_outliers"] == "outlier") | (circ_total["Lower_outliers"] == "outlier")
                    ].copy()
                    circ_outliers_df = pd.concat([circ_outliers_df, outliers]).drop_duplicates()

        # High Stem Counts (>20 stems)
        high_stems_df = pd.DataFrame()
        if "nr_stems_bh" in meas_with_enum.columns:
            high_stems = meas_with_enum[meas_with_enum["nr_stems_bh"] > 20].copy()
            if len(high_stems) > 0:
                high_stems_df = high_stems.copy()

        # Summary statistics
        total_height_outliers = len(height_outliers_df)
        total_circ_outliers = len(circ_outliers_df)
        total_high_stems = len(high_stems_df)

        outlier_summary_data = [
            ["Outlier Type", "Count"],
            ["Height Outliers", str(total_height_outliers)],
            ["Circumference Outliers", str(total_circ_outliers)],
            ["High Stem Counts (>20)", str(total_high_stems)],
            ["Total Vegetation Issues", str(total_height_outliers + total_circ_outliers + total_high_stems)],
        ]

        outlier_summary_table = Table(outlier_summary_data, colWidths=[3 * inch, 2 * inch])
        outlier_summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF6F00")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#FFF3E0")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("PADDING", (0, 1), (-1, -1), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF8F0")]),
                ]
            )
        )
        story.append(outlier_summary_table)
        story.append(Spacer(1, 0.3 * inch))

        # Height outliers details
        if total_height_outliers > 0:
            story.append(Paragraph("Height Outliers - Details", subheading_style))
            story.append(
                Paragraph(
                    "<i>Ratio = Measured Height ÷ Group Median Height (e.g., 4.0x means the tree is 4 times taller than the median). Median calculated per Rabobank methodology.</i>",
                    ParagraphStyle(
                        "RatioExplanation",
                        parent=styles["Normal"],
                        fontSize=8,
                        textColor=colors.grey,
                        spaceAfter=8,
                        leftIndent=10,
                    ),
                )
            )

            # Debug: Print available columns
            print(f"DEBUG PDF: Height outliers columns: {height_outliers_df.columns.tolist()}", file=sys.stderr)

            # Prepare detailed outlier data
            height_details_df = height_outliers_df.copy()
            if "median_height" in height_details_df.columns and "tree_height_m" in height_details_df.columns:
                height_details_df["ratio"] = height_details_df.apply(
                    lambda row: row["tree_height_m"] / row["median_height"]
                    if pd.notna(row["median_height"]) and row["median_height"] > 0
                    else 0,
                    axis=1,
                )

            # Sort by ratio (most extreme outliers first)
            if "ratio" in height_details_df.columns:
                height_details_df = height_details_df.sort_values("ratio", ascending=False)

            # Create detailed table
            height_detail_data = [["Height (m)", "Median (m)", "Ratio", "Issue"]]
            for _, row in height_details_df.head(15).iterrows():
                height = row.get("tree_height_m", 0)
                median = row.get("median_height", 0)
                ratio = row.get("ratio", 0)

                # Determine issue type
                if ratio >= 4:
                    issue = "Extremely tall"
                elif ratio <= 0.25:
                    issue = "Extremely short"
                else:
                    issue = "Outlier"

                height_detail_data.append([f"{height:.1f}", f"{median:.1f}", f"{ratio:.1f}x", issue])

            height_detail_table = Table(height_detail_data, colWidths=[1.4 * inch, 1.4 * inch, 1.4 * inch, 1.5 * inch])
            height_detail_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("PADDING", (0, 1), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ]
                )
            )
            story.append(height_detail_table)

            if len(height_details_df) > 15:
                story.append(
                    Paragraph(
                        f"<i>Showing top 15 of {len(height_details_df)} height outliers</i>",
                        ParagraphStyle("Remaining", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
                    )
                )

        story.append(Spacer(1, 0.3 * inch))

        # Circumference outliers details
        if total_circ_outliers > 0:
            story.append(Paragraph("Circumference Outliers - Details", subheading_style))
            story.append(
                Paragraph(
                    "<i>Ratio = Measured Circumference ÷ Group Median Circumference (e.g., 4.0x means the tree is 4 times thicker than the median). Median calculated per Rabobank methodology.</i>",
                    ParagraphStyle(
                        "RatioExplanation",
                        parent=styles["Normal"],
                        fontSize=8,
                        textColor=colors.grey,
                        spaceAfter=8,
                        leftIndent=10,
                    ),
                )
            )

            # Prepare detailed outlier data
            circ_details_df = circ_outliers_df.copy()

            # Find circumference column
            circ_cols = [
                col for col in circ_details_df.columns if "circumference" in col.lower() and col != "median_circ"
            ]
            circ_col = circ_cols[0] if circ_cols else None

            if circ_col and "median_circ" in circ_details_df.columns:
                circ_details_df["ratio"] = circ_details_df.apply(
                    lambda row: row[circ_col] / row["median_circ"]
                    if pd.notna(row.get("median_circ")) and row["median_circ"] > 0
                    else 0,
                    axis=1,
                )

            # Sort by ratio (most extreme outliers first)
            if "ratio" in circ_details_df.columns:
                circ_details_df = circ_details_df.sort_values("ratio", ascending=False)

            # Create detailed table
            circ_detail_data = [["Circ (cm)", "Median (cm)", "Ratio", "Issue"]]
            for _, row in circ_details_df.head(15).iterrows():
                circ = row.get(circ_col, 0) if circ_col else 0
                median = row.get("median_circ", 0)
                ratio = row.get("ratio", 0)

                # Determine issue type
                if ratio >= 4:
                    issue = "Extremely thick"
                elif ratio <= 0.25:
                    issue = "Extremely thin"
                else:
                    issue = "Outlier"

                circ_detail_data.append([f"{circ:.1f}", f"{median:.1f}", f"{ratio:.1f}x", issue])

            circ_detail_table = Table(circ_detail_data, colWidths=[1.4 * inch, 1.4 * inch, 1.4 * inch, 1.5 * inch])
            circ_detail_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (0, -1), "LEFT"),
                        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("PADDING", (0, 1), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ]
                )
            )
            story.append(circ_detail_table)

            if len(circ_details_df) > 15:
                story.append(
                    Paragraph(
                        f"<i>Showing top 15 of {len(circ_details_df)} circumference outliers</i>",
                        ParagraphStyle("Remaining", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
                    )
                )

        story.append(Spacer(1, 0.3 * inch))

        # High Stem Counts details
        if total_high_stems > 0:
            story.append(Paragraph("High Stem Counts - Details", subheading_style))

            # Prepare detailed high stem data
            high_stems_details = high_stems_df.copy()

            # Sort by stem count (highest first)
            if "nr_stems_bh" in high_stems_details.columns:
                high_stems_details = high_stems_details.sort_values("nr_stems_bh", ascending=False)

            # Create detailed table
            stem_detail_data = [["Stems (BH)", "Threshold", "Issue"]]
            for _, row in high_stems_details.head(15).iterrows():
                stems = row.get("nr_stems_bh", 0)

                stem_detail_data.append([f"{int(stems)}", ">20", "High stem count"])

            stem_detail_table = Table(stem_detail_data, colWidths=[2 * inch, 2 * inch, 2.7 * inch])
            stem_detail_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1976D2")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 9),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 8),
                        ("PADDING", (0, 1), (-1, -1), 6),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
                    ]
                )
            )
            story.append(stem_detail_table)

            if len(high_stems_details) > 15:
                story.append(
                    Paragraph(
                        f"<i>Showing top 15 of {len(high_stems_details)} high stem counts</i>",
                        ParagraphStyle("Remaining", parent=styles["Normal"], fontSize=9, textColor=colors.grey),
                    )
                )

    else:
        story.append(Paragraph("Vegetation measurement data not available for outlier analysis.", normal_style))

    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer
