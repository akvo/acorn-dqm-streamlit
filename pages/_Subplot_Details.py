"""
Subplot Details Page - Vegetation Quality Checks (Error-Focused)
Based on Vegetation_checks.ipynb logic
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import config
from ui.components import show_header, create_sidebar_filters, show_sidebar_info, get_total_measured_subplots
from utils.data_merge_utils import (
    merge_with_enumerator,
    calculate_tree_age,
    get_species_column,
    add_tree_name_column,
)
from utils.vegetation_validation import (
    get_missing_subplots,
    check_unidentified_species,
    check_coverage_only_subplots,
    get_young_trees_with_other,
    get_primary_trees_with_other,
    get_non_primary_trees_with_other,
    validate_species_lists,
    detect_stem_outliers,
    detect_height_outliers,
    detect_circumference_outliers,
    detect_suspicious_circumference_by_age,
    check_tall_trees,
)
from utils.export_helpers import adjust_excel_column_widths

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

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Header
show_header()

st.markdown("## 🌳 Subplot Details & Vegetation Quality Checks")
st.caption("Error-focused analysis with adjustable thresholds")

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
    st.error(
        "❌ Vegetation data not available. Upload complete Excel file with all 5 sheets."
    )
    st.stop()

st.markdown("---")

# ============================================
# GET AND MERGE DATA
# ============================================

# Get raw data
plots_df_all = raw_data.get("plots_subplots", pd.DataFrame())
veg_df_all = raw_data["plots_subplots_vegetation"].copy()
meas_df_all = (
    raw_data.get("plots_subplots_vegetation_measurements", pd.DataFrame())
    if has_measurements
    else pd.DataFrame()
)
complete_df_all = (
    raw_data.get("complete", pd.DataFrame()) if has_complete else pd.DataFrame()
)

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

# ============================================
# SIDEBAR: FUZZY MATCHING FOR "OTHER" SPECIES
# ============================================

st.sidebar.markdown("---")
st.sidebar.markdown("## 🔍 Fuzzy Matching")
st.sidebar.caption("Find 'other' species that match existing species names")

fuzzy_threshold = st.sidebar.slider(
    "Matching Threshold (%)",
    min_value=50,
    max_value=100,
    value=90,
    step=5,
    help="Higher values = stricter matching. 90% is recommended to catch typos and variations."
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
        "⚠️ Outliers & Suspicious",
        "🚫 Missing Data",
        "📏 Measurements",
        "🌲 Tree Classification",
        "🌿 Species Lists",
    ]
)

# ============================================
# TAB 2: MISSING DATA
# ============================================

with tabs[1]:
    st.markdown("### 🚫 Missing Vegetation and Measurement Data")

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
            lambda x: int(re.search(r'\[(\d+)\]', str(x)).group(1)) if re.search(r'\[(\d+)\]', str(x)) else 999
        )

        # Convert measured_subplots to int
        temp_plots["measured_subplots"] = temp_plots["measured_subplots"].apply(
            lambda x: int(x) if pd.notna(x) else 999
        )

        # Only include subplots where subplot_number <= measured_subplots
        plots_df_measured = temp_plots[
            temp_plots["subplot_number"] <= temp_plots["measured_subplots"]
        ].copy()

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
    st.caption("Check density of trees and coverage percentage in subplots")

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

    if (
        len(available_cols) >= 3
    ):  # Need at least SUBPLOT_KEY, vegetation_type_number, coverage_vegetation
        # Create base with ONLY MEASURED subplots (exclude unmeasured subplots)
        # Extract subplot number from subplot_id and compare to measured_subplots
        if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
            import re

            # Create temporary dataframe with subplot info
            temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()

            # Extract subplot number from subplot_id (e.g., "uuid.../sub_plot[12]" -> 12)
            temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                lambda x: int(re.search(r'\[(\d+)\]', str(x)).group(1)) if re.search(r'\[(\d+)\]', str(x)) else 999
            )

            # Convert measured_subplots to int
            temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(
                lambda x: int(x) if pd.notna(x) else 999
            )

            # Only include subplots where subplot_number <= measured_subplots
            measured_subplot_ids = temp_df[
                temp_df["subplot_number"] <= temp_df["measured_subplots"]
            ]["subplot_id"].unique()

            all_subplots_df = pd.DataFrame({"SUBPLOT_KEY": measured_subplot_ids})
        else:
            # Fallback: use all subplot keys
            all_subplot_keys = (
                filtered_gdf["subplot_id"].unique()
                if "subplot_id" in filtered_gdf.columns
                else []
            )
            all_subplots_df = pd.DataFrame({"SUBPLOT_KEY": all_subplot_keys})

        # Left join with vegetation data (keeps all 176 subplots, fills missing with NaN)
        density = all_subplots_df.merge(
            veg_df_actual[available_cols], on="SUBPLOT_KEY", how="left"
        )

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
            (density_df["vegetation_type_number"] == 0)
            | (density_df["vegetation_type_number"].isna())
        ].copy()

        # Distinguish between:
        # 1. Coverage-only: Have vegetation records but 0 trees
        # 2. Empty: Have NO vegetation records at all
        subplots_with_records = set(veg_df_actual["SUBPLOT_KEY"].unique())

        # Coverage-only: in veg_df_actual AND have 0/NaN trees
        subplots_coverage = subplots_zero_trees[
            subplots_zero_trees["SUBPLOT_KEY"].isin(subplots_with_records)
        ].copy()

        # Empty: NOT in veg_df_actual (no records at all)
        subplots_empty = subplots_zero_trees[
            ~subplots_zero_trees["SUBPLOT_KEY"].isin(subplots_with_records)
        ].copy()

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
            st.info(
                f"ℹ️ {len(subplots_coverage)} subplots have coverage data but no trees"
            )

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

                st.dataframe(
                    display_df, use_container_width=True, height=300, hide_index=True
                )

        # Show empty subplots
        if len(subplots_empty) > 0:
            st.warning(
                f"⚠️ {len(subplots_empty)} subplots have NO vegetation data collected"
            )

            with st.expander("View empty subplots"):
                display_df = subplots_empty[["SUBPLOT_KEY"]].copy()
                display_df.insert(0, "#", range(1, len(display_df) + 1))

                st.dataframe(
                    display_df, use_container_width=True, height=300, hide_index=True
                )

        # Show full density table
        with st.expander("View all subplot density data"):
            # Add row numbers
            display_df = density_df.copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))
            st.dataframe(
                display_df, use_container_width=True, height=400, hide_index=True
            )

    else:
        st.error("❌ Required columns not found for density analysis")
        st.write(f"Available columns: {veg_df_actual.columns.tolist()[:20]}")

    st.markdown("---")

    # CHECK 2: Coverage-only subplots with measurements (potential data quality issue)
    st.markdown("#### 3️⃣ Coverage-Only Subplots with Measurements")
    st.caption(
        "Subplots marked as 100% coverage but have measurements. This may indicate enumerators changed their answers."
    )

    if has_measurements:
        # Coverage-only subplots: subplots with vegetation records but 0 trees
        coverage_only = pd.DataFrame()

        if "vegetation_type_number" in veg_df_actual.columns:
            # Coverage-only means: subplot has vegetation records but ALL have NULL vegetation_type_number
            veg_check = veg_df_actual.groupby("SUBPLOT_KEY")["vegetation_type_number"].agg([
                ("has_trees", lambda x: x.notna().any())
            ]).reset_index()

            # Coverage-only = has_trees is False
            coverage_only_keys = veg_check[~veg_check["has_trees"]]["SUBPLOT_KEY"]

            # Get coverage-only subplots with key columns
            if len(coverage_only_keys) > 0:
                coverage_only = (
                    veg_df_actual[veg_df_actual["SUBPLOT_KEY"].isin(coverage_only_keys)]
                    .drop_duplicates(subset=["SUBPLOT_KEY"])
                    [["SUBPLOT_KEY", "enumerator"] if "enumerator" in veg_df_actual.columns else ["SUBPLOT_KEY"]]
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
            if (
                "VEGETATION_KEY" in veg_df_actual.columns
                and "VEGETATION_KEY" in meas_df.columns
            ):
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
            .drop_duplicates(subset=["SUBPLOT_KEY"])
            [["SUBPLOT_KEY", "enumerator"] if "enumerator" in veg_df_actual.columns else ["SUBPLOT_KEY"]]
            .copy()
        )

        # MAIN CHECK: Coverage-only subplots that DO NOT match missing measurements
        # These are subplots marked as coverage-only but actually have measurements
        if len(coverage_only) > 0 and len(missing_veg_df) > 0:
            veg_reverted = coverage_only[
                ~coverage_only["SUBPLOT_KEY"].isin(missing_veg_df["SUBPLOT_KEY"])
            ].copy()
        else:
            veg_reverted = pd.DataFrame()

        # Display the reverted subplots
        st.metric("Coverage-Only with Measurements", len(veg_reverted))

        if len(veg_reverted) > 0:
            st.warning(
                f"⚠️ Found {len(veg_reverted)} subplot(s) marked as 100% coverage but have measurements. "
                "This suggests data was changed after initial collection."
            )

            display_cols = [
                col for col in ["SUBPLOT_KEY", "enumerator"]
                if col in veg_reverted.columns
            ]

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

    st.markdown("---")

    # CHECK 4: Unknown/Unidentified Species
    st.markdown("#### 4️⃣ Unknown/Unidentified Species")
    st.caption(
        "Vegetation records marked as 'other' that need botanical verification and proper identification"
    )

    # Check for unidentified species
    unknown_species = check_unidentified_species(veg_df_actual)

    # Merge with enumerator info
    if len(unknown_species) > 0:
        unknown_species = merge_with_enumerator(unknown_species, filtered_gdf)
        unknown_species = add_tree_name_column(unknown_species)

    st.metric("Unknown Species Records", len(unknown_species))

    if len(unknown_species) > 0:
        st.warning(
            f"⚠️ Found {len(unknown_species)} vegetation record(s) with unidentified species. "
            "These need botanical verification and proper species identification."
        )

        # Build display columns
        display_cols = []
        for col in [
            "SUBPLOT_KEY",
            "enumerator",
            "VEGETATION_KEY",
            "tree_name",
            "vegetation_species_type",
            "woody_species",
            "non_woody_species",
            "other_species",
            "language_other_species",
            "vegetation_type_number",
            "vegetation_type_primary",
        ]:
            if col in unknown_species.columns:
                display_cols.append(col)

        if len(display_cols) > 0:
            # Add row numbers
            display_df = unknown_species[display_cols].copy()
            display_df.insert(0, "#", range(1, len(display_df) + 1))

            st.dataframe(
                display_df,
                use_container_width=True,
                height=min(400, len(unknown_species) * 35 + 38),
                hide_index=True,
            )
        else:
            st.warning("⚠️ No display columns available")
            st.dataframe(unknown_species.head(), use_container_width=True)
    else:
        st.success("✅ All vegetation species are properly identified")

    st.markdown("---")

# ============================================
# TAB 4: TREE CLASSIFICATION
# ============================================

with tabs[3]:
    st.markdown("### 🌲 Tree Classification Quality Check")
    st.caption(
        "Validate primary vs young tree designation - showing 'other' species only"
    )

    # Use RAW vegetation data like notebook does (m_veg)
    # Get tree lists using utility functions on RAW data
    # These match notebook logic exactly with string values
    primary_trees = get_primary_trees_with_other(
        veg_df, primary_value="yes_primary_group"
    )
    non_primary_trees = get_non_primary_trees_with_other(veg_df, non_primary_value="no")
    young_trees_other = get_young_trees_with_other(
        veg_df, young_tree_value="yes_groupbelow1.3"
    )

    # Merge with enumerator for display
    if len(young_trees_other) > 0:
        young_trees_other = merge_with_enumerator(
            young_trees_other, filtered_gdf
        )
        young_trees_other = add_tree_name_column(young_trees_other)
    if len(primary_trees) > 0:
        primary_trees = merge_with_enumerator(
            primary_trees, filtered_gdf
        )
        primary_trees = add_tree_name_column(primary_trees)
    if len(non_primary_trees) > 0:
        non_primary_trees = merge_with_enumerator(
            non_primary_trees, filtered_gdf
        )
        non_primary_trees = add_tree_name_column(non_primary_trees)

    # Calculate totals
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Primary Trees (with 'other')", len(primary_trees))

    with col2:
        st.metric("Non-Primary Trees (with 'other')", len(non_primary_trees))

    with col3:
        st.metric("Young Trees (with 'other')", len(young_trees_other))

    st.markdown("---")

    # Show lists in tabs
    tree_tabs = st.tabs(["Primary Trees", "Young Trees (other)", "Non-Primary Trees"])

    with tree_tabs[0]:
        st.markdown("**Primary Tree List (with 'other' species)**")
        st.caption(
            f"Trees marked as 'yes_primary_group' with woody_species = 'other' - Total: {len(primary_trees)} trees (Notebook: 668 rows)"
        )

        if len(primary_trees) > 0:
            # Use notebook's collector_primary_list columns
            # Note: tree_name now comes from other_species, so we don't need to show other_species separately
            display_cols = []
            for col in [
                "SUBPLOT_KEY",
                "tree_name",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in primary_trees.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(
                    primary_trees[display_cols], use_container_width=True, height=400
                )
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(primary_trees.columns)}")
        else:
            st.info("No primary trees with 'other' species found")

    with tree_tabs[1]:
        st.markdown("**Young Tree List (with 'other' species)**")
        st.caption(
            f"Trees marked as 'yes_groupbelow1.3' with woody_species = 'other' - Total: {len(young_trees_other)} trees (Notebook: 125 rows)"
        )

        if len(young_trees_other) > 0:
            # Use notebook's collector_list_trees_young columns
            # Note: tree_name now comes from other_species, so we don't need to show other_species separately
            display_cols = []
            for col in [
                "SUBPLOT_KEY",
                "tree_name",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in young_trees_other.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(
                    young_trees_other[display_cols],
                    use_container_width=True,
                    height=400,
                )
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(young_trees_other.columns)}")
        else:
            st.info("No young trees with 'other' woody species found")

    with tree_tabs[2]:
        st.markdown("**Non-Primary Tree List (with 'other' species)**")
        st.caption(
            f"Trees marked as 'no' (non-primary) with woody_species = 'other' - Total: {len(non_primary_trees)} trees (Notebook: 240 rows)"
        )

        if len(non_primary_trees) > 0:
            # Use notebook's collector_list_trees columns
            # Note: tree_name now comes from other_species, so we don't need to show other_species separately
            display_cols = []
            for col in [
                "SUBPLOT_KEY",
                "tree_name",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in non_primary_trees.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(
                    non_primary_trees[display_cols],
                    use_container_width=True,
                    height=400,
                )
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(non_primary_trees.columns)}")
        else:
            st.info("No non-primary trees with 'other' species found")

# ============================================
# TAB 5: SPECIES LISTS
# ============================================

with tabs[4]:
    st.markdown("### 🌿 Species Lists Validation")
    st.caption("Check species categorization by type")

    species_lists = validate_species_lists(veg_with_enum)

    # Add tree_name column to all species lists
    woody = species_lists.get("woody", pd.DataFrame())
    if len(woody) > 0:
        woody = add_tree_name_column(woody)

    palm = species_lists.get("palm", pd.DataFrame())
    if len(palm) > 0:
        palm = add_tree_name_column(palm)

    bamboo = species_lists.get("bamboo", pd.DataFrame())
    if len(bamboo) > 0:
        bamboo = add_tree_name_column(bamboo)

    banana = species_lists.get("banana", pd.DataFrame())
    if len(banana) > 0:
        banana = add_tree_name_column(banana)

    living_fences = species_lists.get("living_fences", pd.DataFrame())
    if len(living_fences) > 0:
        living_fences = add_tree_name_column(living_fences)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Woody Species", len(woody))

    with col2:
        st.metric("Palm Species", len(palm))

    with col3:
        st.metric("Bamboo Species", len(bamboo))

    with col4:
        st.metric("Banana Species", len(banana))

    with col5:
        st.metric("Living Fences", len(living_fences))

    st.markdown("---")

    # Show each list in tabs
    species_tabs = st.tabs(["Woody", "Palm", "Bamboo", "Banana", "Living Fences"])

    with species_tabs[0]:
        if len(woody) > 0:
            st.markdown(f"**Woody Species List** ({len(woody)} records)")
            # Only include columns that exist
            display_cols = []
            for col in [
                "VEGETATION_KEY",
                "enumerator",
                "tree_name",
                "woody_species",
                "vegetation_type_number",
            ]:
                if col in woody.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(woody[display_cols], use_container_width=True, height=400)
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(woody.columns)}")
        else:
            st.info("No woody species found")

    with species_tabs[1]:
        if len(palm) > 0:
            st.markdown(f"**Palm Species List** ({len(palm)} records)")
            # Only include columns that exist
            display_cols = []
            for col in [
                "VEGETATION_KEY",
                "enumerator",
                "tree_name",
                "palm_species",
                "vegetation_type_number",
            ]:
                if col in palm.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(palm[display_cols], use_container_width=True, height=400)
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(palm.columns)}")
        else:
            st.info("No palm species found")

    with species_tabs[2]:
        if len(bamboo) > 0:
            st.markdown(f"**Bamboo Species List** ({len(bamboo)} records)")
            # Only include columns that exist
            display_cols = []
            for col in [
                "VEGETATION_KEY",
                "enumerator",
                "tree_name",
                "bamboo_species",
                "vegetation_type_number",
            ]:
                if col in bamboo.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(bamboo[display_cols], use_container_width=True, height=400)
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(bamboo.columns)}")
        else:
            st.info("No bamboo species found")

    with species_tabs[3]:
        if len(banana) > 0:
            st.markdown(f"**Banana Species List** ({len(banana)} records)")
            # Only include columns that exist
            display_cols = []
            for col in [
                "VEGETATION_KEY",
                "enumerator",
                "tree_name",
                "banana_species",
                "vegetation_type_number",
            ]:
                if col in banana.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(banana[display_cols], use_container_width=True, height=400)
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(banana.columns)}")
        else:
            st.info("No banana species found")

    with species_tabs[4]:
        if len(living_fences) > 0:
            st.markdown(f"**Living Fences Species List** ({len(living_fences)} records)")
            # Only include columns that exist
            display_cols = []
            for col in [
                "VEGETATION_KEY",
                "enumerator",
                "tree_name",
                "living_fences_species",
                "vegetation_type_number",
            ]:
                if col in living_fences.columns:
                    display_cols.append(col)

            if len(display_cols) > 0:
                st.dataframe(living_fences[display_cols], use_container_width=True, height=400)
            else:
                st.warning("⚠️ No display columns available")
                st.write(f"Available columns: {list(living_fences.columns)}")
        else:
            st.info("No living fences species found")

    st.markdown("---")

    # ============================================
    # FUZZY MATCHING FOR "OTHER" SPECIES
    # ============================================

    st.markdown("### 🔍 Fuzzy Matching for 'Other' Species")
    st.caption(f"Finding 'other' entries that match existing species (threshold: {fuzzy_threshold}%)")

    if not FUZZY_AVAILABLE:
        st.warning("⚠️ Fuzzy matching library not available. Install 'rapidfuzz' or 'fuzzywuzzy' to enable this feature.")
        st.code("pip install rapidfuzz")
    else:
        # Load official species lists from TSV files
        import os

        species_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "species", config.PARTNER)

        valid_species_by_type = {}

        # Define species files to load
        species_files = {
            "woody": "woody_species.tsv",
            "bamboo": "bamboo_species.tsv",
            "banana": "banana_species.tsv",
            "palm": "palm_species.tsv",
            "living_fences": "living_fences_species.tsv",
        }

        # Track which files were loaded
        files_loaded = []
        files_missing = []

        # Load each species file
        for species_type, filename in species_files.items():
            try:
                filepath = os.path.join(species_dir, filename)
                if os.path.exists(filepath):
                    species_ref = pd.read_csv(filepath, sep="\t")
                    # Use both value and label for matching
                    species_list = []
                    if "label" in species_ref.columns:
                        species_list.extend(list(species_ref["label"].dropna()))
                    if "value" in species_ref.columns:
                        species_list.extend(list(species_ref["value"].dropna()))
                    valid_species_by_type[species_type] = species_list
                    if len(species_list) > 0:
                        files_loaded.append(species_type)
                else:
                    valid_species_by_type[species_type] = []
                    files_missing.append(species_type)
            except Exception as e:
                valid_species_by_type[species_type] = []
                files_missing.append(species_type)

        # Show info about loaded files
        if files_missing:
            st.caption(f"ℹ️ Species files not found for: {', '.join(files_missing)}")

        # Combine all valid species for general matching
        all_valid_species = []
        for species_list in valid_species_by_type.values():
            all_valid_species.extend(species_list)

        # Remove duplicates and "other" entries, filter out NaN
        all_valid_species = sorted(list(set([
            s for s in all_valid_species
            if pd.notna(s) and str(s).lower() not in ['other', 'nan', 'none', '']
            and 'other' not in str(s).lower()
        ])))

        if len(all_valid_species) == 0:
            st.info("ℹ️ No valid species found to match against")
        else:
            # Show reference species counts
            counts_parts = []
            for species_type in ["woody", "bamboo", "banana", "palm", "living_fences"]:
                count = len(valid_species_by_type.get(species_type, []))
                if count > 0:
                    counts_parts.append(f"{species_type.replace('_', ' ').title()}: {count}")
            counts_str = " | ".join(counts_parts) if counts_parts else "None"
            st.caption(f"📚 **Reference Species Loaded:** {counts_str} | **Total: {len(all_valid_species)}**")
            st.markdown("")

            # Define species columns mapping
            species_columns = {
                "woody_species": woody,
                "palm_species": palm,
                "bamboo_species": bamboo,
                "banana_species": banana,
                "living_fences_species": living_fences,
            }

            # Find "other" entries with their specified text
            fuzzy_matches_list = []

            for species_type, species_df in species_columns.items():
                if len(species_df) == 0 or species_type not in species_df.columns:
                    continue

                # Find entries where species is "other"
                # The actual "other" text is in columns: other_species and language_other_species
                has_other_species = "other_species" in species_df.columns
                has_language_other = "language_other_species" in species_df.columns

                if not has_other_species and not has_language_other:
                    continue

                # Filter rows where the species type contains "other"
                other_rows = species_df[
                    (species_df[species_type].notna()) &
                    (species_df[species_type].str.lower().str.contains("other", na=False))
                ].copy()

                if len(other_rows) > 0:
                    for _, row in other_rows.iterrows():
                        # Get text from other_species column
                        other_text = ""
                        if has_other_species and pd.notna(row.get("other_species")):
                            other_text = str(row["other_species"]).strip()

                        # Get text from language_other_species column
                        language_other_text = ""
                        if has_language_other and pd.notna(row.get("language_other_species")):
                            language_other_text = str(row["language_other_species"]).strip()

                        # Get date of collection
                        collection_date = row.get("SubmissionDate") or row.get("starttime") or row.get("date", "N/A")
                        if pd.notna(collection_date) and collection_date != "N/A":
                            try:
                                collection_date = pd.to_datetime(collection_date).strftime("%Y-%m-%d")
                            except:
                                pass

                        # Process other_species
                        if other_text and other_text.lower() not in ['nan', 'none', '']:
                            matches = process.extract(
                                other_text,
                                all_valid_species,
                                scorer=fuzz.ratio,
                                limit=3
                            )
                            good_matches = [m for m in matches if m[1] >= fuzzy_threshold]

                            if good_matches:
                                fuzzy_matches_list.append({
                                    "Type": species_type.replace("_species", "").title(),
                                    "Other Text Entered": other_text,
                                    "Source Column": "other_species",
                                    "Best Match": good_matches[0][0],
                                    "Match Score": f"{good_matches[0][1]}%",
                                    "Alternative Matches": ", ".join([f"{m[0]} ({m[1]}%)" for m in good_matches[1:]]) if len(good_matches) > 1 else "",
                                    "Enumerator": row.get("enumerator", "N/A"),
                                    "Date": collection_date,
                                    "VEGETATION_KEY": row.get("VEGETATION_KEY", "N/A")
                                })

                        # Process language_other_species
                        if language_other_text and language_other_text.lower() not in ['nan', 'none', '']:
                            matches = process.extract(
                                language_other_text,
                                all_valid_species,
                                scorer=fuzz.ratio,
                                limit=3
                            )
                            good_matches = [m for m in matches if m[1] >= fuzzy_threshold]

                            if good_matches:
                                fuzzy_matches_list.append({
                                    "Type": species_type.replace("_species", "").title(),
                                    "Other Text Entered": language_other_text,
                                    "Source Column": "language_other_species",
                                    "Best Match": good_matches[0][0],
                                    "Match Score": f"{good_matches[0][1]}%",
                                    "Alternative Matches": ", ".join([f"{m[0]} ({m[1]}%)" for m in good_matches[1:]]) if len(good_matches) > 1 else "",
                                    "Enumerator": row.get("enumerator", "N/A"),
                                    "Date": collection_date,
                                    "VEGETATION_KEY": row.get("VEGETATION_KEY", "N/A")
                                })

            if len(fuzzy_matches_list) == 0:
                st.success(f"✅ No 'other' species entries found matching threshold of {fuzzy_threshold}%")
            else:
                st.warning(f"⚠️ Found {len(fuzzy_matches_list)} 'other' entries that may match existing species")

                fuzzy_df = pd.DataFrame(fuzzy_matches_list)

                st.dataframe(
                    fuzzy_df,
                    use_container_width=True,
                    height=min(400, 50 + len(fuzzy_df) * 35),
                    column_config={
                        "Type": st.column_config.TextColumn("Species Type", width="small"),
                        "Other Text Entered": st.column_config.TextColumn("Text Entered as 'Other'", width="medium"),
                        "Source Column": st.column_config.TextColumn("Source", width="small"),
                        "Best Match": st.column_config.TextColumn("Best Match", width="medium"),
                        "Match Score": st.column_config.TextColumn("Score", width="small"),
                        "Alternative Matches": st.column_config.TextColumn("Other Possible Matches", width="large"),
                        "Enumerator": st.column_config.TextColumn("Enumerator", width="small"),
                        "Date": st.column_config.TextColumn("Date", width="small"),
                        "VEGETATION_KEY": st.column_config.TextColumn("Veg Key", width="small"),
                    }
                )

                st.caption("💡 **Tip:** These entries were marked as 'other' but closely match existing species. Consider updating them to use the standard species names.")

    st.markdown("---")

    # Coverage quality check
    st.markdown("#### 🌾 Coverage Quality Check")
    st.caption("Coverage should only be used for non-woody species (grasses, crops)")

    # Matches notebook logic:
    # coverage = tree_list where vegetation_type_woody == "nonwoody_coverage" OR vegetation_type_youngtree == "no_coverage"
    coverage_filter = pd.Series([False] * len(veg_df_actual), index=veg_df_actual.index)

    if "vegetation_type_woody" in veg_df_actual.columns:
        coverage_filter |= veg_df_actual["vegetation_type_woody"] == "nonwoody_coverage"

    if "vegetation_type_youngtree" in veg_df_actual.columns:
        coverage_filter |= veg_df_actual["vegetation_type_youngtree"] == "no_coverage"

    coverage = veg_df_actual[coverage_filter].copy()

    if len(coverage) > 0:
        # Add tree_name column
        coverage = add_tree_name_column(coverage)

        # Filter to records with 'other_species'
        collector_list_coverage = [
            "enumerator",
            "SUBPLOT_KEY",
            "tree_name",
            "other_species",
            "language_other_species",
            "coverage_vegetation",
        ]

        available_cols = [
            col for col in collector_list_coverage if col in coverage.columns
        ]
        enumerator_coverage = coverage[available_cols].copy()

        # Drop NaN in other_species
        if "other_species" in enumerator_coverage.columns:
            enumerator_coverage = enumerator_coverage.dropna(subset=["other_species"])

        # Calculate percentage
        percentage_cov = (
            (len(enumerator_coverage) / len(coverage) * 100) if len(coverage) > 0 else 0
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Coverage Records", len(coverage))

        with col2:
            st.metric("'Other' Species in Coverage", len(enumerator_coverage))

        with col3:
            if percentage_cov > 5:
                st.metric("Percentage", f"{percentage_cov:.1f}%", delta_color="inverse")
                st.error("❌ Exceeds 5% threshold")
            else:
                st.metric("Percentage", f"{percentage_cov:.1f}%")
                st.success("✅ Within acceptable range (<5%)")

        if len(enumerator_coverage) > 0:
            with st.expander(
                f"View {len(enumerator_coverage)} 'other' species in coverage"
            ):
                # Add row numbers
                display_df = enumerator_coverage.copy()
                display_df.insert(0, "#", range(1, len(display_df) + 1))

                st.dataframe(
                    display_df, use_container_width=True, height=300, hide_index=True
                )
    else:
        st.info("No coverage data found")

# ============================================
# TAB 3: MEASUREMENTS
# ============================================

with tabs[2]:
    st.markdown("### 📏 Measurement Quality Checks")

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(
        f"Using threshold: Stems > {stem_threshold}, Tall trees > {tall_tree_threshold}m"
    )

    # CHECK 1: Super Tall Trees Check
    st.markdown(f"#### 1️⃣ Super Tall Trees (> {tall_tree_threshold}m)")
    st.caption("Important to verify tall trees are realistic with planting age")

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
                super_tall = height_check[
                    height_check["tree_height_m"] > tall_tree_threshold
                ].copy()

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
        "From notebook: nr_stems_bh > 20 is suspicious (should be constrained to >40?)"
    )

    meas_with_enum = detect_stem_outliers(meas_with_enum, threshold=stem_threshold)
    high_stems = meas_with_enum[meas_with_enum["high_stems_bh"] == True]

    st.metric(f"Trees with > {stem_threshold} stems", len(high_stems))

    if len(high_stems) > 0:
        st.warning(f"⚠️ {len(high_stems)} trees with unusually high stem counts")

        display_cols = []
        for col in [
            "VEGETATION_KEY",
            "enumerator",
            "tree_name",
            "nr_stems_bh",
            "nr_stems_10cm",
            species_col,
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

    # CHECK 4: Height Homogeneity within Groups
    st.markdown("#### 4️⃣ Height Homogeneity Check")
    st.caption(
        "Check for outliers within tree groups - important to identify pruning or coppicing practices"
    )

    st.info(
        """
        **How Height Homogeneity Outliers are Calculated (Official Method):**
        1. **Apply filters**: Date range and enumerator filters from sidebar
        2. **Group by VEGETATION_KEY**: Trees are grouped by their vegetation group/type, NOT by species
        3. **Calculate Median**: The median height is calculated for each vegetation group
        4. **Flag Outliers**:
           - **Too Tall**: Height > **4x** the group median
           - **Too Short**: Height < **0.25x** (1/4) the group median

        **Why this matters**: Trees in the same vegetation group (VEGETATION_KEY) were planted together and should have similar heights.
        Large variations may indicate:
        - Pruning or coppicing practices
        - Data entry errors
        - Mixed planting dates within the group

        ⚠️ **Note**: This respects your date range filter. Only measurements from the selected date range are analyzed.
        This is different from species-based outliers (Tab 1), which groups by species name across all groups.
        """
    )

    # Get the filtered merged veg+meas data (m_mea in notebook)
    if has_measurements and len(meas_df) > 0:
        # Filter to records with actual measurements
        if "MEASUREMENT_KEY" in meas_df.columns:
            m_mea_actual = meas_df[meas_df["MEASUREMENT_KEY"].notna()].copy()
        else:
            m_mea_actual = meas_df.copy()

        # Parameters from notebook
        veg_parameters = [
            "enumerator",
            "VEGETATION_KEY",
            "SUBPLOT_KEY",
            "vegetation_type_number",
            "tree_height_m",
            "tree_year_planted",
            "tree_prune",
            "tree_coppiced",
        ]

        # Filter to available columns
        available_params = [
            col for col in veg_parameters if col in m_mea_actual.columns
        ]

        if "VEGETATION_KEY" in available_params and "tree_height_m" in available_params:
            height_check = m_mea_actual[available_params].copy()

            # Remove NaN heights
            height_check = height_check[height_check["tree_height_m"].notna()]

            if len(height_check) > 0:
                # Calculate median height per VEGETATION_KEY (tree group)
                median_check = (
                    height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                    .median()
                    .reset_index(name="median_height")
                )

                # Merge with original data
                height_total = pd.merge(
                    height_check, median_check, how="inner", on="VEGETATION_KEY"
                )

                # Apply outlier detection (4x and 1/4x median)
                height_total["Upper_outliers"] = height_total.apply(
                    lambda row: (
                        "outlier"
                        if row["tree_height_m"] > (row["median_height"] * 4)
                        else "ok"
                    ),
                    axis=1,
                )
                height_total["Lower_outliers"] = height_total.apply(
                    lambda row: (
                        "outlier"
                        if row["tree_height_m"] < (row["median_height"] / 4)
                        else "ok"
                    ),
                    axis=1,
                )

                # Count outliers
                upper_outliers = height_total[
                    height_total["Upper_outliers"] == "outlier"
                ]
                lower_outliers = height_total[
                    height_total["Lower_outliers"] == "outlier"
                ]
                any_outlier = height_total[
                    (height_total["Upper_outliers"] == "outlier")
                    | (height_total["Lower_outliers"] == "outlier")
                ]

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Total Trees Checked", len(height_total))

                with col2:
                    st.metric("Upper Outliers (>4x median)", len(upper_outliers))

                with col3:
                    st.metric("Lower Outliers (<1/4x median)", len(lower_outliers))

                if len(any_outlier) > 0:
                    st.warning(
                        f"⚠️ {len(any_outlier)} trees have height outliers within their groups"
                    )

                    with st.expander(f"View {len(any_outlier)} height outliers"):
                        # Build display columns safely
                        display_cols = []
                        for col in [
                            "enumerator",
                            "VEGETATION_KEY",
                            "SUBPLOT_KEY",
                            "tree_name",
                            "tree_height_m",
                            "median_height",
                            "Upper_outliers",
                            "Lower_outliers",
                            "tree_prune",
                            "tree_coppiced",
                            "vegetation_type_number",
                        ]:
                            if col and col in any_outlier.columns:
                                display_cols.append(col)

                        st.dataframe(
                            any_outlier[display_cols].sort_values(
                                "tree_height_m", ascending=False
                            ),
                            use_container_width=True,
                            height=400,
                        )
                else:
                    st.success("✅ No height outliers detected within tree groups")

                # Option to view all data
                with st.expander("View all height homogeneity data"):
                    display_cols = [
                        "enumerator",
                        "VEGETATION_KEY",
                        "tree_height_m",
                        "median_height",
                        "Upper_outliers",
                        "Lower_outliers",
                    ]
                    display_cols = [
                        col for col in display_cols if col in height_total.columns
                    ]

                    # Add row numbers
                    display_df = height_total[display_cols].copy()
                    display_df.insert(0, "#", range(1, len(display_df) + 1))
                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        height=400,
                        hide_index=True,
                    )

            else:
                st.info("No height data available for homogeneity check")
        else:
            st.error("❌ Required columns (VEGETATION_KEY, tree_height_m) not found")
    else:
        st.info("ℹ️ Merged measurement data not available for this check")

    st.markdown("---")

    # CHECK 5: Circumference Check with Threshold
    st.markdown("#### 5️⃣ Large Circumference Check")
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
            "vegetation_type_number",
            "circumference_bh",
            "circumference_10cm",
            "tree_year_planted",
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
                    circumference_list = calculate_tree_age_corrected(
                        circumference_list
                    )

                # Calculate median circumference per MEASUREMENT_KEY
                # Use circumference_bh for median calculation (notebook logic)
                if has_bh and "MEASUREMENT_KEY" in circumference_list.columns:
                    # Filter to non-null BH values for median calculation
                    bh_data = circumference_list[
                        circumference_list["circumference_bh"].notna()
                    ]
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
                    st.markdown(
                        f"##### 📏 Circumference at Breast Height > {threshold_bh}cm"
                    )

                    large_bh = cir_total[
                        cir_total["circumference_bh"] > threshold_bh
                    ].copy()

                    st.metric(f"Measurements > {threshold_bh}cm", len(large_bh))

                    if len(large_bh) > 0:

                        # Calculate tree age
                        if "tree_year_planted" in large_bh.columns:
                            large_bh = calculate_tree_age_corrected(
                                large_bh, "tree_year_planted"
                            )

                        # Display columns
                        display_cols = [
                            "enumerator",
                            "VEGETATION_KEY",
                            "MEASUREMENT_KEY",
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

                        display_cols = [
                            col for col in display_cols if col in large_bh.columns
                        ]

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
                    st.markdown(
                        f"##### 📏 Circumference at 10cm Height > {threshold_10cm}cm "
                    )

                    large_10cm = cir_total[
                        cir_total["circumference_10cm"] > threshold_10cm
                    ].copy()

                    st.metric(f"Measurements > {threshold_10cm}cm", len(large_10cm))

                    if len(large_10cm) > 0:

                        # Calculate tree age
                        if "tree_year_planted" in large_10cm.columns:
                            large_10cm = calculate_tree_age_corrected(large_10cm)

                        # Display columns
                        display_cols = [
                            "enumerator",
                            "VEGETATION_KEY",
                            "MEASUREMENT_KEY",
                            "vegetation_type_number",
                            "circumference_10cm",
                            "tree_year_planted",
                        ]

                        if "tree_age" in large_10cm.columns:
                            display_cols.append("tree_age")

                        display_cols = [
                            col for col in display_cols if col in large_10cm.columns
                        ]

                        # Add row numbers
                        display_df = large_10cm[display_cols].copy()
                        display_df.insert(0, "#", range(1, len(display_df) + 1))

                        st.dataframe(
                            display_df.sort_values(
                                "circumference_10cm", ascending=False
                            ),
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
                st.info(
                    "ℹ️ No circumference columns (circumference_bh or circumference_10cm) found"
                )
        else:
            st.info("ℹ️ Required columns not available")
    else:
        st.info(
            "ℹ️ Complete dataset with circumference not available. Make sure your Excel file has a 'circumference' sheet."
        )

# ============================================
# TAB 1: OUTLIERS & SUSPICIOUS (MOVED TO FIRST TAB)
# ============================================

with tabs[0]:
    st.markdown("### ⚠️ Outliers & Suspicious Values")

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(
        "Using VEGETATION_KEY grouping (Rabobank methodology) - trees planted together should have similar heights"
    )

    # CHECK 1: Height outliers using VEGETATION_KEY grouping
    st.markdown(
        "#### 1️⃣ Height Outliers (>4x or <0.25x group median)"
    )

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
    if has_measurements and len(meas_df) > 0 and "VEGETATION_KEY" in meas_df.columns and "tree_height_m" in meas_df.columns:
        # Filter to records with valid height and VEGETATION_KEY
        height_check = meas_df[
            meas_df["tree_height_m"].notna() & meas_df["VEGETATION_KEY"].notna()
        ].copy()

        if len(height_check) > 0:
            # Calculate median height per VEGETATION_KEY (tree group)
            median_check = (
                height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                .median()
                .reset_index(name="median_height")
            )

            # Merge with original data
            height_total = pd.merge(
                height_check, median_check, how="inner", on="VEGETATION_KEY"
            )

            # Apply outlier detection (4x and 1/4x median - Rabobank methodology)
            height_total["Upper_outliers"] = height_total.apply(
                lambda row: (
                    "outlier"
                    if row["tree_height_m"] > (row["median_height"] * 4)
                    else "ok"
                ),
                axis=1,
            )
            height_total["Lower_outliers"] = height_total.apply(
                lambda row: (
                    "outlier"
                    if row["tree_height_m"] < (row["median_height"] / 4)
                    else "ok"
                ),
                axis=1,
            )

            # Filter to outliers only
            height_outliers = height_total[
                (height_total["Upper_outliers"] == "outlier")
                | (height_total["Lower_outliers"] == "outlier")
            ].copy()

            st.metric("Height Outliers", len(height_outliers))

            if len(height_outliers) > 0:
                st.error(
                    f"❌ {len(height_outliers)} height measurements are outliers within their vegetation group"
                )

                # Determine which outlier type
                def get_outlier_type(row):
                    if row.get("Upper_outliers") == "outlier":
                        return "Too Tall"
                    elif row.get("Lower_outliers") == "outlier":
                        return "Too Short"
                    else:
                        return "Unknown"

                height_outliers["Outlier_Type"] = height_outliers.apply(get_outlier_type, axis=1)

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
    st.markdown(
        "#### 2️⃣ Circumference Outliers (>4x or <0.25x group median)"
    )

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
            circ_check = complete_df[
                complete_df[circ_col].notna() & complete_df["VEGETATION_KEY"].notna()
            ].copy()

            if len(circ_check) > 0:
                # Calculate median circumference per VEGETATION_KEY
                median_check = (
                    circ_check.groupby("VEGETATION_KEY")[circ_col]
                    .median()
                    .reset_index(name="median_circ")
                )

                # Merge with original data
                circ_total = pd.merge(
                    circ_check, median_check, how="inner", on="VEGETATION_KEY"
                )

                # Apply outlier detection (4x and 1/4x median)
                circ_total["Upper_outliers"] = circ_total.apply(
                    lambda row: (
                        "outlier"
                        if row[circ_col] > (row["median_circ"] * 4)
                        else "ok"
                    ),
                    axis=1,
                )
                circ_total["Lower_outliers"] = circ_total.apply(
                    lambda row: (
                        "outlier"
                        if row[circ_col] < (row["median_circ"] / 4)
                        else "ok"
                    ),
                    axis=1,
                )

                # Filter to outliers only
                circ_outliers = circ_total[
                    (circ_total["Upper_outliers"] == "outlier")
                    | (circ_total["Lower_outliers"] == "outlier")
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

                    # Build display columns safely
                    display_cols = []
                    for col in [
                        "VEGETATION_KEY",
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
    st.markdown(f"#### 3️⃣ Suspicious Circumference vs Tree Age ")
    st.caption(
        f"Flagging: Circ >{young_tree_circ}cm AND age <5 years, OR Circ >300cm AND age <15 years"
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

                suspicious = circ_data[circ_data["suspicious"] == True]

                st.metric("Suspicious Circumferences", len(suspicious))

                if len(suspicious) > 0:
                    st.error(
                        f"❌ {len(suspicious)} trees have unrealistic circumference for their age"
                    )

                    # Build display columns safely
                    display_cols = []
                    for col in [
                        "VEGETATION_KEY",
                        "enumerator",
                        "tree_name",
                        circ_col,
                        "tree_year_planted",
                        "tree_age",
                        "tree_height_m",
                        species_col,
                    ]:
                        if col and col in suspicious.columns:
                            display_cols.append(col)

                    if len(display_cols) > 0:
                        st.dataframe(
                            (
                                suspicious[display_cols].sort_values(
                                    circ_col, ascending=False
                                )
                                if circ_col in display_cols
                                else suspicious[display_cols]
                            ),
                            use_container_width=True,
                            height=min(400, len(suspicious) * 35 + 38),
                        )
                    else:
                        st.warning("No displayable columns available")
                else:
                    st.success(
                        "✅ No suspicious circumference-age combinations detected"
                    )
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
        "Interactive scatter plot: Height vs Circumference, sized by stem count, colored by species"
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
        available_cols = [
            col for col in required_cols if col and col in complete_with_enum.columns
        ]

        if len(available_cols) >= 4:  # Need at least height, circ, stems, species
            # Prepare data for plotting
            plot_data = complete_with_enum[available_cols].copy()

            # Remove rows with NaN in critical columns
            plot_data = plot_data.dropna(
                subset=["tree_height_m", circ_col, "nr_stems_bh"]
            )

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

                # Clean data for selected variables
                plot_cols = [x_axis, y_axis, size_var, species_col]
                plot_subset = plot_data[plot_cols].dropna()

                if len(plot_subset) > 0:
                    # Create figure
                    fig = px.scatter(
                        plot_subset,
                        x=x_axis,
                        y=y_axis,
                        size=size_var,
                        color=species_col,
                        hover_data={
                            x_axis: True,
                            y_axis: True,
                            size_var: True,
                            species_col: True,
                        },
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
                        legend=dict(
                            orientation="v", yanchor="top", y=1, xanchor="left", x=1.02
                        ),
                    )

                    # Update traces for better visibility
                    fig.update_traces(
                        marker=dict(
                            line=dict(width=0.5, color="DarkSlateGrey"), opacity=0.7
                        )
                    )

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
                            st.metric(
                                "Avg Stems", f"{plot_subset['nr_stems_bh'].mean():.1f}"
                            )

                    # Download data
                    csv = plot_subset.to_csv(index=False)
                    st.download_button(
                        label="📥 Download plot data",
                        data=csv,
                        file_name="tree_measurements_scatter.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning(
                        "⚠️ Not enough data after filtering for selected variables"
                    )
            else:
                st.info(
                    "ℹ️ No complete records with height, circumference, and stem data"
                )
        else:
            st.warning(
                f"⚠️ Missing required columns. Available: {', '.join(available_cols)}"
            )
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

            with pd.ExcelWriter(output, engine='openpyxl') as writer:

                # Sheet 1: Coverage-only subplots
                try:
                    if 'coverage_only' in locals() and len(coverage_only) > 0:
                        export_df = coverage_only.copy()
                        if 'geometry' in export_df.columns:
                            export_df = export_df.drop(columns=['geometry'])
                        sheet_name = 'Coverage Only'
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except: pass

                # Sheet 2: Primary trees with 'other'
                try:
                    if 'primary_trees' in locals() and len(primary_trees) > 0:
                        export_df = primary_trees.copy()
                        if 'geometry' in export_df.columns:
                            export_df = export_df.drop(columns=['geometry'])
                        sheet_name = 'Primary Trees Other'
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except: pass

                # Sheet 3: Young trees with 'other'
                try:
                    if 'young_trees_other' in locals() and len(young_trees_other) > 0:
                        export_df = young_trees_other.copy()
                        if 'geometry' in export_df.columns:
                            export_df = export_df.drop(columns=['geometry'])
                        sheet_name = 'Young Trees Other'
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except: pass

                # Sheet 4: Non-primary trees with 'other'
                try:
                    if 'non_primary_trees' in locals() and len(non_primary_trees) > 0:
                        export_df = non_primary_trees.copy()
                        if 'geometry' in export_df.columns:
                            export_df = export_df.drop(columns=['geometry'])
                        sheet_name = 'Non-Primary Trees Other'
                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = export_df
                        sheets_created += 1
                except: pass

                # Summary sheet if no data
                if sheets_created == 0:
                    summary_df = pd.DataFrame({
                        'Note': ['No flagged records found in quality checks']
                    })
                    sheet_name = 'Summary'
                    summary_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    sheet_dataframes[sheet_name] = summary_df

                # Adjust column widths for all sheets
                try:
                    for sheet_name, df in sheet_dataframes.items():
                        if sheet_name in writer.sheets:
                            worksheet = writer.sheets[sheet_name]
                            adjust_excel_column_widths(worksheet, df)
                except Exception as e:
                    # Column width adjustment is optional - don't fail export if it errors
                    pass

            output.seek(0)

            st.success(f"✅ Created Excel file with {sheets_created} sheet(s)")

            st.download_button(
                label="💾 Download Excel File",
                data=output.getvalue(),
                file_name=f"{config.PARTNER}_quality_checks_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        except Exception as e:
            st.error(f"Error creating export: {str(e)}")

with col2:
    if st.button("📥 Export Filtered Vegetation Data (CSV)", use_container_width=True):
        try:
            # Export the filtered vegetation data
            export_df = veg_with_enum.copy()

            # Remove geometry column if exists
            if 'geometry' in export_df.columns:
                export_df = export_df.drop(columns=['geometry'])

            # Convert to CSV
            csv = export_df.to_csv(index=False)

            st.download_button(
                label="💾 Download CSV File",
                data=csv,
                file_name=f"{config.PARTNER}_vegetation_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )

        except Exception as e:
            st.error(f"Error creating CSV export: {str(e)}")
