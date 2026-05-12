"""
Reusable UI components
"""

import streamlit as st
import config
import pandas as pd


def require_auth():
    """
    Check if user has validated credentials.
    Must have credentials_validated=True in session state.
    Returns True if authenticated, stops page if not.
    """
    credentials_validated = st.session_state.get("credentials_validated", False)

    if not credentials_validated:
        st.warning("⚠️ Please validate your credentials first.")
        st.info("Enter your SurveyCTO credentials on the home page and click 'Validate Credentials'.")
        if st.button("← Go to Home"):
            st.switch_page("app.py")
        st.stop()
        return False
    return True


def get_total_measured_subplots(gdf):
    """
    Calculate total measured subplots using the measured_subplots field.
    Falls back to counting records if field is not available.

    Args:
        gdf: GeoDataFrame with subplot data

    Returns:
        int: Total measured subplots
    """
    if "measured_subplots" in gdf.columns and "PLOT_KEY" in gdf.columns:
        # Group by plot and sum measured_subplots (taking first value per plot since it's the same for all subplots)
        total = gdf.groupby("PLOT_KEY")["measured_subplots"].first().apply(lambda x: int(x) if pd.notna(x) else 0).sum()
        return int(total)
    else:
        # Fallback: count subplot records
        return len(gdf)


def show_header():
    """Display app header with partner information"""
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, #2E7D32 0%, #388E3C 100%);
                    padding: 2rem; border-radius: 10px; margin-bottom: 2rem;">
            <h1 style="color: white; margin: 0;">
                {config.APP_ICON} {config.APP_TITLE}
            </h1>
            <p style="color: #E8F5E9; margin-top: 0.5rem; font-size: 1.1em;">
                {config.APP_SUBTITLE}
            </p>
            <p style="color: #C8E6C9; margin-top: 0.3rem; font-size: 0.9em;">
                Active Partner: <strong>{config.PARTNER}</strong> | Country: <strong>{config.COUNTRY}</strong> | Year: {config.PARTNER_CONFIG["start_date"][:4]}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_partner_selector():
    """Display partner selection info and available partners"""
    st.markdown("### 🌍 Available Partners")

    st.info(
        """
        💡 **How to switch partners:** Add `?partner=PARTNER_NAME` to the URL

        Example URLs:
        - **IORA (India)**: `?partner=IORA`
        - **AFOCO (Kyrgyzstan)**: `?partner=AFOCO`
        - **COMACO (Zambia)**: `?partner=COMACO`
        """
    )

    # Show available partners in a nice table
    partner_data = []
    for partner_code, partner_info in config.PARTNERS.items():
        is_active = "✅ Active" if partner_code == config.PARTNER else ""
        partner_data.append(
            {
                "Partner": partner_code,
                "Description": partner_info["description"],
                "Country": partner_info["country"],
                "Status": is_active,
            }
        )

    df = pd.DataFrame(partner_data)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Partner": st.column_config.TextColumn("Partner Code", width="small"),
            "Description": st.column_config.TextColumn("Description", width="medium"),
            "Country": st.column_config.TextColumn("Country", width="small"),
            "Status": st.column_config.TextColumn("Status", width="small"),
        },
    )


def show_plot_metrics_row(plot_summary):
    """Display plot-level metrics in a row"""
    col1, col2, col3 = st.columns(3)

    with col1:
        total_plots = len(plot_summary) if len(plot_summary) > 0 else 0
        st.metric("📍 Total Plots", f"{total_plots:,}")

    with col2:
        if len(plot_summary) > 0:
            valid_plots = plot_summary["plot_valid"].sum()
            valid_pct = (valid_plots / total_plots * 100) if total_plots > 0 else 0
            st.metric("✅ Valid Plots", f"{valid_plots:,}", f"{valid_pct:.1f}%")
        else:
            st.metric("✅ Valid Plots", "0", "0.0%")

    with col3:
        if len(plot_summary) > 0:
            invalid_plots = (~plot_summary["plot_valid"]).sum()
            invalid_pct = (invalid_plots / total_plots * 100) if total_plots > 0 else 0
            st.metric("❌ Invalid Plots", f"{invalid_plots:,}", f"{invalid_pct:.1f}%")
        else:
            st.metric("❌ Invalid Plots", "0", "0.0%")


def show_metrics_row(summary):
    """Display metrics in a row"""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "📊 Total Subplots",
            f"{summary['total']:,}",
        )

    with col2:
        st.metric(
            "✅ Valid Subplots",
            f"{summary['valid']:,}",
            f"{summary['valid_pct']:.1f}%",
            delta_color="normal",
        )

    with col3:
        st.metric(
            "❌ Invalid Subplots",
            f"{summary['invalid']:,}",
            delta_color="inverse" if summary["invalid"] > 0 else "off",
        )

    with col4:
        issues = sum(summary["reason_counts"].values())
        st.metric(
            "⚠️ Total Issues",
            f"{issues:,}",
        )


def show_status_message(summary):
    """Display status message based on validation results"""
    valid_pct = summary["valid_pct"]

    if valid_pct >= 90:
        st.success(f"✅ {valid_pct:.1f}% of subplots are valid")
    elif valid_pct >= 70:
        st.warning(f"⚠️ {summary['invalid']} subplots need attention ({100 - valid_pct:.1f}% invalid)")
    else:
        st.error(f"❌ {summary['invalid']} subplots are invalid ({100 - valid_pct:.1f}%)")


def show_sidebar_info():
    """
    Show common sidebar information.
    Displays active partner and data status (appears after date filter).
    """
    st.sidebar.markdown(
        '<a href="/" target="_self" style="text-decoration:none;font-size:0.9rem;">← All Cases</a>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")

    # Show active partner
    active_partner = st.session_state.get("partner", config.PARTNER)
    st.sidebar.info(f"🔗 **Partner:** {active_partner}")

    # Show data status if data is loaded
    if st.session_state.get("data") is not None:
        subplots = st.session_state.data.get("subplots")
        if subplots is not None:
            total = get_total_measured_subplots(subplots)
            valid = subplots["geom_valid"].sum() if "geom_valid" in subplots.columns else 0
            st.sidebar.success(f"✅ {total} subplots measured ({valid} valid)")
    else:
        st.sidebar.warning("⚠️ No data loaded")

    st.sidebar.markdown("---")


def create_sidebar_filters(gdf):
    """Create sidebar filters and return filtered data"""
    from datetime import date as date_class

    # Date filter - try to find or add date column (appears at top)
    date_col = None
    gdf_with_date = gdf.copy()

    try:
        # Check if date column already exists (prioritize SubmissionDate over starttime)
        if "SubmissionDate" in gdf.columns:
            date_col = "SubmissionDate"
        elif "starttime" in gdf.columns:
            date_col = "starttime"
        elif hasattr(st.session_state, "data") and st.session_state.data and "raw_data" in st.session_state.data:
            # Try to add date from raw_data
            raw_data = st.session_state.data.get("raw_data", {})
            if "plots_subplots" in raw_data:
                plots_df = raw_data["plots_subplots"]

                # Check for date column with different case variations
                submission_date_col = None
                for col in plots_df.columns:
                    if "submissiondate" in col.lower() and "subplot" in col.lower():
                        submission_date_col = col
                        break
                if not submission_date_col:
                    for col in plots_df.columns:
                        if "submissiondate" in col.lower():
                            submission_date_col = col
                            break
                if not submission_date_col:
                    for col in plots_df.columns:
                        if "starttime" in col.lower():
                            submission_date_col = col
                            break

                # Merge the date column if found
                if submission_date_col and "subplot_id" in gdf.columns and "SUBPLOT_KEY" in plots_df.columns:
                    date_merge = plots_df[["SUBPLOT_KEY", submission_date_col]].drop_duplicates()

                    # Drop SUBPLOT_KEY if it already exists to avoid duplicate column issues
                    if "SUBPLOT_KEY" in gdf.columns:
                        gdf = gdf.drop(columns=["SUBPLOT_KEY"])

                    gdf_with_date = gdf.merge(
                        date_merge,
                        left_on="subplot_id",
                        right_on="SUBPLOT_KEY",
                        how="left",
                        suffixes=("", "_drop"),
                    )

                    # Drop any columns with '_drop' suffix
                    drop_cols = [col for col in gdf_with_date.columns if col.endswith("_drop")]
                    if drop_cols:
                        gdf_with_date = gdf_with_date.drop(columns=drop_cols)

                    date_col = submission_date_col

        if date_col:
            # Convert to datetime
            gdf_with_date[date_col] = pd.to_datetime(gdf_with_date[date_col], errors="coerce")

            # Filter out rows with invalid dates
            valid_dates = gdf_with_date[date_col].notna()

            if valid_dates.sum() > 0:
                # Get min/max dates from valid dates only
                min_date = gdf_with_date.loc[valid_dates, date_col].min().date()
                max_date = gdf_with_date.loc[valid_dates, date_col].max().date()
                today = date_class.today()
                # Allow selecting up to today (or data max if data is from future)
                # max_date = max(data_max_date, today)

                # Use session state to persist date selection across page navigations
                if "date_filter_start" not in st.session_state or "date_filter_end" not in st.session_state:
                    # Initialize with today if in range, otherwise max_date
                    if min_date <= today <= max_date:
                        default_start_date = today
                        default_end_date = today
                    else:
                        default_start_date = max_date
                        default_end_date = max_date
                    st.session_state.date_filter_start = default_start_date
                    st.session_state.date_filter_end = default_end_date
                else:
                    # Use persisted values (but ensure they're within valid range)
                    default_start_date = max(min_date, min(st.session_state.date_filter_start, max_date))
                    default_end_date = max(min_date, min(st.session_state.date_filter_end, max_date))

                date_range = st.sidebar.date_input(
                    "📅 Date Range",
                    value=(default_start_date, default_end_date),
                    min_value=min_date,
                    max_value=max_date,
                    help="Filter data by submission date. Defaults to today's data only.",
                    key="sidebar_date_filter",
                )

                # Update session state when date changes
                if len(date_range) == 2:
                    st.session_state.date_filter_start = date_range[0]
                    st.session_state.date_filter_end = date_range[1]

                # Apply date filter if both dates selected
                if len(date_range) == 2:
                    start_date, end_date = date_range
                    mask = (gdf_with_date[date_col].dt.date >= start_date) & (
                        gdf_with_date[date_col].dt.date <= end_date
                    )
                    gdf = gdf_with_date[mask].copy()

                    # Remove the temporary date column if we added it
                    if (
                        hasattr(st.session_state, "data")
                        and st.session_state.data
                        and "subplots" in st.session_state.data
                    ):
                        if date_col not in st.session_state.data["subplots"].columns:
                            if date_col in gdf.columns:
                                gdf = gdf.drop(columns=[date_col])
                            if (
                                "SUBPLOT_KEY" in gdf.columns
                                and "SUBPLOT_KEY" not in st.session_state.data["subplots"].columns
                            ):
                                gdf = gdf.drop(columns=["SUBPLOT_KEY"])
                else:
                    gdf = gdf_with_date.copy()
            else:
                st.sidebar.warning(f"⚠️ No valid dates in '{date_col}'")
                st.sidebar.caption(f"Found {valid_dates.sum()}/{len(gdf_with_date)} valid dates")
        else:
            st.sidebar.info("ℹ️ No date column found in data")
            # Show available columns for debugging
            with st.sidebar.expander("🔍 Debug: Available Columns"):
                st.write("**Subplot columns:**")
                st.caption(", ".join(sorted(gdf.columns.tolist())[:20]))
                if hasattr(st.session_state, "data") and st.session_state.data:
                    raw_data = st.session_state.data.get("raw_data", {})
                    if "plots_subplots" in raw_data:
                        st.write("**Plot/Subplot columns:**")
                        st.caption(", ".join(sorted(raw_data["plots_subplots"].columns.tolist())[:20]))

    except Exception as e:
        st.sidebar.error("❌ Date filter error")
        with st.sidebar.expander("🔍 Error Details"):
            st.code(str(e))
            import traceback

            st.caption("Full traceback:")
            st.code(traceback.format_exc())

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🔍 Filters")

    # Enumerator filter
    if "enumerator" in gdf.columns:
        enumerators = sorted(gdf["enumerator"].dropna().unique().tolist())
        selected_enums = st.sidebar.multiselect(
            "Enumerator",
            options=enumerators,
            default=enumerators,
        )

        if selected_enums:
            from utils.data_processor import filter_by_enumerator

            gdf = filter_by_enumerator(gdf, selected_enums)

    return gdf


def show_invalid_table(gdf):
    """Display table of invalid subplots"""
    invalid_df = gdf[~gdf["geom_valid"]].copy()

    if len(invalid_df) == 0:
        st.success("🎉 All subplots are valid!")
        return

    st.markdown(f"### ❌ Invalid Subplots ({len(invalid_df)})")

    # Select columns
    display_cols = ["subplot_id"]
    for col in ["enumerator", "area_m2", "nr_vertices", "reasons"]:
        if col in invalid_df.columns:
            display_cols.append(col)

    # Format area if exists
    if "area_m2" in invalid_df.columns:
        invalid_df["area_m2"] = invalid_df["area_m2"].round(1)

    st.dataframe(
        invalid_df[display_cols],
        use_container_width=True,
        height=500,
        column_config={
            "subplot_id": "Subplot ID",
            "enumerator": "Enumerator",
            "area_m2": st.column_config.NumberColumn("Area (m²)", format="%.1f"),
            "nr_vertices": "Vertices",
            "reasons": "Validation Errors",
        },
    )
