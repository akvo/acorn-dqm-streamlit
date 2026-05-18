# ACORN-DQM Streamlit — Onboarding Guide

**Platform:** Ground Truth Data Quality Management for ACORN carbon credit tree/vegetation surveys
**Stack:** Streamlit · GeoPandas · Shapely · Folium · Plotly · SurveyCTO

---

## 1. What This Platform Does

Field enumerators walk the boundary of a plot or subplot with a GPS device. SurveyCTO records each corner as a GPS point. This platform ingests those records and answers two questions:

1. **Is the recorded polygon geometrically valid?** (Shape Quality)
2. **Are the vegetation measurements plausible?** (Vegetation Quality)

As of now it supports **10 partner organisations** across 7 countries (Kenya, India, Zambia, Uganda, Kyrgyzstan, Vietnam, and more). Each partner runs independent GT field campaigns; this single app serves them all via a URL query parameter (`?partner=SOLK`, `?partner=COMACO`, etc.).

---

## 2. Core Data Model

Data is hierarchical. Every level has a unique KEY that cascades downward.

```
PLOT  (1 farm boundary)
  └── SUBPLOT  (up to N measurement areas within a plot)
        └── VEGETATION  (one row per tree/plant observed)
              └── MEASUREMENTS  (numeric readings: height, circumference, stems)
                    └── CIRCUMFERENCE  (circumference at breast height detail)
```

### Key Terminology

| Term | Meaning |
|------|---------|
| **Plot** | The outer farm/land boundary recorded by the enumerator |
| **Subplot** | A ~25m × 25m quadrat inside the plot where trees are counted and measured |
| **GT (Ground Truth)** | Primary field survey data collected by the project's enumerator |
| **DQ (Data Quality)** | Independent verification survey of the same plots by a second enumerator |
| **Enumerator** | The field data collector |
| **PLOT_KEY / SUBPLOT_KEY / VEGETATION_KEY** | Composite surrogate keys used for joining across sheets |

### How Data Is Stored

Each SurveyCTO form produces 5 sheets when exported. The platform reads these and joins them hierarchically:

| Sheet | Contents |
|-------|---------|
| `plots` | Plot-level GPS polygon, enumerator, date |
| `subplots` | Subplot GPS polygon + metadata (measured_subplots count) |
| `vegetation` | Species recorded per subplot (one row per tree/plant) |
| `measurements` | Height, circumference, stems per vegetation record |
| `circumference` | Circumference at breast height detail |

**Join chain:** `plots → subplots → vegetation → measurements → circumference`
All joins are LEFT joins so a missing subordinate record never drops the parent.

---

## 3. Data Ingestion

Two paths produce identical output:

```
Path A: SurveyCTO REST API  →  JSON  →  read_json_to_sheets()
Path B (dev mode only): Excel upload (.xlsx)  →  read_excel_all_sheets()
                              ↓
                    merge_all_data()  →  raw_data dict
                              ↓
               Geometry Processing Pipeline
                              ↓
                   st.session_state.data
```

**Rate limiting** from SurveyCTO is handled automatically:
- HTTP 417 → parses wait time from the error body and retries
- HTTP 429 → waits 60 seconds then retries
- HTTP 503 → waits 60–120 seconds then retries

**GPS accuracy filtering** — every GPS point has a reported accuracy in metres. Points with accuracy worse than 10 m are dropped before building the polygon. You can configure whether accuracy = 0 is treated as valid or invalid via the toggle in the sidebar.

---

## 4. Geometry Processing Pipeline

This is the heart of the platform. It transforms raw GPS strings into validated polygons.

### Step 1 — Parse GPS String (`coordinates_from_vertices`)

SurveyCTO GPS strings look like:
```
-1.2345 36.8765 1600 4.5 -1.2350 36.8770 1601 3.2 ...
```
Each group of four numbers is one GPS point: `latitude longitude altitude accuracy_m`.

Points are filtered by accuracy threshold (≤ 10 m). A polygon is formed only if:
- At least 3 valid points remain
- At least 80% of the original points passed the accuracy filter

### Step 2 — Geometry Fixing (`GeometryFixer` — 13 Steps)

Many GPS-recorded polygons have minor geometric defects. The fixer attempts to repair them in a single pass:

| Step | Fix |
|------|-----|
| 1 | Remove duplicate consecutive vertices |
| 2 | Fix self-intersections → convex hull |
| 3 | Fix winding order → `shapely.orient()` |
| 4 | Fix winding with `geojson_rewind` |
| 5 | Fix with zero-width buffer (`buffer(0)`) |
| 6 | Convert to 2D (strip Z altitude coordinates) |
| 7 | Replace degenerate types (Point or LineString → empty) |
| 8 | Replace MultiPolygons → keep largest part if it is > 90% of total area |
| 9 | Simplify with 0.1 m tolerance |
| 10 | Replace zero-area polygons |
| 11 | Replace None geometries |
| 12 | Replace out-of-bounds geometries (lat outside ±80°, lon outside ±180°) |
| 13 | Replace still-invalid → try `buffer(0)`; if still bad → `representative_point()` |

The column `became_empty_at` records which step caused the geometry to become empty, aiding diagnosis.

### Step 3 — Geometry Validation (`GeometryValidator`)

After fixing, each polygon is validated against these rules. Failure adds to the `reasons` column; a subplot with a non-empty `reasons` is marked `geom_valid = False`.

---

## 5. Geometry Validation Rules (Shape Quality)

### 5.1 Area Check

Measured in m² using either **geodesic** (WGS84 ellipsoid) or **UTM-projected** area calculation.

| Level | Min Area | Max Area |
|-------|----------|----------|
| Subplot | 450 m² | 750 m² |
| Plot | 1,000 m² | 300,000 m² (partner default) |

**Failure reasons:** `"Plot too small"`, `"Plot too big"`

**Why these bounds?** A subplot is nominally a 25 m × 25 m quadrat = 625 m². A ± 28% tolerance (450–750 m²) accounts for irregular walking paths.

### 5.2 GPS Accuracy

| Threshold | Value |
|-----------|-------|
| Maximum acceptable uncertainty | 10 m |

GPS readings above this are dropped. If all or most readings are dropped the polygon cannot be built.

**Failure reasons:** `"No GPS coordinates were recorded"`, or a detail string like `"15 collected, 12 dropped. 10 >10m, 2 =0m"`

### 5.3 Shape Compactness — Proximity Radius (Within Radius)

All vertices of the polygon must lie within a radius of the polygon's centroid.

| Level | Max Radius |
|-------|-----------|
| Subplot | 40 m |
| Plot | 200 m |

**Calculation:** For each exterior vertex, the distance to the centroid is computed in UTM projection. If any vertex exceeds the threshold, the subplot fails.

**Failure reason:** `"Plot outside of radius"`

**Why?** A well-formed 625 m² square has a diagonal of ~35 m, so 40 m allows a generous margin. A vertex at 60 m from the centroid almost certainly represents a GPS wander error.

### 5.4 Shape Regularity — Protruding Ratio

Measures how irregular the shape is relative to its bounding rectangle.

```
protruding_ratio = MRR_area / polygon_area
```

Where **MRR** = Minimum Rotated Rectangle (the smallest rectangle that completely contains the polygon, at any rotation angle).

| Threshold | Value | Interpretation |
|-----------|-------|---------------|
| Maximum ratio | 1.55 | A perfect rectangle = 1.0; values above 1.55 indicate significant protrusions |

**Calculation steps:**
1. Convert polygon to UTM (metric units)
2. Compute `minimum_rotated_rectangle` (Shapely)
3. Compute geodesic area of MRR and of the polygon
4. Divide: `mrr_ratio = MRR_area / polygon_area`

**Failure reason:** `"Plot is protruding"`

**Example:** If a subplot has a thin spike pushed out by a single GPS error, the MRR enclosing that spike will be far larger than the actual polygon area.

### 5.5 Shape Elongation — Aspect Ratio (Length-to-Width Ratio)

Measures how elongated the shape is.

```
length_width_ratio = max_edge / min_edge   (of the MRR)
```

| Threshold | Value | Interpretation |
|-----------|-------|---------------|
| Maximum ratio | 2.0 | A square = 1.0; a 2:1 rectangle = 2.0 |

**Calculation:**
1. Compute MRR vertices in UTM or geodesic
2. Measure the two distinct edge lengths of the rectangle
3. Divide longer by shorter

**Failure reason:** `"Elongation ratio too high"` (shown in `reasons` column)

### 5.6 Vertex Count

A polygon needs at least 4 distinct coordinate points to represent a closed shape (3 corners + closing point = 4).

| Threshold | Value |
|-----------|-------|
| Minimum vertices | > 4 (i.e., 5+) |

**Failure reason:** `"Nr vertices <= 3"`

### 5.7 Overlap Detection

Checks whether two sibling subplots (within the same plot) overlap significantly.

**Calculation:**
1. Buffer each subplot by **−5 m** (shrink inward) — this prevents shared edges from triggering a false overlap
2. Run a self-overlay (ST_Intersects style) on the buffered polygons
3. Compute the fraction of the smaller polygon's area that overlaps

| Threshold | Value |
|-----------|-------|
| Max acceptable overlap | 50% of the smaller subplot's area |

**Failure reason:** `"Overlapping polygons"`. Columns `overlap_ids` and `percentage_overlap` identify which subplots overlap and by how much.

### 5.8 Geographic Bounds

| Coordinate | Valid Range |
|------------|------------|
| Latitude | −80° to 84° |
| Longitude | −180° to 180° |

**Failure reason:** `"Empty geometry"` (applied during fixing step 12)

### 5.9 Country Boundary Check

The subplot centroid must fall within the expected country boundary (world administrative boundaries shapefile).

**Failure reason:** `"Boundary not in country"`

### 5.10 Duplicate ID

The same subplot ID must not appear more than once in the dataset.

**Failure reason:** `"Duplicate plot id"`

---

## 6. Plot-Level Validity

A **subplot** is invalid if `geom_valid = False` (any geometry check fails) or if vegetation checks flag it.

A **plot** is invalid if it has **≥ 8 invalid subplots**. This threshold is hardcoded in `app.py` and is the primary trigger for the "Plot Issues" page.

> The _Plot Issues_ page lists only plots that have crossed this threshold — these are the highest-priority cases for field revisit.

---

## 7. Vegetation Types and Coverage

Each row in the vegetation sheet describes one thing observed inside a subplot. The SurveyCTO form separates observations into distinct **vegetation types**, because each type is measured differently and carries different carbon relevance.

### 7.1 Vegetation Type Categories

| Type | SurveyCTO Field | What It Represents |
|------|----------------|-------------------|
| **Woody trees** | `woody_species` | Hardwood or softwood trees with a woody stem; the primary carbon-credit-bearing category |
| **Bamboo** | `bamboo_species` | Bamboo clumps — measured by stem count rather than individual circumference |
| **Banana** | `banana_species` | Banana and plantain plants; included for completeness but have lower carbon relevance |
| **Palm** | `palm_species` | Palm trees (oil palm, date palm, coconut, etc.) — distinct growth form from woody trees |
| **Living fences** | `living_fences_species` | Planted fence lines of woody shrubs or trees; often linear arrangements |

The platform determines the **display name** (`tree_name` column) by checking these fields in priority order: woody → bamboo → banana → palm → living fences. The first non-empty value wins.

### 7.2 Tree Classification within Woody Types

Woody trees are further classified by maturity and growth stage:

| Classification | `vegetation_type_primary` / `vegetation_type_youngtree` | Meaning |
|---------------|--------------------------------------------------------|---------|
| **Primary tree** | `vegetation_type_primary = "yes_primary_group"` | Full-grown canopy tree, the main carbon-bearing observation |
| **Young tree** | `vegetation_type_youngtree = "yes_groupbelow1.3"` | Tree whose stem height is below 1.3 m (breast height); circumference cannot yet be measured at standard height |
| **Non-primary tree** | `vegetation_type_primary = "no"` | Present and measured but not classified as primary canopy |

Young trees are tracked because they represent future carbon stock — they exist in the data but their circumference-by-age rules differ from mature trees.

### 7.3 Coverage Records (Ground Cover)

Not everything in a subplot is a tree. For non-tree vegetation — grass, herbaceous plants, low shrubs, bare ground — enumerators record **coverage estimates** instead of individual measurements.

Two coverage fields are captured:

| Field | Meaning |
|-------|---------|
| `coverage_vegetation` | Percentage of subplot ground area covered by vegetation (grass, herbs, etc.) |
| `coverage_height` | Estimated height of that ground cover (e.g., 0.5 m for knee-high grass) |

**Coverage-only subplots** are a quality flag: if a subplot has coverage data but no individual tree measurement records, it suggests the enumerator may have recorded only ground cover without counting trees. This is distinct from a genuinely tree-free subplot (which would be expected in a heavily grassed area).

The platform flags these in the "Coverage-only subplots" section of the Subplot Details page and exports them to the Quality Report.

### 7.4 The "Other" Species Problem

When an enumerator cannot identify a species in the field, they select `"other"` in the species dropdown. The form then prompts for two additional free-text fields:

| Field | Purpose |
|-------|---------|
| `other_species` | Enumerator's written name (scientific or local) |
| `language_other_species` | The local-language name if the enumerator wrote it in a vernacular |

The platform attempts to resolve these through the species TSV lookup and fuzzy matching (see Section 9). Unresolved "other" entries require botanical follow-up — they cannot be assigned a carbon coefficient until identified.

---

## 8. Vegetation Quality Checks

Vegetation checks are independent of geometry. A subplot can have a valid geometry but still flag vegetation issues.

### 8.1 Missing Vegetation

**Logic:** Set difference — subplots that appear in the subplot sheet but have no rows in the vegetation sheet.

```
missing = all_subplot_IDs  −  subplot_IDs_with_vegetation_records
```

**Displayed in:** Subplot Details page, and exported to the "Missing Vegetation" sheet in the Quality Report.

### 8.2 Unidentified Species ("Other")

Species recorded as `woody_species = "other"` need botanical verification. The platform distinguishes three sub-categories:

| Category | Filter |
|----------|--------|
| Young tree "other" | `vegetation_type_youngtree == "yes_groupbelow1.3"` AND `woody_species == "other"` |
| Primary tree "other" | `vegetation_type_primary == "yes_primary_group"` AND `woody_species == "other"` |
| Non-primary tree "other" | `vegetation_type_primary == "no"` AND `woody_species == "other"` |

When `woody_species == "other"`, the platform also checks `other_species` and `language_other_species` fields for a written name, and attempts to match it against the species TSV reference lists.

**Plot-level flag:** If a subplot has ≥ 10 trees marked as "other", it appears in the Plot Issues page under vegetation errors.

### 8.3 Height Outliers

**Method:** Median-based, per species group.

```
upper outlier: tree_height_m > 3.0 × median_height_for_species
lower outlier: tree_height_m < 0.33 × median_height_for_species
```

The multipliers 3.0 (upper) and 0.33 (lower) are the defaults. They can be adjusted via sidebar sliders.

**Columns added:** `Upper_outliers`, `Lower_outliers` (`"outlier"` / `"ok"`), `median_height`

### 8.4 Circumference Outliers

**Method:** Median-based, per species group.

```
upper outlier: circumference_bh > 4.0 × median_circumference_for_species
lower outlier: circumference_bh < 0.25 × median_circumference_for_species
```

**Columns added:** `Upper_outliers`, `Lower_outliers`, `median_cir`

### 8.5 Suspicious Circumference by Age

A hard biological rule — trees that are biologically too large for their age:

| Rule | Condition |
|------|-----------|
| Young but large | `circumference_bh > 50 cm` AND `tree_age < 5 years` |
| Medium-aged but enormous | `circumference_bh > 300 cm` AND `tree_age < 15 years` |

**Column added:** `suspicious` (boolean)

**Age calculation:** `tree_age = current_year − planting_year`. The planting year is parsed from `tree_year_planted` which can be a 4-digit year, Unix epoch (ms or s), or date string.

### 8.6 High Stem Count

```
high stems: nr_stems_bh > threshold   (default 20, adjustable 10–50 via slider)
```

**Columns added:** `high_stems_bh`, `high_stems_10cm` (boolean)

### 8.7 Super Tall Trees

```
tall tree: tree_height_m > threshold   (default 30 m, adjustable 15–50 m via slider)
```

**Column added:** `tall_tree` (boolean)

### 8.8 Coverage-Only Subplots

Subplots that have coverage data (`coverage_vegetation`, `coverage_height`) but no individual tree measurement records. These indicate an enumerator recorded ground cover but did not measure individual trees. See Section 7.3 for background.

---

## 9. Species Name Resolution Pipeline

Raw species data comes in as SurveyCTO coded values (e.g., `"acacia_senegal"`). The platform resolves these to human-readable labels via partner-specific TSV reference files.

```
data/species/{PARTNER}/
  ├── woody_species.tsv
  ├── bamboo_species.tsv
  ├── banana_species.tsv
  ├── palm_species.tsv
  └── living_fences_species.tsv
```

Each TSV has two columns: `value` (the SurveyCTO code) and `label` (display name, often including common names separated by `/`).

**Resolution priority for `tree_name` column:**
1. `woody_species` (if not "other")
2. `bamboo_species`
3. `banana_species`
4. `palm_species`
5. `living_fences_species`
6. Fallback: `"Unknown"`

**When species = "other":** checks `other_species` and `language_other_species` free-text fields against the TSV lookup using exact match first, then fuzzy match (rapidfuzz, default threshold 80%, adjustable via slider).

> **IORA partner** also has an AI species classifier (`case-specific/iora/species_classifier.py`) that uses Claude Haiku to classify ambiguous vernacular species names.

---

## 10. UI Pages Reference

### Overview Dashboard (`app.py`)

The landing page after login. Shows:
- **Summary metrics:** total / valid / invalid subplots; total / valid / invalid plots
- **Pie chart** — valid vs invalid breakdown
- **Error breakdown bar chart** — count of each failure reason, sorted ascending
- **Timeline chart** — submissions over time
- **Enumerator performance chart** — stacked bar of valid/invalid per enumerator

**Important:** Only **measured subplots** are counted. The subplot ID is parsed with a regex (e.g., `"PLOT-001/sub_plot[3]" → 3`) and compared to the `measured_subplots` field. Subplots with a number higher than `measured_subplots` are excluded from all metrics.

**Status colour coding:**
- Green: ≥ 90% valid
- Yellow: 70–89% valid
- Red: < 70% valid

### Map View (`_Map_View.py`)

Interactive Folium map showing subplot polygons colour-coded:
- **Green** = `geom_valid = True`
- **Red** = `geom_valid = False`

Clicking a polygon opens a popup with: area (m²), vertex count, enumerator name, submission date, and the full list of validation failure reasons. Use the layer toggles to show/hide valid or invalid polygons. Plot boundaries are drawn as a separate layer.

### Plot Issues (`_Plot_Issues.py`)

Shows only plots with **≥ 8 invalid subplots**. These are the highest-priority cases. For each such plot you can expand a panel showing:
- A table of invalid subplots with their `reasons`
- Tree counts by species (for both geometry-invalid and vegetation-invalid subplots)
- Vegetation flag: subplots with ≥ 10 "other" trees

### Subplot Details (`_Subplot_Details.py`)

The most detailed page. Covers every vegetation quality check with expandable sections and per-category Excel/CSV download. Key tables:

| Section | What You See |
|---------|-------------|
| Missing vegetation | Subplots with no vegetation records |
| Young trees — other species | Young trees (`yes_groupbelow1.3`) with unresolved species |
| Primary trees — other species | Primary canopy trees with unresolved species |
| Non-primary trees — other species | Non-primary trees with unresolved species |
| Stem outliers | Trees exceeding the stem count threshold |
| Suspicious circumference by age | Trees biologically too large for their age |
| Height outliers | Trees with anomalous height vs their species median |
| Circumference outliers | Trees with anomalous circumference vs their species median |
| Super tall trees | Trees exceeding the height ceiling |
| Coverage-only subplots | Subplots with coverage data but no individual measurements |

**Sidebar sliders** let analysts adjust thresholds interactively without reloading data.

### Enumerator Performance (`_Enumerator_Performance.py`)

Per-enumerator breakdown: how many subplots each enumerator collected, and their valid/invalid rates. Supports:
- Individual Folium maps per enumerator
- Enhanced PDF report (ReportLab + matplotlib maps)
- GeoJSON export of each enumerator's subplots

### Exploratory (`_Exploratory.py`)

Deep-drill tool using cascading filters: date → enumerator → plot → subplot. Shows both GT and DQ data side by side for a specific subplot, including all raw vegetation records.

### GT vs DQ Comparison (`_Z_GT_DQ_Comparison.py`)

Cross-validates the GT survey against the independent DQ verification survey. See **Section 11** for the full methodology — plot matching, subplot matching, and species comparison are explained in detail there.

---

## 11. GT vs DQ Cross-Validation

The platform supports loading a second, independently-collected **Data Quality (DQ)** dataset and comparing it geographically and ecologically against the primary **Ground Truth (GT)** dataset. The goal is to detect discrepancies — in subplot boundaries, in tree counts, and in species composition — that would indicate data quality issues.

### 11.1 DQ Data Loading

DQ data is collected on a separate SurveyCTO form (each partner has a distinct `dqID` alongside their `gtID` in `config.py`). It is loaded via the GT/DQ Comparison page using the same two ingestion paths as GT data:

- **API mode:** fetches from `https://akvofoundation.surveycto.com/api/v2/forms/data/wide/json/{dqID}`, filtered from the partner's `start_date`
- **File mode (dev only):** accepts an `.xlsx` upload processed through `process_excel_file()`

The resulting data is stored in `st.session_state.dq_data` with the **identical structure** as GT data — same 5-sheet hierarchy, same GeoDataFrame schema, same geometry pipeline. All geometry validation checks (Section 5) are applied to DQ subplots independently.

### 11.2 Plot Matching — Centroid Distance

`match_plots_by_centroid(gt_gdf, dq_gdf, threshold=50m)` in `utils/comparison_utils.py`

For each DQ plot, the algorithm finds the single closest GT plot by centroid distance:

```
distance = Haversine(DQ_centroid, GT_centroid)   # great-circle on WGS84 ellipsoid
match accepted if distance ≤ 50 m
```

**What happens when there is no match:** the DQ plot is placed on the "Unmatched DQ Plots" list at the bottom of the comparison page. It is not paired and does not contribute to species comparison.

Before matching, both GT and DQ subplots are filtered to **measured subplots only** — subplot number (extracted from subplot_id via regex) must be ≤ `measured_subplots` field. This ensures both datasets are compared on equal footing.

**Output:** a DataFrame of `[gt_plot_key, dq_plot_key, distance_m]`.

### 11.3 Subplot Matching — Two-Pass Algorithm

`match_subplots_within_plot(gt_subplots, dq_subplots, strict_threshold=20m)` in `utils/comparison_utils.py`

Within each matched plot pair, subplots are paired by centroid distance in two passes:

**Pass 1 — Strict (≤ 20 m)**

For each DQ subplot, find the nearest GT subplot. Accept the match only if the distance is ≤ 20 m. Both subplots are then marked as matched and removed from the pool. Result tagged `match_type = "strict"`.

**Pass 2 — Fallback (no limit)**

For any DQ subplot that was not matched in Pass 1, find the nearest remaining unmatched GT subplot regardless of distance. Result tagged `match_type = "fallback"`.

The fallback pass exists because GPS drift or slightly different walking paths can push the same subplot centroid beyond 20 m. Without fallback, these subplots would appear as unmatched on both sides, artificially doubling the apparent discrepancy.

**Output table columns:** `GT Subplot | DQ Subplot | Distance (m) | Match Type`

### 11.4 Species and Tree Count Comparison

`get_tree_count_by_name(plot_key, raw_data)` and `compare_tree_counts(gt_dict, dq_dict)` in `utils/comparison_utils.py`

For each matched plot pair, tree counts are aggregated by species name and compared side by side:

**What is counted:**
- Source: `raw_data["plots_subplots_vegetation"]`
- Only records where `non_woody_species` is NULL (i.e., woody trees, bamboo, banana, palm, and living fences)
- Species identity taken in priority order: `woody_species → bamboo_species → banana_species → palm_species → living_fences`
- The column summed is **`vegetation_type_number`** — this is a count field on the form, not a row count. One row can represent multiple stems of the same species.

**Output comparison table:**

| Species | GT Count | DQ Count | Difference |
|---------|----------|----------|-----------|
| Acacia senegal | 15 | 12 | −3 |
| Mangifera indica | 8 | 10 | +2 |
| **TOTAL** | **23** | **22** | **−1** |

Expanding a species row shows subplot-level detail: subplot ID, count, height, and year planted for each individual tree record.

**Important:** there is no automated pass/fail threshold on these differences. The comparison is descriptive — analysts must interpret whether a discrepancy is within acceptable variation or warrants a field revisit.

### 11.5 What the Comparison Page Shows

| UI Element | Content |
|------------|---------|
| DQ geometry summary | Valid/invalid subplot counts and overlap count for the DQ dataset |
| Folium map | GT plots in blue, DQ plots in orange; valid subplots green, invalid red; each layer toggleable independently |
| Matched Plots table | GT Plot ID · DQ Plot ID · Distance · GT Subplots · DQ Subplots · Subplot Diff · GT Trees · DQ Trees · Tree Diff |
| Per-plot expandable panel | Plot metadata (enumerator, date) for both sides · Subplot mapping table · Species comparison table with expandable per-species detail |
| Unmatched DQ plots | DQ plots for which no GT plot was found within 50 m |
| Summary statistics | Average match distance · Total subplot difference · Total tree difference across all matched pairs |

---

## 12. Key Column Reference

### Subplots GeoDataFrame

| Column | Description |
|--------|-------------|
| `plot_id` | Raw plot identifier |
| `PLOT_KEY` | Composite key for joining |
| `SUBPLOT_KEY` | Composite key for joining |
| `subplot_id` | Subplot identifier |
| `geometry` | Shapely Polygon (WGS84) |
| `geom_valid` | `True` if all validations pass |
| `reasons` | Semicolon-separated list of failure reasons |
| `empty_geom_detail` | Detail about why geometry is empty |
| `area_m2` | Computed polygon area in m² |
| `nr_vertices` | Count of exterior polygon vertices |
| `length_width_ratio` | MRR aspect ratio (< 2.0 is valid) |
| `mrr_ratio` | Protruding ratio = MRR_area / polygon_area (< 1.55 is valid) |
| `in_radius` | True if all vertices within 40 m of centroid |
| `in_country` | True if centroid falls within expected country |
| `overlap_ids` | IDs of overlapping sibling subplots |
| `percentage_overlap` | Fraction of area overlapping with siblings |
| `enumerator` | Name of the data collector |
| `SubmissionDate` | When the form was submitted |
| `measured_subplots` | Number of subplots the enumerator recorded |

### Vegetation DataFrame

| Column | Description |
|--------|-------------|
| `SUBPLOT_KEY` | Join key to subplots |
| `VEGETATION_KEY` | Join key to measurements |
| `vegetation_type_primary` | `"yes_primary_group"` or `"no"` |
| `vegetation_type_youngtree` | `"yes_groupbelow1.3"` or other |
| `woody_species` | Coded woody species value |
| `bamboo_species` | Coded bamboo species value |
| `banana_species` | Coded banana species value |
| `palm_species` | Coded palm species value |
| `living_fences_species` | Coded living fence species value |
| `other_species` | Free-text name when species = "other" |
| `language_other_species` | Local-language name for unidentified species |
| `coverage_vegetation` | % ground cover by non-tree vegetation (grass, herbs) |
| `coverage_height` | Estimated height of ground cover (m) |
| `tree_height_m` | Measured height |
| `circumference_bh` | Circumference at breast height (cm) |
| `nr_stems_bh` | Number of stems at breast height |
| `tree_year_planted` | Planting year (epoch, year integer, or date string) |
| `tree_age` | Computed: `current_year − planting_year` |
| `tree_name` | Resolved display name |
| `normalized_species` | Normalized name used for grouping in outlier detection |

---

## 13. Quality Report Export

The "Complete Quality Report" button on the Overview page generates a multi-sheet Excel workbook. Each sheet uses this standard column format:

> **Submitted Date | Plot ID | Subplot ID | KEY | Data Collector Name | Issue Type | Issue Description | Notes | Clarification**

| Sheet | Content |
|-------|---------|
| Geometry Errors | All subplots with `geom_valid = False` and their `reasons` |
| Height Outliers | Trees flagged by the height outlier check |
| Circumference Outliers | Trees flagged by the circumference outlier check |
| Super Tall Trees | Trees exceeding the height ceiling |
| High Stem Count | Trees exceeding the stem count threshold |
| Suspicious Circ. by Age | Trees biologically too large for their age |
| Missing Vegetation | Subplots with no vegetation records |
| Unknown Species | Subplots/trees with species still marked "other" |

A PDF Summary Report is also available, generated with ReportLab and including embedded maps.

---

## 14. Partner Configuration

Partners are registered in `config.py`. To add a new partner:

1. Add an entry to the `PARTNERS` dict with: `country`, `country_iso3`, `gtID`, `dqID`, `min_plot_area`, `max_plot_area`, `map_center`, `map_zoom`, `start_date`, `description`
2. Optionally create `data/species/{PARTNER_CODE}/` with species TSV files

Access the partner via URL: `http://app/?partner=PARTNERCODE`

| Partner Code | Organisation | Country |
|-------------|-------------|---------|
| SOLK | Solidaridad Kenya | Kenya |
| TFK | Trees for Kenya | Kenya |
| FA | Farm Africa | Kenya |
| INTELLECAP | Intellecap | India |
| IORA | IORA | India (Meghalaya) |
| AFOCO | AFOCO | Kyrgyzstan |
| COMACO | COMACO | Zambia |
| AFEC | AFEC | India (Andhra Pradesh) |
| SOLU | Solidaridad Uganda | Uganda |
| RAV | Rainforest Alliance Vietnam | Vietnam |
| AFEC-26 | AFEC 2026 Campaign | India |

---

## 15. Adding a New Validation Rule

### Geometry rule
1. Implement the check in `GeometryValidator` (`core/gt_check_functions.py`)
2. Add the failure string to `collect_reasons_subplot()`
3. Add the column to the Subplots GeoDataFrame schema

### Vegetation rule
1. Add a function to `utils/vegetation_validation.py`
2. Call it from the relevant page (`_Subplot_Details.py` or `_Plot_Issues.py`)
3. Add a sheet to the Quality Report in `app.py` (lines 809–1826)

---

## 16. Quick Diagnostic Cheatsheet

| Symptom | Where to Look |
|---------|--------------|
| Many "Plot too small / too big" | Check partner `min_plot_area` / `max_plot_area` in `config.py` |
| Many "Plot outside of radius" | Check GPS device quality, common on difficult terrain |
| Many "Overlapping polygons" | Enumerators may be re-walking the same area |
| Many "Nr vertices <= 3" | GPS had too many dropped points (accuracy filter too aggressive or bad device) |
| High "other" species count | Field botanist needed; check species TSV coverage for the partner |
| Suspicious circumference by age | Verify tree age data — planting year field may be incorrect |
| Height outliers for one enumerator | Possible data entry error or measurement technique issue |
| DQ vs GT large discrepancy | Run GT/DQ Comparison page; check subplot matching distances |
| Coverage-only subplots flagged | Confirm whether the subplot genuinely has no trees, or if the enumerator skipped measurement |

---

## 17. Advanced Outlier Detection Methods

Available in the Subplot Details page for height, circumference, and stem count. Three methods complement the default median check:

### Method 1 — Median Multiplier (Default)

Simple, interpretable. Flags values beyond N× the per-species median.

### Method 2 — DBSCAN Clustering (`detect_multivariate_outliers_dbscan`)

Uses the density-based clustering algorithm on **[tree_age, metric]** pairs within each species. Points that fall in low-density regions (DBSCAN assigns them cluster = −1) are flagged as outliers.

- Requires at least `min_samples` (default 3) per species
- Features are normalized with `StandardScaler` before clustering
- Useful for catching outliers that are extreme in the combination of age + metric, not just one dimension

### Method 3 — Linear Regression Residuals (`detect_regression_outliers`)

Fits `metric = β₀ + β₁ × tree_age` per species (requires ≥ 10 samples per species). Points beyond **2 standard deviations** from the regression line are flagged as outliers.

- Columns added: `predicted`, `residual`, `valid_range_lower`, `valid_range_upper`, `is_outlier`
- Useful when there is a clear growth trend (older trees expected to be taller/larger)

### Method 4 — Age-Species Group Stats (`detect_age_species_outliers`)

Groups trees by **species + age** and computes group statistics:
- Height/circumference: flags points beyond mean ± 3 standard deviations within the group
- Stem count: flags stems > 4× group median, lower bound = 1

Requires at least 3 trees in a group to compute statistics.
