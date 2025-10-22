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
    m_plots = pd.merge(plots_df, subplot_df, how="inner", on="PLOT_KEY")

    # Convert submission date if exists
    if "SubmissionDate" in m_plots.columns:
        m_plots["SubmissionDate"] = pd.to_datetime(m_plots["SubmissionDate"]).dt.date

    merged = {"plots_subplots": m_plots}

    # Merge with vegetation if available
    if vegetation_df is not None:
        m_veg = pd.merge(m_plots, vegetation_df, how="left", on="SUBPLOT_KEY")
        merged["plots_subplots_vegetation"] = m_veg

        # Merge with measurements if available
        if measurement_df is not None:
            m_mea = pd.merge(m_veg, measurement_df, how="left", on="VEGETATION_KEY")
            merged["plots_subplots_vegetation_measurements"] = m_mea

            # Merge with circumference if available
            if circumference_df is not None:
                m_cir = pd.merge(
                    m_mea, circumference_df, how="left", on="MEASUREMENT_KEY"
                )
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
    subplots_for_validation = m_plots[
        [
            "starttime" if "starttime" in m_plots.columns else "SubmissionDate",
            "enumerator",
            "gt_subplot",
            "SUBPLOT_KEY",
        ]
    ].copy()

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

    return {
        "count": len(missing_subplots),
        "subplots": (
            missing_df[["enumerator", "SUBPLOT_KEY", "subplot_comments"]]
            if "subplot_comments" in missing_df.columns
            else missing_df[["enumerator", "SUBPLOT_KEY"]]
        ),
    }


def get_vegetation_density_analysis(raw_data):
    """
    Analyze tree density and coverage
    (Like in COMACO notebook)
    """
    if "plots_subplots_vegetation" not in raw_data:
        return None

    m_veg = raw_data["plots_subplots_vegetation"]

    density = (
        m_veg.groupby("SUBPLOT_KEY")
        .agg(
            {
                "vegetation_type_number": "sum",
                "coverage_vegetation": "sum",
                "enumerator": "first",
            }
        )
        .reset_index()
    )

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
