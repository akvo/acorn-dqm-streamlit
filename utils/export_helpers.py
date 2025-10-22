"""
Export utilities
"""

import json
from datetime import datetime
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
