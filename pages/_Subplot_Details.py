"""
Subplot Details Page - Vegetation Quality Checks (Error-Focused)
Based on Vegetation_checks.ipynb logic
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import config
from ui.components import (
    show_header,
    create_sidebar_filters,
    show_sidebar_info,
    get_total_measured_subplots,
    require_auth,
)
from utils.data_merge_utils import (
    merge_with_enumerator,
    calculate_tree_age,
    get_species_column,
    add_tree_name_column,
    load_species_lookup,
    normalize_species_name,
    detect_species_outliers,
    detect_age_species_outliers,
)
from utils.vegetation_validation import (
    get_missing_subplots,
    get_young_trees_with_other,
    get_primary_trees_with_other,
    get_non_primary_trees_with_other,
    detect_stem_outliers,
    detect_suspicious_circumference_by_age,
)
from utils.export_helpers import adjust_excel_column_widths
from utils.session_manager import load_data
import os

# Try to import fuzzy matching library
try:
    from rapidfuzz import fuzz, process

    FUZZY_AVAILABLE = True
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process

        FUZZY_AVAILABLE = True
    except ImportError:
        FUZZY_AVAILABLE = False


# Page config
st.set_page_config(
    page_title="Subplot Details - Ground Truth DQM",
    page_icon="🌳",
    layout="wide",
)

# Refresh partner config from URL
config.refresh_partner_config()

# Authentication check
require_auth()

# Check if data exists (using persistent data store)
data = load_data("gt")
if data is None:
    st.warning("⚠️ No data loaded. Please load data from the home page.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
    st.stop()
st.session_state.data = data  # Ensure session state is in sync

# Header
show_header()

st.markdown("## 🌳 Subplot Details & Vegetation Quality Checks")
st.caption(
    "Comprehensive data quality checks for vegetation records. Use the sidebar filters to narrow down by date range or enumerator. Each section highlights potential issues that may require field verification or data correction."
)

# Page-level documentation
with st.expander("📖 Page Documentation", expanded=False):
    st.markdown("""
**Purpose:** Error-focused vegetation quality analysis with adjustable thresholds.

**Data Flow:** Sidebar filters (date, enumerator) → filtered subplots → validation checks applied to vegetation/measurement data.

**Key Methodology:** VEGETATION_KEY grouping (Rabobank) — trees planted together should have similar measurements. Outlier threshold: >4x or <0.25x group median.

**Thresholds:** Adjustable via sidebar (stem count, tall tree height, young tree circumference, fuzzy match %).
    """)

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# Apply filters first (shows date filter at top)
filtered_gdf = create_sidebar_filters(gdf_subplots)

# Show sidebar info (partner and data status)
show_sidebar_info()

# Check if vegetation data is available
has_vegetation = "plots_subplots_vegetation" in raw_data
has_measurements = "plots_subplots_vegetation_measurements" in raw_data
has_complete = "complete" in raw_data

if not has_vegetation:
    st.error("❌ Vegetation data not available. Upload complete Excel file with all 5 sheets.")
    st.stop()

st.markdown("---")

# ============================================
# GET AND MERGE DATA
# ============================================

# Get raw data
plots_df_all = raw_data.get("plots_subplots", pd.DataFrame())
veg_df_all = raw_data["plots_subplots_vegetation"].copy()
meas_df_all = (
    raw_data.get("plots_subplots_vegetation_measurements", pd.DataFrame()) if has_measurements else pd.DataFrame()
)
complete_df_all = raw_data.get("complete", pd.DataFrame()) if has_complete else pd.DataFrame()

# Filter data based on date/enumerator filters applied to filtered_gdf
# Get the subplot_ids that passed the filters
filtered_subplot_ids = filtered_gdf["subplot_id"].unique() if "subplot_id" in filtered_gdf.columns else []

if len(filtered_subplot_ids) > 0:
    # Filter plots_df to only include subplots from filtered_gdf
    if "SUBPLOT_KEY" in plots_df_all.columns:
        plots_df = plots_df_all[plots_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
    else:
        plots_df = plots_df_all.copy()

    # Filter veg_df to only include vegetation from filtered subplots
    if "SUBPLOT_KEY" in veg_df_all.columns:
        veg_df = veg_df_all[veg_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
    else:
        veg_df = veg_df_all.copy()

    # Filter meas_df to only include measurements from filtered subplots
    if has_measurements and "SUBPLOT_KEY" in meas_df_all.columns:
        meas_df = meas_df_all[meas_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
    else:
        meas_df = meas_df_all.copy() if has_measurements else pd.DataFrame()

    # Filter complete_df to only include data from filtered subplots
    if has_complete and "SUBPLOT_KEY" in complete_df_all.columns:
        complete_df = complete_df_all[complete_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
    else:
        complete_df = complete_df_all.copy() if has_complete else pd.DataFrame()
else:
    # No filter applied, use all data
    plots_df = plots_df_all.copy()
    veg_df = veg_df_all.copy()
    meas_df = meas_df_all.copy() if has_measurements else pd.DataFrame()
    complete_df = complete_df_all.copy() if has_complete else pd.DataFrame()

# Merge with enumerator (for filtered analysis)
veg_with_enum = merge_with_enumerator(veg_df, filtered_gdf)
veg_with_enum = add_tree_name_column(veg_with_enum)

if has_measurements:
    meas_with_enum = merge_with_enumerator(meas_df, filtered_gdf)
    meas_with_enum = add_tree_name_column(meas_with_enum)
else:
    meas_with_enum = pd.DataFrame()

# Get species column (still needed for some checks)
species_col = get_species_column(veg_with_enum)

# ============================================
# SIDEBAR: QUALITY THRESHOLDS
# ============================================

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Quality Thresholds")
st.sidebar.caption("Thresholds for various data quality checks")

st.sidebar.info(
    """
    **Outlier Detection Method:**
    Height & Circumference outliers use **VEGETATION_KEY grouping** (Rabobank methodology).
    - Trees in same group → compared to group median
    - Fixed thresholds: **4x** and **0.25x**
    """
)

stem_threshold = st.sidebar.slider(
    "High Stem Count",
    min_value=10,
    max_value=50,
    value=20,
    help="Flag trees with nr_stems_bh > threshold",
)

tall_tree_threshold = st.sidebar.slider(
    "Super Tall Tree Height (m)",
    min_value=15,
    max_value=50,
    value=25,
    step=1,
    help="Flag exceptionally tall trees - important for age verification",
)

young_tree_circ = st.sidebar.number_input(
    "Young Tree Circ Threshold (cm)",
    min_value=30,
    max_value=100,
    value=50,
    help="Suspicious if circ > this AND age < 5 years",
)


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


def calculate_tree_age_corrected(df, year_column="tree_year_planted"):
    """
    Calculate tree age from planting year
    Handles epoch timestamps, direct years, and date strings

    Parameters:
    - df: DataFrame
    - year_column: Column name containing planting year/date

    Returns: DataFrame with 'tree_age' column added
    """
    if year_column not in df.columns:
        return df

    current_year = datetime.now().year

    # Extract year (handles multiple formats)
    planted_years = extract_year_from_planted(df[year_column])

    # Calculate age
    df["tree_age"] = current_year - planted_years

    return df


# ============================================

# TABS
# ============================================

tabs = st.tabs(
    [
        "📏 Measurements",
        "⚠️ Outliers & Suspicious",
        "🚫 Missing Data",
        "🌲 Tree Classification",
    ]
)

# ============================================
# TAB 3: MISSING DATA
# ============================================

with tabs[2]:
    st.markdown("### 🚫 Missing Vegetation and Measurement Data")
    st.caption(
        "Identifies gaps in data collection. Subplots without vegetation records may indicate incomplete surveys. Vegetation records without measurements may indicate trees that were recorded but not measured. These gaps should be addressed during field revisits or data reconciliation."
    )

    # FILTER veg_df to only actual vegetation (non-null VEGETATION_KEY)
    # This is needed if data_processor uses LEFT JOIN
    if "VEGETATION_KEY" in veg_df.columns:
        veg_df_actual = veg_df[veg_df["VEGETATION_KEY"].notna()].copy()
    else:
        veg_df_actual = veg_df.copy()

    # CHECK 1: Missing vegetation records
    st.markdown("#### 1️⃣ Subplots WITHOUT Vegetation Records")

    st.info(
        """
        **How Missing Vegetation is Calculated:**
        1. **Apply filters**: Date range and enumerator filters from sidebar
        2. **Get filtered subplots**: From the plots/subplots data (reference list)
        3. **Get subplots with vegetation**: From the vegetation records data
        4. **Find the difference**: Subplots in reference list but NOT in vegetation data

        **Formula**: `Missing = Filtered Subplots - Subplots with Vegetation`

        ⚠️ **Note**: This respects your date range filter in the sidebar. Only subplots from the selected
        date range are checked. These subplots were created but have NO vegetation records at all.
        Check the comments to see if enumerators noted a reason (e.g., "No trees", "Access denied", etc.).
        """
    )

    # Filter plots_df to only include MEASURED subplots
    # This ensures we don't count unmeasured subplots as "missing vegetation"
    if "SUBPLOT_KEY" in plots_df.columns and "measured_subplots" in plots_df.columns:
        import re

        # Create temporary dataframe with subplot info
        temp_plots = plots_df.copy()

        # Extract subplot number from SUBPLOT_KEY (e.g., "uuid.../sub_plot[12]" -> 12)
        temp_plots["subplot_number"] = temp_plots["SUBPLOT_KEY"].apply(
            lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
        )

        # Convert measured_subplots to int
        temp_plots["measured_subplots"] = temp_plots["measured_subplots"].apply(
            lambda x: int(x) if pd.notna(x) else 999
        )

        # Only include subplots where subplot_number <= measured_subplots
        plots_df_measured = temp_plots[temp_plots["subplot_number"] <= temp_plots["measured_subplots"]].copy()

        # Drop temporary columns
        plots_df_measured = plots_df_measured.drop(columns=["subplot_number"], errors="ignore")
    else:
        # Fallback: use all plots_df
        plots_df_measured = plots_df.copy()

    # Use utility function with filtered veg_df and measured plots only
    missing_veg = get_missing_subplots(plots_df_measured, veg_df_actual)

    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("Missing Vegetation", len(missing_veg))

    if len(missing_veg) > 0:
        st.error(f"❌ {len(missing_veg)} subplots have NO vegetation records")

        # Display columns from notebook: enumerator, SUBPLOT_KEY, subplot_comments
        col_missing_df = ["enumerator", "SUBPLOT_KEY", "subplot_comments"]

        # Filter to only columns that exist
        display_cols = [col for col in col_missing_df if col in missing_veg.columns]

        if len(display_cols) == 0:
            st.warning("⚠️ No display columns available. Available columns:")
            st.write(missing_veg.columns.tolist())
            st.dataframe(missing_veg.head(), use_container_width=True)
        else:
            # Add row numbers starting from 1
            display_df = missing_veg[display_cols].copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))

            st.dataframe(
                display_df,
                use_container_width=True,
                height=min(400, len(missing_veg) * 35 + 38),
                hide_index=True,
            )
    else:
        st.success("✅ All subplots have vegetation records")

    st.markdown("---")

    # CHECK 4: Tree Density and Coverage Analysis
    st.markdown("#### 2️⃣ Subplot Tree Density & Coverage")
    st.caption(
        "Identifies subplots with zero trees. 'Coverage-Only' subplots have vegetation records but no trees (e.g., grass/crops). 'Empty' subplots have no records at all and may indicate missed data collection."
    )

    # IMPORTANT: Start with ALL subplots from geometry (176), not just those with vegetation (162)
    # This ensures we count empty subplots as coverage-only
    density_parameters = [
        "enumerator",
        "SUBPLOT_KEY",
        "vegetation_type_number",
        "coverage_vegetation",
        "subplot_comments",
    ]

    # Check if all columns exist
    available_cols = [col for col in density_parameters if col in veg_df_actual.columns]

    if len(available_cols) >= 3:  # Need at least SUBPLOT_KEY, vegetation_type_number, coverage_vegetation
        # Create base with ONLY MEASURED subplots (exclude unmeasured subplots)
        # Extract subplot number from subplot_id and compare to measured_subplots
        if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
            import re

            # Create temporary dataframe with subplot info
            temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()

            # Extract subplot number from subplot_id (e.g., "uuid.../sub_plot[12]" -> 12)
            temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
            )

            # Convert measured_subplots to int
            temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)

            # Only include subplots where subplot_number <= measured_subplots
            measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]][
                "subplot_id"
            ].unique()

            all_subplots_df = pd.DataFrame({"SUBPLOT_KEY": measured_subplot_ids})
        else:
            # Fallback: use all subplot keys
            all_subplot_keys = filtered_gdf["subplot_id"].unique() if "subplot_id" in filtered_gdf.columns else []
            all_subplots_df = pd.DataFrame({"SUBPLOT_KEY": all_subplot_keys})

        # Left join with vegetation data (keeps all 176 subplots, fills missing with NaN)
        density = all_subplots_df.merge(veg_df_actual[available_cols], on="SUBPLOT_KEY", how="left")

        # Ensure numeric columns are properly typed (avoid string concatenation on sum)
        if "coverage_vegetation" in density.columns:
            density["coverage_vegetation"] = pd.to_numeric(density["coverage_vegetation"], errors="coerce").fillna(0)
        if "vegetation_type_number" in density.columns:
            density["vegetation_type_number"] = pd.to_numeric(
                density["vegetation_type_number"], errors="coerce"
            ).fillna(0)

        # Group by subplot
        agg_dict = {}
        if "vegetation_type_number" in density.columns:
            # sum() treats NaN as 0, which is what we want
            # Both coverage-only (NULL) and empty subplots will sum to 0
            agg_dict["vegetation_type_number"] = "sum"
        if "coverage_vegetation" in density.columns:
            agg_dict["coverage_vegetation"] = "sum"
        if "enumerator" in density.columns:
            agg_dict["enumerator"] = "unique"
        if "subplot_comments" in density.columns:
            agg_dict["subplot_comments"] = "unique"

        density_df = density.groupby("SUBPLOT_KEY").agg(agg_dict).reset_index()

        # Subplots with 0 trees - includes both coverage-only AND empty subplots
        # Must check BOTH == 0 AND isna() because pandas sum can return NaN for all-NaN groups
        subplots_zero_trees = density_df[
            (density_df["vegetation_type_number"] == 0) | (density_df["vegetation_type_number"].isna())
        ].copy()

        # Distinguish between:
        # 1. Coverage-only: Have vegetation records but 0 trees
        # 2. Empty: Have NO vegetation records at all
        subplots_with_records = set(veg_df_actual["SUBPLOT_KEY"].unique())

        # Coverage-only: in veg_df_actual AND have 0/NaN trees
        subplots_coverage = subplots_zero_trees[subplots_zero_trees["SUBPLOT_KEY"].isin(subplots_with_records)].copy()

        # Empty: NOT in veg_df_actual (no records at all)
        subplots_empty = subplots_zero_trees[~subplots_zero_trees["SUBPLOT_KEY"].isin(subplots_with_records)].copy()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Subplots Analyzed", get_total_measured_subplots(filtered_gdf))
        with col2:
            st.metric("Subplots with 0 Trees", len(subplots_zero_trees))
        with col3:
            st.metric("Coverage-Only", len(subplots_coverage))
        with col4:
            st.metric("Empty (No Data)", len(subplots_empty))

        # Show coverage-only subplots
        if len(subplots_coverage) > 0:
            st.info(f"ℹ️ {len(subplots_coverage)} subplots have coverage data but no trees")

            with st.expander("View coverage-only subplots"):
                display_cols = [
                    col
                    for col in [
                        "SUBPLOT_KEY",
                        "enumerator",
                        "coverage_vegetation",
                        "subplot_comments",
                    ]
                    if col in subplots_coverage.columns
                ]

                # Add row numbers
                display_df = subplots_coverage[display_cols].copy()
                display_df.insert(0, "#", range(1, len(display_df) + 1))

                st.dataframe(display_df, use_container_width=True, height=300, hide_index=True)

        # Show empty subplots
        if len(subplots_empty) > 0:
            st.warning(f"⚠️ {len(subplots_empty)} subplots have NO vegetation data collected")

            with st.expander("View empty subplots"):
                display_df = subplots_empty[["SUBPLOT_KEY"]].copy()
                display_df.insert(0, "#", range(1, len(display_df) + 1))

                st.dataframe(display_df, use_container_width=True, height=300, hide_index=True)

        # Show full density table
        with st.expander("View all subplot density data"):
            # Add row numbers
            display_df = density_df.copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))
            st.dataframe(display_df, use_container_width=True, height=400, hide_index=True)

    else:
        st.error("❌ Required columns not found for density analysis")
        st.write(f"Available columns: {veg_df_actual.columns.tolist()[:20]}")

    st.markdown("---")

    # CHECK 2: Coverage-only subplots with measurements (potential data quality issue)
    st.markdown("#### 3️⃣ Coverage-Only Subplots with Measurements")
    st.caption(
        "Data consistency check: Subplots recorded as 100% coverage (no trees) should not have tree measurements. If measurements exist, the enumerator may have initially recorded trees then changed to coverage-only, or vice versa. These records need review to determine the correct classification."
    )

    if has_measurements:
        # Coverage-only subplots: subplots with vegetation records but 0 trees
        coverage_only = pd.DataFrame()

        if "vegetation_type_number" in veg_df_actual.columns:
            # Coverage-only means: subplot has vegetation records but ALL have NULL vegetation_type_number
            veg_check = (
                veg_df_actual.groupby("SUBPLOT_KEY")["vegetation_type_number"]
                .agg([("has_trees", lambda x: x.notna().any())])
                .reset_index()
            )

            # Coverage-only = has_trees is False
            coverage_only_keys = veg_check[~veg_check["has_trees"]]["SUBPLOT_KEY"]

            # Get coverage-only subplots with key columns
            if len(coverage_only_keys) > 0:
                coverage_only = (
                    veg_df_actual[veg_df_actual["SUBPLOT_KEY"].isin(coverage_only_keys)]
                    .drop_duplicates(subset=["SUBPLOT_KEY"])[
                        ["SUBPLOT_KEY", "enumerator"] if "enumerator" in veg_df_actual.columns else ["SUBPLOT_KEY"]
                    ]
                    .copy()
                )

            # Merge with enumerator if not already present
            if len(coverage_only) > 0 and "enumerator" not in coverage_only.columns:
                coverage_only = merge_with_enumerator(coverage_only, filtered_gdf)
        else:
            coverage_only = pd.DataFrame()

        # Missing measurements calculation (using filtered data)
        if has_measurements and len(meas_df) > 0:
            # Filter to records that have MEASUREMENT_KEY (actual measurements)
            if "MEASUREMENT_KEY" in meas_df.columns:
                m_with_meas = meas_df[meas_df["MEASUREMENT_KEY"].notna()].copy()
                veg_mea = set(m_with_meas["SUBPLOT_KEY"].unique())
            else:
                veg_mea = set()
        else:
            # Fallback: Do INNER JOIN ourselves
            if "VEGETATION_KEY" in veg_df_actual.columns and "VEGETATION_KEY" in meas_df.columns:
                m_mea_temp = veg_df_actual.merge(
                    meas_df[["VEGETATION_KEY"]].drop_duplicates(),
                    on="VEGETATION_KEY",
                    how="inner",
                )
                veg_mea = set(m_mea_temp["SUBPLOT_KEY"].unique())
            else:
                veg_mea = set()

        # All subplots with vegetation
        reference_veg = set(veg_df_actual["SUBPLOT_KEY"].unique())

        # Subplots missing measurements
        missing_veg_keys = reference_veg - veg_mea

        # Get one record per missing subplot for display
        missing_veg_df = (
            veg_df_actual[veg_df_actual["SUBPLOT_KEY"].isin(missing_veg_keys)]
            .drop_duplicates(subset=["SUBPLOT_KEY"])[
                ["SUBPLOT_KEY", "enumerator"] if "enumerator" in veg_df_actual.columns else ["SUBPLOT_KEY"]
            ]
            .copy()
        )

        # MAIN CHECK: Coverage-only subplots that DO NOT match missing measurements
        # These are subplots marked as coverage-only but actually have measurements
        if len(coverage_only) > 0 and len(missing_veg_df) > 0:
            veg_reverted = coverage_only[~coverage_only["SUBPLOT_KEY"].isin(missing_veg_df["SUBPLOT_KEY"])].copy()
        else:
            veg_reverted = pd.DataFrame()

        # Display the reverted subplots
        st.metric("Coverage-Only with Measurements", len(veg_reverted))

        if len(veg_reverted) > 0:
            st.warning(
                f"⚠️ Found {len(veg_reverted)} subplot(s) marked as 100% coverage but have measurements. "
                "This suggests data was changed after initial collection."
            )

            display_cols = [col for col in ["SUBPLOT_KEY", "enumerator"] if col in veg_reverted.columns]

            # Add row numbers
            display_df = veg_reverted[display_cols].copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))

            st.dataframe(
                display_df,
                use_container_width=True,
                height=300,
                hide_index=True,
            )
        else:
            st.success("✅ All coverage-only subplots correctly match missing measurements")
    else:
        st.info("ℹ️ Measurement data not available")

# ============================================
# TAB 4: TREE CLASSIFICATION
# ============================================

with tabs[3]:
    st.markdown("### 🌲 Tree Classification & Species Registry")
    st.caption(
        "Analyzes species entered as 'other' (free-text) to improve data quality and expand the species registry. The first section matches manually-entered species against existing registry entries. The second aggregates frequently reported species that may need to be added to the official TSV lists."
    )

    # Get tree lists using utility functions on RAW data
    primary_trees = get_primary_trees_with_other(veg_df, primary_value="yes_primary_group")
    non_primary_trees = get_non_primary_trees_with_other(veg_df, non_primary_value="no")
    young_trees_other = get_young_trees_with_other(veg_df, young_tree_value="yes_groupbelow1.3")

    # Merge with enumerator and add tree_name
    if len(young_trees_other) > 0:
        young_trees_other = merge_with_enumerator(young_trees_other, filtered_gdf)
        young_trees_other = add_tree_name_column(young_trees_other)
    if len(primary_trees) > 0:
        primary_trees = merge_with_enumerator(primary_trees, filtered_gdf)
        primary_trees = add_tree_name_column(primary_trees)
    if len(non_primary_trees) > 0:
        non_primary_trees = merge_with_enumerator(non_primary_trees, filtered_gdf)
        non_primary_trees = add_tree_name_column(non_primary_trees)

    # ============================================
    # 1. FUZZY MATCHING FOR "OTHER" SPECIES AGAINST REGISTRY
    # ============================================

    st.markdown("### 🔍 Potential Species Matches (Fuzzy)")
    st.caption(
        "When enumerators enter species as 'other' with a free-text name, this check compares those entries against the partner's species registry (TSV files). High-confidence matches suggest the species already exists in the list and enumerators should be trained to select it directly instead of typing manually."
    )

    if not FUZZY_AVAILABLE:
        st.warning("Fuzzy matching library not available. Install 'rapidfuzz' to enable this feature.")
    else:
        # Use complete_df which has enumerator already merged
        if has_complete and len(complete_df) > 0 and "woody_species" in complete_df.columns:
            all_other_trees = complete_df[
                complete_df["woody_species"].fillna("").str.lower().str.strip() == "other"
            ].copy()
        else:
            all_other_trees = pd.concat([primary_trees, non_primary_trees, young_trees_other], ignore_index=True)

        if len(all_other_trees) == 0:
            st.info("No 'other' species entries found to match")
        else:
            # Load species reference files
            import os

            species_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "species", config.PARTNER)

            all_valid_species = []

            for tsv_file in [
                "woody_species.tsv",
                "bamboo_species.tsv",
                "banana_species.tsv",
                "palm_species.tsv",
                "living_fences_species.tsv",
            ]:
                try:
                    filepath = os.path.join(species_dir, tsv_file)
                    if os.path.exists(filepath):
                        ref_df = pd.read_csv(filepath, sep="\t")
                        all_valid_species.extend(list(ref_df["label"].dropna()))
                        all_valid_species.extend(list(ref_df["value"].dropna()))
                except Exception:
                    pass

            all_valid_species = sorted(
                list(
                    set(
                        [
                            s
                            for s in all_valid_species
                            if pd.notna(s) and str(s).lower() not in ["other", "nan", "none", ""]
                        ]
                    )
                )
            )

            if len(all_valid_species) == 0:
                st.warning(f"No species reference files found for partner: {config.PARTNER}")
            else:
                st.caption(f"Reference species loaded: {len(all_valid_species)} entries")

                local_fuzzy_threshold = st.slider(
                    "Match threshold %",
                    min_value=50,
                    max_value=100,
                    value=70,
                    step=5,
                    key="tree_class_fuzzy_threshold",
                    help="Minimum similarity score to show a match",
                )

                fuzzy_matches = []

                for _, row in all_other_trees.iterrows():
                    reported_name = None
                    if pd.notna(row.get("other_species")) and str(row.get("other_species")).strip():
                        reported_name = str(row.get("other_species")).strip()
                    elif pd.notna(row.get("language_other_species")) and str(row.get("language_other_species")).strip():
                        reported_name = str(row.get("language_other_species")).strip()

                    if reported_name and reported_name.lower() not in ["nan", "none", ""]:
                        matches = process.extract(reported_name, all_valid_species, scorer=fuzz.ratio, limit=1)

                        if matches and matches[0][1] >= local_fuzzy_threshold:
                            enumerator_val = row.get("enumerator")
                            enumerator = str(enumerator_val) if pd.notna(enumerator_val) else "Unknown"

                            veg_key_val = row.get("VEGETATION_KEY")
                            veg_key = str(veg_key_val) if pd.notna(veg_key_val) else ""

                            fuzzy_matches.append(
                                {
                                    "enumerator": enumerator,
                                    "VEGETATION_KEY": veg_key,
                                    "reported_name": reported_name,
                                    "matched_name": matches[0][0],
                                    "match_score": matches[0][1],
                                }
                            )

                if len(fuzzy_matches) > 0:
                    fuzzy_df = pd.DataFrame(fuzzy_matches)

                    st.metric(f"Potential Matches (>= {local_fuzzy_threshold}%)", len(fuzzy_df))

                    st.dataframe(
                        fuzzy_df,
                        use_container_width=True,
                        height=400,
                        column_config={
                            "enumerator": st.column_config.TextColumn("Submitter"),
                            "VEGETATION_KEY": st.column_config.TextColumn("Vegetation Key"),
                            "reported_name": st.column_config.TextColumn("Reported Name"),
                            "matched_name": st.column_config.TextColumn("Matched Species"),
                            "match_score": st.column_config.NumberColumn("Score %", format="%d"),
                        },
                    )
                else:
                    st.info(f"No matches found above {local_fuzzy_threshold}% threshold. Try lowering the threshold.")

    # ============================================
    # 2. COMMONLY REPORTED "OTHER" SPECIES (AGGREGATED)
    # ============================================

    st.markdown("---")
    st.markdown("### 📊 Commonly Reported 'Other' Species")
    st.caption(
        "Aggregates all manually-entered 'other' species by name (with fuzzy grouping to handle spelling variations). Use this to identify frequently reported species that should be added to the partner's official species registry (TSV files). 'Total Trees' = sum of vegetation_type_number across all matching records."
    )

    # Combine all "other" trees
    all_other = pd.concat([primary_trees, non_primary_trees, young_trees_other], ignore_index=True)

    if len(all_other) > 0 and "tree_name" in all_other.columns:
        # Clean tree names
        all_other = all_other[all_other["tree_name"].notna()]
        all_other = all_other[~all_other["tree_name"].isin(["Unknown", ""])]

        # Ensure vegetation_type_number is numeric
        if "vegetation_type_number" in all_other.columns:
            all_other["vegetation_type_number"] = pd.to_numeric(
                all_other["vegetation_type_number"], errors="coerce"
            ).fillna(1)
        else:
            all_other["vegetation_type_number"] = 1

        if len(all_other) > 0 and FUZZY_AVAILABLE:
            # Fuzzy cluster similar names
            grouping_threshold = st.slider(
                "Grouping Threshold %",
                min_value=50,
                max_value=100,
                value=90,
                step=5,
                key="tree_grouping_threshold",
                help="Lower = more aggressive grouping of similar spellings",
            )
            unique_names = all_other["tree_name"].unique().tolist()
            clusters = {}  # canonical -> [variants]

            for name in unique_names:
                name_lower = str(name).lower().strip()
                matched = None
                for canonical in clusters:
                    if fuzz.ratio(name_lower, canonical.lower()) >= grouping_threshold:
                        matched = canonical
                        break
                if matched:
                    clusters[matched].append(name)
                else:
                    clusters[name] = [name]

            # Build aggregated table with vegetation_type_number sum
            agg_data = []
            for canonical, variants in clusters.items():
                subset = all_other[all_other["tree_name"].isin(variants)]
                tree_count = int(subset["vegetation_type_number"].sum())
                record_count = len(subset)
                agg_data.append(
                    {
                        "Species Name": canonical,
                        "Variants": ", ".join(sorted(set(v for v in variants if v != canonical))) or "-",
                        "Total Trees": tree_count,
                        "Records": record_count,
                    }
                )

            agg_df = pd.DataFrame(agg_data).sort_values("Total Trees", ascending=False)

            st.dataframe(
                agg_df[["Species Name", "Variants", "Total Trees", "Records"]],
                use_container_width=True,
                hide_index=True,
            )
        elif len(all_other) > 0:
            # Simple groupby without fuzzy
            agg_df = (
                all_other.groupby("tree_name")
                .agg(Total_Trees=("vegetation_type_number", "sum"), Records=("tree_name", "size"))
                .reset_index()
            )
            agg_df.columns = ["Species Name", "Total Trees", "Records"]
            agg_df["Variants"] = "-"
            agg_df = agg_df.sort_values("Total Trees", ascending=False)

            st.dataframe(
                agg_df[["Species Name", "Variants", "Total Trees", "Records"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No valid 'other' species data after filtering")
    else:
        st.info("No 'other' species data available")

    # ============================================
    # 3. COMMONLY REPORTED "OTHER" SPECIES IN COVERAGE
    # ============================================

    st.markdown("---")
    st.markdown("### 🌾 Commonly Reported 'Other' Species in Coverage")
    st.caption(
        "Same as above but for coverage-type records (non-woody vegetation like grasses, crops, ground cover). These are filtered by vegetation_type_woody='nonwoody_coverage' OR vegetation_type_youngtree='no_coverage'. Frequently reported coverage species may warrant addition to the non-woody species list."
    )

    # Filter for coverage records
    coverage_filter = pd.Series([False] * len(veg_df), index=veg_df.index)

    if "vegetation_type_woody" in veg_df.columns:
        coverage_filter |= veg_df["vegetation_type_woody"] == "nonwoody_coverage"

    if "vegetation_type_youngtree" in veg_df.columns:
        coverage_filter |= veg_df["vegetation_type_youngtree"] == "no_coverage"

    coverage = veg_df[coverage_filter].copy()

    if len(coverage) > 0 and "other_species" in coverage.columns:
        # Filter to records with 'other_species' filled in
        coverage_other = coverage[coverage["other_species"].notna()].copy()

        # Clean species names
        coverage_other = coverage_other[~coverage_other["other_species"].isin(["", "nan", "None"])]
        coverage_other["other_species"] = coverage_other["other_species"].astype(str).str.strip()
        coverage_other = coverage_other[coverage_other["other_species"] != ""]

        if len(coverage_other) > 0:
            # Ensure coverage_vegetation is numeric for aggregation
            if "coverage_vegetation" in coverage_other.columns:
                coverage_other["coverage_vegetation"] = pd.to_numeric(
                    coverage_other["coverage_vegetation"], errors="coerce"
                ).fillna(1)
            else:
                coverage_other["coverage_vegetation"] = 1

            if FUZZY_AVAILABLE:
                # Fuzzy cluster similar names
                coverage_grouping_threshold = st.slider(
                    "Grouping Threshold %",
                    min_value=50,
                    max_value=100,
                    value=75,
                    step=5,
                    key="coverage_grouping_threshold",
                    help="Lower = more aggressive grouping of similar spellings",
                )
                unique_names = coverage_other["other_species"].unique().tolist()
                clusters = {}  # canonical -> [variants]

                for name in unique_names:
                    name_lower = str(name).lower().strip()
                    matched = None
                    for canonical in clusters:
                        if fuzz.ratio(name_lower, canonical.lower()) >= coverage_grouping_threshold:
                            matched = canonical
                            break
                    if matched:
                        clusters[matched].append(name)
                    else:
                        clusters[name] = [name]

                # Build aggregated table
                agg_data = []
                for canonical, variants in clusters.items():
                    subset = coverage_other[coverage_other["other_species"].isin(variants)]
                    total_coverage = int(subset["coverage_vegetation"].sum())
                    record_count = len(subset)
                    agg_data.append(
                        {
                            "Species Name": canonical,
                            "Variants": ", ".join(sorted(set(v for v in variants if v != canonical))) or "-",
                            "Total Coverage": total_coverage,
                            "Records": record_count,
                        }
                    )

                agg_df = pd.DataFrame(agg_data).sort_values("Total Coverage", ascending=False)

                st.dataframe(
                    agg_df[["Species Name", "Variants", "Total Coverage", "Records"]],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                # Simple groupby without fuzzy
                agg_df = (
                    coverage_other.groupby("other_species")
                    .agg(Total_Coverage=("coverage_vegetation", "sum"), Records=("other_species", "size"))
                    .reset_index()
                )
                agg_df.columns = ["Species Name", "Total Coverage", "Records"]
                agg_df["Variants"] = "-"
                agg_df = agg_df.sort_values("Total Coverage", ascending=False)

                st.dataframe(
                    agg_df[["Species Name", "Variants", "Total Coverage", "Records"]],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("No 'other' species entries found in coverage records")
    else:
        st.info("No coverage data found")

# ============================================
# TAB 1: MEASUREMENTS
# ============================================

with tabs[0]:
    st.markdown("### 📏 Measurement Quality Checks")
    st.caption(
        "Validates tree measurements (height, circumference, stem count) against configurable thresholds and biological plausibility rules. Adjust thresholds in the sidebar based on regional species characteristics."
    )

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(f"Current thresholds: Stems > {stem_threshold}, Tall trees > {tall_tree_threshold}m")

    # CHECK 1: Super Tall Trees Check
    st.markdown(f"#### 1️⃣ Super Tall Trees (> {tall_tree_threshold}m)")
    st.caption(
        "Lists trees exceeding the height threshold. Cross-check with tree_year_planted - a 40m tree planted in 2023 is likely a data entry error. Adjust the threshold in the sidebar if needed for specific regions or species."
    )

    # Use filtered measurement data for tall tree check
    if has_measurements and len(meas_df) > 0:
        if "MEASUREMENT_KEY" in meas_df.columns:
            m_mea_actual = meas_df[meas_df["MEASUREMENT_KEY"].notna()].copy()
        else:
            m_mea_actual = meas_df.copy()

        if "tree_height_m" in m_mea_actual.columns:
            height_check = m_mea_actual[m_mea_actual["tree_height_m"].notna()].copy()

            if len(height_check) > 0:
                # Filter super tall trees
                super_tall = height_check[height_check["tree_height_m"] > tall_tree_threshold].copy()

                st.metric(f"Trees > {tall_tree_threshold}m", len(super_tall))

                if len(super_tall) > 0:
                    st.warning(
                        f"⚠️ {len(super_tall)} trees exceed {tall_tree_threshold}m - verify planting age is realistic"
                    )

                    # Display columns - build safely
                    display_cols = []
                    for col in [
                        "enumerator",
                        "VEGETATION_KEY",
                        "SUBPLOT_KEY",
                        "tree_name",
                        "tree_height_m",
                        "tree_year_planted",
                        "vegetation_type_number",
                        "tree_prune",
                        "tree_coppiced",
                        species_col,
                    ]:
                        if col and col in super_tall.columns:
                            display_cols.append(col)

                    # Add row numbers
                    display_df = super_tall[display_cols].copy()
                    display_df.insert(0, "#", range(1, len(display_df) + 1))

                    st.dataframe(
                        display_df.sort_values("tree_height_m", ascending=False),
                        use_container_width=True,
                        height=min(400, len(super_tall) * 35 + 38),
                        hide_index=True,
                    )

                    # Download option
                    st.download_button(
                        label="📥 Download super tall trees",
                        data=super_tall[display_cols].to_csv(index=False),
                        file_name=f"height_super_tall_{tall_tree_threshold}m.csv",
                        mime="text/csv",
                    )
                else:
                    st.success(f"✅ No trees exceed {tall_tree_threshold}m")
            else:
                st.info("No height data available")
        else:
            st.error("❌ tree_height_m column not found")
    else:
        st.info("ℹ️ Measurement data not available")

    st.markdown("---")

    # CHECK 2: High stem counts
    st.markdown(f"#### 2️⃣ High Stem Counts (> {stem_threshold})")
    st.caption(
        "Trees with unusually high stem counts at breast height. While some species (e.g., bamboo, coppiced trees) legitimately have many stems, counts above 20-40 may indicate measurement errors or confusion about what constitutes a 'stem'. Review species context before flagging."
    )

    meas_with_enum = detect_stem_outliers(meas_with_enum, threshold=stem_threshold)
    high_stems = meas_with_enum[meas_with_enum["high_stems_bh"] == True]

    st.metric(f"Trees with > {stem_threshold} stems", len(high_stems))

    if len(high_stems) > 0:
        st.warning(f"⚠️ {len(high_stems)} trees with unusually high stem counts")

        high_stems = high_stems.copy()

        # Add tree_name - first try from complete_df which has species columns
        if (
            has_complete
            and len(complete_df) > 0
            and "MEASUREMENT_KEY" in high_stems.columns
            and "MEASUREMENT_KEY" in complete_df.columns
        ):
            # Get tree_name from complete_df which has species info
            complete_with_names = add_tree_name_column(complete_df)
            if "tree_name" in complete_with_names.columns:
                tree_name_map = complete_with_names[["MEASUREMENT_KEY", "tree_name"]].drop_duplicates()
                high_stems = high_stems.merge(tree_name_map, on="MEASUREMENT_KEY", how="left")
        else:
            # Fallback: try adding directly (may result in "Unknown" if no species columns)
            high_stems = add_tree_name_column(high_stems)

        # Add above_1.3m flag based on vegetation_type_height
        # Values: "yes_above_1.3" (above 1.3m) or "no_below_1.3m" (below 1.3m)
        if "vegetation_type_height" in high_stems.columns:
            high_stems["above_1.3m"] = high_stems["vegetation_type_height"].apply(
                lambda x: "Yes" if str(x).lower() == "yes_above_1.3" else "No"
            )

        # Ensure enumerator and SubmissionDate are available from filtered_gdf
        if "subplot_id" in high_stems.columns:
            merge_cols = ["subplot_id"]
            if "enumerator" in filtered_gdf.columns and "enumerator" not in high_stems.columns:
                merge_cols.append("enumerator")
            if "SubmissionDate" in filtered_gdf.columns and "SubmissionDate" not in high_stems.columns:
                merge_cols.append("SubmissionDate")
            if len(merge_cols) > 1:
                enum_date_map = filtered_gdf[merge_cols].drop_duplicates()
                high_stems = high_stems.merge(enum_date_map, on="subplot_id", how="left")

        display_cols = []
        for col in [
            "MEASUREMENT_KEY",
            "enumerator",
            "tree_name",
            "above_1.3m",
            "SubmissionDate",
            "nr_stems_bh",
            "nr_stems_10cm",
            "tree_year_planted",
        ]:
            if col and col in high_stems.columns:
                display_cols.append(col)

        if len(display_cols) > 0:
            # Add row numbers
            display_df = high_stems[display_cols].copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))

            st.dataframe(
                (
                    display_df.sort_values("nr_stems_bh", ascending=False)
                    if "nr_stems_bh" in display_df.columns
                    else display_df
                ),
                use_container_width=True,
                height=min(400, len(high_stems) * 35 + 38),
                hide_index=True,
            )
        else:
            st.warning("No displayable columns")
    else:
        st.success(f"✅ No trees exceed {stem_threshold} stems")

    st.markdown("---")

    # CHECK 5: Circumference Check with Threshold
    st.markdown("#### 3️⃣ Large Circumference Check")
    st.caption(
        "Focus on relationship between tree age and circumference to avoid errors (e.g. circumference 300cm planted in 2024)"
    )

    st.info(
        """
        **How Circumference Homogeneity is Calculated:**
        1. **Apply filters**: Date range and enumerator filters from sidebar
        2. **Group by MEASUREMENT_KEY**: Individual tree measurements grouped together
        3. **Calculate Median**: The median circumference is calculated for each measurement group
        4. **Flag Outliers**: Large variations within a measurement group may indicate data entry errors

        ⚠️ **Note**: This respects your date range filter. Only measurements from the selected date range are analyzed.
        """
    )

    # Get the filtered complete data that includes circumference
    if has_complete and len(complete_df) > 0:
        # Filter to records with actual measurements
        if "MEASUREMENT_KEY" in complete_df.columns:
            m_cir = complete_df[complete_df["MEASUREMENT_KEY"].notna()].copy()
        else:
            m_cir = complete_df.copy()

        # Parameters from notebook
        circumference_cols = [
            "enumerator",
            "VEGETATION_KEY",
            "MEASUREMENT_KEY",
            "CIRCUMFERENCE_KEY",
            "vegetation_type_number",
            "circumference_bh",
            "circumference_10cm",
            "tree_year_planted",
            # Species columns for tree_name lookup
            "woody_spec",
            "woody_species",
            "bamboo_spec",
            "bamboo_species",
            "banana_spec",
            "banana_species",
            "palm_species",
            "living_fences",
            "other_species",
            "language_other_species",
        ]

        # Filter to available columns
        available_cols = [col for col in circumference_cols if col in m_cir.columns]

        if len(available_cols) > 0:
            circumference_list = m_cir[available_cols].copy()

            # Calculate median per MEASUREMENT_KEY
            has_bh = "circumference_bh" in circumference_list.columns
            has_10cm = "circumference_10cm" in circumference_list.columns

            if has_bh or has_10cm:
                # Add tree age calculation
                if "tree_year_planted" in circumference_list.columns:
                    circumference_list = calculate_tree_age_corrected(circumference_list)

                # Calculate median circumference per MEASUREMENT_KEY
                # Use circumference_bh for median calculation (notebook logic)
                if has_bh and "MEASUREMENT_KEY" in circumference_list.columns:
                    # Filter to non-null BH values for median calculation
                    bh_data = circumference_list[circumference_list["circumference_bh"].notna()]
                    if len(bh_data) > 0:
                        median_cir_bh = (
                            bh_data.groupby("MEASUREMENT_KEY")["circumference_bh"]
                            .median()
                            .reset_index(name="median_cir")
                        )
                        cir_total = pd.merge(
                            circumference_list,
                            median_cir_bh,
                            how="left",
                            on="MEASUREMENT_KEY",
                        )

                        # Outlier flags for circumference_bh
                        cir_total["Upper_outliers"] = cir_total.apply(
                            lambda row: (
                                "outlier"
                                if pd.notna(row["circumference_bh"])
                                and pd.notna(row.get("median_cir"))
                                and row["circumference_bh"] > (row["median_cir"] * 4)
                                else "ok"
                            ),
                            axis=1,
                        )
                        cir_total["Lower_outliers"] = cir_total.apply(
                            lambda row: (
                                "outlier"
                                if pd.notna(row["circumference_bh"])
                                and pd.notna(row.get("median_cir"))
                                and row["circumference_bh"] < (row["median_cir"] / 4)
                                else "ok"
                            ),
                            axis=1,
                        )
                    else:
                        cir_total = circumference_list.copy()
                else:
                    # If no BH data, just use the list as is
                    cir_total = circumference_list.copy()

                st.markdown("---")

                # Threshold sliders in columns
                col1, col2 = st.columns(2)

                with col1:
                    if has_bh:
                        threshold_bh = st.slider(
                            "circumference_bh threshold (cm)",
                            min_value=50,
                            max_value=300,
                            value=90,
                            step=10,
                            help="Flag measurements exceeding this circumference at breast height",
                        )

                with col2:
                    if has_10cm:
                        threshold_10cm = st.slider(
                            "circumference_10cm threshold (cm)",
                            min_value=50,
                            max_value=300,
                            value=90,
                            step=10,
                            help="Flag measurements exceeding this circumference at 10cm height",
                        )

                # Show circumference_bh > threshold
                if has_bh:
                    st.markdown(f"##### 📏 Circumference at Breast Height > {threshold_bh}cm")

                    large_bh = cir_total[cir_total["circumference_bh"] > threshold_bh].copy()

                    st.metric(f"Measurements > {threshold_bh}cm", len(large_bh))

                    if len(large_bh) > 0:
                        # Calculate tree age
                        if "tree_year_planted" in large_bh.columns:
                            large_bh = calculate_tree_age_corrected(large_bh, "tree_year_planted")

                        # Add tree_name column
                        from utils.data_merge_utils import add_tree_name_column

                        large_bh = add_tree_name_column(large_bh)

                        # Convert tree_year_planted to year only
                        if "tree_year_planted" in large_bh.columns:
                            large_bh["tree_year_planted"] = pd.to_datetime(
                                large_bh["tree_year_planted"], errors="coerce"
                            ).dt.year

                        # Display columns - use CIRCUMFERENCE_KEY for circumference data
                        display_cols = [
                            "enumerator",
                            "tree_name",
                            "CIRCUMFERENCE_KEY",
                            "vegetation_type_number",
                            "circumference_bh",
                            "tree_year_planted",
                        ]

                        if "tree_age" in large_bh.columns:
                            display_cols.append("tree_age")
                        if "median_cir" in large_bh.columns:
                            display_cols.append("median_cir")
                        if "Upper_outliers" in large_bh.columns:
                            display_cols.append("Upper_outliers")
                        if "Lower_outliers" in large_bh.columns:
                            display_cols.append("Lower_outliers")

                        display_cols = [col for col in display_cols if col in large_bh.columns]

                        # Add row numbers
                        display_df = large_bh[display_cols].copy()
                        display_df.insert(0, "#", range(1, len(display_df) + 1))

                        st.dataframe(
                            display_df.sort_values("circumference_bh", ascending=False),
                            use_container_width=True,
                            height=400,
                            hide_index=True,
                        )

                        # Download option
                        st.download_button(
                            label=f"📥 Download circumference_bh > {threshold_bh}cm",
                            data=large_bh[display_cols].to_csv(index=False),
                            file_name=f"large_circumference_bh_{threshold_bh}cm.csv",
                            mime="text/csv",
                        )
                    else:
                        st.success(f"✅ No measurements exceed {threshold_bh}cm")

                st.markdown("---")

                # Show circumference_10cm > threshold
                if has_10cm:
                    st.markdown(f"##### 📏 Circumference at 10cm Height > {threshold_10cm}cm ")

                    large_10cm = cir_total[cir_total["circumference_10cm"] > threshold_10cm].copy()

                    st.metric(f"Measurements > {threshold_10cm}cm", len(large_10cm))

                    if len(large_10cm) > 0:
                        # Calculate tree age
                        if "tree_year_planted" in large_10cm.columns:
                            large_10cm = calculate_tree_age_corrected(large_10cm)

                        # Display columns - use CIRCUMFERENCE_KEY for circumference data
                        display_cols = [
                            "enumerator",
                            "CIRCUMFERENCE_KEY",
                            "vegetation_type_number",
                            "circumference_10cm",
                            "tree_year_planted",
                        ]

                        if "tree_age" in large_10cm.columns:
                            display_cols.append("tree_age")

                        display_cols = [col for col in display_cols if col in large_10cm.columns]

                        # Add row numbers
                        display_df = large_10cm[display_cols].copy()
                        display_df.insert(0, "#", range(1, len(display_df) + 1))

                        st.dataframe(
                            display_df.sort_values("circumference_10cm", ascending=False),
                            use_container_width=True,
                            height=400,
                            hide_index=True,
                        )

                        # Download option
                        st.download_button(
                            label=f"📥 Download circumference_10cm > {threshold_10cm}cm",
                            data=large_10cm[display_cols].to_csv(index=False),
                            file_name=f"large_circumference_10cm_{threshold_10cm}cm.csv",
                            mime="text/csv",
                        )
                    else:
                        st.success(f"✅ No measurements exceed {threshold_10cm}cm")
            else:
                st.info("ℹ️ No circumference columns (circumference_bh or circumference_10cm) found")
        else:
            st.info("ℹ️ Required columns not available")
    else:
        st.info(
            "ℹ️ Complete dataset with circumference not available. Make sure your Excel file has a 'circumference' sheet."
        )

    st.markdown("---")

    # CHECK 6: Species Measurement Statistics
    st.markdown("#### 4️⃣ Species Measurement Statistics")
    st.caption(
        "Summary statistics (mean, median, min, max) for height, circumference, and stem count by species. Use this to establish baseline expectations for each species and identify species with unusual measurement distributions that may warrant closer inspection."
    )

    # Load species lookup for normalization (returns two dicts)
    scientific_lookup, common_lookup = load_species_lookup(config.PARTNER)

    # Use complete_df which has circumference data, fall back to meas_with_enum
    if has_complete and len(complete_df) > 0:
        stats_source_df = complete_df.copy()
    else:
        stats_source_df = meas_with_enum.copy()

    # Filter for woody vegetation only
    if "vegetation_type_woody" in stats_source_df.columns:
        woody_data = stats_source_df[stats_source_df["vegetation_type_woody"] == "woody"].copy()
    else:
        woody_data = stats_source_df.copy()
        st.info("ℹ️ vegetation_type_woody column not found, showing all data")

    if len(woody_data) > 0:
        # Filter selector for vegetation_type_height
        if "vegetation_type_height" in woody_data.columns:
            height_types = ["All"] + sorted(
                [str(x) for x in woody_data["vegetation_type_height"].dropna().unique().tolist()]
            )
            selected_height_type = st.selectbox(
                "Filter by Height Type",
                options=height_types,
                key="species_stats_height_filter",
            )

            if selected_height_type != "All":
                woody_data = woody_data[woody_data["vegetation_type_height"] == selected_height_type]

        st.caption(f"Showing {len(woody_data)} woody tree records")

        # Normalize species names (using both scientific and common name lookups)
        woody_data["normalized_species"] = woody_data.apply(
            lambda row: normalize_species_name(row, scientific_lookup, common_lookup), axis=1
        )

        # Calculate statistics per species
        metrics = ["tree_height_m", "nr_stems_bh", "circumference_bh"]
        available_metrics = [m for m in metrics if m in woody_data.columns]

        if len(available_metrics) > 0:
            # Group by normalized species and calculate stats
            stats_list = []
            for species in woody_data["normalized_species"].unique():
                species_data = woody_data[woody_data["normalized_species"] == species]
                row_data = {"Species": species, "Count": len(species_data)}

                for metric in available_metrics:
                    metric_data = species_data[metric].dropna()
                    if len(metric_data) > 0:
                        row_data[f"{metric}_mean"] = round(metric_data.mean(), 2)
                        row_data[f"{metric}_median"] = round(metric_data.median(), 2)
                    else:
                        row_data[f"{metric}_mean"] = None
                        row_data[f"{metric}_median"] = None

                stats_list.append(row_data)

            stats_df = pd.DataFrame(stats_list).sort_values("Count", ascending=False).reset_index(drop=True)

            # Rename columns for better display
            column_rename = {
                "tree_height_m_mean": "Height Mean (m)",
                "tree_height_m_median": "Height Median (m)",
                "nr_stems_bh_mean": "Stems Mean",
                "nr_stems_bh_median": "Stems Median",
                "circumference_bh_mean": "Circ Mean (cm)",
                "circumference_bh_median": "Circ Median (cm)",
            }
            stats_df = stats_df.rename(columns=column_rename)

            st.dataframe(
                stats_df,
                use_container_width=True,
                hide_index=True,
            )

            st.caption(f"Total: {len(stats_df)} species")

            # Download option
            st.download_button(
                label="📥 Download species statistics",
                data=stats_df.to_csv(index=False),
                file_name="species_measurement_statistics.csv",
                mime="text/csv",
                key="download_species_stats",
            )

            # Species-Based Outlier Detection Section
            st.markdown("---")
            st.markdown("#### 5️⃣ Species-Based Outlier Detection")
            st.caption(
                "Select a species to view measurements that deviate significantly from the species median (>4x or <0.25x)"
            )

            # Get species counts for dropdown
            species_counts = woody_data.groupby("normalized_species").size().sort_values(ascending=False)

            # Create dropdown options: "Species Name (count)"
            species_options = [f"{sp} ({count})" for sp, count in species_counts.items()]

            if len(species_options) > 0:
                selected_option = st.selectbox(
                    "Select Species",
                    options=species_options,
                    key="species_outlier_selector",
                )

                # Extract species name from selection
                selected_species = selected_option.rsplit(" (", 1)[0] if selected_option else None

                if selected_species:
                    species_data = woody_data[woody_data["normalized_species"] == selected_species].copy()

                    # Detect outliers for each metric in tabs
                    metric_tabs = st.tabs(["Height Outliers", "Circumference Outliers", "Stem Count Outliers"])

                    for i, (metric, metric_name) in enumerate(
                        [
                            ("tree_height_m", "Height"),
                            ("circumference_bh", "Circumference"),
                            ("nr_stems_bh", "Stem Count"),
                        ]
                    ):
                        with metric_tabs[i]:
                            if metric not in species_data.columns:
                                st.info(f"ℹ️ {metric} column not available in data")
                                continue

                            outliers = detect_species_outliers(species_data, metric)

                            if len(outliers) == 0:
                                st.info(f"ℹ️ No valid {metric_name.lower()} data for this species")
                                continue

                            outliers_only = outliers[outliers["is_outlier"] == True]

                            if len(outliers_only) > 0:
                                st.error(f"❌ {len(outliers_only)} {metric_name.lower()} outliers found")

                                # Build display dataframe
                                display_cols = ["normalized_species"]

                                # Add subplot info if available
                                if "subplot_id" in outliers_only.columns:
                                    display_cols.append("subplot_id")
                                elif "SUBPLOT_KEY" in outliers_only.columns:
                                    display_cols.append("SUBPLOT_KEY")

                                # Add appropriate key - CIRCUMFERENCE_KEY for circumference, MEASUREMENT_KEY otherwise
                                if (
                                    metric in ("circumference_bh", "circumference_10cm")
                                    and "CIRCUMFERENCE_KEY" in outliers_only.columns
                                ):
                                    display_cols.append("CIRCUMFERENCE_KEY")
                                elif "MEASUREMENT_KEY" in outliers_only.columns:
                                    display_cols.append("MEASUREMENT_KEY")

                                # Add enumerator and date
                                if "enumerator" in outliers_only.columns:
                                    display_cols.append("enumerator")
                                if "SubmissionDate" in outliers_only.columns:
                                    display_cols.append("SubmissionDate")

                                # Add vegetation_type_height for Stem Count outliers
                                if metric == "nr_stems_bh" and "vegetation_type_height" in outliers_only.columns:
                                    display_cols.append("vegetation_type_height")

                                # Add metric and median
                                display_cols.extend([metric, "species_median"])

                                # Filter to only existing columns
                                display_cols = [c for c in display_cols if c in outliers_only.columns]

                                display_df = outliers_only[display_cols].copy()

                                # Add outlier type column
                                display_df["Outlier Type"] = outliers_only.apply(
                                    lambda row: "Too High" if row.get("is_upper_outlier") else "Too Low",
                                    axis=1,
                                )

                                # Rename columns for display
                                col_renames = {
                                    "normalized_species": "Species",
                                    "subplot_id": "Subplot ID",
                                    "SUBPLOT_KEY": "Subplot ID",
                                    "MEASUREMENT_KEY": "Measurement Key",
                                    "CIRCUMFERENCE_KEY": "Circumference Key",
                                    "enumerator": "Enumerator",
                                    "SubmissionDate": "Date",
                                    "vegetation_type_height": "Height Category",
                                    "species_median": f"{metric_name} Median",
                                    metric: f"{metric_name} Value",
                                }
                                display_df = display_df.rename(columns=col_renames)

                                st.dataframe(display_df, use_container_width=True, hide_index=True)
                            else:
                                st.success(f"✅ No {metric_name.lower()} outliers for {selected_species}")
            else:
                st.info("ℹ️ No species data available for outlier detection")

            # Age + Species Outlier Detection Section
            st.markdown("---")
            st.markdown("#### 6️⃣ Age + Species Outlier Detection")
            st.caption(
                "Groups trees by species AND age. "
                "Height/Circumference: flags values beyond 3 standard deviations. "
                "Stem count: flags values >4x median (min=1)."
            )

            # Ensure tree_age is calculated (already done in DBSCAN section, but check again)
            if "tree_age" not in woody_data.columns and "tree_year_planted" in woody_data.columns:
                woody_data = calculate_tree_age(woody_data)

            if "tree_age" not in woody_data.columns:
                st.warning("tree_age column not available (requires tree_year_planted)")
            elif "normalized_species" not in woody_data.columns:
                st.warning("normalized_species column not available")
            else:
                # Attribute and Species selectors side by side
                age_species_attr_options = {
                    "Height (tree_height_m)": "tree_height_m",
                    "Circumference (circumference_bh)": "circumference_bh",
                    "Stem Count (nr_stems_bh)": "nr_stems_bh",
                }

                available_age_species_attrs = {
                    k: v for k, v in age_species_attr_options.items() if v in woody_data.columns
                }

                if not available_age_species_attrs:
                    st.warning("No physical attribute columns available")
                else:
                    # Get species list with counts for the selector
                    all_species_counts = (
                        woody_data[woody_data["normalized_species"].notna()]
                        .groupby("normalized_species")
                        .size()
                        .sort_values(ascending=False)
                    )
                    species_options_list = ["All"] + [
                        f"{species} ({count})" for species, count in all_species_counts.items()
                    ]
                    species_name_map = {
                        f"{species} ({count})": species for species, count in all_species_counts.items()
                    }

                    col1, col2 = st.columns(2)
                    with col1:
                        selected_age_species_attr = st.selectbox(
                            "Select Attribute",
                            options=list(available_age_species_attrs.keys()),
                            key="age_species_attribute_selector",
                        )
                    with col2:
                        selected_species_option = st.selectbox(
                            "Select Species",
                            options=species_options_list,
                            key="age_species_species_selector",
                        )

                    selected_age_species_col = available_age_species_attrs[selected_age_species_attr]

                    # Filter data by species if not "All"
                    if selected_species_option == "All":
                        filtered_woody_data = woody_data
                        selected_species_name = None
                    else:
                        selected_species_name = species_name_map[selected_species_option]
                        filtered_woody_data = woody_data[woody_data["normalized_species"] == selected_species_name]

                    # Run age+species median-based detection
                    age_species_results = detect_age_species_outliers(
                        filtered_woody_data,
                        metric_col=selected_age_species_col,
                    )

                    if len(age_species_results) > 0:
                        outliers = age_species_results[age_species_results["is_outlier"] == True]

                        st.metric("Outliers", len(outliers), delta=f"of {len(age_species_results)} records")

                        if len(outliers) > 0:
                            # Create display dataframe
                            display_df = outliers.copy()

                            # Create combined valid range column
                            if "valid_range_lower" in display_df.columns and "valid_range_upper" in display_df.columns:
                                display_df["valid_range"] = display_df.apply(
                                    lambda r: f"{r['valid_range_lower']:.2f} - {r['valid_range_upper']:.2f}",
                                    axis=1,
                                )

                            # Display columns
                            display_cols = [
                                "normalized_species",
                                "tree_age",
                                selected_age_species_col,
                                "group_median",
                                "valid_range",
                            ]

                            # For stem count, also show height for context
                            if selected_age_species_col == "nr_stems_bh" and "tree_height_m" in display_df.columns:
                                display_cols.insert(3, "tree_height_m")

                            if "subplot_id" in display_df.columns:
                                display_cols.insert(0, "subplot_id")
                            elif "SUBPLOT_KEY" in display_df.columns:
                                display_cols.insert(0, "SUBPLOT_KEY")

                            # Add appropriate key - CIRCUMFERENCE_KEY for circumference, MEASUREMENT_KEY otherwise
                            if (
                                selected_age_species_col in ("circumference_bh", "circumference_10cm")
                                and "CIRCUMFERENCE_KEY" in display_df.columns
                            ):
                                display_cols.append("CIRCUMFERENCE_KEY")
                            elif "MEASUREMENT_KEY" in display_df.columns:
                                display_cols.append("MEASUREMENT_KEY")
                            if "enumerator" in display_df.columns:
                                display_cols.append("enumerator")

                            display_cols = [c for c in display_cols if c in display_df.columns]
                            display_df = display_df[display_cols].copy()

                            # Round numeric columns
                            if "group_median" in display_df.columns:
                                display_df["group_median"] = display_df["group_median"].round(2)
                            if "tree_height_m" in display_df.columns:
                                display_df["tree_height_m"] = display_df["tree_height_m"].round(2)

                            # Rename for display
                            attr_name = selected_age_species_attr.split(" (")[0]
                            # Different labels for different methods
                            if selected_age_species_col == "nr_stems_bh":
                                valid_range_label = "Valid Range (1 to 4x)"
                                group_stat_label = "Group Median"
                            else:
                                valid_range_label = "Valid Range (mean +/- 3SD)"
                                group_stat_label = "Group Mean"

                            display_df = display_df.rename(
                                columns={
                                    "normalized_species": "Species",
                                    "tree_age": "Age (years)",
                                    selected_age_species_col: f"Actual {attr_name}",
                                    "tree_height_m": "Height (m)",
                                    "group_median": group_stat_label,
                                    "valid_range": valid_range_label,
                                    "subplot_id": "Subplot ID",
                                    "SUBPLOT_KEY": "Subplot ID",
                                    "MEASUREMENT_KEY": "Measurement Key",
                                    "CIRCUMFERENCE_KEY": "Circumference Key",
                                    "enumerator": "Enumerator",
                                }
                            )

                            st.dataframe(display_df, use_container_width=True, hide_index=True)

                            st.download_button(
                                f"Download {attr_name} outliers",
                                data=display_df.to_csv(index=False),
                                file_name=f"age_species_outliers_{selected_age_species_col}.csv",
                                mime="text/csv",
                                key="download_age_species_outliers",
                            )
                        else:
                            st.success("No outliers detected")

                        # Visualization chart (only show if a specific species is selected)
                        if selected_species_option != "All":
                            st.markdown("##### Visualization")
                            species_chart_data = age_species_results.copy()

                            if len(species_chart_data) > 0:
                                import plotly.graph_objects as go

                                # Sort by age for proper plotting
                                species_chart_data = species_chart_data.sort_values("tree_age")

                                attr_name = selected_age_species_attr.split(" (")[0]

                                fig = go.Figure()

                                # Get unique ages and their median/valid ranges (only ages with 3+ trees)
                                age_stats = (
                                    species_chart_data.groupby("tree_age")
                                    .agg(
                                        {
                                            "group_median": "first",
                                            "valid_range_lower": "first",
                                            "valid_range_upper": "first",
                                            "group_count": "first",
                                        }
                                    )
                                    .reset_index()
                                )
                                # Filter to ages with enough samples for meaningful median
                                age_stats = age_stats[age_stats["group_count"] >= 3].sort_values("tree_age")

                                # Add valid range zone (shaded area) - only if we have ages with enough data
                                if len(age_stats) > 0:
                                    fig.add_trace(
                                        go.Scatter(
                                            x=age_stats["tree_age"].tolist() + age_stats["tree_age"].tolist()[::-1],
                                            y=age_stats["valid_range_upper"].tolist()
                                            + age_stats["valid_range_lower"].tolist()[::-1],
                                            fill="toself",
                                            fillcolor="rgba(0, 176, 246, 0.2)",
                                            line=dict(color="rgba(255,255,255,0)"),
                                            name="Valid Range (0.25x-4x median)",
                                            hoverinfo="skip",
                                        )
                                    )

                                    # Add median line
                                    fig.add_trace(
                                        go.Scatter(
                                            x=age_stats["tree_age"],
                                            y=age_stats["group_median"],
                                            mode="lines+markers",
                                            name="Group Median (3+ trees)",
                                            line=dict(color="blue", width=2),
                                            marker=dict(size=6),
                                        )
                                    )

                                # Add normal points (non-outliers)
                                normal_points = species_chart_data[species_chart_data["is_outlier"] == False]
                                if len(normal_points) > 0:
                                    fig.add_trace(
                                        go.Scatter(
                                            x=normal_points["tree_age"],
                                            y=normal_points[selected_age_species_col],
                                            mode="markers",
                                            name="Normal",
                                            marker=dict(color="green", size=8, symbol="circle"),
                                            hovertemplate=(
                                                f"Age: %{{x}} years<br>"
                                                f"Actual {attr_name}: %{{y:.2f}}<br>"
                                                "<extra></extra>"
                                            ),
                                        )
                                    )

                                # Add outlier points
                                outlier_points = species_chart_data[species_chart_data["is_outlier"] == True]
                                if len(outlier_points) > 0:
                                    fig.add_trace(
                                        go.Scatter(
                                            x=outlier_points["tree_age"],
                                            y=outlier_points[selected_age_species_col],
                                            mode="markers",
                                            name="Outliers",
                                            marker=dict(color="red", size=10, symbol="x"),
                                            hovertemplate=(
                                                f"Age: %{{x}} years<br>"
                                                f"Actual {attr_name}: %{{y:.2f}}<br>"
                                                "<extra></extra>"
                                            ),
                                        )
                                    )

                                fig.update_layout(
                                    title=f"{selected_species_name}: Age vs {attr_name}",
                                    xaxis_title="Tree Age (years)",
                                    yaxis_title=attr_name,
                                    hovermode="closest",
                                    showlegend=True,
                                    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
                                )

                                st.plotly_chart(fig, use_container_width=True)

                                # Show species stats
                                n_total = len(species_chart_data)
                                n_outliers = len(outlier_points) if len(outlier_points) > 0 else 0
                                st.caption(
                                    f"{selected_species_name}: {n_total} trees, {n_outliers} outliers "
                                    f"({n_outliers / n_total * 100:.1f}%)"
                                )
                    else:
                        st.info("Not enough valid data for analysis")

        else:
            st.warning("⚠️ No measurement columns (tree_height_m, nr_stems_bh, circumference_bh) found")
    else:
        st.info("ℹ️ No woody vegetation data available")

# ============================================
# TAB 2: OUTLIERS & SUSPICIOUS
# ============================================

with tabs[1]:
    st.markdown("### ⚠️ Outliers & Suspicious Values")

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(
        "Statistical outlier detection using the Rabobank methodology. Trees are grouped by VEGETATION_KEY (trees planted together) and flagged if their measurements deviate significantly from the group. This helps identify potential data entry errors, measurement mistakes, or genuinely unusual trees that need field verification."
    )

    # CHECK 1: Height outliers using VEGETATION_KEY grouping
    st.markdown("#### 1️⃣ Height Outliers (>4x or <0.25x group median)")

    st.info(
        """
        **How Height Outliers are Calculated (Official Method):**
        1. **Apply filters**: Date range and enumerator filters from sidebar
        2. **Group by VEGETATION_KEY**: Trees grouped by their vegetation group (trees planted together)
        3. **Calculate Median**: The median height is calculated for each vegetation group
        4. **Flag Outliers**:
           - **Too Tall**: Height > **4x** the group median
           - **Too Short**: Height < **0.25x** (1/4) the group median

        **Why VEGETATION_KEY?** Trees in the same VEGETATION_KEY were planted together in the same subplot,
        so they should have similar:
        - Planting year (same age)
        - Location and soil conditions
        - Management practices
        - Species (usually)

        Large variations may indicate:
        - Pruning or coppicing practices
        - Data entry errors
        - Individual tree problems or disease

        ⚠️ **Note**: This respects your date range filter. Only measurements from the selected date range are analyzed.
        """
    )

    # Use filtered measurement data
    if (
        has_measurements
        and len(meas_df) > 0
        and "VEGETATION_KEY" in meas_df.columns
        and "tree_height_m" in meas_df.columns
    ):
        # Filter to records with valid height and VEGETATION_KEY
        height_check = meas_df[meas_df["tree_height_m"].notna() & meas_df["VEGETATION_KEY"].notna()].copy()

        if len(height_check) > 0:
            # Calculate median height per VEGETATION_KEY (tree group)
            median_check = (
                height_check.groupby("VEGETATION_KEY")["tree_height_m"].median().reset_index(name="median_height")
            )

            # Merge with original data
            height_total = pd.merge(height_check, median_check, how="inner", on="VEGETATION_KEY")

            # Apply outlier detection (4x and 1/4x median - Rabobank methodology)
            height_total["Upper_outliers"] = height_total.apply(
                lambda row: "outlier" if row["tree_height_m"] > (row["median_height"] * 4) else "ok",
                axis=1,
            )
            height_total["Lower_outliers"] = height_total.apply(
                lambda row: "outlier" if row["tree_height_m"] < (row["median_height"] / 4) else "ok",
                axis=1,
            )

            # Filter to outliers only
            height_outliers = height_total[
                (height_total["Upper_outliers"] == "outlier") | (height_total["Lower_outliers"] == "outlier")
            ].copy()

            st.metric("Height Outliers", len(height_outliers))

            if len(height_outliers) > 0:
                st.error(f"❌ {len(height_outliers)} height measurements are outliers within their vegetation group")

                # Determine which outlier type
                def get_outlier_type(row):
                    if row.get("Upper_outliers") == "outlier":
                        return "Too Tall"
                    elif row.get("Lower_outliers") == "outlier":
                        return "Too Short"
                    else:
                        return "Unknown"

                height_outliers["Outlier_Type"] = height_outliers.apply(get_outlier_type, axis=1)

                # Add tree_name column using utility function
                height_outliers = add_tree_name_column(height_outliers)

                # Build display columns safely
                display_cols = []
                for col in [
                    "VEGETATION_KEY",
                    "enumerator",
                    "tree_name",
                    "tree_height_m",
                    "median_height",
                    "Outlier_Type",
                    "tree_year_planted",
                    "tree_prune",
                    "tree_coppiced",
                ]:
                    if col in height_outliers.columns:
                        display_cols.append(col)

                if len(display_cols) > 0:
                    display_df = height_outliers[display_cols].copy()
                    display_df.insert(0, "#", range(1, len(display_df) + 1))

                    st.dataframe(
                        display_df.sort_values("tree_height_m", ascending=False)
                        if "tree_height_m" in display_cols
                        else display_df,
                        use_container_width=True,
                        height=min(400, len(height_outliers) * 35 + 38),
                        hide_index=True,
                    )

                    # Download option
                    st.download_button(
                        label="📥 Download Height Outliers CSV",
                        data=height_outliers[display_cols].to_csv(index=False),
                        file_name="height_outliers.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("No displayable columns available")
            else:
                st.success("✅ No height outliers detected")
        else:
            st.info("ℹ️ No valid height data with VEGETATION_KEY available")
    else:
        st.info("ℹ️ Required columns (VEGETATION_KEY, tree_height_m) not available for outlier detection")

    st.markdown("---")

    # CHECK 2: Circumference outliers using VEGETATION_KEY grouping
    st.markdown("#### 2️⃣ Circumference Outliers (>4x or <0.25x group median)")

    st.info(
        """
        **How Circumference Outliers are Calculated:**
        1. **Apply filters**: Date range and enumerator filters from sidebar
        2. **Group by VEGETATION_KEY**: Trees grouped by their vegetation group
        3. **Calculate Median**: The median circumference is calculated for each vegetation group
        4. **Flag Outliers**: Circumference > **4x** or < **0.25x** the group median

        Trees in the same VEGETATION_KEY were planted together and should have similar circumference.

        ⚠️ **Note**: This respects your date range filter.
        """
    )

    if has_complete and len(complete_df) > 0 and "VEGETATION_KEY" in complete_df.columns:
        # Determine which circumference column to use
        circ_col = None
        if "circumference_bh" in complete_df.columns:
            circ_col = "circumference_bh"
        elif "circumference_10cm" in complete_df.columns:
            circ_col = "circumference_10cm"

        if circ_col:
            # Filter to records with valid circumference and VEGETATION_KEY
            circ_check = complete_df[complete_df[circ_col].notna() & complete_df["VEGETATION_KEY"].notna()].copy()

            if len(circ_check) > 0:
                # Calculate median circumference per VEGETATION_KEY
                median_check = circ_check.groupby("VEGETATION_KEY")[circ_col].median().reset_index(name="median_circ")

                # Merge with original data
                circ_total = pd.merge(circ_check, median_check, how="inner", on="VEGETATION_KEY")

                # Apply outlier detection (4x and 1/4x median)
                circ_total["Upper_outliers"] = circ_total.apply(
                    lambda row: "outlier" if row[circ_col] > (row["median_circ"] * 4) else "ok",
                    axis=1,
                )
                circ_total["Lower_outliers"] = circ_total.apply(
                    lambda row: "outlier" if row[circ_col] < (row["median_circ"] / 4) else "ok",
                    axis=1,
                )

                # Filter to outliers only
                circ_outliers = circ_total[
                    (circ_total["Upper_outliers"] == "outlier") | (circ_total["Lower_outliers"] == "outlier")
                ].copy()

                st.metric("Circumference Outliers", len(circ_outliers))

                if len(circ_outliers) > 0:
                    st.error(
                        f"❌ {len(circ_outliers)} circumference measurements are outliers within their vegetation group"
                    )

                    # Determine which outlier type
                    def get_circ_outlier_type(row):
                        if row.get("Upper_outliers") == "outlier":
                            return "Too Large"
                        elif row.get("Lower_outliers") == "outlier":
                            return "Too Small"
                        else:
                            return "Unknown"

                    circ_outliers["Outlier_Type"] = circ_outliers.apply(get_circ_outlier_type, axis=1)

                    # Build display columns safely - use CIRCUMFERENCE_KEY for circumference data
                    display_cols = []
                    for col in [
                        "CIRCUMFERENCE_KEY",
                        "enumerator",
                        "tree_name",
                        circ_col,
                        "median_circ",
                        "Outlier_Type",
                        "tree_year_planted",
                    ]:
                        if col in circ_outliers.columns:
                            display_cols.append(col)

                    if len(display_cols) > 0:
                        display_df = circ_outliers[display_cols].copy()
                        display_df.insert(0, "#", range(1, len(display_df) + 1))

                        st.dataframe(
                            display_df.sort_values(circ_col, ascending=False)
                            if circ_col in display_cols
                            else display_df,
                            use_container_width=True,
                            height=min(400, len(circ_outliers) * 35 + 38),
                            hide_index=True,
                        )

                        # Download option
                        st.download_button(
                            label="📥 Download Circumference Outliers CSV",
                            data=circ_outliers[display_cols].to_csv(index=False),
                            file_name="circumference_outliers.csv",
                            mime="text/csv",
                        )
                    else:
                        st.warning("No displayable columns available")
                else:
                    st.success("✅ No circumference outliers detected")
            else:
                st.info("ℹ️ No valid circumference data with VEGETATION_KEY available")
        else:
            st.info("ℹ️ No circumference columns (circumference_bh or circumference_10cm) found")
    else:
        st.info("ℹ️ Complete dataset with VEGETATION_KEY not available")

    st.markdown("---")

    # CHECK 3: Suspicious circumference by age
    st.markdown("#### 3️⃣ Suspicious Circumference vs Tree Age ")
    st.caption(
        f"Cross-validates circumference against tree age. Young trees (<5 years) with circumference >{young_tree_circ}cm, or trees <15 years with circumference >300cm are flagged. These combinations are biologically implausible and likely indicate data entry errors (e.g., entering diameter instead of circumference, or incorrect planting year)."
    )

    if has_complete:
        complete_with_enum = merge_with_enumerator(complete_df, filtered_gdf)

        # Determine circumference column
        if "circumference_bh" in complete_with_enum.columns:
            circ_col = "circumference_bh"
            circ_data = complete_with_enum[complete_with_enum[circ_col].notna()].copy()
        elif "circumference_10cm" in complete_with_enum.columns:
            circ_col = "circumference_10cm"
            circ_data = complete_with_enum[complete_with_enum[circ_col].notna()].copy()
        else:
            circ_data = pd.DataFrame()

        if len(circ_data) > 0 and "tree_year_planted" in circ_data.columns:
            # Calculate age
            circ_data = calculate_tree_age(circ_data)

            # Add tree_name column using utility function
            from utils.data_merge_utils import add_tree_name_column

            circ_data = add_tree_name_column(circ_data)

            if circ_data["tree_age"].notna().any():
                # Detect suspicious
                circ_data = detect_suspicious_circumference_by_age(
                    circ_data,
                    circ_col=circ_col,
                    young_tree_circ_threshold=young_tree_circ,
                    young_tree_age_threshold=5,
                    large_circ_threshold=300,
                    large_circ_age_threshold=15,
                    species_col=species_col,
                    species_filter=None,  # No species filter - analyze all species
                )

                suspicious = circ_data[circ_data["suspicious"] == True].copy()

                st.metric("Suspicious Circumferences", len(suspicious))

                if len(suspicious) > 0:
                    st.error(f"❌ {len(suspicious)} trees have unrealistic circumference for their age")

                    # Ensure enumerator and SubmissionDate are available from filtered_gdf
                    if "subplot_id" in suspicious.columns:
                        merge_cols = ["subplot_id"]
                        if "enumerator" in filtered_gdf.columns and "enumerator" not in suspicious.columns:
                            merge_cols.append("enumerator")
                        if "SubmissionDate" in filtered_gdf.columns and "SubmissionDate" not in suspicious.columns:
                            merge_cols.append("SubmissionDate")
                        if len(merge_cols) > 1:
                            enum_date_map = filtered_gdf[merge_cols].drop_duplicates()
                            suspicious = suspicious.merge(enum_date_map, on="subplot_id", how="left")

                    # Build display columns safely - use CIRCUMFERENCE_KEY for circumference data
                    display_cols = []
                    for col in [
                        "CIRCUMFERENCE_KEY",
                        "enumerator",
                        "SubmissionDate",
                        "tree_name",
                        circ_col,
                        "tree_age",
                        "tree_height_m",
                    ]:
                        if col and col in suspicious.columns:
                            display_cols.append(col)

                    if len(display_cols) > 0:
                        st.dataframe(
                            (
                                suspicious[display_cols].sort_values(circ_col, ascending=False)
                                if circ_col in display_cols
                                else suspicious[display_cols]
                            ),
                            use_container_width=True,
                            height=min(400, len(suspicious) * 35 + 38),
                        )
                    else:
                        st.warning("No displayable columns available")
                else:
                    st.success("✅ No suspicious circumference-age combinations detected")
            else:
                st.info("ℹ️ Could not calculate tree age from planting year")
        else:
            st.info("ℹ️ Circumference or planting year data not available")
    else:
        st.info("ℹ️ Complete dataset not available")

    st.markdown("---")

    # CHECK 4: Tree Measurements Scatter Plot
    st.markdown("#### 4️⃣ Tree Measurements Analysis")
    st.caption(
        "Interactive scatter plot showing the relationship between tree height and circumference. Each point represents one measurement, sized by stem count and colored by species. Look for outliers in unexpected regions (e.g., very tall trees with thin circumference, or very thick trees that are short). Hover over points for details."
    )

    if has_complete and species_col:
        complete_with_enum = merge_with_enumerator(complete_df, filtered_gdf)

        # Calculate tree age
        if "tree_year_planted" in complete_with_enum.columns:
            complete_with_enum = calculate_tree_age_corrected(complete_with_enum)

        # Determine circumference column
        circ_col = None
        if "circumference_bh" in complete_with_enum.columns:
            circ_col = "circumference_bh"
        elif "circumference_10cm" in complete_with_enum.columns:
            circ_col = "circumference_10cm"

        # Check required columns
        required_cols = [
            "tree_height_m",
            circ_col,
            "nr_stems_bh",
            species_col,
            "tree_age",
        ]
        available_cols = [col for col in required_cols if col and col in complete_with_enum.columns]

        if len(available_cols) >= 4:  # Need at least height, circ, stems, species
            # Ensure enumerator is available from filtered_gdf if not already present
            if "enumerator" not in complete_with_enum.columns and "subplot_id" in complete_with_enum.columns:
                if "enumerator" in filtered_gdf.columns:
                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                    complete_with_enum = complete_with_enum.merge(enum_map, on="subplot_id", how="left")

            # Add hover columns (enumerator and key) if available
            hover_cols = []
            if "enumerator" in complete_with_enum.columns:
                hover_cols.append("enumerator")
            if "CIRCUMFERENCE_KEY" in complete_with_enum.columns:
                hover_cols.append("CIRCUMFERENCE_KEY")
            elif "MEASUREMENT_KEY" in complete_with_enum.columns:
                hover_cols.append("MEASUREMENT_KEY")

            # Prepare data for plotting (include hover columns)
            plot_data = complete_with_enum[available_cols + hover_cols].copy()

            # Remove rows with NaN in critical columns
            plot_data = plot_data.dropna(subset=["tree_height_m", circ_col, "nr_stems_bh"])

            if len(plot_data) > 0:
                # User controls
                col1, col2, col3 = st.columns(3)

                with col1:
                    # Build X-axis options from available columns
                    x_options = []
                    for col in ["tree_age", circ_col, "nr_stems_bh"]:
                        if col and col in plot_data.columns:
                            x_options.append(col)

                    if len(x_options) == 0:
                        st.error("No valid X-axis options available")
                        st.stop()

                    x_axis = st.selectbox(
                        "X-axis",
                        options=x_options,
                        index=0,
                        help="Select variable for X-axis",
                    )

                with col2:
                    # Build Y-axis options from available columns
                    y_options = []
                    for col in ["tree_height_m", circ_col, "nr_stems_bh"]:
                        if col and col in plot_data.columns:
                            y_options.append(col)

                    if len(y_options) == 0:
                        st.error("No valid Y-axis options available")
                        st.stop()

                    y_axis = st.selectbox(
                        "Y-axis",
                        options=y_options,
                        index=0,
                        help="Select variable for Y-axis",
                    )

                with col3:
                    # Build Size options from available columns
                    size_options = []
                    for col in ["nr_stems_bh", circ_col, "tree_height_m"]:
                        if col and col in plot_data.columns:
                            size_options.append(col)

                    if len(size_options) == 0:
                        st.error("No valid size options available")
                        st.stop()

                    size_var = st.selectbox(
                        "Size by",
                        options=size_options,
                        index=0,
                        help="Select variable for point size",
                    )

                # Create scatter plot with plotly
                import plotly.express as px

                # Clean data for selected variables (use unique columns to avoid DataFrame ambiguity)
                # Include hover columns in plot_cols
                plot_cols = list(dict.fromkeys([x_axis, y_axis, size_var, species_col] + hover_cols))
                plot_subset = plot_data[plot_cols].dropna(subset=[x_axis, y_axis, size_var, species_col])

                if len(plot_subset) > 0:
                    # Build hover_data dict with available columns
                    hover_data_dict = {
                        x_axis: True,
                        y_axis: True,
                        size_var: True,
                        species_col: True,
                    }
                    # Add enumerator and key to hover if available
                    if "enumerator" in plot_subset.columns:
                        hover_data_dict["enumerator"] = True
                    if "CIRCUMFERENCE_KEY" in plot_subset.columns:
                        hover_data_dict["CIRCUMFERENCE_KEY"] = True
                    elif "MEASUREMENT_KEY" in plot_subset.columns:
                        hover_data_dict["MEASUREMENT_KEY"] = True

                    # Create figure
                    fig = px.scatter(
                        plot_subset,
                        x=x_axis,
                        y=y_axis,
                        size=size_var,
                        color=species_col,
                        hover_data=hover_data_dict,
                        title=f"{y_axis} vs {x_axis} (sized by {size_var})",
                        height=600,
                        template="plotly_white",
                    )

                    # Update layout
                    fig.update_layout(
                        xaxis_title=x_axis.replace("_", " ").title(),
                        yaxis_title=y_axis.replace("_", " ").title(),
                        legend_title=species_col.replace("_", " ").title(),
                        showlegend=True,
                        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
                    )

                    # Update traces for better visibility
                    fig.update_traces(marker=dict(line=dict(width=0.5, color="DarkSlateGrey"), opacity=0.7))

                    st.plotly_chart(fig, use_container_width=True)

                    # Summary stats
                    st.markdown("##### 📊 Summary Statistics ")
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric("Total Trees", len(plot_subset))

                    with col2:
                        st.metric("Unique Species", plot_subset[species_col].nunique())

                    with col3:
                        if "tree_age" in plot_subset.columns:
                            avg_age = plot_subset["tree_age"].mean()
                            st.metric("Avg Age", f"{avg_age:.1f} years")
                        else:
                            st.metric(
                                "Avg Height",
                                f"{plot_subset['tree_height_m'].mean():.1f}m",
                            )

                    with col4:
                        if circ_col in plot_subset.columns:
                            avg_circ = plot_subset[circ_col].mean()
                            st.metric("Avg Circumference", f"{avg_circ:.1f}cm")
                        else:
                            st.metric("Avg Stems", f"{plot_subset['nr_stems_bh'].mean():.1f}")

                    # Download data
                    csv = plot_subset.to_csv(index=False)
                    st.download_button(
                        label="📥 Download plot data",
                        data=csv,
                        file_name="tree_measurements_scatter.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("⚠️ Not enough data after filtering for selected variables")
            else:
                st.info("ℹ️ No complete records with height, circumference, and stem data")
        else:
            st.warning(f"⚠️ Missing required columns. Available: {', '.join(available_cols)}")
    else:
        st.info("ℹ️ Complete dataset or species column not available for visualization")

st.markdown("---")
st.markdown("### 📥 Export Quality Check Results")

col1, col2 = st.columns(2)

with col1:
    if st.button("📥 Export to Excel (All Checks)", use_container_width=True, type="primary"):
        try:
            from io import BytesIO

            # Create Excel writer
            output = BytesIO()
            sheets_created = 0
            # Track dataframes for column width adjustment
            sheet_dataframes = {}

            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                # Sheet 1: Coverage-only subplots
                try:
                    if "coverage_only" in locals() and len(coverage_only) > 0:
                        export_df = coverage_only.copy()
                        if "geometry" in export_df.columns:
                            export_df = export_df.drop(columns=["geometry"])
                        sheet_name = "Coverage Only"
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except:
                    pass

                # Sheet 2: Primary trees with 'other'
                try:
                    if "primary_trees" in locals() and len(primary_trees) > 0:
                        export_df = primary_trees.copy()
                        if "geometry" in export_df.columns:
                            export_df = export_df.drop(columns=["geometry"])
                        sheet_name = "Primary Trees Other"
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except:
                    pass

                # Sheet 3: Young trees with 'other'
                try:
                    if "young_trees_other" in locals() and len(young_trees_other) > 0:
                        export_df = young_trees_other.copy()
                        if "geometry" in export_df.columns:
                            export_df = export_df.drop(columns=["geometry"])
                        sheet_name = "Young Trees Other"
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except:
                    pass

                # Sheet 4: Non-primary trees with 'other'
                try:
                    if "non_primary_trees" in locals() and len(non_primary_trees) > 0:
                        export_df = non_primary_trees.copy()
                        if "geometry" in export_df.columns:
                            export_df = export_df.drop(columns=["geometry"])
                        sheet_name = "Non-Primary Trees Other"
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except:
                    pass

                # Summary sheet if no data
                if sheets_created == 0:
                    summary_df = pd.DataFrame({"Note": ["No flagged records found in quality checks"]})
                    sheet_name = "Summary"
                    summary_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    sheet_dataframes[sheet_name] = summary_df

                # Adjust column widths for all sheets
                try:
                    for sheet_name, df in sheet_dataframes.items():
                        if sheet_name in writer.sheets:
                            worksheet = writer.sheets[sheet_name]
                            adjust_excel_column_widths(worksheet, df)
                except Exception:
                    # Column width adjustment is optional - don't fail export if it errors
                    pass

            output.seek(0)

            st.success(f"✅ Created Excel file with {sheets_created} sheet(s)")

            st.download_button(
                label="💾 Download Excel File",
                data=output.getvalue(),
                file_name=f"{config.PARTNER}_quality_checks_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

        except Exception as e:
            st.error(f"Error creating export: {str(e)}")

with col2:
    if st.button("📥 Export Filtered Vegetation Data (CSV)", use_container_width=True):
        try:
            # Export the filtered vegetation data
            export_df = veg_with_enum.copy()

            # Remove geometry column if exists
            if "geometry" in export_df.columns:
                export_df = export_df.drop(columns=["geometry"])

            # Convert to CSV
            csv = export_df.to_csv(index=False)

            st.download_button(
                label="💾 Download CSV File",
                data=csv,
                file_name=f"{config.PARTNER}_vegetation_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        except Exception as e:
            st.error(f"Error creating CSV export: {str(e)}")
