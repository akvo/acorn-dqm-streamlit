"""
Vegetation Validation Utilities
Quality checks for vegetation data based on ground truth validation logic
"""

import pandas as pd
import streamlit as st
from typing import Dict, List, Tuple, Optional


def check_missing_vegetation(
    subplots_df: pd.DataFrame,
    vegetation_df: pd.DataFrame,
    subplot_key_col: str = "SUBPLOT_KEY",
    subplot_id_col: str = "subplot_id",
) -> pd.DataFrame:
    """
    Identify subplots with no vegetation records.

    Args:
        subplots_df: Dataframe with subplots (uses subplot_id_col)
        vegetation_df: Dataframe with vegetation (uses subplot_key_col)
        subplot_key_col: Column name in vegetation_df (default: SUBPLOT_KEY)
        subplot_id_col: Column name in subplots_df (default: subplot_id)

    Returns dataframe of subplots missing vegetation with their comments.
    """
    # Get unique subplot IDs from both dataframes
    all_subplots = set(subplots_df[subplot_id_col].unique())
    subplots_with_veg = set(vegetation_df[subplot_key_col].unique())

    # Find missing
    missing_subplots = all_subplots - subplots_with_veg

    # Return subplots that are missing
    missing_df = subplots_df[subplots_df[subplot_id_col].isin(missing_subplots)].copy()

    return missing_df


def get_missing_subplots(
    plots_df: pd.DataFrame, vegetation_df: pd.DataFrame, display_cols: List[str] = None
) -> pd.DataFrame:
    """
    Get subplots without vegetation records - matches notebook logic exactly.

    Notebook logic:
    subplots_veg = set(m_veg["SUBPLOT_KEY"].unique())
    reference_subplots = set(m_plots["SUBPLOT_KEY"].unique())
    missing_subplots = reference_subplots - subplots_veg
    missing_df = m_plots[m_plots["SUBPLOT_KEY"].isin(missing_subplots)]

    Args:
        plots_df: DataFrame with ALL subplots (m_plots in notebook)
        vegetation_df: DataFrame with vegetation records (m_veg in notebook)
        display_cols: Columns to display (default: ["enumerator", "SUBPLOT_KEY", "subplot_comments"])

    Returns:
        DataFrame of subplots missing vegetation
    """
    if display_cols is None:
        display_cols = ["enumerator", "SUBPLOT_KEY", "subplot_comments"]

    # Check required columns
    if "SUBPLOT_KEY" not in plots_df.columns:
        return pd.DataFrame()

    if "SUBPLOT_KEY" not in vegetation_df.columns:
        return pd.DataFrame()

    # Exact notebook logic
    subplots_veg = set(vegetation_df["SUBPLOT_KEY"].unique())
    reference_subplots = set(plots_df["SUBPLOT_KEY"].unique())
    missing_subplots = reference_subplots - subplots_veg

    # Get full records
    missing_df = plots_df[plots_df["SUBPLOT_KEY"].isin(missing_subplots)].copy()

    return missing_df


def check_unidentified_species(
    vegetation_df: pd.DataFrame, species_columns: List[str] = None
) -> pd.DataFrame:
    """
    Find vegetation records with 'other' species needing botanical verification.
    """
    if species_columns is None:
        species_columns = [
            "vegetation_species_type",
            "other_species",
            "woody_species",
            "non_woody_species",
        ]

    conditions = []
    for col in species_columns:
        if col in vegetation_df.columns:
            conditions.append(vegetation_df[col].str.lower() == "other")

    if conditions:
        combined = conditions[0]
        for cond in conditions[1:]:
            combined = combined | cond

        return vegetation_df[combined].copy()

    return pd.DataFrame()


def detect_height_outliers(
    df: pd.DataFrame,
    height_col: str = "tree_height_m",
    species_col: str = "woody_species",
    upper_threshold: float = 3.0,
    lower_threshold: float = 0.33,
) -> pd.DataFrame:
    """
    Detect height outliers using median comparison within species groups.

    Logic from notebook: >3x or <0.33x median height for species
    """
    df = df.copy()

    # Filter to records with both height and species
    df_filtered = df[df[height_col].notna() & df[species_col].notna()].copy()

    if len(df_filtered) == 0:
        df["Upper_outliers"] = "ok"
        df["Lower_outliers"] = "ok"
        df["median_height"] = None
        return df

    # Calculate median heights by species
    species_medians = (
        df_filtered.groupby(species_col)[height_col].median().reset_index()
    )
    species_medians.columns = [species_col, "median_height"]

    # Merge back
    df = df.merge(species_medians, on=species_col, how="left")

    # Flag outliers
    df["Upper_outliers"] = df.apply(
        lambda row: (
            "outlier"
            if pd.notna(row.get("median_height"))
            and row[height_col] > (row["median_height"] * upper_threshold)
            else "ok"
        ),
        axis=1,
    )
    df["Lower_outliers"] = df.apply(
        lambda row: (
            "outlier"
            if (
                pd.notna(row.get("median_height"))
                and row["median_height"] > 0
                and row[height_col] < (row["median_height"] * lower_threshold)
            )
            else "ok"
        ),
        axis=1,
    )

    return df


def detect_circumference_outliers(
    df: pd.DataFrame,
    circ_col: str = "circumference_bh",
    species_col: str = "woody_species",
    upper_threshold: float = 4.0,
    lower_threshold: float = 0.25,
) -> pd.DataFrame:
    """
    Detect circumference outliers using median comparison within species groups.

    Logic from notebook: >4x or <0.25x median circumference for species
    """
    df = df.copy()

    # Filter to records with both circumference and species
    df_filtered = df[df[circ_col].notna() & df[species_col].notna()].copy()

    if len(df_filtered) == 0:
        df["Upper_outliers"] = "ok"
        df["Lower_outliers"] = "ok"
        df["median_cir"] = None
        return df

    # Calculate median by species
    median_circ = (
        df_filtered.groupby(species_col)[circ_col]
        .median()
        .reset_index(name="median_cir")
    )

    # Merge back
    df = df.merge(median_circ, on=species_col, how="left")

    # Flag outliers
    df["Upper_outliers"] = df.apply(
        lambda row: (
            "outlier"
            if pd.notna(row.get("median_cir"))
            and row[circ_col] > (row["median_cir"] * upper_threshold)
            else "ok"
        ),
        axis=1,
    )
    df["Lower_outliers"] = df.apply(
        lambda row: (
            "outlier"
            if (
                pd.notna(row.get("median_cir"))
                and row["median_cir"] > 0
                and row[circ_col] < (row["median_cir"] * lower_threshold)
            )
            else "ok"
        ),
        axis=1,
    )

    return df


def detect_suspicious_circumference_by_age(
    df: pd.DataFrame,
    circ_col: str = "circumference_bh",
    age_col: str = "tree_age",
    young_tree_circ_threshold: float = 50.0,
    young_tree_age_threshold: int = 5,
    large_circ_threshold: float = 300.0,
    large_circ_age_threshold: int = 15,
) -> pd.DataFrame:
    """
    Flag suspicious circumferences based on tree age.

    Logic from notebook:
    - Circumference >50cm but age <5 years is suspicious
    - Circumference >300cm but age <15 years is suspicious
    """
    df = df.copy()

    if age_col not in df.columns or circ_col not in df.columns:
        df["suspicious"] = False
        return df

    df["suspicious"] = (
        (df[circ_col] > young_tree_circ_threshold)
        & (df[age_col] < young_tree_age_threshold)
    ) | (
        (df[circ_col] > large_circ_threshold) & (df[age_col] < large_circ_age_threshold)
    )

    return df


def detect_stem_outliers(
    df: pd.DataFrame,
    stem_bh_col: str = "nr_stems_bh",
    stem_10cm_col: str = "nr_stems_10cm",
    threshold: int = 20,
) -> pd.DataFrame:
    """
    Detect trees with unusually high stem counts.

    From notebook: nr_stems_bh > 20 is suspicious (should be >40?)

    Returns df with 'high_stems_bh' and 'high_stems_10cm' boolean columns
    """
    df = df.copy()

    if stem_bh_col in df.columns:
        df["high_stems_bh"] = df[stem_bh_col] > threshold
    else:
        df["high_stems_bh"] = False

    if stem_10cm_col in df.columns:
        df["high_stems_10cm"] = df[stem_10cm_col] > threshold
    else:
        df["high_stems_10cm"] = False

    return df


def check_coverage_only_subplots(
    vegetation_df: pd.DataFrame,
    measurements_df: pd.DataFrame,
    subplot_key_col: str = "SUBPLOT_KEY",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Find subplots with only coverage data (no individual tree measurements).

    Returns:
        - coverage_only_df: Subplots with coverage but no measurements
        - missing_measurements_df: Expected measurements that are missing
    """
    # Subplots with vegetation records
    subplots_with_veg = set(vegetation_df[subplot_key_col].unique())

    # Subplots with measurements
    if "VEGETATION_KEY" in measurements_df.columns:
        veg_with_meas = vegetation_df[
            vegetation_df["VEGETATION_KEY"].isin(measurements_df["VEGETATION_KEY"])
        ]
        subplots_with_meas = set(veg_with_meas[subplot_key_col].unique())
    else:
        subplots_with_meas = set()

    # Coverage only = has vegetation but no measurements
    coverage_only = subplots_with_veg - subplots_with_meas

    coverage_only_df = vegetation_df[
        vegetation_df[subplot_key_col].isin(coverage_only)
    ].copy()

    # Check if coverage columns exist
    has_coverage = False
    for col in ["coverage_vegetation", "coverage_height"]:
        if col in coverage_only_df.columns:
            has_coverage = True
            break

    if not has_coverage:
        # These are truly missing measurements
        missing_measurements_df = coverage_only_df
        coverage_only_df = pd.DataFrame()
    else:
        missing_measurements_df = pd.DataFrame()

    return coverage_only_df, missing_measurements_df


def check_tall_trees(
    df: pd.DataFrame, height_col: str = "tree_height_m", threshold: float = 30.0
) -> pd.DataFrame:
    """
    Flag exceptionally tall trees for review.

    Returns df with 'tall_tree' boolean column
    """
    df = df.copy()

    if height_col in df.columns:
        df["tall_tree"] = df[height_col] > threshold
    else:
        df["tall_tree"] = False

    return df


def check_primary_vs_young_trees(
    vegetation_df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    """
    Separate and validate primary vs young tree records.

    NOTE: This function checks for BOOLEAN values. If your data uses strings
    like "yes_groupbelow1.3", use get_young_trees_with_other() instead.

    Returns dict with:
        - 'primary_only': Trees marked as primary but not young
        - 'young_only': Trees marked as young but not primary
        - 'both': Trees marked as both (quality issue)
        - 'neither': Trees marked as neither (quality issue)
    """
    result = {}

    if "vegetation_type_primary" not in vegetation_df.columns:
        return result

    has_young = "vegetation_type_youngtree" in vegetation_df.columns

    if has_young:
        result["primary_only"] = vegetation_df[
            (vegetation_df["vegetation_type_primary"] == True)
            & (vegetation_df["vegetation_type_youngtree"] == False)
        ].copy()

        result["young_only"] = vegetation_df[
            (vegetation_df["vegetation_type_primary"] == False)
            & (vegetation_df["vegetation_type_youngtree"] == True)
        ].copy()

        result["both"] = vegetation_df[
            (vegetation_df["vegetation_type_primary"] == True)
            & (vegetation_df["vegetation_type_youngtree"] == True)
        ].copy()

        result["neither"] = vegetation_df[
            (vegetation_df["vegetation_type_primary"] == False)
            & (vegetation_df["vegetation_type_youngtree"] == False)
        ].copy()
    else:
        result["primary_only"] = vegetation_df[
            vegetation_df["vegetation_type_primary"] == True
        ].copy()

        result["no_primary"] = vegetation_df[
            vegetation_df["vegetation_type_primary"] == False
        ].copy()

    return result


def get_young_trees_with_other(
    vegetation_df: pd.DataFrame,
    young_tree_value: str = "yes_groupbelow1.3",
    drop_na_cols: List[str] = None,
) -> pd.DataFrame:
    """
    Get young trees with 'other' woody species requiring botanical verification.

    This matches the notebook logic:
    - vegetation_type_youngtree == "yes_groupbelow1.3"
    - woody_species == "other"

    Args:
        vegetation_df: Vegetation dataframe
        young_tree_value: Value that indicates young tree (default: "yes_groupbelow1.3")
        drop_na_cols: Columns to drop NaN from (default: ["vegetation_type_number", "other_species"])

    Returns:
        Filtered dataframe with young trees that have 'other' species
    """
    if drop_na_cols is None:
        drop_na_cols = ["vegetation_type_number", "other_species"]

    # Check required columns exist
    if "vegetation_type_youngtree" not in vegetation_df.columns:
        return pd.DataFrame()

    if "woody_species" not in vegetation_df.columns:
        return pd.DataFrame()

    # Filter using notebook logic
    young_with_other = vegetation_df[
        (vegetation_df["vegetation_type_youngtree"] == young_tree_value)
        & (vegetation_df["woody_species"] == "other")
    ].copy()

    # Drop NaN in specified columns (like notebook does)
    for col in drop_na_cols:
        if col in young_with_other.columns:
            young_with_other = young_with_other.dropna(subset=[col])

    return young_with_other


def get_primary_trees_with_other(
    vegetation_df: pd.DataFrame,
    primary_value: str = "yes_primary_group",
    drop_na_cols: List[str] = None,
) -> pd.DataFrame:
    """
    Get primary trees with 'other' woody species requiring botanical verification.

    This matches the notebook logic:
    - vegetation_type_primary == "yes_primary_group"
    - woody_species == "other"

    Args:
        vegetation_df: Vegetation dataframe
        primary_value: Value that indicates primary tree (default: "yes_primary_group")
        drop_na_cols: Columns to drop NaN from (default: ["vegetation_type_number", "other_species"])

    Returns:
        Filtered dataframe with primary trees that have 'other' species
    """
    if drop_na_cols is None:
        drop_na_cols = ["vegetation_type_number", "other_species"]

    # Check required columns exist
    if "vegetation_type_primary" not in vegetation_df.columns:
        return pd.DataFrame()

    if "woody_species" not in vegetation_df.columns:
        return pd.DataFrame()

    # Filter using notebook logic
    primary_with_other = vegetation_df[
        (vegetation_df["vegetation_type_primary"] == primary_value)
        & (vegetation_df["woody_species"] == "other")
    ].copy()

    # Drop NaN in specified columns (like notebook does)
    for col in drop_na_cols:
        if col in primary_with_other.columns:
            primary_with_other = primary_with_other.dropna(subset=[col])

    return primary_with_other


def get_non_primary_trees_with_other(
    vegetation_df: pd.DataFrame,
    non_primary_value: str = "no",
    drop_na_cols: List[str] = None,
) -> pd.DataFrame:
    """
    Get non-primary trees with 'other' woody species requiring botanical verification.

    This matches the notebook logic:
    - vegetation_type_primary == "no"
    - woody_species == "other"

    Args:
        vegetation_df: Vegetation dataframe
        non_primary_value: Value that indicates non-primary tree (default: "no")
        drop_na_cols: Columns to drop NaN from (default: ["vegetation_type_number", "other_species"])

    Returns:
        Filtered dataframe with non-primary trees that have 'other' species
    """
    if drop_na_cols is None:
        drop_na_cols = ["vegetation_type_number", "other_species"]

    # Check required columns exist
    if "vegetation_type_primary" not in vegetation_df.columns:
        return pd.DataFrame()

    if "woody_species" not in vegetation_df.columns:
        return pd.DataFrame()

    # Filter using notebook logic
    non_primary_with_other = vegetation_df[
        (vegetation_df["vegetation_type_primary"] == non_primary_value)
        & (vegetation_df["woody_species"] == "other")
    ].copy()

    # Drop NaN in specified columns (like notebook does)
    for col in drop_na_cols:
        if col in non_primary_with_other.columns:
            non_primary_with_other = non_primary_with_other.dropna(subset=[col])

    return non_primary_with_other


def get_tree_classification_debug_info(vegetation_df: pd.DataFrame) -> Dict[str, any]:
    """
    Get debug information about tree classification columns.

    Useful for understanding data structure when filters aren't working.

    Returns dict with column info, unique values, and data types.
    """
    debug_info = {
        "total_records": len(vegetation_df),
        "columns": vegetation_df.columns.tolist(),
    }

    # Check vegetation_type_primary
    if "vegetation_type_primary" in vegetation_df.columns:
        debug_info["primary_dtype"] = str(
            vegetation_df["vegetation_type_primary"].dtype
        )
        debug_info["primary_values"] = (
            vegetation_df["vegetation_type_primary"].value_counts().to_dict()
        )
    else:
        debug_info["primary_dtype"] = "Column not found"
        debug_info["primary_values"] = {}

    # Check vegetation_type_youngtree
    if "vegetation_type_youngtree" in vegetation_df.columns:
        debug_info["young_dtype"] = str(
            vegetation_df["vegetation_type_youngtree"].dtype
        )
        debug_info["young_values"] = (
            vegetation_df["vegetation_type_youngtree"].value_counts().to_dict()
        )
    else:
        debug_info["young_dtype"] = "Column not found"
        debug_info["young_values"] = {}

    # Check woody_species
    if "woody_species" in vegetation_df.columns:
        debug_info["woody_dtype"] = str(vegetation_df["woody_species"].dtype)
        debug_info["woody_values_top10"] = (
            vegetation_df["woody_species"].value_counts().head(10).to_dict()
        )
        debug_info["woody_other_count"] = (
            vegetation_df["woody_species"] == "other"
        ).sum()
    else:
        debug_info["woody_dtype"] = "Column not found"
        debug_info["woody_values_top10"] = {}
        debug_info["woody_other_count"] = 0

    return debug_info


def validate_species_lists(vegetation_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Validate species categorization (woody, palm, bamboo, banana).

    Returns dict with DataFrames for each species category
    """
    result = {}

    species_cols = {
        "woody": "woody_species",
        "palm": "palm_species",
        "bamboo": "bamboo_species",
        "banana": "banana_species",
    }

    for category, col in species_cols.items():
        if col in vegetation_df.columns:
            result[category] = vegetation_df[vegetation_df[col].notna()].copy()
        else:
            result[category] = pd.DataFrame()

    return result


def create_threshold_slider(
    label: str,
    default_value: float,
    min_value: float = 0.0,
    max_value: float = 100.0,
    step: float = 1.0,
    key: str = None,
) -> float:
    """
    Create a Streamlit slider for adjustable quality thresholds.

    Example:
        threshold = create_threshold_slider("Stem Count Threshold", default_value=20, max_value=50)
    """
    return st.slider(
        label,
        min_value=min_value,
        max_value=max_value,
        value=default_value,
        step=step,
        key=key,
        help=f"Adjust threshold for {label.lower()}",
    )
