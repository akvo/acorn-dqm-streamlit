from pathlib import Path

# from src.ground_truth.akvo_gt_check.excel_parser import ExcelParser
from excel_parser import ExcelParser

#from src.ground_truth.akvo_gt_check.gt_check_functions import (
from gt_check_functions import (
    add_ecoregion, calculate_area, collect_reasons_subplot, collect_reasons_plot, export_plots,
    export_subplots, fix_geometry, to_geojson, validate_country,
    validate_duplicate_id, validate_length_width_ratio, validate_nr_vertices,
    validate_overlap, validate_protruding_ratio, validate_within_radius)
# from src.ground_truth.akvo_gt_check.gt_config import (COUNTRY, CROP,
from gt_config import (COUNTRY, CROP,
                                                      
                                                      MAX_GT_PLOT_AREA_SIZE,
                                                      MAX_SUBPLOT_AREA_SIZE,
                                                      MIN_GT_PLOT_AREA_SIZE,
                                                      MIN_SUBPLOT_AREA_SIZE,
                                                      PARTNER)

# dir_output = Path.cwd() / "data" / "onboarding" / PARTNER / COUNTRY / CROP
dir_output = Path.cwd() / "/Users/joy/Downloads/Rabobank_ACORN_Initiative/AcornGT/output" / PARTNER


def overlap_filter(x):
    return x[
        (x.in_country)
        & (x.in_radius)
        & (MIN_SUBPLOT_AREA_SIZE < x.area_m2)
        & (x.area_m2 < MAX_SUBPLOT_AREA_SIZE)
        & (~x.protruding_ratio_too_big)
        & (~x.nr_vertices_too_small)
    ]


print(f"Creating subplots files for {PARTNER} {COUNTRY}\n")

df_subplots = (
    ExcelParser.parse_subplots(dir_output)
    .pipe(fix_geometry)
    .pipe(add_ecoregion, "subplot_id")
    .pipe(validate_length_width_ratio, 2)
    .pipe(validate_protruding_ratio, 1.55)
    .pipe(validate_country)
    .pipe(validate_duplicate_id, "subplot_id")
    .pipe(calculate_area)
    .pipe(validate_nr_vertices)
    .pipe(validate_within_radius, radius=40)
    .pipe(
        validate_overlap,
        "subplot_id",
        min_overlap=0.1,
        buffer=-5,
        filter=overlap_filter,
    )
    .assign(
        reasons=lambda x: x.apply(collect_reasons_subplot, axis=1),
        valid=lambda x: x.reasons.apply(len) == 0,
        geojson=lambda x: x.apply(
            lambda x: to_geojson(x.geometry, x.subplot_id), axis=1
        ),
    )
    .pipe(export_subplots, dir_output)
)


def overlap_filter(x):
    return x[
        (x.in_country)
        & (x.in_radius)
        & (MIN_GT_PLOT_AREA_SIZE < x.area_m2)
        & (x.area_m2 < MAX_GT_PLOT_AREA_SIZE)
        & (~x.protruding_ratio_too_big)
        & (~x.nr_vertices_too_small)
    ]


print(f"Creating plots files for {PARTNER} {COUNTRY}\n")


df_plots = (
    ExcelParser.parse_plots(dir_output)
    .pipe(fix_geometry)
    .pipe(add_ecoregion, "plot_id")
    .pipe(validate_protruding_ratio, 1.55)
    .pipe(validate_country)
    .pipe(validate_duplicate_id, "plot_id")
    .pipe(calculate_area)
    .pipe(validate_nr_vertices)
    .pipe(validate_within_radius, radius=200)
    .pipe(
        validate_overlap,
        "plot_id",
        min_overlap=0.1,
        buffer=0,
        filter=overlap_filter,
    )
    .assign(
        reasons=lambda x: x.apply(collect_reasons_plot, axis=1),
        valid=lambda x: x.reasons.apply(len) == 0,
        geojson=lambda x: x.apply(lambda x: to_geojson(x.geometry, x.plot_id), axis=1),
    )
    .pipe(export_plots, dir_output)
)

print("\nDone!")
