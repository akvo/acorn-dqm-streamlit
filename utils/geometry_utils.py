"""
Geometry processing and validation utilities
Ported from the notebooks
"""

import geopandas as gpd
import shapely
from shapely.geometry import Polygon, Point
from shapely import transform as shapely_transform
import json
from pyproj import CRS, Geod, Transformer
import utm
import math
from typing import Optional, Union
import pandas as pd


def geom_to_utm(geom: Polygon, crs: str = "EPSG:4326") -> Polygon:
    """
    Convert geometry from WGS84 to UTM projection
    """
    if geom.is_empty:
        return geom

    lon, lat = geom.centroid.x, geom.centroid.y

    if not -80.0 <= lat <= 84.0 or not -180.0 <= lon <= 180.0:
        return Polygon()

    try:
        _, _, zone, _ = utm.from_latlon(lat, lon)
        project = Transformer.from_crs(
            CRS(crs),
            CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0}),
            always_xy=True,
        ).transform
        return shapely_transform(geom, project)
    except:
        return Polygon()


def calculate_area_m2(geom: Polygon, geodesic: bool = True) -> float:
    """
    Calculate area in square meters
    """
    if geom is None or geom.is_empty:
        return 0.0

    if geodesic:
        geod = Geod(ellps="WGS84")
        try:
            return abs(geod.geometry_area_perimeter(geom)[0])
        except:
            return 0.0
    else:
        geom_utm = geom_to_utm(geom)
        return geom_utm.area if not geom_utm.is_empty else 0.0


def length_width_ratio(geom: Polygon, geodesic: bool = True) -> Optional[float]:
    """
    Calculate length to width ratio of minimum rotated rectangle
    """
    if geom.is_empty:
        return None

    try:
        if not geodesic:
            geom = geom_to_utm(geom)

        mbb = geom.minimum_rotated_rectangle
        x, y = mbb.exterior.coords.xy

        if geodesic:
            geod = Geod(ellps="WGS84")
            edge_length = (
                geod.inv(x[0], y[0], x[1], y[1])[2],
                geod.inv(x[1], y[1], x[2], y[2])[2],
            )
        else:
            edge_length = (
                Point(x[0], y[0]).distance(Point(x[1], y[1])),
                Point(x[1], y[1]).distance(Point(x[2], y[2])),
            )

        if min(edge_length) == 0:
            return max(edge_length) / 0.00000001

        return max(edge_length) / min(edge_length)
    except:
        return None


def calculate_minimum_rotated_rectangle_area(
    geom: Polygon, geodesic: bool = True
) -> float:
    """
    Calculate area of minimum rotated rectangle
    """
    if geom.is_empty:
        return 0.0

    try:
        if geodesic:
            geod = Geod(ellps="WGS84")
            return abs(geod.geometry_area_perimeter(geom.minimum_rotated_rectangle)[0])
        else:
            geom_utm = geom_to_utm(geom)
            return geom_utm.minimum_rotated_rectangle.area
    except:
        return 0.0


def calculate_protruding_ratio(geom: Polygon) -> Optional[float]:
    """
    Calculate ratio of minimum rotated rectangle to actual area
    Higher values indicate more protruding/irregular shapes
    """
    if geom.is_empty:
        return None

    try:
        area = calculate_area_m2(geom, geodesic=True)
        mrr_area = calculate_minimum_rotated_rectangle_area(geom, geodesic=True)

        if area == 0:
            return None

        return mrr_area / area
    except:
        return None


def count_vertices(geom: Polygon) -> int:
    """
    Count number of vertices in polygon
    """
    if geom is None or geom.is_empty:
        return 0

    try:
        return len(geom.exterior.coords.xy[0])
    except:
        return 0


def check_within_radius(geom: Polygon, radius: float) -> bool:
    """
    Check if all points are within radius from centroid
    """
    if geom is None or not geom.is_valid:
        return False

    try:
        geom_utm = geom_to_utm(geom)
        if geom_utm.is_empty:
            return False

        circle = geom_utm.centroid.buffer(radius)
        return circle.covers(geom_utm)
    except:
        return False


def fix_geometry(geom: Polygon) -> Polygon:
    """
    Apply various geometry fixes
    """
    if geom is None or geom.is_empty:
        return Polygon()

    if geom.is_valid:
        return geom

    # Try buffer(0)
    try:
        fixed = geom.buffer(0)
        if fixed.is_valid and not fixed.is_empty:
            # Check if area hasn't changed too much
            if geom.area > 0:
                ratio = fixed.area / geom.area
                if 0.995 <= ratio <= 1.005:
                    return fixed
    except:
        pass

    # Try make_valid
    try:
        from shapely.validation import make_valid

        fixed = make_valid(geom)
        if fixed.is_valid:
            return fixed
    except:
        pass

    return geom


def simplify_geometry(geom: Polygon, tolerance: float = 0.1) -> Polygon:
    """
    Simplify geometry while preserving topology
    """
    if geom.is_empty:
        return geom

    try:
        simplified = geom.simplify(tolerance, preserve_topology=True)
        if simplified.is_valid:
            return simplified
    except:
        pass

    return geom


def to_geojson(geom: Polygon, properties: dict = None) -> dict:
    """
    Convert Shapely geometry to GeoJSON format
    """
    if geom is None or geom.is_empty:
        return None

    feature = {
        "type": "Feature",
        "geometry": shapely.geometry.mapping(geom),
        "properties": properties or {},
    }

    return feature


def check_overlap(geom1: Polygon, geom2: Polygon, buffer_m: float = -5) -> tuple:
    """
    Check if two geometries overlap

    Returns:
        (overlaps: bool, overlap_percentage: float)
    """
    if geom1.is_empty or geom2.is_empty:
        return False, 0.0

    try:
        # Convert to UTM for buffering
        geom1_utm = geom_to_utm(geom1).buffer(buffer_m)
        geom2_utm = geom_to_utm(geom2).buffer(buffer_m)

        if geom1_utm.intersects(geom2_utm):
            intersection = geom1_utm.intersection(geom2_utm)
            overlap_area = intersection.area
            min_area = min(geom1_utm.area, geom2_utm.area)

            if min_area > 0:
                overlap_percentage = overlap_area / min_area
                return overlap_percentage > 0.5, overlap_percentage

        return False, 0.0
    except:
        return False, 0.0
