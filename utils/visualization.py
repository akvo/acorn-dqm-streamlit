"""
Visualization helpers using Plotly
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from typing import Dict, List
import config


def plot_validation_summary(summary: Dict) -> go.Figure:
    """
    Create pie chart of validation status
    """
    labels = ["Valid", "Invalid"]
    values = [summary.get("valid_subplots", 0), summary.get("invalid_subplots", 0)]
    colors = [config.SEVERITY_COLORS["valid"], config.SEVERITY_COLORS["error"]]

    fig = go.Figure(
        data=[
            go.Pie(labels=labels, values=values, marker=dict(colors=colors), hole=0.4)
        ]
    )

    fig.update_layout(title="Subplot Validation Status", showlegend=True, height=400)

    return fig


def plot_issues_by_type(summary: Dict) -> go.Figure:
    """
    Create bar chart of issues by type
    """
    issues_by_type = summary.get("issues_by_type", {})

    if not issues_by_type:
        return None

    df = pd.DataFrame(list(issues_by_type.items()), columns=["Type", "Count"])
    df = df.sort_values("Count", ascending=True)

    fig = px.bar(
        df,
        x="Count",
        y="Type",
        orientation="h",
        title="Issues by Category",
        color="Count",
        color_continuous_scale="Reds",
    )

    fig.update_layout(height=400)

    return fig


def plot_issues_by_severity(summary: Dict) -> go.Figure:
    """
    Create bar chart of issues by severity
    """
    issues_by_severity = summary.get("issues_by_severity", {})

    if not issues_by_severity:
        return None

    severity_order = ["critical", "error", "warning", "info"]
    data = []
    colors_list = []

    for severity in severity_order:
        if severity in issues_by_severity:
            data.append(
                {"Severity": severity.title(), "Count": issues_by_severity[severity]}
            )
            colors_list.append(config.SEVERITY_COLORS.get(severity, "#999999"))

    if not data:
        return None

    df = pd.DataFrame(data)

    fig = go.Figure(
        data=[go.Bar(x=df["Severity"], y=df["Count"], marker=dict(color=colors_list))]
    )

    fig.update_layout(
        title="Issues by Severity",
        xaxis_title="Severity",
        yaxis_title="Count",
        height=400,
    )

    return fig


def plot_collection_timeline(
    df: pd.DataFrame, date_column: str = "SubmissionDate"
) -> go.Figure:
    """
    Create timeline of data collection
    """
    if date_column not in df.columns:
        return None

    df_copy = df.copy()
    df_copy[date_column] = pd.to_datetime(df_copy[date_column])

    daily_counts = df_copy.groupby(df_copy[date_column].dt.date).size().reset_index()
    daily_counts.columns = ["Date", "Count"]

    fig = px.line(
        daily_counts,
        x="Date",
        y="Count",
        title="Data Collection Timeline",
        markers=True,
    )

    fig.update_layout(xaxis_title="Date", yaxis_title="Plots Collected", height=400)

    return fig


def plot_enumerator_performance(df: pd.DataFrame) -> go.Figure:
    """
    Create bar chart of enumerator performance
    """
    if "enumerator" not in df.columns:
        return None

    enum_counts = df["enumerator"].value_counts().reset_index()
    enum_counts.columns = ["Enumerator", "Plots"]

    fig = px.bar(
        enum_counts,
        x="Enumerator",
        y="Plots",
        title="Plots by Enumerator",
        color="Plots",
        color_continuous_scale="Viridis",
    )

    fig.update_layout(height=400)
    fig.update_xaxes(tickangle=45)

    return fig
