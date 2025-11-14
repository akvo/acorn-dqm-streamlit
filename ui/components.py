"""
Reusable UI components
"""

import streamlit as st
import config
import pandas as pd


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
                Active Partner: <strong>{config.PARTNER}</strong> | Country: <strong>{config.COUNTRY}</strong> | Year: {config.YEAR}
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
        partner_data.append({
            "Partner": partner_code,
            "Description": partner_info["description"],
            "Country": partner_info["country"],
            "Status": is_active
        })

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
        }
    )


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
        st.warning(f"⚠️ {summary['invalid']} subplots need attention ({100-valid_pct:.1f}% invalid)")
    else:
        st.error(
            f"❌ {summary['invalid']} subplots are invalid ({100-valid_pct:.1f}%)"
        )


def show_sidebar_info():
    """
    Show common sidebar information.
    Displays active partner and data status (appears after date filter).
    """
    st.sidebar.markdown("---")

    # Show active partner
    active_partner = st.session_state.get("partner", config.PARTNER)
    st.sidebar.info(f"🔗 **Partner:** {active_partner}")

    # Show data status if data is loaded
    if st.session_state.get("data") is not None:
        subplots = st.session_state.data.get("subplots")
        if subplots is not None:
            total = len(subplots)
            valid = subplots["geom_valid"].sum() if "geom_valid" in subplots.columns else 0
            st.sidebar.success(f"✅ {total} subplots loaded ({valid} valid)")
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
        # Check if date column already exists
        if "starttime" in gdf.columns:
            date_col = "starttime"
        elif "SubmissionDate" in gdf.columns:
            date_col = "SubmissionDate"
        elif hasattr(st.session_state, 'data') and st.session_state.data and "raw_data" in st.session_state.data:
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
                        suffixes=('', '_drop')
                    )

                    # Drop any columns with '_drop' suffix
                    drop_cols = [col for col in gdf_with_date.columns if col.endswith('_drop')]
                    if drop_cols:
                        gdf_with_date = gdf_with_date.drop(columns=drop_cols)

                    date_col = submission_date_col

        if date_col:
            # Convert to datetime
            gdf_with_date[date_col] = pd.to_datetime(gdf_with_date[date_col], errors='coerce')

            # Filter out rows with invalid dates
            valid_dates = gdf_with_date[date_col].notna()

            if valid_dates.sum() > 0:
                # Get min/max dates from valid dates only
                min_date = gdf_with_date.loc[valid_dates, date_col].min().date()
                max_date = gdf_with_date.loc[valid_dates, date_col].max().date()
                today = date_class.today()

                # Default to today only if today is within range, otherwise use max_date
                if min_date <= today <= max_date:
                    default_start_date = today
                    default_end_date = today
                else:
                    # If today is out of range, show the last day's data
                    default_start_date = max_date
                    default_end_date = max_date

                date_range = st.sidebar.date_input(
                    "📅 Date Range",
                    value=(default_start_date, default_end_date),
                    min_value=min_date,
                    max_value=max_date,
                    help="Filter data by submission date. Defaults to today's data only.",
                    key="sidebar_date_filter",
                )

                # Apply date filter if both dates selected
                if len(date_range) == 2:
                    start_date, end_date = date_range
                    mask = (
                        (gdf_with_date[date_col].dt.date >= start_date) &
                        (gdf_with_date[date_col].dt.date <= end_date)
                    )
                    gdf = gdf_with_date[mask].copy()

                    # Remove the temporary date column if we added it
                    if hasattr(st.session_state, 'data') and st.session_state.data and "subplots" in st.session_state.data:
                        if date_col not in st.session_state.data["subplots"].columns:
                            if date_col in gdf.columns:
                                gdf = gdf.drop(columns=[date_col])
                            if "SUBPLOT_KEY" in gdf.columns and "SUBPLOT_KEY" not in st.session_state.data["subplots"].columns:
                                gdf = gdf.drop(columns=["SUBPLOT_KEY"])
                else:
                    gdf = gdf_with_date.copy()
            else:
                st.sidebar.warning(f"⚠️ No valid dates found in column: {date_col}")
                # Debug info (can remove later)
                if date_col in gdf_with_date.columns:
                    st.sidebar.caption(f"Column exists but has {valid_dates.sum()}/{len(gdf_with_date)} valid dates")
        else:
            st.sidebar.warning("⚠️ Date column not found")
            # Debug info (can remove later)
            st.sidebar.caption(f"Available columns: starttime={('starttime' in gdf.columns)}, SubmissionDate={('SubmissionDate' in gdf.columns)}")

    except Exception as e:
        st.sidebar.error(f"❌ Date filter error: {str(e)}")
        import traceback
        st.sidebar.caption(f"Error details: {traceback.format_exc()}")

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

    # Validity filter
    validity_filter = st.sidebar.radio(
        "Show",
        options=["All", "Valid Only", "Invalid Only"],
        index=0,
    )

    if validity_filter == "Valid Only":
        gdf = gdf[gdf["geom_valid"]]
    elif validity_filter == "Invalid Only":
        gdf = gdf[~gdf["geom_valid"]]

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
