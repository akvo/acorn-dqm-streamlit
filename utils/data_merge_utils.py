"""
Data Merge Utilities
Handles merging vegetation data with enumerator information and other utilities
"""

import pandas as pd
from datetime import datetime
from typing import Optional
import os
import re


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

    # Add SubmissionDate if it exists
    if "SubmissionDate" in filtered_gdf.columns:
        cols_to_merge.append("SubmissionDate")
    elif "starttime" in filtered_gdf.columns:
        cols_to_merge.append("starttime")

    # Extract only the columns we need
    merge_df = filtered_gdf[cols_to_merge].copy()

    # Prepare vegetation dataframe for merge
    veg_for_merge = veg_df.copy()

    # Ensure we have the key column
    if "SUBPLOT_KEY" in veg_for_merge.columns:
        veg_for_merge = veg_for_merge.rename(columns={"SUBPLOT_KEY": "subplot_id"})

    # Merge using inner join to only include vegetation from filtered subplots
    # This ensures date filters and other subplot filters are applied to vegetation data
    result = pd.merge(veg_for_merge, merge_df, on="subplot_id", how="inner")

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
    mask = (result[date_col].dt.date >= start_date) & (result[date_col].dt.date <= end_date)
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
        return "enumerator" in gdf.columns
    else:
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
    Add a 'tree_name' column using first non-empty species column value.

    Logic:
    1. Check woody species columns (woody_spec, woody_species)
    2. Check bamboo species columns (bamboo_spec, bamboo_species)
    3. Check banana species columns (banana_spec, banana_species)
    4. Check palm_species
    5. Check living_fences
    6. "other" is a valid species name (NOT skipped)

    Args:
        df: DataFrame with species columns

    Returns:
        DataFrame with tree_name column added
    """
    if df is None or len(df) == 0:
        return df

    result = df.copy()

    # Species columns in priority order (woody trees only)
    species_cols = [
        "woody_spec",
        "woody_species",
        "bamboo_spec",
        "bamboo_species",
        "banana_spec",
        "banana_species",
        "palm_species",
        "living_fences",
    ]

    # Filter to only columns that exist in the dataframe
    available_cols = [col for col in species_cols if col in result.columns]

    if not available_cols:
        # No species columns found, return as-is
        result["tree_name"] = "Unknown"
        return result

    def get_first_species(row):
        tree_name = "Unknown"
        for col in available_cols:
            val = row.get(col)
            if pd.notna(val) and str(val).strip():
                tree_name = str(val).strip()
                break

        # If tree_name is "other", enhance with other_species and language_other_species
        if tree_name.lower() == "other":
            other_sp = row.get("other_species", "")
            lang_other = row.get("language_other_species", "")
            if pd.notna(other_sp) and str(other_sp).strip():
                tree_name = f"other: {other_sp}"
                if pd.notna(lang_other) and str(lang_other).strip():
                    tree_name += f" ({lang_other})"
            elif pd.notna(lang_other) and str(lang_other).strip():
                tree_name = f"other ({lang_other})"

        return tree_name

    result["tree_name"] = result.apply(get_first_species, axis=1)

    return result


def load_species_lookup(partner: str) -> tuple:
    """
    Load all species TSV files and create lookup dicts.

    Args:
        partner: Partner name (subdirectory under data/species/)

    Returns:
        - scientific_to_label: dict mapping scientific name to label
        - common_to_label: dict mapping normalized common names to label
    """
    scientific_to_label = {}
    common_to_label = {}
    species_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "species", partner)

    species_files = [
        "woody_species.tsv",
        "bamboo_species.tsv",
        "banana_species.tsv",
        "palm_species.tsv",
        "living_fences_species.tsv",
    ]

    def normalize_text(text):
        """Normalize text for matching: lowercase, remove extra spaces, strip."""
        if not text:
            return ""
        # Lowercase, strip, collapse multiple spaces
        text = re.sub(r"\s+", " ", str(text).strip().lower())
        return text

    for filename in species_files:
        filepath = os.path.join(species_dir, filename)
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, sep="\t")
                if "value" in df.columns and "label" in df.columns:
                    for _, row in df.iterrows():
                        val = str(row["value"]).strip().lower()
                        label = str(row["label"]).strip()
                        if val and label:
                            scientific_to_label[val] = label
                            # Also add common names from label (split by /)
                            for part in label.split("/"):
                                normalized = normalize_text(part)
                                if normalized:
                                    common_to_label[normalized] = label
                                    # Also add without spaces for fuzzy matching
                                    common_to_label[normalized.replace(" ", "")] = label
            except Exception:
                pass

    return scientific_to_label, common_to_label


def normalize_species_name(row, scientific_lookup: dict, common_lookup: dict) -> str:
    """
    Normalize species name by:
    1. Using woody_species if available and not "other"
    2. If "other", check other_species/language_other_species against TSV lookup
    3. Match against both scientific names and common names
    4. Return normalized name for grouping

    Args:
        row: DataFrame row
        scientific_lookup: Dict mapping scientific names to labels
        common_lookup: Dict mapping common names to labels

    Returns:
        Normalized species name string
    """

    def normalize_text(text):
        """Normalize text for matching: lowercase, remove extra spaces, strip."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", str(text).strip().lower())

    species = row.get("woody_species", "")

    if pd.notna(species) and str(species).strip().lower() != "other":
        # Check if it's in lookup (for label display)
        key = str(species).strip().lower().replace(" ", "_")
        return scientific_lookup.get(key, str(species).strip())

    # Handle "other" case - look up other_species in TSV
    other_sp = row.get("other_species", "")
    if pd.notna(other_sp) and str(other_sp).strip():
        other_text = normalize_text(other_sp)

        # Try scientific name lookup first
        key = other_text.replace(" ", "_")
        if key in scientific_lookup:
            return scientific_lookup[key]

        # Try common name lookup (with spaces)
        if other_text in common_lookup:
            return common_lookup[other_text]

        # Try common name lookup (without spaces for "sweetlime" vs "sweet lime")
        no_space = other_text.replace(" ", "")
        if no_space in common_lookup:
            return common_lookup[no_space]

        # No match found - return as "other" but normalized
        return f"other: {other_text}"

    # Check language_other_species
    lang_other = row.get("language_other_species", "")
    if pd.notna(lang_other) and str(lang_other).strip():
        lang_text = normalize_text(lang_other)

        # Try common name lookup
        if lang_text in common_lookup:
            return common_lookup[lang_text]

        no_space = lang_text.replace(" ", "")
        if no_space in common_lookup:
            return common_lookup[no_space]

        return f"other ({lang_text})"

    return "other (unknown)"


def detect_species_outliers(df, metric_col, species_col="normalized_species", multiplier=4):
    """
    Detect outliers based on species median.

    Args:
        df: DataFrame with species and metric columns
        metric_col: Name of the metric column to check (e.g., tree_height_m)
        species_col: Name of the normalized species column
        multiplier: Threshold multiplier (default 4x median for upper, 0.25x for lower)

    Returns:
        DataFrame with outlier flags and median values, or empty DataFrame if no valid data
    """
    if metric_col not in df.columns or species_col not in df.columns:
        return pd.DataFrame()

    # Filter to valid data
    valid_data = df[df[metric_col].notna() & df[species_col].notna()].copy()

    if len(valid_data) == 0:
        return pd.DataFrame()

    # Calculate median per species
    species_median = valid_data.groupby(species_col)[metric_col].median().reset_index(name="species_median")

    # Merge with original data
    result = pd.merge(valid_data, species_median, on=species_col, how="left")

    # Flag outliers (>4x or <0.25x median)
    result["is_upper_outlier"] = result[metric_col] > (result["species_median"] * multiplier)
    result["is_lower_outlier"] = result[metric_col] < (result["species_median"] / multiplier)
    result["is_outlier"] = result["is_upper_outlier"] | result["is_lower_outlier"]

    return result


def detect_multivariate_outliers_dbscan(
    df,
    metric_col,
    species_col="normalized_species",
    age_col="tree_age",
    eps=0.5,
    min_samples=3,
):
    """
    Detect outliers using DBSCAN clustering on age + one metric.
    Runs per-species to respect natural variation between species.

    Args:
        df: DataFrame with species and measurement columns
        metric_col: The physical attribute column (tree_height_m, circumference_bh, or nr_stems_bh)
        species_col: Column for species grouping
        age_col: Tree age column
        eps: DBSCAN epsilon (max distance between points in cluster)
        min_samples: DBSCAN min points to form a cluster

    Returns:
        DataFrame with is_outlier flag (-1 cluster = outlier)
    """
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import StandardScaler

    required_cols = [species_col, metric_col, age_col]
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame()

    # Filter to rows with all required values
    valid_data = df[df[metric_col].notna() & df[age_col].notna() & df[species_col].notna()].copy()

    if len(valid_data) == 0:
        return pd.DataFrame()

    # Process each species separately
    all_results = []

    for species in valid_data[species_col].unique():
        species_data = valid_data[valid_data[species_col] == species].copy()

        # Need at least min_samples for DBSCAN to work
        if len(species_data) < min_samples:
            # Too few samples - mark none as outliers
            species_data["dbscan_cluster"] = 0
            species_data["is_outlier"] = False
            all_results.append(species_data)
            continue

        # Extract 2 features: age + selected metric
        features = species_data[[age_col, metric_col]].values

        # Normalize features
        scaler = StandardScaler()
        features_scaled = scaler.fit_transform(features)

        # Run DBSCAN
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        clusters = dbscan.fit_predict(features_scaled)

        # -1 means outlier (noise point)
        species_data["dbscan_cluster"] = clusters
        species_data["is_outlier"] = clusters == -1

        all_results.append(species_data)

    if not all_results:
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True)


def detect_regression_outliers(
    df,
    metric_col,
    species_col="normalized_species",
    age_col="tree_age",
    std_threshold=2.0,
    min_samples=10,
):
    """
    Detect outliers using linear regression per species.
    Fits age vs metric, flags points beyond N standard deviations from predicted.

    Args:
        df: DataFrame with species and measurement columns
        metric_col: The physical attribute column (tree_height_m, circumference_bh, or nr_stems_bh)
        species_col: Column for species grouping
        age_col: Tree age column
        std_threshold: Number of standard deviations to define outlier zone
        min_samples: Minimum samples needed to fit regression (default 10)

    Returns:
        DataFrame with predicted values, residuals, valid range, and is_outlier flag
    """
    from sklearn.linear_model import LinearRegression
    import numpy as np

    required_cols = [species_col, metric_col, age_col]
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame()

    # Filter to rows with all required values
    valid_data = df[df[metric_col].notna() & df[age_col].notna() & df[species_col].notna()].copy()

    if len(valid_data) == 0:
        return pd.DataFrame()

    # Process each species separately (only species with > min_samples)
    all_results = []

    for species in valid_data[species_col].unique():
        species_data = valid_data[valid_data[species_col] == species].copy()

        # Skip species with insufficient samples (need > 10 for meaningful regression)
        if len(species_data) <= min_samples:
            continue

        # Fit linear regression: metric = b0 + b1 * age
        X = species_data[[age_col]].values
        y = species_data[metric_col].values

        model = LinearRegression()
        model.fit(X, y)
        predicted = model.predict(X)

        # Calculate residuals
        residuals = y - predicted
        std_residual = np.std(residuals) if len(residuals) > 1 else 1.0

        # Store results
        species_data["predicted"] = predicted
        species_data["residual"] = residuals
        species_data["std_residual"] = std_residual

        # Calculate valid range (prediction interval)
        # Lower bound clamped to 0 since physical attributes can't be negative
        margin = std_threshold * std_residual
        species_data["valid_range_lower"] = np.maximum(0, predicted - margin)
        species_data["valid_range_upper"] = predicted + margin

        # Flag outliers (beyond threshold standard deviations)
        species_data["is_outlier"] = np.abs(residuals) > margin

        all_results.append(species_data)

    if not all_results:
        return pd.DataFrame()

    return pd.concat(all_results, ignore_index=True)


def detect_age_species_outliers(
    df,
    metric_col,
    species_col="normalized_species",
    age_col="tree_age",
    std_multiplier=3.0,
    stem_upper_multiplier=4.0,
    min_group_size=3,
):
    """
    Detect outliers by grouping trees by species AND age.

    Uses different methods based on metric type:
    - Height/Circumference: Mean ± 3 standard deviations
    - Stem count: 4x median (with lower bound of 1)

    Args:
        df: DataFrame with species, age, and measurement columns
        metric_col: The physical attribute column (tree_height_m, circumference_bh, or nr_stems_bh)
        species_col: Column for species grouping
        age_col: Tree age column
        std_multiplier: Number of standard deviations for height/circumference (default 3)
        stem_upper_multiplier: Upper multiplier for stem count (default 4x median)
        min_group_size: Minimum trees in a group to calculate stats (default 3)

    Returns:
        DataFrame with group stats, valid_range, and is_outlier flag
    """
    required_cols = [species_col, metric_col, age_col]
    if not all(col in df.columns for col in required_cols):
        return pd.DataFrame()

    # Filter to rows with all required values
    valid_data = df[df[metric_col].notna() & df[age_col].notna() & df[species_col].notna()].copy()

    if len(valid_data) == 0:
        return pd.DataFrame()

    # Use different approach based on metric type
    if metric_col == "nr_stems_bh":
        # Stem count: Use median-based approach (4x median, lower bound = 1)
        group_stats = valid_data.groupby([species_col, age_col])[metric_col].agg(["median", "count"]).reset_index()
        group_stats.columns = [species_col, age_col, "group_median", "group_count"]

        result = pd.merge(valid_data, group_stats, on=[species_col, age_col], how="left")

        # Valid range: 1 to 4x median
        result["valid_range_lower"] = 1.0
        result["valid_range_upper"] = result["group_median"] * stem_upper_multiplier

    else:
        # Height/Circumference: Use mean ± 3 standard deviations
        group_stats = valid_data.groupby([species_col, age_col])[metric_col].agg(["mean", "std", "count"]).reset_index()
        group_stats.columns = [species_col, age_col, "group_mean", "group_std", "group_count"]

        # Fill NaN std with 0 (happens when group has only 1 value)
        group_stats["group_std"] = group_stats["group_std"].fillna(0)

        result = pd.merge(valid_data, group_stats, on=[species_col, age_col], how="left")

        # Valid range: mean ± 3 SD (clamped to 0 for lower bound)
        result["valid_range_lower"] = (result["group_mean"] - std_multiplier * result["group_std"]).clip(lower=0)
        result["valid_range_upper"] = result["group_mean"] + std_multiplier * result["group_std"]

        # Rename for consistent display
        result["group_median"] = result["group_mean"]

    # Flag outliers - only for groups with enough samples
    result["is_outlier"] = False
    has_enough_samples = result["group_count"] >= min_group_size

    result.loc[has_enough_samples, "is_outlier"] = (
        result.loc[has_enough_samples, metric_col] > result.loc[has_enough_samples, "valid_range_upper"]
    ) | (result.loc[has_enough_samples, metric_col] < result.loc[has_enough_samples, "valid_range_lower"])

    return result
