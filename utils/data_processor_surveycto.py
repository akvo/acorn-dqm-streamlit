"""
Data Processor Extension for SurveyCTO API Data
Add this to your data_processor.py file
"""

import pandas as pd
import geopandas as gpd


def process_surveycto_data(data_dict: dict):
    """
    Process data fetched from SurveyCTO API
    Transform API response to match Excel sheet structure

    Parameters:
    - data_dict: Dictionary with 'main' dataframe from API

    Returns:
    - Processed data dictionary ready for validation
    """

    # Get main dataframe
    main_df = data_dict.get("main")

    if main_df is None or len(main_df) == 0:
        raise ValueError("No data received from SurveyCTO API")

    # ============================================
    # EXTRACT PLOTS DATA
    # ============================================

    # Main form columns become plots
    plot_columns = [
        "KEY",  # Will become PLOT_KEY
        "gt_plot",
        "enumerator",
        "starttime",
        "endtime",
        "SubmissionDate",
        # Add other plot-level columns you need
    ]

    # Filter existing columns
    available_plot_cols = [col for col in plot_columns if col in main_df.columns]

    plots_df = main_df[available_plot_cols].copy()
    plots_df = plots_df.rename(columns={"KEY": "PLOT_KEY"})

    # ============================================
    # EXTRACT SUBPLOTS DATA (FROM REPEAT GROUP)
    # ============================================

    # SurveyCTO stores repeat groups with prefixes
    # Common pattern: repeatgroup-columnname
    # For example: subplots-gt_subplot, subplots-gt_subplot_gps

    # Method 1: If repeat group data is in separate columns
    subplot_cols = [col for col in main_df.columns if col.startswith("subplots-")]

    if subplot_cols:
        # Extract repeat group data
        # This is complex because SurveyCTO may have multiple rows per submission
        # with SET-OF prefixes for multi-value repeat groups

        subplots_df = extract_repeat_group(main_df, "subplots")

    else:
        # Method 2: If subplots are in wide format with indices
        # subplots[0]-gt_subplot, subplots[1]-gt_subplot, etc.

        # Find all subplot indices
        subplot_indices = set()
        for col in main_df.columns:
            if "subplot" in col.lower() and "[" in col:
                # Extract index
                try:
                    idx = int(col.split("[")[1].split("]")[0])
                    subplot_indices.add(idx)
                except:
                    pass

        if subplot_indices:
            subplots_df = extract_indexed_repeat_group(
                main_df, "subplots", subplot_indices
            )
        else:
            raise ValueError(
                "Could not find subplot data in SurveyCTO response. "
                "Please check your form structure and repeat group names."
            )

    # ============================================
    # EXTRACT VEGETATION DATA (OPTIONAL)
    # ============================================

    vegetation_cols = [col for col in main_df.columns if "vegetation" in col.lower()]

    if vegetation_cols:
        vegetation_df = extract_repeat_group(main_df, "vegetation")
    else:
        vegetation_df = None

    # ============================================
    # EXTRACT MEASUREMENTS DATA (OPTIONAL)
    # ============================================

    measurement_cols = [col for col in main_df.columns if "measurement" in col.lower()]

    if measurement_cols:
        measurement_df = extract_repeat_group(main_df, "measurements")
    else:
        measurement_df = None

    # ============================================
    # EXTRACT CIRCUMFERENCE DATA (OPTIONAL)
    # ============================================

    circum_cols = [col for col in main_df.columns if "circumference" in col.lower()]

    if circum_cols:
        circumference_df = extract_repeat_group(main_df, "circumference")
    else:
        circumference_df = None

    # ============================================
    # CREATE SHEETS DICTIONARY
    # ============================================

    sheets_dict = {
        "plots": plots_df,
        "subplots": subplots_df,
        "vegetation": vegetation_df,
        "measurements": measurement_df,
        "circumference": circumference_df,
    }

    # ============================================
    # PROCESS USING EXISTING PIPELINE
    # ============================================

    # Now use the existing processing functions
    from utils.data_processor import (
        merge_all_data,
        create_geometries,
        validate_subplots,
        validate_plots,
    )

    # Merge data
    merged = merge_all_data(sheets_dict)

    # Create geometries
    gdf_subplots = create_geometries(merged["plots_subplots"], level="subplot")

    # Validate subplots
    gdf_subplots = validate_subplots(gdf_subplots)

    # Validate plots if needed
    if "gt_plot_gps" in merged["plots_subplots"].columns:
        gdf_plots = create_geometries(merged["plots_subplots"], level="plot")
        gdf_plots = validate_plots(gdf_plots)
    else:
        gdf_plots = None

    # Return processed data
    return {
        "subplots": gdf_subplots,
        "plots": gdf_plots,
        "merged": merged,
        "raw_sheets": sheets_dict,
    }


def extract_repeat_group(df: pd.DataFrame, group_name: str) -> pd.DataFrame:
    """
    Extract repeat group data from SurveyCTO wide format

    Parameters:
    - df: Main dataframe
    - group_name: Name of repeat group (e.g., 'subplots', 'vegetation')

    Returns:
    - DataFrame with repeat group data
    """

    # Find all columns belonging to this repeat group
    # Pattern: {group_name}-{field_name}
    prefix = f"{group_name}-"
    group_cols = [col for col in df.columns if col.startswith(prefix)]

    if not group_cols:
        return None

    # Extract PARENT_KEY (KEY from main form)
    repeat_data = []

    for idx, row in df.iterrows():
        parent_key = row.get("KEY")

        # Check if this row has repeat group data
        # (some rows might not have any repeat group records)
        has_data = any(pd.notna(row[col]) for col in group_cols)

        if has_data:
            # Create record for this repeat
            record = {"PARENT_KEY": parent_key}

            # Add all fields from repeat group
            for col in group_cols:
                # Remove prefix to get field name
                field_name = col.replace(prefix, "")
                record[field_name] = row[col]

            repeat_data.append(record)

    if not repeat_data:
        return None

    repeat_df = pd.DataFrame(repeat_data)

    # Generate KEY for repeat group records
    repeat_df["KEY"] = [
        f"{row['PARENT_KEY']}-{group_name}-{i}"
        for i, row in enumerate(repeat_df.iterrows())
    ]

    return repeat_df


def extract_indexed_repeat_group(
    df: pd.DataFrame, group_name: str, indices: set
) -> pd.DataFrame:
    """
    Extract repeat group data from indexed columns
    Pattern: {group_name}[0]-field, {group_name}[1]-field, etc.

    Parameters:
    - df: Main dataframe
    - group_name: Name of repeat group
    - indices: Set of indices found

    Returns:
    - DataFrame with repeat group data in long format
    """

    repeat_data = []

    for idx, row in df.iterrows():
        parent_key = row.get("KEY")

        # Extract each repeat instance
        for repeat_idx in sorted(indices):
            # Find columns for this index
            prefix = f"{group_name}[{repeat_idx}]-"
            instance_cols = [col for col in df.columns if col.startswith(prefix)]

            if not instance_cols:
                continue

            # Check if this instance has data
            has_data = any(pd.notna(row[col]) for col in instance_cols)

            if has_data:
                record = {
                    "PARENT_KEY": parent_key,
                    "KEY": f"{parent_key}-{group_name}-{repeat_idx}",
                }

                # Extract fields
                for col in instance_cols:
                    field_name = col.replace(prefix, "")
                    record[field_name] = row[col]

                repeat_data.append(record)

    if not repeat_data:
        return None

    return pd.DataFrame(repeat_data)


def map_surveycto_columns(df: pd.DataFrame, column_mapping: dict) -> pd.DataFrame:
    """
    Map SurveyCTO column names to expected column names

    Parameters:
    - df: DataFrame to transform
    - column_mapping: Dictionary mapping SurveyCTO cols to expected cols

    Returns:
    - DataFrame with renamed columns
    """

    # Only rename columns that exist
    existing_mapping = {
        old: new for old, new in column_mapping.items() if old in df.columns
    }

    return df.rename(columns=existing_mapping)


# ============================================
# EXAMPLE COLUMN MAPPINGS
# ============================================

# Define your SurveyCTO form column names here
# Adjust based on your actual form structure

SURVEYCTO_COLUMN_MAPPINGS = {
    # Plot level
    "plots": {
        "gt_plot": "gt_plot",  # If same name
        "gt_plot_gps": "gt_plot_gps",
        "enumerator": "enumerator",
        "start": "starttime",
        "end": "endtime",
        # Add your custom mappings
    },
    # Subplot level
    "subplots": {
        "gt_subplot": "gt_subplot",
        "gt_subplot_gps": "gt_subplot_gps",
        "gt_subplot_gps_accuracy": "gt_subplot_gps_accuracy",
        # Add your custom mappings
    },
    # Vegetation level
    "vegetation": {
        # Add your mappings
    },
}
