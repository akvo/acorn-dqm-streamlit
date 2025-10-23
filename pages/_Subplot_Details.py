"""
Subplot Details Page - Vegetation Quality Checks (Error-Focused)
Based on Vegetation_checks.ipynb logic
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import config
from ui.components import show_header, create_sidebar_filters
from utils.data_merge_utils import (
    merge_with_enumerator,
    calculate_tree_age,
    get_species_column,
)
from utils.vegetation_validation import (
    get_missing_subplots,
    check_unidentified_species,
    check_coverage_only_subplots,
    get_young_trees_with_other,
    get_primary_trees_with_other,
    get_non_primary_trees_with_other,
    get_tree_classification_debug_info,
    validate_species_lists,
    detect_stem_outliers,
    detect_height_outliers,
    detect_circumference_outliers,
    detect_suspicious_circumference_by_age,
    check_tall_trees,
)

# Page config
st.set_page_config(
    page_title="Subplot Details - " + config.APP_TITLE,
    page_icon="🌳",
    layout="wide",
)

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

# Apply filters
filtered_gdf = create_sidebar_filters(gdf_subplots)

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
# SIDEBAR: QUALITY THRESHOLDS
# ============================================

st.sidebar.markdown("---")
st.sidebar.markdown("## ⚙️ Quality Thresholds")
st.sidebar.caption("Adjust thresholds for error detection")

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

height_multiplier = st.sidebar.slider(
    "Height Outlier Multiplier",
    min_value=1.5,
    max_value=5.0,
    value=3.0,
    step=0.5,
    help="Flag heights >Nx or <1/Nx median",
)

circ_multiplier = st.sidebar.slider(
    "Circumference Outlier Multiplier",
    min_value=2.0,
    max_value=6.0,
    value=4.0,
    step=0.5,
    help="Flag circumferences >Nx or <1/Nx median",
)

young_tree_circ = st.sidebar.number_input(
    "Young Tree Circ Threshold (cm)",
    min_value=30,
    max_value=100,
    value=50,
    help="Suspicious if circ > this AND age < 5 years",
)

# ============================================
# GET AND MERGE DATA
# ============================================

# Get raw data
plots_df = raw_data.get("plots_subplots", pd.DataFrame())
veg_df = raw_data["plots_subplots_vegetation"].copy()
meas_df = (
    raw_data.get("plots_subplots_vegetation_measurements", pd.DataFrame())
    if has_measurements
    else pd.DataFrame()
)
complete_df = (
    raw_data.get("complete", pd.DataFrame()) if has_complete else pd.DataFrame()
)

# Merge with enumerator (for filtered analysis)
veg_with_enum = merge_with_enumerator(veg_df, filtered_gdf)
if has_measurements:
    meas_with_enum = merge_with_enumerator(meas_df, filtered_gdf)
else:
    meas_with_enum = pd.DataFrame()

# Get species column
species_col = get_species_column(veg_with_enum)


# ============================================
# TABS
# ============================================

tabs = st.tabs(
    [
        "🚫 Missing Data",
        "🌲 Tree Classification",
        "🌿 Species Lists",
        "📏 Measurements",
        "⚠️ Outliers & Suspicious",
    ]
)

# ============================================
# TAB 1: MISSING DATA
# ============================================

with tabs[0]:
    st.markdown("### 🚫 Missing Vegetation and Measurement Data")

    # FILTER veg_df to only actual vegetation (non-null VEGETATION_KEY)
    # This is needed if data_processor uses LEFT JOIN
    if "VEGETATION_KEY" in veg_df.columns:
        veg_df_actual = veg_df[veg_df["VEGETATION_KEY"].notna()].copy()
    else:
        veg_df_actual = veg_df.copy()

    # CHECK 1: Missing vegetation records
    st.markdown("#### 1️⃣ Subplots WITHOUT Vegetation Records")

    # Use utility function with filtered veg_df
    missing_veg = get_missing_subplots(plots_df, veg_df_actual)

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

    # Use FILTERED veg_df (only actual vegetation records)
    # Calculate density stats per subplot (matches notebook)
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
        density = veg_df_actual[available_cols].copy()

        # Group by subplot
        agg_dict = {}
        if "vegetation_type_number" in density.columns:
            agg_dict["vegetation_type_number"] = "sum"
        if "coverage_vegetation" in density.columns:
            agg_dict["coverage_vegetation"] = "sum"
        if "enumerator" in density.columns:
            agg_dict["enumerator"] = "unique"
        if "subplot_comments" in density.columns:
            agg_dict["subplot_comments"] = "unique"

        density_df = density.groupby("SUBPLOT_KEY").agg(agg_dict).reset_index()

        # Subplots with 0 trees (but have vegetation records - coverage only)
        subplots_coverage = density_df[density_df["vegetation_type_number"] == 0]

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Subplots Analyzed", len(density_df))
        with col2:
            st.metric("Subplots with 0 Trees", len(subplots_coverage))
        with col3:
            avg_trees = (
                density_df["vegetation_type_number"].mean()
                if "vegetation_type_number" in density_df.columns
                else 0
            )
            st.metric("Avg Trees per Subplot", f"{avg_trees:.1f}")

        # Show subplots with 0 trees
        if len(subplots_coverage) > 0:
            st.warning(
                f"⚠️ {len(subplots_coverage)} subplots have 0 trees but vegetation records exist (coverage only)"
            )

            with st.expander("View subplots with 0 trees"):
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

    # CHECK 2: Coverage-only subplots vs Missing Measurements
    st.markdown("#### 3️⃣ Coverage-Only Subplots vs Missing Measurements")
    st.caption(
        "Subplots with only coverage should not have measurements. If they do, enumerators may be changing answers."
    )

    if has_measurements:
        # Coverage-only subplots: subplots with 0 trees
        if "subplots_coverage" in locals() and len(density_df) > 0:
            coverage_only = subplots_coverage.copy()
        else:
            if "vegetation_type_number" in veg_df_actual.columns:
                temp_density = (
                    veg_df_actual.groupby("SUBPLOT_KEY")
                    .agg({"vegetation_type_number": "sum"})
                    .reset_index()
                )
                coverage_only_keys = temp_density[
                    temp_density["vegetation_type_number"] == 0
                ]["SUBPLOT_KEY"]
                coverage_only = veg_df_actual[
                    veg_df_actual["SUBPLOT_KEY"].isin(coverage_only_keys)
                ].copy()
            else:
                coverage_only = pd.DataFrame()

        # Missing measurements calculation
        if "plots_subplots_vegetation_measurements" in raw_data:
            m_all = raw_data["plots_subplots_vegetation_measurements"]

            # Filter to records that have MEASUREMENT_KEY (actual measurements)
            if "MEASUREMENT_KEY" in m_all.columns:
                m_with_meas = m_all[m_all["MEASUREMENT_KEY"].notna()].copy()
                # Get unique SUBPLOT_KEYs that have measurements
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
            .copy()
        )

        col1, col2 = st.columns(2)

        with col1:
            st.metric("Subplots with ONLY Coverage", len(coverage_only))
            if len(coverage_only) > 0:
                with st.expander(f"View {len(coverage_only)} coverage-only subplots"):
                    display_cols = [
                        col
                        for col in [
                            "SUBPLOT_KEY",
                            "enumerator",
                            "coverage_vegetation",
                            "non_woody_species",
                        ]
                        if col in coverage_only.columns
                    ]

                    # Add row numbers
                    display_df = coverage_only[display_cols].copy()
                    display_df.insert(0, "#", range(1, len(display_df) + 1))

                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        height=300,
                        hide_index=True,
                    )

        with col2:
            st.metric("Subplots Missing Measurements", len(missing_veg_df))
            if len(missing_veg_df) > 0:
                with st.expander(
                    f"View {len(missing_veg_df)} subplots missing measurements"
                ):
                    col_missing_veg = [
                        "enumerator",
                        "SUBPLOT_KEY",
                        "subplot_comments",
                        "crop_comments",
                        "non_woody_species",
                        "coverage_vegetation",
                    ]
                    display_cols = [
                        col for col in col_missing_veg if col in missing_veg_df.columns
                    ]

                    # Add row numbers
                    display_df = missing_veg_df[display_cols].copy()
                    display_df.insert(0, "#", range(1, len(display_df) + 1))

                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        height=300,
                        hide_index=True,
                    )

        # Quality check - these numbers should be close (notebook shows 663 vs 661)
        diff = abs(len(coverage_only) - len(missing_veg_df))
        if diff > 10:  # Allow small difference
            st.warning(
                f"⚠️ MISMATCH: {len(coverage_only)} coverage-only vs {len(missing_veg_df)} missing measurements. "
                f"Difference: {diff}. Enumerators may be changing their answers!"
            )
        else:
            st.success(
                f"✅ Coverage-only count ({len(coverage_only)}) matches missing measurements ({len(missing_veg_df)})"
            )
    else:
        st.info("ℹ️ Measurement data not available")

    st.markdown("---")

    st.markdown("#### 4️⃣ Records with 'other' Species")
    st.caption("Species marked as 'other' require botanical verification")

    # Use raw veg_df, then merge with enumerator
    other_species = check_unidentified_species(veg_df)

    # Merge with enumerator info
    if len(other_species) > 0:
        other_species = merge_with_enumerator(
            other_species, filtered_gdf, subplot_key_col="SUBPLOT_KEY"
        )

    if len(other_species) > 0:
        st.warning(
            f"⚠️ {len(other_species)} vegetation records need botanical verification"
        )

        # Group by enumerator
        other_by_enum = (
            other_species.groupby("enumerator").size().reset_index(name="count")
        )
        other_by_enum = other_by_enum.sort_values("count", ascending=False)

        st.dataframe(other_by_enum, use_container_width=True)

        with st.expander("View all unidentified species records"):
            display_cols = ["VEGETATION_KEY", "enumerator", "vegetation_species_type"]
            if "other_species" in other_species.columns:
                display_cols.append("other_species")
            if "woody_species" in other_species.columns:
                display_cols.append("woody_species")

            st.dataframe(
                other_species[display_cols], use_container_width=True, height=400
            )
    else:
        st.success("✅ All species properly identified")

# ============================================
# TAB 2: TREE CLASSIFICATION
# ============================================

with tabs[1]:
    st.markdown("### 🌲 Tree Classification Quality Check")
    st.caption(
        "Validate primary vs young tree designation - showing 'other' species only"
    )

    # Use RAW vegetation data like notebook does (m_veg)
    # Get debug info about data structure
    debug_info = get_tree_classification_debug_info(veg_df)

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
            young_trees_other, filtered_gdf, subplot_key_col="SUBPLOT_KEY"
        )
    if len(primary_trees) > 0:
        primary_trees = merge_with_enumerator(
            primary_trees, filtered_gdf, subplot_key_col="SUBPLOT_KEY"
        )
    if len(non_primary_trees) > 0:
        non_primary_trees = merge_with_enumerator(
            non_primary_trees, filtered_gdf, subplot_key_col="SUBPLOT_KEY"
        )

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
            display_cols = ["enumerator", "SUBPLOT_KEY"]
            for col in [
                "other_species",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in primary_trees.columns:
                    display_cols.append(col)

            st.dataframe(
                primary_trees[display_cols], use_container_width=True, height=400
            )
        else:
            st.info(
                "No primary trees with 'other' species found - check debug expander above"
            )

    with tree_tabs[1]:
        st.markdown("**Young Tree List (with 'other' species)**")
        st.caption(
            f"Trees marked as 'yes_groupbelow1.3' with woody_species = 'other' - Total: {len(young_trees_other)} trees (Notebook: 125 rows)"
        )

        if len(young_trees_other) > 0:
            # Use notebook's collector_list_trees_young columns
            display_cols = ["enumerator", "SUBPLOT_KEY"]

            for col in [
                "other_species",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in young_trees_other.columns:
                    display_cols.append(col)

            st.dataframe(
                young_trees_other[display_cols], use_container_width=True, height=400
            )
        else:
            st.warning("⚠️ No young trees with 'other' woody species found")
            st.info("Check the debug expander above to see the actual data values")

    with tree_tabs[2]:
        st.markdown("**Non-Primary Tree List (with 'other' species)**")
        st.caption(
            f"Trees marked as 'no' (non-primary) with woody_species = 'other' - Total: {len(non_primary_trees)} trees (Notebook: 240 rows)"
        )

        if len(non_primary_trees) > 0:
            # Use notebook's collector_list_trees columns
            display_cols = ["enumerator", "SUBPLOT_KEY"]
            for col in [
                "other_species",
                "language_other_species",
                "vegetation_type_number",
            ]:
                if col in non_primary_trees.columns:
                    display_cols.append(col)

            st.dataframe(
                non_primary_trees[display_cols], use_container_width=True, height=400
            )
        else:
            st.info("No non-primary trees with 'other' species found")

# ============================================
# TAB 3: SPECIES LISTS
# ============================================

with tabs[2]:
    st.markdown("### 🌿 Species Lists Validation")
    st.caption("Check species categorization by type")

    species_lists = validate_species_lists(veg_with_enum)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        woody = species_lists.get("woody", pd.DataFrame())
        st.metric("Woody Species", len(woody))

    with col2:
        palm = species_lists.get("palm", pd.DataFrame())
        st.metric("Palm Species", len(palm))

    with col3:
        bamboo = species_lists.get("bamboo", pd.DataFrame())
        st.metric("Bamboo Species", len(bamboo))

    with col4:
        banana = species_lists.get("banana", pd.DataFrame())
        st.metric("Banana Species", len(banana))

    st.markdown("---")

    # Show each list in tabs
    species_tabs = st.tabs(["Woody", "Palm", "Bamboo", "Banana"])

    with species_tabs[0]:
        if len(woody) > 0:
            st.markdown(f"**Woody Species List** ({len(woody)} records)")
            display_cols = ["VEGETATION_KEY", "enumerator", "woody_species"]
            if "vegetation_type_number" in woody.columns:
                display_cols.append("vegetation_type_number")
            st.dataframe(woody[display_cols], use_container_width=True, height=400)
        else:
            st.info("No woody species found")

    with species_tabs[1]:
        if len(palm) > 0:
            st.markdown(f"**Palm Species List** ({len(palm)} records)")
            display_cols = ["VEGETATION_KEY", "enumerator", "palm_species"]
            if "vegetation_type_number" in palm.columns:
                display_cols.append("vegetation_type_number")
            st.dataframe(palm[display_cols], use_container_width=True, height=400)
        else:
            st.info("No palm species found")

    with species_tabs[2]:
        if len(bamboo) > 0:
            st.markdown(f"**Bamboo Species List** ({len(bamboo)} records)")
            display_cols = ["VEGETATION_KEY", "enumerator", "bamboo_species"]
            if "vegetation_type_number" in bamboo.columns:
                display_cols.append("vegetation_type_number")
            st.dataframe(bamboo[display_cols], use_container_width=True, height=400)
        else:
            st.info("No bamboo species found")

    with species_tabs[3]:
        if len(banana) > 0:
            st.markdown(f"**Banana Species List** ({len(banana)} records)")
            display_cols = ["VEGETATION_KEY", "enumerator", "banana_species"]
            if "vegetation_type_number" in banana.columns:
                display_cols.append("vegetation_type_number")
            st.dataframe(banana[display_cols], use_container_width=True, height=400)
        else:
            st.info("No banana species found")

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
        # Filter to records with 'other_species'
        collector_list_coverage = [
            "enumerator",
            "SUBPLOT_KEY",
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
# TAB 4: MEASUREMENTS
# ============================================

with tabs[3]:
    st.markdown("### 📏 Measurement Quality Checks")

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(
        f"Using threshold: Stems > {stem_threshold}, Tall trees > {tall_tree_threshold}m"
    )

    # CHECK 1: Missing measurements
    st.markdown("#### 1️⃣ Missing Height and Circumference")

    missing_height = meas_with_enum[meas_with_enum["tree_height_m"].isna()]

    # Check circumference columns
    has_circ_bh = "circumference_bh" in meas_with_enum.columns
    has_circ_10 = "circumference_10cm" in meas_with_enum.columns

    if has_circ_bh and has_circ_10:
        missing_circ = meas_with_enum[
            meas_with_enum["circumference_bh"].isna()
            & meas_with_enum["circumference_10cm"].isna()
        ]
    elif has_circ_bh:
        missing_circ = meas_with_enum[meas_with_enum["circumference_bh"].isna()]
    elif has_circ_10:
        missing_circ = meas_with_enum[meas_with_enum["circumference_10cm"].isna()]
    else:
        missing_circ = pd.DataFrame()

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Missing Height", len(missing_height))
        if len(missing_height) > 0:
            with st.expander(f"View {len(missing_height)} trees missing height"):
                display_cols = ["VEGETATION_KEY", "enumerator"]
                if species_col:
                    display_cols.append(species_col)
                st.dataframe(
                    missing_height[display_cols], use_container_width=True, height=300
                )

    with col2:
        st.metric("Missing Circumference", len(missing_circ))
        if len(missing_circ) > 0:
            with st.expander(f"View {len(missing_circ)} trees missing circumference"):
                display_cols = ["VEGETATION_KEY", "enumerator"]
                if species_col:
                    display_cols.append(species_col)
                st.dataframe(
                    missing_circ[display_cols], use_container_width=True, height=300
                )

    st.markdown("---")

    # CHECK 2: Super Tall Trees Check
    st.markdown(f"#### 2️⃣ Super Tall Trees (> {tall_tree_threshold}m)")
    st.caption("Important to verify tall trees are realistic with planting age")

    # Use the height_total data from height homogeneity check if available
    # Otherwise calculate it
    if "plots_subplots_vegetation_measurements" in raw_data:
        m_mea = raw_data["plots_subplots_vegetation_measurements"]

        if "MEASUREMENT_KEY" in m_mea.columns:
            m_mea_actual = m_mea[m_mea["MEASUREMENT_KEY"].notna()].copy()
        else:
            m_mea_actual = m_mea.copy()

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

                    # Display columns
                    display_cols = [
                        "enumerator",
                        "VEGETATION_KEY",
                        "SUBPLOT_KEY",
                        "tree_height_m",
                    ]

                    # Add optional columns
                    for col in [
                        "tree_year_planted",
                        "vegetation_type_number",
                        "tree_prune",
                        "tree_coppiced",
                    ]:
                        if col in super_tall.columns:
                            display_cols.append(col)

                    if species_col and species_col in super_tall.columns:
                        display_cols.append(species_col)

                    display_cols = [
                        col for col in display_cols if col in super_tall.columns
                    ]

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

    # CHECK 3: High stem counts
    st.markdown(f"#### 3️⃣ High Stem Counts (> {stem_threshold})")
    st.caption(
        "From notebook: nr_stems_bh > 20 is suspicious (should be constrained to >40?)"
    )

    meas_with_enum = detect_stem_outliers(meas_with_enum, threshold=stem_threshold)
    high_stems = meas_with_enum[meas_with_enum["high_stems_bh"] == True]

    st.metric(f"Trees with > {stem_threshold} stems", len(high_stems))

    if len(high_stems) > 0:
        st.warning(f"⚠️ {len(high_stems)} trees with unusually high stem counts")

        display_cols = ["VEGETATION_KEY", "enumerator", "nr_stems_bh"]
        if "nr_stems_10cm" in high_stems.columns:
            display_cols.append("nr_stems_10cm")
        if species_col and species_col in high_stems.columns:
            display_cols.append(species_col)
        if "tree_year_planted" in high_stems.columns:
            display_cols.append("tree_year_planted")

        # Add row numbers
        display_df = high_stems[display_cols].copy()
        display_df.insert(0, "#", range(1, len(display_df) + 1))

        st.dataframe(
            display_df.sort_values("nr_stems_bh", ascending=False),
            use_container_width=True,
            height=min(400, len(high_stems) * 35 + 38),
            hide_index=True,
        )
    else:
        st.success(f"✅ No trees exceed {stem_threshold} stems")

    st.markdown("---")

    # CHECK 4: Height Homogeneity within Groups
    st.markdown("#### 4️⃣ Height Homogeneity Check")
    st.caption(
        "Check for outliers within tree groups - important to identify pruning or coppicing practices"
    )

    # Get the merged veg+meas data (m_mea in notebook)
    if "plots_subplots_vegetation_measurements" in raw_data:
        m_mea = raw_data["plots_subplots_vegetation_measurements"]

        # Filter to records with actual measurements
        if "MEASUREMENT_KEY" in m_mea.columns:
            m_mea_actual = m_mea[m_mea["MEASUREMENT_KEY"].notna()].copy()
        else:
            m_mea_actual = m_mea.copy()

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
                        display_cols = [
                            "enumerator",
                            "VEGETATION_KEY",
                            "SUBPLOT_KEY",
                            "tree_height_m",
                            "median_height",
                            "Upper_outliers",
                            "Lower_outliers",
                        ]

                        # Add pruning/coppicing info if available
                        for col in [
                            "tree_prune",
                            "tree_coppiced",
                            "vegetation_type_number",
                        ]:
                            if col in any_outlier.columns:
                                display_cols.append(col)

                        display_cols = [
                            col for col in display_cols if col in any_outlier.columns
                        ]

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

# ============================================
# TAB 5: OUTLIERS & SUSPICIOUS
# ============================================

with tabs[4]:
    st.markdown("### ⚠️ Outliers & Suspicious Values")

    if not has_measurements:
        st.error("❌ Measurement data not available")
        st.stop()

    st.caption(
        f"Using thresholds: Height {height_multiplier}x, Circumference {circ_multiplier}x, Young tree circ > {young_tree_circ}cm"
    )

    # CHECK 1: Height outliers
    st.markdown(
        f"#### 1️⃣ Height Outliers (>{height_multiplier}x or <{1/height_multiplier:.2f}x median)"
    )

    if species_col:
        meas_with_outliers = detect_height_outliers(
            meas_with_enum,
            height_col="tree_height_m",
            species_col=species_col,
            upper_threshold=height_multiplier,
            lower_threshold=1 / height_multiplier,
        )

        height_outliers = meas_with_outliers[
            (meas_with_outliers["Upper_outliers"] == "outlier")
            | (meas_with_outliers["Lower_outliers"] == "outlier")
        ]

        st.metric("Height Outliers", len(height_outliers))

        if len(height_outliers) > 0:
            st.error(
                f"❌ {len(height_outliers)} height measurements are outliers for their species"
            )

            display_cols = [
                "VEGETATION_KEY",
                "enumerator",
                species_col,
                "tree_height_m",
                "median_height",
                "Upper_outliers",
                "Lower_outliers",
            ]
            if "tree_year_planted" in height_outliers.columns:
                display_cols.append("tree_year_planted")

            st.dataframe(
                height_outliers[display_cols].sort_values(
                    "tree_height_m", ascending=False
                ),
                use_container_width=True,
                height=min(400, len(height_outliers) * 35 + 38),
            )
        else:
            st.success("✅ No height outliers detected")
    else:
        st.info("ℹ️ Species column not available for outlier detection")

    st.markdown("---")

    # CHECK 2: Circumference outliers
    st.markdown(
        f"#### 2️⃣ Circumference Outliers (>{circ_multiplier}x or <{1/circ_multiplier:.2f}x median)"
    )

    if has_complete and species_col:
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

        if len(circ_data) > 0:
            circ_with_outliers = detect_circumference_outliers(
                circ_data,
                circ_col=circ_col,
                species_col=species_col,
                upper_threshold=circ_multiplier,
                lower_threshold=1 / circ_multiplier,
            )

            circ_outliers = circ_with_outliers[
                (circ_with_outliers["Upper_outliers"] == "outlier")
                | (circ_with_outliers["Lower_outliers"] == "outlier")
            ]

            st.metric("Circumference Outliers", len(circ_outliers))

            if len(circ_outliers) > 0:
                st.error(
                    f"❌ {len(circ_outliers)} circumference measurements are outliers for their species"
                )

                display_cols = [
                    "VEGETATION_KEY",
                    "enumerator",
                    species_col,
                    circ_col,
                    "median_cir",
                    "Upper_outliers",
                    "Lower_outliers",
                ]
                if "tree_year_planted" in circ_outliers.columns:
                    display_cols.append("tree_year_planted")

                st.dataframe(
                    circ_outliers[display_cols].sort_values(circ_col, ascending=False),
                    use_container_width=True,
                    height=min(400, len(circ_outliers) * 35 + 38),
                )
            else:
                st.success("✅ No circumference outliers detected")
        else:
            st.info("ℹ️ No circumference data available")
    else:
        st.info("ℹ️ Complete dataset or species column not available")

    st.markdown("---")

    # CHECK 3: Suspicious circumference by age
    st.markdown(f"#### 3️⃣ Suspicious Circumference vs Tree Age")
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
                )

                suspicious = circ_data[circ_data["suspicious"] == True]

                st.metric("Suspicious Circumferences", len(suspicious))

                if len(suspicious) > 0:
                    st.error(
                        f"❌ {len(suspicious)} trees have unrealistic circumference for their age"
                    )

                    display_cols = [
                        "VEGETATION_KEY",
                        "enumerator",
                        circ_col,
                        "tree_year_planted",
                        "tree_age",
                    ]
                    if "tree_height_m" in suspicious.columns:
                        display_cols.append("tree_height_m")
                    if species_col and species_col in suspicious.columns:
                        display_cols.append(species_col)

                    st.dataframe(
                        suspicious[display_cols].sort_values(circ_col, ascending=False),
                        use_container_width=True,
                        height=min(400, len(suspicious) * 35 + 38),
                    )
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
        current_year = datetime.now().year

        if "tree_year_planted" in complete_with_enum.columns:
            complete_with_enum["tree_age"] = current_year - pd.to_numeric(
                complete_with_enum["tree_year_planted"], errors="coerce"
            )

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
                    x_axis = st.selectbox(
                        "X-axis",
                        options=["tree_age", circ_col, "nr_stems_bh"],
                        index=0 if "tree_age" in plot_data.columns else 1,
                        help="Select variable for X-axis",
                    )

                with col2:
                    y_axis = st.selectbox(
                        "Y-axis",
                        options=["tree_height_m", circ_col, "nr_stems_bh"],
                        index=0,
                        help="Select variable for Y-axis",
                    )

                with col3:
                    size_var = st.selectbox(
                        "Size by",
                        options=["nr_stems_bh", circ_col, "tree_height_m"],
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
st.markdown("### 📊 Export Options")

# Export filtered data
if st.button("📥 Export All Quality Check Results", use_container_width=True):
    st.info(
        "Export functionality coming soon - will include all flagged records from above checks"
    )
