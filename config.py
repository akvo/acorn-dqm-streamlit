"""
Configuration for Ground Truth DQM
Supports dynamic partner selection via URL parameters
"""

import streamlit as st

# ============================================
# PARTNER CONFIGURATIONS
# ============================================

PARTNERS = {
    "IORA": {
        "country": "India",
        "country_iso3": "IND",
        "dqID": "data_quality_ground_truth_collection_iora_2025_november",
        "gtID": "ground_truth_collection_iora_2025_november",
        "description": "IORA - India",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [25.6, 90.8],
    },
    "AFOCO": {
        "country": "Kyrgyzstan",
        "country_iso3": "KGZ",
        "dqID": "data_quality_ground_truth_collection_afoco_2025",
        "gtID": "Ground_Truth_Collection_AFOCO_2025_translated",
        "description": "AFOCO - Kyrgyzstan",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [41.5, 74.5],
    },
    "COMACO": {
        "country": "Zambia",
        "country_iso3": "ZMB",
        "dqID": "data_quality_ground_truth_collection_comaco_2025",
        "gtID": "Ground_Truth_Collection_COMACO_2025",
        "description": "COMACO - Zambia",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [-13.5, 28.5],
    },
}

# ============================================
# GET ACTIVE PARTNER FROM URL OR DEFAULT
# ============================================


def get_active_partner():
    """
    Get active partner from URL query parameters or default
    Usage: http://localhost:8501/?partner=COMACO
    """
    try:
        # Try to get query parameters using Streamlit's API
        # st.query_params works differently in different Streamlit versions

        # For Streamlit >= 1.22
        if hasattr(st, "query_params"):
            query_params = st.query_params

            # st.query_params is a dict-like object
            if "partner" in query_params:
                partner_param = query_params["partner"]

                if partner_param:
                    partner_param = str(partner_param).upper()

                    # Validate partner exists
                    if partner_param in PARTNERS:
                        return partner_param
                    else:
                        st.warning(
                            f"⚠️ Unknown partner '{partner_param}'. Using default COMACO."
                        )
                        return "COMACO"

        # Fallback: try experimental API for older Streamlit versions
        elif hasattr(st, "experimental_get_query_params"):
            query_params = st.experimental_get_query_params()

            if "partner" in query_params:
                partner_param = (
                    query_params["partner"][0]
                    if isinstance(query_params["partner"], list)
                    else query_params["partner"]
                )

                if partner_param:
                    partner_param = str(partner_param).upper()

                    if partner_param in PARTNERS:
                        return partner_param
                    else:
                        st.warning(
                            f"⚠️ Unknown partner '{partner_param}'. Using default COMACO."
                        )
                        return "COMACO"

    except Exception as e:
        # If any error, use default
        # Silently fail and use default
        pass

    # Default partner if no URL parameter or error
    return "COMACO"


# Initialize with default, will be updated when app runs
_DEFAULT_PARTNER = "COMACO"
ACTIVE_PARTNER = _DEFAULT_PARTNER

# Initialize partner details with default
PARTNER = ACTIVE_PARTNER
PARTNER_CONFIG = PARTNERS[PARTNER]
COUNTRY = PARTNER_CONFIG["country"]
COUNTRY_ISO3 = PARTNER_CONFIG["country_iso3"]
DESCRIPTION = PARTNER_CONFIG["description"]
DQ_FORM_ID = PARTNER_CONFIG["dqID"]
GT_FORM_ID = PARTNER_CONFIG["gtID"]


def refresh_partner_config():
    """
    Refresh partner configuration based on current URL query parameters or session state.
    Call this from the app after Streamlit is fully initialized.
    """
    import streamlit as st

    global ACTIVE_PARTNER, PARTNER, PARTNER_CONFIG, COUNTRY, COUNTRY_ISO3
    global DESCRIPTION, DQ_FORM_ID, GT_FORM_ID, APP_TITLE, APP_SUBTITLE, MAP_CENTER

    # Get partner from URL or session state
    new_partner = get_active_partner()

    # Store in session state for persistence across page navigation
    if "partner" not in st.session_state or st.session_state.partner != new_partner:
        st.session_state.partner = new_partner

    # Use session state value if available
    new_partner = st.session_state.get("partner", new_partner)

    # Only update if partner changed
    if new_partner != ACTIVE_PARTNER:
        ACTIVE_PARTNER = new_partner
        PARTNER = new_partner
        PARTNER_CONFIG = PARTNERS[PARTNER]
        COUNTRY = PARTNER_CONFIG["country"]
        COUNTRY_ISO3 = PARTNER_CONFIG["country_iso3"]
        DESCRIPTION = PARTNER_CONFIG["description"]
        DQ_FORM_ID = PARTNER_CONFIG["dqID"]
        GT_FORM_ID = PARTNER_CONFIG["gtID"]
        APP_TITLE = f"Ground Truth DQM - {DESCRIPTION}"
        APP_SUBTITLE = f"Data Quality Management for {COUNTRY}"
        MAP_CENTER = PARTNER_CONFIG["map_center"]

        # Update query params to match session state (Streamlit 1.50.0 syntax)
        try:
            st.query_params.update({"partner": new_partner})
        except Exception:
            # If query params can't be updated, that's ok - session state will persist
            pass

    return ACTIVE_PARTNER


def switch_page_with_query_params(page_path):
    """
    Switch to a page while preserving query parameters.

    Args:
        page_path: Path to the page (e.g., "pages/_Overview.py")
    """
    import streamlit as st

    # Streamlit 1.50.0 should preserve query params automatically
    # Just call switch_page directly
    st.switch_page(page_path)


# ============================================
# VALIDATION THRESHOLDS
# ============================================

# Subplot area constraints (m²)
MIN_SUBPLOT_AREA_SIZE = 450
MAX_SUBPLOT_AREA_SIZE = 750

# Plot area constraints (m²)
MIN_GT_PLOT_AREA_SIZE = PARTNERS[PARTNER]["min_plot_area"]
MAX_GT_PLOT_AREA_SIZE = PARTNERS[PARTNER]["max_plot_area"]

# Geometry validation
MAX_VERTICES = 4
THRESHOLD_WITHIN_RADIUS = 40  # meters (subplots)
THRESHOLD_WITHIN_RADIUS_PLOT = 200  # meters (plots)
THRESHOLD_LENGTH_WIDTH = 2.0
THRESHOLD_PROTRUDING_RATIO = 1.55

# GPS accuracy
GPS_ACCURACY_THRESHOLD = 10  # meters

# ============================================
# SYSTEM SETTINGS
# ============================================

CRS_EPSG = "EPSG:4326"
YEAR = "2025"

# ============================================
# UI CONFIGURATION
# ============================================

APP_TITLE = f"Ground Truth DQM - {DESCRIPTION}"
APP_SUBTITLE = f"Data Quality Management for {COUNTRY}"
APP_ICON = "🌳"

SEVERITY_COLORS = {
    "critical": "#D32F2F",
    "error": "#F57C00",
    "warning": "#FBC02D",
    "info": "#1976D2",
    "valid": "#388E3C",
}

# Map settings
MAP_CENTER = PARTNERS[PARTNER]["map_center"]
DEFAULT_ZOOM = 7
