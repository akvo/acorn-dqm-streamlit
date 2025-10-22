"""
Overview Dashboard Page
"""

import streamlit as st
import config
from ui.components import (
    show_header,
    show_metrics_row,
    show_status_message,
    create_sidebar_filters,
)
from ui.charts import (
    create_validation_pie_chart,
    create_error_breakdown_chart,
    create_enumerator_performance_chart,
    create_timeline_chart,
)
from utils.data_processor import get_validation_summary

# Page config
st.set_page_config(
    page_title="Overview - " + config.APP_TITLE,
    page_icon="📊",
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

# Get data
gdf_subplots = st.session_state.data["subplots"]

# Apply filters
filtered_gdf = create_sidebar_filters(gdf_subplots)

# Get summary
summary = get_validation_summary(filtered_gdf)

# Main content
st.markdown("## 📊 Overview Dashboard")

# Metrics row
show_metrics_row(summary)

# Status message
st.markdown("---")
show_status_message(summary)

# Charts
st.markdown("---")
st.markdown("## 📈 Validation Analysis")

col1, col2 = st.columns(2)

with col1:
    # Pie chart
    fig_pie = create_validation_pie_chart(summary)
    if fig_pie:
        st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    # Error breakdown
    fig_errors = create_error_breakdown_chart(summary)
    if fig_errors:
        st.plotly_chart(fig_errors, use_container_width=True)
    else:
        st.success("🎉 No validation errors!")

# Timeline
st.markdown("---")
fig_timeline = create_timeline_chart(filtered_gdf)
if fig_timeline:
    st.plotly_chart(fig_timeline, use_container_width=True)

# Enumerator performance
st.markdown("---")
fig_enum = create_enumerator_performance_chart(filtered_gdf)
if fig_enum:
    st.plotly_chart(fig_enum, use_container_width=True)

# Area distribution
st.markdown("---")
st.markdown("## 📏 Area Distribution")

if "area_m2" in filtered_gdf.columns:
    col1, col2, col3 = st.columns(3)

    valid_areas = filtered_gdf[filtered_gdf["geom_valid"]]["area_m2"]

    with col1:
        avg_area = valid_areas.mean()
        st.metric("Average Area (Valid)", f"{avg_area:.1f} m²")

    with col2:
        min_area = valid_areas.min()
        st.metric("Minimum Area (Valid)", f"{min_area:.1f} m²")

    with col3:
        max_area = valid_areas.max()
        st.metric("Maximum Area (Valid)", f"{max_area:.1f} m²")

    # Histogram
    import plotly.express as px

    fig_hist = px.histogram(
        filtered_gdf[filtered_gdf["area_m2"] > 0],
        x="area_m2",
        color="geom_valid",
        title="Subplot Area Distribution",
        labels={"area_m2": "Area (m²)", "geom_valid": "Valid"},
        color_discrete_map={True: "green", False: "red"},
        nbins=50,
    )

    # Add threshold lines
    fig_hist.add_vline(
        x=config.MIN_SUBPLOT_AREA_SIZE,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"Min: {config.MIN_SUBPLOT_AREA_SIZE}m²",
    )
    fig_hist.add_vline(
        x=config.MAX_SUBPLOT_AREA_SIZE,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"Max: {config.MAX_SUBPLOT_AREA_SIZE}m²",
    )

    st.plotly_chart(fig_hist, use_container_width=True)

# Summary table
st.markdown("---")
st.markdown("## 📋 Summary Statistics")

if summary["reason_counts"]:
    import pandas as pd

    error_df = pd.DataFrame(
        {
            "Error Type": list(summary["reason_counts"].keys()),
            "Count": list(summary["reason_counts"].values()),
            "Percentage": [
                f"{(count/summary['invalid']*100):.1f}%"
                for count in summary["reason_counts"].values()
            ],
        }
    ).sort_values("Count", ascending=False)

    st.dataframe(
        error_df,
        use_container_width=True,
        hide_index=True,
    )
