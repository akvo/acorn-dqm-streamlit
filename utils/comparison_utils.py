"""
Comparison utilities for GT vs DQ comparison.
Provides IoU-based plot matching and tree/vegetation comparison functions.
"""

import re
import pandas as pd
import geopandas as gpd
from typing import Dict, List, Any


def raw_centroid_from_gps_string(gps_string):
    """
    Compute mean lat/lon from a raw SurveyCTO GPS string, ignoring accuracy thresholds.
    Format: 'lat lon alt acc;lat lon alt acc;...'
    Returns a shapely Point(lon, lat) or None if no valid coordinates found.
    """
    from shapely.geometry import Point

    if pd.isna(gps_string) or not str(gps_string).strip():
        return None
    lats, lons = [], []
    for vertex in str(gps_string).split(";"):
        parts = vertex.strip().split()
        if len(parts) >= 2:
            try:
                lats.append(float(parts[0]))
                lons.append(float(parts[1]))
            except ValueError:
                continue
    if not lats:
        return None
    return Point(sum(lons) / len(lons), sum(lats) / len(lats))


def calculate_centroid_distance_meters(geom1, geom2) -> float:
    """
    Calculate distance in meters between centroids of two geometries.
    Uses Haversine formula for lat/lon coordinates.

    Args:
        geom1: First geometry (Shapely geometry in EPSG:4326)
        geom2: Second geometry (Shapely geometry in EPSG:4326)

    Returns:
        float: Distance in meters, or float('inf') if invalid
    """
    import math

    try:
        if geom1 is None or geom2 is None:
            return float("inf")
        if geom1.is_empty or geom2.is_empty:
            return float("inf")

        c1 = geom1.centroid
        c2 = geom2.centroid

        # Haversine formula
        lat1, lon1 = math.radians(c1.y), math.radians(c1.x)
        lat2, lon2 = math.radians(c2.y), math.radians(c2.x)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        # Earth's radius in meters
        r = 6371000

        return c * r
    except Exception:
        return float("inf")


def match_plots_by_centroid(
    gt_gdf: gpd.GeoDataFrame, dq_gdf: gpd.GeoDataFrame, distance_threshold: float = 50.0
) -> pd.DataFrame:
    """
    Match GT plots to DQ plots by centroid distance.
    For each DQ plot, find GT plot with closest centroid.
    Match if distance < threshold.

    Args:
        gt_gdf: GeoDataFrame with GT plots (needs PLOT_KEY/plot_id and geometry)
        dq_gdf: GeoDataFrame with DQ plots (needs PLOT_KEY/plot_id and geometry)
        distance_threshold: Maximum distance in meters to consider a match (default 50m)

    Returns:
        DataFrame with columns [gt_plot_key, dq_plot_key, distance_m]
    """
    matches = []

    # Determine plot key column name
    gt_key_col = "PLOT_KEY" if "PLOT_KEY" in gt_gdf.columns else "plot_id" if "plot_id" in gt_gdf.columns else None
    dq_key_col = "PLOT_KEY" if "PLOT_KEY" in dq_gdf.columns else "plot_id" if "plot_id" in dq_gdf.columns else None

    if gt_key_col is None or dq_key_col is None:
        return pd.DataFrame(matches)

    # Filter out empty geometries
    gt_valid = gt_gdf[~gt_gdf.geometry.is_empty & gt_gdf.geometry.notna()].copy()
    dq_valid = dq_gdf[~dq_gdf.geometry.is_empty & dq_gdf.geometry.notna()].copy()

    # For each DQ plot, find closest GT plot
    for _, dq_row in dq_valid.iterrows():
        dq_key = dq_row[dq_key_col]
        dq_geom = dq_row["geometry"]

        if dq_geom is None or dq_geom.is_empty:
            continue

        best_match = None
        best_distance = float("inf")

        for _, gt_row in gt_valid.iterrows():
            gt_key = gt_row[gt_key_col]
            gt_geom = gt_row["geometry"]

            if gt_geom is None or gt_geom.is_empty:
                continue

            distance = calculate_centroid_distance_meters(gt_geom, dq_geom)

            if distance < best_distance:
                best_distance = distance
                best_match = gt_key

        if best_distance <= distance_threshold and best_match is not None:
            matches.append({"gt_plot_key": best_match, "dq_plot_key": dq_key, "distance_m": round(best_distance, 1)})

    return pd.DataFrame(matches)


# Keep old function for backwards compatibility
def match_plots_by_iou(gt_gdf: gpd.GeoDataFrame, dq_gdf: gpd.GeoDataFrame, iou_threshold: float = None) -> pd.DataFrame:
    """Deprecated: Use match_plots_by_centroid instead."""
    return match_plots_by_centroid(gt_gdf, dq_gdf, distance_threshold=50.0)


def match_subplots_within_plot(
    gt_subplots_gdf: gpd.GeoDataFrame,
    dq_subplots_gdf: gpd.GeoDataFrame,
    strict_threshold: float = 20.0,
) -> pd.DataFrame:
    """
    Match DQ subplots to GT subplots using two-pass algorithm.

    Pass 1: Match within strict_threshold (20m) - takes smallest distance match
    Pass 2: Match remaining DQ to nearest unmatched GT subplot (no distance limit)

    Args:
        gt_subplots_gdf: GeoDataFrame of GT subplots for one plot (filtered to measured)
        dq_subplots_gdf: GeoDataFrame of DQ subplots for one plot (filtered to measured)
        strict_threshold: Distance threshold for strict matching (default 20m)

    Returns:
        DataFrame with columns: [gt_subplot_id, dq_subplot_id, distance_m,
                                 gt_subplot_num, dq_subplot_num, match_type]
    """

    def extract_subplot_num(subplot_id):
        match = re.search(r"\[(\d+)\]", str(subplot_id))
        return int(match.group(1)) if match else 0

    matches = []
    matched_gt_ids = set()
    matched_dq_ids = set()

    # Validate inputs
    if gt_subplots_gdf is None or len(gt_subplots_gdf) == 0:
        return pd.DataFrame(matches)
    if dq_subplots_gdf is None or len(dq_subplots_gdf) == 0:
        return pd.DataFrame(matches)
    if "subplot_id" not in gt_subplots_gdf.columns or "subplot_id" not in dq_subplots_gdf.columns:
        return pd.DataFrame(matches)

    # Pass 1: Strict matching within threshold (takes smallest distance)
    for _, dq_row in dq_subplots_gdf.iterrows():
        if dq_row.geometry is None or dq_row.geometry.is_empty:
            continue

        best_match = None
        best_distance = float("inf")

        for _, gt_row in gt_subplots_gdf.iterrows():
            if gt_row["subplot_id"] in matched_gt_ids:
                continue
            if gt_row.geometry is None or gt_row.geometry.is_empty:
                continue

            dist = calculate_centroid_distance_meters(gt_row.geometry, dq_row.geometry)
            # Take the smallest distance within threshold
            if dist < best_distance and dist <= strict_threshold:
                best_distance = dist
                best_match = gt_row

        if best_match is not None:
            matches.append(
                {
                    "gt_subplot_id": best_match["subplot_id"],
                    "dq_subplot_id": dq_row["subplot_id"],
                    "distance_m": round(best_distance, 1),
                    "gt_subplot_num": extract_subplot_num(best_match["subplot_id"]),
                    "dq_subplot_num": extract_subplot_num(dq_row["subplot_id"]),
                    "match_type": "strict",
                }
            )
            matched_gt_ids.add(best_match["subplot_id"])
            matched_dq_ids.add(dq_row["subplot_id"])

    # Pass 2: Fallback - match remaining DQ to nearest unmatched GT (no distance limit)
    for _, dq_row in dq_subplots_gdf.iterrows():
        if dq_row["subplot_id"] in matched_dq_ids:
            continue
        if dq_row.geometry is None or dq_row.geometry.is_empty:
            continue

        best_match = None
        best_distance = float("inf")

        for _, gt_row in gt_subplots_gdf.iterrows():
            if gt_row["subplot_id"] in matched_gt_ids:
                continue
            if gt_row.geometry is None or gt_row.geometry.is_empty:
                continue

            dist = calculate_centroid_distance_meters(gt_row.geometry, dq_row.geometry)
            if dist < best_distance:
                best_distance = dist
                best_match = gt_row

        if best_match is not None:
            matches.append(
                {
                    "gt_subplot_id": best_match["subplot_id"],
                    "dq_subplot_id": dq_row["subplot_id"],
                    "distance_m": round(best_distance, 1),
                    "gt_subplot_num": extract_subplot_num(best_match["subplot_id"]),
                    "dq_subplot_num": extract_subplot_num(dq_row["subplot_id"]),
                    "match_type": "fallback",
                }
            )
            matched_gt_ids.add(best_match["subplot_id"])
            matched_dq_ids.add(dq_row["subplot_id"])

    return pd.DataFrame(matches)


def filter_measured_subplots(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Filter GeoDataFrame to only include measured subplots.
    Applies same logic as GT: subplot_number <= measured_subplots.

    Args:
        gdf: GeoDataFrame with subplot_id and measured_subplots columns

    Returns:
        Filtered GeoDataFrame with only measured subplots
    """
    if gdf is None or len(gdf) == 0:
        return gdf

    if "subplot_id" not in gdf.columns or "measured_subplots" not in gdf.columns:
        return gdf

    temp_df = gdf[["subplot_id", "measured_subplots"]].copy()

    # Extract subplot number from subplot_id (e.g., "[1]", "[2]")
    temp_df["subplot_number"] = temp_df["subplot_id"].apply(
        lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
    )

    # Convert measured_subplots to int
    temp_df["measured_subplots_int"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)

    # Keep only subplots where subplot_number <= measured_subplots
    measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots_int"]]["subplot_id"].unique()

    return gdf[gdf["subplot_id"].isin(measured_subplot_ids)].copy()


def get_subplot_count(plot_key: str, gdf: gpd.GeoDataFrame) -> int:
    """
    Get count of subplots for a plot.

    Args:
        plot_key: The PLOT_KEY to count subplots for
        gdf: GeoDataFrame with subplots

    Returns:
        int: Number of subplots
    """
    if gdf is None or "PLOT_KEY" not in gdf.columns:
        return 0

    return len(gdf[gdf["PLOT_KEY"] == plot_key])


def get_tree_count_by_name(
    plot_key: str,
    raw_data: Dict,
    gdf: gpd.GeoDataFrame = None,
    height_filter: str = "all",
    exclude_species: List[str] = None,
) -> Dict[str, int]:
    """
    Get tree counts grouped by tree_name for a plot (woody trees only).
    Uses normalized vegetation data from plots_subplots_vegetation.

    Args:
        plot_key: The PLOT_KEY to get trees for
        raw_data: Raw data dictionary containing vegetation data
        gdf: Optional GeoDataFrame with subplot info for filtering
        height_filter: "all" | "above_1.3" | "below_1.3"
        exclude_species: Optional list of species names to exclude from counts

    Returns:
        dict {tree_name: count}
    """
    tree_counts = {}
    exclude_set = set(exclude_species) if exclude_species else set()

    # Get vegetation data from raw_data (normalized format)
    veg_df = raw_data.get("plots_subplots_vegetation")
    if veg_df is None or len(veg_df) == 0:
        return tree_counts

    veg_df = veg_df.copy()

    # Filter for woody trees only (non_woody_species must be NULL)
    if "non_woody_species" in veg_df.columns:
        veg_df = veg_df[veg_df["non_woody_species"].isna()]

    if len(veg_df) == 0:
        return tree_counts

    # Filter to this plot's subplots
    # SUBPLOT_KEY format: uuid:xxx/sub_plot[1]
    plot_veg = veg_df[veg_df["SUBPLOT_KEY"].str.startswith(plot_key + "/", na=False)].copy()

    if len(plot_veg) == 0:
        return tree_counts

    # Filter for tree records (vegetation_type_number > 0)
    if "vegetation_type_number" not in plot_veg.columns:
        return tree_counts

    # Convert vegetation_type_number to numeric (may be string)
    plot_veg["vegetation_type_number"] = pd.to_numeric(plot_veg["vegetation_type_number"], errors="coerce")

    tree_records = plot_veg[(plot_veg["vegetation_type_number"].notna()) & (plot_veg["vegetation_type_number"] > 0)]

    # Height filter using the categorical flag set by enumerators
    if height_filter != "all" and "vegetation_type_height" in tree_records.columns:
        if height_filter == "above_1.3":
            tree_records = tree_records[tree_records["vegetation_type_height"] == "yes_above_1.3"]
        elif height_filter == "below_1.3":
            tree_records = tree_records[tree_records["vegetation_type_height"] == "no_below_1.3m"]

    # Species columns to check (in priority order)
    species_cols = [
        "woody_species",
        "bamboo_species",
        "banana_species",
        "palm_species",
        "living_fences",
    ]

    # Group by tree_name and sum vegetation_type_number
    for _, row in tree_records.iterrows():
        # Find species name from first non-empty species column
        tree_name = "Unknown"
        for col in species_cols:
            if col in row.index:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    tree_name = str(val).strip()
                    break

        if tree_name in exclude_set:
            continue

        count = int(row.get("vegetation_type_number", 0))
        tree_counts[tree_name] = tree_counts.get(tree_name, 0) + count

    return tree_counts


def get_all_tree_species(raw_data: Dict) -> List[str]:
    """
    Return the sorted list of unique woody tree species names present in the data.
    Mirrors the species-resolution logic used by get_tree_count_by_name so the
    exclusion dropdown offers exactly the names that drive the counts.

    Args:
        raw_data: Raw data dictionary containing vegetation data

    Returns:
        Sorted list of unique species names (may include "Unknown")
    """
    veg_df = raw_data.get("plots_subplots_vegetation")
    if veg_df is None or len(veg_df) == 0:
        return []

    veg_df = veg_df.copy()

    # Woody trees only (non_woody_species must be NULL)
    if "non_woody_species" in veg_df.columns:
        veg_df = veg_df[veg_df["non_woody_species"].isna()]

    if len(veg_df) == 0 or "vegetation_type_number" not in veg_df.columns:
        return []

    veg_df["vegetation_type_number"] = pd.to_numeric(veg_df["vegetation_type_number"], errors="coerce")
    veg_df = veg_df[(veg_df["vegetation_type_number"].notna()) & (veg_df["vegetation_type_number"] > 0)]

    species_cols = [
        "woody_species",
        "bamboo_species",
        "banana_species",
        "palm_species",
        "living_fences",
    ]

    names = set()
    for _, row in veg_df.iterrows():
        tree_name = "Unknown"
        for col in species_cols:
            if col in row.index:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    tree_name = str(val).strip()
                    break
        names.add(tree_name)

    return sorted(names)


def get_tree_records_by_species(
    plot_key: str,
    species_name: str,
    raw_data: Dict,
    height_filter: str = "all",
    exclude_species: List[str] = None,
) -> pd.DataFrame:
    """
    Get individual vegetation records for a specific species in a plot.

    Args:
        plot_key: The PLOT_KEY to get records for
        species_name: The species name to filter by
        raw_data: Raw data dictionary containing vegetation data
        height_filter: "all" | "above_1.3" | "below_1.3" - filters records by
            the categorical vegetation_type_height flag set by enumerators
        exclude_species: Optional list of species names to exclude; if
            species_name is in this list, an empty frame is returned

    Returns:
        DataFrame with columns: Subplot, Count, Height, Year Planted
    """
    if exclude_species and species_name in set(exclude_species):
        return pd.DataFrame()

    # Get vegetation data from raw_data (normalized format)
    veg_df = raw_data.get("plots_subplots_vegetation")
    if veg_df is None or len(veg_df) == 0:
        return pd.DataFrame()

    veg_df = veg_df.copy()

    # Filter for woody trees only (non_woody_species must be NULL)
    if "non_woody_species" in veg_df.columns:
        veg_df = veg_df[veg_df["non_woody_species"].isna()]

    if len(veg_df) == 0:
        return pd.DataFrame()

    # Filter to this plot's subplots
    plot_veg = veg_df[veg_df["SUBPLOT_KEY"].str.startswith(plot_key + "/", na=False)].copy()

    if len(plot_veg) == 0:
        return pd.DataFrame()

    # Convert vegetation_type_number to numeric
    if "vegetation_type_number" in plot_veg.columns:
        plot_veg["vegetation_type_number"] = pd.to_numeric(plot_veg["vegetation_type_number"], errors="coerce")

    # Filter for tree records (vegetation_type_number > 0)
    tree_records = plot_veg[
        (plot_veg["vegetation_type_number"].notna()) & (plot_veg["vegetation_type_number"] > 0)
    ].copy()

    # Species columns to check (in priority order)
    species_cols = [
        "woody_species",
        "bamboo_species",
        "banana_species",
        "palm_species",
        "living_fences",
    ]

    # Add tree_name column to identify species
    def get_species(row):
        for col in species_cols:
            if col in row.index:
                val = row.get(col)
                if pd.notna(val) and str(val).strip():
                    return str(val).strip()
        return "Unknown"

    tree_records["tree_name"] = tree_records.apply(get_species, axis=1)

    # Filter for the specific species
    species_records = tree_records[tree_records["tree_name"] == species_name]

    # Height filter using the categorical flag set by enumerators
    if height_filter != "all" and "vegetation_type_height" in species_records.columns:
        if height_filter == "above_1.3":
            species_records = species_records[species_records["vegetation_type_height"] == "yes_above_1.3"]
        elif height_filter == "below_1.3":
            species_records = species_records[species_records["vegetation_type_height"] == "no_below_1.3m"]

    if len(species_records) == 0:
        return pd.DataFrame()

    # Extract subplot number from SUBPLOT_KEY (e.g., uuid:xxx/sub_plot[1] -> 1)
    def extract_subplot(subplot_key):
        import re

        match = re.search(r"sub_plot\[(\d+)\]", str(subplot_key))
        return int(match.group(1)) if match else 0

    # Build result DataFrame
    result_rows = []
    for _, row in species_records.iterrows():
        subplot_num = extract_subplot(row.get("SUBPLOT_KEY", ""))

        # Format year planted - remove time portion
        year_planted = row.get("tree_year_planted", "N/A")
        if pd.notna(year_planted) and year_planted != "N/A":
            try:
                year_planted = pd.to_datetime(year_planted).strftime("%Y-%m-%d")
            except:
                pass

        # Build row data
        row_data = {
            "Subplot": subplot_num,
            "Count": int(row.get("vegetation_type_number", 0)),
            "Height": row.get("vegetation_type_height", "N/A"),
            "Year Planted": year_planted,
        }

        # For "other" species, show actual species name
        if species_name == "other":
            other_sp = row.get("other_species", "")
            lang_other = row.get("language_other_species", "")
            if other_sp or lang_other:
                other_name = f"{other_sp} ({lang_other})" if lang_other else str(other_sp)
                row_data["Other Species"] = other_name

        result_rows.append(row_data)

    return pd.DataFrame(result_rows)


def get_total_tree_count(
    plot_key: str,
    raw_data: Dict,
    gdf: gpd.GeoDataFrame = None,
    height_filter: str = "all",
    exclude_species: List[str] = None,
) -> int:
    """
    Get total tree count for a plot.

    Args:
        plot_key: The PLOT_KEY to count trees for
        raw_data: Raw data dictionary containing vegetation data
        gdf: Optional GeoDataFrame with subplot info for filtering
        height_filter: "all" | "above_1.3" | "below_1.3"
        exclude_species: Optional list of species names to exclude from the total

    Returns:
        int: Total number of trees
    """
    tree_counts = get_tree_count_by_name(
        plot_key, raw_data, gdf, height_filter=height_filter, exclude_species=exclude_species
    )
    return sum(tree_counts.values())


def get_vegetation_coverage(plot_key: str, raw_data: Dict, gdf: gpd.GeoDataFrame = None) -> List[Dict]:
    """
    Get vegetation coverage for plots with no trees.
    Filters for: vegetation_type_woody == 'nonwoody_coverage' OR
                 vegetation_type_youngtree == 'no_coverage'

    Args:
        plot_key: The PLOT_KEY to get coverage for
        raw_data: Raw data dictionary containing vegetation data
        gdf: Optional GeoDataFrame with subplot info for filtering

    Returns:
        list of dicts with subplot_key, coverage_vegetation
    """
    coverage_list = []

    # Get vegetation data from raw_data (normalized format)
    veg_df = raw_data.get("plots_subplots_vegetation")
    if veg_df is None or len(veg_df) == 0:
        return coverage_list

    # Filter to this plot's subplots
    # SUBPLOT_KEY format: uuid:xxx/sub_plot[1]
    veg_df = veg_df[veg_df["SUBPLOT_KEY"].str.startswith(plot_key + "/", na=False)]

    if len(veg_df) == 0:
        return coverage_list

    # Filter for coverage-only records
    coverage_filter = pd.Series([False] * len(veg_df), index=veg_df.index)

    if "vegetation_type_woody" in veg_df.columns:
        coverage_filter |= veg_df["vegetation_type_woody"] == "nonwoody_coverage"

    if "vegetation_type_youngtree" in veg_df.columns:
        coverage_filter |= veg_df["vegetation_type_youngtree"] == "no_coverage"

    coverage_records = veg_df[coverage_filter]

    for _, row in coverage_records.iterrows():
        coverage_list.append(
            {"subplot_key": row.get("SUBPLOT_KEY", ""), "coverage_vegetation": row.get("coverage_vegetation", None)}
        )

    return coverage_list


def compare_tree_counts(gt_tree_dict: Dict[str, int], dq_tree_dict: Dict[str, int]) -> pd.DataFrame:
    """
    Compare two tree count dictionaries.

    Args:
        gt_tree_dict: GT tree counts {tree_name: count}
        dq_tree_dict: DQ tree counts {tree_name: count}

    Returns:
        DataFrame with columns [tree_name, gt_count, dq_count, difference]
    """
    all_names = set(gt_tree_dict.keys()) | set(dq_tree_dict.keys())

    comparison = []
    for name in sorted(all_names):
        gt_count = gt_tree_dict.get(name, 0)
        dq_count = dq_tree_dict.get(name, 0)
        comparison.append(
            {"tree_name": name, "gt_count": gt_count, "dq_count": dq_count, "difference": dq_count - gt_count}
        )

    return pd.DataFrame(comparison)


def get_plot_details(plot_key: str, gdf: gpd.GeoDataFrame, raw_data: Dict) -> Dict[str, Any]:
    """
    Get all details for a plot for the expandable section.

    Args:
        plot_key: The PLOT_KEY to get details for
        gdf: GeoDataFrame with subplot data
        raw_data: Raw data dictionary

    Returns:
        dict with plot_info, subplot_summary, trees_by_type, coverage
    """
    details = {"plot_info": {}, "subplot_summary": {}, "trees_by_type": {}, "coverage": []}

    if gdf is None or len(gdf) == 0:
        return details

    # Get plot subplots
    plot_subplots = gdf[gdf["PLOT_KEY"] == plot_key]

    if len(plot_subplots) == 0:
        return details

    # Plot info from first row
    first_row = plot_subplots.iloc[0]
    details["plot_info"] = {
        "plot_key": plot_key,
        "enumerator": first_row.get("enumerator", ""),
        "date": first_row.get("date", ""),
        "geom_valid": first_row.get("geom_valid", None),
    }

    # Subplot summary
    total_subplots = len(plot_subplots)
    valid_subplots = plot_subplots["geom_valid"].sum() if "geom_valid" in plot_subplots.columns else 0
    details["subplot_summary"] = {
        "total": total_subplots,
        "valid": int(valid_subplots),
        "invalid": total_subplots - int(valid_subplots),
    }

    # Trees by type
    trees = get_tree_count_by_name(plot_key, raw_data, gdf)
    details["trees_by_type"] = trees

    # Coverage (if no trees)
    if sum(trees.values()) == 0:
        details["coverage"] = get_vegetation_coverage(plot_key, raw_data, gdf)

    return details


def calculate_plot_validation_summary(gdf: gpd.GeoDataFrame) -> Dict[str, int]:
    """
    Calculate plot validation summary from subplot data.

    Args:
        gdf: GeoDataFrame with subplot data (needs PLOT_KEY, geom_valid, overall_valid)

    Returns:
        dict with total_plots, valid_plots, invalid_plots
    """
    if gdf is None or len(gdf) == 0 or "PLOT_KEY" not in gdf.columns:
        return {"total_plots": 0, "valid_plots": 0, "invalid_plots": 0}

    # Use overall_valid if available, otherwise geom_valid
    valid_col = "overall_valid" if "overall_valid" in gdf.columns else "geom_valid"

    if valid_col not in gdf.columns:
        return {"total_plots": len(gdf["PLOT_KEY"].unique()), "valid_plots": 0, "invalid_plots": 0}

    # Group by plot and check validity (plot is invalid if >= 8 subplots are invalid)
    plot_summary = (
        gdf.groupby("PLOT_KEY")
        .agg(
            total_subplots=("SUBPLOT_KEY", "count") if "SUBPLOT_KEY" in gdf.columns else (valid_col, "count"),
            invalid_subplots=(valid_col, lambda x: (~x).sum()),
        )
        .reset_index()
    )

    # Plot is invalid if >= 8 subplots are invalid
    plot_summary["is_valid"] = plot_summary["invalid_subplots"] < 8

    total_plots = len(plot_summary)
    valid_plots = plot_summary["is_valid"].sum()
    invalid_plots = total_plots - valid_plots

    return {"total_plots": total_plots, "valid_plots": int(valid_plots), "invalid_plots": int(invalid_plots)}
