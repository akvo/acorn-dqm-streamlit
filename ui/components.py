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
    Show common sidebar information at the top of all pages.
    Displays active partner and data status.
    """
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
        if st.sidebar.button("← Go to Home"):
            st.switch_page("app.py")

    st.sidebar.markdown("---")


def create_sidebar_filters(gdf):
    """Create sidebar filters and return filtered data"""
    st.sidebar.markdown("## 🔍 Filters")

    # Date filter
    if "starttime" in gdf.columns:
        gdf_copy = gdf.copy()
        gdf_copy["starttime"] = pd.to_datetime(gdf_copy["starttime"])

        min_date = gdf_copy["starttime"].min().date()
        max_date = gdf_copy["starttime"].max().date()

        date_range = st.sidebar.date_input(
            "Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if len(date_range) == 2:
            from utils.data_processor import filter_by_date

            gdf = filter_by_date(gdf, date_range[0], date_range[1])

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
