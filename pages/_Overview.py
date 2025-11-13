"""
Overview Dashboard Page
"""

import streamlit as st
import pandas as pd
import config
from ui.components import (
    show_header,
    show_metrics_row,
    show_status_message,
    create_sidebar_filters,
    show_sidebar_info,
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
    page_title="Overview - Ground Truth DQM",
    page_icon="📊",
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

# Get data
gdf_subplots = st.session_state.data["subplots"]

# Show sidebar info
show_sidebar_info()

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

# Export section
st.markdown("---")
st.markdown("## 📥 Export All Quality Checks")
st.caption("Download comprehensive quality report with all validation checks")

if st.button(
    "📥 Generate Complete Quality Report (Excel)",
    use_container_width=True,
    type="primary",
):
    with st.spinner("Generating comprehensive quality report..."):
        try:
            from io import BytesIO
            from utils.data_merge_utils import (
                merge_with_enumerator,
                calculate_tree_age,
                get_species_column,
                add_tree_name_column,
            )
            from utils.vegetation_validation import (
                get_missing_subplots,
                check_coverage_only_subplots,
                get_young_trees_with_other,
                get_primary_trees_with_other,
                get_non_primary_trees_with_other,
                validate_species_lists,
                detect_stem_outliers,
                detect_height_outliers,
                detect_circumference_outliers,
                detect_suspicious_circumference_by_age,
            )
            from utils.export_helpers import adjust_excel_column_widths

            # Get raw data
            raw_data = st.session_state.data.get("raw_data", {})

            # Check data availability
            has_vegetation = "plots_subplots_vegetation" in raw_data
            has_measurements = "plots_subplots_vegetation_measurements" in raw_data
            has_complete = "complete" in raw_data

            if not has_vegetation:
                st.error("❌ Vegetation data not available for export")
                st.stop()

            # Extract data
            plots_df = raw_data.get("plots_subplots", pd.DataFrame())
            veg_df = raw_data["plots_subplots_vegetation"].copy()
            meas_df = (
                raw_data.get("plots_subplots_vegetation_measurements", pd.DataFrame())
                if has_measurements
                else pd.DataFrame()
            )
            complete_df = (
                raw_data.get("complete", pd.DataFrame())
                if has_complete
                else pd.DataFrame()
            )

            # Merge with enumerator
            veg_with_enum = merge_with_enumerator(veg_df, filtered_gdf)
            veg_with_enum = add_tree_name_column(veg_with_enum)

            if has_measurements:
                meas_with_enum = merge_with_enumerator(meas_df, filtered_gdf)
                meas_with_enum = add_tree_name_column(meas_with_enum)
            else:
                meas_with_enum = pd.DataFrame()

            species_col = get_species_column(veg_with_enum)

            # Helper function to format dataframe for export
            def format_for_export(
                df, issue_type, issue_description_col=None, additional_cols=None
            ):
                """
                Format dataframe according to user's specification:
                Plot id | Subplot id | Data collector name | Issue type | Issue description | Empty | Clarification
                """
                if df is None or len(df) == 0:
                    return pd.DataFrame()

                result = pd.DataFrame()

                # Plot ID (from SUBPLOT_KEY - extract plot portion)
                if "SUBPLOT_KEY" in df.columns:
                    result["Plot ID"] = df["SUBPLOT_KEY"].apply(
                        lambda x: (
                            str(x).split("-")[0]
                            if pd.notna(x) and "-" in str(x)
                            else str(x)
                        )
                    )
                elif "PLOT_KEY" in df.columns:
                    result["Plot ID"] = df["PLOT_KEY"]
                else:
                    result["Plot ID"] = ""

                # Subplot ID
                if "SUBPLOT_KEY" in df.columns:
                    result["Subplot ID"] = df["SUBPLOT_KEY"]
                elif "subplot_id" in df.columns:
                    result["Subplot ID"] = df["subplot_id"]
                else:
                    result["Subplot ID"] = ""

                # Data collector name
                if "enumerator" in df.columns:
                    result["Data Collector Name"] = df["enumerator"]
                else:
                    result["Data Collector Name"] = ""

                # Issue type
                result["Issue Type"] = issue_type

                # Issue description
                if issue_description_col and issue_description_col in df.columns:
                    result["Issue Description"] = df[issue_description_col]
                elif additional_cols:
                    # Build description from multiple columns row-wise
                    available_cols = [
                        col for col in additional_cols if col in df.columns
                    ]
                    if available_cols:
                        # Convert first column to string
                        result["Issue Description"] = df[available_cols[0]].astype(str)
                        # Concatenate remaining columns with " | " separator
                        for col in available_cols[1:]:
                            result["Issue Description"] = (
                                result["Issue Description"]
                                + " | "
                                + df[col].astype(str)
                            )
                    else:
                        result["Issue Description"] = ""
                else:
                    result["Issue Description"] = ""

                # Empty column for notes
                result["Notes"] = ""

                # Clarification
                result["Clarification"] = ""

                return result

            # Create Excel file
            output = BytesIO()
            sheets_created = 0
            # Track dataframes for column width adjustment
            sheet_dataframes = {}

            with pd.ExcelWriter(output, engine="openpyxl") as writer:

                # SHEET 1: Geometry Validation Errors (Invalid Subplots)
                try:
                    # Get invalid subplots
                    invalid_subplots = filtered_gdf[~filtered_gdf["geom_valid"]].copy()

                    if len(invalid_subplots) > 0:
                        # Prepare export dataframe
                        result = pd.DataFrame()

                        # Plot ID (extract from subplot_id)
                        if "subplot_id" in invalid_subplots.columns:
                            result["Plot ID"] = invalid_subplots["subplot_id"].apply(
                                lambda x: (
                                    str(x).split("-")[0]
                                    if pd.notna(x) and "-" in str(x)
                                    else str(x)
                                )
                            )
                            result["Subplot ID"] = invalid_subplots["subplot_id"]
                        else:
                            result["Plot ID"] = ""
                            result["Subplot ID"] = ""

                        # Data collector
                        if "enumerator" in invalid_subplots.columns:
                            result["Data Collector Name"] = invalid_subplots[
                                "enumerator"
                            ]
                        else:
                            result["Data Collector Name"] = ""

                        # Issue type
                        result["Issue Type"] = "Geometry Validation Error"

                        # Issue description - combine validation reasons with measurements
                        desc_parts = []

                        # Add reasons if available
                        if "reasons" in invalid_subplots.columns:
                            desc_parts.append(
                                invalid_subplots["reasons"].fillna("Unknown error")
                            )

                        # Add area if available
                        if "area_m2" in invalid_subplots.columns:
                            desc_parts.append(
                                "Area: "
                                + invalid_subplots["area_m2"].round(2).astype(str)
                                + " m²"
                            )

                        # Add vertex count if available
                        if "nr_vertices" in invalid_subplots.columns:
                            desc_parts.append(
                                "Vertices: "
                                + invalid_subplots["nr_vertices"].astype(str)
                            )

                        # Combine all description parts
                        if desc_parts:
                            result["Issue Description"] = desc_parts[0].astype(str)
                            for part in desc_parts[1:]:
                                result["Issue Description"] = (
                                    result["Issue Description"]
                                    + " | "
                                    + part.astype(str)
                                )
                        else:
                            result["Issue Description"] = "Geometry validation failed"

                        # Empty columns for manual review
                        result["Notes"] = ""
                        result["Clarification"] = ""

                        # Export
                        sheet_name = "Geometry Errors"
                        result.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = result
                        sheets_created += 1
                except Exception as e:
                    st.warning(f"Could not export Geometry Errors: {str(e)}")

                # SHEET 2: Height Outliers
                if has_measurements and len(meas_with_enum) > 0 and species_col:
                    try:
                        meas_outliers = detect_height_outliers(
                            meas_with_enum,
                            height_col="tree_height_m",
                            species_col=species_col,
                            upper_threshold=3.0,
                            lower_threshold=1 / 3.0,
                        )

                        height_outliers = meas_outliers[
                            (meas_outliers["Upper_outliers"] == "outlier")
                            | (meas_outliers["Lower_outliers"] == "outlier")
                        ]

                        if len(height_outliers) > 0:
                            # Ensure enumerator column exists - try multiple approaches
                            if "enumerator" not in height_outliers.columns:
                                # Try to add from filtered_gdf if available
                                if "enumerator" in filtered_gdf.columns and "subplot_id" in height_outliers.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    height_outliers = height_outliers.merge(enum_map, on="subplot_id", how="left")
                                elif "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in height_outliers.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                    height_outliers = height_outliers.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                else:
                                    height_outliers["enumerator"] = ""

                            export_df = format_for_export(
                                height_outliers,
                                issue_type="Height Outlier",
                                additional_cols=[
                                    "tree_height_m",
                                    "median_height",
                                    "tree_name",
                                    "Upper_outliers",
                                    "Lower_outliers",
                                ],
                            )
                            sheet_name = "Height Outliers"
                            export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                            sheet_dataframes[sheet_name] = export_df
                            sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Height Outliers: {str(e)}")

                # SHEET 3: Circumference Outliers
                if has_complete and species_col:
                    try:
                        complete_with_enum = merge_with_enumerator(
                            complete_df, filtered_gdf
                        )
                        complete_with_enum = add_tree_name_column(complete_with_enum)

                        if "circumference_bh" in complete_with_enum.columns:
                            circ_col = "circumference_bh"
                        elif "circumference_10cm" in complete_with_enum.columns:
                            circ_col = "circumference_10cm"
                        else:
                            circ_col = None

                        if circ_col:
                            circ_data = complete_with_enum[
                                complete_with_enum[circ_col].notna()
                            ].copy()

                            if len(circ_data) > 0:
                                circ_outliers_df = detect_circumference_outliers(
                                    circ_data,
                                    circ_col=circ_col,
                                    species_col=species_col,
                                    upper_threshold=4.0,
                                    lower_threshold=1 / 4.0,
                                )

                                circ_outliers = circ_outliers_df[
                                    (circ_outliers_df["Upper_outliers"] == "outlier")
                                    | (circ_outliers_df["Lower_outliers"] == "outlier")
                                ]

                                if len(circ_outliers) > 0:
                                    # Ensure enumerator column exists - try multiple approaches
                                    if "enumerator" not in circ_outliers.columns:
                                        # Try to add from filtered_gdf if available
                                        if "enumerator" in filtered_gdf.columns and "subplot_id" in circ_outliers.columns:
                                            enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                            circ_outliers = circ_outliers.merge(enum_map, on="subplot_id", how="left")
                                        elif "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in circ_outliers.columns:
                                            enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                            enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                            circ_outliers = circ_outliers.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                        else:
                                            circ_outliers["enumerator"] = ""

                                    export_df = format_for_export(
                                        circ_outliers,
                                        issue_type="Circumference Outlier",
                                        additional_cols=[
                                            circ_col,
                                            "median_circ",
                                            "tree_name",
                                            "Upper_outliers",
                                            "Lower_outliers",
                                        ],
                                    )
                                    sheet_name = "Circumference Outliers"
                                    export_df.to_excel(
                                        writer, sheet_name=sheet_name, index=False
                                    )
                                    sheet_dataframes[sheet_name] = export_df
                                    sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Circumference Outliers: {str(e)}")

                # SHEET 4: Missing Vegetation Records
                # try:
                #     if "VEGETATION_KEY" in veg_df.columns:
                #         veg_df_actual = veg_df[veg_df["VEGETATION_KEY"].notna()].copy()
                #     else:
                #         veg_df_actual = veg_df.copy()

                #     missing_veg = get_missing_subplots(plots_df, veg_df_actual)

                #     if len(missing_veg) > 0:
                #         export_df = format_for_export(
                #             missing_veg,
                #             issue_type="Missing Vegetation Records",
                #             issue_description_col="subplot_comments"
                #         )
                #         export_df.to_excel(writer, sheet_name='Missing Vegetation', index=False)
                #         sheets_created += 1
                # except Exception as e:
                #     st.warning(f"Could not export Missing Vegetation: {str(e)}")

                # SHEET 5: Coverage-Only Subplots
                # try:
                #     if "vegetation_type_number" in veg_df_actual.columns:
                #         veg_check = veg_df_actual.groupby("SUBPLOT_KEY")["vegetation_type_number"].agg([
                #             ("has_trees", lambda x: x.notna().any())
                #         ]).reset_index()

                #         coverage_only_keys = veg_check[~veg_check["has_trees"]]["SUBPLOT_KEY"]

                #         if len(coverage_only_keys) > 0:
                #             coverage_only = veg_df_actual[veg_df_actual["SUBPLOT_KEY"].isin(coverage_only_keys)]

                #             export_df = format_for_export(
                #                 coverage_only,
                #                 issue_type="Coverage Only Subplot",
                #                 additional_cols=["coverage_vegetation", "non_woody_species"]
                #             )
                #             export_df.to_excel(writer, sheet_name='Coverage Only', index=False)
                #             sheets_created += 1
                # except Exception as e:
                #     st.warning(f"Could not export Coverage Only: {str(e)}")

                # SHEET 6: Primary Trees with 'other'
                # try:
                #     primary_trees = get_primary_trees_with_other(
                #         veg_df, primary_value="yes_primary_group"
                #     )
                #     if len(primary_trees) > 0:
                #         primary_trees = merge_with_enumerator(
                #             primary_trees, filtered_gdf
                #         )
                #         primary_trees = add_tree_name_column(primary_trees)

                #         export_df = format_for_export(
                #             primary_trees,
                #             issue_type="Primary Tree - Other Species",
                #             additional_cols=[
                #                 "tree_name",
                #                 "other_species",
                #                 "language_other_species",
                #             ],
                #         )
                #         export_df.to_excel(
                #             writer, sheet_name="Primary Trees Other", index=False
                #         )
                #         sheets_created += 1
                # except Exception as e:
                #     st.warning(f"Could not export Primary Trees: {str(e)}")

                # # SHEET 7: Young Trees with 'other'
                # try:
                #     young_trees = get_young_trees_with_other(
                #         veg_df, young_tree_value="yes_groupbelow1.3"
                #     )
                #     if len(young_trees) > 0:
                #         young_trees = merge_with_enumerator(young_trees, filtered_gdf)
                #         young_trees = add_tree_name_column(young_trees)

                #         export_df = format_for_export(
                #             young_trees,
                #             issue_type="Young Tree - Other Species",
                #             additional_cols=[
                #                 "tree_name",
                #                 "other_species",
                #                 "language_other_species",
                #             ],
                #         )
                #         export_df.to_excel(
                #             writer, sheet_name="Young Trees Other", index=False
                #         )
                #         sheets_created += 1
                # except Exception as e:
                #     st.warning(f"Could not export Young Trees: {str(e)}")

                # # SHEET 8: Non-Primary Trees with 'other'
                # try:
                #     non_primary = get_non_primary_trees_with_other(
                #         veg_df, non_primary_value="no"
                #     )
                #     if len(non_primary) > 0:
                #         non_primary = merge_with_enumerator(non_primary, filtered_gdf)
                #         non_primary = add_tree_name_column(non_primary)

                #         export_df = format_for_export(
                #             non_primary,
                #             issue_type="Non-Primary Tree - Other Species",
                #             additional_cols=[
                #                 "tree_name",
                #                 "other_species",
                #                 "language_other_species",
                #             ],
                #         )
                #         export_df.to_excel(
                #             writer, sheet_name="Non-Primary Trees Other", index=False
                #         )
                #         sheets_created += 1
                # except Exception as e:
                #     st.warning(f"Could not export Non-Primary Trees: {str(e)}")

                # # SHEET 9: Missing Height
                # if has_measurements and len(meas_with_enum) > 0:
                #     try:
                #         missing_height = meas_with_enum[
                #             meas_with_enum["tree_height_m"].isna()
                #         ]

                #         if len(missing_height) > 0:
                #             export_df = format_for_export(
                #                 missing_height,
                #                 issue_type="Missing Height Measurement",
                #                 additional_cols=[
                #                     "VEGETATION_KEY",
                #                     "tree_name",
                #                     species_col,
                #                 ],
                #             )
                #             export_df.to_excel(
                #                 writer, sheet_name="Missing Height", index=False
                #             )
                #             sheets_created += 1
                #     except Exception as e:
                #         st.warning(f"Could not export Missing Height: {str(e)}")

                # SHEET 10: Super Tall Trees (>25m)
                if has_measurements:
                    try:
                        m_mea = raw_data["plots_subplots_vegetation_measurements"]
                        if "MEASUREMENT_KEY" in m_mea.columns:
                            m_mea_actual = m_mea[
                                m_mea["MEASUREMENT_KEY"].notna()
                            ].copy()
                        else:
                            m_mea_actual = m_mea.copy()

                        if "tree_height_m" in m_mea_actual.columns:
                            super_tall = m_mea_actual[
                                m_mea_actual["tree_height_m"] > 25
                            ].copy()

                            if len(super_tall) > 0:
                                super_tall = merge_with_enumerator(
                                    super_tall, filtered_gdf
                                )
                                super_tall = add_tree_name_column(super_tall)

                                # Ensure enumerator column exists - try multiple approaches
                                if "enumerator" not in super_tall.columns:
                                    # Try to add from filtered_gdf if available
                                    if "enumerator" in filtered_gdf.columns and "subplot_id" in super_tall.columns:
                                        enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                        super_tall = super_tall.merge(enum_map, on="subplot_id", how="left")
                                    elif "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in super_tall.columns:
                                        enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                        enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                        super_tall = super_tall.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                    else:
                                        super_tall["enumerator"] = ""

                                export_df = format_for_export(
                                    super_tall,
                                    issue_type="Super Tall Tree (>25m)",
                                    additional_cols=[
                                        "tree_height_m",
                                        "tree_name",
                                        "tree_year_planted",
                                    ],
                                )
                                sheet_name = "Super Tall Trees"
                                export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                                sheet_dataframes[sheet_name] = export_df
                                sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Super Tall Trees: {str(e)}")

                # SHEET 11: High Stem Counts (>20)
                if has_measurements and len(meas_with_enum) > 0:
                    try:
                        meas_with_stems = detect_stem_outliers(
                            meas_with_enum, threshold=20
                        )
                        high_stems = meas_with_stems[
                            meas_with_stems["high_stems_bh"] == True
                        ]

                        if len(high_stems) > 0:
                            # Ensure enumerator column exists - try multiple approaches
                            if "enumerator" not in high_stems.columns:
                                # Try to add from filtered_gdf if available
                                if "enumerator" in filtered_gdf.columns and "subplot_id" in high_stems.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    high_stems = high_stems.merge(enum_map, on="subplot_id", how="left")
                                elif "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in high_stems.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                    high_stems = high_stems.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                else:
                                    high_stems["enumerator"] = ""

                            export_df = format_for_export(
                                high_stems,
                                issue_type="High Stem Count (>20)",
                                additional_cols=[
                                    "nr_stems_bh",
                                    "tree_name",
                                    species_col,
                                ],
                            )
                            sheet_name = "High Stem Counts"
                            export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                            sheet_dataframes[sheet_name] = export_df
                            sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export High Stem Counts: {str(e)}")

                # SHEET 12: Suspicious Circumference by Age
                if has_complete:
                    try:
                        complete_with_enum = merge_with_enumerator(
                            complete_df, filtered_gdf
                        )
                        complete_with_enum = add_tree_name_column(complete_with_enum)

                        if "circumference_bh" in complete_with_enum.columns:
                            circ_col = "circumference_bh"
                        elif "circumference_10cm" in complete_with_enum.columns:
                            circ_col = "circumference_10cm"
                        else:
                            circ_col = None

                        if (
                            circ_col
                            and "tree_year_planted" in complete_with_enum.columns
                        ):
                            circ_data = complete_with_enum[
                                complete_with_enum[circ_col].notna()
                            ].copy()
                            circ_data = calculate_tree_age(circ_data)

                            if circ_data["tree_age"].notna().any():
                                circ_data = detect_suspicious_circumference_by_age(
                                    circ_data,
                                    circ_col=circ_col,
                                    young_tree_circ_threshold=50,
                                    young_tree_age_threshold=5,
                                    large_circ_threshold=300,
                                    large_circ_age_threshold=15,
                                )

                                suspicious = circ_data[circ_data["suspicious"] == True]

                                if len(suspicious) > 0:
                                    # Ensure enumerator column exists - try multiple approaches
                                    if "enumerator" not in suspicious.columns:
                                        # Try to add from filtered_gdf if available
                                        if "enumerator" in filtered_gdf.columns and "subplot_id" in suspicious.columns:
                                            enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                            suspicious = suspicious.merge(enum_map, on="subplot_id", how="left")
                                        elif "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in suspicious.columns:
                                            enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                            enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                            suspicious = suspicious.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                        else:
                                            suspicious["enumerator"] = ""

                                    export_df = format_for_export(
                                        suspicious,
                                        issue_type="Suspicious Circ vs Age",
                                        additional_cols=[
                                            circ_col,
                                            "tree_age",
                                            "tree_year_planted",
                                            "tree_name",
                                        ],
                                    )
                                    sheet_name = "Suspicious Circ by Age"
                                    export_df.to_excel(
                                        writer, sheet_name=sheet_name, index=False
                                    )
                                    sheet_dataframes[sheet_name] = export_df
                                    sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Suspicious Circ by Age: {str(e)}")

                # Summary sheet if no data
                if sheets_created == 0:
                    summary_df = pd.DataFrame(
                        {"Note": ["No quality issues found - all checks passed!"]}
                    )
                    sheet_name = "Summary"
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

            st.success(f"✅ Generated quality report with {sheets_created} sheet(s)")

            st.download_button(
                label="💾 Download Complete Quality Report",
                data=output.getvalue(),
                file_name=f"{config.PARTNER}_complete_quality_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="download_complete_quality_report",
            )

        except Exception as e:
            st.error(f"❌ Error generating report: {str(e)}")
            st.exception(e)

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
