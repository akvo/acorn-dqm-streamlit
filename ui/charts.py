"""
Chart and visualization functions
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


def create_validation_pie_chart(summary):
    """Create pie chart of validation status"""
    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Valid", "Invalid"],
                values=[summary["valid"], summary["invalid"]],
                marker_colors=["#4CAF50", "#F44336"],
                hole=0.4,
                textinfo="label+percent+value",
                textfont_size=14,
            )
        ]
    )

    fig.update_layout(
        title={"text": "Validation Status", "x": 0.5, "xanchor": "center"},
        height=400,
        showlegend=True,
    )

    return fig


def create_error_breakdown_chart(summary):
    """Create bar chart of error types"""
    if not summary["reason_counts"]:
        return None

    df = pd.DataFrame(
        {
            "Error Type": list(summary["reason_counts"].keys()),
            "Count": list(summary["reason_counts"].values()),
        }
    ).sort_values("Count", ascending=True)

    fig = px.bar(
        df,
        x="Count",
        y="Error Type",
        orientation="h",
        title="Most Common Validation Errors",
        color="Count",
        color_continuous_scale="Reds",
    )

    fig.update_layout(height=max(400, len(df) * 40))

    return fig


def create_enumerator_performance_chart(gdf):
    """Create performance chart by enumerator"""
    if "enumerator" not in gdf.columns or "geom_valid" not in gdf.columns:
        return None

    enum_stats = (
        gdf.groupby("enumerator").agg({"geom_valid": ["sum", "count"]}).reset_index()
    )

    enum_stats.columns = ["enumerator", "valid", "total"]
    enum_stats["invalid"] = enum_stats["total"] - enum_stats["valid"]
    enum_stats = enum_stats.sort_values("valid", ascending=True)

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            name="Valid",
            x=enum_stats["enumerator"],
            y=enum_stats["valid"],
            marker_color="green",
        )
    )

    fig.add_trace(
        go.Bar(
            name="Invalid",
            x=enum_stats["enumerator"],
            y=enum_stats["invalid"],
            marker_color="red",
        )
    )

    fig.update_layout(
        barmode="stack",
        title="Validation Results by Enumerator",
        xaxis_title="Enumerator",
        yaxis_title="Number of Subplots",
        height=400,
    )

    return fig


def create_timeline_chart(gdf):
    """Create timeline of submissions"""
    if "starttime" not in gdf.columns:
        return None

    gdf_copy = gdf.copy()
    gdf_copy["starttime"] = pd.to_datetime(gdf_copy["starttime"])
    gdf_copy["date"] = gdf_copy["starttime"].dt.date

    timeline = gdf_copy.groupby("date").size().reset_index(name="count")

    fig = px.line(
        timeline,
        x="date",
        y="count",
        title="Submissions Over Time",
        markers=True,
    )

    fig.update_layout(xaxis_title="Date", yaxis_title="Number of Subplots", height=400)

    return fig
