"""
Ground Truth Check Functions
Extracted from AKVO_plot_subplot_check.ipynb
"""

import pandas as pd
import geopandas as gpd
import shapely
from typing import Callable, Optional, Union
import json
import dataclasses as dc
from shapely.lib import ShapelyError
from pyproj import CRS, Geod, Transformer
from shapely.geometry import (
    GeometryCollection,
    MultiPolygon,
    Point,
    Polygon,
    shape,
)
import math
import utm
from geojson_rewind import rewind
from shapely.geometry.polygon import orient


# ============================================
# GEOMETRY TYPE ERROR
# ============================================


class GeometryTypeError(ShapelyError):
    """An error raised when the type of the geometry is unrecognized or inappropriate."""

    pass


# ============================================
# COORDINATE REFERENCE SYSTEM
# ============================================

crs = "EPSG:4326"


# ============================================
# GEOMETRY MAPPING AND TRANSFORMATION
# ============================================


def mapping(ob):
    """Returns a GeoJSON-like mapping from a Geometry"""
    return ob.__geo_interface__


def transform(func, geom):
    """Applies `func` to all coordinates of `geom` and returns a new geometry"""
    if geom.is_empty:
        return geom
    if geom.geom_type in ("Point", "LineString", "LinearRing", "Polygon"):
        try:
            if geom.geom_type in ("Point", "LineString", "LinearRing"):
                return type(geom)(zip(*func(*zip(*geom.coords))))
            elif geom.geom_type == "Polygon":
                shell = type(geom.exterior)(zip(*func(*zip(*geom.exterior.coords))))
                holes = list(
                    type(ring)(zip(*func(*zip(*ring.coords))))
                    for ring in geom.interiors
                )
                return type(geom)(shell, holes)
        except TypeError:
            if geom.geom_type in ("Point", "LineString", "LinearRing"):
                return type(geom)([func(*c) for c in geom.coords])
            elif geom.geom_type == "Polygon":
                shell = type(geom.exterior)([func(*c) for c in geom.exterior.coords])
                holes = list(
                    type(ring)([func(*c) for c in ring.coords])
                    for ring in geom.interiors
                )
                return type(geom)(shell, holes)
    elif geom.geom_type.startswith("Multi") or geom.geom_type == "GeometryCollection":
        return type(geom)([transform(func, part) for part in geom.geoms])
    else:
        raise GeometryTypeError(f"Type {geom.geom_type!r} not recognized")


def round_coordinates(geom, ndigits=2):
    """Round coordinates to specified decimal places"""

    def _round_coords(x, y, z=None):
        x = round(x, ndigits)
        y = round(y, ndigits)
        if z is not None:
            z = round(z, ndigits)
        return [c for c in (x, y, z) if c is not None]

    return transform(_round_coords, geom)


# ============================================
# GEOJSON CONVERSION
# ============================================


def to_geojson(geom: Polygon, id: str = "plot_id") -> Optional[str]:
    """Convert geometry to GeoJSON string"""
    if geom is None:
        return None
    else:
        return json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"id": id},
                        "geometry": mapping(round_coordinates(geom, 7)),
                    }
                ],
            }
        )


# ============================================
# GEOMETRY METRICS
# ============================================


def length_width_ratio(geom: Polygon, geodisic=False) -> Optional[float]:
    """Calculate length to width ratio of minimum rotated rectangle"""
    if geom.is_empty:
        return None

    if not geodisic:
        geom = geom_to_utm(geom)
    mbb = geom.minimum_rotated_rectangle
    x, y = mbb.exterior.coords.xy

    if geodisic:
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
        print("too small width, length is: " + str(max(edge_length)))
        ratio = max(edge_length) / 0.00000000001
    else:
        ratio = max(edge_length) / min(edge_length)
    return ratio


def add_length_width_ratio(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add length/width ratio column to GeoDataFrame"""
    gdf["length_width_ratio"] = gdf.geometry.apply(length_width_ratio, geodisic=True)
    return gdf


def calculate_minimum_rotated_rectangle(
    gdf: gpd.GeoDataFrame, geodesic=False
) -> gpd.GeoDataFrame:
    """Calculate minimum rotated rectangle area"""
    if not geodesic:
        gdf["minimum_rotated_rectangle_m2"] = gdf.geometry.apply(
            lambda x: geom_to_utm(x).minimum_rotated_rectangle.area
        )
    else:
        geod = Geod(ellps="WGS84")
        gdf["minimum_rotated_rectangle_m2"] = gdf.geometry.apply(
            lambda x: abs(geod.geometry_area_perimeter(x.minimum_rotated_rectangle)[0])
        )
    return gdf


def add_protruding_ratio(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add protruding ratio (MRR/area) to GeoDataFrame"""
    gdf_shapes = (
        gdf[~gdf.geometry.isna()]
        .pipe(calculate_area, geodisic=True)
        .pipe(calculate_minimum_rotated_rectangle, geodesic=True)
        .assign(mrr_ratio=lambda x: x.minimum_rotated_rectangle_m2 / x.area_m2)
        .drop(columns=["area_m2", "minimum_rotated_rectangle_m2"])
    )
    return gdf_shapes


def calculate_area(
    gdf: gpd.GeoDataFrame,
    geodisic=False,
    area_field: str = "area_m2",
    geometry_field: str = "geometry",
) -> gpd.GeoDataFrame:
    """Calculate area and add to GeoDataFrame"""
    if len(gdf) == 0:
        gdf[area_field] = None
        gdf[area_field] = gdf[area_field].astype(float)
        return gdf

    if geodisic:
        if gdf.crs.to_epsg() != 4326:
            gdf_4326 = gdf.to_crs(crs)
        else:
            gdf_4326 = gdf

        geod = Geod(ellps="WGS84")
        gdf[area_field] = gdf_4326[geometry_field].apply(
            lambda x: (
                0
                if x is None or pd.isna(x)
                else abs(geod.geometry_area_perimeter(x)[0])
            )
        )
    else:
        if gdf.crs.is_projected:
            gdf[area_field] = gdf[geometry_field].area
        else:
            gdf[area_field] = gdf[geometry_field].apply(
                lambda x: (0 if x is None or pd.isna(x) else geom_to_utm(x).area)
            )

    return gdf


# ============================================
# GEOMETRY FIXING FUNCTIONS
# ============================================


def fix_self_intersecting_square(geom: Polygon) -> Polygon:
    """Fix self-intersecting squares using convex hull"""
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    coords = geom.exterior.coords.xy
    if len(coords[0]) == 5:
        return geom.convex_hull
    return geom


def fix_with_orient(geom: Polygon) -> Polygon:
    """Fix geometry using orient (winding order)"""
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    new_geom = orient(geom)
    if new_geom.is_valid:
        return new_geom
    return geom


def fix_with_rewind(geom: Polygon) -> Polygon:
    """Fix geometry using geojson_rewind"""
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    new_geom = shape(json.loads(rewind(json.dumps(mapping(geom)))))
    if new_geom.is_valid:
        return new_geom
    return geom


def fix_with_zero_buffer(geom: Polygon) -> Polygon:
    """Fix geometry using zero buffer"""
    if geom is None:
        return None
    elif geom.is_valid:
        return geom
    new_geom = geom.buffer(0)
    if geom.area > 0:
        ratio = new_geom.area / geom.area
    else:
        ratio = 10000
    if 0.995 <= ratio and ratio < 1.005:
        return new_geom
    return geom


def fix_with_2d_polygon(geom: Polygon) -> Polygon:
    """Force geometry to 2D"""
    if geom is None:
        return Polygon()
    else:
        return shapely.wkb.loads(shapely.wkb.dumps(geom, output_dimension=2))


def nr_vertices(geom: Polygon) -> Optional[int]:
    """Count number of vertices in polygon"""
    if geom is None or geom.is_empty:
        return 0
    elif isinstance(geom, Polygon):
        return len(geom.exterior.coords.xy[0])
    else:
        return None


def number_of_vertices_per_polygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add vertex count column to GeoDataFrame"""
    gdf["nr_vertices"] = gdf.geometry.apply(nr_vertices)
    return gdf


def remove_duplicate_vertices(geom: Polygon) -> Polygon:
    """Remove duplicate vertices from polygon"""
    if geom.is_empty:
        return Polygon()
    else:
        coords_list = list(geom.exterior.coords)
        if ~len(coords_list) == 0:
            if coords_list[0] == coords_list[-1]:
                coords_list = coords_list[:-1]
            unique_vertices = list(set(coords_list))
            if len(unique_vertices) < len(coords_list):
                unique_vertices.append(unique_vertices[0])
                if len(unique_vertices) > 2:
                    return Polygon((unique_vertices))
                else:
                    return Polygon()
        return geom


def replace_area_zero(geom: Polygon) -> Polygon:
    """Replace zero-area geometries"""
    if geom is None:
        return None
    elif geom.area == 0 and geom.is_empty:
        return Polygon()
    else:
        return geom


def replace_invalid(geom: Polygon) -> Polygon:
    """Replace invalid geometries"""
    if geom.is_valid:
        return geom
    elif geom.buffer(0).is_empty:
        return geom.representative_point().buffer(0.00005)
    else:
        return Polygon()


def replace_multipolygons(
    geom: Union[Polygon, MultiPolygon, GeometryCollection],
) -> Union[Polygon, MultiPolygon, GeometryCollection]:
    """Replace multipolygons with largest polygon"""
    if isinstance(geom, Polygon):
        return geom
    elif isinstance(geom, MultiPolygon):
        if len(geom.geoms) == 1:
            return geom.geoms[0]
        else:
            total_area_geom = geom_to_utm(geom).area
            max_area_geom = max(geom.geoms, key=lambda x: geom_to_utm(x).area)
            max_area = geom_to_utm(max_area_geom).area
            if 0.9 * total_area_geom < max_area:
                return max_area_geom
            else:
                return geom
    elif isinstance(geom, GeometryCollection):
        if len(geom.geoms) == 1:
            print(geom)
            return geom.geoms[0]
        else:
            return geom
    else:
        raise SyntaxError(
            "Geometry is not a Polygon, Multipolygon or GeometryCollection"
        )


def replace_none_geometries(geom: Polygon) -> Polygon:
    """Replace None geometries with empty polygon"""
    if geom is None:
        return Polygon()
    return geom


def replace_out_of_bound_geometries(geom: Polygon) -> Polygon:
    """Replace out-of-bounds geometries with empty polygon"""
    if geom.is_empty:
        return geom
    minx, miny, maxx, maxy = geom.bounds
    if minx <= -180 or 180 <= maxx or miny <= -80 or 84 <= maxy:
        return Polygon()
    return geom


# ============================================
# UTM CONVERSION
# ============================================


def geom_to_utm(geom: Polygon) -> Polygon:
    """Convert WGS84 geometry to UTM projection"""
    if geom.is_empty:
        return geom
    lon, lat = geom.centroid.x, geom.centroid.y
    if not -80.0 <= lat <= 84.0:
        geom = Polygon()
        return geom
    if not -180.0 <= lon <= 180.0:
        geom = Polygon()
        return geom
    _, _, zone, _ = utm.from_latlon(lat, lon)
    project = Transformer.from_crs(
        CRS(crs),
        CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0}),
        always_xy=True,
    ).transform
    return transform(project, geom)


def geom_to_utm_with_crs(geom: Polygon):
    """Convert to UTM and return CRS"""
    if geom.is_empty:
        return geom
    lon, lat = geom.centroid.x, geom.centroid.y
    if not -80.0 <= lat <= 84.0:
        geom = Polygon()
        return geom
    if not -180.0 <= lon <= 180.0:
        geom = Polygon()
        return geom
    _, _, zone, _ = utm.from_latlon(lat, lon)
    crs_dict = CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0})
    project = Transformer.from_crs(CRS(crs), crs_dict, always_xy=True).transform
    geom_utm = transform(project, geom)
    return geom_utm, crs_dict


def simplify_geometry(geom, tolerance: float = 0.05, units="meters"):
    """Simplify geometry using tolerance"""
    assert units in ("meters", "degrees")
    if geom.is_empty:
        return geom

    if units == "meters":
        utm_geom_with_crs = geom_to_utm_with_crs(geom)
        if type(utm_geom_with_crs) is tuple:
            utm_geom, utm_crs_dict = utm_geom_with_crs[0], utm_geom_with_crs[1]
        else:
            return utm_geom_with_crs
        utm_geom_s = utm_geom.simplify(tolerance, preserve_topology=True)
        project = Transformer.from_crs(utm_crs_dict, CRS(crs), always_xy=True).transform
        simple_geom = transform(project, utm_geom_s)
    else:
        simple_geom = geom.simplify(tolerance, preserve_topology=True)

    if ~simple_geom.is_valid:
        return geom

    return simple_geom


# ============================================
# WGS84 POINT
# ============================================


@dc.dataclass(frozen=True)
class WGS84Point:
    """A point on earth in WGS 84 (EPSG 4326)"""

    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(
                f"latitude should be between -90 and 90 but found {self.latitude!r}"
            )
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(
                f"longitude should be between -180 and 180 but found {self.longitude!r}"
            )


def gdf_center(gdf: gpd.GeoDataFrame) -> WGS84Point:
    """Get center point of GeoDataFrame"""
    min_lon, min_lat, max_lon, max_lat = gdf.geometry.total_bounds
    lat = (min_lat + max_lat) / 2
    lon = (min_lon + max_lon) / 2
    return WGS84Point(latitude=lat, longitude=lon)


def epsg_code(lon: float, lat: float) -> str:
    """Get UTM EPSG code for location"""
    utm_band = str((math.floor((lon + 180) / 6) % 60) + 1)
    if len(utm_band) == 1:
        utm_band = "0" + utm_band
    if lat >= 0:
        epsg_code = "326" + utm_band
        return epsg_code
    epsg_code = "327" + utm_band
    return epsg_code


def wgs_to_utm(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Convert GeoDataFrame to UTM"""
    gdf.crs = crs
    centroid = gdf_center(gdf)
    code = epsg_code(centroid.longitude, centroid.latitude)
    return gdf.to_crs(f"EPSG:{code}")


# ============================================
# OVERLAP VALIDATION
# ============================================


def validate_overlap(
    gdf: gpd.GeoDataFrame,
    id_column: str,
    min_overlap: float,
    buffer: float = -5,
    filter: Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame] = lambda x: x,
) -> gpd.GeoDataFrame:
    """Validate overlapping geometries"""
    df_overlap = (
        gdf.pipe(lambda x: wgs_to_utm(x))
        .assign(geometry=lambda x: x.geometry.buffer(buffer))
        .to_crs(crs)
        .pipe(filter)
        .pipe(calculate_area, geodisic=True)
        .pipe(lambda x: x.overlay(x, keep_geom_type=False))
        .pipe(lambda x: x[x[f"{id_column}_1"] != x[f"{id_column}_2"]])
        .pipe(calculate_area, geodisic=True)
        .assign(
            min_area=lambda x: (
                x[["area_m2_1", "area_m2_2"]].min(axis=1)
                if not x.empty
                else pd.Series(dtype="float64")
            ),
            overlay_ratio=lambda x: x.area_m2 / x.min_area,
            overlap=lambda x: min_overlap < x.overlay_ratio.to_numpy(),
        )
        .pipe(lambda x: x[x.overlap])
    )

    if df_overlap.empty:
        df_overlap_all = gpd.GeoDataFrame(
            columns=[id_column, "overlap_ids", "percentage_overlap"]
        )
    else:
        df_overlap_ids = (
            df_overlap.groupby(f"{id_column}_1")[f"{id_column}_2"]
            .apply(lambda x: ";".join([str(i) for i in x if i is not None]))
            .reset_index()
            .rename(
                columns={f"{id_column}_1": id_column, f"{id_column}_2": "overlap_ids"}
            )
        )

        df_overlap_max = (
            df_overlap.groupby(f"{id_column}_1")
            .agg({"overlay_ratio": ["max"]})
            .droplevel(axis=1, level=0)
            .reset_index()
            .rename(columns={f"{id_column}_1": id_column, "max": "percentage_overlap"})
            .round(decimals=2)
        )

        df_overlap_all = df_overlap_ids.merge(df_overlap_max, on=id_column, how="left")

    return gdf.merge(df_overlap_all, how="left").assign(
        overlap_ids=lambda x: x.overlap_ids.fillna(""),
        percentage_overlap_float=lambda x: x.percentage_overlap.astype(float),
        percentage_overlap=lambda x: x.percentage_overlap_float.fillna(""),
    )


# ============================================
# GEOMETRY FROM SCTO STRING
# ============================================


def is_invalid_polygon_string(polygon_string, pd_row=None, column=None):
    """Check if polygon string is invalid"""
    if pd.isna(polygon_string):
        if column is not None:
            print(f"No coordinates for: {column}, so returning empty Polygon")
        return True
    if len(polygon_string) == 32767:
        if pd_row is not None:
            print(
                f"Reached cell limit of excel for: {getattr(pd_row, 'plot_id', '')} "
                f"collected by: {getattr(pd_row, 'enumerator_id', '')},"
                "so returning empty Polygon"
            )
        return True
    return False


def coordinates_from_vertices(vertices, accuracy_m, accuracy_zero_valid=False):
    """Extract coordinates from vertices with accuracy filtering"""
    coordinates = []
    skip_coordinates_counter = 0

    for vertex in vertices:
        if not vertex.strip():
            skip_coordinates_counter += 1
            continue

        parts = vertex.strip().split(" ")
        accuracy = float(parts[3])

        if accuracy_zero_valid:
            if accuracy > accuracy_m:
                skip_coordinates_counter += 1
                continue
        else:
            if accuracy > accuracy_m or abs(accuracy - 0.0) < 1e-9:
                skip_coordinates_counter += 1
                continue

        lon = float(parts[0])
        lat = float(parts[1])
        coordinates.append((lat, lon))

    return coordinates, skip_coordinates_counter


def geom_from_scto_str(pd_row, column, accuracy_m, accuracy_zero_valid=False):
    """Create geometry from SurveyCTO coordinate string"""
    polygon_string = pd_row[column]
    if is_invalid_polygon_string(polygon_string, pd_row, column):
        return shapely.geometry.polygon.Polygon()

    vertices = polygon_string.split(";")
    coordinates, skip_coordinates_counter = coordinates_from_vertices(
        vertices, accuracy_m, accuracy_zero_valid
    )

    if len(coordinates) < 3 or (len(coordinates) < (skip_coordinates_counter * 4)):
        print(f"Dropped too many points for pd_row")
        return shapely.geometry.polygon.Polygon()

    geom = shapely.geometry.polygon.Polygon(coordinates)
    return geom


# ============================================
# VALIDATION REASONS COLLECTION
# ============================================


def collect_reasons_subplot(
    row: pd.Series, min_subplot_area_size: float, max_subplot_area_size: float
) -> str:
    """Collect all validation failure reasons for subplot"""
    if row.geometry is None:
        return "Geometry missing"
    if row.geometry.is_empty:
        return "Empty geometry"
    if not row.geometry.is_valid:
        return "Invalid geometry"

    reasons = [
        (
            "Overlapping polygons"
            if "overlap_ids" in row.index and row.overlap_ids
            else ""
        ),
        "Duplicate plot id" if "duplicate_id" in row.index and row.duplicate_id else "",
        (
            "Boundary not in country"
            if "in_country" in row.index and not row.in_country
            else ""
        ),
        (
            "Plot outside of radius"
            if "in_radius" in row.index and not row.in_radius
            else ""
        ),
        (
            "Plot too small"
            if "area_m2" in row.index and row.area_m2 < min_subplot_area_size
            else ""
        ),
        (
            "Plot too big"
            if "area_m2" in row.index and row.area_m2 > max_subplot_area_size
            else ""
        ),
        (
            f"Nr vertices <= {3}"
            if "nr_vertices_too_small" in row.index and row.nr_vertices_too_small
            else ""
        ),
        (
            "Plot is protruding"
            if "protruding_ratio_too_big" in row.index and row.protruding_ratio_too_big
            else ""
        ),
    ]

    return ";".join(filter(None, reasons))


def collect_reasons_plot(
    row: pd.Series, min_plot_area_size: float, max_plot_area_size: float
) -> str:
    """Collect all validation failure reasons for plot"""
    return collect_reasons_subplot(row, min_plot_area_size, max_plot_area_size)


def assign_geom_valid_geojson(
    gdf: gpd.GeoDataFrame, min_area: float, max_area: float
) -> gpd.GeoDataFrame:
    """Assign validity and geojson to GeoDataFrame"""
    gdf["reasons"] = gdf.apply(
        lambda x: collect_reasons_subplot(x, min_area, max_area), axis=1
    )
    gdf["geom_valid"] = gdf["reasons"].apply(lambda x: len(x) == 0)
    gdf["geojson"] = gdf.apply(
        lambda x: to_geojson(x.geometry, x.get("subplot_id", "unknown")), axis=1
    )
    return gdf


# ============================================
# GEOMETRY FIXER CLASS
# ============================================


class GeometryFixer:
    """Handles geometry fixing operations"""

    def fix_geometry(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Apply all geometry fixes in sequence"""
        gdf["original_vertices"] = gdf.geometry.apply(
            lambda x: len(x.exterior.coords) if x.geom_type == "Polygon" else 0
        )
        gdf["geometry"] = gdf.geometry.apply(remove_duplicate_vertices)

        valid = gdf.is_valid.sum()

        gdf["geometry"] = gdf.geometry.apply(fix_self_intersecting_square)
        gdf["geometry"] = gdf.geometry.apply(fix_with_orient)
        gdf["geometry"] = gdf.geometry.apply(fix_with_rewind)
        gdf["geometry"] = gdf.geometry.apply(fix_with_zero_buffer)
        gdf["geometry"] = gdf.geometry.apply(fix_with_2d_polygon)
        gdf["geometry"] = gdf["geometry"].apply(
            lambda geom: (
                geom
                if geom.geom_type not in ["Point", "LineString", "MultiLineString"]
                else Polygon()
            )
        )
        gdf["geometry"] = gdf.geometry.apply(replace_multipolygons)
        gdf["geometry"] = gdf.geometry.apply(simplify_geometry, tolerance=0.1)

        print(f"\nFixed {gdf.is_valid.sum() - valid} polygons")
        empty = gdf.is_empty.sum()

        gdf["geometry"] = gdf.geometry.apply(replace_area_zero)
        gdf["geometry"] = gdf.geometry.apply(replace_none_geometries)
        gdf["geometry"] = gdf.geometry.apply(replace_out_of_bound_geometries)
        gdf["geometry"] = gdf.geometry.apply(replace_invalid)
        print(f"Replaced {gdf.is_empty.sum() - empty} polygons with empty polygons\n")

        return gdf


# ============================================
# GEOMETRY VALIDATOR CLASS
# ============================================


class GeometryValidator:
    """Handles geometry validation operations"""

    def __init__(
        self,
        partner: str,
        country: str,
        threshold_length_width: float,
        threshold_protruding_ratio: float,
        validate_id: str,
        threshold_within_radius: float,
        min_area_size: float,
        max_area_size: float,
        max_vertices: float,
    ):
        self.partner = partner
        self.country = country
        self.threshold_length_width = threshold_length_width
        self.threshold_protruding_ratio = threshold_protruding_ratio
        self.validate_id = validate_id
        self.threshold_within_radius = threshold_within_radius
        self.min_area_size = min_area_size
        self.max_area_size = max_area_size
        self.max_vertices = max_vertices

    def validate_geometry(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Apply all validations to GeoDataFrame"""
        if "index" in gdf.columns:
            gdf = gdf.drop(columns=["index"])

        if gdf.geometry.is_empty.all():
            print("All geometries in gdf are empty, no validation can be done")
        else:
            gdf = (
                gdf.pipe(self.validate_length_width_ratio)
                .pipe(self.validate_protruding_ratio)
                .assign(in_country=True)
                .assign(duplicate_id=False)
                .pipe(calculate_area, geodisic=True)
                .pipe(self.validate_nr_vertices)
                .pipe(self.validate_within_radius)
                .pipe(
                    validate_overlap,
                    id_column=self.validate_id,
                    min_overlap=0.5,
                    buffer=-5,
                    filter=self.overlap_filter,
                )
            )

        return gdf

    def validate_length_width_ratio(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Validate length/width ratio"""
        return gdf.pipe(add_length_width_ratio).assign(
            length_width_ratio_too_big=lambda x: x.length_width_ratio
            > self.threshold_length_width
        )

    def validate_protruding_ratio(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Validate protruding ratio"""
        return gdf.pipe(add_protruding_ratio).assign(
            protruding_ratio_too_big=lambda x: x.mrr_ratio
            > self.threshold_protruding_ratio
        )

    def validate_nr_vertices(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Validate number of vertices"""
        return (
            gdf.pipe(number_of_vertices_per_polygon)
            .assign(vertices_dropped=lambda x: x.original_vertices - x.nr_vertices)
            .assign(
                vertices_valid_percentage=lambda x: 100
                * x.nr_vertices
                / x.original_vertices
            )
            .assign(nr_vertices_too_small=lambda x: x.nr_vertices <= self.max_vertices)
        )

    def validate_within_radius(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Validate if all points within radius"""
        gdf["in_radius"] = gdf.geometry.apply(
            lambda x: self.all_points_in_radius(x, self.threshold_within_radius)
        )
        return gdf

    def overlap_filter(self, x):
        """Filter for overlap validation"""
        return x[
            (x.in_country)
            & (x.in_radius)
            & (self.min_area_size < x.area_m2)
            & (x.area_m2 < self.max_area_size)
            & (~x.protruding_ratio_too_big)
            & (~x.nr_vertices_too_small)
        ]

    @staticmethod
    def all_points_in_radius(geom: Polygon, radius: float):
        """Check if all points are within radius from centroid"""
        if geom is not None and geom.is_valid:
            geom_utm = geom_to_utm(geom)
            circle = geom_utm.centroid.buffer(radius)
            return circle.covers(geom_utm)
        return None
