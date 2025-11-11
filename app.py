"""
Ground Truth DQM - Main Landing Page
API-powered with manual credential input
"""

import streamlit as st
import config
from ui.components import show_header
from utils.data_processor import (
    process_excel_file,
    get_validation_summary,
    process_json_data,
)
import pandas as pd
import requests
from io import BytesIO

# Page config (must be first)
st.set_page_config(
    page_title="Ground Truth DQM",
    page_icon="🌳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Refresh partner configuration based on URL parameter
# This must be called AFTER set_page_config and BEFORE anything else
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

# Sidebar - API Configuration
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

# Main content
if st.session_state.data is not None:
    # Get data
    gdf_subplots = st.session_state.data["subplots"]
    summary = get_validation_summary(gdf_subplots)

    # Show quick summary
    st.markdown("## 📊 Quick Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Subplots", f"{summary['total']:,}")

    with col2:
        st.metric(
            "Valid Subplots",
            f"{summary['valid']:,}",
            f"{summary['valid_pct']:.1f}%",
        )

    with col3:
        st.metric("Invalid Subplots", f"{summary['invalid']:,}")

    with col4:
        total_issues = sum(summary["reason_counts"].values())
        st.metric("Total Issues", f"{total_issues:,}")

    # Status message
    st.markdown("---")
    valid_pct = summary["valid_pct"]

    if valid_pct >= 95:
        st.success(f"🎉 Excellent! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 90:
        st.success(f"✅ Very good! {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 80:
        st.warning(f"⚠️ Good, but {summary['invalid']} subplots need attention")
    else:
        st.error(f"❌ Critical: {summary['invalid']} subplots invalid")

    # Navigation cards
    st.markdown("---")
    st.markdown("## 🧭 Navigate to:")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
        <div class="metric-card">
            <h3>📊 Overview Dashboard</h3>
            <p>Detailed metrics, charts, and validation breakdown</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Overview →", key="nav_overview", use_container_width=True):
            config.switch_page_with_query_params("pages/_Overview.py")

    with col2:
        st.markdown(
            """
        <div class="metric-card">
            <h3>🗺️ Map View</h3>
            <p>Interactive map showing valid and invalid subplots</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Map →", key="nav_map", use_container_width=True):
            config.switch_page_with_query_params("pages/_Map_View.py")

    with col3:
        st.markdown(
            """
        <div class="metric-card">
            <h3>❌ Invalid Subplots</h3>
            <p>Detailed list of subplots requiring attention</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Issues →", key="nav_issues", use_container_width=True):
            config.switch_page_with_query_params("pages/_Plot_Issues.py")

    st.markdown("<br>", unsafe_allow_html=True)

    col4, col5 = st.columns(2)

    with col4:
        st.markdown(
            """
        <div class="metric-card">
            <h3>🌳 Subplot Details</h3>
            <p>Deep dive into individual subplot information</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Details →", key="nav_details", use_container_width=True):
            config.switch_page_with_query_params("pages/_Subplot_Details.py")

    with col5:
        st.markdown(
            """
        <div class="metric-card">
            <h3>👤 Enumerator Performance</h3>
            <p>Quality tracking by data collector</p>
        </div>
        """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Performance →", key="nav_enum", use_container_width=True):
            config.switch_page_with_query_params("pages/_Enumerator_Performance.py")

else:
    # Welcome screen
    st.markdown("## 👋 Welcome to Ground Truth DQM")

    st.info(
        "👈 Enter your SurveyCTO credentials and click 'Fetch & Validate' to load data"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
        ### 📋 How It Works
        
        This application validates ground truth forestry data:
        
        1. **Fetch** - Automatically get latest data from SurveyCTO API
        2. **Parse** - Read and structure the data
        3. **Create Geometries** - Convert GPS coordinates
        4. **Fix Geometries** - Apply 13 correction operations
        5. **Validate** - Check area, vertices, overlaps
        6. **Report** - Generate comprehensive results
        
        ### ✅ What Gets Validated
        
        - ✓ GPS accuracy (≤10m threshold)
        - ✓ Subplot area (450-750 m²)
        - ✓ Plot area (1,000-300,000 m²)
        - ✓ Geometry validity and structure
        - ✓ Vertex count (minimum 4)
        - ✓ Shape analysis (not too elongated)
        - ✓ Radius constraints
        - ✓ Overlapping boundaries
        """
        )

    with col2:
        st.markdown(
            """
        ### 🌐 API Setup
        
        Enter your credentials in the sidebar:
        
        1. **Server Name** - Your SurveyCTO server (e.g., akvofoundation)
        2. **Username** - Your SurveyCTO username
        3. **Password** - Your SurveyCTO password
        4. **Form ID** - Your form ID
        
        ### 📊 After Processing
        
        - **Overview Dashboard** - Statistics and charts
        - **Interactive Map** - Visual representation
        - **Issue List** - Invalid subplots with reasons
        - **Subplot Details** - Individual information
        - **Performance Metrics** - Quality by enumerator
        - **Export Options** - Download validated data
        
        ### 🔄 Always Fresh
        
        API automatically fetches latest submissions!
        No manual export or upload needed.
        
        ### 🔒 Security
        
        Credentials are only used for this session and not stored.
        """
        )
