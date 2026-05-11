"""
Configuration for Ground Truth DQM
Supports dynamic partner selection via URL parameters
"""

import streamlit as st

# ============================================
# PARTNER CONFIGURATIONS
# ============================================

PARTNERS = {
    "RAV": {
        "country": "Vietnam",
        "country_iso3": "VNM",
        "dqID": "data_quality_ground_truth_collection_ra_vietnam_2026_may_vietnamese",
        "gtID": "ground_truth_collection_RA_Vietnam_2026_may_Vietnamese",
        "description": "Rainforest Alliance Vietnam 2026",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [13.920683, 108.438476],
        "start_date": "2026-05-06",
    },
    "SOLK": {
        "country": "Kenya",
        "country_iso3": "KEN",
        "dqID": "data_quality_ground_truth_collection_Solidaridad_Kenya_2026_February",
        "gtID": "ground_truth_collection_Solidaridad_Kenya_2026_February",
        "description": "Solidaridad Kenya 2026",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [0.705, 37.422],
        "start_date": "2026-02-09",
    },
    "TFK": {
        "country": "Kenya",
        "country_iso3": "KEN",
        "dqID": "data_quality_ground_truth_collection_trees_for_kenya_2026_january",
        "gtID": "ground_truth_collection_trees_for_kenya_2026_january",
        "description": "Trees for Kenya 2026",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [0.705, 37.422],
        "start_date": "2026-01-26",
    },
    "FA": {
        "country": "Kenya",
        "country_iso3": "KEN",
        "dqID": "data_quality_ground_truth_collection_farm_africa_2026_january",
        "gtID": "ground_truth_collection_Farm_Africa_2026_January",
        "description": "Farm Africa 2026",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [0.705, 37.422],
        "start_date": "2026-01-12",
    },
    "INTELLECAP": {
        "country": "India",
        "country_iso3": "IND",
        "dqID": "data_quality_ground_truth_collection_INTELLECAP_2025_December",
        "gtID": "ground_truth_collection_INTELLECAP_2025_December",
        "description": "Intellecap - India",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [23.67, 85.38],
        "start_date": "2025-12-01",
    },
    "IORA": {
        "country": "India",
        "country_iso3": "IND",
        "dqID": "data_quality_ground_truth_collection_iora_2025_november",
        "gtID": "ground_truth_collection_iora_2025_november",
        "description": "IORA - India",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [25.6, 90.8],
        "start_date": "2025-11-01",
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
        "start_date": "2025-01-01",
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
        "start_date": "2025-01-01",
    },
    "AFEC": {
        "country": "India",
        "country_iso3": "IND",
        "dqID": "data_quality_ground_truth_collection_afec_2025_november",
        "gtID": "ground_truth_collection_afec_2025_december",
        "description": "AFEC - India",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [14.6, 77.4],
        "start_date": "2025-11-01",
    },
    "SOLU": {
        "country": "Uganda",
        "country_iso3": "UGA",
        "dqID": "data_quality_ground_truth_collection_Solidaridad_Uganda_2026_February",
        "gtID": "ground_truth_collection_Solidaridad_Uganda_2026_February",
        "description": "Solidaridad Uganda 2026",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [0.705, 37.422],
        "start_date": "2026-02-19",
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
                        st.warning(f"⚠️ Unknown partner '{partner_param}'. Using default COMACO.")
                        return "COMACO"

        # Fallback: try experimental API for older Streamlit versions
        elif hasattr(st, "experimental_get_query_params"):
            query_params = st.experimental_get_query_params()

            if "partner" in query_params:
                partner_param = (
                    query_params["partner"][0] if isinstance(query_params["partner"], list) else query_params["partner"]
                )

                if partner_param:
                    partner_param = str(partner_param).upper()

                    if partner_param in PARTNERS:
                        return partner_param
                    else:
                        st.warning(f"⚠️ Unknown partner '{partner_param}'. Using default COMACO.")
                        return "COMACO"

    except Exception:
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
    Refresh partner configuration based on URL query parameters or session state.
    Call this from the app after Streamlit is fully initialized.

    Priority: Session State > URL Parameter > Default

    For multi-user apps: URL params are the source of truth.
    Users should always access via /?partner=PARTNER_NAME
    """
    import streamlit as st

    global ACTIVE_PARTNER, PARTNER, PARTNER_CONFIG, COUNTRY, COUNTRY_ISO3
    global DESCRIPTION, DQ_FORM_ID, GT_FORM_ID, APP_TITLE, APP_SUBTITLE, MAP_CENTER

    # Priority 1: Session state (for navigation within same session)
    if "partner" in st.session_state and st.session_state.partner:
        new_partner = st.session_state.partner
    else:
        # Priority 2: URL parameter (for initial load or explicit request)
        new_partner = get_active_partner()
        # Store in session state for navigation persistence
        st.session_state.partner = new_partner

    # Validate partner exists
    if new_partner not in PARTNERS:
        new_partner = _DEFAULT_PARTNER
        st.session_state.partner = new_partner

    # Update globals if partner changed
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

    # Always sync URL params with current partner (keeps URL shareable)
    try:
        if st.query_params.get("partner") != new_partner:
            st.query_params["partner"] = new_partner
    except Exception:
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

# PDF Generation Settings
# Lower DPI = faster PDF generation (50 gives ~4x speedup vs 100)
PDF_MAP_DPI = 50

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
DEFAULT_ZOOM = 10
