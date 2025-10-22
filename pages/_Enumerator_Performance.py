"""
Enumerator Performance Analysis - Complete quality control by enumerator
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import config
from ui.components import show_header
from utils.data_processor import get_validation_summary

# Page config
st.set_page_config(
    page_title="Enumerator Performance - " + config.APP_TITLE,
    page_icon="👥",
    layout="wide",
)

# Check if data exists
if "data" not in st.session_state or st.session_state.data is None:
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    st.info("👈 Use the sidebar to navigate back to the home page")
    st.stop()

# Header
show_header()

st.markdown("## 👥 Enumerator Performance Analysis")
st.markdown("Complete quality control and performance metrics by enumerator")

# Get data
gdf_subplots = st.session_state.data["subplots"]
raw_data = st.session_state.data.get("raw_data", {})

# Check if vegetation data available
has_vegetation = "plots_subplots_vegetation" in raw_data
has_measurements = "plots_subplots_vegetation_measurements" in raw_data
has_circumference = "complete" in raw_data

st.markdown("---")

# ============================================
# ENUMERATOR SELECTION
# ============================================

enumerators = (
    sorted(gdf_subplots["enumerator"].unique().tolist())
    if "enumerator" in gdf_subplots.columns
    else []
)

if not enumerators:
    st.error("No enumerator data found in the dataset")
    st.stop()

col1, col2 = st.columns([3, 1])

with col1:
    selected_enumerators = st.multiselect(
        "Select enumerators to analyze",
        options=enumerators,
        default=enumerators,
    )

with col2:
    st.metric("Total Enumerators", len(enumerators))

if not selected_enumerators:
    st.info("Please select at least one enumerator to analyze")
    st.stop()

# Filter data
filtered_gdf = gdf_subplots[gdf_subplots["enumerator"].isin(selected_enumerators)]

st.markdown("---")

# ============================================
# TABS
# ============================================

if has_vegetation:
    tabs = st.tabs(
        [
            "📊 Overview",
            "📐 Geometry Quality",
            "🌲 Vegetation Completeness",
            "🌳 Tree Density & Coverage",
            "📏 Measurements & Outliers",
            "⚠️ Quality Issues",
            "🌳 Species Lists & Management",
            "📋 Individual Details",
        ]
    )
else:
    tabs = st.tabs(["📊 Overview", "📐 Geometry Quality", "📋 Individual Details"])

# ============================================
# TAB 1: OVERVIEW
# ============================================

with tabs[0]:
    st.markdown("### 📊 Performance Overview")

    # Calculate stats by enumerator
    enum_stats = []

    for enum in selected_enumerators:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum]

        stats = {
            "Enumerator": enum,
            "Total Subplots": len(enum_data),
            "Valid Subplots": enum_data["geom_valid"].sum(),
            "Invalid Subplots": (~enum_data["geom_valid"]).sum(),
            "Valid %": (
                (enum_data["geom_valid"].sum() / len(enum_data) * 100)
                if len(enum_data) > 0
                else 0
            ),
        }

        if "area_m2" in enum_data.columns:
            stats["Avg Area (m²)"] = enum_data["area_m2"].mean()

        if has_vegetation and "total_trees" in enum_data.columns:
            stats["Total Trees"] = enum_data["total_trees"].sum()
            stats["Avg Trees/Subplot"] = enum_data["total_trees"].mean()

        enum_stats.append(stats)

    stats_df = pd.DataFrame(enum_stats)

    # Display summary table
    format_dict = {}
    gradient_cols = []

    if "Valid %" in stats_df.columns:
        format_dict["Valid %"] = "{:.1f}%"
        gradient_cols.append("Valid %")

    if "Avg Area (m²)" in stats_df.columns:
        format_dict["Avg Area (m²)"] = "{:.1f}"

    if "Total Trees" in stats_df.columns:
        format_dict["Total Trees"] = "{:.0f}"

    if "Avg Trees/Subplot" in stats_df.columns:
        format_dict["Avg Trees/Subplot"] = "{:.1f}"

    # Apply styling

    st.dataframe(
        stats_df,
        use_container_width=True,
        height=min(500, len(stats_df) * 35 + 38),
    )

    st.markdown("---")

    # Visualizations
    col1, col2 = st.columns(2)

    with col1:
        # Valid vs Invalid
        fig = px.bar(
            stats_df,
            x="Enumerator",
            y=["Valid Subplots", "Invalid Subplots"],
            title="Valid vs Invalid Subplots by Enumerator",
            barmode="stack",
            color_discrete_map={
                "Valid Subplots": "#28a745",
                "Invalid Subplots": "#dc3545",
            },
        )
        fig.update_layout(legend_title_text="Status")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Validation rate
        fig = px.bar(
            stats_df,
            x="Enumerator",
            y="Valid %",
            title="Validation Rate by Enumerator",
            color="Valid %",
            color_continuous_scale=["red", "yellow", "green"],
            range_color=[0, 100],
        )
        fig.add_hline(
            y=90, line_dash="dash", line_color="green", annotation_text="90% Target"
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    if has_vegetation:
        st.markdown("---")
        st.markdown("### 🌲 Vegetation Collection")

        col1, col2 = st.columns(2)

        with col1:
            if "Total Trees" in stats_df.columns:
                fig = px.bar(
                    stats_df,
                    x="Enumerator",
                    y="Total Trees",
                    title="Total Trees Measured by Enumerator",
                    color="Total Trees",
                    color_continuous_scale="Greens",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if "Avg Trees/Subplot" in stats_df.columns:
                fig = px.bar(
                    stats_df,
                    x="Enumerator",
                    y="Avg Trees/Subplot",
                    title="Average Trees per Subplot",
                    color="Avg Trees/Subplot",
                    color_continuous_scale="Blues",
                )
                st.plotly_chart(fig, use_container_width=True)

# ============================================
# TAB 2: GEOMETRY QUALITY
# ============================================

with tabs[1]:
    st.markdown("### 📐 Geometry Quality by Enumerator")

    # Validation issues breakdown
    st.markdown("#### ❌ Validation Issues Breakdown")

    issue_data = []

    for enum in selected_enumerators:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == enum]
        invalid_data = enum_data[~enum_data["geom_valid"]]

        if len(invalid_data) > 0 and "reasons" in invalid_data.columns:
            for reasons in invalid_data["reasons"]:
                if pd.notna(reasons) and str(reasons).strip():
                    for reason in str(reasons).split(";"):
                        reason = reason.strip()
                        if reason:
                            issue_data.append(
                                {"Enumerator": enum, "Issue": reason, "Count": 1}
                            )

    if issue_data:
        issues_df = pd.DataFrame(issue_data)
        issues_summary = (
            issues_df.groupby(["Enumerator", "Issue"])["Count"].sum().reset_index()
        )

        # Pivot for heatmap
        issues_pivot = issues_summary.pivot(
            index="Issue", columns="Enumerator", values="Count"
        ).fillna(0)

        fig = px.imshow(
            issues_pivot,
            title="Validation Issues Heatmap",
            labels=dict(x="Enumerator", y="Issue", color="Count"),
            color_continuous_scale="Reds",
            aspect="auto",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Detailed table
        with st.expander("📊 View detailed issue breakdown table"):
            st.dataframe(
                issues_summary.pivot(
                    index="Issue", columns="Enumerator", values="Count"
                ).fillna(0),
                use_container_width=True,
            )
    else:
        st.success("✅ No validation issues found!")

    st.markdown("---")

    # Geometry metrics comparison
    st.markdown("#### 📊 Geometry Metrics Distribution")

    col1, col2 = st.columns(2)

    with col1:
        if "area_m2" in filtered_gdf.columns:
            fig = px.box(
                filtered_gdf,
                x="enumerator",
                y="area_m2",
                title="Subplot Area Distribution by Enumerator",
                color="enumerator",
            )
            fig.add_hline(
                y=config.MIN_SUBPLOT_AREA_SIZE,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Min: {config.MIN_SUBPLOT_AREA_SIZE}",
            )
            fig.add_hline(
                y=config.MAX_SUBPLOT_AREA_SIZE,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Max: {config.MAX_SUBPLOT_AREA_SIZE}",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        if "nr_vertices" in filtered_gdf.columns:
            fig = px.box(
                filtered_gdf,
                x="enumerator",
                y="nr_vertices",
                title="Number of Vertices Distribution",
                color="enumerator",
            )
            st.plotly_chart(fig, use_container_width=True)

# ============================================
# TAB 3: VEGETATION COMPLETENESS (if available)
# ============================================

if has_vegetation:
    with tabs[2]:
        st.markdown("### 🌲 Vegetation Data Completeness")
        st.caption("Analysis of subplots without vegetation and their reasons")

        m_plots = raw_data["plots_subplots"]
        m_veg = raw_data["plots_subplots_vegetation"]

        # Filter by selected enumerators
        m_plots_filtered = m_plots[m_plots["enumerator"].isin(selected_enumerators)]
        m_veg_filtered = m_veg[m_veg["enumerator"].isin(selected_enumerators)]

        # Missing subplots analysis (like in notebook)
        st.markdown("#### 🔍 Subplots Without Vegetation Data")

        missing_by_enum = []

        for enum in selected_enumerators:
            enum_plots = m_plots[m_plots["enumerator"] == enum]
            enum_veg = m_veg[m_veg["enumerator"] == enum]

            subplots_veg = set(enum_veg["SUBPLOT_KEY"].unique())
            reference_subplots = set(enum_plots["SUBPLOT_KEY"].unique())
            missing_subplots = reference_subplots - subplots_veg

            missing_df = enum_plots[enum_plots["SUBPLOT_KEY"].isin(missing_subplots)]

            missing_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Subplots": len(reference_subplots),
                    "With Vegetation": len(subplots_veg),
                    "Missing Vegetation": len(missing_subplots),
                    "Missing %": (
                        (len(missing_subplots) / len(reference_subplots) * 100)
                        if len(reference_subplots) > 0
                        else 0
                    ),
                    "missing_df": missing_df,
                }
            )

        missing_summary = pd.DataFrame(
            [{k: v for k, v in d.items() if k != "missing_df"} for d in missing_by_enum]
        )

        # Visualization
        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                missing_summary,
                x="Enumerator",
                y=["With Vegetation", "Missing Vegetation"],
                title="Vegetation Data Completeness by Enumerator",
                barmode="stack",
                color_discrete_map={
                    "With Vegetation": "#28a745",
                    "Missing Vegetation": "#ffc107",
                },
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                missing_summary,
                use_container_width=True,
                height=300,
            )

        # Show reasons for missing vegetation
        st.markdown("---")
        st.markdown("#### 📝 Reasons for Missing Vegetation")

        selected_enum_missing = st.selectbox(
            "Select enumerator to view missing subplot reasons",
            options=selected_enumerators,
            key="missing_enum",
        )

        if selected_enum_missing:
            enum_missing_data = next(
                (
                    d
                    for d in missing_by_enum
                    if d["Enumerator"] == selected_enum_missing
                ),
                None,
            )

            if enum_missing_data and len(enum_missing_data["missing_df"]) > 0:
                st.write(
                    f"**{len(enum_missing_data['missing_df'])} subplots without vegetation data**"
                )

                if "subplot_comments" in enum_missing_data["missing_df"].columns:
                    reasons_display = enum_missing_data["missing_df"][
                        ["SUBPLOT_KEY", "subplot_comments"]
                    ].copy()
                    reasons_display.columns = ["Subplot ID", "Reason/Comment"]
                    st.dataframe(reasons_display, use_container_width=True, height=300)
                else:
                    st.dataframe(
                        enum_missing_data["missing_df"][["SUBPLOT_KEY"]],
                        use_container_width=True,
                        height=300,
                    )
            else:
                st.success(
                    f"✅ All subplots have vegetation data for {selected_enum_missing}"
                )

        st.markdown("---")

        # Measurement consistency check
        st.markdown("#### 🔄 Measurement Consistency Check")
        st.caption(
            "Subplots with only coverage (0 trees) should match subplots missing measurements"
        )

        consistency_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            # Subplots with 0 trees
            density = (
                enum_veg_data.groupby("SUBPLOT_KEY")
                .agg(
                    {
                        "vegetation_type_number": "sum",
                        "coverage_vegetation": "sum",
                    }
                )
                .reset_index()
            )

            subplots_coverage = density[density["vegetation_type_number"] == 0]

            # Subplots missing measurements
            if has_measurements:
                m_mea = raw_data["plots_subplots_vegetation_measurements"]
                enum_mea = m_mea[m_mea["enumerator"] == enum]

                veg_mea = set(enum_mea["SUBPLOT_KEY"].unique())
                reference_veg = set(enum_veg_data["SUBPLOT_KEY"].unique())
                missing_veg = reference_veg - veg_mea

                # Check if they match
                coverage_set = set(subplots_coverage["SUBPLOT_KEY"])
                match = len(coverage_set) == len(missing_veg)
                difference = len(coverage_set) - len(missing_veg)

                consistency_by_enum.append(
                    {
                        "Enumerator": enum,
                        "Subplots with 0 Trees": len(subplots_coverage),
                        "Missing Measurements": len(missing_veg),
                        "Difference": abs(difference),
                        "Match": "✅" if match else f"⚠️ {difference:+d}",
                    }
                )

        if consistency_by_enum:
            consistency_df = pd.DataFrame(consistency_by_enum)
            st.dataframe(consistency_df, use_container_width=True)

            mismatches = consistency_df[consistency_df["Difference"] > 0]
            if len(mismatches) > 0:
                st.warning(
                    f"⚠️ {len(mismatches)} enumerator(s) have inconsistencies between coverage and measurements"
                )
            else:
                st.success(
                    "✅ All enumerators have consistent coverage and measurement data"
                )

# ============================================
# TAB 4: TREE DENSITY & COVERAGE (if vegetation available)
# ============================================

if has_vegetation:
    with tabs[3]:
        st.markdown("### 🌳 Tree Density and Coverage Analysis")

        m_veg = raw_data["plots_subplots_vegetation"]

        # Filter by selected enumerators
        enum_veg = m_veg[m_veg["enumerator"].isin(selected_enumerators)]

        # Density analysis (like in notebook)
        st.markdown("#### 📊 Tree Density Distribution")

        density_parameters = [
            "enumerator",
            "SUBPLOT_KEY",
            "vegetation_type_number",
            "coverage_vegetation",
        ]

        density = enum_veg[density_parameters].copy()

        density_df = (
            density.groupby(["enumerator", "SUBPLOT_KEY"])
            .agg(
                {
                    "vegetation_type_number": "sum",
                    "coverage_vegetation": "sum",
                }
            )
            .reset_index()
        )

        # Distribution by enumerator
        col1, col2 = st.columns(2)

        with col1:
            fig = px.histogram(
                density_df,
                x="vegetation_type_number",
                color="enumerator",
                title="Distribution of Trees per Subplot",
                labels={"vegetation_type_number": "Number of Trees"},
                nbins=30,
                barmode="overlay",
            )
            fig.update_traces(opacity=0.7)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Box plot
            fig = px.box(
                density_df,
                x="enumerator",
                y="vegetation_type_number",
                title="Tree Count Distribution by Enumerator",
                color="enumerator",
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Subplots with zero trees
        st.markdown("#### 🔍 Subplots with Zero Trees")

        zero_trees_by_enum = []

        for enum in selected_enumerators:
            enum_density = density_df[density_df["enumerator"] == enum]
            zero_trees = enum_density[enum_density["vegetation_type_number"] == 0]

            zero_trees_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Subplots": len(enum_density),
                    "Zero Trees": len(zero_trees),
                    "Zero Trees %": (
                        (len(zero_trees) / len(enum_density) * 100)
                        if len(enum_density) > 0
                        else 0
                    ),
                    "Avg Coverage (Zero Trees)": (
                        zero_trees["coverage_vegetation"].mean()
                        if len(zero_trees) > 0
                        else 0
                    ),
                }
            )

        zero_trees_df = pd.DataFrame(zero_trees_by_enum)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                zero_trees_df,
                x="Enumerator",
                y="Zero Trees %",
                title="Percentage of Subplots with Zero Trees",
                color="Zero Trees %",
                color_continuous_scale="Oranges",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                zero_trees_df,
                use_container_width=True,
                height=300,
            )

        st.markdown("---")

        # Coverage analysis
        st.markdown("#### 🌾 Coverage Vegetation Analysis")

        fig = px.box(
            density_df,
            x="enumerator",
            y="coverage_vegetation",
            title="Coverage Distribution by Enumerator",
            color="enumerator",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Summary stats
        coverage_stats = (
            density_df.groupby("enumerator")["coverage_vegetation"]
            .agg(
                [
                    ("Mean", "mean"),
                    ("Median", "median"),
                    ("Min", "min"),
                    ("Max", "max"),
                ]
            )
            .reset_index()
        )

        st.dataframe(
            coverage_stats,
            use_container_width=True,
        )

# ============================================
# TAB 5: MEASUREMENTS & OUTLIERS (if available)
# ============================================

if has_vegetation and has_measurements:
    with tabs[4]:
        st.markdown("### 📏 Measurement Data Quality & Outliers")

        m_mea = raw_data["plots_subplots_vegetation_measurements"]
        enum_mea = m_mea[m_mea["enumerator"].isin(selected_enumerators)]

        # Height outliers
        st.markdown("#### 📊 Height Outlier Detection")
        st.caption(
            "Outliers are trees with height > 4× or < 0.25× the median height of their group"
        )

        from utils.data_processor import get_height_outliers

        height_outliers = get_height_outliers(raw_data, threshold_multiplier=4)

        if height_outliers:
            # Filter for selected enumerators
            enum_outliers = height_outliers["outliers_df"][
                height_outliers["outliers_df"]["enumerator"].isin(selected_enumerators)
            ]

            outliers_by_enum = (
                enum_outliers.groupby("enumerator").size().reset_index(name="Outliers")
            )
            total_by_enum = (
                enum_mea.groupby("enumerator").size().reset_index(name="Total")
            )

            height_quality = pd.merge(
                outliers_by_enum, total_by_enum, on="enumerator", how="outer"
            ).fillna(0)
            height_quality["Outlier %"] = (
                height_quality["Outliers"] / height_quality["Total"] * 100
            )

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    height_quality,
                    x="enumerator",
                    y="Outlier %",
                    title="Height Outliers by Enumerator (%)",
                    color="Outlier %",
                    color_continuous_scale="Reds",
                )
                fig.add_hline(
                    y=2,
                    line_dash="dash",
                    line_color="orange",
                    annotation_text="2% Threshold",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(
                    height_quality,
                    use_container_width=True,
                    height=300,
                )

            # Show specific outliers
            with st.expander("🔍 View height outliers"):
                selected_enum_height = st.selectbox(
                    "Select enumerator", options=selected_enumerators, key="height_enum"
                )

                if selected_enum_height:
                    enum_height_outliers = enum_outliers[
                        enum_outliers["enumerator"] == selected_enum_height
                    ]

                    if len(enum_height_outliers) > 0:
                        display_cols = [
                            "VEGETATION_KEY",
                            "tree_height_m",
                            "median_height",
                            "tree_year_planted",
                            "Upper_outliers",
                            "Lower_outliers",
                        ]
                        st.dataframe(
                            enum_height_outliers[display_cols],
                            use_container_width=True,
                            height=300,
                        )
                    else:
                        st.success(f"✅ No height outliers for {selected_enum_height}")

        st.markdown("---")

        # Tall trees check (>25m)
        st.markdown("#### 🌲 Very Tall Trees (>25m)")
        st.caption("Check if tall trees are realistic with planting age")

        tall_trees = enum_mea[enum_mea["tree_height_m"] > 25]

        if len(tall_trees) > 0:
            tall_by_enum = (
                tall_trees.groupby("enumerator").size().reset_index(name="Tall Trees")
            )

            st.dataframe(tall_by_enum, use_container_width=True)

            with st.expander("🔍 View tall trees details"):
                tall_display = tall_trees[
                    [
                        "enumerator",
                        "VEGETATION_KEY",
                        "tree_height_m",
                        "tree_year_planted",
                        "SUBPLOT_KEY",
                    ]
                ].sort_values("tree_height_m", ascending=False)

                st.dataframe(tall_display, use_container_width=True, height=300)
        else:
            st.success("✅ No trees >25m found")

        st.markdown("---")

        # Circumference outliers
        if has_circumference:
            st.markdown("#### 📏 Circumference Outlier Detection")
            st.caption(
                "Outliers are measurements > 4× or < 0.25× the median of their group"
            )

            from utils.data_processor import get_circumference_outliers

            circ_outliers = get_circumference_outliers(raw_data, threshold_multiplier=4)

            if circ_outliers:
                # Filter for selected enumerators
                enum_circ_outliers = circ_outliers["outliers_df"][
                    circ_outliers["outliers_df"]["enumerator"].isin(
                        selected_enumerators
                    )
                ]

                circ_outliers_by_enum = (
                    enum_circ_outliers.groupby("enumerator")
                    .size()
                    .reset_index(name="Outliers")
                )
                circ_total_by_enum = (
                    raw_data["complete"][
                        raw_data["complete"]["enumerator"].isin(selected_enumerators)
                    ]
                    .groupby("enumerator")
                    .size()
                    .reset_index(name="Total")
                )

                circ_quality = pd.merge(
                    circ_outliers_by_enum,
                    circ_total_by_enum,
                    on="enumerator",
                    how="outer",
                ).fillna(0)
                circ_quality["Outlier %"] = (
                    circ_quality["Outliers"] / circ_quality["Total"] * 100
                )

                col1, col2 = st.columns([2, 1])

                with col1:
                    fig = px.bar(
                        circ_quality,
                        x="enumerator",
                        y="Outlier %",
                        title="Circumference Outliers by Enumerator (%)",
                        color="Outlier %",
                        color_continuous_scale="Oranges",
                    )
                    fig.add_hline(
                        y=2,
                        line_dash="dash",
                        line_color="orange",
                        annotation_text="2% Threshold",
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with col2:
                    st.dataframe(
                        circ_quality,
                        use_container_width=True,
                        height=300,
                    )

                # Large circumference check (>90cm at BH)
                st.markdown("---")
                st.markdown("#### ⚠️ Large Circumferences (>90cm at BH)")

                m_cir = raw_data["complete"]
                large_circ = m_cir[
                    (m_cir["enumerator"].isin(selected_enumerators))
                    & (m_cir["circumference_bh"] > 90)
                ]

                if len(large_circ) > 0:
                    large_by_enum = (
                        large_circ.groupby("enumerator")
                        .size()
                        .reset_index(name="Count")
                    )
                    st.dataframe(large_by_enum, use_container_width=True)

                    with st.expander("🔍 View large circumference details"):
                        display_cols = [
                            "enumerator",
                            "MEASUREMENT_KEY",
                            "circumference_bh",
                            "tree_year_planted",
                            "vegetation_type_number",
                        ]
                        st.dataframe(
                            large_circ[display_cols].sort_values(
                                "circumference_bh", ascending=False
                            ),
                            use_container_width=True,
                            height=300,
                        )
                else:
                    st.success("✅ No circumferences >90cm found")

        st.markdown("---")

        # Stem count check
        st.markdown("#### 🌿 Multi-Stem Trees (>20 stems)")

        multi_stem = enum_mea[enum_mea["nr_stems_bh"] > 20]

        if len(multi_stem) > 0:
            stem_by_enum = (
                multi_stem.groupby("enumerator")
                .size()
                .reset_index(name="Multi-Stem Trees")
            )

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    stem_by_enum,
                    x="enumerator",
                    y="Multi-Stem Trees",
                    title="Trees with >20 Stems by Enumerator",
                    color="Multi-Stem Trees",
                    color_continuous_scale="Purples",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(stem_by_enum, use_container_width=True, height=300)

            with st.expander("🔍 View multi-stem details"):
                display_cols = [
                    "enumerator",
                    "VEGETATION_KEY",
                    "nr_stems_bh",
                    "woody_species",
                    "other_species",
                    "vegetation_type_number",
                ]
                st.dataframe(
                    multi_stem[display_cols].sort_values(
                        "nr_stems_bh", ascending=False
                    ),
                    use_container_width=True,
                    height=300,
                )
        else:
            st.success("✅ No trees with >20 stems found")

# ============================================
# TAB 6: QUALITY ISSUES (if vegetation available)
# ============================================

if has_vegetation:
    with tabs[5]:
        st.markdown("### ⚠️ Data Quality Issues Summary")

        m_veg = raw_data["plots_subplots_vegetation"]

        # Coverage quality check (from notebook)
        st.markdown("#### 🌾 Coverage Quality Check")
        st.caption(
            "Coverage should ONLY be used for non-woody species (grasses, weeds, crops)"
        )
        st.caption("**Target:** <5% 'other' species in coverage")

        coverage_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            coverage = enum_veg_data[
                (enum_veg_data["vegetation_type_woody"] == "nonwoody_coverage")
                | (enum_veg_data["vegetation_type_youngtree"] == "no_coverage")
            ]

            enumerator_coverage = coverage.dropna(subset=["other_species"])

            total = len(coverage)
            with_other = len(enumerator_coverage)
            pct = (with_other / total * 100) if total > 0 else 0

            status = "✅ Good" if pct <= 5 else "⚠️ Review" if pct <= 10 else "❌ Poor"

            coverage_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Coverage Entries": total,
                    "Using 'Other' Species": with_other,
                    "Other %": pct,
                    "Status": status,
                }
            )

        coverage_quality_df = pd.DataFrame(coverage_by_enum)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                coverage_quality_df,
                x="Enumerator",
                y="Other %",
                title="'Other' Species in Coverage (%)",
                color="Other %",
                color_continuous_scale=["green", "yellow", "red"],
                range_color=[0, 15],
            )
            fig.add_hline(
                y=5, line_dash="dash", line_color="green", annotation_text="5% Target"
            )
            fig.add_hline(
                y=10,
                line_dash="dash",
                line_color="orange",
                annotation_text="10% Warning",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                coverage_quality_df,
                use_container_width=True,
                height=300,
            )

        # Show problematic coverage entries
        problem_enums = coverage_quality_df[coverage_quality_df["Other %"] > 5][
            "Enumerator"
        ].tolist()

        if problem_enums:
            st.warning(f"⚠️ {len(problem_enums)} enumerator(s) exceed 5% threshold")

            with st.expander("🔍 View problematic coverage entries"):
                selected_problem_enum = st.selectbox(
                    "Select enumerator", options=problem_enums, key="problem_enum"
                )

                if selected_problem_enum:
                    enum_veg_data = m_veg[m_veg["enumerator"] == selected_problem_enum]
                    coverage = enum_veg_data[
                        (enum_veg_data["vegetation_type_woody"] == "nonwoody_coverage")
                        | (enum_veg_data["vegetation_type_youngtree"] == "no_coverage")
                    ]
                    problem_coverage = coverage.dropna(subset=["other_species"])

                    display_cols = [
                        "SUBPLOT_KEY",
                        "other_species",
                        "language_other_species",
                        "coverage_vegetation",
                    ]
                    st.dataframe(
                        problem_coverage[display_cols],
                        use_container_width=True,
                        height=300,
                    )
        else:
            st.success("✅ All enumerators meet coverage quality standards")

        st.markdown("---")

        # Species identification quality
        st.markdown("#### 🌳 Species Identification Quality")

        species_quality = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            # Primary trees with 'other'
            primary_total = len(
                enum_veg_data[
                    enum_veg_data["vegetation_type_primary"] == "yes_primary_group"
                ]
            )
            primary_other = len(
                enum_veg_data[
                    (enum_veg_data["vegetation_type_primary"] == "yes_primary_group")
                    & (enum_veg_data["woody_species"] == "other")
                ].dropna(subset=["other_species"])
            )

            # Young trees with 'other'
            young_total = len(
                enum_veg_data[
                    enum_veg_data["vegetation_type_youngtree"] == "yes_groupbelow1.3"
                ]
            )
            young_other = len(
                enum_veg_data[
                    (enum_veg_data["vegetation_type_youngtree"] == "yes_groupbelow1.3")
                    & (enum_veg_data["woody_species"] == "other")
                ].dropna(subset=["other_species"])
            )

            species_quality.append(
                {
                    "Enumerator": enum,
                    "Primary Trees": primary_total,
                    "Primary 'Other'": primary_other,
                    "Primary Other %": (
                        (primary_other / primary_total * 100)
                        if primary_total > 0
                        else 0
                    ),
                    "Young Trees": young_total,
                    "Young 'Other'": young_other,
                    "Young Other %": (
                        (young_other / young_total * 100) if young_total > 0 else 0
                    ),
                }
            )

        species_quality_df = pd.DataFrame(species_quality)

        st.dataframe(
            species_quality_df,
            use_container_width=True,
        )
if has_vegetation:
    # Update the tabs list at the top to include this new tab
    # Change line ~85 from:
    # tabs = st.tabs([...])
    # To include: "🌳 Species Lists & Management"

    with tabs[6]:  # Adjust index based on total tabs
        st.markdown("### 🌳 Species Lists & Management Quality Checks")

        m_veg = raw_data["plots_subplots_vegetation"]

        # Filter by selected enumerators
        enum_veg = m_veg[m_veg["enumerator"].isin(selected_enumerators)]

        # ============================================
        # 1. PRIMARY TREES LIST
        # ============================================

        st.markdown("#### 🌲 Primary Trees - 'Other' Species Check")
        st.caption(
            "Trees in primary group (yes_primary_group) using 'other' as woody_species"
        )

        primary_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            trees_primary = enum_veg_data[
                (enum_veg_data["vegetation_type_primary"] == "yes_primary_group")
                & (enum_veg_data["woody_species"] == "other")
            ]

            enumerator_trees_primary = trees_primary.dropna(
                subset=["vegetation_type_number", "other_species"]
            )

            total_trees = trees_primary["vegetation_type_number"].sum()
            other_trees = enumerator_trees_primary["vegetation_type_number"].sum()

            primary_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Primary Trees": (
                        int(total_trees) if pd.notna(total_trees) else 0
                    ),
                    "Primary 'Other' Entries": len(enumerator_trees_primary),
                    "Primary 'Other' Trees": (
                        int(other_trees) if pd.notna(other_trees) else 0
                    ),
                }
            )

        primary_df = pd.DataFrame(primary_by_enum)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                primary_df,
                x="Enumerator",
                y=["Primary 'Other' Trees"],
                title="Primary Trees Using 'Other' Species",
                color_discrete_sequence=["#ff7f0e"],
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(primary_df, use_container_width=True, height=300)

        # Show details
        with st.expander("🔍 View primary 'other' species details"):
            selected_enum_primary = st.selectbox(
                "Select enumerator", options=selected_enumerators, key="primary_enum"
            )

            if selected_enum_primary:
                enum_veg_data = m_veg[m_veg["enumerator"] == selected_enum_primary]

                trees_primary = enum_veg_data[
                    (enum_veg_data["vegetation_type_primary"] == "yes_primary_group")
                    & (enum_veg_data["woody_species"] == "other")
                ]

                enumerator_trees_primary = trees_primary[
                    [
                        "SUBPLOT_KEY",
                        "other_species",
                        "language_other_species",
                        "vegetation_type_number",
                    ]
                ].dropna(subset=["vegetation_type_number", "other_species"])

                if len(enumerator_trees_primary) > 0:
                    st.dataframe(
                        enumerator_trees_primary, use_container_width=True, height=300
                    )
                else:
                    st.success(
                        f"✅ No 'other' species in primary trees for {selected_enum_primary}"
                    )

        st.markdown("---")

        # ============================================
        # 2. YOUNG TREES LIST
        # ============================================

        st.markdown("#### 🌱 Young Trees (<1.3m) - 'Other' Species Check")
        st.caption("Young trees (yes_groupbelow1.3) using 'other' as woody_species")

        young_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            trees_young = enum_veg_data[
                (enum_veg_data["vegetation_type_youngtree"] == "yes_groupbelow1.3")
                & (enum_veg_data["woody_species"] == "other")
            ]

            enumerator_trees_young = trees_young.dropna(
                subset=["vegetation_type_number", "other_species"]
            )

            total_trees = trees_young["vegetation_type_number"].sum()
            other_trees = enumerator_trees_young["vegetation_type_number"].sum()

            young_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Young Trees": (
                        int(total_trees) if pd.notna(total_trees) else 0
                    ),
                    "Young 'Other' Entries": len(enumerator_trees_young),
                    "Young 'Other' Trees": (
                        int(other_trees) if pd.notna(other_trees) else 0
                    ),
                }
            )

        young_df = pd.DataFrame(young_by_enum)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                young_df,
                x="Enumerator",
                y=["Young 'Other' Trees"],
                title="Young Trees Using 'Other' Species",
                color_discrete_sequence=["#2ca02c"],
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(young_df, use_container_width=True, height=300)

        # Show details
        with st.expander("🔍 View young 'other' species details"):
            selected_enum_young = st.selectbox(
                "Select enumerator", options=selected_enumerators, key="young_enum"
            )

            if selected_enum_young:
                enum_veg_data = m_veg[m_veg["enumerator"] == selected_enum_young]

                trees_young = enum_veg_data[
                    (enum_veg_data["vegetation_type_youngtree"] == "yes_groupbelow1.3")
                    & (enum_veg_data["woody_species"] == "other")
                ]

                enumerator_trees_young = trees_young[
                    [
                        "SUBPLOT_KEY",
                        "other_species",
                        "language_other_species",
                        "vegetation_type_number",
                    ]
                ].dropna(subset=["vegetation_type_number", "other_species"])

                if len(enumerator_trees_young) > 0:
                    st.dataframe(
                        enumerator_trees_young, use_container_width=True, height=300
                    )
                else:
                    st.success(
                        f"✅ No 'other' species in young trees for {selected_enum_young}"
                    )

        st.markdown("---")

        # ============================================
        # 3. NON-PRIMARY TREES LIST
        # ============================================

        st.markdown("#### 🌳 Non-Primary Trees - 'Other' Species Check")
        st.caption(
            "Trees marked as non-primary (vegetation_type_primary = 'no') using 'other' as woody_species"
        )

        non_primary_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            trees_non_primary = enum_veg_data[
                (enum_veg_data["vegetation_type_primary"] == "no")
                & (enum_veg_data["woody_species"] == "other")
            ]

            enumerator_trees = trees_non_primary.dropna(
                subset=["vegetation_type_number", "other_species"]
            )

            total_trees = trees_non_primary["vegetation_type_number"].sum()
            other_trees = enumerator_trees["vegetation_type_number"].sum()
            percentage = (other_trees / total_trees * 100) if total_trees > 0 else 0

            non_primary_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Non-Primary Trees": (
                        int(total_trees) if pd.notna(total_trees) else 0
                    ),
                    "Non-Primary 'Other' Entries": len(enumerator_trees),
                    "Non-Primary 'Other' Trees": (
                        int(other_trees) if pd.notna(other_trees) else 0
                    ),
                    "Percentage": percentage,
                }
            )

        non_primary_df = pd.DataFrame(non_primary_by_enum)

        col1, col2 = st.columns([2, 1])

        with col1:
            fig = px.bar(
                non_primary_df,
                x="Enumerator",
                y="Percentage",
                title="Non-Primary Trees Using 'Other' Species (%)",
                color="Percentage",
                color_continuous_scale="Blues",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.dataframe(
                non_primary_df,
                use_container_width=True,
                height=300,
            )

        # Show details
        with st.expander("🔍 View non-primary 'other' species details"):
            selected_enum_non_primary = st.selectbox(
                "Select enumerator",
                options=selected_enumerators,
                key="non_primary_enum",
            )

            if selected_enum_non_primary:
                enum_veg_data = m_veg[m_veg["enumerator"] == selected_enum_non_primary]

                trees_non_primary = enum_veg_data[
                    (enum_veg_data["vegetation_type_primary"] == "no")
                    & (enum_veg_data["woody_species"] == "other")
                ]

                enumerator_trees = trees_non_primary[
                    [
                        "SUBPLOT_KEY",
                        "other_species",
                        "language_other_species",
                        "vegetation_type_number",
                    ]
                ].dropna(subset=["vegetation_type_number", "other_species"])

                if len(enumerator_trees) > 0:
                    st.dataframe(enumerator_trees, use_container_width=True, height=300)
                else:
                    st.success(
                        f"✅ No 'other' species in non-primary trees for {selected_enum_non_primary}"
                    )

        st.markdown("---")

        # ============================================
        # 4. PALM LIST CHECK
        # ============================================

        st.markdown("#### 🌴 Palm Species - Quality Check")
        st.caption("**Target:** <5% 'other' species in palms category")

        palm_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            palms = enum_veg_data[enum_veg_data["vegetation_species_type"] == "palms"]

            enumerator_palms = palms.dropna(
                subset=["vegetation_type_number", "other_species"]
            )

            total_palms = palms["vegetation_type_number"].sum()
            other_palms = enumerator_palms["vegetation_type_number"].sum()
            percentage = (other_palms / total_palms * 100) if total_palms > 0 else 0

            status = (
                "✅ Good"
                if percentage <= 5
                else "⚠️ Review" if percentage <= 10 else "❌ Poor"
            )

            palm_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Palms": int(total_palms) if pd.notna(total_palms) else 0,
                    "Palm 'Other' Count": len(enumerator_palms),
                    "Other %": percentage,
                    "Status": status,
                }
            )

        palm_df = pd.DataFrame(palm_by_enum)

        # Filter out enumerators with no palms
        palm_df_display = palm_df[palm_df["Total Palms"] > 0]

        if len(palm_df_display) > 0:
            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    palm_df_display,
                    x="Enumerator",
                    y="Other %",
                    title="'Other' Species in Palms (%)",
                    color="Other %",
                    color_continuous_scale=["green", "yellow", "red"],
                    range_color=[0, 15],
                )
                fig.add_hline(
                    y=5,
                    line_dash="dash",
                    line_color="green",
                    annotation_text="5% Target",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(
                    palm_df_display,
                    use_container_width=True,
                    height=300,
                )

            # Check for issues
            palm_issues = palm_df_display[palm_df_display["Other %"] > 5]
            if len(palm_issues) > 0:
                st.warning(
                    f"⚠️ {len(palm_issues)} enumerator(s) exceed 5% threshold for palms"
                )
            else:
                st.success("✅ All enumerators meet palm quality standards")
        else:
            st.info("ℹ️ No palm species recorded in the selected data")

        st.markdown("---")

        # ============================================
        # 5. BAMBOO LIST CHECK
        # ============================================

        st.markdown("#### 🎋 Bamboo Species - Quality Check")
        st.caption("**Target:** <5% 'other' species in bamboo category")

        bamboo_by_enum = []

        for enum in selected_enumerators:
            enum_veg_data = m_veg[m_veg["enumerator"] == enum]

            bamboo = enum_veg_data[enum_veg_data["vegetation_species_type"] == "bamboo"]

            enumerator_bamboo = bamboo.dropna(
                subset=["vegetation_type_number", "other_species"]
            )

            total_bamboo = bamboo["vegetation_type_number"].sum()
            other_bamboo = enumerator_bamboo["vegetation_type_number"].sum()
            percentage = (other_bamboo / total_bamboo * 100) if total_bamboo > 0 else 0

            status = (
                "✅ Good"
                if percentage <= 5
                else "⚠️ Review" if percentage <= 10 else "❌ Poor"
            )

            bamboo_by_enum.append(
                {
                    "Enumerator": enum,
                    "Total Bamboo": int(total_bamboo) if pd.notna(total_bamboo) else 0,
                    "Bamboo 'Other' Count": len(enumerator_bamboo),
                    "Other %": percentage,
                    "Status": status,
                }
            )

        bamboo_df = pd.DataFrame(bamboo_by_enum)

        # Filter out enumerators with no bamboo
        bamboo_df_display = bamboo_df[bamboo_df["Total Bamboo"] > 0]

        if len(bamboo_df_display) > 0:
            col1, col2 = st.columns([2, 1])

            with col1:
                fig = px.bar(
                    bamboo_df_display,
                    x="Enumerator",
                    y="Other %",
                    title="'Other' Species in Bamboo (%)",
                    color="Other %",
                    color_continuous_scale=["green", "yellow", "red"],
                    range_color=[0, 15],
                )
                fig.add_hline(
                    y=5,
                    line_dash="dash",
                    line_color="green",
                    annotation_text="5% Target",
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(
                    bamboo_df_display,
                    use_container_width=True,
                    height=300,
                )

            # Check for issues
            bamboo_issues = bamboo_df_display[bamboo_df_display["Other %"] > 5]
            if len(bamboo_issues) > 0:
                st.warning(
                    f"⚠️ {len(bamboo_issues)} enumerator(s) exceed 5% threshold for bamboo"
                )
            else:
                st.success("✅ All enumerators meet bamboo quality standards")
        else:
            st.info("ℹ️ No bamboo species recorded in the selected data")

        st.markdown("---")

        # ============================================
        # 6. COPPICING AND POLLARDING CHECK
        # ============================================

        if has_measurements:
            st.markdown("#### ✂️ Coppicing & Pollarding Quality Check")
            st.caption("Outlier detection for coppiced height (>4× or <0.25× median)")

            m_mea = raw_data["plots_subplots_vegetation_measurements"]
            enum_mea = m_mea[m_mea["enumerator"].isin(selected_enumerators)]

            # Check if coppicing columns exist
            required_cols = ["coppiced_height", "tree_coppiced"]
            has_coppice_data = all(col in enum_mea.columns for col in required_cols)

            if not has_coppice_data:
                st.info("ℹ️ No coppicing/pollarding data available in this dataset")
                st.caption("Required columns: coppiced_height, tree_coppiced")
            else:
                # Calculate median coppiced height per vegetation group
                available_cols = [
                    "enumerator",
                    "VEGETATION_KEY",
                    "vegetation_type_number",
                    "tree_height_m",
                ]

                # Add optional columns if they exist
                if "prune_height" in enum_mea.columns:
                    available_cols.append("prune_height")
                if "coppiced_height" in enum_mea.columns:
                    available_cols.append("coppiced_height")
                if "tree_year_planted" in enum_mea.columns:
                    available_cols.append("tree_year_planted")
                if "tree_prune" in enum_mea.columns:
                    available_cols.append("tree_prune")
                if "tree_coppiced" in enum_mea.columns:
                    available_cols.append("tree_coppiced")

                coppice_check = enum_mea[available_cols].copy()

                # Only analyze trees with coppiced height data
                coppice_check_filtered = coppice_check.dropna(
                    subset=["coppiced_height"]
                )

                if len(coppice_check_filtered) > 0:
                    median_cop_check = (
                        coppice_check_filtered.groupby("VEGETATION_KEY")[
                            "coppiced_height"
                        ]
                        .median()
                        .reset_index(name="median_coppiced")
                    )

                    coppiced_total = pd.merge(
                        coppice_check_filtered,
                        median_cop_check,
                        how="inner",
                        on="VEGETATION_KEY",
                    )

                    coppiced_total["Upper_outliers"] = coppiced_total.apply(
                        lambda row: (
                            "outlier"
                            if pd.notna(row["median_coppiced"])
                            and row["coppiced_height"] > (row["median_coppiced"] * 4)
                            else "ok"
                        ),
                        axis=1,
                    )
                    coppiced_total["Lower_outliers"] = coppiced_total.apply(
                        lambda row: (
                            "outlier"
                            if pd.notna(row["median_coppiced"])
                            and row["median_coppiced"] > 0
                            and row["coppiced_height"] < (row["median_coppiced"] / 4)
                            else "ok"
                        ),
                        axis=1,
                    )

                    # Count outliers by enumerator
                    outliers = coppiced_total[
                        (coppiced_total["Upper_outliers"] == "outlier")
                        | (coppiced_total["Lower_outliers"] == "outlier")
                    ]

                    coppice_by_enum = []

                    for enum in selected_enumerators:
                        enum_coppice = coppiced_total[
                            coppiced_total["enumerator"] == enum
                        ]
                        enum_outliers = outliers[outliers["enumerator"] == enum]

                        total = len(enum_coppice)
                        outlier_count = len(enum_outliers)
                        percentage = (outlier_count / total * 100) if total > 0 else 0

                        coppice_by_enum.append(
                            {
                                "Enumerator": enum,
                                "Total Coppiced": total,
                                "Outliers": outlier_count,
                                "Outlier %": percentage,
                            }
                        )

                    coppice_df = pd.DataFrame(coppice_by_enum)

                    # Filter out enumerators with no coppiced trees
                    coppice_df_display = coppice_df[coppice_df["Total Coppiced"] > 0]

                    if len(coppice_df_display) > 0:
                        col1, col2 = st.columns([2, 1])

                        with col1:
                            fig = px.bar(
                                coppice_df_display,
                                x="Enumerator",
                                y="Outlier %",
                                title="Coppiced Height Outliers by Enumerator (%)",
                                color="Outlier %",
                                color_continuous_scale="Reds",
                            )
                            fig.add_hline(
                                y=2,
                                line_dash="dash",
                                line_color="orange",
                                annotation_text="2% Threshold",
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        with col2:
                            st.dataframe(
                                coppice_df_display, use_container_width=True, height=300
                            )

                        # Show outlier details
                        with st.expander("🔍 View coppicing outliers"):
                            selected_enum_coppice = st.selectbox(
                                "Select enumerator",
                                options=selected_enumerators,
                                key="coppice_enum",
                            )

                            if selected_enum_coppice:
                                enum_coppice_outliers = outliers[
                                    outliers["enumerator"] == selected_enum_coppice
                                ]

                                if len(enum_coppice_outliers) > 0:
                                    display_cols = [
                                        "VEGETATION_KEY",
                                        "coppiced_height",
                                        "median_coppiced",
                                        "tree_height_m",
                                    ]

                                    # Add optional columns
                                    if (
                                        "tree_year_planted"
                                        in enum_coppice_outliers.columns
                                    ):
                                        display_cols.append("tree_year_planted")

                                    display_cols.extend(
                                        ["Upper_outliers", "Lower_outliers"]
                                    )

                                    st.dataframe(
                                        enum_coppice_outliers[display_cols],
                                        use_container_width=True,
                                        height=300,
                                    )
                                else:
                                    st.success(
                                        f"✅ No coppicing outliers for {selected_enum_coppice}"
                                    )
                    else:
                        st.info("ℹ️ No coppiced trees recorded in the selected data")
                else:
                    st.info("ℹ️ No coppiced height data available")

# ============================================
# LAST TAB: INDIVIDUAL DETAILS
# ============================================

with tabs[-1]:
    st.markdown("### 📋 Individual Enumerator Detailed View")

    selected_enum = st.selectbox(
        "Select enumerator for complete breakdown",
        options=selected_enumerators,
        key="detail_enum",
    )

    if selected_enum:
        enum_data = filtered_gdf[filtered_gdf["enumerator"] == selected_enum]

        st.markdown(f"#### Complete Data for: **{selected_enum}**")

        # Summary metrics
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("Total Subplots", len(enum_data))

        with col2:
            valid = enum_data["geom_valid"].sum()
            st.metric("Valid", valid, f"{valid/len(enum_data)*100:.1f}%")

        with col3:
            invalid = (~enum_data["geom_valid"]).sum()
            st.metric("Invalid", invalid)

        with col4:
            if "total_trees" in enum_data.columns:
                st.metric("Total Trees", f"{enum_data['total_trees'].sum():.0f}")

        with col5:
            if "area_m2" in enum_data.columns:
                st.metric("Avg Area", f"{enum_data['area_m2'].mean():.1f} m²")

        st.markdown("---")

        # All subplots table
        st.markdown("#### 📊 All Subplots")

        display_cols = ["subplot_id", "geom_valid"]

        for col in ["area_m2", "nr_vertices", "total_trees", "avg_coverage", "reasons"]:
            if col in enum_data.columns:
                display_cols.append(col)

        st.dataframe(
            enum_data[display_cols],
            use_container_width=True,
            height=400,
        )

        # Export options
        st.markdown("---")
        st.markdown("#### 📥 Export Options")

        col1, col2 = st.columns(2)

        with col1:
            csv_data = enum_data.drop(columns=["geometry"], errors="ignore").to_csv(
                index=False
            )
            st.download_button(
                f"📊 Download {selected_enum}'s Data (CSV)",
                data=csv_data,
                file_name=f"{config.PARTNER}_{selected_enum}_complete_data.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col2:
            if has_vegetation:
                # Export vegetation data for this enumerator
                enum_veg_export = raw_data["plots_subplots_vegetation"][
                    raw_data["plots_subplots_vegetation"]["enumerator"] == selected_enum
                ]
                veg_csv = enum_veg_export.to_csv(index=False)

                st.download_button(
                    f"🌲 Download {selected_enum}'s Vegetation Data (CSV)",
                    data=veg_csv,
                    file_name=f"{config.PARTNER}_{selected_enum}_vegetation_data.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
