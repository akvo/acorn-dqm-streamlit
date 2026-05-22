"""
Landing page: partner tiles grid with inline SVG country outline maps.
"""

import json
import os
import streamlit as st
from config import PARTNERS
from rapidfuzz import fuzz, process

_GEOJSON_PATH = os.path.join(os.path.dirname(__file__), "..", "countries.geojson")


@st.cache_data
def _load_country_shapes() -> dict:
    """Load countries.geojson once and return {ADM0_A3: geometry_dict}."""
    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {feat["properties"]["ADM0_A3"]: feat["geometry"] for feat in data["features"]}


def _extract_all_coords(geometry: dict) -> list:
    """Return all exterior-ring (lon, lat) tuples from a Polygon or MultiPolygon."""
    coords = []
    if geometry["type"] == "Polygon":
        for lon, lat in geometry["coordinates"][0]:
            coords.append((lon, lat))
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            for lon, lat in polygon[0]:
                coords.append((lon, lat))
    return coords


def _build_svg_paths(geometry: dict, proj) -> str:
    """Convert GeoJSON geometry to SVG <path> elements using proj(lon, lat) -> (x, y)."""
    parts = []

    def ring_to_d(ring):
        pts = [proj(lon, lat) for lon, lat in ring]
        return "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"

    if geometry["type"] == "Polygon":
        for ring in geometry["coordinates"]:
            parts.append(ring_to_d(ring))
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["coordinates"]:
            for ring in polygon:
                parts.append(ring_to_d(ring))

    d = " ".join(parts)
    return f'<path d="{d}" fill="#a5d6a7" stroke="#2E7D32" stroke-width="0.8" fill-rule="evenodd"/>'


def _render_country_svg(iso3: str, map_center: list, width: int = 256, height: int = 130) -> str:
    """Return an inline SVG showing the country outline with a red dot at map_center."""
    shapes = _load_country_shapes()
    geometry = shapes.get(iso3)

    if geometry is None:
        return f'<div style="width:{width}px;height:{height}px;background:#e8f5e9;"></div>'

    all_coords = _extract_all_coords(geometry)
    if not all_coords:
        return f'<div style="width:{width}px;height:{height}px;background:#e8f5e9;"></div>'

    min_lon = min(c[0] for c in all_coords)
    max_lon = max(c[0] for c in all_coords)
    min_lat = min(c[1] for c in all_coords)
    max_lat = max(c[1] for c in all_coords)

    # 8% padding on each axis
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat
    pad_lon = lon_span * 0.08
    pad_lat = lat_span * 0.08
    min_lon -= pad_lon
    max_lon += pad_lon
    min_lat -= pad_lat
    max_lat += pad_lat
    lon_span = max_lon - min_lon
    lat_span = max_lat - min_lat

    scale = min(width / lon_span, height / lat_span)
    offset_x = (width - lon_span * scale) / 2
    offset_y = (height - lat_span * scale) / 2

    def proj(lon, lat):
        x = offset_x + (lon - min_lon) * scale
        y = offset_y + (max_lat - lat) * scale  # flip Y axis
        return x, y

    paths_svg = _build_svg_paths(geometry, proj)

    # map_center is [lat, lon]
    mx, my = proj(map_center[1], map_center[0])

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:#e8f5e9;display:block;">'
        f"{paths_svg}"
        f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="5" fill="#D32F2F" stroke="#fff" stroke-width="2"/>'
        f"</svg>"
    )


def _render_tile_card(code: str, cfg: dict) -> str:
    svg_html = _render_country_svg(cfg["country_iso3"], cfg["map_center"])

    return f"""
<a href="/?partner={code}" target="_self" style="text-decoration:none;color:inherit;">
  <div style="
    border:1px solid #e0e0e0;
    border-radius:10px;
    overflow:hidden;
    background:#fff;
    box-shadow:0 2px 6px rgba(0,0,0,0.08);
    transition:box-shadow 0.2s;
    margin-bottom:1rem;
    cursor:pointer;
  "
  onmouseover="this.style.boxShadow='0 4px 16px rgba(46,125,50,0.18)'"
  onmouseout="this.style.boxShadow='0 2px 6px rgba(0,0,0,0.08)'"
  >
    <div style="position:relative;height:130px;overflow:hidden;background:#e8f5e9;">
      {svg_html}
      <div style="
        position:absolute;bottom:0;left:0;right:0;
        background:linear-gradient(transparent,rgba(0,0,0,0.35));
        padding:4px 10px;
      ">
        <span style="color:#fff;font-size:0.75rem;font-weight:600;letter-spacing:0.5px;">
          {cfg["country"].upper()}
        </span>
      </div>
    </div>
    <div style="padding:0.85rem 1rem;">
      <div style="
        display:inline-block;
        background:#2E7D32;
        color:#fff;
        font-size:0.7rem;
        font-weight:700;
        letter-spacing:1px;
        padding:2px 8px;
        border-radius:4px;
        margin-bottom:0.4rem;
      ">{code}</div>
      <div style="font-size:0.95rem;font-weight:600;color:#1a1a1a;margin-bottom:0.2rem;line-height:1.3;">
        {cfg["description"]}
      </div>
      <div style="font-size:0.8rem;color:#666;">
        Since {cfg["start_date"]}
      </div>
    </div>
  </div>
</a>
"""


def render_landing_page():
    """Render the partner tiles landing page. Called from app.py when no ?partner= param."""

    st.markdown(
        """
        <div style="background:linear-gradient(90deg,#2E7D32 0%,#388E3C 100%);
                    padding:2rem;border-radius:10px;margin-bottom:1.5rem;">
          <h1 style="color:#fff;margin:0;">🌳 Ground Truth DQM</h1>
          <p style="color:#E8F5E9;margin-top:0.4rem;font-size:1.05em;">
            Select a partner case to begin data quality review
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Case name search
    search_query = st.text_input(
        "Search by case name",
        placeholder="e.g. COMACO, Conservation, Zambia…",
    )

    # Country filter
    countries = sorted({cfg["country"] for cfg in PARTNERS.values()})
    selected_country = st.selectbox(
        "Filter by country",
        options=["All Countries"] + countries,
        index=0,
    )

    # Build combined search strings for fuzzy matching (lowercased for case-insensitive search)
    choices = {f"{code} {cfg['description']} {cfg['country']}".lower(): (code, cfg) for code, cfg in PARTNERS.items()}

    if search_query.strip():
        matches = process.extract(search_query.lower(), choices.keys(), scorer=fuzz.partial_ratio, score_cutoff=90)
        candidate_pairs = [choices[m[0]] for m in matches]
    else:
        candidate_pairs = list(PARTNERS.items())

    filtered = [
        (code, cfg)
        for code, cfg in candidate_pairs
        if selected_country == "All Countries" or cfg["country"] == selected_country
    ]
    filtered.sort(key=lambda item: item[1]["start_date"], reverse=True)

    if not filtered:
        st.info("No partners match your search.")
        return

    # Render in rows of 3
    for row_start in range(0, len(filtered), 3):
        row = filtered[row_start : row_start + 3]
        cols = st.columns(3)
        for col, (code, cfg) in zip(cols, row):
            with col:
                st.markdown(_render_tile_card(code, cfg), unsafe_allow_html=True)
