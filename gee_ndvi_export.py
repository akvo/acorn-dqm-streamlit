import os
import sys
import datetime
import pandas as pd
import geopandas as gpd
import ee
import geemap
import argparse
from gt_config import PARTNER

# --- CONFIGURABLE ---
DEFAULT_SELECTED_PLOTS_PATH = os.path.join(os.path.dirname(__file__), '../output/selected_plots.geojson')
OUTPUT_XLSX_PATH = os.path.join(os.path.dirname(__file__), f'../output/selected_plots_ndvi_{PARTNER}.xlsx')
CLOUD_PCT_THRESHOLD = 20  # Max cloud cover %
N_IMAGES = 6  # Number of latest images to use

# --- INIT EE ---
try:
    ee.Initialize()
except Exception:
    ee.Authenticate()
    ee.Initialize()

def get_latest_s2_ndvi_images(aoi, n_images=6, cloud_pct=20):
    """Get the latest n_images Sentinel-2 images with low cloud cover and compute NDVI, within the last 1 year."""
    today = datetime.date.today()
    one_year_ago = today - datetime.timedelta(days=365)
    s2 = ee.ImageCollection('COPERNICUS/S2_SR') \
        .filterBounds(aoi) \
        .filter(ee.Filter.lte('CLOUDY_PIXEL_PERCENTAGE', cloud_pct)) \
        .filterDate(str(one_year_ago), str(today))
    # Sort by date descending and take the latest n_images
    s2 = s2.sort('system:time_start', False).limit(n_images)
    s2 = s2.map(lambda img: img.addBands(img.normalizedDifference(['B8', 'B4']).rename('NDVI')))
    return s2

def get_mean_ndvi_for_polygon_latest(geom, n_images=6, cloud_pct=20):
    aoi = ee.Geometry.Polygon(geom)
    s2 = get_latest_s2_ndvi_images(aoi, n_images, cloud_pct)
    ndvi_images = s2.select('NDVI')
    mean_ndvi_img = ndvi_images.mean()
    mean_dict = mean_ndvi_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=10,
        maxPixels=1e8
    )
    # Also get the dates of the images used
    image_list = s2.toList(s2.size())
    dates = []
    for i in range(s2.size().getInfo()):
        img = ee.Image(image_list.get(i))
        date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
        dates.append(date)
    return mean_dict.getInfo().get('NDVI'), dates

def load_selected_plots(input_path):
    ext = os.path.splitext(input_path)[1].lower()
    if ext in ['.geojson', '.json', '.shp', '.gpkg']:
        gdf = gpd.read_file(input_path)
    elif ext in ['.xlsx', '.xls']:
        df = pd.read_excel(input_path)
        # Try to find a geometry column
        geom_col = None
        for col in df.columns:
            if col.lower() == 'geometry':
                geom_col = col
                break
        if geom_col is None:
            raise ValueError('No geometry column found in Excel file.')
        gdf = gpd.GeoDataFrame(df, geometry=geom_col)
        if gdf.crs is None:
            gdf.set_crs('EPSG:4326', inplace=True)
    else:
        raise ValueError(f'Unsupported file extension: {ext}')
    # Ensure geometries are in WGS84
    if gdf.crs is not None and gdf.crs.to_string() != 'EPSG:4326':
        gdf = gdf.to_crs('EPSG:4326')
    return gdf

def main():
    parser = argparse.ArgumentParser(description='Compute mean NDVI for selected plots using Sentinel-2 imagery.')
    parser.add_argument('--input', type=str, default=DEFAULT_SELECTED_PLOTS_PATH, help='Path to selected plots file (GeoJSON, Shapefile, or Excel with geometry).')
    parser.add_argument('--output', type=str, default=OUTPUT_XLSX_PATH, help='Output Excel file for NDVI results.')
    args = parser.parse_args()

    gdf = load_selected_plots(args.input)
    results = []
    for idx, row in gdf.iterrows():
        plot_id = row['plot_id'] if 'plot_id' in row else idx
        geom = row['geometry']
        # Convert shapely geometry to geojson coordinates
        coords = None
        if geom.geom_type == 'Polygon':
            coords = [list(geom.exterior.coords)]
        elif geom.geom_type == 'MultiPolygon':
            coords = [list(poly.exterior.coords) for poly in geom.geoms]
        else:
            print(f"Skipping plot {plot_id}: unsupported geometry type {geom.geom_type}")
            continue
        try:
            mean_ndvi, dates = get_mean_ndvi_for_polygon_latest(coords, N_IMAGES, CLOUD_PCT_THRESHOLD)
        except Exception as e:
            print(f"Error for plot {plot_id}: {e}")
            mean_ndvi = None
            dates = []
        results.append({
            'plot_id': plot_id,
            'mean_ndvi': mean_ndvi,
            'image_dates': ','.join(dates)
        })
        print(f"Plot {plot_id}: mean NDVI = {mean_ndvi}, dates used: {dates}")
    # Save to Excel
    df = pd.DataFrame(results)
    df.to_excel(args.output, index=False)
    print(f"Saved NDVI results to {args.output}")

if __name__ == '__main__':
    main() 