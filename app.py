"""
Ground Truth DQM - Overview Dashboard
Main landing page with data loading and overview analytics
"""

from dotenv import load_dotenv

load_dotenv()  # Load .env file for dev mode

import streamlit as st
import pandas as pd
import config
import requests
from io import BytesIO
from utils.cache_utils import is_dev_mode, load_from_cache, save_to_cache, cache_exists
from utils.session_manager import save_data, load_data, has_data, get_data_timestamp
from ui.components import (
    show_header,
    show_plot_metrics_row,
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
    process_excel_file,
    get_validation_summary,
    filter_by_date,
)
import re as regex_module
from datetime import datetime


def format_time_ago(timestamp: datetime) -> str:
    """Format a timestamp as human-readable time ago string."""
    if timestamp is None:
        return "unknown"
    delta = datetime.now() - timestamp
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "just now"
    elif minutes < 60:
        return f"{minutes} min ago"
    else:
        hours = minutes // 60
        return f"{hours}h ago"


def fetch_surveycto_data(
    server_name, username, password, form_id, progress_bar=None, progress_start=0, progress_end=100, label="", start_date=None
):
    """
    Fetch data from SurveyCTO API with comprehensive error handling.

    Args:
        server_name: SurveyCTO server name
        username: API username
        password: API password
        form_id: Form ID to fetch
        progress_bar: Optional Streamlit progress bar
        progress_start: Start percentage for progress bar
        progress_end: End percentage for progress bar
        label: Label for progress messages (e.g., "GT" or "DQ")
        start_date: Optional start date string (YYYY-MM-DD) to fetch data from

    Returns:
        tuple: (success: bool, data: dict or None, error_message: str or None)
    """
    from datetime import datetime

    try:
        if progress_bar:
            progress_bar.progress(progress_start, text=f"Fetching {label} data from API...")

        url = f"https://{server_name}.surveycto.com/api/v2/forms/data/wide/json/{form_id}"

        # Convert start_date to Unix timestamp (milliseconds) if provided
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                start_timestamp = int(start_dt.timestamp() * 1000)
                params = {"date": str(start_timestamp)}
            except ValueError:
                params = {"date": "0"}  # Fallback if date parsing fails
        else:
            params = {"date": "0"}

        response = requests.get(url, auth=(username, password), params=params, timeout=60)

        # Check for specific HTTP errors
        if response.status_code == 417:
            try:
                error_data = response.json()
                wait_seconds = error_data.get("error", {}).get("message", "")
                match = regex_module.search(r"(\d+)\s*seconds", wait_seconds)
                if match:
                    wait_time = int(match.group(1))
                    return False, None, f"Rate limit: Please wait {wait_time} seconds before retrying."
                else:
                    return False, None, f"Rate limit: {wait_seconds}"
            except:
                return False, None, "Rate limit: Please wait approximately 5 minutes before retrying."

        elif response.status_code == 429:
            return False, None, "Rate limit exceeded. Please wait 60 seconds before trying again."

        elif response.status_code == 503:
            return False, None, "Service temporarily unavailable. Please wait 60-120 seconds."

        elif response.status_code == 401:
            return False, None, "Authentication failed. Check your credentials."

        elif response.status_code == 403:
            return False, None, "Access denied. You may not have permission to access this form."

        elif response.status_code == 404:
            return False, None, f"Form '{form_id}' not found on server '{server_name}'."

        elif response.status_code == 412:
            try:
                error_response = response.json()
                error_msg = error_response.get("error", {}).get("message", response.text)
            except:
                error_msg = response.text
            return False, None, f"Precondition failed: {error_msg}"

        elif response.status_code >= 500:
            return False, None, f"Server error (Status: {response.status_code}). Try again later."

        response.raise_for_status()
        json_data = response.json()

        if progress_bar:
            mid_progress = progress_start + (progress_end - progress_start) // 2
            progress_bar.progress(mid_progress, text=f"Processing {label} data...")

        # Process the data
        data = process_json_data(json_data)

        if progress_bar:
            progress_bar.progress(progress_end, text=f"{label} data processed!")

        return True, data, None

    except requests.exceptions.Timeout:
        return False, None, "Request timeout. The request took too long."

    except requests.exceptions.ConnectionError:
        return False, None, "Connection error. Could not connect to SurveyCTO server."

    except ValueError as e:
        return False, None, f"Invalid response: {str(e)}"

    except Exception as e:
        return False, None, f"Unexpected error: {str(e)}"


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
# Hardcoded server name
st.session_state.server_name = "akvofoundation"
if "username" not in st.session_state:
    st.session_state.username = ""
if "password" not in st.session_state:
    st.session_state.password = ""
if "dq_data" not in st.session_state:
    st.session_state.dq_data = None
if "dq_filename" not in st.session_state:
    st.session_state.dq_filename = None
if "data_source_mode" not in st.session_state:
    st.session_state.data_source_mode = "api"

# Header
show_header()

# Sidebar - API Configuration & Filters
with st.sidebar:
    # Show active partner
    active_partner = st.session_state.get("partner", config.PARTNER)
    st.info(f"🔗 **Active Partner:** {active_partner}")

    st.markdown("---")

    # Initialize variables
    server_name = "akvofoundation"
    credentials_configured = False
    form_id = config.GT_FORM_ID  # Always use partner's form ID
    uploaded_file = None

    # Initialize session state for accuracy_zero_valid if not exists
    if "accuracy_zero_valid" not in st.session_state:
        st.session_state.accuracy_zero_valid = False

    # Dev mode: show data source options and file upload
    if is_dev_mode():
        st.warning("🛠️ **Dev Mode Active**")

        st.markdown("## 📊 Data Source")
        data_source = st.radio(
            "Select data source:",
            options=["api", "file"],
            format_func=lambda x: "🌐 SurveyCTO API" if x == "api" else "📁 Excel File Upload",
            horizontal=True,
            help="Use API for live data, or upload an Excel export as fallback",
        )
        st.session_state.data_source_mode = data_source

        if st.session_state.data_source_mode == "file":
            # FILE UPLOAD MODE
            st.markdown("### 📁 Upload Excel File")
            uploaded_file = st.file_uploader(
                "Upload Ground Truth Excel file:",
                type=["xlsx", "xls"],
                key="gt_excel_uploader",
            )
            if uploaded_file:
                st.success(f"📁 File: `{uploaded_file.name}`")
    else:
        # Production mode: always use API
        st.session_state.data_source_mode = "api"

    # API Credentials (shown in both modes when using API)
    if st.session_state.data_source_mode == "api":
        st.markdown("### 🔐 SurveyCTO Credentials")

        username = st.text_input(
            "Username", value=st.session_state.username, key="username_input", help="Your SurveyCTO username"
        )
        st.session_state.username = username

        password = st.text_input(
            "Password",
            value=st.session_state.password,
            key="password_input",
            type="password",
            help="Your SurveyCTO password",
        )
        st.session_state.password = password

        credentials_configured = bool(username and password)

        if credentials_configured:
            st.success(f"✅ Connected to: {server_name}")
        else:
            st.warning("⚠️ Enter credentials above")

    st.markdown("---")

    # Process button
    process_btn = False
    use_cache_btn = False
    if st.session_state.data_source_mode == "api":
        if credentials_configured and form_id:
            # Check if cached data exists for this partner
            cached_data_exists = has_data("gt", config.PARTNER)
            cache_time = get_data_timestamp(config.PARTNER)

            if cached_data_exists and cache_time:
                # Show both buttons: Use Cached and Fetch Fresh
                age_str = format_time_ago(cache_time)
                col1, col2 = st.columns(2)
                with col1:
                    use_cache_btn = st.button(f"📂 Use Cached ({age_str})", use_container_width=True)
                with col2:
                    process_btn = st.button("🚀 Fetch Fresh", type="primary", use_container_width=True)
            else:
                # No cache - show single fetch button
                process_btn = st.button("🚀 Fetch GT Data", type="primary", use_container_width=True)
        else:
            if not credentials_configured:
                st.warning("⚠️ Configure API credentials")
    else:
        # File upload mode (dev only)
        if uploaded_file is not None:
            process_btn = st.button("🔄 Process Uploaded File", type="primary", use_container_width=True)
        else:
            process_btn = False
            st.warning("⚠️ Upload an Excel file to continue")

# Handle "Use Cached" button - load data from shared cache
if use_cache_btn:
    data = load_data("gt", config.PARTNER)
    if data:
        st.session_state.data = data
        st.success("📂 Loaded data from cache")
        st.rerun()
    else:
        st.error("Cache data no longer available. Please fetch fresh data.")

# Process data (fetch from API or cache, then process) - API MODE
if st.session_state.data_source_mode == "api" and process_btn and credentials_configured:
    with st.spinner("Fetching and processing data..."):
        try:
            progress_bar = st.progress(0, text="Connecting to SurveyCTO...")

            # Check for cached data in dev mode
            use_cache = is_dev_mode() and cache_exists(config.PARTNER, "gt")

            if use_cache:
                # Load from cache
                progress_bar.progress(25, text="📁 Loading from local cache...")
                json_data = load_from_cache(config.PARTNER, "gt")
                st.info(f"📁 Loaded GT data from local cache (dev mode) - {len(json_data)} records")
            else:
                # Fetch JSON data directly from API
                progress_bar.progress(25, text="📡 Downloading from API...")

                url = f"https://{server_name}.surveycto.com/api/v2/forms/data/wide/json/{form_id}"

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

                response = requests.get(url, auth=(username, password), params=params, timeout=60)

                # Check for specific HTTP errors
                if response.status_code == 417:
                    # SurveyCTO rate limit response
                    progress_bar.empty()
                    try:
                        error_data = response.json()
                        wait_seconds = error_data.get("error", {}).get("message", "")

                        # Extract wait time from message
                        import re

                        match = re.search(r"(\d+)\s*seconds", wait_seconds)
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
                            st.warning(f"⏱️ {wait_seconds}\n\nPlease wait before retrying.")
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
                        "❌ Your username or password is incorrect.\n\n**Please check your credentials and try again.**"
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

                # Save to cache if dev mode is enabled
                if is_dev_mode():
                    save_to_cache(config.PARTNER, "gt", json_data)
                    st.caption("💾 Saved GT data to local cache")

            # Process using new JSON processor (common path for both cache and API)
            progress_bar.progress(50, text="📖 Processing data...")
            data = process_json_data(json_data)

            progress_bar.progress(100, text="✅ Validation complete!")

            # Store in session state and persistent cache
            save_data(data, "gt")
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
            st.error("❌ **Unexpected Error**")
            st.warning(f"An unexpected error occurred while fetching data.\n\n**Error details:** {str(e)}")
            st.exception(e)
            progress_bar.empty()

# Process uploaded file (FILE UPLOAD MODE)
if st.session_state.data_source_mode == "file" and process_btn and uploaded_file is not None:
    with st.spinner("Processing uploaded file..."):
        try:
            progress_bar = st.progress(0, text="Reading Excel file...")
            progress_bar.progress(25, text="Parsing sheets...")

            data = process_excel_file(uploaded_file)

            progress_bar.progress(75, text="Validating geometries...")

            if data.get("subplots") is None or len(data["subplots"]) == 0:
                st.error("❌ No subplot data found in file")
                st.stop()

            progress_bar.progress(100, text="✅ Complete!")

            # Store in session state and persistent cache
            save_data(data, "gt")
            st.session_state.filename = f"File: {uploaded_file.name}"

            st.success(f"✅ Processed {len(data['subplots'])} subplots!")
            progress_bar.empty()

        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            st.exception(e)

# Main content - Overview Dashboard
if st.session_state.data is not None:
    # Get data
    gdf_subplots = st.session_state.data["subplots"]

    # Apply filters first (shows date filter at top)
    filtered_gdf = create_sidebar_filters(gdf_subplots)

    # Show sidebar info (partner and data status)
    show_sidebar_info()

    # Calculate plot-level metrics using same logic as Plot Issues page
    # Need to add vegetation validation first
    raw_data = st.session_state.data.get("raw_data", {})

    # Add vegetation validation if not already present
    if "overall_valid" not in filtered_gdf.columns:
        # Add SUBPLOT_KEY if needed
        if "SUBPLOT_KEY" not in filtered_gdf.columns:
            filtered_gdf["SUBPLOT_KEY"] = filtered_gdf["subplot_id"]

        # Simple vegetation validation for overview
        if "plots_subplots_vegetation" in raw_data:
            veg_df = raw_data["plots_subplots_vegetation"]
            veg_valid_list = []
            for idx, row in filtered_gdf.iterrows():
                subplot_key = row["SUBPLOT_KEY"]
                subplot_veg = veg_df[veg_df["SUBPLOT_KEY"] == subplot_key]

                # Check for 'other' species
                other_count = 0
                if "other_species" in subplot_veg.columns:
                    other_count = subplot_veg["other_species"].notna().sum()
                elif "vegetation_species_type" in subplot_veg.columns:
                    other_count = (subplot_veg["vegetation_species_type"].astype(str).str.lower() == "other").sum()

                veg_valid_list.append(other_count < 10)

            filtered_gdf["veg_valid"] = veg_valid_list
        else:
            filtered_gdf["veg_valid"] = True

        # Create overall_valid column
        filtered_gdf["overall_valid"] = filtered_gdf["geom_valid"] & filtered_gdf["veg_valid"]

    # Now calculate plot validation using overall_valid
    import re

    if "PLOT_KEY" not in filtered_gdf.columns and "subplot_id" in filtered_gdf.columns:
        filtered_gdf["PLOT_KEY"] = filtered_gdf["subplot_id"].str.split("/").str[0]

    if "PLOT_KEY" in filtered_gdf.columns:
        # Filter to only measured subplots (same as Plot Issues page)
        if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
            temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()
            temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
            )
            temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
            measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]][
                "subplot_id"
            ].unique()
            gdf_for_plots = filtered_gdf[filtered_gdf["subplot_id"].isin(measured_subplot_ids)].copy()
        else:
            gdf_for_plots = filtered_gdf.copy()

        plot_summary = (
            gdf_for_plots.groupby("PLOT_KEY").agg({"subplot_id": "count", "overall_valid": "sum"}).reset_index()
        )
        plot_summary.columns = ["PLOT_KEY", "total_subplots", "valid_subplots"]
        plot_summary["invalid_subplots"] = plot_summary["total_subplots"] - plot_summary["valid_subplots"]
        # Plot is invalid if ≥8 subplots are invalid
        plot_summary["plot_valid"] = plot_summary["invalid_subplots"] < 8
    else:
        # Fallback: Still try to filter by measured subplots even without PLOT_KEY
        plot_summary = pd.DataFrame()
        if "subplot_id" in filtered_gdf.columns and "measured_subplots" in filtered_gdf.columns:
            temp_df = filtered_gdf[["subplot_id", "measured_subplots"]].copy()
            temp_df["subplot_number"] = temp_df["subplot_id"].apply(
                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1)) if re.search(r"\[(\d+)\]", str(x)) else 999
            )
            temp_df["measured_subplots"] = temp_df["measured_subplots"].apply(lambda x: int(x) if pd.notna(x) else 999)
            measured_subplot_ids = temp_df[temp_df["subplot_number"] <= temp_df["measured_subplots"]][
                "subplot_id"
            ].unique()
            gdf_for_plots = filtered_gdf[filtered_gdf["subplot_id"].isin(measured_subplot_ids)].copy()
        else:
            gdf_for_plots = filtered_gdf.copy()

    # Calculate summary from MEASURED subplots only (not all 16 subplots per plot)
    summary = get_validation_summary(gdf_for_plots)

    # Main content
    st.markdown("## 📊 Overview Dashboard")
    st.caption("High-level summary of data quality. Green metrics indicate healthy data. Yellow/red metrics require attention. Click through to detailed pages for investigation and remediation guidance.")

    # Plot-level metrics (Row 1)
    show_plot_metrics_row(plot_summary)

    # Subplot-level metrics (Row 2)
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
                    # COMMENTED OUT: Only used by species-based and DBSCAN outlier detection
                    # load_species_lookup,
                    # normalize_species_name,
                    # detect_species_outliers,
                    # detect_multivariate_outliers_dbscan,
                )
                from utils.vegetation_validation import (
                    get_missing_subplots,
                    detect_stem_outliers,
                    detect_suspicious_circumference_by_age,
                    check_unidentified_species,
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
                plots_df_all = raw_data.get("plots_subplots", pd.DataFrame())
                veg_df_all = raw_data["plots_subplots_vegetation"].copy()
                meas_df_all = (
                    raw_data.get("plots_subplots_vegetation_measurements", pd.DataFrame())
                    if has_measurements
                    else pd.DataFrame()
                )
                complete_df_all = raw_data.get("complete", pd.DataFrame()) if has_complete else pd.DataFrame()

                # IMPORTANT: Filter data based on filtered_gdf (which has date/enumerator filters applied)
                # This ensures the export respects the sidebar filters
                filtered_subplot_ids = (
                    filtered_gdf["subplot_id"].unique() if "subplot_id" in filtered_gdf.columns else []
                )

                if len(filtered_subplot_ids) > 0:
                    # Filter all dataframes to only include subplots from filtered_gdf
                    plots_df = (
                        plots_df_all[plots_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
                        if "SUBPLOT_KEY" in plots_df_all.columns
                        else plots_df_all.copy()
                    )
                    veg_df = (
                        veg_df_all[veg_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
                        if "SUBPLOT_KEY" in veg_df_all.columns
                        else veg_df_all.copy()
                    )
                    meas_df = (
                        meas_df_all[meas_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
                        if has_measurements and "SUBPLOT_KEY" in meas_df_all.columns
                        else meas_df_all.copy()
                    )
                    complete_df = (
                        complete_df_all[complete_df_all["SUBPLOT_KEY"].isin(filtered_subplot_ids)].copy()
                        if has_complete and "SUBPLOT_KEY" in complete_df_all.columns
                        else complete_df_all.copy()
                    )
                else:
                    plots_df = plots_df_all.copy()
                    veg_df = veg_df_all.copy()
                    meas_df = meas_df_all.copy()
                    complete_df = complete_df_all.copy()

                # DEBUG: Check what columns are in filtered_gdf
                import sys

                print(f"DEBUG EXPORT: filtered_gdf columns: {filtered_gdf.columns.tolist()}", file=sys.stderr)
                print(f"DEBUG EXPORT: Has SubmissionDate: {'SubmissionDate' in filtered_gdf.columns}", file=sys.stderr)
                print(f"DEBUG EXPORT: Has starttime: {'starttime' in filtered_gdf.columns}", file=sys.stderr)

                # Merge with enumerator
                veg_with_enum = merge_with_enumerator(veg_df, filtered_gdf)
                veg_with_enum = add_tree_name_column(veg_with_enum)

                print(
                    f"DEBUG EXPORT: veg_with_enum columns after merge: {veg_with_enum.columns.tolist()}",
                    file=sys.stderr,
                )
                print(
                    f"DEBUG EXPORT: veg_with_enum has SubmissionDate: {'SubmissionDate' in veg_with_enum.columns}",
                    file=sys.stderr,
                )
                print(
                    f"DEBUG EXPORT: veg_with_enum has starttime: {'starttime' in veg_with_enum.columns}",
                    file=sys.stderr,
                )

                if has_measurements:
                    meas_with_enum = merge_with_enumerator(meas_df, filtered_gdf)
                    meas_with_enum = add_tree_name_column(meas_with_enum)
                else:
                    meas_with_enum = pd.DataFrame()

                species_col = get_species_column(veg_with_enum)

                # Helper function to format dataframe for export
                def format_for_export(df, issue_type, issue_description_col=None, additional_cols=None, key_col=None):
                    """
                    Format dataframe according to user's specification:
                    Plot id | Subplot id | KEY | Data collector name | Issue type | Issue description | Empty | Clarification

                    key_col: The column to use for the KEY field (e.g., SUBPLOT_KEY, VEGETATION_KEY, MEASUREMENT_KEY, CIRCUMFERENCE_KEY)
                    """
                    if df is None or len(df) == 0:
                        return pd.DataFrame()

                    result = pd.DataFrame()

                    # Submitted Date (FIRST COLUMN)
                    if "SubmissionDate" in df.columns:
                        result["Submitted Date"] = df["SubmissionDate"]
                    elif "starttime" in df.columns:
                        result["Submitted Date"] = df["starttime"]
                    else:
                        result["Submitted Date"] = ""

                    # Plot ID (from SUBPLOT_KEY - extract plot portion)
                    if "SUBPLOT_KEY" in df.columns:
                        result["Plot ID"] = df["SUBPLOT_KEY"].apply(
                            lambda x: (str(x).split("-")[0] if pd.notna(x) and "-" in str(x) else str(x))
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

                    # KEY column (most granular key for SurveyCTO reference)
                    if key_col and key_col in df.columns:
                        result["KEY"] = df[key_col]
                    else:
                        result["KEY"] = ""

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
                        available_cols = [col for col in additional_cols if col in df.columns]
                        if available_cols:
                            # Convert first column to string
                            result["Issue Description"] = df[available_cols[0]].astype(str)
                            # Concatenate remaining columns with " | " separator
                            for col in available_cols[1:]:
                                result["Issue Description"] = result["Issue Description"] + " | " + df[col].astype(str)
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

                            # Submitted Date (FIRST COLUMN)
                            if "SubmissionDate" in invalid_subplots.columns:
                                result["Submitted Date"] = invalid_subplots["SubmissionDate"]
                            elif "starttime" in invalid_subplots.columns:
                                result["Submitted Date"] = invalid_subplots["starttime"]
                            else:
                                result["Submitted Date"] = ""

                            # Plot ID (extract from subplot_id)
                            if "subplot_id" in invalid_subplots.columns:
                                result["Plot ID"] = invalid_subplots["subplot_id"].apply(
                                    lambda x: (str(x).split("-")[0] if pd.notna(x) and "-" in str(x) else str(x))
                                )
                                result["Subplot ID"] = invalid_subplots["subplot_id"]
                            else:
                                result["Plot ID"] = ""
                                result["Subplot ID"] = ""

                            # KEY column (subplot_id for geometry errors)
                            if "subplot_id" in invalid_subplots.columns:
                                result["KEY"] = invalid_subplots["subplot_id"]
                            else:
                                result["KEY"] = ""

                            # Data collector
                            if "enumerator" in invalid_subplots.columns:
                                result["Data Collector Name"] = invalid_subplots["enumerator"]
                            else:
                                result["Data Collector Name"] = ""

                            # Issue type
                            result["Issue Type"] = "Geometry Validation Error"

                            # Issue description - combine validation reasons with measurements
                            desc_parts = []

                            # Add reasons if available
                            if "reasons" in invalid_subplots.columns:
                                desc_parts.append(invalid_subplots["reasons"].fillna("Unknown error"))

                            # Add area if available
                            if "area_m2" in invalid_subplots.columns:
                                desc_parts.append("Area: " + invalid_subplots["area_m2"].round(2).astype(str) + " m²")

                            # Add vertex count if available
                            if "nr_vertices" in invalid_subplots.columns:
                                desc_parts.append("Vertices: " + invalid_subplots["nr_vertices"].astype(str))

                            # Combine all description parts
                            if desc_parts:
                                result["Issue Description"] = desc_parts[0].astype(str)
                                for part in desc_parts[1:]:
                                    result["Issue Description"] = result["Issue Description"] + " | " + part.astype(str)
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

                    # SHEET 2: Height Outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                    if has_measurements and len(meas_with_enum) > 0:
                        try:
                            # Use VEGETATION_KEY grouping instead of species-based
                            if "tree_height_m" in meas_with_enum.columns and "VEGETATION_KEY" in meas_with_enum.columns:
                                height_check = meas_with_enum[
                                    meas_with_enum["tree_height_m"].notna() & meas_with_enum["VEGETATION_KEY"].notna()
                                ].copy()

                                if len(height_check) > 0:
                                    # Calculate median height per VEGETATION_KEY (tree group)
                                    median_check = (
                                        height_check.groupby("VEGETATION_KEY")["tree_height_m"]
                                        .median()
                                        .reset_index(name="median_height")
                                    )

                                    # Merge and apply 4x/0.25x thresholds
                                    height_total = pd.merge(
                                        height_check, median_check, how="inner", on="VEGETATION_KEY"
                                    )
                                    height_total["Upper_outliers"] = height_total.apply(
                                        lambda row: "outlier"
                                        if row["tree_height_m"] > (row["median_height"] * 4)
                                        else "ok",
                                        axis=1,
                                    )
                                    height_total["Lower_outliers"] = height_total.apply(
                                        lambda row: "outlier"
                                        if row["tree_height_m"] < (row["median_height"] / 4)
                                        else "ok",
                                        axis=1,
                                    )

                                    height_outliers = height_total[
                                        (height_total["Upper_outliers"] == "outlier")
                                        | (height_total["Lower_outliers"] == "outlier")
                                    ]
                                else:
                                    height_outliers = pd.DataFrame()
                            else:
                                height_outliers = pd.DataFrame()

                            if len(height_outliers) > 0:
                                # Ensure enumerator column exists - try multiple approaches
                                if "enumerator" not in height_outliers.columns:
                                    # Try to add from filtered_gdf if available
                                    if "enumerator" in filtered_gdf.columns and "subplot_id" in height_outliers.columns:
                                        enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                        height_outliers = height_outliers.merge(enum_map, on="subplot_id", how="left")
                                    elif (
                                        "enumerator" in filtered_gdf.columns
                                        and "SUBPLOT_KEY" in height_outliers.columns
                                    ):
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
                                    key_col="MEASUREMENT_KEY",
                                )
                                sheet_name = "Height Outliers"
                                export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                                sheet_dataframes[sheet_name] = export_df
                                sheets_created += 1
                        except Exception as e:
                            st.warning(f"Could not export Height Outliers: {str(e)}")

                    # SHEET 3: Circumference Outliers (using VEGETATION_KEY grouping - Rabobank methodology)
                    if has_measurements and len(meas_with_enum) > 0:
                        try:
                            # Find circumference column
                            if "circumference_bh" in meas_with_enum.columns:
                                circ_col = "circumference_bh"
                            elif "circumference_10cm" in meas_with_enum.columns:
                                circ_col = "circumference_10cm"
                            else:
                                circ_col = None

                            # Use VEGETATION_KEY grouping instead of species-based
                            if circ_col and "VEGETATION_KEY" in meas_with_enum.columns:
                                circ_check = meas_with_enum[
                                    meas_with_enum[circ_col].notna() & meas_with_enum["VEGETATION_KEY"].notna()
                                ].copy()

                                if len(circ_check) > 0:
                                    # Calculate median circumference per VEGETATION_KEY (tree group)
                                    median_check = (
                                        circ_check.groupby("VEGETATION_KEY")[circ_col]
                                        .median()
                                        .reset_index(name="median_circ")
                                    )

                                    # Merge and apply 4x/0.25x thresholds
                                    circ_total = pd.merge(circ_check, median_check, how="inner", on="VEGETATION_KEY")
                                    circ_total["Upper_outliers"] = circ_total.apply(
                                        lambda row: "outlier" if row[circ_col] > (row["median_circ"] * 4) else "ok",
                                        axis=1,
                                    )
                                    circ_total["Lower_outliers"] = circ_total.apply(
                                        lambda row: "outlier" if row[circ_col] < (row["median_circ"] / 4) else "ok",
                                        axis=1,
                                    )

                                    circ_outliers = circ_total[
                                        (circ_total["Upper_outliers"] == "outlier")
                                        | (circ_total["Lower_outliers"] == "outlier")
                                    ]
                                else:
                                    circ_outliers = pd.DataFrame()
                            else:
                                circ_outliers = pd.DataFrame()

                            if len(circ_outliers) > 0:
                                # Ensure enumerator column exists - try multiple approaches
                                if "enumerator" not in circ_outliers.columns:
                                    # Try to add from filtered_gdf if available
                                    if "enumerator" in filtered_gdf.columns and "subplot_id" in circ_outliers.columns:
                                        enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                        circ_outliers = circ_outliers.merge(enum_map, on="subplot_id", how="left")
                                    elif (
                                        "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in circ_outliers.columns
                                    ):
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
                                    key_col="CIRCUMFERENCE_KEY",
                                )
                                sheet_name = "Circumference Outliers"
                                export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                                sheet_dataframes[sheet_name] = export_df
                                sheets_created += 1
                        except Exception as e:
                            st.warning(f"Could not export Circumference Outliers: {str(e)}")

                    # COMMENTED OUT: Height Outliers (by Species) - IQR-based detection
                    # if has_complete and len(complete_df) > 0:
                    #     try:
                    #         # Load species lookup for normalization
                    #         scientific_lookup, common_lookup = load_species_lookup(config.PARTNER)
                    #
                    #         # Filter to woody trees only
                    #         if "vegetation_type_woody" in complete_df.columns:
                    #             woody_export = complete_df[complete_df["vegetation_type_woody"] == "woody"].copy()
                    #         else:
                    #             woody_export = complete_df.copy()
                    #
                    #         # Normalize species names
                    #         woody_export["normalized_species"] = woody_export.apply(
                    #             lambda row: normalize_species_name(row, scientific_lookup, common_lookup), axis=1
                    #         )
                    #
                    #         # Height outliers by species
                    #         if "tree_height_m" in woody_export.columns:
                    #             height_by_species = detect_species_outliers(woody_export, "tree_height_m")
                    #             if len(height_by_species) > 0:
                    #                 height_outliers_species = height_by_species[height_by_species["is_outlier"] == True]
                    #
                    #                 if len(height_outliers_species) > 0:
                    #                     # Add outlier type
                    #                     height_outliers_species = height_outliers_species.copy()
                    #                     height_outliers_species["outlier_type"] = height_outliers_species.apply(
                    #                         lambda row: "Too High" if row.get("is_upper_outlier") else "Too Low",
                    #                         axis=1,
                    #                     )
                    #
                    #                     export_df = format_for_export(
                    #                         height_outliers_species,
                    #                         issue_type="Height Outlier (by Species)",
                    #                         additional_cols=[
                    #                             "tree_height_m",
                    #                             "species_median",
                    #                             "normalized_species",
                    #                             "outlier_type",
                    #                         ],
                    #                         key_col="MEASUREMENT_KEY",
                    #                     )
                    #                     sheet_name = "Height Outliers (Species)"
                    #                     export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    #                     sheet_dataframes[sheet_name] = export_df
                    #                     sheets_created += 1
                    #     except Exception as e:
                    #         st.warning(f"Could not export Height Outliers (Species): {str(e)}")

                    # COMMENTED OUT: Circumference Outliers (by Species) - IQR-based detection
                    # if has_complete and len(complete_df) > 0:
                    #     try:
                    #         # Load species lookup if not already loaded
                    #         if "scientific_lookup" not in locals():
                    #             scientific_lookup, common_lookup = load_species_lookup(config.PARTNER)
                    #
                    #         # Filter to woody trees only
                    #         if "vegetation_type_woody" in complete_df.columns:
                    #             woody_export = complete_df[complete_df["vegetation_type_woody"] == "woody"].copy()
                    #         else:
                    #             woody_export = complete_df.copy()
                    #
                    #         # Normalize species names if not already done
                    #         if "normalized_species" not in woody_export.columns:
                    #             woody_export["normalized_species"] = woody_export.apply(
                    #                 lambda row: normalize_species_name(row, scientific_lookup, common_lookup), axis=1
                    #             )
                    #
                    #         # Circumference outliers by species
                    #         if "circumference_bh" in woody_export.columns:
                    #             circ_by_species = detect_species_outliers(woody_export, "circumference_bh")
                    #             if len(circ_by_species) > 0:
                    #                 circ_outliers_species = circ_by_species[circ_by_species["is_outlier"] == True]
                    #
                    #                 if len(circ_outliers_species) > 0:
                    #                     # Add outlier type
                    #                     circ_outliers_species = circ_outliers_species.copy()
                    #                     circ_outliers_species["outlier_type"] = circ_outliers_species.apply(
                    #                         lambda row: "Too High" if row.get("is_upper_outlier") else "Too Low",
                    #                         axis=1,
                    #                     )
                    #
                    #                     export_df = format_for_export(
                    #                         circ_outliers_species,
                    #                         issue_type="Circumference Outlier (by Species)",
                    #                         additional_cols=[
                    #                             "circumference_bh",
                    #                             "species_median",
                    #                             "normalized_species",
                    #                             "outlier_type",
                    #                         ],
                    #                         key_col="CIRCUMFERENCE_KEY",
                    #                     )
                    #                     sheet_name = "Circ Outliers (Species)"
                    #                     export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    #                     sheet_dataframes[sheet_name] = export_df
                    #                     sheets_created += 1
                    #     except Exception as e:
                    #         st.warning(f"Could not export Circumference Outliers (Species): {str(e)}")

                    # COMMENTED OUT: Stem Count Outliers (by Species) - IQR-based detection
                    # if has_complete and len(complete_df) > 0:
                    #     try:
                    #         # Load species lookup if not already loaded
                    #         if "scientific_lookup" not in locals():
                    #             scientific_lookup, common_lookup = load_species_lookup(config.PARTNER)
                    #
                    #         # Filter to woody trees only
                    #         if "vegetation_type_woody" in complete_df.columns:
                    #             woody_export = complete_df[complete_df["vegetation_type_woody"] == "woody"].copy()
                    #         else:
                    #             woody_export = complete_df.copy()
                    #
                    #         # Normalize species names if not already done
                    #         if "normalized_species" not in woody_export.columns:
                    #             woody_export["normalized_species"] = woody_export.apply(
                    #                 lambda row: normalize_species_name(row, scientific_lookup, common_lookup), axis=1
                    #             )
                    #
                    #         # Stem count outliers by species
                    #         if "nr_stems_bh" in woody_export.columns:
                    #             stems_by_species = detect_species_outliers(woody_export, "nr_stems_bh")
                    #             if len(stems_by_species) > 0:
                    #                 stems_outliers_species = stems_by_species[stems_by_species["is_outlier"] == True]
                    #
                    #                 if len(stems_outliers_species) > 0:
                    #                     # Add outlier type
                    #                     stems_outliers_species = stems_outliers_species.copy()
                    #                     stems_outliers_species["outlier_type"] = stems_outliers_species.apply(
                    #                         lambda row: "Too High" if row.get("is_upper_outlier") else "Too Low",
                    #                         axis=1,
                    #                     )
                    #
                    #                     export_df = format_for_export(
                    #                         stems_outliers_species,
                    #                         issue_type="Stem Count Outlier (by Species)",
                    #                         additional_cols=[
                    #                             "nr_stems_bh",
                    #                             "species_median",
                    #                             "normalized_species",
                    #                             "outlier_type",
                    #                         ],
                    #                         key_col="MEASUREMENT_KEY",
                    #                     )
                    #                     sheet_name = "Stem Outliers (Species)"
                    #                     export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    #                     sheet_dataframes[sheet_name] = export_df
                    #                     sheets_created += 1
                    #     except Exception as e:
                    #         st.warning(f"Could not export Stem Count Outliers (Species): {str(e)}")

                    # COMMENTED OUT: DBSCAN Outliers (one sheet per attribute: Height, Circ, Stems)
                    # if has_complete and len(complete_df) > 0:
                    #     # Prepare woody data with age and species
                    #     woody_export = complete_df.copy()
                    #     if "vegetation_type_woody" in woody_export.columns:
                    #         woody_export = woody_export[woody_export["vegetation_type_woody"] == "woody"].copy()
                    #
                    #     if "tree_age" not in woody_export.columns and "tree_year_planted" in woody_export.columns:
                    #         woody_export = calculate_tree_age(woody_export)
                    #
                    #     if "normalized_species" not in woody_export.columns:
                    #         if "scientific_lookup" not in locals():
                    #             scientific_lookup, common_lookup = load_species_lookup(config.PARTNER)
                    #         woody_export["normalized_species"] = woody_export.apply(
                    #             lambda row: normalize_species_name(row, scientific_lookup, common_lookup),
                    #             axis=1,
                    #         )
                    #
                    #     # Export for each attribute (Height, Circumference, Stems)
                    #     for metric_col, sheet_suffix in [
                    #         ("tree_height_m", "Height"),
                    #         ("circumference_bh", "Circ"),
                    #         ("nr_stems_bh", "Stems"),
                    #     ]:
                    #         if (
                    #             metric_col in woody_export.columns
                    #             and "tree_age" in woody_export.columns
                    #             and "normalized_species" in woody_export.columns
                    #         ):
                    #             try:
                    #                 dbscan_results = detect_multivariate_outliers_dbscan(
                    #                     woody_export,
                    #                     metric_col=metric_col,
                    #                     eps=0.5,
                    #                     min_samples=3,
                    #                 )
                    #                 if len(dbscan_results) > 0:
                    #                     dbscan_outliers = dbscan_results[dbscan_results["is_outlier"] == True]
                    #                     if len(dbscan_outliers) > 0:
                    #                         export_df = format_for_export(
                    #                             dbscan_outliers,
                    #                             issue_type=f"DBSCAN Outlier ({sheet_suffix})",
                    #                             additional_cols=[
                    #                                 "tree_age",
                    #                                 metric_col,
                    #                                 "normalized_species",
                    #                             ],
                    #                             key_col="MEASUREMENT_KEY",
                    #                         )
                    #                         sheet_name = f"Outliers DBSCAN ({sheet_suffix})"
                    #                         export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                    #                         sheet_dataframes[sheet_name] = export_df
                    #                         sheets_created += 1
                    #             except Exception as e:
                    #                 st.warning(f"Could not export DBSCAN {sheet_suffix} Outliers: {str(e)}")

                    # SHEET 10: Super Tall Trees (>25m)
                    if has_measurements:
                        try:
                            m_mea = raw_data["plots_subplots_vegetation_measurements"]
                            if "MEASUREMENT_KEY" in m_mea.columns:
                                m_mea_actual = m_mea[m_mea["MEASUREMENT_KEY"].notna()].copy()
                            else:
                                m_mea_actual = m_mea.copy()

                            if "tree_height_m" in m_mea_actual.columns:
                                super_tall = m_mea_actual[m_mea_actual["tree_height_m"] > 25].copy()

                                if len(super_tall) > 0:
                                    super_tall = merge_with_enumerator(super_tall, filtered_gdf)
                                    super_tall = add_tree_name_column(super_tall)

                                    # Ensure enumerator column exists - try multiple approaches
                                    if "enumerator" not in super_tall.columns:
                                        # Try to add from filtered_gdf if available
                                        if "enumerator" in filtered_gdf.columns and "subplot_id" in super_tall.columns:
                                            enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                            super_tall = super_tall.merge(enum_map, on="subplot_id", how="left")
                                        elif (
                                            "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in super_tall.columns
                                        ):
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
                                        key_col="MEASUREMENT_KEY",
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
                            meas_with_stems = detect_stem_outliers(meas_with_enum, threshold=20)
                            high_stems = meas_with_stems[meas_with_stems["high_stems_bh"] == True]

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
                                        "nr_stems_10cm",
                                        "tree_name",
                                        species_col,
                                    ],
                                    key_col="MEASUREMENT_KEY",
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
                            complete_with_enum = merge_with_enumerator(complete_df, filtered_gdf)
                            complete_with_enum = add_tree_name_column(complete_with_enum)

                            if "circumference_bh" in complete_with_enum.columns:
                                circ_col = "circumference_bh"
                            elif "circumference_10cm" in complete_with_enum.columns:
                                circ_col = "circumference_10cm"
                            else:
                                circ_col = None

                            if circ_col and "tree_year_planted" in complete_with_enum.columns:
                                circ_data = complete_with_enum[complete_with_enum[circ_col].notna()].copy()
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
                                            if (
                                                "enumerator" in filtered_gdf.columns
                                                and "subplot_id" in suspicious.columns
                                            ):
                                                enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                                suspicious = suspicious.merge(enum_map, on="subplot_id", how="left")
                                            elif (
                                                "enumerator" in filtered_gdf.columns
                                                and "SUBPLOT_KEY" in suspicious.columns
                                            ):
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
                                            key_col="CIRCUMFERENCE_KEY",
                                        )
                                        sheet_name = "Suspicious Circ by Age"
                                        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                                        sheet_dataframes[sheet_name] = export_df
                                        sheets_created += 1
                        except Exception as e:
                            st.warning(f"Could not export Suspicious Circ by Age: {str(e)}")

                    # SHEET 13: Missing Vegetation
                    try:
                        # Filter veg_df to only actual vegetation (non-null VEGETATION_KEY)
                        if "VEGETATION_KEY" in veg_df.columns:
                            veg_df_actual = veg_df[veg_df["VEGETATION_KEY"].notna()].copy()
                        else:
                            veg_df_actual = veg_df.copy()

                        # Filter plots_df to only include MEASURED subplots
                        # This ensures we don't count unmeasured subplots as "missing vegetation"
                        if "SUBPLOT_KEY" in plots_df.columns and "measured_subplots" in plots_df.columns:
                            import re

                            # Create temporary dataframe with subplot info
                            temp_plots = plots_df.copy()

                            # Extract subplot number from SUBPLOT_KEY (e.g., "uuid.../sub_plot[12]" -> 12)
                            temp_plots["subplot_number"] = temp_plots["SUBPLOT_KEY"].apply(
                                lambda x: int(re.search(r"\[(\d+)\]", str(x)).group(1))
                                if re.search(r"\[(\d+)\]", str(x))
                                else 999
                            )

                            # Convert measured_subplots to int
                            temp_plots["measured_subplots"] = temp_plots["measured_subplots"].apply(
                                lambda x: int(x) if pd.notna(x) else 999
                            )

                            # Only include subplots where subplot_number <= measured_subplots
                            plots_df_measured = temp_plots[
                                temp_plots["subplot_number"] <= temp_plots["measured_subplots"]
                            ].copy()

                            # Drop temporary columns
                            plots_df_measured = plots_df_measured.drop(columns=["subplot_number"], errors="ignore")
                        else:
                            # Fallback: use all plots_df
                            plots_df_measured = plots_df.copy()

                        # Get missing vegetation subplots (using measured plots only and actual vegetation)
                        missing_veg = get_missing_subplots(plots_df_measured, veg_df_actual)

                        if len(missing_veg) > 0:
                            # Ensure enumerator column exists
                            if "enumerator" not in missing_veg.columns:
                                # Try to add from filtered_gdf if available
                                if "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in missing_veg.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                    missing_veg = missing_veg.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                else:
                                    missing_veg["enumerator"] = ""

                            # Add explanation about measured_subplots vs actual data collected
                            if "measured_subplots" in missing_veg.columns and "SUBPLOT_KEY" in missing_veg.columns:
                                import re

                                def create_missing_description(row):
                                    parts = []

                                    # Extract subplot number
                                    subplot_match = re.search(r"\[(\d+)\]", str(row.get("SUBPLOT_KEY", "")))
                                    if subplot_match:
                                        subplot_num = subplot_match.group(1)
                                        parts.append(f"Subplot #{subplot_num}")

                                    # Add measured_subplots info
                                    if pd.notna(row.get("measured_subplots")):
                                        parts.append(
                                            f"Enumerator claimed {int(row['measured_subplots'])} subplots measured"
                                        )

                                    # Add comments if available
                                    if pd.notna(row.get("subplot_comments")):
                                        parts.append(f"Comment: {row['subplot_comments']}")
                                    else:
                                        parts.append("No vegetation data collected")

                                    return " | ".join(parts) if parts else "No vegetation data"

                                missing_veg["description"] = missing_veg.apply(create_missing_description, axis=1)

                                export_df = format_for_export(
                                    missing_veg,
                                    issue_type="Missing Vegetation",
                                    issue_description_col="description",
                                    key_col="SUBPLOT_KEY",
                                )
                            else:
                                export_df = format_for_export(
                                    missing_veg,
                                    issue_type="Missing Vegetation",
                                    additional_cols=["subplot_comments"],
                                    key_col="SUBPLOT_KEY",
                                )
                            sheet_name = "Missing Vegetation"
                            export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                            sheet_dataframes[sheet_name] = export_df
                            sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Missing Vegetation: {str(e)}")

                    # SHEET 14: Unknown/Unidentified Species
                    try:
                        # Get vegetation data with actual records only
                        if "VEGETATION_KEY" in veg_df.columns:
                            veg_df_actual = veg_df[veg_df["VEGETATION_KEY"].notna()].copy()
                        else:
                            veg_df_actual = veg_df.copy()

                        # Check for unidentified species (where species = "other")
                        unknown_species = check_unidentified_species(veg_df_actual)

                        if len(unknown_species) > 0:
                            # Ensure enumerator column exists
                            if "enumerator" not in unknown_species.columns:
                                # Try to add from filtered_gdf if available
                                if "enumerator" in filtered_gdf.columns and "SUBPLOT_KEY" in unknown_species.columns:
                                    enum_map = filtered_gdf[["subplot_id", "enumerator"]].drop_duplicates()
                                    enum_map.columns = ["SUBPLOT_KEY", "enumerator"]
                                    unknown_species = unknown_species.merge(enum_map, on="SUBPLOT_KEY", how="left")
                                else:
                                    unknown_species["enumerator"] = ""

                            # Add tree_name column for display
                            unknown_species = add_tree_name_column(unknown_species)

                            # Create issue description
                            def create_unknown_description(row):
                                parts = []

                                # Add tree name if available
                                if pd.notna(row.get("tree_name")) and row.get("tree_name") != "other":
                                    parts.append(f"Tree: {row['tree_name']}")
                                else:
                                    parts.append("Species marked as 'other'")

                                # Check which species column has "other"
                                species_cols = [
                                    "woody_species",
                                    "bamboo_species",
                                    "palm_species",
                                    "banana_species",
                                    "non_woody_species",
                                    "vegetation_species_type",
                                ]
                                for col in species_cols:
                                    if (
                                        col in row.index
                                        and pd.notna(row.get(col))
                                        and str(row.get(col)).lower() == "other"
                                    ):
                                        parts.append(f"Type: {col.replace('_', ' ').title()}")
                                        break

                                if (
                                    pd.notna(row.get("language_other_species"))
                                    and row.get("language_other_species") != ""
                                ):
                                    parts.append(f"Local: {row['language_other_species']}")

                                parts.append("Needs botanical verification")

                                return " | ".join(parts)

                            unknown_species["description"] = unknown_species.apply(create_unknown_description, axis=1)

                            export_df = format_for_export(
                                unknown_species,
                                issue_type="Unknown Species",
                                issue_description_col="description",
                                additional_cols=[
                                    "tree_name",
                                    "woody_species",
                                    "non_woody_species",
                                    "bamboo_species",
                                    "palm_species",
                                    "banana_species",
                                ],
                                key_col="VEGETATION_KEY",
                            )
                            sheet_name = "Unknown Species"
                            export_df.to_excel(writer, sheet_name=sheet_name, index=False)
                            sheet_dataframes[sheet_name] = export_df
                            sheets_created += 1
                    except Exception as e:
                        st.warning(f"Could not export Unknown Species: {str(e)}")

                    # Summary sheet if no data
                    if sheets_created == 0:
                        summary_df = pd.DataFrame({"Note": ["No quality issues found - all checks passed!"]})
                        sheet_name = "Summary"
                        summary_df.to_excel(writer, sheet_name=sheet_name, index=False)
                        sheet_dataframes[sheet_name] = summary_df

                    # Adjust column widths for all sheets
                    try:
                        for sheet_name, df in sheet_dataframes.items():
                            if sheet_name in writer.sheets:
                                worksheet = writer.sheets[sheet_name]
                                adjust_excel_column_widths(worksheet, df)
                    except Exception:
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

    # PDF Summary Report
    st.markdown("---")
    st.markdown("## 📄 Summary PDF Report")
    st.caption("Download comprehensive summary report with all quality check statisticss")

    if st.button(
        "📄 Generate Summary PDF Report",
        use_container_width=True,
        type="secondary",
    ):
        with st.status("Generating PDF summary report...", expanded=True) as status:
            try:
                from utils.pdf_summary_report import generate_summary_pdf_report

                # Get raw data
                status.update(label="Preparing data...", state="running")
                raw_data = st.session_state.data.get("raw_data", {})

                # Get DQ data from session state if available
                dq_data = st.session_state.get("dq_data")
                if dq_data:
                    dq_gdf = dq_data.get("subplots")
                    dq_raw_data = dq_data.get("raw_data", {})

                    # Apply date filter to DQ data (same as GT data)
                    if dq_gdf is not None and len(dq_gdf) > 0:
                        date_start = st.session_state.get("date_filter_start")
                        date_end = st.session_state.get("date_filter_end")
                        if date_start and date_end:
                            dq_gdf = filter_by_date(dq_gdf, date_start, date_end)
                else:
                    dq_gdf = None
                    dq_raw_data = None

                # Calculate expected work
                num_enumerators = filtered_gdf["enumerator"].nunique() if "enumerator" in filtered_gdf.columns else 0
                num_plots = filtered_gdf["PLOT_KEY"].nunique() if "PLOT_KEY" in filtered_gdf.columns else 0
                st.write(f"Processing {num_enumerators} enumerators, {num_plots} plots...")

                # Generate PDF with progress updates
                status.update(label="Generating maps and tables (this may take a moment)...", state="running")
                st.caption("Tip: PDF generation speed depends on the number of plots. Maps are rendered at reduced DPI for faster generation.")

                pdf_buffer = generate_summary_pdf_report(
                    filtered_gdf,
                    raw_data,
                    partner_name=config.PARTNER,
                    dq_gdf=dq_gdf,
                    dq_raw_data=dq_raw_data,
                )

                pdf_bytes = pdf_buffer.getvalue()
                timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

                status.update(label="PDF generated successfully!", state="complete")

                # Download button INSIDE the if-block - no session state needed
                st.download_button(
                    label="💾 Download Summary PDF Report",
                    data=pdf_bytes,
                    file_name=f"{config.PARTNER}_summary_report_{timestamp}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
                st.success(f"✅ PDF generated! ({len(pdf_bytes)/1024:.0f} KB)")

            except Exception as e:
                status.update(label="PDF generation failed", state="error")
                st.error(f"❌ Error generating PDF report: {str(e)}")
                st.exception(e)
                import traceback

                st.code(traceback.format_exc())

    # Charts
    st.markdown("---")
    st.markdown("## 📈 Validation Analysis")
    st.caption("Visual breakdown of geometry validation results. The pie chart shows overall pass/fail ratio. The bar chart breaks down specific error types to identify systemic issues (e.g., GPS accuracy problems, area calculation errors).")

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
    st.markdown("## 📅 Data Collection Timeline")
    st.caption("Shows submission volume over time. Use this to identify data collection patterns, gaps in fieldwork, or periods of intensive surveying. Spikes may indicate batch uploads or focused field campaigns.")
    fig_timeline = create_timeline_chart(filtered_gdf)
    if fig_timeline:
        st.plotly_chart(fig_timeline, use_container_width=True)

    # Enumerator performance (using only measured subplots)
    st.markdown("---")
    st.markdown("## 👥 Enumerator Overview")
    st.caption("Submission counts by enumerator (measured subplots only). Use this for workload distribution analysis. For detailed quality metrics per enumerator (error rates, measurement patterns), see the Enumerator Performance page.")
    fig_enum = create_enumerator_performance_chart(gdf_for_plots)
    if fig_enum:
        st.plotly_chart(fig_enum, use_container_width=True)

    # Summary table
    st.markdown("---")
    st.markdown("## 📋 Summary Statistics")
    st.caption("Detailed breakdown of validation errors by type. The percentage shows each error's contribution to total invalid records. Focus on high-percentage errors first for maximum impact on data quality improvement.")

    if summary["reason_counts"]:
        error_df = pd.DataFrame(
            {
                "Error Type": list(summary["reason_counts"].keys()),
                "Count": list(summary["reason_counts"].values()),
                "Percentage": [
                    f"{(count / summary['invalid'] * 100):.1f}%" for count in summary["reason_counts"].values()
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

    st.info("👈 Enter your SurveyCTO credentials and click 'Fetch & Validate' to load data")
