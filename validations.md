# Data Quality Validations

This document explains the quality checks performed on field-collected plot and subplot data. These validations help ensure that the geographic boundaries recorded by field enumerators are accurate and usable for vegetation analysis.



## Validation Checks

### 1. Shape Size (Area)

**What it checks:** Whether the recorded area is within expected bounds.

**Why it matters:** A subplot that's too small may not capture enough trees for meaningful analysis. One that's too large might overlap with neighboring areas or indicate the enumerator walked an incorrect path.

| Level | Minimum Size | Maximum Size |
|-------|--------------|--------------|
| Subplot | 450 m² | 750 m² |
| Plot | 1,000 m² | 300,000 m² |

**Failure reasons:**
- "Plot too small" — The recorded area is smaller than the minimum
- "Plot too big" — The recorded area exceeds the maximum

---

### 2. GPS Accuracy

**What it checks:** The precision of each GPS point recorded.

**Why it matters:** GPS devices report how confident they are about each location. Points with poor accuracy (high uncertainty) can distort the shape of the polygon. We exclude points where the GPS was unsure of the location.

| Threshold | Value |
|-----------|-------|
| Maximum acceptable uncertainty | 10 meters |

**What happens:** Points with accuracy worse than 10 meters are dropped. If too many points are dropped, the shape cannot be formed.

**Failure reasons:**
- "No GPS coordinates were recorded" — The device didn't capture any location data
- Empty geometry with details like "15 collected, 12 dropped. 10 >10m, 2 =0m" — Most points had poor accuracy

---

### 3. Shape Compactness (Within Radius)

**What it checks:** Whether all corners of the shape are within a reasonable distance from its center.

**Why it matters:** A well-formed subplot or plot should be relatively compact. If corners are too far from the center, it might indicate:
- The enumerator wandered off course
- GPS errors pushed some points far from their true location
- The wrong area was measured

| Level | Maximum Distance from Center |
|-------|------------------------------|
| Subplot | 40 meters |
| Plot | 200 meters |

**Failure reason:**
- "Plot outside of radius" — One or more corners are too far from the center point

---

### 4. Shape Regularity (Protruding Ratio)

**What it checks:** Whether the shape is reasonably regular or has unusual spikes and protrusions.

**Why it matters:** Field plots should generally be simple shapes (roughly rectangular or square). A shape with long narrow extensions or sharp protrusions often indicates GPS errors or walking mistakes.

This is measured by comparing the actual shape to the smallest rectangle that could contain it. If the rectangle is much larger than the shape itself, the shape has irregular protrusions.

| Threshold | Value |
|-----------|-------|
| Maximum ratio | 1.55 |

A perfect rectangle has a ratio of 1.0. Higher values indicate more irregular shapes.

**Failure reason:**
- "Plot is protruding" — The shape has irregular extensions or spikes

---

### 5. Elongation (Length-to-Width Ratio)

**What it checks:** Whether the shape is too long and narrow.

**Why it matters:** Subplots and plots should be roughly square or slightly rectangular. A very elongated shape (like a thin strip) is usually a sign of:
- Walking along a path instead of around an area
- GPS drift causing points to cluster along one direction
- Incorrect measurement technique

| Threshold | Value |
|-----------|-------|
| Maximum length-to-width ratio | 2.0 |

A square has a ratio of 1.0. A rectangle twice as long as it is wide has a ratio of 2.0.

---

### 6. Minimum Points (Vertex Count)

**What it checks:** Whether the shape has enough corner points to form a valid polygon.

**Why it matters:** A polygon needs at least 4 distinct points to form a closed shape (3 corners plus returning to the start). Shapes with fewer points are invalid and cannot represent a real area.

| Threshold | Value |
|-----------|-------|
| Minimum vertices required | More than 4 points |

**Failure reason:**
- "Nr vertices <= 3" — Not enough points to form a valid shape

---

### 7. Overlapping Areas

**What it checks:** Whether different subplots or plots overlap with each other.

**Why it matters:** Each subplot should represent a unique area. Significant overlap between areas suggests:
- The same area was measured twice
- Boundaries were recorded incorrectly
- GPS errors caused shapes to expand into neighboring areas

| Threshold | Value |
|-----------|-------|
| Maximum acceptable overlap | 50% of the smaller area |

A small buffer (5 meters) is applied before checking, so minor edge touching is ignored.

**Failure reason:**
- "Overlapping polygons" — This area significantly overlaps with another recorded area

---

### 8. Geographic Bounds

**What it checks:** Whether the coordinates are within valid Earth locations.

**Why it matters:** Sometimes GPS errors produce impossible coordinates (outside the valid range for latitude and longitude). These records cannot represent real locations.

| Coordinate | Valid Range |
|------------|-------------|
| Latitude | -80° to 84° |
| Longitude | -180° to 180° |

**Failure reason:**
- "Empty geometry" — Coordinates were outside valid bounds

---

### 9. Geometry Validity

**What it checks:** Whether the shape is mathematically valid (no self-intersections, proper closure).

**Why it matters:** A polygon where the boundary crosses itself (like a figure-8) or doesn't close properly cannot be used for area calculations or mapping.

The system attempts to automatically fix common issues like:
- Self-intersecting boundaries
- Incorrect winding order (clockwise vs counter-clockwise)
- Duplicate points

**Failure reasons:**
- "Invalid geometry" — The shape has structural problems that couldn't be fixed
- "Empty geometry" — The shape collapsed during fixing (e.g., all points were on a single line)
- "Geometry missing" — No shape data was recorded

---

## Summary of Failure Reasons

| Failure Reason | What It Means |
|----------------|---------------|
| Plot too small | Area is below the minimum threshold |
| Plot too big | Area exceeds the maximum threshold |
| Plot outside of radius | Shape is too spread out from its center |
| Plot is protruding | Shape has irregular spikes or extensions |
| Nr vertices <= 3 | Not enough points to form a valid polygon |
| Overlapping polygons | Significant overlap with another recorded area |
| Invalid geometry | Shape has structural problems (self-intersection, etc.) |
| Empty geometry | No valid shape could be created from the GPS data |
| Geometry missing | No GPS data was recorded |
| Boundary not in country | Shape falls outside the expected country boundaries |
| Duplicate plot id | Same identifier used for multiple records |

