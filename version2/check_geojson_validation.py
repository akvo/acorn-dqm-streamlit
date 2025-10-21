"""
Script to verify the validation counts from the generated GeoJSON file
This will confirm if 852 valid / 1648 total is correct
"""

import json
import pandas as pd

print("=" * 60)
print("GEOJSON VALIDATION CHECKER")
print("=" * 60)

# Check which GeoJSON file you have
geojson_files = [
    "Ground Truth Collection COMACO 2025_subplots_checks.geojson",
    "Ground Truth Collection AFOCO 2025_subplots_checks.geojson",
]

file_found = None
for filename in geojson_files:
    try:
        with open(filename, "r") as f:
            data = json.load(f)
        file_found = filename
        print(f"\n✓ Found file: {filename}")
        break
    except FileNotFoundError:
        continue

if not file_found:
    print("\n❌ No GeoJSON file found. Looking for:")
    for f in geojson_files:
        print(f"   - {f}")
    print("\nPlease run the AKVO_plot_subplot_check.ipynb notebook first.")
    exit()

# Extract features from GeoJSON
features = data.get("features", [])
total_subplots = len(features)

print(f"\n📊 Total features in GeoJSON: {total_subplots}")

# Count valid and invalid based on properties
valid_count = 0
invalid_count = 0
issues_list = []

for feature in features:
    props = feature.get("properties", {})

    # Check the geom_valid property
    is_valid = props.get("geom_valid", False)
    reasons = props.get("reasons", "")

    if is_valid:
        valid_count += 1
    else:
        invalid_count += 1
        if reasons:
            # Count individual issues (separated by semicolons)
            issue_count = reasons.count(";") + 1 if reasons else 0
            issues_list.append(reasons)

# Calculate total issues
total_issues = sum(reason.count(";") + 1 for reason in issues_list if reason)

print("\n" + "=" * 60)
print("VALIDATION RESULTS")
print("=" * 60)

print(f"\n✅ Valid subplots:   {valid_count}")
print(f"❌ Invalid subplots: {invalid_count}")
print(f"📋 Total subplots:   {total_subplots}")
print(f"⚠️  Total issues:     {total_issues}")

# Calculate percentages
if total_subplots > 0:
    valid_pct = (valid_count / total_subplots) * 100
    invalid_pct = (invalid_count / total_subplots) * 100

    print(f"\n📈 Valid percentage:   {valid_pct:.1f}%")
    print(f"📉 Invalid percentage: {invalid_pct:.1f}%")

# Verify the math
print("\n" + "=" * 60)
print("VERIFICATION")
print("=" * 60)

checks = []
checks.append(
    (
        "Total = Valid + Invalid",
        total_subplots == valid_count + invalid_count,
        f"{total_subplots} = {valid_count} + {invalid_count}",
    )
)

checks.append(
    (
        "Your screenshot total (1648)",
        total_subplots == 1648,
        f"{total_subplots} == 1648",
    )
)

checks.append(
    ("Your screenshot valid (852)", valid_count == 852, f"{valid_count} == 852")
)

checks.append(
    ("Your screenshot invalid (796)", invalid_count == 796, f"{invalid_count} == 796")
)

all_correct = True
for check_name, is_correct, detail in checks:
    status = "✅" if is_correct else "❌"
    print(f"\n{status} {check_name}")
    print(f"   {detail}")
    if not is_correct:
        all_correct = False

# Show issue breakdown
if issues_list:
    print("\n" + "=" * 60)
    print("TOP VALIDATION ISSUES")
    print("=" * 60)

    # Count each type of issue
    issue_types = {}
    for reasons in issues_list:
        if reasons:
            for issue in reasons.split(";"):
                issue = issue.strip()
                if issue:
                    issue_types[issue] = issue_types.get(issue, 0) + 1

    # Sort by count
    sorted_issues = sorted(issue_types.items(), key=lambda x: x[1], reverse=True)

    print("\nIssue breakdown:")
    for issue, count in sorted_issues[:10]:  # Show top 10
        print(f"  • {issue}: {count}")

# Final verdict
print("\n" + "=" * 60)
print("FINAL VERDICT")
print("=" * 60)

if all_correct:
    print("\n🎉 ALL CHECKS PASSED!")
    print("   Your screenshot data (852/1648) is CORRECT! ✓")
else:
    print("\n⚠️  DISCREPANCY FOUND")
    print("   The numbers don't match. Please check:")
    print("   1. Is this the correct GeoJSON file?")
    print("   2. Was the data filtered correctly?")
    print("   3. Run the notebook again to regenerate")

print("\n" + "=" * 60)
