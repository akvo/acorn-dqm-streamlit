"""
Reusable UI components
"""

import streamlit as st
import config
import pandas as pd


def show_header():
    """Display app header"""
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, #2E7D32 0%, #388E3C 100%); 
                    padding: 2rem; border-radius: 10px; margin-bottom: 2rem;">
            <h1 style="color: white; margin: 0;">
                {config.APP_ICON} {config.APP_TITLE}
            </h1>
            <p style="color: #E8F5E9; margin-top: 0.5rem;">
                Country: {config.COUNTRY} | Partner: {config.PARTNER} | Year: {config.YEAR}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_metrics_row(summary):
    """Display metrics in a row"""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📊 Total Subplots",
            f"{summary['total']:,}",
        )

    with col2:
        st.metric(
            "✅ Valid Subplots",
            f"{summary['valid']:,}",
            f"{summary['valid_pct']:.1f}%",
            delta_color="normal",
        )

    with col3:
        st.metric(
            "❌ Invalid Subplots",
            f"{summary['invalid']:,}",
            delta_color="inverse" if summary["invalid"] > 0 else "off",
        )

    with col4:
        issues = sum(summary["reason_counts"].values())
        st.metric(
            "⚠️ Total Issues",
            f"{issues:,}",
        )


def show_status_message(summary):
    """Display status message based on validation results"""
    valid_pct = summary["valid_pct"]

    if valid_pct >= 95:
        st.success(f"🎉 Excellent! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 90:
        st.success(f"✅ Very good! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 80:
        st.warning(f"⚠️ Good, but {summary['invalid']} subplots need attention")
    elif valid_pct >= 70:
        st.warning(f"⚠️ Attention needed: {summary['invalid']} invalid subplots")
    else:
        st.error(
            f"❌ Critical: {summary['invalid']} subplots are invalid ({100-valid_pct:.1f}%)"
        )


def create_sidebar_filters(gdf):
    """Create sidebar filters and return filtered data"""
    st.sidebar.markdown("## 🔍 Filters")

    # Date filter
    if "starttime" in gdf.columns:
        gdf_copy = gdf.copy()
        gdf_copy["starttime"] = pd.to_datetime(gdf_copy["starttime"])

        min_date = gdf_copy["starttime"].min().date()
        max_date = gdf_copy["starttime"].max().date()

        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if len(date_range) == 2:
            from utils.data_processor import filter_by_date

            gdf = filter_by_date(gdf, date_range[0], date_range[1])

    # Enumerator filter
    if "enumerator" in gdf.columns:
        enumerators = sorted(gdf["enumerator"].dropna().unique().tolist())
        selected_enums = st.sidebar.multiselect(
            "Enumerator",
            options=enumerators,
            default=enumerators,
        )

        if selected_enums:
            from utils.data_processor import filter_by_enumerator

            gdf = filter_by_enumerator(gdf, selected_enums)

    # Validity filter
    validity_filter = st.sidebar.radio(
        "Show",
        options=["All", "Valid Only", "Invalid Only"],
        index=0,
    )

    if validity_filter == "Valid Only":
        gdf = gdf[gdf["geom_valid"]]
    elif validity_filter == "Invalid Only":
        gdf = gdf[~gdf["geom_valid"]]

    return gdf


def show_invalid_table(gdf):
    """Display table of invalid subplots"""
    invalid_df = gdf[~gdf["geom_valid"]].copy()

    if len(invalid_df) == 0:
        st.success("🎉 All subplots are valid!")
        return

    st.markdown(f"### ❌ Invalid Subplots ({len(invalid_df)})")

    # Select columns
    display_cols = ["subplot_id"]
    for col in ["enumerator", "area_m2", "nr_vertices", "reasons"]:
        if col in invalid_df.columns:
            display_cols.append(col)

    # Format area if exists
    if "area_m2" in invalid_df.columns:
        invalid_df["area_m2"] = invalid_df["area_m2"].round(1)

    st.dataframe(
        invalid_df[display_cols],
        use_container_width=True,
        height=500,
        column_config={
            "subplot_id": "Subplot ID",
            "enumerator": "Enumerator",
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
            "nr_vertices": "Vertices",
            "reasons": "Validation Errors",
        },
    )
