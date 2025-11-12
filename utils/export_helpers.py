"""
Export utilities
"""

import json
from datetime import datetime
import pandas as pd
import config


def create_validation_report(summary, filename):
    """Create JSON validation report"""
    report = {
        "partner": config.PARTNER,
        "country": config.COUNTRY,
        "timestamp": datetime.now().isoformat(),
        "filename": filename,
        "summary": {
            "total_subplots": summary["total"],
            "valid_subplots": summary["valid"],
            "invalid_subplots": summary["invalid"],
            "valid_percentage": round(summary["valid_pct"], 2),
        },
        "validation_thresholds": {
            "min_subplot_area": config.MIN_SUBPLOT_AREA_SIZE,
            "max_subplot_area": config.MAX_SUBPLOT_AREA_SIZE,
            "gps_accuracy": config.GPS_ACCURACY_THRESHOLD,
            "max_vertices": config.MAX_VERTICES,
        },
        "error_breakdown": summary["reason_counts"],
    }

    return json.dumps(report, indent=2)


def create_geojson_export(gdf, valid_only=True):
    """Create GeoJSON export"""
    if valid_only:
        gdf = gdf[gdf["geom_valid"]]

    return gdf.to_json()


def create_csv_export(gdf, valid_only=False):
    """Create CSV export (without geometry)"""
    export_df = gdf.copy()

    if valid_only:
        export_df = export_df[export_df["geom_valid"]]

    # Remove geometry columns
    cols_to_drop = ["geometry", "geojson"]
    cols_to_drop = [c for c in cols_to_drop if c in export_df.columns]
    export_df = export_df.drop(columns=cols_to_drop)

    return export_df.to_csv(index=False)


def adjust_excel_column_widths(worksheet, dataframe, min_width=10, max_width=50):
    """
    Automatically adjust Excel column widths based on content.

    This function calculates optimal column widths by examining both the header
    names and the actual data content, ensuring the Excel export is readable
    without being too congested.

    Args:
        worksheet: openpyxl worksheet object
        dataframe: pandas DataFrame that was written to the worksheet
        min_width: Minimum column width (default: 10)
        max_width: Maximum column width (default: 50)

    Returns:
        None (modifies worksheet in place)

    Example:
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Data', index=False)
            worksheet = writer.sheets['Data']
            adjust_excel_column_widths(worksheet, df)
    """
    if dataframe is None or len(dataframe) == 0:
        return

    try:
        from openpyxl.utils import get_column_letter

        for idx, col in enumerate(dataframe.columns):
            column_letter = get_column_letter(idx + 1)

            # Start with header length
            max_length = len(str(col))

            # Check content length in first 100 rows (for performance)
            sample_size = min(100, len(dataframe))
            if sample_size > 0:
                # Get max length from sample of data
                col_data = dataframe[col].head(sample_size).astype(str)
                if len(col_data) > 0:
                    content_max = col_data.str.len().max()
                    if pd.notna(content_max):
                        max_length = max(max_length, content_max)

            # Apply min/max constraints
            # Add 2 for padding
            adjusted_width = min(max(max_length + 2, min_width), max_width)

            # Set the column width
            worksheet.column_dimensions[column_letter].width = adjusted_width

    except Exception as e:
        # Fail silently - column width adjustment is a nice-to-have
        pass
