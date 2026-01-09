"""
Plot Issues Page - Focus on plots with validation errors
Shows plots with ≥8 invalid subplots and detailed error breakdown
"""

import streamlit as st
import pandas as pd
import re
import config
from ui.components import show_header, create_sidebar_filters, show_sidebar_info
from utils.comparison_utils import get_tree_count_by_name, get_tree_records_by_species

# Page config
st.set_page_config(
    page_title="Plot Issues - Ground Truth DQM",
    page_icon="⚠️",
    layout="wide",
)

# Refresh partner config from URL
config.refresh_partner_config()

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
    st.stop()

# Header
show_header()

st.markdown("## ⚠️ Plot Issues")
st.caption("Identifies plots with significant validation problems (≥8 invalid subplots per plot). These plots likely need field revisits or data correction. Use this view to prioritize QA/QC efforts on the most problematic plots first.")

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# ============================================
# VEGETATION VALIDATION
# ============================================


def validate_subplot_vegetation(subplot_key, raw_data):
    """
    Validate subplot based on vegetation data
    Rule: Flag if ≥10 trees marked as 'other'
    Returns: (is_valid, error_messages, other_count)
    """
    errors = []
    other_count = 0

    # Get vegetation data
    if "plots_subplots_vegetation" not in raw_data:
        return True, [], 0

    veg_df = raw_data["plots_subplots_vegetation"]

    # Filter to this subplot
    subplot_veg = veg_df[veg_df["SUBPLOT_KEY"] == subplot_key]

    if len(subplot_veg) == 0:
        return True, [], 0

    # Check 'other_species' column (primary indicator)
    if "other_species" in subplot_veg.columns:
        other_count = subplot_veg["other_species"].notna().sum()

    # Alternative: check vegetation_species_type
    if other_count == 0 and "vegetation_species_type" in subplot_veg.columns:
        other_count = (subplot_veg["vegetation_species_type"].astype(str).str.lower() == "other").sum()

    # Flag if 10 or more trees are marked as 'other'
    if other_count >= 10:
        errors.append(f"≥10 trees marked as 'other' ({other_count} found)")

    is_valid = len(errors) == 0
    return is_valid, errors, other_count


def add_vegetation_validation(gdf_subplots, raw_data):
    """Add vegetation validation columns to subplot dataframe"""
    if "SUBPLOT_KEY" not in gdf_subplots.columns:
        gdf_subplots["SUBPLOT_KEY"] = gdf_subplots["subplot_id"]

    veg_valid_list = []
    veg_errors_list = []
    other_count_list = []

    for idx, row in gdf_subplots.iterrows():
        subplot_key = row["SUBPLOT_KEY"]
        is_valid, errors, other_count = validate_subplot_vegetation(subplot_key, raw_data)
        veg_valid_list.append(is_valid)
        veg_errors_list.append("; ".join(errors) if errors else "")
        other_count_list.append(other_count)

    gdf_subplots["veg_valid"] = veg_valid_list
    gdf_subplots["veg_errors"] = veg_errors_list
    gdf_subplots["other_count"] = other_count_list

    # Combined validation: geometry AND vegetation must be valid
    gdf_subplots["overall_valid"] = gdf_subplots["geom_valid"] & gdf_subplots["veg_valid"]

    return gdf_subplots


# ============================================
# PLOT-LEVEL VALIDATION
# ============================================


def calculate_plot_validation(gdf_subplots):
    """
    Calculate plot-level validation
    Rule: Plot is invalid if ≥8 subplots are invalid
    Only counts measured subplots (filters based on measured_subplots field)
    """
    import re

    if "PLOT_KEY" not in gdf_subplots.columns:
        # Try to extract from subplot_id
        if "subplot_id" in gdf_subplots.columns:
            gdf_subplots["PLOT_KEY"] = gdf_subplots["subplot_id"].str.split("/").str[0]
        else:
            return pd.DataFrame()

    # Filter to only measured subplots
    if "subplot_id" in gdf_subplots.columns and "measured_subplots" in gdf_subplots.columns:
        # Extract subplot number from subplot_id and compare to measured_subplots
        temp_df = gdf_subplots[["subplot_id", "measured_subplots"]].copy()
        temp_df["subplot_number"] = temp_df["subplot_id"].apply(
            lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
        )
        temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
        measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]]["subplot_id"].unique()

        # Filter gdf to only measured subplots
        gdf_filtered = gdf_subplots[gdf_subplots["subplot_id"].isin(measured_subplot_ids)].copy()
    else:
        gdf_filtered = gdf_subplots.copy()

    # Group by plot
    plot_summary = (
        gdf_filtered.groupby("PLOT_KEY")
        .agg(
            {
                "subplot_id": "count",
                "overall_valid": "sum",
                "geom_valid": "sum",
                "veg_valid": "sum",
            }
        )
        .reset_index()
    )

    plot_summary.columns = [
        "PLOT_KEY",
        "total_subplots",
        "valid_subplots",
        "geom_valid_count",
        "veg_valid_count",
    ]

    # Calculate invalid counts
    plot_summary["invalid_subplots"] = plot_summary["total_subplots"] - plot_summary["valid_subplots"]
    plot_summary["geom_invalid"] = plot_summary["total_subplots"] - plot_summary["geom_valid_count"]
    plot_summary["veg_invalid"] = plot_summary["total_subplots"] - plot_summary["veg_valid_count"]

    # Plot is invalid if ≥8 subplots are invalid
    plot_summary["plot_valid"] = plot_summary["invalid_subplots"] < 8

    return plot_summary


# Add vegetation validation
gdf_subplots = add_vegetation_validation(gdf_subplots, raw_data)

# Apply filters (shows date filter at top of sidebar)
filtered_gdf = create_sidebar_filters(gdf_subplots)

# Calculate plot validation on FILTERED data
plot_summary = calculate_plot_validation(filtered_gdf)

# Filter to only MEASURED subplots for overall metrics
if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
    temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()
    temp_df["subplot_number"] = temp_df["subplot_id"].apply(
        lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
    )
    temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
    measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]]["subplot_id"].unique()
    measured_gdf = filtered_gdf[filtered_gdf["subplot_id"].isin(measured_subplot_ids)].copy()
else:
    measured_gdf = filtered_gdf.copy()

# Enrich plot_summary with enumerator and date info
if len(plot_summary) > 0 and "PLOT_KEY" in filtered_gdf.columns:
    # Get first enumerator and starttime per plot
    plot_info = (
        filtered_gdf.groupby("PLOT_KEY")
        .agg({"enumerator": "first", "starttime": "first" if "starttime" in filtered_gdf.columns else lambda x: None})
        .reset_index()
    )

    # Merge with plot_summary
    plot_summary = plot_summary.merge(plot_info, on="PLOT_KEY", how="left")

# Show sidebar info (partner and data status)
show_sidebar_info()

# ============================================
# SUMMARY METRICS
# ============================================

st.markdown("### 📊 Overall Summary")
st.caption("High-level validation status across all plots and subplots. 'Invalid Plots' have ≥8 invalid subplots and should be prioritized for review.")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    total_plots = len(plot_summary) if len(plot_summary) > 0 else 0
    st.metric("Total Plots", f"{total_plots:,}")

with col2:
    if len(plot_summary) > 0:
        valid_plots = plot_summary["plot_valid"].sum()
        valid_pct = (valid_plots / total_plots * 100) if total_plots > 0 else 0
        st.metric("✅ Valid Plots", f"{valid_plots:,}", f"{valid_pct:.1f}%")
    else:
        st.metric("✅ Valid Plots", "0", "0.0%")

with col3:
    if len(plot_summary) > 0:
        invalid_plots = (~plot_summary["plot_valid"]).sum()
        invalid_pct = (invalid_plots / total_plots * 100) if total_plots > 0 else 0
        st.metric("❌ Invalid Plots", f"{invalid_plots:,}", f"{invalid_pct:.1f}%")
    else:
        st.metric("❌ Invalid Plots", "0", "0.0%")

with col4:
    total_subplots = len(measured_gdf)
    st.metric("Total Subplots", f"{total_subplots:,}")

with col5:
    invalid_subplots = (~measured_gdf["overall_valid"]).sum()
    invalid_sub_pct = (invalid_subplots / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("❌ Invalid Subplots", f"{invalid_subplots:,}", f"{invalid_sub_pct:.1f}%")

st.markdown("---")

# ============================================
# SUBPLOT ISSUE BREAKDOWN
# ============================================

st.markdown("### ⚠️ Subplot Issues Breakdown")
st.caption("Categorizes subplot issues by type. 'Geometry Only' = GPS/area problems. 'Vegetation Only' = species classification issues (≥10 trees as 'other'). 'Both' = subplots with multiple issue types requiring comprehensive review.")

col1, col2, col3 = st.columns(3)

with col1:
    geom_only = (~measured_gdf["geom_valid"] & measured_gdf["veg_valid"]).sum()
    geom_pct = (geom_only / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("🔶 Geometry Issues Only", f"{geom_only:,}", f"{geom_pct:.1f}%")

with col2:
    veg_only = (measured_gdf["geom_valid"] & ~measured_gdf["veg_valid"]).sum()
    veg_pct = (veg_only / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("🌿 Vegetation Issues Only", f"{veg_only:,}", f"{veg_pct:.1f}%")

with col3:
    both = (~measured_gdf["geom_valid"] & ~measured_gdf["veg_valid"]).sum()
    both_pct = (both / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("❌ Both Issues", f"{both:,}", f"{both_pct:.1f}%")

st.markdown("---")

# ============================================
# PLOTS WITH ISSUES (≥8 INVALID SUBPLOTS)
# ============================================

st.markdown("### 📋 Plots with ≥8 Invalid Subplots")
st.caption("Plots exceeding the error threshold. Click column headers to sort. Focus on plots with highest invalid_subplots count first. The enumerator column helps identify if issues are concentrated with specific field staff.")

if len(plot_summary) > 0:
    invalid_plots_df = plot_summary[~plot_summary["plot_valid"]].sort_values("invalid_subplots", ascending=False)

    if len(invalid_plots_df) > 0:
        st.warning(f"⚠️ {len(invalid_plots_df)} plots have ≥8 invalid subplots and need attention")

        # Display table
        display_cols = [
            "PLOT_KEY",
            "enumerator",
            "total_subplots",
            "invalid_subplots",
            "valid_subplots",
            "geom_invalid",
            "veg_invalid",
        ]

        # Add starttime if available
        if "starttime" in invalid_plots_df.columns:
            display_cols.insert(2, "starttime")

        display_df = invalid_plots_df[display_cols].copy()

        # Add row numbers
        display_df.insert(0, "#", range(1, len(display_df) + 1))

        column_config = {
            "#": st.column_config.NumberColumn("#", width="small"),
            "PLOT_KEY": "Plot ID",
            "enumerator": "Enumerator",
            "total_subplots": st.column_config.NumberColumn("Total", width="small"),
            "invalid_subplots": st.column_config.NumberColumn("❌ Invalid", width="small"),
            "valid_subplots": st.column_config.NumberColumn("✅ Valid", width="small"),
            "geom_invalid": st.column_config.NumberColumn("🔶 Geom", width="small"),
            "veg_invalid": st.column_config.NumberColumn("🌿 Veg", width="small"),
        }

        # Add starttime config if available
        if "starttime" in display_df.columns:
            column_config["starttime"] = st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD")

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            column_config=column_config,
            hide_index=True,
        )

        # Download button
        csv_data = invalid_plots_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Invalid Plots CSV",
            data=csv_data,
            file_name=f"{config.PARTNER}_invalid_plots.csv",
            mime="text/csv",
        )
    else:
        st.success("✅ No plots with ≥8 invalid subplots - all plots meet quality standards!")
else:
    st.info("No plot data available")

st.markdown("---")

# ============================================
# SUBPLOTS WITH VEGETATION ISSUES ONLY
# ============================================

st.markdown("### 🌿 Subplots with Vegetation Issues Only")
st.caption("Subplots with valid GPS boundaries but excessive 'other' species entries (≥10 trees). This often indicates enumerators couldn't identify species from the dropdown list. Consider adding commonly reported species to the partner's species registry.")

veg_issues_only = measured_gdf[measured_gdf["geom_valid"] & ~measured_gdf["veg_valid"]].copy()

if len(veg_issues_only) > 0:
    st.warning(f"⚠️ {len(veg_issues_only)} subplots have vegetation issues (≥10 'other' trees)")

    # Prepare display columns
    display_cols = ["subplot_id", "PLOT_KEY", "enumerator", "other_count", "veg_errors"]

    # Add optional columns if they exist
    for col in ["starttime", "area_m2"]:
        if col in veg_issues_only.columns:
            display_cols.append(col)

    display_cols = [col for col in display_cols if col in veg_issues_only.columns]

    veg_display = veg_issues_only[display_cols].copy()

    # Sort by other_count descending
    if "other_count" in veg_display.columns:
        veg_display = veg_display.sort_values("other_count", ascending=False)

    # Add row numbers
    veg_display.insert(0, "#", range(1, len(veg_display) + 1))

    st.dataframe(
        veg_display,
        use_container_width=True,
        height=400,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "subplot_id": "Subplot ID",
            "PLOT_KEY": "Plot ID",
            "enumerator": "Enumerator",
            "other_count": st.column_config.NumberColumn("'Other' Trees", width="small"),
            "veg_errors": "Issue Description",
            "starttime": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
        },
        hide_index=True,
    )

    # Download button
    csv_data = veg_issues_only[display_cols].to_csv(index=False)
    st.download_button(
        label="📥 Download Vegetation Issues CSV",
        data=csv_data,
        file_name=f"{config.PARTNER}_vegetation_issues.csv",
        mime="text/csv",
    )
else:
    st.success("✅ No subplots with vegetation-only issues!")

st.markdown("---")

# ============================================
# SUBPLOTS WITH GEOMETRY ISSUES ONLY
# ============================================

st.markdown("### 🔶 Subplots with Geometry Issues Only")
st.caption("Subplots with correct species data but GPS/area validation failures. Common causes: insufficient GPS accuracy, irregular polygon shapes, area outside acceptable range (450-750 m²), or overlapping boundaries. May require field revisit to re-capture GPS coordinates.")

geom_issues_only = measured_gdf[~measured_gdf["geom_valid"] & measured_gdf["veg_valid"]].copy()

if len(geom_issues_only) > 0:
    st.warning(f"⚠️ {len(geom_issues_only)} subplots have geometry issues")

    # Prepare display columns
    display_cols = ["subplot_id", "PLOT_KEY", "enumerator", "reasons"]

    # Add optional columns if they exist
    for col in [
        "starttime",
        "area_m2",
        "nr_vertices",
        "length_width_ratio",
        "mrr_ratio",
        "in_radius",
    ]:
        if col in geom_issues_only.columns:
            display_cols.append(col)

    display_cols = [col for col in display_cols if col in geom_issues_only.columns]

    geom_display = geom_issues_only[display_cols].copy()

    # Add row numbers
    geom_display.insert(0, "#", range(1, len(geom_display) + 1))

    st.dataframe(
        geom_display,
        use_container_width=True,
        height=400,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "subplot_id": "Subplot ID",
            "PLOT_KEY": "Plot ID",
            "enumerator": "Enumerator",
            "reasons": "Issue Description",
            "starttime": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
            "nr_vertices": st.column_config.NumberColumn("Vertices", width="small"),
            "length_width_ratio": st.column_config.NumberColumn("L/W Ratio", format="%.2f"),
            "mrr_ratio": st.column_config.NumberColumn("MRR Ratio", format="%.2f"),
            "in_radius": st.column_config.CheckboxColumn("In Radius"),
        },
        hide_index=True,
    )

    # Download button
    csv_data = geom_issues_only[display_cols].to_csv(index=False)
    st.download_button(
        label="📥 Download Geometry Issues CSV",
        data=csv_data,
        file_name=f"{config.PARTNER}_geometry_issues.csv",
        mime="text/csv",
    )
else:
    st.success("✅ No subplots with geometry-only issues!")

st.markdown("---")

# ============================================
# SUBPLOTS WITH EMPTY GEOMETRY
# ============================================

st.markdown("### 📍 Subplots with Empty Geometry")
st.caption("Subplots where GPS data was missing, incomplete, or couldn't form a valid polygon. This typically indicates: GPS device issues, incomplete field visits, or data transmission failures. These subplots have no spatial footprint and must be revisited.")

# Filter for empty geometry subplots
empty_geom_subplots = measured_gdf[measured_gdf["reasons"].str.contains("Empty geometry", case=False, na=False)].copy()

if len(empty_geom_subplots) > 0:
    st.error(f"📍 {len(empty_geom_subplots)} subplots have empty geometry - GPS data collection issues")

    # Prepare display columns
    display_cols = [
        "subplot_id",
        "PLOT_KEY",
        "enumerator",
    ]

    # Add empty_geom_detail if it exists and has non-empty values
    if "empty_geom_detail" in empty_geom_subplots.columns:
        # Check if column has any non-empty values
        has_data = (
            empty_geom_subplots["empty_geom_detail"].notna().any()
            and (empty_geom_subplots["empty_geom_detail"] != "").any()
        )
        if has_data:
            display_cols.append("empty_geom_detail")
        else:
            # Fall back to reasons column if empty_geom_detail is empty
            st.info("ℹ️ Detailed GPS statistics not available. Please reload the data to see detailed reasons.")
            display_cols.append("reasons")
    else:
        display_cols.append("reasons")

    # Add starttime if available
    if "starttime" in empty_geom_subplots.columns:
        display_cols.insert(3, "starttime")

    display_cols = [col for col in display_cols if col in empty_geom_subplots.columns]

    empty_geom_display = empty_geom_subplots[display_cols].copy()

    # Add row numbers
    empty_geom_display.insert(0, "#", range(1, len(empty_geom_display) + 1))

    column_config = {
        "#": st.column_config.NumberColumn("#", width="small"),
        "subplot_id": "Subplot ID",
        "PLOT_KEY": "Plot ID",
        "enumerator": "Enumerator",
    }

    # Add appropriate issue description column
    if "empty_geom_detail" in empty_geom_display.columns:
        column_config["empty_geom_detail"] = "Issue Description"
    elif "reasons" in empty_geom_display.columns:
        column_config["reasons"] = "Issue Description"

    # Add starttime config if available
    if "starttime" in empty_geom_display.columns:
        column_config["starttime"] = st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD")

    st.dataframe(
        empty_geom_display,
        use_container_width=True,
        height=400,
        column_config=column_config,
        hide_index=True,
    )
else:
    st.success("✅ No subplots with empty geometry!")

st.markdown("---")

# ============================================
# SUBPLOTS WITH BOTH ISSUES
# ============================================

st.markdown("### ❌ Subplots with Both Geometry & Vegetation Issues")
st.caption("Highest priority for field revisits. These subplots have both GPS boundary problems AND species classification issues. Often indicates rushed data collection or challenging field conditions. Review enumerator patterns to determine if retraining is needed.")

both_issues = measured_gdf[~measured_gdf["geom_valid"] & ~measured_gdf["veg_valid"]].copy()

if len(both_issues) > 0:
    st.error(f"❌ {len(both_issues)} subplots have BOTH geometry and vegetation issues - high priority!")

    # Prepare display columns
    display_cols = [
        "subplot_id",
        "PLOT_KEY",
        "enumerator",
        "reasons",
        "veg_errors",
        "other_count",
    ]

    # Add optional columns if they exist
    for col in ["starttime", "area_m2"]:
        if col in both_issues.columns:
            display_cols.append(col)

    display_cols = [col for col in display_cols if col in both_issues.columns]

    both_display = both_issues[display_cols].copy()

    # Sort by other_count descending
    if "other_count" in both_display.columns:
        both_display = both_display.sort_values("other_count", ascending=False)

    # Add row numbers
    both_display.insert(0, "#", range(1, len(both_display) + 1))

    st.dataframe(
        both_display,
        use_container_width=True,
        height=400,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "subplot_id": "Subplot ID",
            "PLOT_KEY": "Plot ID",
            "enumerator": "Enumerator",
            "reasons": "Geometry Issues",
            "veg_errors": "Vegetation Issues",
            "other_count": st.column_config.NumberColumn("'Other' Trees", width="small"),
            "starttime": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
        },
        hide_index=True,
    )

    # Download button
    csv_data = both_issues[display_cols].to_csv(index=False)
    st.download_button(
        label="📥 Download Both Issues CSV",
        data=csv_data,
        file_name=f"{config.PARTNER}_both_issues.csv",
        mime="text/csv",
    )
else:
    st.success("✅ No subplots with both types of issues!")

st.markdown("---")


# ============================================
# VALIDATION RULES REFERENCE
# ============================================

with st.expander("📖 Validation Rules Reference"):
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Plot-Level Validation:**")
        st.write("• Plot is ❌ invalid if **≥8 subplots** are invalid")
        st.write("• Plot is ✅ valid if **<8 subplots** are invalid")

        st.markdown("**Geometry Validation:**")
        st.write(f"• Area: {config.MIN_SUBPLOT_AREA_SIZE}-{config.MAX_SUBPLOT_AREA_SIZE} m²")
        st.write(f"• Length/Width ratio: ≤{config.THRESHOLD_LENGTH_WIDTH}")
        st.write(f"• Protruding ratio: ≤{config.THRESHOLD_PROTRUDING_RATIO}")
        st.write(f"• Within radius: {config.THRESHOLD_WITHIN_RADIUS}m")

    with col2:
        st.markdown("**Vegetation Validation:**")
        st.write("• **<10 trees** marked as 'other'")
        st.write("• Flag if ≥10 trees unidentified")

        st.markdown("**Overall Validation:**")
        st.write("• Subplot must pass **BOTH** geometry AND vegetation")
        st.write("• Any failure = subplot marked invalid")

st.markdown("---")

# ============================================
# LIVING FENCES TABLE
# ============================================

st.markdown("### 🌿 Plots with Living Fences")
st.caption("Living fences are perimeter plantings that serve as boundaries. This table shows plots where living_fences vegetation type was recorded. Count indicates number of vegetation records per plot. Use this to verify living fence documentation across plots.")

# Get living fences data from raw_data
raw_data = st.session_state.data.get("raw_data", {})
veg_df = raw_data.get("plots_subplots_vegetation")

if veg_df is not None and len(veg_df) > 0 and "vegetation_species_type" in veg_df.columns:
    # Filter to records where vegetation_species_type is "living_fences"
    living_fences_df = veg_df[veg_df["vegetation_species_type"].astype(str).str.lower() == "living_fences"].copy()

    if len(living_fences_df) > 0:
        # Extract PLOT_KEY from SUBPLOT_KEY (format: uuid:xxx/sub_plot[n])
        if "SUBPLOT_KEY" in living_fences_df.columns:
            living_fences_df["PLOT_KEY"] = living_fences_df["SUBPLOT_KEY"].apply(
                lambda x: str(x).split("/")[0] if pd.notna(x) and "/" in str(x) else str(x)
            )

        # Count occurrences per plot
        living_fences_summary = living_fences_df.groupby("PLOT_KEY").size().reset_index(name="Count")

        # Add "Has Living Fences" column
        living_fences_summary["Has Living Fences"] = "Yes"

        # Prepare display dataframe
        display_df = living_fences_summary[["PLOT_KEY", "Has Living Fences", "Count"]].copy()
        display_df = display_df.sort_values("Count", ascending=False)

        # Add row numbers
        display_df.insert(0, "#", range(1, len(display_df) + 1))

        st.info(f"📊 {len(display_df)} plots have living fences recorded")

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            column_config={
                "#": st.column_config.NumberColumn("#", width="small"),
                "PLOT_KEY": "Plot ID",
                "Has Living Fences": st.column_config.TextColumn("Has Living Fences", width="small"),
                "Count": st.column_config.NumberColumn("Count", width="small"),
            },
            hide_index=True,
        )

        # Download button
        csv_data = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Living Fences CSV",
            data=csv_data,
            file_name=f"{config.PARTNER}_living_fences.csv",
            mime="text/csv",
        )
    else:
        st.success("✅ No plots with living fences recorded")
else:
    st.info("No living fences data available in the dataset")

st.markdown("---")

# ============================================
# PLOT DETAILS EXPLORER
# ============================================

st.markdown("### 🔍 Plot Details Explorer")
st.caption("Interactive drill-down into individual plots. Select a plot to see all its subplots, validation status, and tree species data. ❌ indicates plots with ≥8 invalid subplots. ✅ indicates plots meeting quality thresholds. Use this to investigate specific issues in detail.")

# Get all unique plot keys
if "PLOT_KEY" in filtered_gdf.columns:
    all_plot_keys = sorted(filtered_gdf["PLOT_KEY"].dropna().unique().tolist())

    if len(all_plot_keys) > 0:
        # Build dropdown options with subplot count
        plot_options = ["-- Select a plot --"]
        for pk in all_plot_keys:
            subplot_count = len(filtered_gdf[filtered_gdf["PLOT_KEY"] == pk])
            # Check if plot is in invalid list
            is_invalid = (
                pk in plot_summary[~plot_summary["plot_valid"]]["PLOT_KEY"].values if len(plot_summary) > 0 else False
            )
            status_icon = "❌" if is_invalid else "✅"
            plot_options.append(f"{status_icon} {pk} ({subplot_count} subplots)")

        selected_plot_display = st.selectbox(
            "Select a plot to view details", options=plot_options, index=0, key="plot_explorer_select"
        )

        # Extract plot key from selection
        if selected_plot_display != "-- Select a plot --":
            # Remove status icon and subplot count to get plot key
            selected_plot_key = selected_plot_display.split(" ", 1)[1].rsplit(" (", 1)[0]

            # Get plot data
            plot_subplots = filtered_gdf[filtered_gdf["PLOT_KEY"] == selected_plot_key].copy()
            raw_data = st.session_state.data.get("raw_data", {})

            if len(plot_subplots) > 0:
                with st.expander(f"📋 Plot Details: {selected_plot_key}", expanded=True):
                    first_row = plot_subplots.iloc[0]

                    # Plot Information
                    st.markdown("**Plot Information:**")
                    info_col1, info_col2, info_col3 = st.columns(3)
                    with info_col1:
                        st.write(f"**Plot ID:** {selected_plot_key}")
                    with info_col2:
                        enumerator = first_row.get("enumerator", "N/A")
                        st.write(f"**Enumerator:** {enumerator}")
                    with info_col3:
                        plot_date = (
                            first_row.get("SubmissionDate")
                            or first_row.get("starttime")
                            or first_row.get("date", "N/A")
                        )
                        if pd.notna(plot_date) and plot_date != "N/A":
                            try:
                                plot_date = pd.to_datetime(plot_date).strftime("%Y-%m-%d")
                            except:
                                pass
                        st.write(f"**Date:** {plot_date}")

                    # Subplot Summary
                    st.markdown("**Subplot Summary:**")
                    total_subplots = len(plot_subplots)
                    valid_col = "overall_valid" if "overall_valid" in plot_subplots.columns else "geom_valid"
                    if valid_col in plot_subplots.columns:
                        valid_subplots = int(plot_subplots[valid_col].sum())
                    else:
                        valid_subplots = 0
                    invalid_subplots = total_subplots - valid_subplots

                    sub_col1, sub_col2, sub_col3 = st.columns(3)
                    with sub_col1:
                        st.metric("Total", total_subplots)
                    with sub_col2:
                        st.metric("✅ Valid", valid_subplots)
                    with sub_col3:
                        st.metric("❌ Invalid", invalid_subplots)

                    # Tree Species Table
                    st.markdown("**Tree Species Summary:**")
                    tree_counts = get_tree_count_by_name(selected_plot_key, raw_data, filtered_gdf)

                    if tree_counts:
                        # Build tree summary table
                        tree_data = []
                        for species_name, count in sorted(tree_counts.items(), key=lambda x: x[1], reverse=True):
                            # Get subplot breakdown for this species
                            species_records = get_tree_records_by_species(selected_plot_key, species_name, raw_data)
                            if len(species_records) > 0:
                                subplot_list = sorted(species_records["Subplot"].unique().tolist())
                                subplot_str = ", ".join([str(s) for s in subplot_list])
                            else:
                                subplot_str = "N/A"

                            tree_data.append({"Species": species_name, "Total Count": count, "Subplots": subplot_str})

                        # Add total row
                        total_trees = sum(tree_counts.values())
                        tree_data.append({"Species": "**TOTAL**", "Total Count": total_trees, "Subplots": "-"})

                        tree_df = pd.DataFrame(tree_data)
                        st.dataframe(
                            tree_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Species": "Species Name",
                                "Total Count": st.column_config.NumberColumn("Count", width="small"),
                                "Subplots": "Found in Subplots",
                            },
                        )

                        # Expandable species details
                        st.markdown("**Detailed Tree Records per Species:**")
                        for species_name, count in sorted(tree_counts.items(), key=lambda x: x[1], reverse=True):
                            with st.expander(f"{species_name}: {count} trees"):
                                species_records = get_tree_records_by_species(selected_plot_key, species_name, raw_data)
                                if len(species_records) > 0:
                                    st.dataframe(species_records, use_container_width=True, hide_index=True)
                                else:
                                    st.caption("No detailed records available")
                    else:
                        st.info("No tree data recorded for this plot")

                    # Invalid subplots list
                    invalid_subs = (
                        plot_subplots[~plot_subplots[valid_col]]
                        if valid_col in plot_subplots.columns
                        else pd.DataFrame()
                    )
                    if len(invalid_subs) > 0:
                        st.markdown("**Invalid Subplots:**")
                        invalid_display = (
                            invalid_subs[["subplot_id", "reasons"]].copy()
                            if "reasons" in invalid_subs.columns
                            else invalid_subs[["subplot_id"]].copy()
                        )

                        # Extract subplot number for cleaner display
                        invalid_display["Subplot #"] = invalid_display["subplot_id"].apply(
                            lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) + 1
                            if re.search(r"\[(\d+)\]", str(x))
                            else 0
                        )

                        if "reasons" in invalid_display.columns:
                            display_df = invalid_display[["Subplot #", "reasons"]].rename(columns={"reasons": "Issues"})
                        else:
                            display_df = invalid_display[["Subplot #"]]

                        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No plots available")
else:
    st.warning("PLOT_KEY column not found in data")
