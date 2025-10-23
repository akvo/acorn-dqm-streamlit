"""
Plot Issues Page - Focus on plots with validation errors
Shows plots with ≥8 invalid subplots and detailed error breakdown
"""

import streamlit as st
import pandas as pd
import config
from ui.components import show_header, create_sidebar_filters

# Page config
st.set_page_config(
    page_title="Plot Issues - " + config.APP_TITLE,
    page_icon="⚠️",
    layout="wide",
)

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
    st.stop()

# Header
show_header()

st.markdown("## ⚠️ Plot Issues")
st.caption("Focus on plots with validation errors (≥8 invalid subplots)")

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
        other_count = (
            subplot_veg["vegetation_species_type"].astype(str).str.lower() == "other"
        ).sum()

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
        is_valid, errors, other_count = validate_subplot_vegetation(
            subplot_key, raw_data
        )
        veg_valid_list.append(is_valid)
        veg_errors_list.append("; ".join(errors) if errors else "")
        other_count_list.append(other_count)

    gdf_subplots["veg_valid"] = veg_valid_list
    gdf_subplots["veg_errors"] = veg_errors_list
    gdf_subplots["other_count"] = other_count_list

    # Combined validation: geometry AND vegetation must be valid
    gdf_subplots["overall_valid"] = (
        gdf_subplots["geom_valid"] & gdf_subplots["veg_valid"]
    )

    return gdf_subplots


# ============================================
# PLOT-LEVEL VALIDATION
# ============================================


def calculate_plot_validation(gdf_subplots):
    """
    Calculate plot-level validation
    Rule: Plot is invalid if ≥8 subplots are invalid
    """
    if "PLOT_KEY" not in gdf_subplots.columns:
        # Try to extract from subplot_id
        if "subplot_id" in gdf_subplots.columns:
            gdf_subplots["PLOT_KEY"] = gdf_subplots["subplot_id"].str.split("/").str[0]
        else:
            return pd.DataFrame()

    # Group by plot
    plot_summary = (
        gdf_subplots.groupby("PLOT_KEY")
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
    plot_summary["invalid_subplots"] = (
        plot_summary["total_subplots"] - plot_summary["valid_subplots"]
    )
    plot_summary["geom_invalid"] = (
        plot_summary["total_subplots"] - plot_summary["geom_valid_count"]
    )
    plot_summary["veg_invalid"] = (
        plot_summary["total_subplots"] - plot_summary["veg_valid_count"]
    )

    # Plot is invalid if ≥8 subplots are invalid
    plot_summary["plot_valid"] = plot_summary["invalid_subplots"] < 8

    return plot_summary


# Add vegetation validation
gdf_subplots = add_vegetation_validation(gdf_subplots, raw_data)

# Calculate plot validation
plot_summary = calculate_plot_validation(gdf_subplots)

# Apply filters
filtered_gdf = create_sidebar_filters(gdf_subplots)

# ============================================
# SUMMARY METRICS
# ============================================

st.markdown("### 📊 Overall Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    total_plots = len(plot_summary) if len(plot_summary) > 0 else 0
    st.metric("Total Plots", f"{total_plots:,}")

with col2:
    if len(plot_summary) > 0:
        invalid_plots = (~plot_summary["plot_valid"]).sum()
        invalid_pct = (invalid_plots / total_plots * 100) if total_plots > 0 else 0
        st.metric("❌ Invalid Plots", f"{invalid_plots:,}", f"{invalid_pct:.1f}%")
    else:
        st.metric("❌ Invalid Plots", "0", "0.0%")

with col3:
    total_subplots = len(filtered_gdf)
    st.metric("Total Subplots", f"{total_subplots:,}")

with col4:
    invalid_subplots = (~filtered_gdf["overall_valid"]).sum()
    invalid_sub_pct = (
        (invalid_subplots / total_subplots * 100) if total_subplots > 0 else 0
    )
    st.metric("❌ Invalid Subplots", f"{invalid_subplots:,}", f"{invalid_sub_pct:.1f}%")

st.markdown("---")

# ============================================
# SUBPLOT ISSUE BREAKDOWN
# ============================================

st.markdown("### ⚠️ Subplot Issues Breakdown")

col1, col2, col3 = st.columns(3)

with col1:
    geom_only = (~filtered_gdf["geom_valid"] & filtered_gdf["veg_valid"]).sum()
    geom_pct = (geom_only / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("🔶 Geometry Issues Only", f"{geom_only:,}", f"{geom_pct:.1f}%")

with col2:
    veg_only = (filtered_gdf["geom_valid"] & ~filtered_gdf["veg_valid"]).sum()
    veg_pct = (veg_only / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("🌿 Vegetation Issues Only", f"{veg_only:,}", f"{veg_pct:.1f}%")

with col3:
    both = (~filtered_gdf["geom_valid"] & ~filtered_gdf["veg_valid"]).sum()
    both_pct = (both / total_subplots * 100) if total_subplots > 0 else 0
    st.metric("❌ Both Issues", f"{both:,}", f"{both_pct:.1f}%")

st.markdown("---")

# ============================================
# PLOTS WITH ISSUES (≥8 INVALID SUBPLOTS)
# ============================================

st.markdown("### 📋 Plots with ≥8 Invalid Subplots")

if len(plot_summary) > 0:
    invalid_plots_df = plot_summary[~plot_summary["plot_valid"]].sort_values(
        "invalid_subplots", ascending=False
    )

    if len(invalid_plots_df) > 0:
        st.warning(
            f"⚠️ {len(invalid_plots_df)} plots have ≥8 invalid subplots and need attention"
        )

        # Display table
        display_df = invalid_plots_df[
            [
                "PLOT_KEY",
                "total_subplots",
                "invalid_subplots",
                "valid_subplots",
                "geom_invalid",
                "veg_invalid",
            ]
        ].copy()

        # Add row numbers
        display_df.insert(0, "#", range(1, len(display_df) + 1))

        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
            column_config={
                "#": st.column_config.NumberColumn("#", width="small"),
                "PLOT_KEY": "Plot ID",
                "total_subplots": st.column_config.NumberColumn("Total", width="small"),
                "invalid_subplots": st.column_config.NumberColumn(
                    "❌ Invalid", width="small"
                ),
                "valid_subplots": st.column_config.NumberColumn(
                    "✅ Valid", width="small"
                ),
                "geom_invalid": st.column_config.NumberColumn("🔶 Geom", width="small"),
                "veg_invalid": st.column_config.NumberColumn("🌿 Veg", width="small"),
            },
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
        st.success(
            "✅ No plots with ≥8 invalid subplots - all plots meet quality standards!"
        )
else:
    st.info("No plot data available")

st.markdown("---")

# ============================================
# SUBPLOTS WITH VEGETATION ISSUES ONLY
# ============================================

st.markdown("### 🌿 Subplots with Vegetation Issues Only")
st.caption("Subplots that pass geometry checks but have ≥10 'other' trees")

veg_issues_only = filtered_gdf[
    filtered_gdf["geom_valid"] & ~filtered_gdf["veg_valid"]
].copy()

if len(veg_issues_only) > 0:
    st.warning(
        f"⚠️ {len(veg_issues_only)} subplots have vegetation issues (≥10 'other' trees)"
    )

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
            "other_count": st.column_config.NumberColumn(
                "'Other' Trees", width="small"
            ),
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
st.caption("Subplots that pass vegetation checks but have geometry problems")

geom_issues_only = filtered_gdf[
    ~filtered_gdf["geom_valid"] & filtered_gdf["veg_valid"]
].copy()

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
            "length_width_ratio": st.column_config.NumberColumn(
                "L/W Ratio", format="%.2f"
            ),
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
# SUBPLOTS WITH BOTH ISSUES
# ============================================

st.markdown("### ❌ Subplots with Both Geometry & Vegetation Issues")
st.caption("Subplots that fail both validation checks - highest priority for revisit")

both_issues = filtered_gdf[
    ~filtered_gdf["geom_valid"] & ~filtered_gdf["veg_valid"]
].copy()

if len(both_issues) > 0:
    st.error(
        f"❌ {len(both_issues)} subplots have BOTH geometry and vegetation issues - high priority!"
    )

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
            "other_count": st.column_config.NumberColumn(
                "'Other' Trees", width="small"
            ),
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
        st.write(
            f"• Area: {config.MIN_SUBPLOT_AREA_SIZE}-{config.MAX_SUBPLOT_AREA_SIZE} m²"
        )
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
