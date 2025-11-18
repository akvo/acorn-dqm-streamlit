"""
Ground Truth DQM - Overview Dashboard
Main landing page with data loading and overview analytics
"""

import streamlit as st
import pandas as pd
import config
import requests
from io import BytesIO
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
from utils.data_processor import (
    process_json_data,
    get_validation_summary,
)

# Page config (must be first)
st.set_page_config(
    page_title="Ground Truth DQM",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Refresh partner configuration based on URL parameter
config.refresh_partner_config()

# Custom CSS
st.markdown(
    """
<style>
    .main-header {
        background: linear-gradient(90deg, #2E7D32 0%, #388E3C 100%);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        border-left: 4px solid #2E7D32;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize session state
if "data" not in st.session_state:
    st.session_state.data = None
if "filename" not in st.session_state:
    st.session_state.filename = None
if "server_name" not in st.session_state:
    st.session_state.server_name = "akvofoundation"
if "username" not in st.session_state:
    st.session_state.username = ""
if "password" not in st.session_state:
    st.session_state.password = ""

# Header
show_header()

# Sidebar - API Configuration & Filters
with st.sidebar:
    # Show active partner
    active_partner = st.session_state.get("partner", config.PARTNER)
    st.info(f"🔗 **Active Partner:** {active_partner}")

    st.markdown("## 🌐 Data Source: API")
    st.markdown("### 🔐 SurveyCTO Credentials")

    # Manual credential inputs (persisted in session state)
    server_name = st.text_input(
        "Server Name",
        value=st.session_state.server_name,
        key="server_name_input",
        help="Your SurveyCTO server name (e.g., akvofoundation)",
    )
    st.session_state.server_name = server_name

    username = st.text_input(
        "Username",
        value=st.session_state.username,
        key="username_input",
        help="Your SurveyCTO username"
    )
    st.session_state.username = username

    password = st.text_input(
        "Password",
        value=st.session_state.password,
        key="password_input",
        type="password",
        help="Your SurveyCTO password"
    )
    st.session_state.password = password

    credentials_configured = bool(server_name and username and password)

    if credentials_configured:
        st.success(f"✅ Connected to: {server_name}")
    else:
        st.warning("⚠️ Enter credentials above")

    # Form ID input
    st.markdown("---")
    st.markdown("### 📋 Form ID")

    # Show current partner's form ID
    st.info(
        f"📋 **Active Partner**: {config.PARTNER}\n\n"
        f"**Form ID**: `{config.GT_FORM_ID}`"
    )

    form_id = st.text_input(
        "Form ID (auto-filled based on partner):",
        value=config.GT_FORM_ID,
        help=f"Form ID for {config.PARTNER} - Change URL ?partner= to switch partners",
        placeholder=config.GT_FORM_ID,
    )

    if form_id:
        st.caption(f"✅ Using: `{form_id}`")
    else:
        st.warning("⚠️ Form ID required")

    st.markdown("---")

    # Settings display
    st.markdown("## ⚙️ Validation Settings")
    st.caption(f"**Min Subplot Area:** {config.MIN_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**Max Subplot Area:** {config.MAX_SUBPLOT_AREA_SIZE} m²")
    st.caption(f"**GPS Accuracy:** ≤ {config.GPS_ACCURACY_THRESHOLD}m")
    st.caption(f"**Radius Check:** {config.THRESHOLD_WITHIN_RADIUS}m")

    st.markdown("---")

    # Process button
    if credentials_configured and form_id:
        process_btn = st.button(
            "🚀 Fetch & Validate", type="primary", use_container_width=True
        )
    else:
        process_btn = False
        if not credentials_configured:
            st.warning("⚠️ Configure API credentials")
        elif not form_id:
            st.warning("⚠️ Enter form ID")

# Process data (fetch from API, then process)
if process_btn and credentials_configured:
    with st.spinner("Fetching and processing data..."):
        try:
            progress_bar = st.progress(0, text="Connecting to SurveyCTO...")

            # Fetch JSON data directly
            progress_bar.progress(25, text="📡 Downloading from API...")

            url = f"https://{server_name}.surveycto.com/api/v2/forms/data/wide/json/{form_id}"
            params = {"date": "0"}

            response = requests.get(
                url, auth=(username, password), params=params, timeout=60
            )

            # Check for specific HTTP errors
            if response.status_code == 417:
                # SurveyCTO rate limit response
                progress_bar.empty()
                try:
                    error_data = response.json()
                    wait_seconds = error_data.get("error", {}).get("message", "")

                    # Extract wait time from message
                    import re
                    match = re.search(r'(\d+)\s*seconds', wait_seconds)
                    if match:
                        wait_time = int(match.group(1))
                        wait_minutes = wait_time // 60
                        wait_remaining = wait_time % 60

                        st.error("🚫 **SurveyCTO Rate Limit**")
                        st.warning(
                            f"⏱️ **Please wait {wait_minutes} minutes and {wait_remaining} seconds before retrying.**\n\n"
                            f"Exact wait time: {wait_time} seconds"
                        )
                    else:
                        st.error("🚫 **SurveyCTO Rate Limit**")
                        st.warning(
                            f"⏱️ {wait_seconds}\n\n"
                            "Please wait before retrying."
                        )
                except:
                    st.error("🚫 **SurveyCTO Rate Limit**")
                    st.warning("⏱️ Please wait approximately 5 minutes before retrying.")

                st.info(
                    "📘 **About SurveyCTO Rate Limits**\n\n"
                    "When downloading **all data** (`date=0`), SurveyCTO enforces a **5-minute quiet period** "
                    "between requests to prevent server overload.\n\n"
                    "**Options:**\n"
                    "- ⏰ Wait the specified time and try again\n"
                    "- 📥 Use Excel export for frequent testing\n"
                    "- 📅 Use incremental downloads with a date filter (if supported)"
                )
                st.stop()

            elif response.status_code == 429:
                progress_bar.empty()
                st.error("🚫 **Rate Limit Exceeded**")
                st.warning(
                    "⏱️ SurveyCTO API has a rate limit. You can only fetch data once per minute.\n\n"
                    "**Please wait 60 seconds before trying again.**"
                )
                st.info(
                    "💡 **Tip:** The API limits are per form and per user. "
                    "If you need to fetch data more frequently, consider:\n"
                    "- Waiting a minute between requests\n"
                    "- Using Excel export for frequent testing\n"
                    "- Contacting SurveyCTO support for higher limits"
                )
                st.stop()

            elif response.status_code == 503:
                progress_bar.empty()
                st.error("🚫 **Service Temporarily Unavailable**")
                st.warning(
                    "⏱️ SurveyCTO API is temporarily unavailable (possibly due to rate limiting).\n\n"
                    "**Please wait 60-120 seconds before trying again.**"
                )
                st.stop()

            elif response.status_code == 401:
                progress_bar.empty()
                st.error("🔐 **Authentication Failed**")
                st.warning(
                    "❌ Your username or password is incorrect.\n\n"
                    "**Please check your credentials and try again.**"
                )
                st.stop()

            elif response.status_code == 403:
                progress_bar.empty()
                st.error("🚫 **Access Denied**")
                st.warning(
                    "❌ You don't have permission to access this form.\n\n"
                    "**Possible reasons:**\n"
                    "- The form ID is incorrect\n"
                    "- Your account doesn't have access to this form\n"
                    "- The form is archived or deleted"
                )
                st.stop()

            elif response.status_code == 404:
                progress_bar.empty()
                st.error("📋 **Form Not Found**")
                st.warning(
                    f"❌ Form ID `{form_id}` does not exist on server `{server_name}`.\n\n"
                    "**Please check:**\n"
                    "- The form ID is correct\n"
                    "- You selected the right partner (which auto-fills the form ID)\n"
                    "- The form exists on your SurveyCTO server"
                )
                st.stop()

            elif response.status_code == 412:
                progress_bar.empty()
                st.error("🚫 **Precondition Failed**")

                # Try to get the server's error message
                try:
                    error_response = response.json()
                    error_msg = error_response.get("error", {}).get("message", response.text)
                except:
                    error_msg = response.text

                st.warning(
                    "❌ SurveyCTO rejected the request because a precondition was not met.\n\n"
                    "**This usually happens when:**\n"
                    "- Your authentication session has expired\n"
                    "- The form has been modified since your last request\n"
                    "- Required request headers are missing or incorrect\n"
                    "- Your account permissions have changed\n\n"
                    "**Try these steps:**\n"
                    "1. Re-enter your credentials and try again\n"
                    "2. Check that you still have access to this form\n"
                    "3. If the issue persists, try using Excel export instead"
                )

                if error_msg:
                    st.error(f"**Server Error Message:**\n\n{error_msg}")

                st.info(
                    "💡 **Alternative:** Download the data as Excel from SurveyCTO and upload it here to avoid API issues."
                )
                st.stop()

            elif response.status_code >= 500:
                progress_bar.empty()
                st.error("⚠️ **Server Error**")
                st.warning(
                    f"❌ SurveyCTO server returned an error (Status: {response.status_code}).\n\n"
                    "**This is a problem with SurveyCTO's servers, not this app.**\n\n"
                    "Please try again in a few minutes."
                )
                st.stop()

            # Raise for any other HTTP errors
            response.raise_for_status()

            json_data = response.json()

            st.success(f"✅ Fetched {len(json_data)} submissions")

            # Process using new JSON processor
            progress_bar.progress(50, text="📖 Processing data...")
            data = process_json_data(json_data)

            progress_bar.progress(100, text="✅ Validation complete!")

            # Store in session state
            st.session_state.data = data
            st.session_state.filename = f"API: {form_id}"

            st.success(f"✅ Processed {len(data['subplots'])} subplots successfully!")
            progress_bar.empty()

        except requests.exceptions.Timeout:
            st.error("⏱️ **Request Timeout**")
            st.warning(
                "❌ The request took too long to complete (>60 seconds).\n\n"
                "**Possible causes:**\n"
                "- Slow internet connection\n"
                "- Large form with many submissions\n"
                "- SurveyCTO server is slow\n\n"
                "**Please try again.**"
            )
            progress_bar.empty()

        except requests.exceptions.ConnectionError:
            st.error("🌐 **Connection Error**")
            st.warning(
                "❌ Could not connect to SurveyCTO server.\n\n"
                "**Possible causes:**\n"
                "- No internet connection\n"
                "- Server name is incorrect\n"
                "- SurveyCTO is down\n\n"
                "**Please check your connection and try again.**"
            )
            progress_bar.empty()

        except ValueError as e:
            st.error("📄 **Invalid Response**")
            st.warning(
                "❌ Could not parse the API response.\n\n"
                "**This might mean:**\n"
                "- The API returned invalid JSON\n"
                "- The form has no data\n\n"
                f"**Error details:** {str(e)}"
            )
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ **Unexpected Error**")
            st.warning(
                "An unexpected error occurred while fetching data.\n\n"
                f"**Error details:** {str(e)}"
            )
            st.exception(e)
            progress_bar.empty()

# Main content - Overview Dashboard
if st.session_state.data is not None:
    # Get data
    gdf_subplots = st.session_state.data["subplots"]

    # Apply filters first (shows date filter at top)
    filtered_gdf = create_sidebar_filters(gdf_subplots)

    # Show sidebar info (partner and data status)
    show_sidebar_info()

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

else:
    # Welcome screen
    st.markdown("## 👋 Welcome to Ground Truth DQM")

    st.info(
        "👈 Enter your SurveyCTO credentials and click 'Fetch & Validate' to load data"
    )
