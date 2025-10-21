"""
Script to verify subplot validation data from Ground Truth Collection COMACO 2025
This extracts the key validation metrics shown in your screenshot
"""

import pandas as pd
from datetime import date

# Configuration (update these paths if needed)
file_name = "Ground Truth Collection COMACO 2025"
local_path = "/Volumes/Navin/acorn-dqm-streamlit/version2/"

# Date range for filtering
start_date = date(2025, 8, 11)
end_date = date(2025, 8, 28)

print("=" * 60)
print("SUBPLOT DATA VERIFICATION")
print("=" * 60)

try:
    # Read the data
    print(f"\n1. Reading data from: {local_path}{file_name}.xlsx")

    plots_df = pd.read_excel(
        f"{local_path}{file_name}.xlsx",
        sheet_name=0,
    ).rename(columns={"KEY": "PLOT_KEY"})

    subplot_df = pd.read_excel(
        f"{local_path}{file_name}.xlsx",
        sheet_name=1,
    ).rename(columns={"PARENT_KEY": "PLOT_KEY", "KEY": "SUBPLOT_KEY"})

    # Merge plots and subplots
    m_plots = pd.merge(plots_df, subplot_df, how="inner", on="PLOT_KEY")
    m_plots["SubmissionDate"] = pd.to_datetime(m_plots["SubmissionDate"]).dt.date

    # Filter by date range
    m_plots = m_plots[
        (m_plots["SubmissionDate"] >= start_date)
        & (m_plots["SubmissionDate"] <= end_date)
    ]

    print(f"   ✓ Data loaded successfully")
    print(f"   ✓ Date range: {start_date} to {end_date}")

    # Calculate Total Subplots
    total_subplots = len(m_plots)
    print(f"\n2. TOTAL SUBPLOTS: {total_subplots}")

    # Note: To get exact Valid/Invalid counts, you need to run the full geometry validation
    # from the AKVO_plot_subplot_check.ipynb notebook. This requires:
    # - geopandas installation
    # - Running the geometry validation pipeline

    print("\n" + "=" * 60)
    print("VALIDATION STATUS BREAKDOWN")
    print("=" * 60)

    # Check if geometry validation has been run
    if "geom_valid" in m_plots.columns:
        valid_count = m_plots["geom_valid"].sum()
        invalid_count = len(m_plots) - valid_count

        print(
            f"\n✓ Valid subplots:   {valid_count} ({valid_count/total_subplots*100:.1f}%)"
        )
        print(
            f"✗ Invalid subplots: {invalid_count} ({invalid_count/total_subplots*100:.1f}%)"
        )

        # Count issues
        if "reasons" in m_plots.columns:
            # Count non-empty reasons (each reason represents an issue)
            issues = m_plots[m_plots["reasons"].notna() & (m_plots["reasons"] != "")]
            total_issues = issues["reasons"].str.count(";").sum() + len(issues)
            print(f"\n📋 Total Issues: {total_issues}")

            # Show breakdown of issue types
            print("\nIssue Breakdown:")
            issue_types = {}
            for reasons in issues["reasons"].dropna():
                for reason in reasons.split(";"):
                    reason = reason.strip()
                    if reason:
                        issue_types[reason] = issue_types.get(reason, 0) + 1

            for issue, count in sorted(
                issue_types.items(), key=lambda x: x[1], reverse=True
            ):
                print(f"  • {issue}: {count}")
    else:
        print("\n⚠️  Geometry validation not yet run on this data.")
        print("    To get Valid/Invalid counts, you need to:")
        print("    1. Run the AKVO_plot_subplot_check.ipynb notebook")
        print("    2. This will create the validation columns")

    # Show some basic statistics
    print("\n" + "=" * 60)
    print("ADDITIONAL STATISTICS")
    print("=" * 60)
    print(f"\nTotal plots: {len(plots_df)}")
    print(f"Unique enumerators: {m_plots['enumerator'].nunique()}")
    print(
        f"Date range: {m_plots['SubmissionDate'].min()} to {m_plots['SubmissionDate'].max()}"
    )

    # Show enumerator breakdown
    print("\nSubplots by enumerator:")
    enumerator_counts = m_plots["enumerator"].value_counts()
    for enum, count in enumerator_counts.items():
        print(f"  • {enum}: {count}")

except FileNotFoundError:
    print(f"\n❌ ERROR: Could not find file '{file_name}.xlsx'")
    print("   Please make sure:")
    print("   1. The file name is correct")
    print("   2. The file is in the same folder as this script")
    print("   3. Update 'local_path' if the file is in a different folder")
except Exception as e:
    print(f"\n❌ ERROR: {str(e)}")
    print("\nPlease check that all required packages are installed:")
    print("  pip install pandas openpyxl")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
