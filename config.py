"""
Configuration for Ground Truth DQM
Supports dynamic partner selection via URL parameters
"""

import streamlit as st

# ============================================
# PARTNER CONFIGURATIONS
# ============================================

PARTNERS = {
    "AFOCO": {
        "country": "Kyrgyzstan",
        "country_iso3": "KGZ",
        "min_plot_area": 1000,
        "max_plot_area": 300000,
        "map_center": [41.5, 74.5],
    },
    "COMACO": {
        "country": "Zambia",
        "country_iso3": "ZMB",
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
    # Try to get partner from URL query parameters
    query_params = st.query_params

    # Check if 'partner' is in query params
    if "partner" in query_params:
        partner_param = query_params["partner"].upper()

        # Validate partner exists
        if partner_param in PARTNERS:
            return partner_param
        else:
            st.warning(f"⚠️ Unknown partner '{partner_param}'. Using default AFOCO.")
            return "AFOCO"

    # Default partner if no URL parameter
    return "AFOCO"


# Set active partner
ACTIVE_PARTNER = get_active_partner()

# Partner details
PARTNER = ACTIVE_PARTNER
COUNTRY = PARTNERS[PARTNER]["country"]
COUNTRY_ISO3 = PARTNERS[PARTNER]["country_iso3"]

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

APP_TITLE = f"Ground Truth DQM - {PARTNER}"
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
