import dataclasses as dc
import datetime as dt
import json
import math
import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import geopandas as gpd
import pandas as pd
import shapely
import utm
from geojson_rewind import rewind
from geopandas import GeoDataFrame
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, mapping, shape
from shapely.geometry.polygon import Point, orient
from shapely.ops import transform
import logging
import warnings
import numpy as np

# from src.ground_truth.akvo_gt_check.gt_config import (COUNTRY_ISO3,
from gt_config import (COUNTRY_ISO3,
                                                      
                                                      MAX_SUBPLOT_AREA_SIZE,
                                                      MAX_VERTICES, MIN_GT_PLOT_AREA_SIZE, MAX_GT_PLOT_AREA_SIZE,
                                                      MIN_SUBPLOT_AREA_SIZE,
                                                      PARTNER, YEAR)

F = TypeVar("F", bound=Callable[..., Any])

# Configure logging
logger = logging.getLogger(__name__)

# Suppress specific warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='geopandas')
warnings.filterwarnings('ignore', category=FutureWarning, module='pandas')
warnings.filterwarnings('ignore', category=RuntimeWarning, module='shapely')
warnings.filterwarnings('ignore', message=".*'type' attribute is deprecated.*")
warnings.filterwarnings('ignore', message=".*invalid value encountered.*")
warnings.filterwarnings('ignore', message=".*elementwise comparison failed.*")

def log_step(func: F) -> Any:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        tic = dt.datetime.now()
        result = func(*args, **kwargs)
        time = str(dt.datetime.now() - tic)

        print(
            f"{func.__name__.ljust(30)} shape={str(result.shape).ljust(10)} time={time}"
        )
        return result

    return wrapper

@log_step
#def add_ecoregion(gdf: gpd.GeoDataFrame, id_column: str) -> gpd.GeoDataFrame:
 #   path = Path.cwd() / "data" / "datasets" / "wwf-ecoregions" / "wwf_terr_ecos.shp"
  #  ecoregion = (
   #     gpd.read_file(path)
    #    .to_crs("EPSG:4326")
     #   .rename(columns={"ECO_NAME": "ecoregion"})[["geometry", "ecoregion"]]
    #)


def add_ecoregion(gdf: gpd.GeoDataFrame, id_column: str) -> gpd.GeoDataFrame:
    path = "/Users/joy/Downloads/Rabobank_ACORN_Initiative/AcornGT/datasets/wwf-ecoregions/wwf_terr_ecos.shp"
    ecoregion = (
        gpd.read_file(path)
        .to_crs("EPSG:4326")
        .rename(columns={"ECO_NAME": "ecoregion"})[["geometry", "ecoregion"]]
    )

    # you can overlap with multiple ecoregions, but we choose the biggest overlap
    overlap = (
        gdf.assign(geometry=lambda x: x.buffer(0))
        .overlay(ecoregion, keep_geom_type=False)
        .pipe(calculate_area)
        .sort_values(by="area_m2")
        .drop_duplicates(subset=[id_column], keep="last")[[id_column, "ecoregion"]]
    )
    return gdf.merge(overlap, how="left")

def calculate_area(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    # gdf["area_m2"] = gdf.geometry.apply(lambda x: geom_to_utm(x).area)
    gdf["area_m2"] = gdf[~gdf.geometry.isna()].geometry.apply(
        lambda x: geom_to_utm(x).area
    )
    return gdf

def geom_to_utm(geom: Polygon) -> Polygon:
    if geom.is_empty:
        return geom
    lon, lat = geom.centroid.x, geom.centroid.y
    if not -80.0 <= lat <= 84.0:
        # change/mirror XY-coordinates?
        geom = Polygon()
        return geom
    if not -180.0 <= lon <= 180.0:
        # change/mirror XY-coordinates?
        geom = Polygon()
        return geom
    _, _, zone, _ = utm.from_latlon(lat, lon)
    project = Transformer.from_crs(
        CRS("EPSG:4326"),
        CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0}),
        always_xy=True,
    ).transform
    return transform(project, geom)

@log_step
def validate_country(
    gdf: gpd.GeoDataFrame, country_code: str = COUNTRY_ISO3
) -> gpd.GeoDataFrame:
    country_path = "/Users/joy/Downloads/Rabobank_ACORN_Initiative/AcornGT/datasets/world-administrative-boundaries/world-administrative-boundaries.shp"
    gdf_countries = (
        gpd.read_file(country_path)
        .to_crs("EPSG:4326")
        .pipe(lambda x: x[x.iso3 == country_code])
        .pipe(lambda x: wgs_to_utm(x))[["geometry", "iso3"]]
        .assign(geometry=lambda x: x.geometry.buffer(10_000))
        .to_crs("EPSG:4326")
    )


    gdf["overlapping_countries"] = (
        gdf.reset_index()
        .pipe(lambda x: x.sjoin(gdf_countries, how="left"))
        .astype({"iso3": "str"})
        .groupby("index")["iso3"]
        .apply(lambda x: ";".join(x))
    )
    gdf["in_country"] = country_code == gdf["overlapping_countries"]

    return gdf

def wgs_to_utm(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf.crs = "EPSG:4326"
    centroid = gdf_center(gdf)
    code = epsg_code(centroid.longitude, centroid.latitude)
    return gdf.to_crs(f"EPSG:{code}")


@dc.dataclass(frozen=True)
class WGS84Point:
    """
    A point on earth in WGS 84 (EPSG 4326).

    Important:
        It is the constructors responsibility to ensure a point is valid. Specifically
        this means that ``-90 <= latitude <= 90 and -180 <= longitude <= 180``.

    Raises:
        ValueError: If ``latitude`` or ``longitude`` is out of bounds.

    See Also:
        See https://epsg.io/4326 for more info on the coordinate system.
    """

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
    min_lon, min_lat, max_lon, max_lat = gdf.geometry.total_bounds
    lat = (min_lat + max_lat) / 2
    lon = (min_lon + max_lon) / 2
    return WGS84Point(latitude=lat, longitude=lon)



def epsg_code(lon: float, lat: float) -> str:
    utm_band = str((math.floor((lon + 180) / 6) % 60) + 1)
    if len(utm_band) == 1:
        utm_band = "0" + utm_band
    if lat >= 0:
        epsg_code = "326" + utm_band
        return epsg_code
    epsg_code = "327" + utm_band
    return epsg_code


@log_step
def validate_overlap(
    gdf: gpd.GeoDataFrame,
    id_column: str,
    min_overlap: float = 0.1,
    buffer: float = -5,
    filter: Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame] = lambda x: x,
) -> gpd.GeoDataFrame:
    df_overlap = (
        gdf
        # .pipe(lambda x: x[x.valid])
        .pipe(lambda x: wgs_to_utm(x))
        .assign(geometry=lambda x: x.geometry.buffer(buffer))
        .to_crs("EPSG:4326")
        .pipe(filter)
        .pipe(calculate_area)
        .pipe(lambda x: x.overlay(x))
        .pipe(lambda x: x[x[f"{id_column}_1"] != x[f"{id_column}_2"]])
        .pipe(calculate_area)
        .assign(
            min_area=lambda x: x[["area_m2_1", "area_m2_2"]].min(axis=1),
            overlay_ratio=lambda x: x.area_m2 / x.min_area,
            overlap=lambda x: min_overlap < x.overlay_ratio.to_numpy(),
        )
        .pipe(lambda x: x[x.overlap])
    )

    df_overlap_ids = (
        df_overlap.groupby(f"{id_column}_1")[f"{id_column}_2"]
        .apply(lambda x: ";".join(x))
        .reset_index()
        .rename(columns={f"{id_column}_1": id_column, f"{id_column}_2": "overlap_ids"})
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
    )


def to_geojson(geom: Polygon, id: str = "plot_id") -> Optional[str]:
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
    
def round_coordinates(geom, ndigits=2):
    def _round_coords(x, y, z=None):
        x = round(x, ndigits)
        y = round(y, ndigits)
        if z is not None:
            z = round(z, ndigits)
        return [c for c in (x, y, z) if c is not None]

    return transform(_round_coords, geom)

@log_step
def validate_duplicate_id(gdf: GeoDataFrame, id_column: str) -> GeoDataFrame:
    gdf["duplicate_id"] = gdf[id_column].duplicated(keep=False)
    return gdf


def collect_reasons_subplot(row: pd.Series) -> str:
    if row.geometry is None:
        return "Geometry missing"
    if row.geometry.is_empty:
        return "Empty geometry"
    if not row.geometry.is_valid:
        return "Invalid geometry"
    reasons = []
    if "overlap_ids" in row.index.tolist():
        if len(row.overlap_ids) > 0:
            reasons.append("Overlapping polygons")
    if row.duplicate_id:
        reasons.append("Duplicate plot id")
    if not row.in_country:
        reasons.append("Boundary not in country")
    # if np.isnan(row.above_ground_biomass):
    #     reasons.append("Plot has tree(s) with unknown biomass")
    if not row.in_radius:
        reasons.append("Plot outside of radius")
    if row.area_m2 < MIN_SUBPLOT_AREA_SIZE:
        reasons.append("Plot too small")
    if MAX_SUBPLOT_AREA_SIZE < row.area_m2:
        reasons.append("Plot too big")
    if row.nr_vertices_too_small:
        reasons.append("Nr vertices <= {}".format(3))
    # if row.length_width_ratio_too_big:
    #     reasons.append("Plot seems to long")
    if row.protruding_ratio_too_big:
        reasons.append("Plot is protruding")

    return ";".join(reasons)

# Plot
def collect_reasons_plot(row: pd.Series) -> str:
    if row.geometry is None:
        return "Geometry missing"
    if row.geometry.is_empty:
        return "Empty geometry"
    if not row.geometry.is_valid:
        return "Invalid geometry"
    reasons = []
    if "overlap_ids" in row.index.tolist():
        if len(row.overlap_ids) > 0:
            reasons.append("Overlapping polygons")
    if row.duplicate_id:
        reasons.append("Duplicate plot id")
    if not row.in_country:
        reasons.append("Boundary not in country")
    # if np.isnan(row.above_ground_biomass):
    #     reasons.append("Plot has tree(s) with unknown biomass")
    if not row.in_radius:
        reasons.append("Plot outside of radius")
    if row.area_m2 < MIN_GT_PLOT_AREA_SIZE:
        reasons.append("Plot too small")
    if MAX_GT_PLOT_AREA_SIZE < row.area_m2:
        reasons.append("Plot too big")
    if row.nr_vertices_too_small:
        reasons.append("Nr vertices <= {}".format(3))
    # if row.length_width_ratio_too_big:
    #     reasons.append("Plot seems to long")
    if row.protruding_ratio_too_big:
        reasons.append("Plot is protruding")

    return ";".join(reasons)


def export_plots(df_plots, output_dir):
    """Export plots to GeoJSON files"""
    try:
        # Split into valid and invalid plots
        df_valid = df_plots[df_plots['valid']].copy()
        df_invalid = df_plots[~df_plots['valid']].copy()
        
        # Validate geometry before export
        def validate_geometry_for_export(df, name):
            bad_shapes = 0
            valid_records = []
            
            for idx, row in df.iterrows():
                try:
                    # Check if geojson exists and is valid
                    if 'geojson' in row and row.geojson is not None:
                        # Try to parse the geojson to validate it
                        geojson_data = json.loads(row.geojson)
                        if geojson_data and 'features' in geojson_data and len(geojson_data['features']) > 0:
                            valid_records.append(row)
                        else:
                            bad_shapes += 1
                            logger.warning(f"Bad {name} geojson at index {idx}: empty or invalid geojson")
                    else:
                        bad_shapes += 1
                        logger.warning(f"Bad {name} geojson at index {idx}: missing geojson")
                except Exception as e:
                    bad_shapes += 1
                    logger.warning(f"Bad {name} geojson at index {idx}: {str(e)}")
            
            logger.info(f"Found {bad_shapes} bad {name} shapes out of {len(df)} total")
            return pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
        
        # Validate and filter valid plots
        df_valid_clean = validate_geometry_for_export(df_valid, "plot")
        
        # Validate and filter invalid plots
        df_invalid_clean = validate_geometry_for_export(df_invalid, "plot")
        
        # Log problematic records before export
        if not df_invalid.empty:
            logger.info(f"Found {len(df_invalid)} invalid plots")
            for idx, row in df_invalid.iterrows():
                try:
                    # Try to access geojson to check if it's valid
                    _ = row.geojson
                    logger.info(f"Invalid plot {row.get('plot_id', 'unknown')}: {row.get('reasons', 'unknown reasons')}")
                except Exception as e:
                    logger.error(f"Problematic plot record at index {idx}: {str(e)}")
                    logger.error(f"Record data: {row.to_dict()}")
        
        # Export valid plots
        if not df_valid_clean.empty:
            try:
                # Convert back to GeoDataFrame and create a copy without the geojson column for export
                df_valid_gdf = gpd.GeoDataFrame(df_valid_clean, geometry='geometry', crs="EPSG:4326")
                df_valid_export = df_valid_gdf.drop(columns=["geojson"])
                df_valid_export.to_file(
                    output_dir / "plots_valid.geojson",
                    driver="GeoJSON",
                    index=False
                )
                logger.info(f"Successfully exported {len(df_valid_clean)} valid plots")
            except Exception as e:
                logger.error(f"Error exporting valid plots: {str(e)}")
                logger.error("Traceback:", exc_info=True)
        else:
            logger.warning("No valid plots with good geometry to export")
        
        # Export invalid plots
        if not df_invalid_clean.empty:
            try:
                # Convert back to GeoDataFrame and create a copy without the geojson column for export
                df_invalid_gdf = gpd.GeoDataFrame(df_invalid_clean, geometry='geometry', crs="EPSG:4326")
                df_invalid_export = df_invalid_gdf.drop(columns=["geojson"])
                df_invalid_export.to_file(
                    output_dir / "plots_invalid.geojson",
                    driver="GeoJSON",
                    index=False
                )
                logger.info(f"Successfully exported {len(df_invalid_clean)} invalid plots")
            except Exception as e:
                logger.error(f"Error exporting invalid plots: {str(e)}")
                logger.error("Traceback:", exc_info=True)
        else:
            logger.warning("No invalid plots with good geometry to export")
                
    except Exception as e:
        logger.error(f"Error in export_plots: {str(e)}")
        logger.error("Traceback:", exc_info=True)

def export_subplots(df_subplots, output_dir):
    """Export subplots to GeoJSON files"""
    try:
        # Split into valid and invalid subplots
        df_valid = df_subplots[df_subplots['valid']].copy()
        df_invalid = df_subplots[~df_subplots['valid']].copy()
        
        # Validate geometry before export
        def validate_geometry_for_export(df, name):
            bad_shapes = 0
            valid_records = []
            
            for idx, row in df.iterrows():
                try:
                    # Check if geojson exists and is valid
                    if 'geojson' in row and row.geojson is not None:
                        # Try to parse the geojson to validate it
                        geojson_data = json.loads(row.geojson)
                        if geojson_data and 'features' in geojson_data and len(geojson_data['features']) > 0:
                            valid_records.append(row)
                        else:
                            bad_shapes += 1
                            logger.warning(f"Bad {name} geojson at index {idx}: empty or invalid geojson")
                    else:
                        bad_shapes += 1
                        logger.warning(f"Bad {name} geojson at index {idx}: missing geojson")
                except Exception as e:
                    bad_shapes += 1
                    logger.warning(f"Bad {name} geojson at index {idx}: {str(e)}")
            
            logger.info(f"Found {bad_shapes} bad {name} shapes out of {len(df)} total")
            return pd.DataFrame(valid_records) if valid_records else pd.DataFrame()
        
        # Validate and filter valid subplots
        df_valid_clean = validate_geometry_for_export(df_valid, "subplot")
        
        # Validate and filter invalid subplots
        df_invalid_clean = validate_geometry_for_export(df_invalid, "subplot")
        
        # Log problematic records before export
        if not df_invalid.empty:
            logger.info(f"Found {len(df_invalid)} invalid subplots")
            for idx, row in df_invalid.iterrows():
                try:
                    # Try to access geojson to check if it's valid
                    _ = row.geojson
                    logger.info(f"Invalid subplot {row.get('subplot_id', 'unknown')}: {row.get('reasons', 'unknown reasons')}")
                except Exception as e:
                    logger.error(f"Problematic subplot record at index {idx}: {str(e)}")
                    logger.error(f"Record data: {row.to_dict()}")
        
        # Export valid subplots
        if not df_valid_clean.empty:
            try:
                # Convert back to GeoDataFrame and create a copy without the geojson column for export
                df_valid_gdf = gpd.GeoDataFrame(df_valid_clean, geometry='geometry', crs="EPSG:4326")
                df_valid_export = df_valid_gdf.drop(columns=["geojson"])
                df_valid_export.to_file(
                    output_dir / "subplots_valid.geojson",
                    driver="GeoJSON",
                    index=False
                )
                logger.info(f"Successfully exported {len(df_valid_clean)} valid subplots")
            except Exception as e:
                logger.error(f"Error exporting valid subplots: {str(e)}")
                logger.error("Traceback:", exc_info=True)
        else:
            logger.warning("No valid subplots with good geometry to export")
        
        # Export invalid subplots
        if not df_invalid_clean.empty:
            try:
                # Convert back to GeoDataFrame and create a copy without the geojson column for export
                df_invalid_gdf = gpd.GeoDataFrame(df_invalid_clean, geometry='geometry', crs="EPSG:4326")
                df_invalid_export = df_invalid_gdf.drop(columns=["geojson"])
                df_invalid_export.to_file(
                    output_dir / "subplots_invalid.geojson",
                    driver="GeoJSON",
                    index=False
                )
                logger.info(f"Successfully exported {len(df_invalid_clean)} invalid subplots")
            except Exception as e:
                logger.error(f"Error exporting invalid subplots: {str(e)}")
                logger.error("Traceback:", exc_info=True)
        else:
            logger.warning("No invalid subplots with good geometry to export")
                
    except Exception as e:
        logger.error(f"Error in export_subplots: {str(e)}")
        logger.error("Traceback:", exc_info=True)

@log_step
def fix_geometry(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["geometry"] = gdf.geometry.apply(remove_duplicate_vertices)
    valid = gdf.is_valid.sum()
    gdf["geometry"] = gdf.geometry.apply(fix_self_intersecting_square)
    gdf["geometry"] = gdf.geometry.apply(fix_with_orient)
    gdf["geometry"] = gdf.geometry.apply(fix_with_rewind)
    gdf["geometry"] = gdf.geometry.apply(fix_with_zero_buffer)
    gdf["geometry"] = gdf.geometry.apply(simplify_geometry, tolerance=0.1)
    print(f"Fixed {gdf.is_valid.sum() - valid} polygons")
    empty = gdf.is_empty.sum()
    gdf["geometry"] = gdf.geometry.apply(replace_area_zero)
    gdf["geometry"] = gdf.geometry.apply(replace_none_geometries)
    gdf["geometry"] = gdf.geometry.apply(replace_out_of_bound_geometries)
    gdf["geometry"] = gdf.geometry.apply(replace_invalid)
    print(f"Replaced {gdf.is_empty.sum() - empty} polygons with empty polygons")

    return gdf

def remove_duplicate_vertices(geom: Polygon) -> Polygon:
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
    
def fix_self_intersecting_square(geom: Polygon) -> Polygon:
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    coords = geom.exterior.coords.xy
    if len(coords[0]) == 5:
        return geom.convex_hull
    return geom


def fix_with_orient(geom: Polygon) -> Polygon:
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    new_geom = orient(geom)
    if new_geom.is_valid:
        return new_geom
    return geom


def fix_with_rewind(geom: Polygon) -> Polygon:
    if geom is None:
        return geom
    if geom.is_valid:
        return geom
    new_geom = shape(json.loads(rewind(json.dumps(mapping(geom)))))
    if new_geom.is_valid:
        return new_geom
    return geom

def fix_with_zero_buffer(geom: Polygon) -> Polygon:
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


def simplify_geometry(geom, tolerance: float = 0.05):
    if geom.is_empty:
        return geom
    utm_geom, utm_crs_dict = geom_to_utm_with_crs(geom)
    utm_geom_s = utm_geom.simplify(tolerance, preserve_topology=True)
    project = Transformer.from_crs(
        utm_crs_dict, CRS("EPSG:4326"), always_xy=True
    ).transform
    wgs_geom = transform(project, utm_geom_s)
    if ~wgs_geom.is_valid:
        return geom
    return wgs_geom

def geom_to_utm_with_crs(geom: Polygon) -> Polygon:
    if geom.is_empty:
        return geom
    lon, lat = geom.centroid.x, geom.centroid.y
    if not -80.0 <= lat <= 84.0:
        # change/mirror XY-coordinates?
        geom = Polygon()
        return geom
    if not -180.0 <= lon <= 180.0:
        # change/mirror XY-coordinates?
        geom = Polygon()
        return geom
    _, _, zone, _ = utm.from_latlon(lat, lon)
    crs_dict = CRS.from_dict({"proj": "utm", "zone": zone, "south": lat < 0})
    project = Transformer.from_crs(CRS("EPSG:4326"), crs_dict, always_xy=True).transform
    geom_utm = transform(project, geom)
    return geom_utm, crs_dict

def replace_area_zero(geom: Polygon) -> Polygon:
    if geom is None:
        return None
    elif geom.area == 0:
        return Polygon()
    else:
        return geom

def replace_none_geometries(geom: Polygon) -> Polygon:
    if geom is None:
        return Polygon()
    return geom

def replace_out_of_bound_geometries(geom: Polygon) -> Polygon:
    if geom.is_empty:
        return geom
    minx, miny, maxx, maxy = geom.bounds
    if minx <= -180 or 180 <= maxx or miny <= -80 or 84 <= maxy:
        return Polygon()
    return geom

def replace_invalid(geom: Polygon) -> Polygon:
    if geom.is_valid:
        return geom
    else:
        return Polygon()
    
@log_step
def validate_length_width_ratio(gdf: gpd.GeoDataFrame, threshold) -> gpd.GeoDataFrame:
    return gdf.pipe(add_length_width_ratio).assign(
        length_width_ratio_too_big=lambda x: x.length_width_ratio > threshold
    )

def add_length_width_ratio(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["length_width_ratio"] = gdf.geometry.apply(geom_to_utm).apply(
        length_width_ratio
    )
    return gdf

def length_width_ratio(geom: Polygon) -> Optional[float]:
    if geom.is_empty:
        return None
    mbb = geom.minimum_rotated_rectangle
    x, y = mbb.exterior.coords.xy
    edge_length = (
        Point(x[0], y[0]).distance(Point(x[1], y[1])),
        Point(x[1], y[1]).distance(Point(x[2], y[2])),
    )
    ratio = max(edge_length) / min(edge_length)
    return ratio

@log_step
def validate_nr_vertices(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf.pipe(number_of_vertices_per_polygon).assign(
        nr_vertices_too_small=lambda x: x.nr_vertices <= MAX_VERTICES
    )

def number_of_vertices_per_polygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["nr_vertices"] = gdf.geometry.apply(nr_vertices)
    return gdf

def nr_vertices(geom: Polygon) -> Optional[int]:
    if geom.is_empty:
        return 0
    elif type(geom) == Polygon:
        return len(geom.exterior.coords.xy[0])
    return None

@log_step
def validate_protruding_ratio(gdf: gpd.GeoDataFrame, threshold) -> gpd.GeoDataFrame:
    return gdf.pipe(add_protruding_ratio).assign(
        protruding_ratio_too_big=lambda x: x.mrr_ratio > threshold
    )

def add_protruding_ratio(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf_shapes = (
        gdf[~gdf.geometry.isna()]
        .pipe(calculate_area)
        .pipe(calculate_minimum_rotated_rectangle)
        .assign(mrr_ratio=lambda x: x.minimum_rotated_rectangle_m2 / x.area_m2)
        .drop(columns=["area_m2", "minimum_rotated_rectangle_m2"])
    )
    return gdf_shapes

def calculate_minimum_rotated_rectangle(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf["minimum_rotated_rectangle_m2"] = gdf.geometry.apply(
        lambda x: geom_to_utm(x).minimum_rotated_rectangle.area
    )
    return gdf

@log_step
def validate_within_radius(gdf: gpd.GeoDataFrame, radius: float) -> gpd.GeoDataFrame:
    gdf["in_radius"] = gdf.geometry.apply(lambda x: all_points_in_radius(x, radius))
    return gdf


def all_points_in_radius(geom: Polygon, radius: float) -> Any:
    if geom is not None and geom.is_valid:
        if geom.type == "MultiPolygon":
            geom = geom.geoms[0]
        geom_utm = geom_to_utm(geom)
        circle = geom_utm.centroid.buffer(radius)
        return circle.covers(geom_utm)
    return None

def create_gt_plotid(row):
    partner = PARTNER.replace(" ", "")
    country_code = COUNTRY_ISO3
    collection_date = row["starttime"].strftime("%Y%m%d")
    return (
        f"{country_code}_{partner}_{collection_date}_"
        f"{row.enumerator_id}_{str(row.name + 1)}"
    )
# START 
# def geom_from_scto_str(pd_row, column, accuracy_m):
#     polygon_string = pd_row[column]
#     if pd.isna(polygon_string):
#         # print(f"No coordinates for :{column}, so returning empty Polygon")
#         return shapely.geometry.polygon.Polygon()

#     if len(polygon_string) == 32767:
#         if "plot_id" in pd_row:
#             column_name = "plot_id"
#         else:
#             farmer_name = (
#                 pd_row["Primary Contact First Name"]
#                 + " "
#                 + pd_row["Primary Contact Last Name"]
#             )
#             column_name = farmer_name
#         print(
#             f"Reached cell limit of excel for {[column_name]}:{farmer_name}, so"
#             " returning empty Polygon"
#         )
#         return shapely.geometry.polygon.Polygon()

#     coordinates = []
#     skip_coordinates_counter = 0
#     for vertex_nr in range(len(polygon_string.split(";"))):
#         if (
#             (len(polygon_string.split(";")[vertex_nr]) == 0)
#             or (
#                 float(polygon_string.split(";")[vertex_nr].strip().split(" ")[3])
#                 > accuracy_m
#             )
#             or (polygon_string.split(";")[vertex_nr].strip().split(" ")[3] == "0.0")
#         ):
#             skip_coordinates_counter = skip_coordinates_counter + 1
#             continue
#         lon = float(polygon_string.split(";")[vertex_nr].strip().split(" ")[0])
#         lat = float(polygon_string.split(";")[vertex_nr].strip().split(" ")[1])
#         coordinates.append((lat, lon))

# # Edits proposed by Laura
#     if len(coordinates) < 3 or (len(coordinates) < (skip_coordinates_counter * 4)):
#         if "plot_id" in pd_row:
#             column_name = "plot_id"
#         elif "farmer_id" in pd_row:
#             column_name = "farmer_id"
#         print(
#             "Dropped too many points for :"
#             f"{pd_row[column_name]},collected by {pd_row.enumerator_name}"
#         )
#         return shapely.geometry.polygon.Polygon()
#     geom = shapely.geometry.polygon.Polygon(coordinates)
#     return geom
# #

def geom_from_scto_str(pd_row, column, accuracy_m):

    EXCEL_CELL_LIMIT = 32767

    polygon_string = pd_row[column]

    if pd.isna(polygon_string):

        # print(f"No coordinates for :{column}, so returning empty Polygon")

        return shapely.geometry.polygon.Polygon()

 

    if len(polygon_string) == EXCEL_CELL_LIMIT:

        column_name = pd_row.get(

            "plot_id", f"{pd_row.get('first_name', '')} {pd_row.get('last_name', '')}"

        )

        enumerator_name = (

            f"{pd_row.get('enumerator_name', '')} {pd_row.get('enumerator_id', '')}"

        )

        print(

            f"Reached cell limit of excel for: {column_name} "

            " collected by: {enumerator_name}, so returning empty Polygon"

        )

        return shapely.geometry.polygon.Polygon()

 

    coordinates = []

    skip_coordinates_counter = 0

    for vertex_nr in range(len(polygon_string.split(";"))):

        if (

            (len(polygon_string.split(";")[vertex_nr]) == 0)

            or (

                float(polygon_string.split(";")[vertex_nr].strip().split(" ")[3])

                > accuracy_m

            )

            # or (polygon_string.split(";")[vertex_nr].strip().split(" ")[3] == "0.0")

        ):

            skip_coordinates_counter = skip_coordinates_counter + 1

            continue

        lon = float(polygon_string.split(";")[vertex_nr].strip().split(" ")[0])

        lat = float(polygon_string.split(";")[vertex_nr].strip().split(" ")[1])

        coordinates.append((lat, lon))

 

    if len(coordinates) < 3 or (len(coordinates) < (skip_coordinates_counter * 4)):

        column_name = pd_row.get(

            "plot_id", f"{pd_row.get('first_name', '')} {pd_row.get('last_name', '')}"

        )

        enumerator_name = (

            f"{pd_row.get('enumerator_name', '')} {pd_row.get('enumerator_id', '')}"

        )

        print(f"Dropped too many points for : {column_name} by {enumerator_name}")

        return shapely.geometry.polygon.Polygon()

    geom = shapely.geometry.polygon.Polygon(coordinates)

    return geom








def export_plots(df: pd.DataFrame, dir_path: Path) -> None:
    TIMESTAMP = datetime.now().strftime("%Y%m%dT%H%M%S")

    # Create all necessary directories
    backup_dir = dir_path
    ground_truth_dir = dir_path
    backup_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_dir.mkdir(parents=True, exist_ok=True)

    # Ensure we keep all relevant fields including enumerator
    export_columns = ['plot_id', 'enumerator_id', 'enumerator', 'collection_date', 'device',
                     'geometry', 'ecoregion', 'mrr_ratio', 'protruding_ratio_too_big', 
                     'overlapping_countries', 'in_country', 'duplicate_id', 'area_m2', 
                     'nr_vertices', 'nr_vertices_too_small', 'in_radius', 'overlap_ids', 
                     'reasons', 'valid', 'geojson']

    # df.to_excel(backup_dir / f"plots_{TIMESTAMP}.xlsx", index=False)
    df.to_excel(ground_truth_dir / "plots.xlsx", index=False)

    df_invalid = df[~df.valid]
    print(f"Number of invalid plots: {df_invalid.shape[0]}")
    df_invalid.to_excel(ground_truth_dir / "plots_invalid.xlsx", index=False)
    
    if df_invalid.shape[0] > 0:
       df_invalid.drop(columns="geojson").to_file(
           ground_truth_dir / "plots_invalid.geojson",
           driver="GeoJSON",
           index=False,
        )

    df_valid = df[df.valid]
    print(f"Number of valid plots: {df_valid.shape[0]}")
    df_valid.to_excel(ground_truth_dir / "plots_valid.xlsx", index=False)
    if df_valid.shape[0] > 0:
        df_valid.drop(columns="geojson").to_file(
            ground_truth_dir / "plots_valid.geojson",
            driver="GeoJSON",
            index=False,
        )

def generate_country_dropdown_json():
    """
    One-time utility to generate a JSON file for country dropdown options from the world-administrative-boundaries shapefile.
    Output: country_dropdown_options.json with a list of {"iso3": ..., "name": ...}
    """
    shp_path = "geo-feature-v1/datasets/world-administrative-boundaries/world-administrative-boundaries.shp"
    out_path = "country_dropdown_options.json"
    if os.path.exists(out_path):
        print(f"{out_path} already exists. Skipping generation.")
        return
    df = gpd.read_file(shp_path)
    # Use the columns you provided: 'iso3' and 'name'
    dropdown_list = [
        {"iso3": row["iso3"], "name": row["name"]}
        for _, row in df.iterrows()
        if pd.notnull(row["iso3"]) and pd.notnull(row["name"])
    ]
    # Remove duplicates (some shapefiles have multiple polygons per country)
    seen = set()
    unique_list = []
    for item in dropdown_list:
        key = (item["iso3"], item["name"])
        if key not in seen:
            unique_list.append(item)
            seen.add(key)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(unique_list, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(unique_list)} country options to {out_path}")

# Uncomment and run this function ONCE to generate the JSON file
generate_country_dropdown_json()