"""
Data loading utilities - UPDATED TO MATCH NOTEBOOK LOGIC
This will filter GPS accuracy and fix geometries like the notebook does
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
import shapely
from typing import Dict, Optional
import streamlit as st


def geom_from_scto_str(
    pd_row, column: str, accuracy_m: float = 10, accuracy_zero_valid: bool = False
) -> Polygon:
    """
    Create geometry from SurveyCTO coordinate string with accuracy filtering

    THIS IS THE KEY FUNCTION FROM THE NOTEBOOK
    It filters out GPS points with poor accuracy BEFORE creating geometry

    Args:
        pd_row: DataFrame row
        column: Column name with coordinate string
        accuracy_m: Maximum allowed accuracy in meters
        accuracy_zero_valid: Whether to accept accuracy=0.0

    Returns:
        Shapely Polygon
    """
    polygon_string = pd_row[column]

    # Check for invalid/missing data
    if pd.isna(polygon_string):
        return Polygon()

    if len(str(polygon_string)) == 32767:  # Excel cell limit
        return Polygon()

    # Parse coordinate string
    # Format: "lat lon altitude accuracy;lat lon altitude accuracy;..."
    vertices = str(polygon_string).split(";")

    coordinates = []
    skip_coordinates_counter = 0

    for vertex in vertices:
        if not vertex.strip():
            skip_coordinates_counter += 1
            continue

        parts = vertex.strip().split(" ")
        if len(parts) < 4:
            continue

        try:
            accuracy = float(parts[3])

            # CRITICAL: Filter by accuracy (this is what makes the difference!)
            if accuracy_zero_valid:
                if accuracy > accuracy_m:
                    skip_coordinates_counter += 1
                    continue
            else:
                # Skip if accuracy too high OR exactly zero
                if accuracy >= accuracy_m or abs(accuracy - 0.0) < 1e-9:
                    skip_coordinates_counter += 1
                    continue

            lon = float(parts[0])
            lat = float(parts[1])
            coordinates.append((lat, lon))

        except (ValueError, IndexError):
            skip_coordinates_counter += 1
            continue

    # Need at least 3 points for a polygon
    if len(coordinates) < 3:
        return Polygon()

    # Check if we dropped too many points
    if len(coordinates) < (skip_coordinates_counter * 4):
        return Polygon()

    return Polygon(coordinates)


def fix_geometry(geom: Polygon) -> Polygon:
    """
    Apply geometry fixes from the notebook

    This processes geometry to fix common issues before validation
    """
    if geom is None or geom.is_empty:
        return Polygon()

    # Fix 1: Self-intersecting squares (convex hull)
    if not geom.is_valid:
        coords = geom.exterior.coords.xy
        if len(coords[0]) == 5:
            geom = geom.convex_hull

    # Fix 2: Orient (fix winding order)
    if not geom.is_valid:
        from shapely.geometry.polygon import orient

        new_geom = orient(geom)
        if new_geom.is_valid:
            geom = new_geom

    # Fix 3: Zero buffer
    if not geom.is_valid:
        new_geom = geom.buffer(0)
        if geom.area > 0:
            ratio = new_geom.area / geom.area
            if 0.995 <= ratio < 1.005:  # Area didn't change much
                geom = new_geom

    # Fix 4: Convert to 2D (remove Z coordinates)
    geom = shapely.wkb.loads(shapely.wkb.dumps(geom, output_dimension=2))

    # Fix 5: Replace multipolygons with largest polygon
    if geom.geom_type == "MultiPolygon":
        if len(geom.geoms) == 1:
            geom = geom.geoms[0]
        else:
            # Keep largest polygon
            geom = max(geom.geoms, key=lambda x: x.area)

    # Fix 6: Simplify geometry (remove excess vertices)
    if not geom.is_empty and geom.is_valid:
        from shapely.ops import transform

        try:
            # Simple simplification
            simplified = geom.simplify(0.0001, preserve_topology=True)
            if simplified.is_valid:
                geom = simplified
        except:
            pass

    # Fix 7: Check bounds
    if not geom.is_empty:
        minx, miny, maxx, maxy = geom.bounds
        if minx <= -180 or 180 <= maxx or miny <= -80 or 84 <= maxy:
            return Polygon()

    # Fix 8: Replace invalid with empty
    if not geom.is_valid or geom.area == 0:
        return Polygon()

    return geom


def load_excel_data(uploaded_file) -> Optional[Dict[str, pd.DataFrame]]:
    """
    Load Excel file with multiple sheets

    Returns dictionary with DataFrames for each sheet
    """
    try:
        # Read all sheets
        plots_df = pd.read_excel(uploaded_file, sheet_name=0)
        subplots_df = pd.read_excel(uploaded_file, sheet_name=1)

        try:
            vegetation_df = pd.read_excel(uploaded_file, sheet_name=2)
        except:
            vegetation_df = pd.DataFrame()

        try:
            measurements_df = pd.read_excel(uploaded_file, sheet_name=3)
        except:
            measurements_df = pd.DataFrame()

        try:
            circumferences_df = pd.read_excel(uploaded_file, sheet_name=4)
        except:
            circumferences_df = pd.DataFrame()

        return {
            "plots": plots_df,
            "subplots": subplots_df,
            "vegetation": vegetation_df,
            "measurements": measurements_df,
            "circumferences": circumferences_df,
        }

    except Exception as e:
        st.error(f"Error loading Excel file: {str(e)}")
        return None


def merge_data(raw_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Merge sheets into combined DataFrames
    """
    # Rename keys for consistency
    plots_df = raw_data["plots"].rename(columns={"KEY": "PLOT_KEY"})
    subplots_df = raw_data["subplots"].rename(
        columns={"PARENT_KEY": "PLOT_KEY", "KEY": "SUBPLOT_KEY"}
    )

    # Merge plots and subplots
    plots_subplots = pd.merge(plots_df, subplots_df, how="inner", on="PLOT_KEY")

    # Merge with vegetation if available
    if not raw_data["vegetation"].empty:
        vegetation_df = raw_data["vegetation"].rename(
            columns={"PARENT_KEY": "SUBPLOT_KEY", "KEY": "VEGETATION_KEY"}
        )
        plots_vegetation = pd.merge(
            plots_subplots, vegetation_df, how="left", on="SUBPLOT_KEY"
        )
    else:
        plots_vegetation = plots_subplots.copy()

    # Merge with measurements if available
    if not raw_data["measurements"].empty:
        measurements_df = raw_data["measurements"].rename(
            columns={"PARENT_KEY": "VEGETATION_KEY", "KEY": "MEASUREMENT_KEY"}
        )
        plots_measurements = pd.merge(
            plots_vegetation, measurements_df, how="left", on="VEGETATION_KEY"
        )
    else:
        plots_measurements = plots_vegetation.copy()

    return {
        "plots_subplots": plots_subplots,
        "plots_vegetation": plots_vegetation,
        "plots_measurements": plots_measurements,
    }


def add_geometry_to_subplots(
    df: pd.DataFrame, accuracy_m: float = 10, apply_fixes: bool = True
) -> gpd.GeoDataFrame:
    """
    Add geometry column to subplots DataFrame

    UPDATED TO MATCH NOTEBOOK:
    - Filters GPS accuracy (accuracy_m=10)
    - Applies geometry fixes BEFORE validation

    Args:
        df: DataFrame with gt_subplot column
        accuracy_m: Maximum GPS accuracy in meters (default: 10)
        apply_fixes: Whether to apply geometry fixes (default: True)

    Returns:
        GeoDataFrame with geometry column
    """
    # Create geometry with accuracy filtering (LIKE NOTEBOOK)
    df["geometry"] = df.apply(
        lambda row: geom_from_scto_str(
            row,
            column="gt_subplot",
            accuracy_m=accuracy_m,  # THIS IS THE KEY!
            accuracy_zero_valid=False,
        ),
        axis=1,
    )

    # Apply geometry fixes (LIKE NOTEBOOK)
    if apply_fixes:
        df["geometry"] = df["geometry"].apply(fix_geometry)

    # Convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")

    return gdf


def filter_by_date(df: pd.DataFrame, start_date, end_date) -> pd.DataFrame:
    """Filter DataFrame by date range"""
    if "SubmissionDate" not in df.columns:
        return df

    df["SubmissionDate"] = pd.to_datetime(df["SubmissionDate"]).dt.date

    return df[(df["SubmissionDate"] >= start_date) & (df["SubmissionDate"] <= end_date)]


def get_unique_enumerators(df: pd.DataFrame) -> list:
    """Get list of unique enumerators"""
    if "enumerator" in df.columns:
        return sorted(df["enumerator"].dropna().unique().tolist())
    return []
