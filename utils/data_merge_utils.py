"""
Data Merge Utilities
Common merge operations for handling enumerator assignments across all analysis pages
"""

import pandas as pd
from typing import Optional


def merge_with_enumerator(
    df: pd.DataFrame,
    filtered_gdf: pd.DataFrame,
    subplot_key_col: str = "SUBPLOT_KEY",
    drop_existing_enumerator: bool = True
) -> pd.DataFrame:
    """
    Merge any dataframe with enumerator information from filtered_gdf.
    
    This is a common operation needed when:
    - Raw data has an old/incorrect enumerator column
    - We need to use the filtered enumerator based on user selection
    
    Args:
        df: Source dataframe to merge
        filtered_gdf: GeoDataFrame with subplot_id and enumerator columns
        subplot_key_col: Column name in df that matches subplot_id in filtered_gdf
        drop_existing_enumerator: Whether to drop existing enumerator column before merge
        
    Returns:
        Merged dataframe with enumerator column from filtered_gdf
    """
    df = df.copy()
    
    # Drop existing enumerator to avoid _x/_y suffix issues
    if drop_existing_enumerator and "enumerator" in df.columns:
        df = df.drop(columns=["enumerator"])
    
    # Merge with filtered_gdf
    merged = df.merge(
        filtered_gdf[["subplot_id", "enumerator"]],
        left_on=subplot_key_col,
        right_on="subplot_id",
        how="left"
    )
    
    # Filter to only records with enumerator info
    merged = merged[merged["enumerator"].notna()]
    
    return merged


def calculate_tree_age(
    df: pd.DataFrame,
    year_planted_col: str = "tree_year_planted"
) -> pd.DataFrame:
    """
    Calculate tree age from planting year, handling datetime/numeric types.
    
    Args:
        df: Dataframe with tree planting year column
        year_planted_col: Column name containing planting year
        
    Returns:
        Dataframe with 'tree_age' column added
    """
    df = df.copy()
    current_year = pd.Timestamp.now().year
    
    if year_planted_col not in df.columns:
        df["tree_age"] = None
        return df
    
    # Handle different data types
    if pd.api.types.is_datetime64_any_dtype(df[year_planted_col]):
        # If datetime, extract year
        df["tree_age"] = current_year - df[year_planted_col].dt.year
    elif pd.api.types.is_numeric_dtype(df[year_planted_col]):
        # If numeric (year), use directly
        df["tree_age"] = current_year - df[year_planted_col]
    else:
        # Try to convert to datetime then extract year
        try:
            df["tree_age"] = current_year - pd.to_datetime(df[year_planted_col]).dt.year
        except:
            df["tree_age"] = None
    
    return df


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