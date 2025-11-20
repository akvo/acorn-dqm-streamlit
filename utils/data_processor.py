"""
Enhanced Data Processing Utilities
Handles complete vegetation data from 5 Excel sheets
"""

import pandas as pd
import geopandas as gpd
from datetime import date
from core import (
    GeometryFixer,
    GeometryValidator,
    geom_from_scto_str,
    assign_geom_valid_geojson,
)
import config
import sys


def read_excel_all_sheets(uploaded_file):
    """
    Read all 5 sheets from Ground Truth Collection Excel file

    Returns:
        dict: Dictionary with all dataframes
    """
    try:
        # Sheet 0: Plots
        plots_df = pd.read_excel(uploaded_file, sheet_name=0).rename(
            columns={"KEY": "PLOT_KEY"}
        )

        # Sheet 1: Subplots
        subplot_df = pd.read_excel(uploaded_file, sheet_name=1).rename(
            columns={"PARENT_KEY": "PLOT_KEY", "KEY": "SUBPLOT_KEY"}
        )

        # Try to read additional sheets (may not exist for all files)
        try:
            # Sheet 2: Vegetation
            vegetation_df = pd.read_excel(uploaded_file, sheet_name=2).rename(
                columns={"PARENT_KEY": "SUBPLOT_KEY", "KEY": "VEGETATION_KEY"}
            )
        except:
            vegetation_df = None

        try:
            # Sheet 3: Measurements
            measurement_df = pd.read_excel(uploaded_file, sheet_name=3).rename(
                columns={"PARENT_KEY": "VEGETATION_KEY", "KEY": "MEASUREMENT_KEY"}
            )
        except:
            measurement_df = None

        try:
            # Sheet 4: Circumference
            circumference_df = pd.read_excel(uploaded_file, sheet_name=4).rename(
                columns={"PARENT_KEY": "MEASUREMENT_KEY", "KEY": "CIRCUMFERENCE_KEY"}
            )
        except:
            circumference_df = None

        return {
            "plots": plots_df,
            "subplots": subplot_df,
            "vegetation": vegetation_df,
            "measurements": measurement_df,
            "circumference": circumference_df,
        }

    except Exception as e:
        raise Exception(f"Error reading Excel file: {str(e)}")


def merge_all_data(sheets_dict):
    """
    Merge all sheets together (plots -> subplots -> vegetation -> measurements -> circumference)

    Returns:
        dict: Dictionary with merged dataframes at different levels
    """
    plots_df = sheets_dict["plots"]
    subplot_df = sheets_dict["subplots"]
    vegetation_df = sheets_dict["vegetation"]
    measurement_df = sheets_dict["measurements"]
    circumference_df = sheets_dict["circumference"]

    # Merge plots with subplots
    m_plots = pd.merge(plots_df, subplot_df, how="inner", on="PLOT_KEY", suffixes=("_plot", "_subplot"))

    # Handle duplicate columns
    # Enumerator
    if "enumerator_subplot" in m_plots.columns and "enumerator_plot" in m_plots.columns:
        m_plots["enumerator"] = m_plots["enumerator_subplot"].fillna(m_plots["enumerator_plot"])
        m_plots = m_plots.drop(columns=["enumerator_plot", "enumerator_subplot"])
    elif "enumerator_plot" in m_plots.columns:
        m_plots["enumerator"] = m_plots["enumerator_plot"]
        m_plots = m_plots.drop(columns=["enumerator_plot"])
    elif "enumerator_subplot" in m_plots.columns:
        m_plots["enumerator"] = m_plots["enumerator_subplot"]
        m_plots = m_plots.drop(columns=["enumerator_subplot"])

    # KEY and PARENT_KEY - keep subplot version
    if "KEY_subplot" in m_plots.columns:
        m_plots["KEY"] = m_plots["KEY_subplot"]
        m_plots = m_plots.drop(columns=["KEY_subplot"], errors="ignore")
    if "KEY_plot" in m_plots.columns:
        m_plots = m_plots.drop(columns=["KEY_plot"], errors="ignore")
    if "PARENT_KEY_subplot" in m_plots.columns:
        m_plots["PARENT_KEY"] = m_plots["PARENT_KEY_subplot"]
        m_plots = m_plots.drop(columns=["PARENT_KEY_subplot"], errors="ignore")
    if "PARENT_KEY_plot" in m_plots.columns:
        m_plots = m_plots.drop(columns=["PARENT_KEY_plot"], errors="ignore")

    # Convert submission date if exists
    if "SubmissionDate" in m_plots.columns:
        m_plots["SubmissionDate"] = pd.to_datetime(
            m_plots["SubmissionDate"], format="mixed", errors="coerce"
        ).dt.date

    merged = {"plots_subplots": m_plots}

    # Merge with vegetation if available
    if vegetation_df is not None:
        # INNER JOIN - only subplots WITH vegetation (matches notebook)
        # This ensures m_veg only contains subplots that have vegetation records
        m_veg = pd.merge(m_plots, vegetation_df, how="inner", on="SUBPLOT_KEY", suffixes=("", "_veg"))

        # Clean up duplicate KEY/PARENT_KEY columns - keep vegetation version
        if "KEY_veg" in m_veg.columns:
            m_veg["KEY"] = m_veg["KEY_veg"]
            m_veg = m_veg.drop(columns=["KEY_veg"], errors="ignore")
        if "PARENT_KEY_veg" in m_veg.columns:
            m_veg["PARENT_KEY"] = m_veg["PARENT_KEY_veg"]
            m_veg = m_veg.drop(columns=["PARENT_KEY_veg"], errors="ignore")

        merged["plots_subplots_vegetation"] = m_veg

        # Merge with measurements if available
        if measurement_df is not None:
            m_mea = pd.merge(m_veg, measurement_df, how="left", on="VEGETATION_KEY", suffixes=("", "_mea"))

            # Clean up duplicate KEY/PARENT_KEY columns - keep measurement version
            if "KEY_mea" in m_mea.columns:
                m_mea["KEY"] = m_mea["KEY_mea"]
                m_mea = m_mea.drop(columns=["KEY_mea"], errors="ignore")
            if "PARENT_KEY_mea" in m_mea.columns:
                m_mea["PARENT_KEY"] = m_mea["PARENT_KEY_mea"]
                m_mea = m_mea.drop(columns=["PARENT_KEY_mea"], errors="ignore")

            merged["plots_subplots_vegetation_measurements"] = m_mea

            # Merge with circumference if available
            if circumference_df is not None:
                m_cir = pd.merge(
                    m_mea, circumference_df, how="left", on="MEASUREMENT_KEY", suffixes=("", "_cir")
                )

                # Clean up duplicate KEY/PARENT_KEY columns - keep circumference version
                if "KEY_cir" in m_cir.columns:
                    m_cir["KEY"] = m_cir["KEY_cir"]
                    m_cir = m_cir.drop(columns=["KEY_cir"], errors="ignore")
                if "PARENT_KEY_cir" in m_cir.columns:
                    m_cir["PARENT_KEY"] = m_cir["PARENT_KEY_cir"]
                    m_cir = m_cir.drop(columns=["PARENT_KEY_cir"], errors="ignore")

                merged["complete"] = m_cir

    return merged


def process_excel_file(uploaded_file):
    """
    Complete processing pipeline:
    1. Read all sheets
    2. Merge data
    3. Create geometries
    4. Validate
    5. Add statistics

    Returns:
        dict with all processed data
    """
    # Read all sheets
    sheets = read_excel_all_sheets(uploaded_file)

    # Merge all data
    merged = merge_all_data(sheets)

    # Get plots-subplots merged data
    m_plots = merged["plots_subplots"]

    # Process subplots for geometry validation
    # Determine which time column to use
    time_col = None
    if "starttime" in m_plots.columns:
        time_col = "starttime"
    elif "SubmissionDate" in m_plots.columns:
        time_col = "SubmissionDate"

    # Build column list dynamically based on what exists
    cols_to_select = []
    if time_col:
        cols_to_select.append(time_col)
    if "enumerator" in m_plots.columns:
        cols_to_select.append("enumerator")

    # Always need these columns
    cols_to_select.extend(["gt_subplot", "SUBPLOT_KEY"])

    # Add measured_subplots if available (from plots data)
    if "measured_subplots" in m_plots.columns:
        cols_to_select.append("measured_subplots")

    # Add PLOT_KEY to group by plot for measured_subplots aggregation
    if "PLOT_KEY" in m_plots.columns:
        cols_to_select.append("PLOT_KEY")

    # Select only existing columns
    subplots_for_validation = m_plots[cols_to_select].copy()

    print(f"m_plots columns: {m_plots.columns.tolist()}", file=sys.stderr)
    print(f"cols_to_select: {cols_to_select}", file=sys.stderr)
    print(
        f"subplots_for_validation columns: {subplots_for_validation.columns.tolist()}",
        file=sys.stderr,
    )
    if "enumerator" in subplots_for_validation.columns:
        print(f"✓ enumerator in subplots_for_validation", file=sys.stderr)
    else:
        print(f"✗ enumerator NOT in subplots_for_validation", file=sys.stderr)

    subplots_for_validation = subplots_for_validation.rename(
        columns={"SUBPLOT_KEY": "subplot_id"}
    )

    # Create geometry
    subplots_for_validation["geometry"] = subplots_for_validation.apply(
        lambda row: geom_from_scto_str(
            row,
            column="gt_subplot",
            accuracy_m=config.GPS_ACCURACY_THRESHOLD,
            accuracy_zero_valid=False,
        ),
        axis=1,
    )

    gdf_subplots = gpd.GeoDataFrame(
        subplots_for_validation, geometry="geometry", crs=4326
    )

    # Fix geometries
    geometry_fixer = GeometryFixer()
    gdf_subplots_fixed = geometry_fixer.fix_geometry(gdf_subplots)

    # Validate
    geometry_validator = GeometryValidator(
        partner=config.PARTNER,
        country=config.COUNTRY,
        threshold_length_width=config.THRESHOLD_LENGTH_WIDTH,
        threshold_protruding_ratio=config.THRESHOLD_PROTRUDING_RATIO,
        validate_id="subplot_id",
        threshold_within_radius=config.THRESHOLD_WITHIN_RADIUS,
        min_area_size=config.MIN_SUBPLOT_AREA_SIZE,
        max_area_size=config.MAX_SUBPLOT_AREA_SIZE,
        max_vertices=config.MAX_VERTICES,
    )
    gdf_subplots_validated = geometry_validator.validate_geometry(gdf_subplots_fixed)

    # Collect reasons
    gdf_final = assign_geom_valid_geojson(
        gdf_subplots_validated,
        min_area=config.MIN_SUBPLOT_AREA_SIZE,
        max_area=config.MAX_SUBPLOT_AREA_SIZE,
    )

    # Ensure enumerator, time, and PLOT_KEY columns are preserved
    # (They might be lost during geometry operations)
    preserve_cols = []
    if "enumerator" in subplots_for_validation.columns:
        preserve_cols.append("enumerator")
    if time_col and time_col in subplots_for_validation.columns:
        preserve_cols.append(time_col)
    if "PLOT_KEY" in subplots_for_validation.columns:
        preserve_cols.append("PLOT_KEY")

    if preserve_cols:
        # Merge back the preserved columns using subplot_id
        preserve_data = subplots_for_validation[
            ["subplot_id"] + preserve_cols
        ].drop_duplicates()

        # Only merge if columns are missing in gdf_final
        cols_to_add = [col for col in preserve_cols if col not in gdf_final.columns]
        if cols_to_add:
            gdf_final = gdf_final.merge(
                preserve_data[["subplot_id"] + cols_to_add], on="subplot_id", how="left"
            )

    # Process plots
    plots_for_validation = sheets["plots"].copy()
    if "gt_plot" in plots_for_validation.columns:
        plots_for_validation["geometry"] = plots_for_validation.apply(
            lambda row: geom_from_scto_str(
                row,
                column="gt_plot",
                accuracy_m=config.GPS_ACCURACY_THRESHOLD,
                accuracy_zero_valid=False,
            ),
            axis=1,
        )
        gdf_plots = gpd.GeoDataFrame(
            plots_for_validation, geometry="geometry", crs=4326
        )
    else:
        gdf_plots = None

    # Add vegetation statistics to subplots if available
    if "plots_subplots_vegetation" in merged:
        try:
            veg_stats = calculate_vegetation_stats(merged["plots_subplots_vegetation"])
            gdf_final = gdf_final.merge(veg_stats, on="subplot_id", how="left")
        except Exception as e:
            print(f"Warning: Could not calculate vegetation stats: {str(e)}")

    # Add measurement statistics if available
    if "plots_subplots_vegetation_measurements" in merged:
        try:
            mea_stats = calculate_measurement_stats(
                merged["plots_subplots_vegetation_measurements"]
            )
            gdf_final = gdf_final.merge(mea_stats, on="subplot_id", how="left")
        except Exception as e:
            print(f"Warning: Could not calculate measurement stats: {str(e)}")

    return {
        "subplots": gdf_final,
        "plots": gdf_plots,
        "raw_data": merged,
        "sheets": sheets,
    }


def calculate_vegetation_stats(m_veg):
    """
    Calculate vegetation statistics per subplot
    """
    # Group by SUBPLOT_KEY (the key used in the merged data)
    stats = (
        m_veg.groupby("SUBPLOT_KEY")
        .agg(
            {
                "vegetation_type_number": ["sum", "count"],
                "coverage_vegetation": "mean",
            }
        )
        .reset_index()
    )

    stats.columns = ["SUBPLOT_KEY", "total_trees", "species_count", "avg_coverage"]

    # Count species types
    species_cols = [col for col in m_veg.columns if "species" in col.lower()]
    if species_cols:
        for col in species_cols:
            if col in m_veg.columns:
                try:
                    species_count = (
                        m_veg.groupby("SUBPLOT_KEY")[col]
                        .nunique()
                        .reset_index(name=f"{col}_count")
                    )
                    stats = stats.merge(species_count, on="SUBPLOT_KEY", how="left")
                except:
                    pass  # Skip if column has issues

    # Rename SUBPLOT_KEY to subplot_id at the end (to match the validated GeoDataFrame)
    stats = stats.rename(columns={"SUBPLOT_KEY": "subplot_id"})

    return stats


def calculate_measurement_stats(m_mea):
    """
    Calculate measurement statistics per subplot
    """
    # Check if required columns exist
    agg_dict = {}
    if "tree_height_m" in m_mea.columns:
        agg_dict["tree_height_m"] = ["mean", "median", "min", "max"]
    if "nr_stems_bh" in m_mea.columns:
        agg_dict["nr_stems_bh"] = "mean"

    if not agg_dict:
        # Return empty dataframe if no measurement columns
        return pd.DataFrame(columns=["subplot_id"])

    stats = m_mea.groupby("SUBPLOT_KEY").agg(agg_dict).reset_index()

    # Flatten column names
    stats.columns = ["SUBPLOT_KEY"] + [
        f"{col[0]}_{col[1]}" if isinstance(col, tuple) else col
        for col in stats.columns[1:]
    ]

    # Rename for clarity
    rename_map = {"SUBPLOT_KEY": "subplot_id"}
    if "tree_height_m_mean" in stats.columns:
        rename_map.update(
            {
                "tree_height_m_mean": "avg_height",
                "tree_height_m_median": "median_height",
                "tree_height_m_min": "min_height",
                "tree_height_m_max": "max_height",
            }
        )
    if "nr_stems_bh_mean" in stats.columns:
        rename_map["nr_stems_bh_mean"] = "avg_stems"

    stats = stats.rename(columns=rename_map)

    return stats


def get_validation_summary(gdf):
    """Get summary statistics from validated GeoDataFrame"""
    total = len(gdf)
    valid = gdf["geom_valid"].sum() if "geom_valid" in gdf.columns else 0
    invalid = total - valid

    # Count reasons
    reason_counts = {}
    if "reasons" in gdf.columns:
        for reasons in gdf[~gdf["geom_valid"]]["reasons"]:
            if pd.notna(reasons) and str(reasons).strip():
                for reason in str(reasons).split(";"):
                    reason = reason.strip()
                    if reason:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "valid_pct": (valid / total * 100) if total > 0 else 0,
        "reason_counts": reason_counts,
    }


def filter_by_enumerator(gdf, enumerators):
    """Filter GeoDataFrame by enumerator list"""
    if not enumerators or "enumerator" not in gdf.columns:
        return gdf
    return gdf[gdf["enumerator"].isin(enumerators)]


def filter_by_date(gdf, start_date, end_date):
    """Filter GeoDataFrame by date range"""
    date_col = None
    for col in ["starttime", "SubmissionDate"]:
        if col in gdf.columns:
            date_col = col
            break

    if not date_col:
        return gdf

    gdf = gdf.copy()
    gdf[date_col] = pd.to_datetime(gdf[date_col])

    return gdf[
        (gdf[date_col].dt.date >= start_date) & (gdf[date_col].dt.date <= end_date)
    ]


def get_missing_subplots_analysis(raw_data):
    """
    Analyze subplots without vegetation data
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation" not in raw_data:
        return None

    m_plots = raw_data["plots_subplots"]
    m_veg = raw_data["plots_subplots_vegetation"]

    subplots_veg = set(m_veg["SUBPLOT_KEY"].unique())
    reference_subplots = set(m_plots["SUBPLOT_KEY"].unique())

    missing_subplots = reference_subplots - subplots_veg

    missing_df = m_plots[m_plots["SUBPLOT_KEY"].isin(missing_subplots)]

    # Build display columns list based on what exists
    display_cols = ["SUBPLOT_KEY"]
    if "enumerator" in missing_df.columns:
        display_cols.insert(0, "enumerator")
    if "subplot_comments" in missing_df.columns:
        display_cols.append("subplot_comments")

    return {
        "count": len(missing_subplots),
        "subplots": missing_df[display_cols] if len(display_cols) > 1 else missing_df,
    }


def get_vegetation_density_analysis(raw_data):
    """
    Analyze tree density and coverage
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation" not in raw_data:
        return None

    m_veg = raw_data["plots_subplots_vegetation"]

    # Build aggregation dict based on available columns
    agg_dict = {
        "vegetation_type_number": "sum",
        "coverage_vegetation": "sum",
    }

    # Add enumerator only if it exists
    if "enumerator" in m_veg.columns:
        agg_dict["enumerator"] = "first"

    density = m_veg.groupby("SUBPLOT_KEY").agg(agg_dict).reset_index()

    # Subplots with zero trees
    zero_trees = density[density["vegetation_type_number"] == 0]

    return {
        "density_df": density,
        "zero_trees_count": len(zero_trees),
        "zero_trees_df": zero_trees,
    }


def get_species_analysis(raw_data, species_type="primary"):
    """
    Analyze tree species by type (primary, young, non-primary)
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation" not in raw_data:
        return None

    m_veg = raw_data["plots_subplots_vegetation"]

    if species_type == "primary":
        filtered = m_veg[
            (m_veg["vegetation_type_primary"] == "yes_primary_group")
            & (m_veg["woody_species"] == "other")
        ]
    elif species_type == "young":
        filtered = m_veg[
            (m_veg["vegetation_type_youngtree"] == "yes_groupbelow1.3")
            & (m_veg["woody_species"] == "other")
        ]
    elif species_type == "non_primary":
        filtered = m_veg[
            (m_veg["vegetation_type_primary"] == "no")
            & (m_veg["woody_species"] == "other")
        ]
    else:
        filtered = m_veg

    species_list = filtered[
        [
            "enumerator",
            "SUBPLOT_KEY",
            "other_species",
            "language_other_species",
            "vegetation_type_number",
        ]
    ].dropna(subset=["vegetation_type_number", "other_species"])

    return {
        "count": len(species_list),
        "species_df": species_list,
        "total_trees": (
            species_list["vegetation_type_number"].sum() if len(species_list) > 0 else 0
        ),
    }


def get_height_outliers(raw_data, threshold_multiplier=4):
    """
    Detect height outliers within vegetation groups
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation_measurements" not in raw_data:
        return None

    m_mea = raw_data["plots_subplots_vegetation_measurements"]

    # Calculate median height per vegetation group
    median_check = (
        m_mea.groupby("VEGETATION_KEY")["tree_height_m"]
        .median()
        .reset_index(name="median_height")
    )
    height_total = pd.merge(m_mea, median_check, how="inner", on="VEGETATION_KEY")

    height_total["Upper_outliers"] = height_total.apply(
        lambda row: (
            "outlier"
            if row["tree_height_m"] > (row["median_height"] * threshold_multiplier)
            else "ok"
        ),
        axis=1,
    )
    height_total["Lower_outliers"] = height_total.apply(
        lambda row: (
            "outlier"
            if row["tree_height_m"] < (row["median_height"] / threshold_multiplier)
            else "ok"
        ),
        axis=1,
    )

    outliers = height_total[
        (height_total["Upper_outliers"] == "outlier")
        | (height_total["Lower_outliers"] == "outlier")
    ]

    return {
        "count": len(outliers),
        "outliers_df": outliers,
        "all_with_flags": height_total,
    }


def get_circumference_outliers(raw_data, threshold_multiplier=4):
    """
    Detect circumference outliers within measurement groups
    (Like in COMACO notebook)
    """
    if "complete" not in raw_data:
        return None

    m_cir = raw_data["complete"]

    # Calculate median circumference per measurement group
    median_cir = (
        m_cir.groupby("MEASUREMENT_KEY")["circumference_bh"]
        .median()
        .reset_index(name="median_cir")
    )
    cir_total = pd.merge(m_cir, median_cir, how="inner", on="MEASUREMENT_KEY")

    cir_total["Upper_outliers"] = cir_total.apply(
        lambda row: (
            "outlier"
            if pd.notna(row["circumference_bh"])
            and pd.notna(row["median_cir"])
            and row["circumference_bh"] > (row["median_cir"] * threshold_multiplier)
            else "ok"
        ),
        axis=1,
    )
    cir_total["Lower_outliers"] = cir_total.apply(
        lambda row: (
            "outlier"
            if pd.notna(row["circumference_bh"])
            and pd.notna(row["median_cir"])
            and row["circumference_bh"] < (row["median_cir"] / threshold_multiplier)
            else "ok"
        ),
        axis=1,
    )

    outliers = cir_total[
        (cir_total["Upper_outliers"] == "outlier")
        | (cir_total["Lower_outliers"] == "outlier")
    ]

    return {
        "count": len(outliers),
        "outliers_df": outliers,
        "all_with_flags": cir_total,
    }


def get_coverage_quality_check(raw_data, max_percentage=5):
    """
    Quality check for coverage vegetation
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation" not in raw_data:
        return None

    m_veg = raw_data["plots_subplots_vegetation"]

    coverage = m_veg[
        (m_veg["vegetation_type_woody"] == "nonwoody_coverage")
        | (m_veg["vegetation_type_youngtree"] == "no_coverage")
    ]

    enumerator_coverage = coverage[
        [
            "enumerator",
            "SUBPLOT_KEY",
            "other_species",
            "language_other_species",
            "coverage_vegetation",
        ]
    ].dropna(subset=["other_species"])

    percentage_cov = (
        (len(enumerator_coverage) / len(coverage) * 100) if len(coverage) > 0 else 0
    )

    return {
        "percentage": percentage_cov,
        "coverage_df": enumerator_coverage,
        "total_coverage": len(coverage),
        "other_species_count": len(enumerator_coverage),
        "is_valid": percentage_cov <= max_percentage,
    }


def read_json_to_sheets(json_data):
    """
    Convert SurveyCTO JSON data to sheet structure matching Excel format

    Args:
        json_data: List of dictionaries from SurveyCTO API

    Returns:
        dict: Dictionary with all dataframes matching Excel structure
    """
    import re

    df_main = pd.DataFrame(json_data)

    # Sheet 0: Plots (main form data - keep all non-repeat columns)
    # Exclude columns that are part of repeat groups (contain _number_ pattern)
    plot_cols = []
    for col in df_main.columns:
        # Keep if it doesn't match repeat group patterns
        if not re.search(r"_\d+_\d+", col) and not re.match(r"gt_subplot_\d+$", col):
            plot_cols.append(col)

    plots_df = df_main[plot_cols].copy()
    plots_df = plots_df.rename(columns={"KEY": "PLOT_KEY"})

    # Ensure enumerator field exists - handle different formats from API
    if "enumerator" not in plots_df.columns:
        if "enumerator_name" in plots_df.columns:
            plots_df["enumerator"] = plots_df["enumerator_name"]
        elif "enumerator_id" in plots_df.columns:
            plots_df["enumerator"] = plots_df["enumerator_id"].astype(str)

    # Parse SubmissionDate if it exists and is in string format
    if "SubmissionDate" in plots_df.columns:
        try:
            plots_df["SubmissionDate"] = pd.to_datetime(
                plots_df["SubmissionDate"], format="mixed", errors="coerce"
            )
        except:
            pass  # Keep as is if parsing fails

    # Sheet 1: Subplots (extract from repeat groups)
    subplot_records = []
    for idx, row in df_main.iterrows():
        plot_key = row.get("KEY")

        # Get enumerator - handle different field names
        enumerator = row.get("enumerator")
        if pd.isna(enumerator) or enumerator is None:
            enumerator = row.get("enumerator_name")
        if pd.isna(enumerator) or enumerator is None:
            enumerator = row.get("enumerator_id")

        starttime = row.get("starttime")
        submission_date = row.get("SubmissionDate")

        # Extract subplot data from columns like gt_subplot_1, gt_subplot_2, etc.
        subplot_nums = set()
        for col in df_main.columns:
            match = re.match(r"gt_subplot_(\d+)$", col)
            if match:
                subplot_nums.add(int(match.group(1)))

        for num in sorted(subplot_nums):
            gt_subplot_val = row.get(f"gt_subplot_{num}")
            # Only add if gt_subplot exists, is not null, and is not empty string
            if pd.notna(gt_subplot_val) and str(gt_subplot_val).strip():
                # Match Excel format: uuid:xxx/sub_plot[1] (with brackets!)
                subplot_key = f"{plot_key}/sub_plot[{num}]"

                subplot_rec = {
                    "PLOT_KEY": plot_key,
                    "SUBPLOT_KEY": subplot_key,
                    "KEY": subplot_key,  # Add KEY column to match Excel
                    "PARENT_KEY": plot_key,  # Add PARENT_KEY to match Excel
                    "gt_subplot": gt_subplot_val,
                    "subplot_comments": row.get(f"subplot_comments_{num}", ""),
                    "starttime": starttime,
                    "SubmissionDate": submission_date,
                    "enumerator": enumerator,
                }
                subplot_records.append(subplot_rec)

    subplot_df = pd.DataFrame(subplot_records) if subplot_records else pd.DataFrame()

    # Sheet 2: Vegetation (extract from nested repeat groups)
    vegetation_records = []
    vegetation_keys_found = set()  # Track which (plot_key, subplot_num, veg_num) combinations we've seen

    for idx, row in df_main.iterrows():
        plot_key = row.get("KEY")

        # First pass: Find all vegetation records by looking for vegetation_type_number
        for col in df_main.columns:
            # Match patterns like vegetation_type_number_1_1, vegetation_type_number_1_2, etc.
            match = re.match(r"vegetation_type_number_(\d+)_(\d+)$", col)
            if match:
                subplot_num = int(match.group(1))
                veg_num = int(match.group(2))

                veg_type_num = row.get(
                    f"vegetation_type_number_{subplot_num}_{veg_num}"
                )
                # Add if vegetation_type_number exists and is not null
                if pd.notna(veg_type_num):
                    # Only mark as found if we're actually adding the record
                    vegetation_keys_found.add((plot_key, subplot_num, veg_num))

                    # Match Excel format: uuid:xxx/sub_plot[1]/new_vegetation[1]
                    subplot_key = f"{plot_key}/sub_plot[{subplot_num}]"
                    veg_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]"

                    veg_rec = {
                        "SUBPLOT_KEY": subplot_key,
                        "PARENT_KEY": subplot_key,  # Match Excel
                        "VEGETATION_KEY": veg_key,
                        "KEY": veg_key,  # Match Excel
                        "vegetation_type_number": veg_type_num,
                        "vegetation_type_height": row.get(
                            f"vegetation_type_height_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_woody": row.get(
                            f"vegetation_type_woody_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_primary": row.get(
                            f"vegetation_type_primary_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_dbh": row.get(
                            f"vegetation_type_dbh_{subplot_num}_{veg_num}"
                        ),
                        "tree_year_planted": row.get(
                            f"tree_year_planted_{subplot_num}_{veg_num}"
                        ),
                        "woody_species": row.get(
                            f"woody_species_{subplot_num}_{veg_num}"
                        ),
                        "non_woody_species": row.get(
                            f"non_woody_species_{subplot_num}_{veg_num}"
                        ),
                        "bamboo_species": row.get(
                            f"bamboo_species_{subplot_num}_{veg_num}"
                        ),
                        "banana_species": row.get(
                            f"banana_species_{subplot_num}_{veg_num}"
                        ),
                        "palm_species": row.get(
                            f"palm_species_{subplot_num}_{veg_num}"
                        ),
                        "other_species": row.get(
                            f"other_species_{subplot_num}_{veg_num}"
                        ),
                        "language_other_species": row.get(
                            f"language_other_species_{subplot_num}_{veg_num}"
                        ),
                        "coverage_vegetation": row.get(
                            f"coverage_vegetation_{subplot_num}_{veg_num}"
                        ),
                        "coverage_height": row.get(
                            f"coverage_height_{subplot_num}_{veg_num}"
                        ),
                        "crop_prune": row.get(
                            f"crop_prune_{subplot_num}_{veg_num}"
                        ),
                        "coverage_prune_height": row.get(
                            f"coverage_prune_height_{subplot_num}_{veg_num}"
                        ),
                        "crop_comments": row.get(
                            f"crop_comments_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_youngtree": row.get(
                            f"vegetation_type_youngtree_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_species_type": row.get(
                            f"vegetation_species_type_{subplot_num}_{veg_num}"
                        ),
                    }
                    vegetation_records.append(veg_rec)

        # Second pass: Find coverage-only records (those without vegetation_type_number)
        # Look for non_woody_species or coverage_vegetation patterns
        for col in df_main.columns:
            # Match patterns like non_woody_species_1_3, coverage_vegetation_1_3, etc.
            match = re.match(r"(?:non_woody_species|coverage_vegetation)_(\d+)_(\d+)$", col)
            if match:
                subplot_num = int(match.group(1))
                veg_num = int(match.group(2))

                # Skip if we already found this vegetation record in first pass
                if (plot_key, subplot_num, veg_num) in vegetation_keys_found:
                    continue

                # Check if this record has coverage data
                has_coverage = row.get(f"coverage_vegetation_{subplot_num}_{veg_num}")
                has_non_woody = row.get(f"non_woody_species_{subplot_num}_{veg_num}")
                has_veg_height = row.get(f"vegetation_type_height_{subplot_num}_{veg_num}")

                # Only add if at least one coverage field exists
                if pd.notna(has_coverage) or pd.notna(has_non_woody) or pd.notna(has_veg_height):
                    vegetation_keys_found.add((plot_key, subplot_num, veg_num))

                    # Match Excel format: uuid:xxx/sub_plot[1]/new_vegetation[1]
                    subplot_key = f"{plot_key}/sub_plot[{subplot_num}]"
                    veg_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]"

                    veg_rec = {
                        "SUBPLOT_KEY": subplot_key,
                        "PARENT_KEY": subplot_key,  # Match Excel
                        "VEGETATION_KEY": veg_key,
                        "KEY": veg_key,  # Match Excel
                        "vegetation_type_number": None,  # Coverage-only has no tree count
                        "vegetation_type_height": row.get(
                            f"vegetation_type_height_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_species_type": row.get(
                            f"vegetation_species_type_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_woody": row.get(
                            f"vegetation_type_woody_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_primary": row.get(
                            f"vegetation_type_primary_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_dbh": row.get(
                            f"vegetation_type_dbh_{subplot_num}_{veg_num}"
                        ),
                        "tree_year_planted": row.get(
                            f"tree_year_planted_{subplot_num}_{veg_num}"
                        ),
                        "woody_species": row.get(
                            f"woody_species_{subplot_num}_{veg_num}"
                        ),
                        "non_woody_species": row.get(
                            f"non_woody_species_{subplot_num}_{veg_num}"
                        ),
                        "bamboo_species": row.get(
                            f"bamboo_species_{subplot_num}_{veg_num}"
                        ),
                        "banana_species": row.get(
                            f"banana_species_{subplot_num}_{veg_num}"
                        ),
                        "palm_species": row.get(
                            f"palm_species_{subplot_num}_{veg_num}"
                        ),
                        "other_species": row.get(
                            f"other_species_{subplot_num}_{veg_num}"
                        ),
                        "language_other_species": row.get(
                            f"language_other_species_{subplot_num}_{veg_num}"
                        ),
                        "coverage_vegetation": row.get(
                            f"coverage_vegetation_{subplot_num}_{veg_num}"
                        ),
                        "coverage_height": row.get(
                            f"coverage_height_{subplot_num}_{veg_num}"
                        ),
                        "crop_prune": row.get(
                            f"crop_prune_{subplot_num}_{veg_num}"
                        ),
                        "coverage_prune_height": row.get(
                            f"coverage_prune_height_{subplot_num}_{veg_num}"
                        ),
                        "crop_comments": row.get(
                            f"crop_comments_{subplot_num}_{veg_num}"
                        ),
                        "vegetation_type_youngtree": row.get(
                            f"vegetation_type_youngtree_{subplot_num}_{veg_num}"
                        ),
                    }
                    vegetation_records.append(veg_rec)

    vegetation_df = (
        pd.DataFrame(vegetation_records) if vegetation_records else pd.DataFrame()
    )

    # Convert numeric columns to proper types
    if len(vegetation_df) > 0:
        numeric_cols = ["vegetation_type_number"]
        for col in numeric_cols:
            if col in vegetation_df.columns:
                # Convert to numeric, None/NaN will remain as NaN (for coverage-only records)
                vegetation_df[col] = pd.to_numeric(vegetation_df[col], errors="coerce")

        # Parse tree_year_planted as datetime if it exists
        if "tree_year_planted" in vegetation_df.columns:
            vegetation_df["tree_year_planted"] = pd.to_datetime(
                vegetation_df["tree_year_planted"], format="mixed", errors="coerce"
            )

    # Sheet 3: Measurements
    measurement_records = []
    for idx, row in df_main.iterrows():
        plot_key = row.get("KEY")
        for col in df_main.columns:
            match = re.match(r"tree_height_m_(\d+)_(\d+)_(\d+)$", col)
            if match:
                subplot_num = int(match.group(1))
                veg_num = int(match.group(2))
                mea_num = int(match.group(3))

                tree_height = row.get(
                    f"tree_height_m_{subplot_num}_{veg_num}_{mea_num}"
                )
                # Only add if tree_height exists and is not null
                if pd.notna(tree_height):
                    # Match Excel format: uuid:xxx/sub_plot[1]/new_vegetation[1]/vegetation_measurements[1]
                    veg_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]"
                    mea_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]/vegetation_measurements[{mea_num}]"

                    mea_rec = {
                        "VEGETATION_KEY": veg_key,
                        "PARENT_KEY": veg_key,  # Match Excel
                        "MEASUREMENT_KEY": mea_key,
                        "KEY": mea_key,  # Match Excel
                        "tree_height_m": tree_height,
                        "tree_prune": row.get(
                            f"tree_prune_{subplot_num}_{veg_num}_{mea_num}"
                        ),
                        # NOTE: API has typo "prune_heigth" instead of "prune_height"
                        "prune_height": row.get(
                            f"prune_heigth_{subplot_num}_{veg_num}_{mea_num}"
                        ),
                        "nr_stems_bh": row.get(
                            f"nr_stems_bh_{subplot_num}_{veg_num}_{mea_num}"
                        ),
                        "nr_stems_10cm": row.get(
                            f"nr_stems_10cm_{subplot_num}_{veg_num}_{mea_num}"
                        ),
                        "tree_comments": row.get(
                            f"tree_comments_{subplot_num}_{veg_num}_{mea_num}"
                        ),
                    }
                    measurement_records.append(mea_rec)

    measurement_df = (
        pd.DataFrame(measurement_records) if measurement_records else pd.DataFrame()
    )

    # Convert numeric columns to proper types
    if len(measurement_df) > 0:
        numeric_cols = ["tree_height_m", "nr_stems_bh", "nr_stems_10cm", "prune_height"]
        for col in numeric_cols:
            if col in measurement_df.columns:
                measurement_df[col] = pd.to_numeric(
                    measurement_df[col], errors="coerce"
                )

    # Sheet 4: Circumference
    circumference_records = []
    circumference_keys_found = set()  # Track which (plot_key, subplot, veg, mea, cir) we've seen

    for idx, row in df_main.iterrows():
        plot_key = row.get("KEY")

        # First pass: Extract from circumference_bh columns
        for col in df_main.columns:
            match = re.match(r"circumference_bh_(\d+)_(\d+)_(\d+)_(\d+)$", col)
            if match:
                subplot_num = int(match.group(1))
                veg_num = int(match.group(2))
                mea_num = int(match.group(3))
                cir_num = int(match.group(4))

                circumference_bh = row.get(
                    f"circumference_bh_{subplot_num}_{veg_num}_{mea_num}_{cir_num}"
                )
                circumference_10cm = row.get(
                    f"circumference_10cm_{subplot_num}_{veg_num}_{mea_num}_{cir_num}"
                )

                # Only add if at least one circumference exists and is not null
                if pd.notna(circumference_bh) or pd.notna(circumference_10cm):
                    circumference_keys_found.add((plot_key, subplot_num, veg_num, mea_num, cir_num))

                    # Match Excel format: uuid:xxx/sub_plot[1]/new_vegetation[1]/vegetation_measurements[1]/circumference_bh_group[1]
                    mea_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]/vegetation_measurements[{mea_num}]"
                    cir_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]/vegetation_measurements[{mea_num}]/circumference_bh_group[{cir_num}]"

                    cir_rec = {
                        "MEASUREMENT_KEY": mea_key,
                        "PARENT_KEY": mea_key,  # Match Excel
                        "CIRCUMFERENCE_KEY": cir_key,
                        "KEY": cir_key,  # Match Excel
                        "circumference_bh": circumference_bh,
                        "circumference_10cm": circumference_10cm,
                    }
                    circumference_records.append(cir_rec)

        # Second pass: Find circumference_10cm-only records (no circumference_bh column exists)
        for col in df_main.columns:
            match = re.match(r"circumference_10cm_(\d+)_(\d+)_(\d+)_(\d+)$", col)
            if match:
                subplot_num = int(match.group(1))
                veg_num = int(match.group(2))
                mea_num = int(match.group(3))
                cir_num = int(match.group(4))

                # Skip if we already processed this circumference in first pass
                if (plot_key, subplot_num, veg_num, mea_num, cir_num) in circumference_keys_found:
                    continue

                circumference_10cm = row.get(
                    f"circumference_10cm_{subplot_num}_{veg_num}_{mea_num}_{cir_num}"
                )

                # Only add if circumference_10cm exists and is not null
                if pd.notna(circumference_10cm):
                    circumference_keys_found.add((plot_key, subplot_num, veg_num, mea_num, cir_num))

                    # Match Excel format
                    mea_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]/vegetation_measurements[{mea_num}]"
                    cir_key = f"{plot_key}/sub_plot[{subplot_num}]/new_vegetation[{veg_num}]/vegetation_measurements[{mea_num}]/circumference_bh_group[{cir_num}]"

                    cir_rec = {
                        "MEASUREMENT_KEY": mea_key,
                        "PARENT_KEY": mea_key,
                        "CIRCUMFERENCE_KEY": cir_key,
                        "KEY": cir_key,
                        "circumference_bh": None,  # No circumference_bh for these records
                        "circumference_10cm": circumference_10cm,
                    }
                    circumference_records.append(cir_rec)

    circumference_df = (
        pd.DataFrame(circumference_records) if circumference_records else pd.DataFrame()
    )

    # Convert numeric columns to proper types
    if len(circumference_df) > 0:
        if "circumference_bh" in circumference_df.columns:
            circumference_df["circumference_bh"] = pd.to_numeric(
                circumference_df["circumference_bh"], errors="coerce"
            )
        if "circumference_10cm" in circumference_df.columns:
            circumference_df["circumference_10cm"] = pd.to_numeric(
                circumference_df["circumference_10cm"], errors="coerce"
            )

    return {
        "plots": plots_df,
        "subplots": subplot_df,
        "vegetation": vegetation_df,
        "measurements": measurement_df,
        "circumference": circumference_df,
    }


def process_json_data(json_data):
    """
    Complete processing pipeline for JSON data from API:
    1. Convert JSON to sheets structure
    2. Merge data
    3. Create geometries
    4. Validate
    5. Add statistics

    Args:
        json_data: List of dictionaries from SurveyCTO API

    Returns:
        dict with all processed data
    """
    # Convert JSON to sheets structure
    sheets = read_json_to_sheets(json_data)

    # Use existing merge and processing logic
    merged = merge_all_data(sheets)

    # Get plots-subplots merged data
    m_plots = merged["plots_subplots"]

    # Process subplots for geometry validation
    # Determine which time column to use
    time_col = None
    if "starttime" in m_plots.columns:
        time_col = "starttime"
    elif "SubmissionDate" in m_plots.columns:
        time_col = "SubmissionDate"

    # Build column list dynamically based on what exists
    cols_to_select = []
    if time_col:
        cols_to_select.append(time_col)
    if "enumerator" in m_plots.columns:
        cols_to_select.append("enumerator")

    # Always need these columns
    cols_to_select.extend(["gt_subplot", "SUBPLOT_KEY"])

    # Add measured_subplots if available (from plots data)
    if "measured_subplots" in m_plots.columns:
        cols_to_select.append("measured_subplots")

    # Add PLOT_KEY to group by plot for measured_subplots aggregation
    if "PLOT_KEY" in m_plots.columns:
        cols_to_select.append("PLOT_KEY")

    # Select only existing columns
    subplots_for_validation = m_plots[cols_to_select].copy()
    if "enumerator" in subplots_for_validation.columns:
        print(f"✓ enumerator in subplots_for_validation", file=sys.stderr)
    else:
        print(f"✗ enumerator NOT in subplots_for_validation", file=sys.stderr)

    subplots_for_validation = subplots_for_validation.rename(
        columns={"SUBPLOT_KEY": "subplot_id"}
    )

    # Create geometry
    subplots_for_validation["geometry"] = subplots_for_validation.apply(
        lambda row: geom_from_scto_str(
            row,
            column="gt_subplot",
            accuracy_m=config.GPS_ACCURACY_THRESHOLD,
            accuracy_zero_valid=False,
        ),
        axis=1,
    )

    gdf_subplots = gpd.GeoDataFrame(
        subplots_for_validation, geometry="geometry", crs=4326
    )

    # Fix geometries
    geometry_fixer = GeometryFixer()
    gdf_subplots_fixed = geometry_fixer.fix_geometry(gdf_subplots)

    # Validate
    geometry_validator = GeometryValidator(
        partner=config.PARTNER,
        country=config.COUNTRY,
        threshold_length_width=config.THRESHOLD_LENGTH_WIDTH,
        threshold_protruding_ratio=config.THRESHOLD_PROTRUDING_RATIO,
        validate_id="subplot_id",
        threshold_within_radius=config.THRESHOLD_WITHIN_RADIUS,
        min_area_size=config.MIN_SUBPLOT_AREA_SIZE,
        max_area_size=config.MAX_SUBPLOT_AREA_SIZE,
        max_vertices=config.MAX_VERTICES,
    )
    gdf_subplots_validated = geometry_validator.validate_geometry(gdf_subplots_fixed)

    # Collect reasons
    gdf_final = assign_geom_valid_geojson(
        gdf_subplots_validated,
        min_area=config.MIN_SUBPLOT_AREA_SIZE,
        max_area=config.MAX_SUBPLOT_AREA_SIZE,
    )

    # Ensure enumerator, time, and PLOT_KEY columns are preserved
    # (They might be lost during geometry operations)
    preserve_cols = []
    if "enumerator" in subplots_for_validation.columns:
        preserve_cols.append("enumerator")
    if time_col and time_col in subplots_for_validation.columns:
        preserve_cols.append(time_col)
    if "PLOT_KEY" in subplots_for_validation.columns:
        preserve_cols.append("PLOT_KEY")

    if preserve_cols:
        # Merge back the preserved columns using subplot_id
        preserve_data = subplots_for_validation[
            ["subplot_id"] + preserve_cols
        ].drop_duplicates()

        # Only merge if columns are missing in gdf_final
        cols_to_add = [col for col in preserve_cols if col not in gdf_final.columns]
        if cols_to_add:
            gdf_final = gdf_final.merge(
                preserve_data[["subplot_id"] + cols_to_add], on="subplot_id", how="left"
            )

    # Process plots
    plots_for_validation = sheets["plots"].copy()
    if "gt_plot" in plots_for_validation.columns:
        plots_for_validation["geometry"] = plots_for_validation.apply(
            lambda row: geom_from_scto_str(
                row,
                column="gt_plot",
                accuracy_m=config.GPS_ACCURACY_THRESHOLD,
                accuracy_zero_valid=False,
            ),
            axis=1,
        )
        gdf_plots = gpd.GeoDataFrame(
            plots_for_validation, geometry="geometry", crs=4326
        )
    else:
        gdf_plots = None

    # Add vegetation statistics to subplots if available
    if "plots_subplots_vegetation" in merged:
        try:
            veg_stats = calculate_vegetation_stats(merged["plots_subplots_vegetation"])
            gdf_final = gdf_final.merge(veg_stats, on="subplot_id", how="left")
        except Exception as e:
            print(f"Warning: Could not calculate vegetation stats: {str(e)}")

    # Add measurement statistics if available
    if "plots_subplots_vegetation_measurements" in merged:
        try:
            mea_stats = calculate_measurement_stats(
                merged["plots_subplots_vegetation_measurements"]
            )
            gdf_final = gdf_final.merge(mea_stats, on="subplot_id", how="left")
        except Exception as e:
            print(f"Warning: Could not calculate measurement stats: {str(e)}")

    return {
        "subplots": gdf_final,
        "plots": gdf_plots,
        "raw_data": merged,
        "sheets": sheets,
    }
