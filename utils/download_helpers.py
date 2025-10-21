"""
Download and export functionality
"""

import json
import io
import zipfile
from datetime import datetime
import pandas as pd
from typing import Dict, List
import config


def create_hierarchical_json(plot_data: Dict) -> Dict:
    """
    Create detailed hierarchical JSON structure
    """
    return {
        "plot_id": plot_data.get("plot_id"),
        "enumerator": plot_data.get("enumerator"),
        "collection_date": str(plot_data.get("collection_date", "")),
        "validation_status": plot_data.get("validation_status", "unknown"),
        "issues_summary": plot_data.get("issues_summary", {}),
        "geometry": plot_data.get("geometry"),
        "subplots": plot_data.get("subplots", []),
        "metadata": {
            "partner": plot_data.get("partner"),
            "country": plot_data.get("country"),
            "validation_date": datetime.now().isoformat(),
            "validation_rules": {
                "min_subplot_area": config.MIN_SUBPLOT_AREA_SIZE,
                "max_subplot_area": config.MAX_SUBPLOT_AREA_SIZE,
                "max_plot_area": config.MAX_PLOT_AREA_SIZE,
                "max_vertices": config.MAX_VERTICES,
            },
        },
    }


def create_flat_json(plot_data: Dict) -> Dict:
    """
    Create flat JSON focused on issues
    """
    issues = []

    for subplot in plot_data.get("subplots", []):
        subplot_id = subplot.get("subplot_id")
        for issue in subplot.get("issues", []):
            issues.append(
                {
                    "subplot": subplot_id,
                    "issue": issue.get("message"),
                    "severity": issue.get("severity"),
                    "field": issue.get("field"),
                    "current_value": issue.get("value"),
                    "threshold": issue.get("threshold"),
                }
            )

    return {
        "plot_id": plot_data.get("plot_id"),
        "enumerator": plot_data.get("enumerator"),
        "collection_date": str(plot_data.get("collection_date", "")),
        "total_subplots": len(plot_data.get("subplots", [])),
        "invalid_subplots": len(
            [s for s in plot_data.get("subplots", []) if not s.get("valid", True)]
        ),
        "validation_errors": issues,
    }


def create_geojson(plot_data: Dict) -> Dict:
    """
    Create GeoJSON for GIS software
    """
    features = []

    for subplot in plot_data.get("subplots", []):
        if subplot.get("geometry"):
            feature = {
                "type": "Feature",
                "properties": {
                    "id": subplot.get("subplot_id"),
                    "plot_id": plot_data.get("plot_id"),
                    "status": "valid" if subplot.get("valid", False) else "invalid",
                    "area_m2": subplot.get("area_m2"),
                    "issues": "; ".join(
                        [i["message"] for i in subplot.get("issues", [])]
                    ),
                    "issue_count": len(subplot.get("issues", [])),
                },
                "geometry": subplot.get("geometry"),
            }
            features.append(feature)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "plot_id": plot_data.get("plot_id"),
            "enumerator": plot_data.get("enumerator"),
            "validation_status": plot_data.get("validation_status"),
        },
        "features": features,
    }


def create_bulk_download(
    plot_list: List[Dict], format_type: str = "hierarchical"
) -> bytes:
    """
    Create ZIP file with multiple plots
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for plot in plot_list:
            if format_type == "hierarchical":
                plot_json = create_hierarchical_json(plot)
            elif format_type == "flat":
                plot_json = create_flat_json(plot)
            elif format_type == "geojson":
                plot_json = create_geojson(plot)
            else:
                plot_json = create_hierarchical_json(plot)

            filename = f"{plot.get('plot_id', 'unknown')}_{plot.get('enumerator', 'unknown')}.json"
            zip_file.writestr(filename, json.dumps(plot_json, indent=2))

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def create_excel_export(df: pd.DataFrame, sheet_name: str = "Data") -> bytes:
    """
    Create Excel file from DataFrame
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    output.seek(0)
    return output.getvalue()


def create_csv_export(df: pd.DataFrame) -> str:
    """
    Create CSV from DataFrame
    """
    return df.to_csv(index=False)
