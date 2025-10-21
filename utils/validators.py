"""
Validation logic ported from notebooks
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon
from typing import Dict, List, Tuple
import config
from .geometry_utils import *


class PlotValidator:
    """Validates plot-level data"""

    def __init__(self):
        self.issues = []

    def validate(self, plot_gdf: gpd.GeoDataFrame) -> Dict:
        """
        Validate plot geometry

        Returns:
            Dictionary with validation results
        """
        self.issues = []

        if plot_gdf.empty:
            return {"valid": False, "issues": ["No plot data"]}

        # Check geometry exists
        if "geometry" not in plot_gdf.columns:
            return {"valid": False, "issues": ["No geometry column"]}

        # For now, plots are considered valid if they exist
        return {"valid": True, "issues": []}


class SubplotValidator:
    """Validates subplot-level data"""

    def __init__(self):
        self.issues = []

    def validate(self, subplot_row: pd.Series) -> Dict:
        """
        Validate single subplot

        Returns:
            Dictionary with validation results and issues
        """
        self.issues = []
        geom = subplot_row.get("geometry")

        # Check if geometry exists
        if geom is None or geom.is_empty:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "critical",
                    "message": "Empty geometry",
                    "field": "geometry",
                }
            )
            return {"valid": False, "issues": self.issues}

        # Check if geometry is valid
        if not geom.is_valid:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "error",
                    "message": "Invalid geometry",
                    "field": "geometry",
                }
            )

        # Check area
        area = calculate_area_m2(geom, geodesic=True)
        subplot_row["area_m2"] = area

        if area < config.MIN_SUBPLOT_AREA_SIZE:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "error",
                    "message": f"Plot too small ({area:.1f} m² < {config.MIN_SUBPLOT_AREA_SIZE} m²)",
                    "field": "area_m2",
                    "value": area,
                    "threshold": config.MIN_SUBPLOT_AREA_SIZE,
                }
            )

        if area > config.MAX_SUBPLOT_AREA_SIZE:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "error",
                    "message": f"Plot too large ({area:.1f} m² > {config.MAX_SUBPLOT_AREA_SIZE} m²)",
                    "field": "area_m2",
                    "value": area,
                    "threshold": config.MAX_SUBPLOT_AREA_SIZE,
                }
            )

        # Check vertices
        vertices = count_vertices(geom)
        if vertices <= config.MAX_VERTICES:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "warning",
                    "message": f"Too few vertices ({vertices} ≤ {config.MAX_VERTICES})",
                    "field": "nr_vertices",
                    "value": vertices,
                    "threshold": config.MAX_VERTICES,
                }
            )

        # Check length-width ratio
        lw_ratio = length_width_ratio(geom, geodesic=True)
        if lw_ratio and lw_ratio > config.THRESHOLD_LENGTH_WIDTH:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "warning",
                    "message": f"Elongated shape (ratio: {lw_ratio:.2f} > {config.THRESHOLD_LENGTH_WIDTH})",
                    "field": "length_width_ratio",
                    "value": lw_ratio,
                    "threshold": config.THRESHOLD_LENGTH_WIDTH,
                }
            )

        # Check protruding ratio
        prot_ratio = calculate_protruding_ratio(geom)
        if prot_ratio and prot_ratio > config.THRESHOLD_PROTRUDING_RATIO:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "warning",
                    "message": f"Irregular/protruding shape (ratio: {prot_ratio:.2f} > {config.THRESHOLD_PROTRUDING_RATIO})",
                    "field": "protruding_ratio",
                    "value": prot_ratio,
                    "threshold": config.THRESHOLD_PROTRUDING_RATIO,
                }
            )

        # Check radius
        within_radius = check_within_radius(geom, config.THRESHOLD_WITHIN_RADIUS)
        if not within_radius:
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "warning",
                    "message": f"Points outside {config.THRESHOLD_WITHIN_RADIUS}m radius from center",
                    "field": "in_radius",
                    "value": False,
                    "threshold": config.THRESHOLD_WITHIN_RADIUS,
                }
            )

        # Check for overlaps (if overlap data exists)
        if (
            "overlap_ids" in subplot_row
            and pd.notna(subplot_row["overlap_ids"])
            and subplot_row["overlap_ids"] != ""
        ):
            overlap_pct = subplot_row.get("percentage_overlap", 0)
            self.issues.append(
                {
                    "type": "geometry",
                    "severity": "error",
                    "message": f"Overlapping with other subplot(s): {subplot_row['overlap_ids']} ({overlap_pct:.0%})",
                    "field": "overlap_ids",
                    "value": subplot_row["overlap_ids"],
                    "percentage": overlap_pct,
                }
            )

        is_valid = (
            len([i for i in self.issues if i["severity"] in ["critical", "error"]]) == 0
        )

        return {
            "valid": is_valid,
            "issues": self.issues,
            "area_m2": area,
            "vertices": vertices,
            "length_width_ratio": lw_ratio,
            "protruding_ratio": prot_ratio,
            "within_radius": within_radius,
        }


class VegetationValidator:
    """Validates vegetation/species data"""

    def __init__(self):
        self.issues = []

    def validate(self, veg_row: pd.Series) -> Dict:
        """
        Validate vegetation entry
        """
        self.issues = []

        # Check if species marked as "other"
        if pd.notna(veg_row.get("other_species")):
            species_name = veg_row.get("other_species", "")
            if species_name.lower() == "other":
                self.issues.append(
                    {
                        "type": "species",
                        "severity": "warning",
                        "message": "Species marked as 'other' - needs botanical verification",
                        "field": "other_species",
                        "value": species_name,
                    }
                )
            else:
                self.issues.append(
                    {
                        "type": "species",
                        "severity": "info",
                        "message": f"Non-standard species name: '{species_name}' - needs verification",
                        "field": "other_species",
                        "value": species_name,
                    }
                )

        # Check if coverage used for woody species
        species_type = veg_row.get("vegetation_species_type", "")
        has_measurements = pd.notna(veg_row.get("tree_height_m"))
        coverage = veg_row.get("coverage_vegetation", 0)

        if species_type == "woody" and not has_measurements and coverage > 0:
            self.issues.append(
                {
                    "type": "species",
                    "severity": "warning",
                    "message": "Woody species measured as coverage only - should have individual measurements",
                    "field": "coverage_vegetation",
                    "value": coverage,
                }
            )

        # Check tree count
        tree_count = veg_row.get("vegetation_type_number", 0)
        if tree_count == 0 and coverage == 0:
            self.issues.append(
                {
                    "type": "missing_data",
                    "severity": "error",
                    "message": "No trees and no coverage recorded",
                    "field": "vegetation_type_number",
                }
            )

        is_valid = (
            len([i for i in self.issues if i["severity"] in ["critical", "error"]]) == 0
        )

        return {"valid": is_valid, "issues": self.issues}


class MeasurementValidator:
    """Validates tree measurements"""

    def __init__(self):
        self.issues = []

    def validate(self, measurement_row: pd.Series, group_median: Dict = None) -> Dict:
        """
        Validate tree measurement

        Args:
            measurement_row: Single measurement
            group_median: Median values for the tree group (for outlier detection)
        """
        self.issues = []

        # Check height
        height = measurement_row.get("tree_height_m")
        if pd.notna(height):
            if height > config.MAX_TREE_HEIGHT:
                self.issues.append(
                    {
                        "type": "measurement",
                        "severity": "error",
                        "message": f"Tree height too large ({height}m > {config.MAX_TREE_HEIGHT}m)",
                        "field": "tree_height_m",
                        "value": height,
                        "threshold": config.MAX_TREE_HEIGHT,
                    }
                )

        if height < config.MIN_TREE_HEIGHT:
            self.issues.append(
                {
                    "type": "measurement",
                    "severity": "error",
                    "message": f"Tree height too small ({height}m < {config.MIN_TREE_HEIGHT}m)",
                    "field": "tree_height_m",
                    "value": height,
                    "threshold": config.MIN_TREE_HEIGHT,
                }
            )

        # Check against group median for outliers
        if group_median and "height" in group_median:
            median_height = group_median["height"]
            if median_height > 0:
                if height > median_height * config.HEIGHT_OUTLIER_RATIO:
                    self.issues.append(
                        {
                            "type": "measurement",
                            "severity": "warning",
                            "message": f"Height outlier: {height}m (group median: {median_height}m)",
                            "field": "tree_height_m",
                            "value": height,
                            "median": median_height,
                        }
                    )
                elif height < median_height / config.HEIGHT_OUTLIER_RATIO:
                    self.issues.append(
                        {
                            "type": "measurement",
                            "severity": "warning",
                            "message": f"Height outlier (low): {height}m (group median: {median_height}m)",
                            "field": "tree_height_m",
                            "value": height,
                            "median": median_height,
                        }
                    )

        # Check circumference at breast height
        circ_bh = measurement_row.get("circumference_bh")
        if pd.notna(circ_bh):
            if circ_bh > config.MAX_CIRCUMFERENCE_BH:
                self.issues.append(
                    {
                        "type": "measurement",
                        "severity": "warning",
                        "message": f"Circumference BH very large ({circ_bh}cm > {config.MAX_CIRCUMFERENCE_BH}cm)",
                        "field": "circumference_bh",
                        "value": circ_bh,
                        "threshold": config.MAX_CIRCUMFERENCE_BH,
                    }
                )

            # Check against planting year
            year_planted = measurement_row.get("tree_year_planted")
            if pd.notna(year_planted):
                try:
                    from datetime import datetime

                    year = pd.to_datetime(year_planted).year
                    current_year = datetime.now().year
                    tree_age = current_year - year

                    # Very rough check: circumference shouldn't exceed age * 20cm
                    expected_max = tree_age * 20
                    if circ_bh > expected_max and tree_age < 10:
                        self.issues.append(
                            {
                                "type": "measurement",
                                "severity": "error",
                                "message": f"Circumference ({circ_bh}cm) unlikely for tree age ({tree_age} years)",
                                "field": "circumference_bh",
                                "value": circ_bh,
                                "tree_age": tree_age,
                            }
                        )
                except:
                    pass

        # Check circumference at 10cm
        circ_10cm = measurement_row.get("circumference_10cm")
        if pd.notna(circ_10cm):
            if circ_10cm > config.MAX_CIRCUMFERENCE_10CM:
                self.issues.append(
                    {
                        "type": "measurement",
                        "severity": "warning",
                        "message": f"Circumference 10cm very large ({circ_10cm}cm > {config.MAX_CIRCUMFERENCE_10CM}cm)",
                        "field": "circumference_10cm",
                        "value": circ_10cm,
                        "threshold": config.MAX_CIRCUMFERENCE_10CM,
                    }
                )

        # Check stem counts
        stems_bh = measurement_row.get("nr_stems_bh")
        if pd.notna(stems_bh) and stems_bh > config.MAX_STEMS_BH:
            self.issues.append(
                {
                    "type": "measurement",
                    "severity": "warning",
                    "message": f"Very high stem count at BH ({stems_bh} > {config.MAX_STEMS_BH})",
                    "field": "nr_stems_bh",
                    "value": stems_bh,
                    "threshold": config.MAX_STEMS_BH,
                }
            )

        # Check pruning/coppicing consistency
        prune_height = measurement_row.get("prune_height")
        coppice_height = measurement_row.get("coppiced_height")

        if pd.notna(prune_height) and pd.notna(coppice_height):
            if prune_height > coppice_height:
                self.issues.append(
                    {
                        "type": "measurement",
                        "severity": "warning",
                        "message": f"Prune height ({prune_height}m) > coppice height ({coppice_height}m) - check consistency",
                        "field": "prune_height",
                        "value": prune_height,
                        "coppice_height": coppice_height,
                    }
                )

        is_valid = (
            len([i for i in self.issues if i["severity"] in ["critical", "error"]]) == 0
        )

        return {"valid": is_valid, "issues": self.issues}


def validate_dataset(merged_data: Dict[str, pd.DataFrame]) -> Dict:
    """
    Validate entire dataset

    Returns:
        Dictionary with validation results for all levels
    """
    plots_subplots = merged_data["plots_subplots"]
    plots_vegetation = merged_data["plots_vegetation"]
    plots_measurements = merged_data["plots_measurements"]

    results = {"plots": {}, "subplots": {}, "vegetation": {}, "measurements": {}}

    # Validate subplots
    subplot_validator = SubplotValidator()
    for idx, row in plots_subplots.iterrows():
        if "SUBPLOT_KEY" in row and pd.notna(row["SUBPLOT_KEY"]):
            subplot_id = row["SUBPLOT_KEY"]
            validation = subplot_validator.validate(row)
            results["subplots"][subplot_id] = validation

    # Validate vegetation
    veg_validator = VegetationValidator()
    for idx, row in plots_vegetation.iterrows():
        if "VEGETATION_KEY" in row and pd.notna(row["VEGETATION_KEY"]):
            veg_id = row["VEGETATION_KEY"]
            validation = veg_validator.validate(row)
            results["vegetation"][veg_id] = validation

    # Validate measurements
    meas_validator = MeasurementValidator()

    # Group measurements by vegetation group for outlier detection
    if "VEGETATION_KEY" in plots_measurements.columns:
        for veg_key, group in plots_measurements.groupby("VEGETATION_KEY"):
            if pd.notna(veg_key):
                # Calculate group medians
                group_median = {
                    "height": group["tree_height_m"].median(),
                    "circumference_bh": (
                        group["circumference_breast_height"].median()
                        if "circumference_breast_height" in group.columns
                        else None
                    ),
                }

                for idx, row in group.iterrows():
                    if "MEASUREMENT_KEY" in row and pd.notna(row["MEASUREMENT_KEY"]):
                        meas_id = row["MEASUREMENT_KEY"]
                        validation = meas_validator.validate(row, group_median)
                        results["measurements"][meas_id] = validation

    return results


def aggregate_validation_results(validation_results: Dict) -> Dict:
    """
    Aggregate validation results to plot level
    """
    summary = {
        "total_subplots": len(validation_results.get("subplots", {})),
        "valid_subplots": 0,
        "invalid_subplots": 0,
        "total_issues": 0,
        "issues_by_type": {},
        "issues_by_severity": {},
    }

    # Count subplot issues
    for subplot_id, result in validation_results.get("subplots", {}).items():
        if result["valid"]:
            summary["valid_subplots"] += 1
        else:
            summary["invalid_subplots"] += 1

        for issue in result.get("issues", []):
            summary["total_issues"] += 1

            issue_type = issue.get("type", "unknown")
            severity = issue.get("severity", "unknown")

            summary["issues_by_type"][issue_type] = (
                summary["issues_by_type"].get(issue_type, 0) + 1
            )
            summary["issues_by_severity"][severity] = (
                summary["issues_by_severity"].get(severity, 0) + 1
            )

    # Add vegetation and measurement issues
    for veg_id, result in validation_results.get("vegetation", {}).items():
        for issue in result.get("issues", []):
            summary["total_issues"] += 1
            issue_type = issue.get("type", "unknown")
            severity = issue.get("severity", "unknown")
            summary["issues_by_type"][issue_type] = (
                summary["issues_by_type"].get(issue_type, 0) + 1
            )
            summary["issues_by_severity"][severity] = (
                summary["issues_by_severity"].get(severity, 0) + 1
            )

    for meas_id, result in validation_results.get("measurements", {}).items():
        for issue in result.get("issues", []):
            summary["total_issues"] += 1
            issue_type = issue.get("type", "unknown")
            severity = issue.get("severity", "unknown")
            summary["issues_by_type"][issue_type] = (
                summary["issues_by_type"].get(issue_type, 0) + 1
            )
            summary["issues_by_severity"][severity] = (
                summary["issues_by_severity"].get(severity, 0) + 1
            )

    return summary
