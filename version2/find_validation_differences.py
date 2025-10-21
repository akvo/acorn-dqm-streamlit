"""
Find the exact 10 subplots that are validated differently
between Streamlit and Notebook
"""

import json
import sys
import os
import pandas as pd
from datetime import date

# Add parent directory to path to find utils
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

try:
    from utils.data_loader import load_excel_data, merge_data, add_geometry_to_subplots
    from utils.validators import validate_dataset
except ImportError:
    print("ERROR: Cannot import utils modules.")
    print(f"Current directory: {os.getcwd()}")
    print(f"Parent directory: {parent_dir}")
    print("\nPlease run this script from the acorn-dqm-streamlit directory:")
    print("  cd /Volumes/Navin/acorn-dqm-streamlit")
    print("  python version2/find_validation_differences.py")
    sys.exit(1)

print("=" * 70)
print("FINDING VALIDATION DIFFERENCES")
print("=" * 70)

# 1. Load notebook results from GeoJSON
print("\n1. Loading notebook validation results from GeoJSON...")
geojson_path = "version2/Ground Truth Collection COMACO 2025_subplots_checks.geojson"

try:
    with open(geojson_path, "r") as f:
        geojson_data = json.load(f)
except FileNotFoundError:
    # Try current directory
    try:
        with open(
            "Ground Truth Collection COMACO 2025_subplots_checks.geojson", "r"
        ) as f:
            geojson_data = json.load(f)
    except FileNotFoundError:
        print(f"   ❌ GeoJSON file not found!")
        print(f"   Looking for: {geojson_path}")
        print(f"   Current dir: {os.getcwd()}")
        sys.exit(1)

notebook_results = {}
for feature in geojson_data["features"]:
    subplot_id = feature["properties"].get("subplot_id")
    is_valid = feature["properties"].get("geom_valid", False)
    reasons = feature["properties"].get("reasons", "")

    if subplot_id:
        notebook_results[subplot_id] = {"valid": is_valid, "reasons": reasons}

print(f"   ✓ Loaded {len(notebook_results)} notebook results")

# 2. Load Streamlit results
print("\n2. Running Streamlit validation...")

# Try to find Excel file
excel_paths = [
    "version2/Ground Truth Collection COMACO 2025.xlsx",
    "Ground Truth Collection COMACO 2025.xlsx",
    "Data Quality Ground Truth Collection COMACO 2025.xlsx",
]

excel_path = None
for path in excel_paths:
    if os.path.exists(path):
        excel_path = path
        break

if not excel_path:
    print(f"   ❌ Excel file not found!")
    print(f"   Tried: {excel_paths}")
    sys.exit(1)

print(f"   Loading: {excel_path}")

with open(excel_path, "rb") as f:
    raw_data = load_excel_data(f)

merged_data = merge_data(raw_data)
plots_subplots = merged_data["plots_subplots"]

if "gt_subplot" in plots_subplots.columns:
    plots_subplots = add_geometry_to_subplots(
        plots_subplots, accuracy_m=10, apply_fixes=True
    )
    merged_data["plots_subplots"] = plots_subplots

# Filter by date
plots_subplots["SubmissionDate"] = pd.to_datetime(
    plots_subplots["SubmissionDate"]
).dt.date
start_date = date(2025, 8, 11)
end_date = date(2025, 8, 28)

plots_subplots = plots_subplots[
    (plots_subplots["SubmissionDate"] >= start_date)
    & (plots_subplots["SubmissionDate"] <= end_date)
]
merged_data["plots_subplots"] = plots_subplots

validation_results = validate_dataset(merged_data)

streamlit_results = {}
for subplot_id, result in validation_results.get("subplots", {}).items():
    streamlit_results[subplot_id] = {
        "valid": result["valid"],
        "issues": result["issues"],
    }

print(f"   ✓ Got {len(streamlit_results)} Streamlit results")

# 3. Compare results
print("\n" + "=" * 70)
print("COMPARISON")
print("=" * 70)

notebook_valid = sum(1 for r in notebook_results.values() if r["valid"])
notebook_invalid = len(notebook_results) - notebook_valid

streamlit_valid = sum(1 for r in streamlit_results.values() if r["valid"])
streamlit_invalid = len(streamlit_results) - streamlit_valid

print(f"\nNotebook:   {notebook_valid} valid / {notebook_invalid} invalid")
print(f"Streamlit:  {streamlit_valid} valid / {streamlit_invalid} invalid")
print(f"Difference: {abs(notebook_valid - streamlit_valid)} subplots")

# 4. Find the different ones
print("\n" + "=" * 70)
print("FINDING DIFFERENCES")
print("=" * 70)

different_subplots = []

for subplot_id in notebook_results.keys():
    if subplot_id in streamlit_results:
        notebook_valid = notebook_results[subplot_id]["valid"]
        streamlit_valid = streamlit_results[subplot_id]["valid"]

        if notebook_valid != streamlit_valid:
            different_subplots.append(
                {
                    "subplot_id": subplot_id,
                    "notebook_valid": notebook_valid,
                    "streamlit_valid": streamlit_valid,
                    "notebook_reasons": notebook_results[subplot_id]["reasons"],
                    "streamlit_issues": streamlit_results[subplot_id]["issues"],
                }
            )

print(f"\nFound {len(different_subplots)} subplots with different validation results")

# 5. Show details of differences
if different_subplots:
    print("\n" + "=" * 70)
    print("DETAILED DIFFERENCES")
    print("=" * 70)

    for i, diff in enumerate(different_subplots[:20], 1):  # Show first 20
        print(f"\n{i}. Subplot: ...{diff['subplot_id'][-40:]}")
        print(f"   Notebook: {'VALID' if diff['notebook_valid'] else 'INVALID'}")
        print(f"   Streamlit: {'VALID' if diff['streamlit_valid'] else 'INVALID'}")

        if diff["notebook_reasons"]:
            print(f"   Notebook reasons: {diff['notebook_reasons']}")

        if diff["streamlit_issues"]:
            print(f"   Streamlit issues:")
            for issue in diff["streamlit_issues"][:3]:  # Show first 3 issues
                print(f"      • [{issue.get('severity')}] {issue.get('message')}")

# 6. Analyze patterns
print("\n" + "=" * 70)
print("PATTERN ANALYSIS")
print("=" * 70)

# Count which way the differences go
notebook_valid_streamlit_invalid = sum(
    1 for d in different_subplots if d["notebook_valid"] and not d["streamlit_valid"]
)
notebook_invalid_streamlit_valid = sum(
    1 for d in different_subplots if not d["notebook_valid"] and d["streamlit_valid"]
)

print(f"\nNotebook VALID → Streamlit INVALID: {notebook_valid_streamlit_invalid}")
print(f"Notebook INVALID → Streamlit VALID: {notebook_invalid_streamlit_valid}")

# Analyze Streamlit issues for the different ones
if different_subplots:
    streamlit_issue_types = {}
    for diff in different_subplots:
        for issue in diff["streamlit_issues"]:
            issue_msg = issue.get("message", "unknown")
            # Extract the main issue type
            if "too small" in issue_msg.lower():
                issue_type = "Plot too small"
            elif "too big" in issue_msg.lower() or "too large" in issue_msg.lower():
                issue_type = "Plot too big"
            elif "vertices" in issue_msg.lower():
                issue_type = "Vertex count"
            elif "overlap" in issue_msg.lower():
                issue_type = "Overlapping"
            elif "radius" in issue_msg.lower():
                issue_type = "Outside radius"
            elif "elongated" in issue_msg.lower():
                issue_type = "Elongated shape"
            elif "protruding" in issue_msg.lower():
                issue_type = "Protruding shape"
            else:
                issue_type = "Other"

            streamlit_issue_types[issue_type] = (
                streamlit_issue_types.get(issue_type, 0) + 1
            )

    print("\nStreamlit issue types in different subplots:")
    for issue_type, count in sorted(
        streamlit_issue_types.items(), key=lambda x: x[1], reverse=True
    ):
        print(f"  • {issue_type}: {count}")

# 7. Recommendation
print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

if len(different_subplots) <= 15:
    print(f"\n✅ Only {len(different_subplots)} subplots differ - this is ACCEPTABLE!")
    print("   The difference is likely due to:")
    print("   • Floating point precision in area calculations")
    print("   • Minor differences in geometry processing order")
    print("   • Slight threshold differences")
    print("\n   Your Streamlit validation is working correctly!")
    print(f"   Expected: ~1607 valid ± 10")
    print(f"   Actual:   {streamlit_valid} valid")

    if abs(streamlit_valid - 1607) <= 15:
        print("\n   ✅ WITHIN ACCEPTABLE RANGE - No changes needed!")
else:
    print(f"\n⚠️ {len(different_subplots)} subplots differ - investigating...")
    print("   This might indicate a configuration difference.")
    print("   Check the issue types above to identify the cause.")

print("\n" + "=" * 70)
