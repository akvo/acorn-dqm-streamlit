"""
Subplot Details Page - Deep dive into individual subplots
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import config
from ui.components import show_header, create_sidebar_filters
from utils.data_processor import get_validation_summary

# Page config
st.set_page_config(
    page_title="Subplot Details - " + config.APP_TITLE,
    page_icon="🌳",
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

st.markdown("## 🌳 Subplot Details")

# Get data
gdf_subplots = st.session_state.data["subplots"]

# Apply filters
filtered_gdf = create_sidebar_filters(gdf_subplots)

# Summary
summary = get_validation_summary(filtered_gdf)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total", f"{summary['total']:,}")

with col2:
    st.metric("Valid", f"{summary['valid']:,}", f"{summary['valid_pct']:.1f}%")

with col3:
    st.metric("Invalid", f"{summary['invalid']:,}")

with col4:
    avg_area = (
        filtered_gdf["area_m2"].mean() if "area_m2" in filtered_gdf.columns else 0
    )
    st.metric("Avg Area", f"{avg_area:.1f} m²")

st.markdown("---")

# Subplot search and filter
st.markdown("### 🔍 Search Subplots")

col1, col2 = st.columns([2, 1])

with col1:
    search_term = st.text_input(
        "Search by Subplot ID", placeholder="Enter subplot ID..."
    )

with col2:
    show_only = st.selectbox(
        "Show",
        ["All Subplots", "Valid Only", "Invalid Only"],
    )

# Apply search and filter
search_df = filtered_gdf.copy()

if search_term:
    search_df = search_df[
        search_df["subplot_id"]
        .astype(str)
        .str.contains(search_term, case=False, na=False)
    ]

if show_only == "Valid Only":
    search_df = search_df[search_df["geom_valid"]]
elif show_only == "Invalid Only":
    search_df = search_df[~search_df["geom_valid"]]

st.markdown(f"**Showing {len(search_df)} of {len(filtered_gdf)} subplots**")

st.markdown("---")

# Display table with all details
st.markdown("### 📊 Subplot Data Table")

# Select columns to display
display_cols = ["subplot_id", "geom_valid"]

for col in [
    "enumerator",
    "starttime",
    "area_m2",
    "nr_vertices",
    "length_width_ratio",
    "mrr_ratio",
    "in_radius",
    "reasons",
]:
    if col in search_df.columns:
        display_cols.append(col)

# Format the dataframe
display_df = search_df[display_cols].copy()

if "area_m2" in display_df.columns:
    display_df["area_m2"] = display_df["area_m2"].round(1)

if "length_width_ratio" in display_df.columns:
    display_df["length_width_ratio"] = display_df["length_width_ratio"].round(2)

if "mrr_ratio" in display_df.columns:
    display_df["mrr_ratio"] = display_df["mrr_ratio"].round(2)

# Display
st.dataframe(
    display_df,
    use_container_width=True,
    height=500,
    column_config={
        "subplot_id": "Subplot ID",
        "geom_valid": st.column_config.CheckboxColumn("Valid"),
        "enumerator": "Enumerator",
        "starttime": st.column_config.DatetimeColumn(
            "Collection Date", format="YYYY-MM-DD"
        ),
        "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
        "nr_vertices": "Vertices",
        "length_width_ratio": st.column_config.NumberColumn("L/W Ratio", format="%.2f"),
        "mrr_ratio": st.column_config.NumberColumn("MRR Ratio", format="%.2f"),
        "in_radius": st.column_config.CheckboxColumn("In Radius"),
        "reasons": "Validation Issues",
    },
)

# Download current view
st.markdown("---")
st.markdown("### 📥 Export Current View")

csv_data = display_df.to_csv(index=False)

st.download_button(
    label="📊 Download Table as CSV",
    data=csv_data,
    file_name=f"{config.PARTNER}_subplot_details.csv",
    mime="text/csv",
    use_container_width=True,
)

# Statistics for filtered view
st.markdown("---")
st.markdown("### 📈 Statistics for Current View")

col1, col2 = st.columns(2)

with col1:
    # Vertex distribution
    if "nr_vertices" in search_df.columns:
        st.markdown("#### Vertex Count Distribution")

        vertex_counts = search_df["nr_vertices"].value_counts().sort_index()

        fig_vertices = px.bar(
            x=vertex_counts.index,
            y=vertex_counts.values,
            labels={"x": "Number of Vertices", "y": "Count"},
            title="Distribution of Vertex Counts",
        )
        fig_vertices.update_traces(marker_color="steelblue")

        st.plotly_chart(fig_vertices, use_container_width=True)

with col2:
    # Area distribution for current view
    if "area_m2" in search_df.columns:
        st.markdown("#### Area Distribution")

        fig_area = px.histogram(
            search_df[search_df["area_m2"] > 0],
            x="area_m2",
            nbins=30,
            title="Area Distribution (Current View)",
            labels={"area_m2": "Area (m²)"},
        )

        fig_area.add_vline(
            x=config.MIN_SUBPLOT_AREA_SIZE,
            line_dash="dash",
            line_color="red",
            annotation_text="Min",
        )
        fig_area.add_vline(
            x=config.MAX_SUBPLOT_AREA_SIZE,
            line_dash="dash",
            line_color="red",
            annotation_text="Max",
        )

        st.plotly_chart(fig_area, use_container_width=True)

# Individual subplot inspector
st.markdown("---")
st.markdown("### 🔬 Individual Subplot Inspector")

if len(search_df) > 0:
    subplot_ids = search_df["subplot_id"].tolist()

    selected_subplot = st.selectbox(
        "Select a subplot to inspect in detail:",
        options=subplot_ids,
        format_func=lambda x: f"{x} {'✅' if search_df[search_df['subplot_id']==x]['geom_valid'].iloc[0] else '❌'}",
    )

    if selected_subplot:
        subplot_data = search_df[search_df["subplot_id"] == selected_subplot].iloc[0]

        # Create three columns for detailed view
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 📋 Basic Information")
            st.write(f"**Subplot ID:** {subplot_data['subplot_id']}")
            st.write(
                f"**Status:** {'✅ Valid' if subplot_data['geom_valid'] else '❌ Invalid'}"
            )

            if "enumerator" in subplot_data.index:
                st.write(f"**Enumerator:** {subplot_data['enumerator']}")

            if "starttime" in subplot_data.index:
                st.write(f"**Collection Date:** {subplot_data['starttime']}")

        with col2:
            st.markdown("#### 📐 Geometry Metrics")

            if "area_m2" in subplot_data.index:
                area = subplot_data["area_m2"]
                area_status = (
                    "✅"
                    if config.MIN_SUBPLOT_AREA_SIZE
                    <= area
                    <= config.MAX_SUBPLOT_AREA_SIZE
                    else "❌"
                )
                st.write(f"{area_status} **Area:** {area:.2f} m²")

            if "nr_vertices" in subplot_data.index:
                vertices = subplot_data["nr_vertices"]
                vert_status = "✅" if vertices > config.MAX_VERTICES else "❌"
                st.write(f"{vert_status} **Vertices:** {vertices}")

            if "original_vertices" in subplot_data.index:
                st.write(f"**Original Vertices:** {subplot_data['original_vertices']}")

            if "vertices_dropped" in subplot_data.index:
                dropped = subplot_data["vertices_dropped"]
                if dropped > 0:
                    st.write(f"⚠️ **Vertices Dropped:** {dropped}")

        with col3:
            st.markdown("#### 📊 Shape Analysis")

            if "length_width_ratio" in subplot_data.index and pd.notna(
                subplot_data["length_width_ratio"]
            ):
                lw_ratio = subplot_data["length_width_ratio"]
                lw_status = "✅" if lw_ratio <= config.THRESHOLD_LENGTH_WIDTH else "⚠️"
                st.write(f"{lw_status} **L/W Ratio:** {lw_ratio:.2f}")
                st.caption(f"Threshold: {config.THRESHOLD_LENGTH_WIDTH}")

            if "mrr_ratio" in subplot_data.index and pd.notna(
                subplot_data["mrr_ratio"]
            ):
                mrr = subplot_data["mrr_ratio"]
                mrr_status = "✅" if mrr <= config.THRESHOLD_PROTRUDING_RATIO else "⚠️"
                st.write(f"{mrr_status} **Protruding Ratio:** {mrr:.2f}")
                st.caption(f"Threshold: {config.THRESHOLD_PROTRUDING_RATIO}")

            if "in_radius" in subplot_data.index:
                in_rad = subplot_data["in_radius"]
                rad_status = "✅" if in_rad else "⚠️"
                st.write(f"{rad_status} **In Radius:** {'Yes' if in_rad else 'No'}")
                st.caption(f"Radius: {config.THRESHOLD_WITHIN_RADIUS}m")

        # Show validation issues if invalid
        if not subplot_data["geom_valid"] and "reasons" in subplot_data.index:
            st.markdown("---")
            st.markdown("#### ❌ Validation Issues")

            reasons = str(subplot_data["reasons"]).split(";")
            for reason in reasons:
                if reason.strip():
                    st.error(f"• {reason.strip()}")

        # Show geometry preview (if not empty)
        if not subplot_data.geometry.is_empty:
            st.markdown("---")
            st.markdown("#### 🗺️ Geometry Preview")

            import folium
            from streamlit_folium import st_folium

            # Create small map
            centroid = subplot_data.geometry.centroid

            m = folium.Map(
                location=[centroid.y, centroid.x],
                zoom_start=15,
            )

            coords = list(subplot_data.geometry.exterior.coords)
            coords_latlon = [(lat, lon) for lon, lat in coords]

            color = "green" if subplot_data["geom_valid"] else "red"

            folium.Polygon(
                locations=coords_latlon,
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.4,
                weight=2,
            ).add_to(m)

            st_folium(m, width=700, height=400)

else:
    st.info("No subplots found with current filters")
