"""
Exploratory Page - Deep dive into GT and DQ data
Combines both datasets for comprehensive analysis
"""

import streamlit as st
import pandas as pd
import re
import os
import config
from ui.components import require_auth
from utils.session_manager import load_data

st.set_page_config(
    page_title="Exploratory - Ground Truth DQM",
    page_icon="🔍",
    layout="wide",
)

config.refresh_partner_config()

# Authentication check
require_auth()

# ============================================
# PAGE HEADER
# ============================================

st.title("🔍 Exploratory Analysis")
st.markdown("Deep dive into GT and DQ data for comprehensive analysis")

# ============================================
# DATA AVAILABILITY CHECK
# ============================================

# Check GT data (mandatory) - using persistent data store
data = load_data("gt")
if data is None:
    st.warning("⚠️ No GT data loaded. Please fetch GT data from the home page.")
    if st.button("← Go to Home"):
        st.switch_page("app.py")
    st.stop()
st.session_state.data = data  # Ensure session state is in sync

# Check DQ data (optional) - using persistent data store
dq_data_loaded = load_data("dq")
dq_loaded = dq_data_loaded is not None
if dq_loaded:
    st.session_state.dq_data = dq_data_loaded  # Ensure session state is in sync
else:
    st.info("ℹ️ DQ data not loaded. Some comparison features will be unavailable.")

# ============================================
# GET DATA
# ============================================

gt_gdf = st.session_state.data["subplots"].copy()
gt_raw = st.session_state.data.get("raw_data", {})

dq_gdf = None
dq_raw = {}
if dq_loaded:
    dq_gdf = st.session_state.dq_data["subplots"].copy()
    dq_raw = st.session_state.dq_data.get("raw_data", {})

# Combine GT and DQ data for filters
combined_gdf = gt_gdf.copy()
if dq_loaded and dq_gdf is not None:
    combined_gdf = pd.concat([gt_gdf, dq_gdf], ignore_index=True)

# ============================================
# LOAD SPECIES LOOKUP (scientific name -> common name)
# ============================================


@st.cache_data
def load_species_lookup(partner: str) -> dict:
    """Load all species TSV files and create a lookup dict from value to label."""
    lookup = {}
    species_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "species", partner)

    species_files = [
        "woody_species.tsv",
        "bamboo_species.tsv",
        "banana_species.tsv",
        "palm_species.tsv",
        "living_fences_species.tsv",
        "non_woody.tsv",
    ]

    for filename in species_files:
        filepath = os.path.join(species_dir, filename)
        if os.path.exists(filepath):
            try:
                df = pd.read_csv(filepath, sep="\t")
                if "value" in df.columns and "label" in df.columns:
                    for _, row in df.iterrows():
                        val = str(row["value"]).strip().lower()
                        label = str(row["label"]).strip()
                        if val and label:
                            lookup[val] = label
            except Exception:
                pass

    return lookup


species_lookup = load_species_lookup(config.PARTNER)

# ============================================
# SIDEBAR FILTERS
# ============================================

with st.sidebar:
    st.markdown("## 🔍 Filters")

    # Date filter (independent)
    date_col = "SubmissionDate" if "SubmissionDate" in combined_gdf.columns else "starttime"
    date_range = None
    if date_col in combined_gdf.columns:
        combined_gdf[date_col] = pd.to_datetime(combined_gdf[date_col], errors="coerce")
        valid_dates = combined_gdf[date_col].dropna()
        if len(valid_dates) > 0:
            min_date = valid_dates.min().date()
            max_date = valid_dates.max().date()
            date_range = st.date_input("📅 Date Range", value=(min_date, max_date), key="exp_date_filter")

    # Enumerator filter (independent)
    selected_enum = "All"
    if "enumerator" in combined_gdf.columns:
        enumerators = ["All"] + sorted(combined_gdf["enumerator"].dropna().unique().tolist())
        selected_enum = st.selectbox("👤 Enumerator", options=enumerators, key="exp_enum_filter")

    # Filter combined_gdf based on date and enumerator for dependent filters
    filtered_gdf_for_plots = combined_gdf.copy()

    # Apply date filter
    if date_range and len(date_range) == 2:
        start_date = pd.Timestamp(date_range[0])
        end_date = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
        filtered_gdf_for_plots = filtered_gdf_for_plots[
            (filtered_gdf_for_plots[date_col] >= start_date) & (filtered_gdf_for_plots[date_col] < end_date)
        ]

    # Apply enumerator filter
    if selected_enum != "All" and "enumerator" in filtered_gdf_for_plots.columns:
        filtered_gdf_for_plots = filtered_gdf_for_plots[filtered_gdf_for_plots["enumerator"] == selected_enum]

    # Plot key filter (dependent on date and enumerator)
    selected_plot = "All"
    if "PLOT_KEY" in filtered_gdf_for_plots.columns:
        plot_keys = ["All"] + sorted(filtered_gdf_for_plots["PLOT_KEY"].dropna().unique().tolist())
        selected_plot = st.selectbox("📍 Plot Key", options=plot_keys, key="exp_plot_filter")

    # Subplot filter (dependent on plot key)
    selected_subplot = "All"
    if selected_plot != "All":
        # Get subplots for the selected plot from combined vegetation data
        gt_veg_temp = gt_raw.get("plots_subplots_vegetation", pd.DataFrame())
        dq_veg_temp = dq_raw.get("plots_subplots_vegetation", pd.DataFrame())

        # Combine GT and DQ vegetation data for subplot options
        combined_veg_temp = gt_veg_temp.copy() if gt_veg_temp is not None else pd.DataFrame()
        if dq_loaded and dq_veg_temp is not None and len(dq_veg_temp) > 0:
            combined_veg_temp = pd.concat([combined_veg_temp, dq_veg_temp], ignore_index=True)

        if len(combined_veg_temp) > 0:
            plot_veg = combined_veg_temp[combined_veg_temp["SUBPLOT_KEY"].str.startswith(selected_plot + "/", na=False)]
            subplot_nums = set()
            for sk in plot_veg["SUBPLOT_KEY"].dropna().unique():
                match = re.search(r"\[(\d+)\]", str(sk))
                if match:
                    subplot_nums.add(int(match.group(1)))
            if subplot_nums:
                subplot_options = ["All"] + sorted(subplot_nums)
                selected_subplot = st.selectbox("📊 Subplot #", options=subplot_options, key="exp_subplot_filter")

    # Vegetation type filters - use combined GT and DQ data
    gt_veg_for_filter = gt_raw.get("plots_subplots_vegetation", pd.DataFrame())
    dq_veg_for_filter = dq_raw.get("plots_subplots_vegetation", pd.DataFrame())

    combined_veg_for_filter = gt_veg_for_filter.copy() if gt_veg_for_filter is not None else pd.DataFrame()
    if dq_loaded and dq_veg_for_filter is not None and len(dq_veg_for_filter) > 0:
        combined_veg_for_filter = pd.concat([combined_veg_for_filter, dq_veg_for_filter], ignore_index=True)

    # Vegetation type primary filter
    selected_primary_type = "All"
    if (
        combined_veg_for_filter is not None
        and len(combined_veg_for_filter) > 0
        and "vegetation_type_primary" in combined_veg_for_filter.columns
    ):
        primary_types = combined_veg_for_filter["vegetation_type_primary"].dropna().unique().tolist()
        primary_types = [str(p) for p in primary_types if str(p).strip()]
        primary_types = ["All"] + sorted(set(primary_types))
        selected_primary_type = st.selectbox("🌿 Primary Type", options=primary_types, key="exp_primary_filter")

    # Vegetation type woody filter
    selected_woody_type = "All"
    if (
        combined_veg_for_filter is not None
        and len(combined_veg_for_filter) > 0
        and "vegetation_type_woody" in combined_veg_for_filter.columns
    ):
        woody_types = combined_veg_for_filter["vegetation_type_woody"].dropna().unique().tolist()
        woody_types = [str(w) for w in woody_types if str(w).strip()]
        woody_types = ["All"] + sorted(set(woody_types))
        selected_woody_type = st.selectbox("🌲 Woody Type", options=woody_types, key="exp_woody_filter")

    # Vegetation type height filter
    selected_height_type = "All"
    if (
        combined_veg_for_filter is not None
        and len(combined_veg_for_filter) > 0
        and "vegetation_type_height" in combined_veg_for_filter.columns
    ):
        height_types = combined_veg_for_filter["vegetation_type_height"].dropna().unique().tolist()
        height_types = [str(h) for h in height_types if str(h).strip()]
        height_types = ["All"] + sorted(set(height_types))
        selected_height_type = st.selectbox("📏 Height Type", options=height_types, key="exp_height_filter")

# ============================================
# SHOW ACTIVE FILTERS
# ============================================

filter_info = []
if selected_plot != "All":
    filter_info.append(f"**Plot:** {selected_plot}")
if selected_subplot != "All":
    filter_info.append(f"**Subplot:** {selected_subplot}")
if selected_enum != "All":
    filter_info.append(f"**Enumerator:** {selected_enum}")
if selected_primary_type != "All":
    filter_info.append(f"**Primary Type:** {selected_primary_type}")
if selected_woody_type != "All":
    filter_info.append(f"**Woody Type:** {selected_woody_type}")
if selected_height_type != "All":
    filter_info.append(f"**Height Type:** {selected_height_type}")
if date_range and len(date_range) == 2:
    filter_info.append(f"**Date:** {date_range[0]} to {date_range[1]}")

if filter_info:
    st.info(" | ".join(filter_info))

# ============================================
# SPECIES COUNT BY SUBPLOT
# ============================================

st.markdown("### 🌳 Species Count by Subplot")

# Get vegetation data from GT and DQ
gt_veg = gt_raw.get("plots_subplots_vegetation", pd.DataFrame())
dq_veg = dq_raw.get("plots_subplots_vegetation", pd.DataFrame())

# Add source column and combine
if gt_veg is not None and len(gt_veg) > 0:
    gt_veg = gt_veg.copy()
    gt_veg["_source"] = "GT"
else:
    gt_veg = pd.DataFrame()

if dq_loaded and dq_veg is not None and len(dq_veg) > 0:
    dq_veg = dq_veg.copy()
    dq_veg["_source"] = "DQ"
else:
    dq_veg = pd.DataFrame()

# Combine GT and DQ vegetation data
combined_veg = pd.concat([gt_veg, dq_veg], ignore_index=True)

if len(combined_veg) == 0:
    st.warning("No vegetation data available.")
    st.stop()

# Apply filters to combined vegetation data
filtered_veg = combined_veg.copy()

# Filter by plot if selected
if selected_plot != "All":
    filtered_veg = filtered_veg[filtered_veg["SUBPLOT_KEY"].str.startswith(selected_plot + "/", na=False)]

# Filter by subplot if selected
if selected_subplot != "All":
    subplot_pattern = f"sub_plot[{selected_subplot}]"
    filtered_veg = filtered_veg[
        filtered_veg["SUBPLOT_KEY"].str.contains(re.escape(subplot_pattern), na=False, regex=True)
    ]

# Filter by enumerator if selected
if selected_enum != "All" and "enumerator" in filtered_veg.columns:
    filtered_veg = filtered_veg[filtered_veg["enumerator"] == selected_enum]

# Filter by primary type if selected
if selected_primary_type != "All" and "vegetation_type_primary" in filtered_veg.columns:
    filtered_veg = filtered_veg[filtered_veg["vegetation_type_primary"].astype(str) == selected_primary_type]

# Filter by woody type if selected
if selected_woody_type != "All" and "vegetation_type_woody" in filtered_veg.columns:
    filtered_veg = filtered_veg[filtered_veg["vegetation_type_woody"].astype(str) == selected_woody_type]

# Filter by height type if selected
if selected_height_type != "All" and "vegetation_type_height" in filtered_veg.columns:
    filtered_veg = filtered_veg[filtered_veg["vegetation_type_height"].astype(str) == selected_height_type]

# Filter by date range if selected
if date_range and len(date_range) == 2:
    veg_date_col = "SubmissionDate" if "SubmissionDate" in filtered_veg.columns else "starttime"
    if veg_date_col in filtered_veg.columns:
        filtered_veg[veg_date_col] = pd.to_datetime(filtered_veg[veg_date_col], errors="coerce")
        start_date = pd.Timestamp(date_range[0])
        end_date = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
        filtered_veg = filtered_veg[
            (filtered_veg[veg_date_col] >= start_date) & (filtered_veg[veg_date_col] < end_date)
        ]

if len(filtered_veg) == 0:
    st.warning("No vegetation data matches the selected filters.")
    st.stop()

# Build species count table per subplot
species_data = []
for _, row in filtered_veg.iterrows():
    subplot_key = row.get("SUBPLOT_KEY", "")

    # Extract subplot number from key (format: uuid:xxx/sub_plot[n])
    subplot_num = "N/A"
    if "[" in str(subplot_key):
        match = re.search(r"\[(\d+)\]", str(subplot_key))
        if match:
            subplot_num = int(match.group(1))

    # Get vegetation type - skip row if blank
    veg_type = row.get("vegetation_species_type", "")
    if pd.isna(veg_type) or str(veg_type).strip() == "" or veg_type == "N/A":
        continue

    # Check if this is a no_coverage case (non-woody vegetation)
    youngtree_type = row.get("vegetation_type_youngtree", "")
    is_coverage = str(youngtree_type).lower() == "no_coverage"

    # Get tree name from species columns
    tree_name = "Unknown"
    if is_coverage:
        # For no_coverage, get from non_woody_species
        non_woody = row.get("non_woody_species", "")
        if pd.notna(non_woody) and str(non_woody).strip():
            tree_name = str(non_woody).strip()
    else:
        # Normal case - check woody species columns
        species_cols = [
            "woody_species",
            "bamboo_species",
            "banana_species",
            "palm_species",
            "living_fences_species",
        ]
        for col in species_cols:
            val = row.get(col)
            if pd.notna(val) and str(val).strip():
                tree_name = str(val).strip()
                break

    # If tree_name is "other", get from other_species column
    if tree_name.lower() == "other":
        other_sp = row.get("other_species", "")
        lang_other = row.get("language_other_species", "")
        if pd.notna(other_sp) and str(other_sp).strip():
            tree_name = f"other: {other_sp}"
            if pd.notna(lang_other) and str(lang_other).strip():
                tree_name += f" ({lang_other})"

    # Get common name from lookup (using scientific name)
    common_name = ""
    tree_name_lookup_key = tree_name.lower().replace(" ", "_")
    if tree_name_lookup_key in species_lookup:
        common_name = species_lookup[tree_name_lookup_key]

    # Get count - for no_coverage use coverage_vegetation (percentage)
    if is_coverage:
        count = row.get("coverage_vegetation", 0)
        if pd.isna(count):
            count = 0
        else:
            count = int(float(count))
        count_display = f"{count}%"  # Indicate it's a percentage
    else:
        count = row.get("vegetation_type_number", 0)
        if pd.isna(count):
            count = 0
        else:
            count = int(float(count))
        count_display = str(count)

    # Get date (full date)
    date_val = row.get("SubmissionDate", row.get("starttime", "N/A"))
    if pd.notna(date_val):
        try:
            date_val = pd.to_datetime(date_val).strftime("%Y-%m-%d")
        except Exception:
            date_val = str(date_val)
    else:
        date_val = "N/A"

    # Get source (GT or DQ)
    source = row.get("_source", "GT")

    # Get year planted (year only)
    year_planted = row.get("tree_year_planted", "N/A")
    if pd.notna(year_planted) and year_planted != "N/A":
        try:
            # Handle epoch timestamps or date strings
            yr_val = float(year_planted)
            if yr_val > 10000:  # Likely epoch timestamp
                year_planted = pd.to_datetime(yr_val, unit="ms").strftime("%Y")
            elif 1900 <= yr_val <= 2100:
                year_planted = str(int(yr_val))
            else:
                year_planted = "N/A"
        except (ValueError, TypeError):
            try:
                year_planted = pd.to_datetime(year_planted).strftime("%Y")
            except Exception:
                year_planted = "N/A"
    else:
        year_planted = "N/A"

    # Get above 1.3m indicator from vegetation_type_height
    veg_height = row.get("vegetation_type_height", "")
    if pd.notna(veg_height) and "above" in str(veg_height).lower():
        above_1_3 = "Y"
    else:
        above_1_3 = "N"

    species_data.append(
        {
            "Source": source,
            "Subplot #": subplot_num,
            "Vegetation Type": veg_type,
            "Tree Name": tree_name,
            "Common Name": common_name,
            "Count": count_display,
            "_tree_count": 0 if is_coverage else count,  # Only count trees, not coverage
            "Above 1.3": above_1_3,
            "Year Planted": year_planted,
            "Enumerator": row.get("enumerator", "N/A"),
            "Date": date_val,
        }
    )

# Create DataFrame and display
species_df = pd.DataFrame(species_data)

# Sort by source, subplot number, vegetation type
species_df["_sort_key"] = pd.to_numeric(species_df["Subplot #"], errors="coerce")
species_df = species_df.sort_values(["Source", "_sort_key", "Vegetation Type"]).drop(columns=["_sort_key"])

# Display summary metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Records", len(species_df))
with col2:
    st.metric("Total Tree Count", int(species_df["_tree_count"].sum()))
with col3:
    unique_subplots = species_df["Subplot #"].nunique()
    st.metric("Unique Subplots", unique_subplots)
with col4:
    unique_species = species_df["Tree Name"].nunique()
    st.metric("Unique Species", unique_species)

# Display the dataframe (drop internal columns)
display_df = species_df.drop(columns=["_tree_count"])
st.dataframe(display_df, use_container_width=True, height=500)

# ============================================
# DOWNLOAD OPTION
# ============================================

csv = species_df.to_csv(index=False)
st.download_button(
    label="📥 Download as CSV",
    data=csv,
    file_name="species_count_by_subplot.csv",
    mime="text/csv",
)
