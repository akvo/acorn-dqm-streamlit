"""
Enumerator Performance Page
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils.validators import aggregate_validation_results

st.set_page_config(page_title="Enumerator Performance", page_icon="👤", layout="wide")

st.title("👤 Enumerator Performance")

if not st.session_state.get("data_loaded", False):
    st.warning("⚠️ No data loaded. Please upload a file from the home page.")
    if st.button("Go to Home"):
        st.switch_page("app.py")
    st.stop()

# Get data
plots_subplots = st.session_state.merged_data["plots_subplots"]
validation_results = st.session_state.validation_results

# Calculate per-enumerator statistics
enumerator_stats = []

for enumerator, group in plots_subplots.groupby("enumerator"):
    stats = {
        "enumerator": enumerator,
        "total_plots": group["PLOT_KEY"].nunique(),
        "total_subplots": len(group),
        "valid_subplots": 0,
        "invalid_subplots": 0,
        "geometry_errors": 0,
        "species_errors": 0,
        "measurement_errors": 0,
        "last_collection": (
            group["SubmissionDate"].max() if "SubmissionDate" in group.columns else None
        ),
    }

    # Count issues
    for idx, row in group.iterrows():
        subplot_id = row.get("SUBPLOT_KEY")
        if subplot_id in validation_results["subplots"]:
            validation = validation_results["subplots"][subplot_id]

            if validation["valid"]:
                stats["valid_subplots"] += 1
            else:
                stats["invalid_subplots"] += 1

            for issue in validation["issues"]:
                issue_type = issue.get("type", "unknown")
                if issue_type == "geometry":
                    stats["geometry_errors"] += 1
                elif issue_type == "species":
                    stats["species_errors"] += 1
                elif issue_type == "measurement":
                    stats["measurement_errors"] += 1

    # Calculate valid percentage
    if stats["total_subplots"] > 0:
        stats["valid_pct"] = (stats["valid_subplots"] / stats["total_subplots"]) * 100
    else:
        stats["valid_pct"] = 0

    enumerator_stats.append(stats)

# Create DataFrame
df_enum = pd.DataFrame(enumerator_stats)
df_enum = df_enum.sort_values("valid_pct", ascending=False)

# Display summary
st.subheader("Performance Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Enumerators", len(df_enum))

with col2:
    avg_valid = df_enum["valid_pct"].mean()
    st.metric("Avg Valid %", f"{avg_valid:.1f}%")

with col3:
    best_enum = df_enum.iloc[0]["enumerator"] if len(df_enum) > 0 else "N/A"
    st.metric("Best Performer", best_enum)

with col4:
    total_plots = df_enum["total_plots"].sum()
    st.metric("Total Plots", total_plots)

st.markdown("---")

# Performance table
st.subheader("Detailed Performance")

# Format the DataFrame for display
df_display = df_enum.copy()
df_display["Valid %"] = df_display["valid_pct"].apply(lambda x: f"{x:.1f}%")
df_display = df_display[
    [
        "enumerator",
        "total_plots",
        "total_subplots",
        "Valid %",
        "geometry_errors",
        "species_errors",
        "measurement_errors",
        "last_collection",
    ]
]

df_display.columns = [
    "Enumerator",
    "Plots",
    "Subplots",
    "Valid %",
    "Geometry Errors",
    "Species Errors",
    "Measurement Errors",
    "Last Collection",
]

st.dataframe(df_display, use_container_width=True, hide_index=True)

st.markdown("---")

# Charts
col1, col2 = st.columns(2)

with col1:
    # Valid % by enumerator
    fig_valid = px.bar(
        df_enum,
        x="enumerator",
        y="valid_pct",
        title="Valid Subplot Percentage by Enumerator",
        labels={"enumerator": "Enumerator", "valid_pct": "Valid %"},
        color="valid_pct",
        color_continuous_scale="RdYlGn",
    )
    fig_valid.update_layout(height=400)
    fig_valid.update_xaxes(tickangle=45)
    st.plotly_chart(fig_valid, use_container_width=True)

with col2:
    # Error distribution
    error_data = []
    for _, row in df_enum.iterrows():
        error_data.append(
            {
                "Enumerator": row["enumerator"],
                "Geometry": row["geometry_errors"],
                "Species": row["species_errors"],
                "Measurement": row["measurement_errors"],
            }
        )

    df_errors = pd.DataFrame(error_data)

    fig_errors = go.Figure()
    fig_errors.add_trace(
        go.Bar(name="Geometry", x=df_errors["Enumerator"], y=df_errors["Geometry"])
    )
    fig_errors.add_trace(
        go.Bar(name="Species", x=df_errors["Enumerator"], y=df_errors["Species"])
    )
    fig_errors.add_trace(
        go.Bar(
            name="Measurement", x=df_errors["Enumerator"], y=df_errors["Measurement"]
        )
    )

    fig_errors.update_layout(
        title="Error Distribution by Enumerator",
        xaxis_title="Enumerator",
        yaxis_title="Number of Errors",
        barmode="stack",
        height=400,
    )
    fig_errors.update_xaxes(tickangle=45)

    st.plotly_chart(fig_errors, use_container_width=True)

# Collection timeline by enumerator
st.subheader("Collection Timeline")

if "SubmissionDate" in plots_subplots.columns:
    plots_subplots["SubmissionDate"] = pd.to_datetime(plots_subplots["SubmissionDate"])

    timeline_data = (
        plots_subplots.groupby([plots_subplots["SubmissionDate"].dt.date, "enumerator"])
        .size()
        .reset_index()
    )
    timeline_data.columns = ["Date", "Enumerator", "Count"]

    fig_timeline = px.line(
        timeline_data,
        x="Date",
        y="Count",
        color="Enumerator",
        title="Plots Collected Over Time",
        markers=True,
    )
    fig_timeline.update_layout(height=400)

    st.plotly_chart(fig_timeline, use_container_width=True)
