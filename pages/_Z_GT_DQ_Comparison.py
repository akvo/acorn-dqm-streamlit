"""
GT vs DQ Comparison Page
Compare Ground Truth data with Data Quality validation data
"""

from dotenv import load_dotenv

load_dotenv()  # Load .env file for dev mode

import streamlit as st
import pandas as pd
import re
import requests
import config
from ui.components import show_header, show_sidebar_info, require_auth
from utils.data_processor import process_json_data, process_excel_file
from utils.cache_utils import (
    is_dev_mode,
    load_from_cache,
    save_to_cache,
    cache_exists,
)
from utils.session_manager import load_data, save_data

# Import folium for maps
try:
    import folium
    from streamlit_folium import folium_static

    FOLIUM_AVAILABLE = True
except ImportError:
    FOLIUM_AVAILABLE = False

# Page config
st.set_page_config(
    page_title="GT vs DQ Comparison - Ground Truth DQM",
    page_icon="🔄",
    layout="wide",
)

# Refresh partner config from URL
config.refresh_partner_config()

# Authentication check
require_auth()

# Check if GT data exists (using persistent data store)
data = load_data("gt")
if data is None:
    st.warning("⚠️ No GT data loaded. Please fetch GT data from the home page.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
    st.stop()
st.session_state.data = data  # Ensure session state is in sync

# Header
show_header()

st.markdown("## 🔄 GT vs DQ Comparison")
st.caption(
    "Cross-validates Ground Truth (GT) survey data against Data Quality (DQ) monitoring visits. Matches plots by geographic proximity (<50m) to identify discrepancies in subplot measurements, species counts, and validation status between the two datasets."
)

# Show dev mode indicator if enabled
if is_dev_mode():
    st.info("🛠️ **Dev Mode Active** - Using local cache when available")

# ============================================
# DQ DATA FETCH SECTION
# ============================================
st.markdown("### 🔍 Load DQ Data")

# Initialize DQ data source mode in session state
if "dq_data_source_mode" not in st.session_state:
    st.session_state.dq_data_source_mode = "api"

# Data source toggle
dq_data_source = st.radio(
    "Select DQ data source:",
    options=["api", "file"],
    format_func=lambda x: "🌐 SurveyCTO API" if x == "api" else "📁 Excel File Upload",
    horizontal=True,
    help="Use API for live data, or upload an Excel export as fallback",
    key="dq_source_radio",
)
st.session_state.dq_data_source_mode = dq_data_source

# Check if DQ data already loaded (using persistent data store)
dq_data_loaded = load_data("dq")
dq_loaded = dq_data_loaded is not None
if dq_loaded:
    st.session_state.dq_data = dq_data_loaded  # Ensure session state is in sync

if dq_loaded:
    st.success(f"✅ DQ data loaded: {st.session_state.get('dq_filename', 'Unknown')}")

# Initialize variables
server_name = "akvofoundation"  # Hardcoded
credentials_configured = False
dq_uploaded_file = None
dq_process_btn = False

if st.session_state.dq_data_source_mode == "api":
    # API MODE
    st.info(f"**DQ Form ID:** `{config.DQ_FORM_ID}`")

    # Get credentials from session state
    username = st.session_state.get("username", "")
    password = st.session_state.get("password", "")
    credentials_configured = bool(username and password)

    if not credentials_configured:
        st.warning("⚠️ API credentials not configured. Please configure them on the home page first.")

    fetch_btn_label = "🔄 Refresh DQ Data" if dq_loaded else "🚀 Fetch DQ Data"

    if credentials_configured:
        dq_process_btn = st.button(fetch_btn_label, type="primary", key="dq_fetch_btn")

else:
    # FILE UPLOAD MODE
    st.info(
        "💡 **Export from SurveyCTO:**\n\n"
        "1. Go to your SurveyCTO server\n"
        "2. Export the DQ form → Download (Wide format, Excel)\n"
        "3. Upload the file below"
    )

    dq_uploaded_file = st.file_uploader(
        "Upload DQ Excel file:",
        type=["xlsx", "xls"],
        key="dq_excel_uploader",
    )

    if dq_uploaded_file:
        st.success(f"📁 File: `{dq_uploaded_file.name}`")

    upload_btn_label = "🔄 Re-process DQ File" if dq_loaded else "🔄 Process DQ File"

    if dq_uploaded_file is not None:
        dq_process_btn = st.button(upload_btn_label, type="primary", key="dq_upload_btn")
    else:
        st.warning("⚠️ Upload a DQ Excel file to continue")

# Process DQ data - API MODE
if st.session_state.dq_data_source_mode == "api" and dq_process_btn and credentials_configured:
    with st.spinner("Fetching DQ data..."):
        try:
            progress_bar = st.progress(0, text="Connecting to SurveyCTO for DQ data...")

            dq_form_id = config.DQ_FORM_ID

            # Check for cached data in dev mode
            use_cache = is_dev_mode() and cache_exists(config.PARTNER, "dq")

            if use_cache:
                # Load from cache
                progress_bar.progress(25, text="📁 Loading DQ data from local cache...")
                json_data = load_from_cache(config.PARTNER, "dq")
                st.info(f"📁 Loaded DQ data from local cache (dev mode) - {len(json_data)} records")
            else:
                # Fetch from API
                progress_bar.progress(25, text=f"Downloading DQ data ({dq_form_id})...")

                url = f"https://{server_name}.surveycto.com/api/v2/forms/data/wide/json/{dq_form_id}"

                # Use partner's start_date to avoid fetching all historical data (reduces throttling)
                from datetime import datetime

                partner_config = config.PARTNERS.get(config.PARTNER, {})
                start_date_str = partner_config.get("start_date", None)

                if start_date_str:
                    try:
                        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
                        start_timestamp = int(start_dt.timestamp() * 1000)  # milliseconds
                        params = {"date": str(start_timestamp)}
                    except ValueError:
                        params = {"date": "0"}
                else:
                    params = {"date": "0"}

                response = requests.get(url, auth=(username, password), params=params, timeout=300)

                # Handle errors
                if response.status_code == 417:
                    # SurveyCTO rate limit response
                    progress_bar.empty()
                    try:
                        error_data = response.json()
                        wait_seconds = error_data.get("error", {}).get("message", "")

                        # Extract wait time from message
                        match = re.search(r"(\d+)\s*seconds", wait_seconds)
                        if match:
                            wait_time = int(match.group(1))
                            wait_minutes = wait_time // 60
                            wait_remaining = wait_time % 60

                            st.error("🚫 **SurveyCTO Rate Limit** (DQ Form)")
                            st.warning(
                                f"⏱️ **Please wait {wait_minutes} minutes and {wait_remaining} seconds before retrying.**\n\n"
                                f"Exact wait time: {wait_time} seconds"
                            )
                        else:
                            st.error("🚫 **SurveyCTO Rate Limit** (DQ Form)")
                            st.warning(f"⏱️ {wait_seconds}\n\nPlease wait before retrying.")
                    except:
                        st.error("🚫 **SurveyCTO Rate Limit** (DQ Form)")
                        st.warning("⏱️ Please wait approximately 5 minutes before retrying.")

                    st.info(
                        "📘 **About SurveyCTO Rate Limits**\n\n"
                        "When downloading **all data** (`date=0`), SurveyCTO enforces a **5-minute quiet period** "
                        "between requests to prevent server overload.\n\n"
                        "**Options:**\n"
                        "- ⏰ Wait the specified time and try again\n"
                        "- 📥 Use Excel export for frequent testing"
                    )
                    st.stop()

                elif response.status_code == 429:
                    progress_bar.empty()
                    st.error("🚫 **Rate Limit Exceeded** (DQ Form)")
                    st.warning(
                        "⏱️ SurveyCTO API has a rate limit. You can only fetch data once per minute.\n\n"
                        "**Please wait 60 seconds before trying again.**"
                    )
                    st.stop()

                elif response.status_code in [401, 403, 404]:
                    progress_bar.empty()
                    st.error(f"❌ **DQ Form Error** (Status: {response.status_code})")
                    st.warning(f"Could not access DQ form: `{dq_form_id}`")
                    st.stop()

                elif response.status_code >= 400:
                    progress_bar.empty()
                    st.error(f"❌ **DQ Fetch Failed** (Status: {response.status_code})")
                    st.stop()

                response.raise_for_status()
                json_data = response.json()

                st.success(f"✅ Fetched {len(json_data)} DQ submissions")

                # Save to cache if dev mode is enabled
                if is_dev_mode():
                    save_to_cache(config.PARTNER, "dq", json_data)
                    st.caption("💾 Saved DQ data to local cache")

            # Process DQ data (common path for both cache and API)
            progress_bar.progress(50, text="Processing DQ data...")
            dq_data = process_json_data(json_data)

            progress_bar.progress(100, text="✅ DQ validation complete!")

            # Store in session state and persistent cache
            save_data(dq_data, "dq")
            st.session_state.dq_filename = f"API: {dq_form_id}"

            st.success(f"✅ Processed {len(dq_data['subplots'])} DQ subplots successfully!")
            progress_bar.empty()
            st.rerun()

        except Exception as e:
            st.error("❌ **DQ Fetch Error**")
            st.warning(f"Error fetching DQ data: {str(e)}")

# Process DQ data - FILE UPLOAD MODE
if st.session_state.dq_data_source_mode == "file" and dq_process_btn and dq_uploaded_file is not None:
    with st.spinner("Processing uploaded DQ file..."):
        try:
            progress_bar = st.progress(0, text="Reading DQ Excel file...")
            progress_bar.progress(25, text="Parsing DQ sheets...")

            dq_data = process_excel_file(dq_uploaded_file)

            progress_bar.progress(75, text="Validating DQ geometries...")

            if dq_data.get("subplots") is None or len(dq_data["subplots"]) == 0:
                st.error("❌ No subplot data found in DQ file")
                st.stop()

            progress_bar.progress(100, text="✅ DQ processing complete!")

            # Store in session state and persistent cache
            save_data(dq_data, "dq")
            st.session_state.dq_filename = f"File: {dq_uploaded_file.name}"

            st.success(f"✅ Processed {len(dq_data['subplots'])} DQ subplots!")
            progress_bar.empty()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error processing DQ file: {str(e)}")
            st.exception(e)

st.markdown("---")

# Only show comparison if DQ data is loaded
if not dq_loaded:
    st.info("👆 Please fetch DQ data above to see the comparison.")
    st.stop()

# Import comparison utilities
from utils.comparison_utils import (
    match_plots_by_centroid,
    match_subplots_within_plot,
    get_tree_count_by_name,
    get_tree_records_by_species,
    get_total_tree_count,
    get_vegetation_coverage,
    raw_centroid_from_gps_string,
)

# Show sidebar info
with st.sidebar:
    show_sidebar_info()
    st.markdown("---")
    st.markdown("### Data Status")
    st.success(f"✅ GT: {st.session_state.filename}")
    if st.session_state.get("dq_filename"):
        st.success(f"✅ DQ: {st.session_state.dq_filename}")


# ============================================
# HELPER FUNCTIONS
# ============================================


def filter_to_measured_subplots(gdf):
    """Filter GeoDataFrame to only include measured subplots."""
    if gdf is None or len(gdf) == 0:
        return gdf

    if "subplot_id" not in gdf.columns or "measured_subplots" not in gdf.columns:
        return gdf

    temp_df = gdf[["subplot_id", "measured_subplots"]].copy()
    temp_df["subplot_number"] = temp_df["subplot_id"].apply(
        lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
    )
    temp_df["measured_subplots_int"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
    measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots_int"]]["subplot_id"].unique()

    return gdf[gdf["subplot_id"].isin(measured_subplot_ids)].copy()


def get_plot_level_stats(gdf):
    """Calculate plot-level validation statistics."""
    if gdf is None or len(gdf) == 0 or "PLOT_KEY" not in gdf.columns:
        return {"total_plots": 0, "valid_plots": 0, "invalid_plots": 0}

    # Use overall_valid if available, otherwise geom_valid
    valid_col = "overall_valid" if "overall_valid" in gdf.columns else "geom_valid"
    if valid_col not in gdf.columns:
        return {
            "total_plots": len(gdf["PLOT_KEY"].unique()),
            "valid_plots": 0,
            "invalid_plots": 0,
        }

    plot_summary = (
        gdf.groupby("PLOT_KEY")
        .agg(
            total_subplots=(("subplot_id", "count") if "subplot_id" in gdf.columns else (valid_col, "count")),
            invalid_subplots=(valid_col, lambda x: (~x).sum()),
        )
        .reset_index()
    )

    # Plot is invalid if >= 8 subplots are invalid
    plot_summary["is_valid"] = plot_summary["invalid_subplots"] < 8

    return {
        "total_plots": len(plot_summary),
        "valid_plots": int(plot_summary["is_valid"].sum()),
        "invalid_plots": int((~plot_summary["is_valid"]).sum()),
    }


def get_subplot_stats(gdf):
    """Calculate subplot-level statistics."""
    if gdf is None or len(gdf) == 0:
        return {"total": 0, "valid": 0, "invalid": 0}

    total = len(gdf)
    valid_col = "overall_valid" if "overall_valid" in gdf.columns else "geom_valid"
    if valid_col in gdf.columns:
        valid = int(gdf[valid_col].sum())
    else:
        valid = 0

    return {"total": total, "valid": valid, "invalid": total - valid}


# ============================================
# LOAD AND PREPARE DATA
# ============================================

# Get GT data (subplots for stats, plots for geometry comparison)
gt_gdf = st.session_state.data["subplots"].copy()
gt_plots_gdf = st.session_state.data.get("plots")  # Plot-level geometry
gt_raw = st.session_state.data.get("raw_data", {})

# Get DQ data (subplots for stats, plots for geometry comparison)
dq_gdf = st.session_state.dq_data["subplots"].copy()
dq_plots_gdf = st.session_state.dq_data.get("plots")  # Plot-level geometry
dq_raw = st.session_state.dq_data.get("raw_data", {})

# ============================================
# GT DATE FILTER (to exclude training data)
# ============================================
st.markdown("### 📅 GT Data Filter")
st.caption(
    "Filter GT submissions by date range. Use this to exclude early training data or focus on specific data collection periods. Only GT plots within the selected range will be matched against DQ data."
)

# Get date range from GT plots
if gt_plots_gdf is not None and len(gt_plots_gdf) > 0 and "SubmissionDate" in gt_plots_gdf.columns:
    # Parse dates
    gt_plots_gdf["_parsed_date"] = pd.to_datetime(gt_plots_gdf["SubmissionDate"], errors="coerce")
    valid_dates = gt_plots_gdf["_parsed_date"].dropna()

    if len(valid_dates) > 0:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "Start Date (inclusive)",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
            )
        with col2:
            end_date = st.date_input(
                "End Date (inclusive)",
                value=max_date,
                min_value=min_date,
                max_value=max_date,
            )

        # Filter GT plots by date range (inclusive)
        mask = (gt_plots_gdf["_parsed_date"].dt.date >= start_date) & (gt_plots_gdf["_parsed_date"].dt.date <= end_date)
        gt_plots_gdf = gt_plots_gdf[mask].copy()

        # Get filtered plot keys
        filtered_plot_keys = set()
        if "PLOT_KEY" in gt_plots_gdf.columns:
            filtered_plot_keys = set(gt_plots_gdf["PLOT_KEY"].unique())
        elif "plot_id" in gt_plots_gdf.columns:
            filtered_plot_keys = set(gt_plots_gdf["plot_id"].unique())

        # Filter GT subplots to only include filtered plots
        if "PLOT_KEY" not in gt_gdf.columns and "subplot_id" in gt_gdf.columns:
            gt_gdf["PLOT_KEY"] = gt_gdf["subplot_id"].str.split("/").str[0]

        if "PLOT_KEY" in gt_gdf.columns and len(filtered_plot_keys) > 0:
            gt_gdf = gt_gdf[gt_gdf["PLOT_KEY"].isin(filtered_plot_keys)].copy()

        st.info(f"📊 Showing **{len(gt_plots_gdf)}** GT plots from {start_date} to {end_date}")
    else:
        st.warning("⚠️ No valid dates found in GT data")
else:
    st.warning("⚠️ SubmissionDate not available in GT plots data")

st.markdown("---")

# Ensure PLOT_KEY exists in subplots
if "PLOT_KEY" not in gt_gdf.columns and "subplot_id" in gt_gdf.columns:
    gt_gdf["PLOT_KEY"] = gt_gdf["subplot_id"].str.split("/").str[0]

if "PLOT_KEY" not in dq_gdf.columns and "subplot_id" in dq_gdf.columns:
    dq_gdf["PLOT_KEY"] = dq_gdf["subplot_id"].str.split("/").str[0]

# ============================================
# DQ VALIDATION SUMMARY (Row 1)
# ============================================

st.markdown("### 📊 DQ Data Quality Summary")
st.caption(
    "Overview of DQ (Data Quality) dataset validation status. 'Overlap with GT' shows how many DQ plots are within 50m of a GT plot, enabling direct comparison. Unmatched plots may indicate: new areas surveyed by DQ, or GT plots that haven't been revisited."
)

# Get date range from DQ plots
if dq_plots_gdf is not None and len(dq_plots_gdf) > 0 and "SubmissionDate" in dq_plots_gdf.columns:
    # Parse dates
    dq_plots_gdf["_parsed_date"] = pd.to_datetime(dq_plots_gdf["SubmissionDate"], errors="coerce")
    valid_dates_dq = dq_plots_gdf["_parsed_date"].dropna()

    if len(valid_dates_dq) > 0:
        min_date_dq = valid_dates_dq.min().date()
        max_date_dq = valid_dates_dq.max().date()

        col1_dq, col2_dq = st.columns(2)
        with col1_dq:
            start_date_dq = st.date_input(
                "DQ Start Date (inclusive)",
                value=min_date_dq,
                min_value=min_date_dq,
                max_value=max_date_dq,
                key="dq_start_date",
            )
        with col2_dq:
            end_date_dq = st.date_input(
                "DQ End Date (inclusive)",
                value=max_date_dq,
                min_value=min_date_dq,
                max_value=max_date_dq,
                key="dq_end_date",
            )

        # Filter DQ plots by date range (inclusive)
        mask_dq = (dq_plots_gdf["_parsed_date"].dt.date >= start_date_dq) & (
            dq_plots_gdf["_parsed_date"].dt.date <= end_date_dq
        )
        dq_plots_gdf = dq_plots_gdf[mask_dq].copy()

        # Get filtered plot keys
        filtered_plot_keys_dq = set()
        if "PLOT_KEY" in dq_plots_gdf.columns:
            filtered_plot_keys_dq = set(dq_plots_gdf["PLOT_KEY"].unique())
        elif "plot_id" in dq_plots_gdf.columns:
            filtered_plot_keys_dq = set(dq_plots_gdf["plot_id"].unique())

        # Filter DQ subplots to only include filtered plots
        if "PLOT_KEY" in dq_gdf.columns and len(filtered_plot_keys_dq) > 0:
            dq_gdf = dq_gdf[dq_gdf["PLOT_KEY"].isin(filtered_plot_keys_dq)].copy()

        st.info(f"📊 Showing **{len(dq_plots_gdf)}** DQ plots from {start_date_dq} to {end_date_dq}")
    else:
        st.warning("⚠️ No valid dates found in DQ data")
else:
    st.warning("⚠️ SubmissionDate not available in DQ plots data")

st.markdown("---")

# Filter to measured subplots only
gt_measured = filter_to_measured_subplots(gt_gdf)
dq_measured = filter_to_measured_subplots(dq_gdf)


# Match plots using raw GPS centroids (bypasses accuracy filtering — all vertices used regardless of accuracy)
def _build_raw_centroid_gdf(plots_gdf, gps_col="gt_plot"):
    import geopandas as gpd

    if plots_gdf is None or len(plots_gdf) == 0 or gps_col not in plots_gdf.columns:
        return plots_gdf
    gdf = plots_gdf.copy()
    gdf["geometry"] = gdf[gps_col].apply(raw_centroid_from_gps_string)
    gdf = gdf[gdf["geometry"].notna()].copy()
    return gpd.GeoDataFrame(gdf, geometry="geometry", crs=4326)


if gt_plots_gdf is not None and dq_plots_gdf is not None and len(gt_plots_gdf) > 0 and len(dq_plots_gdf) > 0:
    _gt_for_match = _build_raw_centroid_gdf(gt_plots_gdf)
    _dq_for_match = _build_raw_centroid_gdf(dq_plots_gdf)
    matches_df = match_plots_by_centroid(_gt_for_match, _dq_for_match, distance_threshold=50.0)
else:
    matches_df = match_plots_by_centroid(gt_measured, dq_measured, distance_threshold=50.0)

matched_count = len(matches_df)

# Find unmatched plots
matched_gt_keys = set(matches_df["gt_plot_key"]) if len(matches_df) > 0 else set()
matched_dq_keys = set(matches_df["dq_plot_key"]) if len(matches_df) > 0 else set()
gt_only_keys = set(gt_measured["PLOT_KEY"].unique()) - matched_gt_keys if "PLOT_KEY" in gt_measured.columns else set()
dq_only_keys = set(dq_measured["PLOT_KEY"].unique()) - matched_dq_keys if "PLOT_KEY" in dq_measured.columns else set()

dq_plot_stats = get_plot_level_stats(dq_measured)
dq_subplot_stats = get_subplot_stats(dq_measured)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("DQ Total Plots", dq_plot_stats["total_plots"])

with col2:
    st.metric("DQ Valid Plots", dq_plot_stats["valid_plots"])

with col3:
    st.metric("Overlap with GT", matched_count)

with col4:
    st.metric("DQ Total Subplots", dq_subplot_stats["total"])

with col5:
    st.metric("DQ Valid Subplots", dq_subplot_stats["valid"])

st.markdown("---")

# ============================================
# DQ ENUMERATOR PERFORMANCE TABLE
# ============================================

st.markdown("### 👥 DQ Enumerator Performance")
st.caption(
    "Aggregated performance metrics for DQ validation enumerators. "
    "Shows total monitored subplots, valid/invalid geometries, and error rates."
)

# Calculate DQ enumerator performance statistics
if "enumerator" in dq_measured.columns:
    dq_enumerators = sorted(dq_measured["enumerator"].dropna().unique().tolist())
else:
    dq_enumerators = []

if len(dq_enumerators) > 0:
    dq_enum_stats = []
    valid_col = "overall_valid" if "overall_valid" in dq_measured.columns else "geom_valid"

    for enum in dq_enumerators:
        enum_data = dq_measured[dq_measured["enumerator"] == enum]
        total_subplots = len(enum_data)

        # Calculate total unique plots for this enumerator
        if "PLOT_KEY" in enum_data.columns:
            total_plots = enum_data["PLOT_KEY"].nunique()
        elif "plot_id" in enum_data.columns:
            total_plots = enum_data["plot_id"].nunique()
        else:
            total_plots = (
                enum_data["subplot_id"].str.split("/").str[0].nunique()
                if "subplot_id" in enum_data.columns
                else total_subplots
            )

        if valid_col in enum_data.columns:
            valid = int(enum_data[valid_col].sum())
        else:
            valid = 0
        invalid = total_subplots - valid
        error_rate = (invalid / total_subplots * 100) if total_subplots > 0 else 0.0

        dq_enum_stats.append(
            {
                "Enumerator": enum,
                "Total Plots": total_plots,
                "Total Subplots": total_subplots,
                "Valid": valid,
                "Invalid": invalid,
                "Error Rate (%)": error_rate,
            }
        )

    dq_stats_df = pd.DataFrame(dq_enum_stats)

    st.dataframe(
        dq_stats_df,
        use_container_width=True,
        height=min(300, 35 * len(dq_stats_df) + 40),
        column_config={
            "Enumerator": "Enumerator",
            "Total Plots": st.column_config.NumberColumn("Total Plots", format="%d"),
            "Total Subplots": st.column_config.NumberColumn("Total Subplots", format="%d"),
            "Valid": st.column_config.NumberColumn("Valid", format="%d"),
            "Invalid": st.column_config.NumberColumn("Invalid", format="%d"),
            "Error Rate (%)": st.column_config.NumberColumn("Error Rate (%)", format="%.2f"),
        },
        hide_index=True,
    )
else:
    st.info("No enumerator data available in DQ dataset.")

st.markdown("---")


# ============================================
# DQ SUBPLOT ISSUES TABLE
# ============================================

st.markdown("### ⚠️ DQ Subplot Issues")
st.caption(
    "DQ subplots that failed geometry validation. These issues were identified during the quality monitoring visit. Review 'reasons' column to understand specific failures. Compare against GT data to see if the same subplots had issues in the original survey."
)

# Get invalid DQ subplots
dq_invalid_subplots = (
    dq_measured[~dq_measured["geom_valid"]].copy() if "geom_valid" in dq_measured.columns else pd.DataFrame()
)

if len(dq_invalid_subplots) > 0:
    st.warning(f"⚠️ {len(dq_invalid_subplots)} DQ subplots have validation issues")

    # Prepare display columns
    display_cols = ["subplot_id", "PLOT_KEY", "enumerator", "reasons"]

    # Add optional columns if they exist
    for col in [
        "area_m2",
        "nr_vertices",
        "length_width_ratio",
        "mrr_ratio",
        "in_radius",
    ]:
        if col in dq_invalid_subplots.columns:
            display_cols.append(col)

    display_cols = [col for col in display_cols if col in dq_invalid_subplots.columns]

    dq_issues_display = dq_invalid_subplots[display_cols].copy()

    # Add row numbers
    dq_issues_display.insert(0, "#", range(1, len(dq_issues_display) + 1))

    st.dataframe(
        dq_issues_display,
        use_container_width=True,
        height=300,
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "subplot_id": "Subplot ID",
            "PLOT_KEY": "Plot ID",
            "enumerator": "Enumerator",
            "reasons": "Issue Description",
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
            "nr_vertices": st.column_config.NumberColumn("Vertices", width="small"),
            "length_width_ratio": st.column_config.NumberColumn("L/W Ratio", format="%.2f"),
            "mrr_ratio": st.column_config.NumberColumn("MRR Ratio", format="%.2f"),
            "in_radius": st.column_config.CheckboxColumn("In Radius"),
        },
        hide_index=True,
    )
else:
    st.success("✅ All DQ subplots pass validation!")

st.markdown("---")


# ============================================
# DQ PLOT ISSUES TABLE
# ============================================

if "PLOT_KEY" in dq_measured.columns and "geom_valid" in dq_measured.columns:
    _valid_col = "overall_valid" if "overall_valid" in dq_measured.columns else "geom_valid"
    _agg_kwargs = {
        "total_subplots": ("subplot_id", "count") if "subplot_id" in dq_measured.columns else (_valid_col, "count"),
        "invalid_subplots": (_valid_col, lambda x: (~x).sum()),
    }
    if "enumerator" in dq_measured.columns:
        _agg_kwargs["enumerator"] = ("enumerator", "first")
    _plot_agg = dq_measured.groupby("PLOT_KEY").agg(**_agg_kwargs).reset_index()
    dq_plot_issues = _plot_agg[_plot_agg["invalid_subplots"] >= 8].copy()

    if len(dq_plot_issues) > 0:
        dq_plot_issues["error_rate"] = (
            dq_plot_issues["invalid_subplots"] / dq_plot_issues["total_subplots"].replace(0, pd.NA) * 100
        ).round(1)
        dq_plot_issues = dq_plot_issues.sort_values("invalid_subplots", ascending=False).reset_index(drop=True)

        st.markdown("### ⚠️ DQ Plot Issues")
        st.caption(
            "DQ plots with ≥8 invalid subplots. These plots have significant data quality concerns identified during the quality monitoring visit."
        )
        st.warning(f"⚠️ {len(dq_plot_issues)} DQ plot(s) have ≥8 invalid subplots")

        dq_plot_issues.insert(0, "#", range(1, len(dq_plot_issues) + 1))
        display_cols = ["#", "PLOT_KEY", "enumerator", "total_subplots", "invalid_subplots", "error_rate"]
        display_cols = [c for c in display_cols if c in dq_plot_issues.columns]

        st.dataframe(
            dq_plot_issues[display_cols],
            use_container_width=True,
            height=min(400, 35 * len(dq_plot_issues) + 40),
            column_config={
                "#": st.column_config.NumberColumn("#", width="small"),
                "PLOT_KEY": "Plot ID",
                "enumerator": "Enumerator",
                "total_subplots": st.column_config.NumberColumn("Total Subplots", format="%d"),
                "invalid_subplots": st.column_config.NumberColumn("Invalid Subplots", format="%d"),
                "error_rate": st.column_config.NumberColumn("Error Rate (%)", format="%.1f"),
            },
            hide_index=True,
        )
        st.markdown("---")


# ============================================
# MAP VIEW (GT vs DQ)
# ============================================

st.markdown("### 🗺️ Map View")
st.caption(
    "Side-by-side geographic comparison of GT (blue) and DQ (orange) plot locations. Use the dropdown to zoom to specific DQ plots. Toggle subplot layers to inspect individual subplot boundaries. Overlapping plots indicate successful matches; non-overlapping may indicate GPS drift or different survey locations."
)

if FOLIUM_AVAILABLE:
    # Use plot-level geometries for the map
    gt_with_geom = (
        gt_plots_gdf[~gt_plots_gdf.geometry.is_empty].copy()
        if gt_plots_gdf is not None and len(gt_plots_gdf) > 0
        else None
    )
    dq_with_geom = (
        dq_plots_gdf[~dq_plots_gdf.geometry.is_empty].copy()
        if dq_plots_gdf is not None and len(dq_plots_gdf) > 0
        else None
    )

    has_gt = gt_with_geom is not None and len(gt_with_geom) > 0
    has_dq = dq_with_geom is not None and len(dq_with_geom) > 0

    # DQ Plot selector dropdown
    selected_plot_key = None
    selected_geom = None
    if has_dq:
        # Build dropdown options: Plot ID + Enumerator
        dq_options = ["Show All"]
        dq_plot_map = {}
        for idx, row in dq_with_geom.iterrows():
            plot_key = row.get("PLOT_KEY", row.get("plot_id", "Unknown"))
            # Get enumerator from subplot data
            enumerator = ""
            if "PLOT_KEY" in dq_measured.columns:
                plot_subs = dq_measured[dq_measured["PLOT_KEY"] == plot_key]
                if len(plot_subs) > 0:
                    enumerator = plot_subs.iloc[0].get("enumerator", "")
            label = f"{plot_key} - {enumerator}" if enumerator else str(plot_key)
            dq_options.append(label)
            dq_plot_map[label] = (plot_key, row.geometry)

        selected = st.selectbox("🔍 Jump to DQ Plot:", dq_options, index=0)
        if selected != "Show All":
            selected_plot_key, selected_geom = dq_plot_map[selected]

    if has_gt or has_dq:
        # Calculate map center
        if selected_plot_key and selected_geom:
            # Zoom to selected plot
            centroid = selected_geom.centroid
            center_lat, center_lon = centroid.y, centroid.x
            zoom_start = 17
        else:
            # Show all plots
            all_bounds = []
            if has_gt:
                all_bounds.append(gt_with_geom.total_bounds)
            if has_dq:
                all_bounds.append(dq_with_geom.total_bounds)

            if all_bounds:
                min_x = min(b[0] for b in all_bounds)
                min_y = min(b[1] for b in all_bounds)
                max_x = max(b[2] for b in all_bounds)
                max_y = max(b[3] for b in all_bounds)
                center_lat = (min_y + max_y) / 2
                center_lon = (min_x + max_x) / 2
            else:
                center_lat, center_lon = config.MAP_CENTER
            zoom_start = 12

        # Create map with Satellite as default
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_start,
            tiles=None,
        )

        # Add tile layers - Google Hybrid as default (show=True), OpenStreetMap as option
        folium.TileLayer(
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google",
            name="Satellite",
            show=True,
        ).add_to(m)
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", show=False).add_to(m)

        # Create feature groups for plots and subplots
        gt_group = folium.FeatureGroup(name="🔵 GT Plots", show=True)
        dq_group = folium.FeatureGroup(name="🟠 DQ Plots", show=True)
        gt_subplot_group = folium.FeatureGroup(name="🟢 GT Subplots", show=False)
        dq_subplot_group = folium.FeatureGroup(name="🟢 DQ Subplots", show=False)

        # Helper to get enumerator and date from plot/subplot data
        def get_plot_info(plot_key, measured_gdf, plots_gdf):
            enumerator = "N/A"
            date = "N/A"
            # Get enumerator from subplot data
            if "PLOT_KEY" in measured_gdf.columns:
                plot_subs = measured_gdf[measured_gdf["PLOT_KEY"] == plot_key]
                if len(plot_subs) > 0:
                    enumerator = plot_subs.iloc[0].get("enumerator", "N/A")
            # Get date from plots data (SubmissionDate)
            if plots_gdf is not None and len(plots_gdf) > 0:
                plot_row = plots_gdf[
                    (plots_gdf.get("PLOT_KEY", pd.Series()) == plot_key)
                    | (plots_gdf.get("plot_id", pd.Series()) == plot_key)
                ]
                if len(plot_row) > 0:
                    date = plot_row.iloc[0].get(
                        "SubmissionDate",
                        plot_row.iloc[0].get("submission_date", "N/A"),
                    )
            return enumerator, date

        # Add GT plots (blue)
        if has_gt:
            for idx, row in gt_with_geom.iterrows():
                if row.geometry.is_empty:
                    continue

                geom = row.geometry
                plot_key = row.get("PLOT_KEY", row.get("plot_id", "N/A"))
                enumerator, date = get_plot_info(plot_key, gt_measured, gt_plots_gdf)
                tooltip = f"<b>GT Plot:</b> {plot_key}<br><b>Enumerator:</b> {enumerator}<br><b>Date:</b> {date}"

                def add_polygon_to_group(polygon, group, color, fill_color, tooltip_text):
                    coords = [[lat, lon] for lon, lat in polygon.exterior.coords]
                    folium.Polygon(
                        locations=coords,
                        color=color,
                        fill_color=fill_color,
                        weight=3,
                        fill_opacity=0.3,
                        tooltip=folium.Tooltip(tooltip_text),
                    ).add_to(group)

                if geom.geom_type == "Polygon":
                    add_polygon_to_group(geom, gt_group, "#2196F3", "#64B5F6", tooltip)
                elif geom.geom_type == "MultiPolygon":
                    for poly in geom.geoms:
                        add_polygon_to_group(poly, gt_group, "#2196F3", "#64B5F6", tooltip)

        # Add DQ plots (orange)
        if has_dq:
            for idx, row in dq_with_geom.iterrows():
                if row.geometry.is_empty:
                    continue

                geom = row.geometry
                plot_key = row.get("PLOT_KEY", row.get("plot_id", "N/A"))
                enumerator, date = get_plot_info(plot_key, dq_measured, dq_plots_gdf)
                tooltip = f"<b>DQ Plot:</b> {plot_key}<br><b>Enumerator:</b> {enumerator}<br><b>Date:</b> {date}"

                if geom.geom_type == "Polygon":
                    coords = [[lat, lon] for lon, lat in geom.exterior.coords]
                    folium.Polygon(
                        locations=coords,
                        color="#FF9800",
                        fill_color="#FFB74D",
                        weight=3,
                        fill_opacity=0.3,
                        tooltip=folium.Tooltip(tooltip),
                    ).add_to(dq_group)
                elif geom.geom_type == "MultiPolygon":
                    for poly in geom.geoms:
                        coords = [[lat, lon] for lon, lat in poly.exterior.coords]
                        folium.Polygon(
                            locations=coords,
                            color="#FF9800",
                            fill_color="#FFB74D",
                            weight=3,
                            fill_opacity=0.3,
                            tooltip=folium.Tooltip(tooltip),
                        ).add_to(dq_group)

        # Helper function to add subplot to group
        def add_subplot_to_group(subplot_row, group, is_valid):
            geom = subplot_row.geometry
            if geom is None or geom.is_empty:
                return

            subplot_id = subplot_row.get("subplot_id", "N/A")
            enumerator = subplot_row.get("enumerator", "N/A")
            reasons = subplot_row.get("reasons", "") if not is_valid else "Valid"

            # Red for invalid, green for valid
            if is_valid:
                color = "#4CAF50"  # Green
                fill_color = "#81C784"
            else:
                color = "#F44336"  # Red
                fill_color = "#E57373"

            status = "✅ Valid" if is_valid else "❌ Invalid"
            tooltip_text = f"<b>Subplot:</b> {subplot_id}<br><b>Status:</b> {status}<br><b>Enumerator:</b> {enumerator}"
            if not is_valid and reasons:
                tooltip_text += f"<br><b>Issues:</b> {reasons}"

            if geom.geom_type == "Polygon":
                coords = [[lat, lon] for lon, lat in geom.exterior.coords]
                folium.Polygon(
                    locations=coords,
                    color=color,
                    fill_color=fill_color,
                    weight=2,
                    fill_opacity=0.4,
                    tooltip=folium.Tooltip(tooltip_text),
                ).add_to(group)
            elif geom.geom_type == "MultiPolygon":
                for poly in geom.geoms:
                    coords = [[lat, lon] for lon, lat in poly.exterior.coords]
                    folium.Polygon(
                        locations=coords,
                        color=color,
                        fill_color=fill_color,
                        weight=2,
                        fill_opacity=0.4,
                        tooltip=folium.Tooltip(tooltip_text),
                    ).add_to(group)

        # Add GT subplots (green=valid, red=invalid)
        gt_subplots_with_geom = gt_measured[~gt_measured.geometry.is_empty].copy() if len(gt_measured) > 0 else None
        if gt_subplots_with_geom is not None and len(gt_subplots_with_geom) > 0:
            for idx, row in gt_subplots_with_geom.iterrows():
                is_valid = row.get("geom_valid", True)
                add_subplot_to_group(row, gt_subplot_group, is_valid)

        # Add DQ subplots (green=valid, red=invalid)
        dq_subplots_with_geom = dq_measured[~dq_measured.geometry.is_empty].copy() if len(dq_measured) > 0 else None
        if dq_subplots_with_geom is not None and len(dq_subplots_with_geom) > 0:
            for idx, row in dq_subplots_with_geom.iterrows():
                is_valid = row.get("geom_valid", True)
                add_subplot_to_group(row, dq_subplot_group, is_valid)

        # Add groups to map
        gt_group.add_to(m)
        dq_group.add_to(m)
        gt_subplot_group.add_to(m)
        dq_subplot_group.add_to(m)

        # Add layer control
        folium.LayerControl().add_to(m)

        # Display map
        folium_static(m, width=1200, height=500)

        # Legend
        st.markdown(
            """
        **Legend:**
        - 🔵 GT Plots (Blue) | 🟠 DQ Plots (Orange)
        - 🟢 Valid Subplots (Green) | 🔴 Invalid Subplots (Red)

        *Use layer control (top-right) to toggle layers. Subplot layers are hidden by default.*
        """
        )
    else:
        st.warning("No geometries available to display on map.")
else:
    st.warning("📦 Folium not installed. Install with: `pip install folium streamlit-folium`")

st.markdown("---")


# ============================================
# MATCHED PLOTS COMPARISON TABLE
# ============================================

st.markdown("### 📋 Matched Plots (Distance < 50m)")
st.caption(
    "Plots where GT and DQ centroids are within 50m (considered the same location). Compare subplot counts and tree counts between datasets. Differences may indicate: trees added/removed between visits, different measurement methodologies, or data collection errors."
)

if len(matches_df) > 0:
    # Build comparison table
    comparison_data = []

    for idx, row in matches_df.iterrows():
        gt_key = row["gt_plot_key"]
        dq_key = row["dq_plot_key"]
        distance = row["distance_m"]

        # Get subplot counts
        gt_subplots = len(gt_measured[gt_measured["PLOT_KEY"] == gt_key])
        dq_subplots = len(dq_measured[dq_measured["PLOT_KEY"] == dq_key])

        # Get tree counts
        gt_trees = get_total_tree_count(gt_key, gt_raw, gt_measured)
        dq_trees = get_total_tree_count(dq_key, dq_raw, dq_measured)

        comparison_data.append(
            {
                "#": idx + 1,
                "GT Plot ID": gt_key,
                "DQ Plot ID": dq_key,
                "Distance (m)": f"{distance:.1f}",
                "GT Subplots": gt_subplots,
                "DQ Subplots": dq_subplots,
                "Subplot Diff": dq_subplots - gt_subplots,
                "GT Trees": gt_trees,
                "DQ Trees": dq_trees,
                "Tree Diff": dq_trees - gt_trees,
            }
        )

    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    # ============================================
    # EXPANDABLE DQ PLOT DETAILS
    # ============================================

    st.markdown("### 📝 DQ Plot Details")
    st.caption(
        "Click to expand individual plot comparisons. Shows subplot-by-subplot validation status, tree species breakdown (GT vs DQ), and identifies specific discrepancies. Use this for detailed investigation of data quality issues."
    )

    for idx, row in matches_df.iterrows():
        dq_key = row["dq_plot_key"]
        gt_key = row["gt_plot_key"]
        distance = row["distance_m"]

        with st.expander(f"DQ Plot: {dq_key} (matched with GT: {gt_key}, Distance: {distance:.1f}m)"):
            # Get plot details
            dq_plot_data = dq_measured[dq_measured["PLOT_KEY"] == dq_key]
            gt_plot_data = gt_measured[gt_measured["PLOT_KEY"] == gt_key]

            if len(dq_plot_data) > 0:
                dq_first_row = dq_plot_data.iloc[0]
                has_gt_data = len(gt_plot_data) > 0
                gt_first_row = gt_plot_data.iloc[0] if has_gt_data else None

                # Plot Information - DQ
                st.markdown("**DQ Plot Information:**")
                info_col1, info_col2, info_col3 = st.columns(3)
                with info_col1:
                    st.write(f"**Plot ID:** {dq_key}")
                with info_col2:
                    enumerator = dq_first_row.get("enumerator", "N/A")
                    st.write(f"**Enumerator:** {enumerator}")
                with info_col3:
                    # Try SubmissionDate first, then date
                    dq_date = (
                        dq_first_row.get("SubmissionDate")
                        or dq_first_row.get("starttime")
                        or dq_first_row.get("date", "N/A")
                    )
                    if pd.notna(dq_date) and dq_date != "N/A":
                        try:
                            dq_date = pd.to_datetime(dq_date).strftime("%Y-%m-%d")
                        except:
                            pass
                    st.write(f"**Date:** {dq_date}")

                # Plot Information - GT
                st.markdown("**GT Plot Information:**")
                gt_col1, gt_col2, gt_col3 = st.columns(3)
                with gt_col1:
                    st.write(f"**Plot ID:** {gt_key}")
                with gt_col2:
                    gt_enumerator = gt_first_row.get("enumerator", "N/A") if has_gt_data else "N/A"
                    st.write(f"**Enumerator:** {gt_enumerator}")
                with gt_col3:
                    if has_gt_data:
                        gt_date = (
                            gt_first_row.get("SubmissionDate")
                            or gt_first_row.get("starttime")
                            or gt_first_row.get("date", "N/A")
                        )
                        if pd.notna(gt_date) and gt_date != "N/A":
                            try:
                                gt_date = pd.to_datetime(gt_date).strftime("%Y-%m-%d")
                            except:
                                pass
                    else:
                        gt_date = "N/A"
                    st.write(f"**Date:** {gt_date}")

                # Subplot Summary
                st.markdown("**Subplot Summary:**")
                total_subplots = len(dq_plot_data)
                valid_col = "overall_valid" if "overall_valid" in dq_plot_data.columns else "geom_valid"
                if valid_col in dq_plot_data.columns:
                    valid_subplots = int(dq_plot_data[valid_col].sum())
                else:
                    valid_subplots = 0
                invalid_subplots = total_subplots - valid_subplots

                sub_col1, sub_col2, sub_col3 = st.columns(3)
                with sub_col1:
                    st.write(f"**Total:** {total_subplots}")
                with sub_col2:
                    st.write(f"**Valid:** {valid_subplots}")
                with sub_col3:
                    st.write(f"**Invalid:** {invalid_subplots}")

                # Subplot Mapping (GT to DQ)
                st.markdown("**Subplot Mapping (GT ↔ DQ):**")
                st.caption("Matches subplots by centroid distance (strict: ≤20m, fallback: nearest unmatched)")

                # Get subplot data for this plot
                gt_plot_subplots = gt_measured[gt_measured["PLOT_KEY"] == gt_key]
                dq_plot_subplots = dq_measured[dq_measured["PLOT_KEY"] == dq_key]

                # Create subplot mapping
                subplot_mapping = match_subplots_within_plot(gt_plot_subplots, dq_plot_subplots)

                if len(subplot_mapping) > 0:
                    display_cols = [
                        "gt_subplot_num",
                        "dq_subplot_num",
                        "distance_m",
                        "match_type",
                    ]
                    st.dataframe(
                        subplot_mapping[display_cols].rename(
                            columns={
                                "gt_subplot_num": "GT Subplot",
                                "dq_subplot_num": "DQ Subplot",
                                "distance_m": "Distance (m)",
                                "match_type": "Match Type",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No subplot mapping available (missing geometry data)")

                # Tree Species Comparison (GT vs DQ)
                gt_tree_counts = get_tree_count_by_name(gt_key, gt_raw, gt_measured)
                dq_tree_counts = get_tree_count_by_name(dq_key, dq_raw, dq_measured)

                if gt_tree_counts or dq_tree_counts:
                    st.markdown("**Tree Species Comparison (GT vs DQ):**")
                    all_species = sorted(set(gt_tree_counts.keys()) | set(dq_tree_counts.keys()))
                    comparison_rows = [
                        {
                            "Species": sp,
                            "GT Count": gt_tree_counts.get(sp, 0),
                            "DQ Count": dq_tree_counts.get(sp, 0),
                            "Difference": dq_tree_counts.get(sp, 0) - gt_tree_counts.get(sp, 0),
                        }
                        for sp in all_species
                    ]
                    # Add total row
                    gt_total = sum(gt_tree_counts.values())
                    dq_total = sum(dq_tree_counts.values())
                    comparison_rows.append(
                        {
                            "Species": "**TOTAL**",
                            "GT Count": gt_total,
                            "DQ Count": dq_total,
                            "Difference": dq_total - gt_total,
                        }
                    )
                    st.dataframe(
                        pd.DataFrame(comparison_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Expandable details per species
                    st.markdown("**Species Details:**")

                    # Create mapping dicts for easy lookup in details tables
                    gt_to_dq_map = {}
                    dq_to_gt_map = {}
                    if len(subplot_mapping) > 0:
                        gt_to_dq_map = dict(zip(subplot_mapping["gt_subplot_num"], subplot_mapping["dq_subplot_num"]))
                        dq_to_gt_map = dict(zip(subplot_mapping["dq_subplot_num"], subplot_mapping["gt_subplot_num"]))

                    for sp in all_species:
                        sp_gt_count = gt_tree_counts.get(sp, 0)
                        sp_dq_count = dq_tree_counts.get(sp, 0)
                        sp_diff = sp_dq_count - sp_gt_count

                        with st.expander(f"{sp} | GT: {sp_gt_count} | DQ: {sp_dq_count} | Diff: {sp_diff}"):
                            # 1. Fetch both records up front
                            gt_records = get_tree_records_by_species(gt_key, sp, gt_raw)
                            dq_records = get_tree_records_by_species(dq_key, sp, dq_raw)

                            # 2. Add Mapped column for GT
                            if len(gt_records) > 0:
                                gt_records["Mapped DQ Subplot"] = gt_records["Subplot"].map(
                                    lambda x: f"{gt_to_dq_map[x]}" if x in gt_to_dq_map else "N/A"
                                )
                                # Put Mapped DQ Subplot next to Subplot
                                cols = list(gt_records.columns)
                                if "Mapped DQ Subplot" in cols:
                                    cols.remove("Mapped DQ Subplot")
                                    cols.insert(1, "Mapped DQ Subplot")
                                    gt_records = gt_records[cols]

                            # 3. Add Mapped column for DQ
                            if len(dq_records) > 0:
                                dq_records["Mapped GT Subplot"] = dq_records["Subplot"].map(
                                    lambda x: f"{dq_to_gt_map[x]}" if x in dq_to_gt_map else "N/A"
                                )
                                # Put Mapped GT Subplot next to Subplot
                                cols = list(dq_records.columns)
                                if "Mapped GT Subplot" in cols:
                                    cols.remove("Mapped GT Subplot")
                                    cols.insert(1, "Mapped GT Subplot")
                                    dq_records = dq_records[cols]

                            # 4. Define styling functions
                            def style_gt(df):
                                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                                if len(df) == 0:
                                    return styles

                                # Create lookup dictionary for DQ records by Subplot (for same species)
                                dq_lookup = {}
                                if len(dq_records) > 0:
                                    for _, r in dq_records.iterrows():
                                        try:
                                            dq_lookup[int(r["Subplot"])] = r
                                        except Exception:
                                            pass

                                for idx, row in df.iterrows():
                                    try:
                                        sub = int(row["Subplot"])
                                    except Exception:
                                        continue

                                    mapped_dq_val = row.get("Mapped DQ Subplot", "N/A")
                                    if mapped_dq_val == "N/A":
                                        styles.at[idx, "Mapped DQ Subplot"] = (
                                            "background-color: #f0f0f0; color: #888888;"
                                        )
                                    else:
                                        try:
                                            mapped_dq = int(mapped_dq_val)
                                        except Exception:
                                            mapped_dq = None

                                        if mapped_dq is not None:
                                            dq_row = dq_lookup.get(mapped_dq)
                                            if dq_row is None:
                                                # Mapped DQ subplot exists but no record for this species
                                                styles.at[idx, "Count"] = "background-color: #ffd2d2; color: #d32f2f;"
                                                styles.at[idx, "Height"] = "background-color: #ffd2d2; color: #d32f2f;"
                                            else:
                                                # Both exist, check mismatches in count/height
                                                if int(row.get("Count", 0)) != int(dq_row.get("Count", 0)):
                                                    styles.at[idx, "Count"] = (
                                                        "background-color: #ffd2d2; color: #d32f2f;"
                                                    )
                                                if (
                                                    str(row.get("Height", "N/A")).strip()
                                                    != str(dq_row.get("Height", "N/A")).strip()
                                                ):
                                                    styles.at[idx, "Height"] = (
                                                        "background-color: #ffd2d2; color: #d32f2f;"
                                                    )
                                return styles

                            def style_dq(df):
                                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                                if len(df) == 0:
                                    return styles

                                # Create lookup dictionary for GT records by Subplot (for same species)
                                gt_lookup = {}
                                if len(gt_records) > 0:
                                    for _, r in gt_records.iterrows():
                                        try:
                                            gt_lookup[int(r["Subplot"])] = r
                                        except Exception:
                                            pass

                                for idx, row in df.iterrows():
                                    try:
                                        sub = int(row["Subplot"])
                                    except Exception:
                                        continue

                                    mapped_gt_val = row.get("Mapped GT Subplot", "N/A")
                                    if mapped_gt_val == "N/A":
                                        styles.at[idx, "Mapped GT Subplot"] = (
                                            "background-color: #f0f0f0; color: #888888;"
                                        )
                                    else:
                                        try:
                                            mapped_gt = int(mapped_gt_val)
                                        except Exception:
                                            mapped_gt = None

                                        if mapped_gt is not None:
                                            gt_row = gt_lookup.get(mapped_gt)
                                            if gt_row is None:
                                                # Mapped GT subplot exists but no record for this species
                                                styles.at[idx, "Count"] = "background-color: #ffd2d2; color: #d32f2f;"
                                                styles.at[idx, "Height"] = "background-color: #ffd2d2; color: #d32f2f;"
                                            else:
                                                # Both exist, check mismatches in count/height
                                                if int(row.get("Count", 0)) != int(gt_row.get("Count", 0)):
                                                    styles.at[idx, "Count"] = (
                                                        "background-color: #ffd2d2; color: #d32f2f;"
                                                    )
                                                if (
                                                    str(row.get("Height", "N/A")).strip()
                                                    != str(gt_row.get("Height", "N/A")).strip()
                                                ):
                                                    styles.at[idx, "Height"] = (
                                                        "background-color: #ffd2d2; color: #d32f2f;"
                                                    )
                                return styles

                            # 5. Render tables
                            detail_col1, detail_col2 = st.columns(2)
                            with detail_col1:
                                st.markdown("**GT Records:**")
                                if len(gt_records) > 0:
                                    st.dataframe(
                                        gt_records.style.apply(style_gt, axis=None),
                                        use_container_width=True,
                                        hide_index=True,
                                    )
                                else:
                                    st.caption("No records")
                            with detail_col2:
                                st.markdown("**DQ Records:**")
                                if len(dq_records) > 0:
                                    st.dataframe(
                                        dq_records.style.apply(style_dq, axis=None),
                                        use_container_width=True,
                                        hide_index=True,
                                    )
                                else:
                                    st.caption("No records")
                else:
                    # Check for vegetation coverage
                    dq_coverage = get_vegetation_coverage(dq_key, dq_raw, dq_measured)
                    if dq_coverage:
                        st.markdown("**Vegetation Coverage (no trees):**")
                        for cov in dq_coverage:
                            subplot = cov.get("subplot_key", "")
                            pct = cov.get("coverage_vegetation", "N/A")
                            st.write(f"- {subplot}: {pct}%")
                    else:
                        st.info("No tree or coverage data available for this plot.")

    st.markdown("---")

else:
    st.info("No matching plots found between GT and DQ data (centroid distance < 50m)")


# ============================================
# UNMATCHED PLOTS TABLES
# ============================================

st.markdown("### 🔍 Unmatched Plots")
st.caption(
    "Plots that couldn't be matched between GT and DQ datasets (>50m apart). DQ plots not in GT may be monitoring visits to new areas. GT plots not in DQ haven't been revisited for quality verification yet."
)

# DQ plots not in GT
st.markdown("#### DQ Plots Not Found in GT")
if len(dq_only_keys) > 0:
    dq_only_data = []
    for dq_key in dq_only_keys:
        plot_data = dq_measured[dq_measured["PLOT_KEY"] == dq_key]
        if len(plot_data) > 0:
            first_row = plot_data.iloc[0]
            valid_col = "overall_valid" if "overall_valid" in plot_data.columns else "geom_valid"
            geom_valid = plot_data[valid_col].all() if valid_col in plot_data.columns else "N/A"

            dq_only_data.append(
                {
                    "Plot ID": dq_key,
                    "Enumerator": first_row.get("enumerator", "N/A"),
                    "Date": first_row.get("date", "N/A"),
                    "Subplots": len(plot_data),
                    "Trees": get_total_tree_count(dq_key, dq_raw, dq_measured),
                    "Geometry Valid": "Yes" if geom_valid else "No",
                }
            )

    st.dataframe(pd.DataFrame(dq_only_data), use_container_width=True, hide_index=True)
else:
    st.success("All DQ plots have matching GT plots!")

st.markdown("---")


# ============================================
# SUMMARY STATISTICS
# ============================================

with st.expander("📈 Summary Statistics"):
    if len(matches_df) > 0:
        avg_distance = matches_df["distance_m"].mean()

        # Calculate total differences
        total_subplot_diff = 0
        total_tree_diff = 0

        for idx, row in matches_df.iterrows():
            gt_key = row["gt_plot_key"]
            dq_key = row["dq_plot_key"]

            gt_subplots = len(gt_measured[gt_measured["PLOT_KEY"] == gt_key])
            dq_subplots = len(dq_measured[dq_measured["PLOT_KEY"] == dq_key])
            total_subplot_diff += dq_subplots - gt_subplots

            gt_trees = get_total_tree_count(gt_key, gt_raw, gt_measured)
            dq_trees = get_total_tree_count(dq_key, dq_raw, dq_measured)
            total_tree_diff += dq_trees - gt_trees

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Average Distance", f"{avg_distance:.1f}m")
        with col2:
            st.metric(
                "Total Subplot Difference",
                total_subplot_diff,
                help="Sum of (DQ - GT) across all matched plots",
            )
        with col3:
            st.metric(
                "Total Tree Difference",
                total_tree_diff,
                help="Sum of (DQ - GT) across all matched plots",
            )
    else:
        st.info("No matched plots to calculate statistics.")


# ============================================
# EXPORT DQ DATA
# ============================================

st.markdown("---")
st.markdown("### 📥 Export DQ Data")
st.caption(
    "Download the filtered DQ subplot data for use in GIS software (QGIS, ArcGIS) or spreadsheets. "
    "Data reflects the current date filter and includes only measured subplots. "
    "GeoJSON preserves geometry for mapping. CSV is for tabular analysis. 'Errors Only' exports just invalid DQ subplots."
)

_export_dq = dq_measured[~dq_measured.geometry.is_empty].copy()

col1, col2, col3 = st.columns(3)

# GeoJSON Export (Full data)
with col1:
    st.markdown("##### 🗺️ GeoJSON Export")
    st.caption("Geographic data format")

    st.download_button(
        label="🗺️ Download GeoJSON",
        data=_export_dq.to_json(default=str),
        file_name=f"{config.PARTNER}_dq_subplots.geojson",
        mime="application/geo+json",
        use_container_width=True,
    )

# CSV Export
with col2:
    st.markdown("##### 📊 CSV Export")
    st.caption("Spreadsheet format")

    try:
        from utils.export_helpers import create_csv_export

        _csv_data = create_csv_export(_export_dq, valid_only=False)
    except ImportError:
        _csv_df = _export_dq.drop(columns=["geometry"], errors="ignore")
        _csv_data = _csv_df.to_csv(index=False)

    st.download_button(
        label="📊 Download CSV",
        data=_csv_data,
        file_name=f"{config.PARTNER}_dq_subplots.csv",
        mime="text/csv",
        use_container_width=True,
    )

# Errors Only GeoJSON
with col3:
    st.markdown("##### ⚠️ Errors Only")
    st.caption("Invalid subplots GeoJSON")

    if "geom_valid" in _export_dq.columns:
        _invalid_dq = _export_dq[~_export_dq["geom_valid"]].copy()
    else:
        _invalid_dq = pd.DataFrame()

    if len(_invalid_dq) > 0:
        st.download_button(
            label="🗺️ Download Errors GeoJSON",
            data=_invalid_dq.to_json(default=str),
            file_name=f"{config.PARTNER}_dq_errors.geojson",
            mime="application/geo+json",
            use_container_width=True,
        )
    else:
        st.success("✅ No errors to export!")
