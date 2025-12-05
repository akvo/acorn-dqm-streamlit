# CLAUDE.md - Project Guide for AI Assistants

## Project Overview

**ACORN-DQM-Streamlit** is a Streamlit-based web application for managing and validating ground truth data quality for tree/vegetation surveys. It supports multiple partner organizations (IORA, AFOCO, COMACO, AFEC) with different geographic regions and validation requirements.

**Primary purpose:** Perform comprehensive data quality checks on geospatial plot and subplot data, vegetation measurements, and generate detailed reports.

## Quick Start

```bash
# Install dependencies (use Python 3.11 or 3.12, not 3.14)
pip install -r requirements.txt

# Run the application
streamlit run app.py

# Access at http://localhost:8501
# Select partner via URL: http://localhost:8501/?partner=COMACO
```

## Project Structure

```
acorn-dqm-streamlit/
├── app.py                    # Main entry point - Overview Dashboard
├── config.py                 # Partner configs, validation thresholds
├── requirements.txt          # Python dependencies
├── pages/                    # Streamlit multi-page app
│   ├── _Map_View.py         # Interactive folium map
│   ├── _Plot_Issues.py      # Plots with validation errors
│   ├── _Subplot_Details.py  # Vegetation quality checks (largest file)
│   ├── _Enumerator_Performance.py  # Enumerator stats, PDF export
│   └── _Z_GT_DQ_Comparison.py      # GT vs DQ comparison
├── core/                     # Core validation logic
│   └── gt_check_functions.py # Geometry validation & transformation
├── utils/                    # Utility modules
│   ├── data_processor.py    # Main data processing pipeline
│   ├── data_processor_surveycto.py  # SurveyCTO API parsing
│   ├── data_merge_utils.py  # Data merging and enrichment
│   ├── vegetation_validation.py     # Species & vegetation checks
│   ├── comparison_utils.py  # GT vs DQ comparison functions
│   ├── export_helpers.py    # GeoJSON, CSV, Excel export
│   ├── pdf_summary_report.py # PDF report generation
│   └── cache_utils.py       # Dev mode caching
├── ui/                       # UI components
│   ├── components.py        # Reusable Streamlit components
│   └── charts.py            # Plotly visualizations
├── data/species/            # Species reference lists (TSV files)
├── case-specific/iora/      # Partner-specific utilities
└── .streamlit/              # Streamlit config (config.toml, secrets.toml)
```

## Key Technologies

- **Streamlit 1.50.0** - Web framework
- **pandas** - Data manipulation
- **geopandas** - Geospatial data processing
- **shapely** - Geometric operations
- **folium** - Interactive maps
- **plotly** - Charts and visualizations
- **reportlab** - PDF generation

## Architecture Patterns

### Data Flow
```
SurveyCTO API / Excel Upload
    → process_json_data() / process_excel_file()
    → Extract 5 sheets: Plots, Subplots, Vegetation, Measurements, Circumference
    → merge_all_data() → GeoDataFrame
    → Geometry Validation (GeometryValidator, GeometryFixer)
    → Display in Pages → Export (GeoJSON, CSV, PDF)
```

### Session State Pattern
```python
if "data" not in st.session_state:
    st.session_state.data = None
```

### Data Dictionary Pattern
Functions return dict with multiple dataframes:
```python
data = {
    'plots': GeoDataFrame,
    'subplots': GeoDataFrame,
    'vegetation': DataFrame,
    'measurements': DataFrame,
    'circumference': DataFrame,
    'raw_data': {...}
}
```

### Validation Pattern
```python
reasons = []
if area < min_area:
    reasons.append(f"Area too small: {area} m²")
valid = len(reasons) == 0
```

## Partner Configuration

Partners are configured in `config.py`:
- **IORA** - India (Meghalaya)
- **AFOCO** - Kyrgyzstan
- **COMACO** - Zambia
- **AFEC** - India (Andhra Pradesh)

Each partner has: country, form IDs (gtID, dqID), map center coordinates, and optional custom thresholds.

Access current partner config:
```python
config.PARTNER           # e.g., "COMACO"
config.COUNTRY          # e.g., "Zambia"
config.GT_FORM_ID       # SurveyCTO form ID
config.PARTNER_CONFIG   # Full config dict
```

## Validation Thresholds

- Subplot area: 450-750 m²
- Plot area: 1000-300000 m²
- Max vertices: 4 (quadrilateral plots)
- GPS accuracy: ≤ 10 meters
- Proximity check: 40m (subplots), 200m (plots)

## Key Files by Function

| File | Purpose |
|------|---------|
| `app.py` | Main dashboard, data loading, API integration |
| `config.py` | All partner configs and validation settings |
| `core/gt_check_functions.py` | GeometryValidator, GeometryFixer, coordinate transforms |
| `utils/data_processor.py` | Complete data pipeline for Excel/JSON processing |
| `utils/vegetation_validation.py` | Species validation, height/circumference outliers |
| `pages/_Subplot_Details.py` | Most comprehensive page - vegetation quality checks |
| `pages/_Enumerator_Performance.py` | Per-enumerator metrics, PDF reports |

## Environment Variables

- `DEV_MODE=true` - Enable local caching of API responses (for development)

## Coordinate Reference System

All geometries use **WGS84 (EPSG:4326)**. Area/distance calculations may use UTM projections.

## Common Development Tasks

### Adding a new partner
1. Add config entry to `PARTNERS` dict in `config.py`
2. Include: country, gtID, dqID, map_center coordinates
3. Optionally add custom thresholds

### Adding validation rules
1. Add validation logic in `core/gt_check_functions.py` or `utils/vegetation_validation.py`
2. Append reason string to reasons list
3. Update relevant page to display the validation

### Modifying exports
- GeoJSON/CSV/Excel: `utils/export_helpers.py`
- PDF reports: `utils/pdf_summary_report.py`

## Git Workflow

- **main** - Production branch
- **version-two** - Active development branch
