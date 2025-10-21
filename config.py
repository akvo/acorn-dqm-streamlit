"""
Configuration file for DQM App
Contains all thresholds, constants, and validation rules
"""

# ============================================
# VALIDATION THRESHOLDS
# ============================================

# Plot Geometry
MAX_PLOT_AREA_SIZE = 30  # hectares
MIN_SUBPLOT_AREA_SIZE = 450  # m²
MAX_SUBPLOT_AREA_SIZE = 750  # m²
MAX_VERTICES = 4
THRESHOLD_WITHIN_RADIUS = 40  # meters
THRESHOLD_LENGTH_WIDTH = 2.0
THRESHOLD_PROTRUDING_RATIO = 1.55

# Measurements
MAX_TREE_HEIGHT = 80  # meters
MIN_TREE_HEIGHT = 0.5  # meters
MAX_CIRCUMFERENCE_BH = 500  # cm
MAX_CIRCUMFERENCE_10CM = 1200  # cm
MAX_STEMS_BH = 50
HEIGHT_OUTLIER_RATIO = 4  # times median
CIRCUMFERENCE_OUTLIER_RATIO = 4

# Coverage
MAX_COVERAGE_PERCENTAGE = 100
MIN_COVERAGE_PERCENTAGE = 0

# ============================================
# COORDINATE SYSTEM
# ============================================
CRS = "EPSG:4326"  # WGS84

# ============================================
# SPECIES VALIDATION
# ============================================
WOODY_SPECIES_LIST = [
    "gliricidia_sepium",
    "parinari_curatellifolia",
    "mangifera_indica",
    "kigelia_africana",
    "combretum_molle",
    "manihot_esculenta",
]

BANANA_SPECIES_LIST = ["musa_acuminata", "musa_balbisiana"]

PALM_SPECIES_LIST = ["elaeis_guineensis", "cocos_nucifera"]

NON_WOODY_SPECIES_LIST = ["poacea", "grass", "weeds"]

# Coverage-only species (should not have individual measurements)
COVERAGE_ONLY_SPECIES = NON_WOODY_SPECIES_LIST + ["crops", "maize", "rice", "potatoes"]

# ============================================
# UI CONFIGURATION
# ============================================
SEVERITY_COLORS = {
    "critical": "#D32F2F",  # Red
    "error": "#F57C00",  # Orange
    "warning": "#FBC02D",  # Yellow
    "info": "#1976D2",  # Blue
    "valid": "#388E3C",  # Green
}

ISSUE_CATEGORIES = [
    "Geometry Issues",
    "Species Issues",
    "Measurement Issues",
    "Missing Data",
    "Overlapping Boundaries",
]

# ============================================
# PARTNERS & COUNTRIES
# ============================================
PARTNER_CONFIG = {
    "AFOCO": {"country": "Kyrgyzstan", "accuracy_threshold": 10},
    "COMACO": {"country": "Zambia", "accuracy_threshold": 10},
}

# ============================================
# EXPORT FORMATS
# ============================================
EXPORT_FORMATS = {
    "json": "application/json",
    "geojson": "application/geo+json",
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}

# ============================================
# DATE FORMATS
# ============================================
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================
# FILE UPLOAD SETTINGS
# ============================================
ALLOWED_EXTENSIONS = [".xlsx", ".xls"]
MAX_FILE_SIZE_MB = 500

# ============================================
# MAP SETTINGS
# ============================================
DEFAULT_MAP_CENTER = [0, 0]
DEFAULT_MAP_ZOOM = 2
MARKER_COLORS = {"valid": "green", "warning": "orange", "critical": "red"}
