"""
Data Merge Utilities
Handles merging vegetation data with enumerator information and other utilities
"""

import pandas as pd
from datetime import datetime
from typing import Optional
import sys


def merge_with_enumerator(veg_df, filtered_gdf):
    """
    Merge vegetation dataframe with enumerator information from GeoDataFrame

    Args:
        veg_df: Vegetation DataFrame with SUBPLOT_KEY
        filtered_gdf: GeoDataFrame with subplot_id and optionally enumerator

    Returns:
        Merged DataFrame with enumerator information
    """
    if veg_df is None or len(veg_df) == 0:
        return veg_df

    if filtered_gdf is None or len(filtered_gdf) == 0:
        return veg_df

    # Check what columns are available in filtered_gdf
    cols_to_merge = ["subplot_id"]

    # Add enumerator if it exists
    if "enumerator" in filtered_gdf.columns:
        cols_to_merge.append("enumerator")

    # Extract only the columns we need
    merge_df = filtered_gdf[cols_to_merge].copy()

    # Prepare vegetation dataframe for merge
    veg_for_merge = veg_df.copy()

    # Ensure we have the key column
    if "SUBPLOT_KEY" in veg_for_merge.columns:
        veg_for_merge = veg_for_merge.rename(columns={"SUBPLOT_KEY": "subplot_id"})

    # Merge
    result = pd.merge(veg_for_merge, merge_df, on="subplot_id", how="left")

    return result


def add_enumerator_to_dataframe(df, subplots_gdf, subplot_key_col="SUBPLOT_KEY"):
    """
    Add enumerator column to any dataframe that has subplot keys

    Args:
        df: DataFrame with subplot keys
        subplots_gdf: GeoDataFrame with subplot_id and enumerator
        subplot_key_col: Name of the subplot key column in df

    Returns:
        DataFrame with enumerator column added
    """
    if df is None or len(df) == 0:
        return df

    if subplots_gdf is None or len(subplots_gdf) == 0:
        return df

    # Check if enumerator exists in source
    if "enumerator" not in subplots_gdf.columns:
        # Return original df unchanged if no enumerator data
        return df

    # Prepare merge
    result = df.copy()

    # Create mapping from subplot_id to enumerator
    enum_map = subplots_gdf[["subplot_id", "enumerator"]].drop_duplicates()

    # Rename to match
    if subplot_key_col in result.columns:
        result = result.rename(columns={subplot_key_col: "subplot_id"})

    # Merge
    result = pd.merge(result, enum_map, on="subplot_id", how="left")

    # Rename back if needed
    if subplot_key_col != "subplot_id":
        result = result.rename(columns={"subplot_id": subplot_key_col})

    return result


def extract_year_from_planted(series):
    """
    Extract year from tree_year_planted column
    Handles both formats:
    - Direct year (e.g., 2020, 2015)
    - Epoch timestamp (converts to year)
    - Date strings (extracts year)

    Returns: Series of years (integers)
    """

    def parse_year(value):
        if pd.isna(value):
            return None

        try:
            # First, try to convert to numeric
            num_val = float(value)

            # If it's a large number (>10000), it's likely an epoch timestamp
            if num_val > 10000:
                # Try different epoch units
                # Milliseconds (most common)
                if num_val > 1e12:
                    dt = pd.to_datetime(num_val, unit="ms", errors="coerce")
                else:
                    # Seconds
                    dt = pd.to_datetime(num_val, unit="s", errors="coerce")

                if pd.notna(dt):
                    return dt.year
                return None
            else:
                # It's already a year (between 1900-2100)
                year = int(num_val)
                if 1900 <= year <= 2100:
                    return year
                return None
        except:
            # If numeric conversion fails, try parsing as date string
            try:
                dt = pd.to_datetime(value, errors="coerce")
                if pd.notna(dt):
                    return dt.year
            except:
                pass
            return None

    return series.apply(parse_year)


def calculate_tree_age(df, planting_year_col="tree_year_planted", reference_year=None):
    """
    Calculate tree age from planting year
    Handles epoch timestamps, direct years, and date strings

    Args:
        df: DataFrame with planting year column
        planting_year_col: Name of the planting year column
        reference_year: Reference year (defaults to current year)

    Returns:
        DataFrame with tree_age column added
    """
    if df is None or len(df) == 0:
        return df

    if planting_year_col not in df.columns:
        return df

    result = df.copy()

    # Get reference year
    if reference_year is None:
        reference_year = datetime.now().year

    # Extract year (handles multiple formats)
    planted_years = extract_year_from_planted(result[planting_year_col])

    # Calculate age
    result["tree_age"] = reference_year - planted_years

    return result


def merge_measurement_data(veg_df, mea_df):
    """
    Merge vegetation data with measurement data

    Args:
        veg_df: Vegetation DataFrame with VEGETATION_KEY
        mea_df: Measurement DataFrame with VEGETATION_KEY

    Returns:
        Merged DataFrame
    """
    if veg_df is None or len(veg_df) == 0:
        return veg_df

    if mea_df is None or len(mea_df) == 0:
        return veg_df

    if "VEGETATION_KEY" not in veg_df.columns or "VEGETATION_KEY" not in mea_df.columns:
        return veg_df

    result = pd.merge(veg_df, mea_df, on="VEGETATION_KEY", how="left")

    return result


def add_subplot_geometry(df, subplots_gdf, subplot_key_col="SUBPLOT_KEY"):
    """
    Add geometry information to dataframe from subplots GeoDataFrame

    Args:
        df: DataFrame with subplot keys
        subplots_gdf: GeoDataFrame with geometry
        subplot_key_col: Name of subplot key column

    Returns:
        GeoDataFrame with geometry added
    """
    import geopandas as gpd

    if df is None or len(df) == 0:
        return df

    if subplots_gdf is None or len(subplots_gdf) == 0:
        return df

    result = df.copy()

    # Prepare for merge
    if subplot_key_col in result.columns:
        result = result.rename(columns={subplot_key_col: "subplot_id"})

    # Get geometry from subplots
    geom_df = subplots_gdf[["subplot_id", "geometry"]].copy()

    # Merge
    result = pd.merge(result, geom_df, on="subplot_id", how="left")

    # Convert to GeoDataFrame if geometry exists
    if "geometry" in result.columns:
        result = gpd.GeoDataFrame(result, geometry="geometry", crs=subplots_gdf.crs)

    return result


def filter_by_date_range(df, start_date, end_date, date_col="SubmissionDate"):
    """
    Filter dataframe by date range

    Args:
        df: DataFrame with date column
        start_date: Start date
        end_date: End date
        date_col: Name of date column

    Returns:
        Filtered DataFrame
    """
    if df is None or len(df) == 0:
        return df

    if date_col not in df.columns:
        return df

    result = df.copy()

    # Ensure date column is datetime
    if not pd.api.types.is_datetime64_any_dtype(result[date_col]):
        result[date_col] = pd.to_datetime(result[date_col], errors="coerce")

    # Filter
    mask = (result[date_col].dt.date >= start_date) & (
        result[date_col].dt.date <= end_date
    )
    result = result[mask]

    return result


def aggregate_by_subplot(df, agg_dict, subplot_key_col="SUBPLOT_KEY"):
    """
    Aggregate data by subplot

    Args:
        df: DataFrame to aggregate
        agg_dict: Dictionary of column: aggregation function
        subplot_key_col: Name of subplot key column

    Returns:
        Aggregated DataFrame
    """
    if df is None or len(df) == 0:
        return df

    if subplot_key_col not in df.columns:
        return df

    # Filter agg_dict to only include columns that exist
    valid_agg = {col: func for col, func in agg_dict.items() if col in df.columns}

    if not valid_agg:
        return df

    result = df.groupby(subplot_key_col).agg(valid_agg).reset_index()

    # Flatten column names if MultiIndex
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = ["_".join(col).strip("_") for col in result.columns.values]

    return result


def debug_enumerator_data(gdf, context=""):
    """
    Debug helper to check if enumerator data exists

    Args:
        gdf: GeoDataFrame to check
        context: Context string for debugging

    Returns:
        Boolean indicating if enumerator exists
    """

    if gdf is not None and len(gdf) > 0:
        print(f"Columns: {gdf.columns.tolist()}", file=sys.stderr)

        if "enumerator" in gdf.columns:
            unique_enums = gdf["enumerator"].nunique()
            print(
                f"✓ Enumerator column exists with {unique_enums} unique values",
                file=sys.stderr,
            )
            print(
                f"Sample values: {gdf['enumerator'].head().tolist()}", file=sys.stderr
            )
            return True
        else:
            print("✗ No enumerator column found", file=sys.stderr)
            return False
    else:
        print("✗ GDF is None or empty", file=sys.stderr)
        return False


def get_primary_species(df):
    """
    Get primary species from vegetation dataframe

    Args:
        df: Vegetation DataFrame

    Returns:
        DataFrame filtered for primary species
    """
    if df is None or len(df) == 0:
        return df

    if "vegetation_type_primary" not in df.columns:
        return df

    # Filter for primary species
    result = df[df["vegetation_type_primary"] == "yes_primary_group"].copy()

    return result


def get_species_counts(df, species_col="woody_species"):
    """
    Count species occurrences

    Args:
        df: Vegetation DataFrame
        species_col: Name of species column

    Returns:
        DataFrame with species counts
    """
    if df is None or len(df) == 0:
        return pd.DataFrame()

    if species_col not in df.columns:
        return pd.DataFrame()

    counts = df[species_col].value_counts().reset_index()
    counts.columns = ["species", "count"]

    return counts


def get_species_column(df: pd.DataFrame) -> Optional[str]:
    """
    Identify which species column is available and has data.

    Args:
        df: Dataframe to check

    Returns:
        Name of the species column with data, or None
    """
    species_cols = ["woody_species", "bamboo_species", "palm_species", "banana_species"]

    for col in species_cols:
        if col in df.columns and df[col].notna().any():
            return col

    return None


def add_tree_name_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a 'tree_name' column that is the union of all species columns.

    Logic:
    1. First check other_species (local tree name)
    2. Then check language_other_species (language field)
    3. Then check species columns (woody, bamboo, palm, banana, non_woody)
    4. Skip any values that are exactly "other"

    This ensures when woody_species="other", we use the actual tree name from
    other_species instead of the language field.

    Args:
        df: DataFrame with species columns

    Returns:
        DataFrame with tree_name column added
    """
    if df is None or len(df) == 0:
        return df

    result = df.copy()

    # Priority order: specific names first, then general species columns
    species_cols = [
        "other_species",           # Local name (highest priority for display)
        "language_other_species",  # Language field
        "non_woody_species",
        "woody_species",
        "bamboo_species",
        "banana_species",
        "palm_species",
    ]

    # Filter to only columns that exist in the dataframe
    available_cols = [col for col in species_cols if col in result.columns]

    if not available_cols:
        # No species columns found, return as-is
        return result

    # Initialize tree_name with None
    result["tree_name"] = None

    # Go through columns in priority order and fill tree_name
    for col in available_cols:
        # Create a mask for rows where tree_name is still None
        mask = result["tree_name"].isna()

        # For this column, get non-null values that are NOT "other"
        valid_values = result[col].notna() & (result[col] != "other")

        # Fill tree_name where it's None and we have a valid value
        result.loc[mask & valid_values, "tree_name"] = result.loc[mask & valid_values, col]

    return result
