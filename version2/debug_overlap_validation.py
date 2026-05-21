"""
Debug script to investigate false positive overlap detection
for plot uuid:45e321be-18bf-48da-9452-b92835a6dea8, subplots 4, 6, 13

Run from project root: python version2/debug_overlap_validation.py
"""

import json
import pandas as pd
import geopandas as gpd
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.gt_check_functions import (
    wgs_to_utm,
    calculate_area,
    geom_from_scto_str,
    geom_to_utm,
)

crs = "EPSG:4326"


def main():
    print("=" * 80)
    print("DEBUG: Overlap Validation Investigation")
    print("=" * 80)

    # Load cached data
    cache_file = "data_cache/AFEC_gt.json"
    print(f"\n1. Loading cached data from {cache_file}...")

    with open(cache_file, "r") as f:
        data = json.load(f)

    print(f"   Total records in cache: {len(data)}")

    # Convert to DataFrame
    main_df = pd.DataFrame(data)
    print(f"   Columns available: {len(main_df.columns)}")

    # Find the specific plot
    plot_key = "uuid:45e321be-18bf-48da-9452-b92835a6dea8"
    print(f"\n2. Searching for plot: {plot_key}")

    if "KEY" in main_df.columns:
        plot_data = main_df[main_df["KEY"] == plot_key]
        print(f"   Found {len(plot_data)} record(s) for this plot")

        if len(plot_data) == 0:
            print("\n   ERROR: Plot not found. Available keys:")
            print(main_df["KEY"].head(10).tolist())
            return
    else:
        print("   ERROR: 'KEY' column not found")
        print(f"   Available columns: {main_df.columns.tolist()[:20]}...")
        return

    # Find subplot geometry columns
    print("\n3. Looking for subplot geometry columns...")
    subplot_cols = [c for c in main_df.columns if "subplot" in c.lower()]
    print(f"   Subplot-related columns: {subplot_cols[:10]}...")

    gps_cols = [
        c
        for c in main_df.columns
        if "gps" in c.lower() or "geoshape" in c.lower()
    ]
    print(f"   GPS-related columns: {gps_cols[:10]}...")

    # Look for indexed subplot columns (e.g., subplots[0]-gt_subplot_gps)
    indexed_cols = [
        c for c in main_df.columns if "[" in c and "subplot" in c.lower()
    ]
    print(f"   Indexed subplot columns: {indexed_cols[:10]}...")

    # Extract subplot GPS data for the specific plot
    print("\n4. Extracting subplot geometries...")

    plot_row = plot_data.iloc[0]

    # Find all subplot GPS columns with indices
    subplot_gps_cols = sorted(
        [c for c in main_df.columns if "gt_subplot_gps" in c.lower()]
    )
    print(f"   Found {len(subplot_gps_cols)} subplot GPS columns")

    if not subplot_gps_cols:
        # Try alternative naming
        subplot_gps_cols = sorted(
            [
                c
                for c in main_df.columns
                if "subplot" in c.lower()
                and ("gps" in c.lower() or "geoshape" in c.lower())
            ]
        )
        print(f"   Alternative search found: {subplot_gps_cols[:5]}...")

    # Parse geometries
    geometries = []
    subplot_ids = []

    for col in subplot_gps_cols:
        value = plot_row.get(col)
        if pd.notna(value) and value:
            # Extract subplot index from column name
            try:
                if "[" in col:
                    idx = int(col.split("[")[1].split("]")[0])
                else:
                    idx = len(geometries)

                # Parse geometry
                geom, metadata = geom_from_scto_str(
                    plot_row.to_dict(),
                    col,
                    accuracy_m=10,
                    accuracy_zero_valid=True,
                )

                if not geom.is_empty:
                    geometries.append(geom)
                    subplot_ids.append(idx + 1)  # 1-indexed subplot numbers
                    print(
                        f"   Subplot {idx + 1}: Valid geometry with area ~{geom_to_utm(geom).area:.1f} m²"
                    )
                else:
                    print(
                        f"   Subplot {idx + 1}: Empty geometry - {metadata.get('reason', 'unknown')}"
                    )
            except Exception as e:
                print(f"   Error parsing {col}: {e}")

    print(f"\n   Total valid geometries: {len(geometries)}")

    if len(geometries) < 2:
        print("   ERROR: Not enough geometries to check for overlap")
        return

    # Create GeoDataFrame
    print("\n5. Creating GeoDataFrame for overlap analysis...")
    gdf = gpd.GeoDataFrame(
        {"subplot_id": subplot_ids, "geometry": geometries}, crs=crs
    )

    print(f"   GeoDataFrame created with {len(gdf)} subplots")

    # Check which subplots we're interested in
    target_subplots = [4, 6, 13]
    available_targets = [s for s in target_subplots if s in subplot_ids]
    print(
        f"   Target subplots {target_subplots}: available = {available_targets}"
    )

    # Run overlap validation step by step
    print("\n6. Running overlap validation step-by-step...")

    print("\n   Step 6a: Convert to UTM...")
    gdf_utm = wgs_to_utm(gdf.copy())
    print(f"   CRS after conversion: {gdf_utm.crs}")

    print("\n   Step 6b: Apply -5m buffer...")
    gdf_buffered = gdf_utm.copy()
    gdf_buffered["geometry"] = gdf_buffered.geometry.buffer(-5)

    for idx, row in gdf_buffered.iterrows():
        subplot_id = row["subplot_id"]
        geom = row["geometry"]
        original_area = gdf_utm.loc[idx, "geometry"].area
        buffered_area = geom.area if not geom.is_empty else 0
        print(
            f"   Subplot {subplot_id}: {original_area:.1f} m² -> {buffered_area:.1f} m² (after -5m buffer)"
        )
        if geom.is_empty:
            print("      WARNING: Geometry became EMPTY after buffer!")
        elif not geom.is_valid:
            print("      WARNING: Geometry became INVALID after buffer!")

    print("\n   Step 6c: Convert back to WGS84...")
    gdf_wgs = gdf_buffered.to_crs(crs)

    print("\n   Step 6d: Calculate areas...")
    gdf_with_area = calculate_area(gdf_wgs.copy(), geodisic=True)
    for idx, row in gdf_with_area.iterrows():
        print(
            f"   Subplot {row['subplot_id']}: area_m2 = {row['area_m2']:.1f}"
        )

    print("\n   Step 6e: Perform overlay (self-intersection)...")
    try:
        overlay_result = gdf_with_area.overlay(
            gdf_with_area, keep_geom_type=False
        )
        print(f"   Overlay produced {len(overlay_result)} results")

        # Filter to different subplots only
        overlay_filtered = overlay_result[
            overlay_result["subplot_id_1"] != overlay_result["subplot_id_2"]
        ]
        print(
            f"   After filtering (different subplots): {len(overlay_filtered)} results"
        )

        if len(overlay_filtered) > 0:
            print("\n   Overlapping pairs found:")
            # Calculate overlap areas
            overlay_filtered = calculate_area(
                overlay_filtered.copy(), geodisic=True
            )

            for idx, row in overlay_filtered.iterrows():
                s1 = row["subplot_id_1"]
                s2 = row["subplot_id_2"]
                intersection_area = row["area_m2"]
                area1 = row["area_m2_1"]
                area2 = row["area_m2_2"]
                min_area = min(area1, area2)
                ratio = (
                    intersection_area / min_area
                    if min_area > 0
                    else float("inf")
                )
                geom_type = row["geometry"].geom_type

                print(f"\n   Subplot {s1} <-> Subplot {s2}:")
                print(f"      Geometry type: {geom_type}")
                print(f"      Intersection area: {intersection_area:.2f} m²")
                print(f"      Area 1: {area1:.1f} m², Area 2: {area2:.1f} m²")
                print(f"      Min area: {min_area:.1f} m²")
                print(f"      Overlay ratio: {ratio:.4f}")
                print(f"      Would be flagged (ratio > 0.5): {ratio > 0.5}")

                if s1 in target_subplots or s2 in target_subplots:
                    print("      *** THIS INVOLVES TARGET SUBPLOTS ***")
        else:
            print("   No overlapping pairs found after -5m buffer")

    except Exception as e:
        print(f"   ERROR during overlay: {e}")
        import traceback

        traceback.print_exc()

    # Also check without the buffer to see original overlap
    print("\n7. Checking overlap WITHOUT buffer (for comparison)...")
    gdf_no_buffer = gdf.copy()
    gdf_no_buffer = calculate_area(gdf_no_buffer, geodisic=True)

    try:
        overlay_no_buffer = gdf_no_buffer.overlay(
            gdf_no_buffer, keep_geom_type=False
        )
        overlay_no_buffer = overlay_no_buffer[
            overlay_no_buffer["subplot_id_1"]
            != overlay_no_buffer["subplot_id_2"]
        ]
        print(f"   Overlapping pairs without buffer: {len(overlay_no_buffer)}")

        if len(overlay_no_buffer) > 0:
            overlay_no_buffer = calculate_area(
                overlay_no_buffer.copy(), geodisic=True
            )
            for idx, row in overlay_no_buffer.iterrows():
                s1 = row["subplot_id_1"]
                s2 = row["subplot_id_2"]
                intersection_area = row["area_m2"]
                print(
                    f"   Subplot {s1} <-> Subplot {s2}: intersection = {intersection_area:.2f} m²"
                )
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
