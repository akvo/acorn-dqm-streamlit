# High-Level Design: ACORN DQM Streamlit

**Version:** 2.0 (branch: version-two)  
**Date:** 2026-04-28  
**Purpose:** Ground Truth Data Quality Management for ACORN carbon credit tree/vegetation surveys

---

## 1. System Purpose

ACORN-DQM validates geospatial and vegetation data submitted by field enumerators via SurveyCTO forms. It supports 10 partner organisations across 7 countries. The platform checks both **Ground Truth (GT)** data (primary field survey) and **Data Quality (DQ)** data (independent verification survey) and cross-validates them.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Browser / User                       │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│              Streamlit Web App (port 8080)                │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ app.py   │  │ Map View │  │Subplot   │  │Enum.   │  │
│  │(Overview)│  │          │  │Details   │  │Perf.   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───┬────┘  │
│       │             │              │              │       │
│  ┌────▼─────────────▼──────────────▼──────────────▼───┐  │
│  │              UI Layer (ui/)                         │  │
│  │  components.py (auth gate, filters, metrics)        │  │
│  │  charts.py (Plotly visualisations)                  │  │
│  └────────────────────┬────────────────────────────────┘  │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────────┐  │
│  │            Utils / Business Logic (utils/)           │  │
│  │  data_processor.py     data_merge_utils.py           │  │
│  │  vegetation_validation.py  comparison_utils.py       │  │
│  │  export_helpers.py     pdf_summary_report.py         │  │
│  └────────────────────┬────────────────────────────────┘  │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────────┐  │
│  │            Core Geometry Engine (core/)              │  │
│  │  gt_check_functions.py                               │  │
│  │  GeometryFixer → GeometryValidator → GeoDataFrame    │  │
│  └────────────────────┬────────────────────────────────┘  │
│                       │                                  │
│  ┌────────────────────▼────────────────────────────────┐  │
│  │            Config & State (config.py)                │  │
│  │  PARTNERS dict, thresholds, module-level globals     │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  SurveyCTO REST API            Local Excel Upload
  (JSON response)               (.xlsx, up to 500 MB)
```

---

## 3. Partner & Configuration System

### 3.1 Multi-Partner Design

The platform is **single-deployment, multi-tenant** — one Streamlit instance serves all partners, differentiated by URL query parameter.

**Partner selection priority (highest → lowest):**
1. `st.session_state.partner` (set during navigation)
2. URL query param `?partner=PARTNERCODE`
3. Default: `COMACO`

```
http://app.example.com/?partner=SOLK   →  Solidaridad Kenya
http://app.example.com/?partner=IORA   →  IORA India
```

### 3.2 Partner Registry (`config.py`)

| Partner | Country | ISO3 |
|---------|---------|------|
| RAV | Vietnam | VNM |
| SOLK | Kenya | KEN |
| TFK | Kenya | KEN |
| FA | Kenya | KEN |
| INTELLECAP | India | IND |
| IORA | India (Meghalaya) | IND |
| AFOCO | Kyrgyzstan | KGZ |
| COMACO | Zambia | ZMB |
| AFEC | India (AP) | IND |
| SOLU | Uganda | UGA |

Each entry contains: `country`, `country_iso3`, `gtID`, `dqID` (SurveyCTO form IDs), `min_plot_area`, `max_plot_area`, `map_center`, `start_date`, `description`.

### 3.3 Global Config State Pattern

`config.refresh_partner_config()` sets module-level globals via `global` keyword. Must be called at app startup on every page. Globals include: `PARTNER`, `COUNTRY`, `COUNTRY_ISO3`, `GT_FORM_ID`, `DQ_FORM_ID`, `PARTNER_CONFIG`, `MAP_CENTER`, `APP_TITLE`.

---

## 4. Data Ingestion Layer

### 4.1 Two Ingestion Paths

```
Path A: SurveyCTO REST API
  ├── Credentials validated (username/password)
  ├── fetch_surveycto_data(form_id, server, user, pw)
  ├── Rate-limit handling:
  │     417 → parse wait_seconds from error body (regex)
  │     429 → fixed 60s retry
  │     503 → 60–120s retry
  └── JSON → read_json_to_sheets() → 5-sheet dict

Path B: Excel File Upload (.xlsx, max 500 MB)
  └── read_excel_all_sheets() → 5-sheet dict
```

Both paths produce an identical **5-sheet dictionary**:

| Key | Contents |
|-----|----------|
| `plots` | Plot-level records |
| `subplots` | Subplot GPS polygons |
| `vegetation` | Species + measurement records |
| `measurements` | Numeric measurements |
| `circumference` | Circumference at breast height data |

### 4.2 Hierarchical Merge (`data_processor.py: merge_all_data`)

```
plots
  └── LEFT JOIN subplots        → plots_subplots
        └── LEFT JOIN vegetation → plots_subplots_vegetation
              └── LEFT JOIN measurements → plots_subplots_vegetation_measurements
                    └── LEFT JOIN circumference → complete
```

Output stored as `raw_data` dict inside `st.session_state.data`.

---

## 5. Geometry Processing Pipeline (`core/gt_check_functions.py`)

### 5.1 GPS String Parsing

`coordinates_from_vertices(vertices_str, accuracy_m=10)`

- Splits SurveyCTO GPS string (space-separated: `lat lon alt accuracy` per point)
- Filters: accuracy > threshold → dropped
- Returns list of `WGS84Point` frozen dataclasses

`geom_from_scto_str(row, column, accuracy_m=10)`

- Requires ≥ 3 valid coordinate points
- Requires ≥ 80% of points to be valid (tolerance for bad GPS readings)
- Returns Shapely `Polygon` + metadata columns

### 5.2 Geometry Fixing (`GeometryFixer`) — 13-Step Single-Pass Pipeline

All 13 steps execute in one `.apply()` call for performance. Steps run sequentially; each step records whether it caused the geometry to become empty (`became_empty_at` column).

| Step | Fix Applied |
|------|------------|
| 1 | Remove duplicate consecutive vertices |
| 2 | Fix self-intersections → convex hull |
| 3 | Fix winding order → `shapely.orient()` |
| 4 | Fix winding with `geojson_rewind` |
| 5 | Fix with zero-width buffer (`buffer(0)`) |
| 6 | Convert to 2D (strip Z coordinates) |
| 7 | Replace degenerate types (Point/LineString → empty) |
| 8 | Replace MultiPolygons → keep largest part if >90% of total area |
| 9 | Simplify with 0.1m tolerance |
| 10 | Replace zero-area polygons |
| 11 | Replace None geometries |
| 12 | Replace out-of-bounds (lat ∉ [-80,84] or lon ∉ [-180,180]) |
| 13 | Replace invalid → attempt `buffer(0)`; if still invalid → `representative_point()` |

### 5.3 Geometry Validation (`GeometryValidator`)

After fixing, each subplot geometry is validated. Validation adds boolean flag columns:

| Column | Rule |
|--------|------|
| `area_m2` | Computed (geodesic or projected UTM) |
| `nr_vertices` | Count of polygon exterior vertices |
| `nr_vertices_too_small` | `nr_vertices < 3` |
| `length_width_ratio_too_big` | Aspect ratio of MRR > `THRESHOLD_LENGTH_WIDTH` (2.0) |
| `protruding_ratio_too_big` | Protruding ratio of MRR > `THRESHOLD_PROTRUDING_RATIO` (1.55) |
| `in_radius` | Subplot centroid within 40m of plot centroid |
| `in_country` | Geometry within expected country boundary |
| `duplicate_id` | Repeated subplot ID |
| `overlap_ids` | Overlapping sibling subplots (uses -5m inner buffer to avoid false positives at touching edges) |
| `percentage_overlap` | Fraction of area overlapping with sibling subplots |

### 5.4 Reason Collection & Final Status

`collect_reasons_subplot(row, min_area, max_area)` — aggregates all failing validation flags into a semicolon-separated `reasons` string.

`assign_geom_valid_geojson(gdf, min, max)` — final step that adds:
- `reasons`: semicolon-joined failure reasons
- `geom_valid`: `True` if `reasons` is empty
- `geojson`: GeoJSON string for map rendering

### 5.5 Area Calculation & UTM Projection

`geom_to_utm(geom)` converts WGS84 geometry to the appropriate UTM projection for accurate metric area/distance calculations.

---

## 6. Validation Thresholds

### 6.1 Global Thresholds (`config.py`)

| Threshold | Value | Constant |
|-----------|-------|----------|
| Subplot min area | 450 m² | `MIN_SUBPLOT_AREA_SIZE` |
| Subplot max area | 750 m² | `MAX_SUBPLOT_AREA_SIZE` |
| Plot min area | 1,000 m² | `MIN_GT_PLOT_AREA_SIZE` (partner default) |
| Plot max area | 300,000 m² | `MAX_GT_PLOT_AREA_SIZE` (partner default) |
| Max polygon vertices | 4 | `MAX_VERTICES` |
| GPS accuracy threshold | ≤ 10 m | `GPS_ACCURACY_THRESHOLD` |
| Subplot proximity to plot | ≤ 40 m | `THRESHOLD_WITHIN_RADIUS` |
| Plot proximity | ≤ 200 m | `THRESHOLD_WITHIN_RADIUS_PLOT` |
| Aspect ratio limit | 2.0 | `THRESHOLD_LENGTH_WIDTH` |
| Protruding ratio limit | 1.55 | `THRESHOLD_PROTRUDING_RATIO` |
| Invalid subplots → bad plot | ≥ 8 | Hardcoded in `app.py:770` |

### 6.2 User-Adjustable Thresholds (sidebar sliders, `_Subplot_Details.py`)

| Parameter | Range | Default |
|-----------|-------|---------|
| Max stems | 10–50 | 20 |
| Tall tree height | 15–50 m | 30 m |
| Fuzzy species match | 50–100% | 80% |
| Circumference outlier multiplier | configurable | 4× |

---

## 7. Vegetation Validation (`utils/vegetation_validation.py`, `utils/data_merge_utils.py`)

### 7.1 Check Categories

| Check | Logic |
|-------|-------|
| **Missing vegetation** | Set diff: `all_subplots - subplots_with_vegetation_records` |
| **Unidentified species** | `vegetation_type = "other"` with no resolution |
| **Height outliers** | > 3× or < 0.33× median per species group |
| **Circumference outliers** | > 4× or < 0.25× median per species group |
| **Suspicious circumference by age** | > 50 cm at < 5 years OR > 300 cm at < 15 years |
| **Stem outliers** | `nr_stems_bh > threshold` (default 20) |
| **Tall trees** | `tree_height_m > threshold` (default 30 m) |
| **Coverage-only subplots** | Has coverage record but no measurement record |

### 7.2 Species Resolution Pipeline (`data_merge_utils.py`)

```
Raw species field (e.g. "woody_species")
  ↓
add_tree_name_column() — priority cascade:
    woody → bamboo → banana → palm → living_fences → "Unknown"
  ↓
load_species_lookup(partner)
    reads data/species/{PARTNER}/{type}_species.tsv
    returns (scientific_to_label dict, common_to_label dict)
  ↓
normalize_species_name(name, lookup)
    exact match → scientific name → common name → fuzzy match (rapidfuzz)
  ↓
normalized_species column
```

### 7.3 Outlier Detection Methods

Three complementary methods available:

| Method | Function | Approach |
|--------|----------|----------|
| IQR/Median | `detect_species_outliers()` | > 4× or < 0.25× median per species |
| DBSCAN | `detect_multivariate_outliers_dbscan()` | Clustering on [age, metric] per species; noise points = outliers |
| Regression | `detect_regression_outliers()` | Linear regression residuals per species group |

Age is extracted by `extract_year_from_planted()` which handles: Unix epoch (ms/s), 4-digit year strings, and ISO date strings.

---

## 8. GT vs DQ Cross-Validation (`utils/comparison_utils.py`, `pages/_Z_GT_DQ_Comparison.py`)

### 8.1 Purpose

Independently collected DQ data is matched against GT data geographically to detect discrepancies in tree counts and subplot validation.

### 8.2 Plot Matching

`match_plots_by_centroid(gt_gdf, dq_gdf, threshold=50m)`

- For each DQ plot, find GT plot with minimum centroid distance (Haversine formula)
- Match accepted if distance < 50 m
- Returns `[gt_plot_key, dq_plot_key, distance_m]`

### 8.3 Subplot Matching (Two-Pass)

`match_subplots_within_plot(gt, dq)`

- **Pass 1 (strict):** Match by centroid distance < 20 m
- **Pass 2 (fallback):** For unmatched subplots, use nearest regardless of distance
- Prevents unmatched subplots from inflating discrepancy counts

### 8.4 Tree Count Comparison

`compare_tree_counts(gt_raw, dq_raw, matches)`

- Groups by species (`tree_name`) per matched plot pair
- Side-by-side GT count vs DQ count
- Flags discrepancies

---

## 9. UI Pages

| Page | File | Key Function |
|------|------|-------------|
| Overview Dashboard | `app.py` | Data ingestion, summary metrics, export trigger |
| Map View | `pages/_Map_View.py` | Folium map with valid/invalid polygons, popups |
| Plot Issues | `pages/_Plot_Issues.py` | Plots with ≥ 8 invalid subplots |
| Subplot Details | `pages/_Subplot_Details.py` | All vegetation quality checks |
| Enumerator Performance | `pages/_Enumerator_Performance.py` | Per-enumerator metrics, PDF/GeoJSON export |
| Exploratory | `pages/_Exploratory.py` | Deep-dive GT+DQ drill-down |
| GT/DQ Comparison | `pages/_Z_GT_DQ_Comparison.py` | Cross-validation of GT vs DQ |

### 9.1 Auth Gate

`require_auth()` in `ui/components.py` checks `credentials_validated`. All pages call this on load; unauthenticated users are redirected to `app.py`.

### 9.2 Shared Sidebar Filters

`create_sidebar_filters(gdf)` provides date range + enumerator multiselect on every page. Filters persist in session state across page navigation.

---

## 10. Export & Reporting

### 10.1 Quality Report (Excel, 8 sheets)

Generated in `app.py` (lines 809–1826). Each sheet follows the standard column format:

> Submitted Date | Plot ID | Subplot ID | KEY | Data Collector Name | Issue Type | Issue Description | Notes | Clarification

| Sheet | Content |
|-------|---------|
| Geometry Errors | Subplots with geometry validation failures |
| Height Outliers | Trees with anomalous height values |
| Circumference Outliers | Trees with anomalous circumference values |
| Super Tall Trees | Trees exceeding height threshold |
| High Stem Count | Subplots with excessive stem counts |
| Suspicious Circ. by Age | Circumference/age combinations flagged as unlikely |
| Missing Vegetation | Subplots with no vegetation records |
| Unknown Species | Species recorded as "other" |

### 10.2 PDF Summary Report (`utils/pdf_summary_report.py`)

ReportLab-based, multi-page. Generated by `generate_summary_pdf_report()`. Optionally includes DQ data sections. Maps embedded using matplotlib at `PDF_MAP_DPI=50` (optimised for speed).

### 10.3 GeoJSON / CSV Exports

Lightweight helpers in `utils/export_helpers.py` for per-enumerator and per-category exports.

---

## 11. Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Web Framework | Streamlit | 1.50.0 |
| Tabular Data | Pandas | 2.1.3 |
| Geospatial | GeoPandas | 0.14.1 |
| Geometry Engine | Shapely | 2.0.2 |
| CRS Transforms | PyProj | 3.6.1 |
| Interactive Maps | Folium | 0.15.1 |
| Charts | Plotly | 5.18.0 |
| PDF Generation | ReportLab | ≥ 3.6.0 |
| ML / Outliers | scikit-learn | ≥ 1.3.0 |
| Fuzzy Matching | rapidfuzz | ≥ 3.0.0 |
| Excel I/O | openpyxl | 3.1.2 |
| CRS Standard | WGS84 | EPSG:4326 |

---

## 12. Key Design Decisions & Constraints

| Decision | Rationale |
|----------|-----------|
| Module-level globals in `config.py` | Streamlit's execution model reruns on every interaction; globals set by `refresh_partner_config()` provide consistent per-request config |
| Single-pass 13-step geometry fixer | One `.apply()` call instead of 13 is ~13× faster on large datasets |
| -5 m inner buffer for overlap detection | Prevents shared boundary edges from falsely triggering overlap validation |
| Subplot number regex from ID | `PLOT-001/sub_plot[3]` → 3; compared to `measured_subplots` to exclude unmeasured subplots from metrics |
| Two-pass subplot matching (20m then unlimited) | Prevents unmatched subplots from artificially inflating DQ discrepancy counts |
