# CLAUDE.md - Project Guide for AI Assistants

## Project Overview

**ACORN-DQM-Streamlit** is a Streamlit-based web application for managing and validating ground truth (GT) data quality for tree/vegetation surveys under the ACORN carbon credit program. It supports 9 partner organizations across multiple countries. Each partner submits geospatial plot/subplot data and vegetation measurements via SurveyCTO forms. This app performs comprehensive data quality checks and generates reports.

## Quick Start

```bash
# Python 3.11 or 3.12 (NOT 3.14)
pip install -r requirements.txt
streamlit run app.py
# Access: http://localhost:8501/?partner=COMACO
```

## Project Structure

```
acorn-dqm-streamlit/
├── app.py                          # Main entry point - Overview Dashboard (1964 lines)
├── config.py                       # Partner configs, validation thresholds (306 lines)
├── requirements.txt
├── pages/
│   ├── _Map_View.py               # Interactive folium map (831 lines)
│   ├── _Plot_Issues.py            # Plots with ≥8 invalid subplots (878 lines)
│   ├── _Subplot_Details.py        # Vegetation quality checks (2571 lines)
│   ├── _Enumerator_Performance.py # Per-enumerator stats, PDF/GeoJSON export (3316 lines)
│   ├── _Exploratory.py            # Deep dive GT+DQ analysis (484 lines)
│   └── _Z_GT_DQ_Comparison.py     # GT vs DQ comparison (1110 lines)
├── core/
│   └── gt_check_functions.py      # Geometry validation & transformation (987 lines)
├── utils/
│   ├── __init__.py                # Public API exports
│   ├── data_processor.py          # Main data pipeline (1155 lines)
│   ├── data_processor_surveycto.py # SurveyCTO API parsing (320 lines)
│   ├── data_merge_utils.py        # Data merging, species analysis, outlier detection (857 lines)
│   ├── vegetation_validation.py   # Species & vegetation checks (642 lines)
│   ├── comparison_utils.py        # GT vs DQ matching & comparison (631 lines)
│   ├── export_helpers.py          # GeoJSON, CSV, Excel export (113 lines)
│   ├── pdf_summary_report.py      # Multi-page PDF report (1487 lines)
│   ├── cache_utils.py             # Dev mode caching (43 lines)
│   └── session_manager.py         # Multi-user session/data management (113 lines)
├── ui/
│   ├── __init__.py
│   ├── components.py              # Reusable Streamlit components (410 lines)
│   └── charts.py                  # Plotly visualizations (124 lines)
├── data/species/{PARTNER}/        # Species reference TSV files per partner
├── case-specific/iora/
│   └── species_classifier.py      # AI species classification (Claude Haiku)
└── .streamlit/
    ├── config.toml                # Theme, server config (port 8080, max upload 500MB)
    └── secrets.toml               # SurveyCTO server config
```

## Complete Data Flow

```
SurveyCTO API (JSON)  ──→  read_json_to_sheets()  ──┐
                                                      ├──→ merge_all_data()
Excel Upload (.xlsx)  ──→  read_excel_all_sheets() ──┘         │
                                                        5 sheets extracted:
                                                        plots, subplots, vegetation,
                                                        measurements, circumference
                                                                │
                                                    ┌───────────┘
                                                    ▼
                                          Hierarchical merging:
                                          plots_subplots
                                          plots_subplots_vegetation
                                          plots_subplots_vegetation_measurements
                                          complete (all merged)
                                                    │
                                                    ▼
                                    GPS string → coordinates_from_vertices()
                                    (accuracy filtering: ≤10m, optional zero handling)
                                                    │
                                                    ▼
                                    geom_from_scto_str() → Polygon
                                    (requires ≥3 valid points, ≥80% valid)
                                                    │
                                                    ▼
                                    GeometryFixer.fix_geometry()
                                    (13-step single-pass pipeline)
                                                    │
                                                    ▼
                                    GeometryValidator.validate_geometry()
                                    (area, vertices, ratio, overlap, radius)
                                                    │
                                                    ▼
                                    assign_geom_valid_geojson()
                                    → GeoDataFrame with geom_valid, reasons columns
                                                    │
                                                    ▼
                                    st.session_state.data = {
                                        'subplots': GeoDataFrame,
                                        'plots': GeoDataFrame,
                                        'raw_data': {merged DataFrames},
                                        'sheets': {original 5 sheets}
                                    }
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                              Pages display    Export reports    DQ Comparison
                              (filtered by     (PDF, Excel,     (match plots by
                               date/enum)      GeoJSON, CSV)     centroid <50m)
```

## Partner Configuration (config.py)

9 partners configured in `PARTNERS` dict:

| Partner | Country | Notes |
|---------|---------|-------|
| SOLK | Kenya | |
| TFK | Kenya | |
| FA | Kenya | |
| INTELLECAP | India | |
| IORA | India (Meghalaya) | Has AI species classifier |
| AFOCO | Kyrgyzstan | |
| COMACO | Zambia | Default partner |
| AFEC | India (Andhra Pradesh) | |
| SOLU | Uganda | |

Each config: `country`, `country_iso3`, `gtID`, `dqID` (SurveyCTO form IDs), `min_plot_area`, `max_plot_area`, `map_center`, `start_date`, `description`.

**Partner selection priority:** Session State > URL param `?partner=X` > Default (COMACO)

**Global state pattern:** `config.refresh_partner_config()` sets module-level globals (`PARTNER`, `COUNTRY`, `GT_FORM_ID`, `DQ_FORM_ID`, `PARTNER_CONFIG`, `MAP_CENTER`, etc.) via `global` keyword.

## Validation Thresholds (config.py constants)

| Threshold | Value | Constant |
|-----------|-------|----------|
| Subplot area | 450-750 m² | `MIN/MAX_SUBPLOT_AREA_SIZE` |
| Plot area | 1000-300000 m² | `MIN/MAX_GT_PLOT_AREA_SIZE` (partner-specific) |
| Max vertices | 4 | `MAX_VERTICES` |
| GPS accuracy | ≤10m | `GPS_ACCURACY_THRESHOLD` |
| Subplot proximity | 40m | `THRESHOLD_WITHIN_RADIUS` |
| Plot proximity | 200m | `THRESHOLD_WITHIN_RADIUS_PLOT` |
| Aspect ratio | 2.0 | `THRESHOLD_LENGTH_WIDTH` |
| Protruding ratio | 1.55 | `THRESHOLD_PROTRUDING_RATIO` |
| Plot invalid threshold | ≥8 invalid subplots | Hardcoded in app.py line 770 |

## Session State Keys

```python
st.session_state.data                  # GT processed data dict (subplots GDF, raw_data, etc.)
st.session_state.dq_data               # DQ processed data dict (same structure)
st.session_state.filename              # GT data source display name
st.session_state.dq_filename           # DQ data source display name
st.session_state.server_name           # "akvofoundation" (hardcoded)
st.session_state.username              # SurveyCTO credentials
st.session_state.password              # SurveyCTO credentials
st.session_state.data_source_mode      # "api" or "file"
st.session_state.dq_data_source_mode   # "api" or "file"
st.session_state.credentials_validated # Bool - auth gate for pages
st.session_state.accuracy_zero_valid   # Bool - GPS accuracy=0 considered valid?
st.session_state.partner               # Active partner code
st.session_state.date_filter_start     # Persistent date filter
st.session_state.date_filter_end       # Persistent date filter
```

## Core Module: gt_check_functions.py

### Key Classes

**`GeometryFixer`** - 13-step single-pass fixing pipeline (optimized: single `.apply()` call):
1. Remove duplicate vertices
2. Fix self-intersecting (convex hull)
3. Fix winding order (orient)
4. Fix with rewind (geojson_rewind)
5. Fix with zero buffer
6. Convert to 2D polygon
7. Replace degraded types (Point/LineString → empty)
8. Replace multipolygons (keep largest if >90% area)
9. Simplify (0.1m tolerance)
10. Replace zero-area
11. Replace None geometries
12. Replace out-of-bounds (lat [-80,84], lon [-180,180])
13. Replace invalid (buffer(0) or representative point)

Tracks which step caused emptiness via `became_empty_at` column.

**`GeometryValidator`** - Validation pipeline adds columns:
- `length_width_ratio_too_big`, `protruding_ratio_too_big`
- `area_m2`, `nr_vertices`, `nr_vertices_too_small`
- `in_radius`, `in_country`, `duplicate_id`
- `overlap_ids`, `percentage_overlap`

**`WGS84Point`** - Frozen dataclass for validated lat/lon coordinates.

### Key Functions

| Function | Purpose |
|----------|---------|
| `coordinates_from_vertices(vertices, accuracy_m)` | Parse GPS string, filter by accuracy |
| `geom_from_scto_str(pd_row, column, accuracy_m)` | SurveyCTO string → Polygon + metadata |
| `collect_reasons_subplot(row, min, max)` | Collect all validation failure reasons as semicolon-separated string |
| `assign_geom_valid_geojson(gdf, min, max)` | Add `reasons`, `geom_valid`, `geojson` columns |
| `calculate_area(gdf, geodisic=False)` | Geodesic or projected area calculation |
| `validate_overlap(gdf, id_col, min_overlap)` | Self-overlay with -5m buffer to find overlaps |
| `geom_to_utm(geom)` | WGS84 → UTM with cached transformers |

**UTM transformer caching:** `_utm_transformer_cache` dict avoids recreating transformers per geometry.

## Utils Module Detail

### data_processor.py (main pipeline)

| Function | Purpose |
|----------|---------|
| `read_excel_all_sheets(file)` | Read 5-sheet GT Excel format |
| `read_json_to_sheets(json_data)` | Convert SurveyCTO JSON to sheet structure |
| `merge_all_data(sheets_dict)` | Hierarchical merge → dict of merged DataFrames |
| `process_excel_file(file)` | Complete Excel pipeline → dict with GeoDataFrame |
| `process_json_data(json_data)` | Complete JSON pipeline → dict with GeoDataFrame |
| `get_validation_summary(gdf)` | Stats: total, valid, invalid, percentage, reason_counts |
| `filter_by_enumerator(gdf, list)` | Filter GDF by enumerator names |
| `filter_by_date(gdf, start, end)` | Filter GDF by date range |
| `get_height_outliers(raw_data, threshold)` | Height outliers: >Nx or <1/Nx median per VEGETATION_KEY group |
| `get_circumference_outliers(raw_data, threshold)` | Same for circumference |
| `get_missing_subplots_analysis(raw_data)` | Measured subplots without vegetation records |

### data_merge_utils.py (merging & species)

| Function | Purpose |
|----------|---------|
| `merge_with_enumerator(veg_df, subplots_gdf)` | INNER JOIN vegetation + enumerator info |
| `add_tree_name_column(df)` | Priority: woody→bamboo→banana→palm→living_fences→"Unknown" |
| `load_species_lookup(partner)` | Load TSV files → (scientific_to_label, common_to_label) dicts |
| `normalize_species_name(name, lookup)` | Match against scientific and common names |
| `detect_species_outliers(df)` | >4x or <0.25x median per species |
| `detect_multivariate_outliers_dbscan(df)` | DBSCAN on [age, metric] per species |
| `detect_regression_outliers(df)` | Linear regression-based outlier detection |
| `extract_year_from_planted(series)` | Handles epochs (ms/s), years, date strings |

Species TSV files located at: `data/species/{PARTNER}/{type}_species.tsv` (value\tlabel format)

### vegetation_validation.py

| Function | Purpose |
|----------|---------|
| `check_missing_vegetation(raw_data)` | Subplots with no vegetation records |
| `check_unidentified_species(raw_data)` | Species marked as "other" |
| `detect_height_outliers(df, threshold)` | >3x or <0.33x median per species |
| `detect_circumference_outliers(df, threshold)` | >4x or <0.25x median per species |
| `detect_suspicious_circumference_by_age(df)` | >50cm at <5yrs OR >300cm at <15yrs |
| `detect_stem_outliers(df, threshold)` | Default >20 stems |
| `check_tall_trees(df, threshold)` | Default >30m (adjustable via sidebar) |
| `check_coverage_only_subplots(raw_data)` | Coverage records but no measurements |

### comparison_utils.py (GT vs DQ)

| Function | Purpose |
|----------|---------|
| `match_plots_by_centroid(gt_gdf, dq_gdf, threshold)` | Match by centroid distance (default 50m) |
| `match_subplots_within_plot(gt, dq)` | Two-pass: strict 20m then fallback unlimited |
| `filter_measured_subplots(gdf)` | Keep subplots where number ≤ measured_subplots |
| `get_tree_count_by_name(raw, plot_key)` | Tree counts by species (woody only) |
| `compare_tree_counts(gt_raw, dq_raw, matches)` | Side-by-side GT vs DQ counts |
| `calculate_plot_validation_summary(gdf)` | Plot invalid if ≥8 subplots invalid |

### session_manager.py

Uses `@st.cache_resource` for shared data store across users. Data keyed by `{partner}_{data_type}`.

| Function | Purpose |
|----------|---------|
| `save_data(data, data_type, partner)` | Save to shared cache with timestamp |
| `load_data(data_type, partner)` | Session state first, then shared cache |
| `has_data(data_type, partner)` | Check availability |
| `clear_all_partner_data(partner)` | Clear GT + DQ for partner |

### cache_utils.py (dev mode only)

Files saved to `data_cache/{partner}_{data_type}.json`. Enabled by `DEV_MODE=true` env var.

## Pages Detail

### app.py - Overview Dashboard
- Credential validation → SurveyCTO API fetch with rate limit handling (417/429/503)
- Data source: API (prod) or API/File toggle (dev mode)
- Overview metrics: total/valid/invalid subplots and plots
- **Measured subplots filtering**: Extracts subplot number from ID regex, compares to `measured_subplots` field
- **Export "Complete Quality Report"**: Multi-sheet Excel with 8 analysis sheets (geometry errors, height/circumference outliers, super tall trees, high stems, suspicious circ vs age, missing vegetation, unknown species)
- **PDF Summary Report**: Calls `generate_summary_pdf_report()` with optional DQ data
- Charts: validation pie, error breakdown bar, timeline, enumerator performance

### _Map_View.py - Interactive Map
- Folium map with valid/invalid subplot polygons (green/red)
- Plot selection dropdown, layer toggle checkboxes
- Popups with area, vertices, enumerator, validation errors

### _Plot_Issues.py - Plot-Level Issues
- Shows plots with ≥8 invalid subplots
- Vegetation validation: flags subplots with ≥10 trees marked "other"
- Expandable per-plot details with tree counting

### _Subplot_Details.py - Vegetation Quality (largest page)
- Adjustable thresholds via sidebar sliders (stems 10-50, tall trees 15-50m, fuzzy match 50-100%)
- Categories: missing vegetation, young/primary/non-primary "other" species, stem outliers, circumference-by-age, species outliers
- Excel/CSV exports per category

### _Enumerator_Performance.py - Per-Enumerator Analysis
- Metrics grouped by enumerator
- Folium maps per enumerator
- Enhanced PDF reports with maps (ReportLab + matplotlib)
- GeoJSON exports

### _Exploratory.py - Deep Dive
- Dependent filters: date → enumerator → plot → subplot
- Species lookup from TSV files
- Supports both GT and DQ data side-by-side

### _Z_GT_DQ_Comparison.py - GT vs DQ Cross-Validation
- Loads DQ data (API or file upload, uses `config.DQ_FORM_ID`)
- Geographic matching: plots by centroid (<50m), subplots two-pass (20m strict, then unlimited)
- Tree count comparison, discrepancy identification

## UI Components

### components.py
- `require_auth()` - Gates pages behind credential validation
- `create_sidebar_filters(gdf)` - Date range + enumerator multiselect, returns filtered GDF
- `show_metrics_row(summary)` - 4-column metric display
- `show_status_message(summary)` - Color-coded status (green ≥90%, yellow 70-89%, red <70%)
- `get_total_measured_subplots(gdf)` - Uses `measured_subplots` field grouped by `PLOT_KEY`

### charts.py (all Plotly)
- `create_validation_pie_chart()` - Donut chart, green/red
- `create_error_breakdown_chart()` - Horizontal bar, sorted ascending
- `create_enumerator_performance_chart()` - Stacked bar (valid/invalid per enumerator)
- `create_timeline_chart()` - Line chart of submissions over time

## Key Column Schemas

### Subplots GeoDataFrame
```
plot_id, PLOT_KEY, SUBPLOT_KEY, subplot_id
geometry, geom_valid, reasons, empty_geom_detail
enumerator, SubmissionDate, starttime, measured_subplots
area_m2, nr_vertices, length_width_ratio, mrr_ratio
in_radius, in_country, overlap_ids, percentage_overlap
```

### Vegetation DataFrame
```
SUBPLOT_KEY, VEGETATION_KEY, vegetation_type_number
vegetation_type_primary, vegetation_type_youngtree, vegetation_type_woody
woody_species, bamboo_species, banana_species, palm_species, living_fences_species
other_species, language_other_species
tree_height_m, circumference_bh, nr_stems_bh, nr_stems_10cm
tree_year_planted, tree_age, normalized_species, tree_name
coverage_vegetation, coverage_height
```

### Merged Data Dict Keys
```python
raw_data = {
    'plots_subplots': DataFrame,
    'plots_subplots_vegetation': DataFrame,
    'plots_subplots_vegetation_measurements': DataFrame,
    'complete': DataFrame  # all sheets merged
}
```

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| streamlit | 1.50.0 | Web framework |
| pandas | 2.1.3 | Data manipulation |
| geopandas | 0.14.1 | Geospatial DataFrames |
| shapely | 2.0.2 | Geometric operations |
| pyproj | 3.6.1 | CRS transformations |
| folium | 0.15.1 | Interactive maps |
| plotly | 5.18.0 | Charts |
| reportlab | ≥3.6.0 | PDF generation |
| scikit-learn | ≥1.3.0 | DBSCAN, regression outliers |
| rapidfuzz | ≥3.0.0 | Fuzzy species matching |
| anthropic | ≥0.18.0 | Claude API (species classifier) |
| openpyxl | 3.1.2 | Excel I/O |

## Environment & Config

- `DEV_MODE=true` env var → enables local caching + file upload toggle
- `.streamlit/config.toml`: port 8080, max upload 500MB, XSRF enabled, headless
- `.streamlit/secrets.toml`: SurveyCTO server name and default form ID
- CRS: **WGS84 (EPSG:4326)** everywhere; UTM used for area/distance calculations

## Common Development Tasks

### Adding a new partner
1. Add entry to `PARTNERS` dict in `config.py` with: country, country_iso3, gtID, dqID, map_center, min_plot_area, max_plot_area, start_date, description
2. Optionally add species TSV files in `data/species/{PARTNER}/`
3. Partner auto-detected from URL `?partner=CODE`

### Adding a validation rule
1. **Geometry:** Add to `GeometryValidator` in `core/gt_check_functions.py`, update `collect_reasons_subplot()`
2. **Vegetation:** Add function in `utils/vegetation_validation.py`
3. **Display:** Update relevant page to show the new validation
4. **Export:** Add sheet to quality report in `app.py` (lines 809-1826)

### Modifying exports
- GeoJSON/CSV/Excel helpers: `utils/export_helpers.py`
- PDF reports: `utils/pdf_summary_report.py` (1487 lines, ReportLab-based)
- Quality Report Excel: `app.py` lines 809-1826 (8 analysis sheets)

### Rate limiting from SurveyCTO
- 417: Parse wait time from error message (regex)
- 429: Generic 60-second wait
- 503: Service temporarily unavailable (60-120s wait)
- All handled in `app.py` `fetch_surveycto_data()` (lines 118-224)

## Design Decisions & Gotchas

1. **Global config state**: `config.py` uses module-level globals set by `refresh_partner_config()`. Must be called at app startup.
2. **Measured subplots filtering**: Subplot number extracted via regex from `subplot_id` (e.g., "PLOT-001/sub_plot[3]" → 3), compared to `measured_subplots` field. Unmeasured subplots excluded from metrics.
3. **GPS accuracy=0 handling**: Configurable via `accuracy_zero_valid` session state flag. When False, zero-accuracy GPS readings are dropped.
4. **Geometry fixing performance**: Single `.apply()` call for all 13 fix steps instead of 13 separate passes.
5. **Overlap validation**: Uses buffer(-5m) to avoid touching boundaries being counted as overlaps.
6. **UTM caching**: Transformer objects cached by (zone, south, inverse) tuple to avoid recreation per geometry.
7. **Export column format**: All quality report sheets use: Submitted Date | Plot ID | Subplot ID | KEY | Data Collector Name | Issue Type | Issue Description | Notes | Clarification.
8. **Authentication gate**: `require_auth()` in `ui/components.py` checks `credentials_validated` session state. All pages redirect to home if not authenticated.
9. **Multi-user support**: `session_manager.py` uses `@st.cache_resource` for shared data across Streamlit sessions, keyed by partner.

## Git Workflow

- **main** - Production branch
- **version-two** - Active development branch
