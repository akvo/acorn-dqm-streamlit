"""
Centralized session/data management for multi-user Streamlit app.

Uses st.cache_resource for shared data across users (team collaboration).
Data is cached per-partner to allow multiple partners to be viewed simultaneously.
Includes timestamp tracking and manual refresh capability.
"""
import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime


@st.cache_resource
def _get_data_store() -> Dict[str, Any]:
    """
    Returns a persistent data store shared across all users.
    Data is keyed by partner to support multiple partners.
    """
    return {
        "data": {},  # {partner: {"gt": data, "dq": data, "fetched_at": datetime}}
    }


def save_data(data: Dict, data_type: str = "gt", partner: str = None) -> None:
    """Save data to shared cache, keyed by partner."""
    if partner is None:
        import config
        partner = config.PARTNER

    store = _get_data_store()

    if partner not in store["data"]:
        store["data"][partner] = {"gt": None, "dq": None, "fetched_at": None}

    store["data"][partner][data_type] = data
    store["data"][partner]["fetched_at"] = datetime.now()

    # Also save to session state for immediate access
    session_key = "data" if data_type == "gt" else "dq_data"
    st.session_state[session_key] = data


def load_data(data_type: str = "gt", partner: str = None) -> Optional[Dict]:
    """Load data from session state, falling back to shared cache."""
    if partner is None:
        import config
        partner = config.PARTNER

    session_key = "data" if data_type == "gt" else "dq_data"

    # First, try session state
    if session_key in st.session_state and st.session_state[session_key] is not None:
        return st.session_state[session_key]

    # Fall back to shared cache
    store = _get_data_store()
    if partner in store["data"] and store["data"][partner].get(data_type) is not None:
        data = store["data"][partner][data_type]
        st.session_state[session_key] = data
        return data

    return None


def has_data(data_type: str = "gt", partner: str = None) -> bool:
    """Check if data is available."""
    return load_data(data_type, partner) is not None


def get_data_timestamp(partner: str = None) -> Optional[datetime]:
    """Get when data was last fetched for a partner."""
    if partner is None:
        import config
        partner = config.PARTNER

    store = _get_data_store()
    if partner in store["data"]:
        return store["data"][partner].get("fetched_at")
    return None


def clear_data(data_type: str = "gt", partner: str = None) -> None:
    """Clear data for a specific partner and type."""
    if partner is None:
        import config
        partner = config.PARTNER

    session_key = "data" if data_type == "gt" else "dq_data"

    if session_key in st.session_state:
        st.session_state[session_key] = None

    store = _get_data_store()
    if partner in store["data"]:
        store["data"][partner][data_type] = None


def clear_all_partner_data(partner: str = None) -> None:
    """Clear all data (GT and DQ) for a partner. Use when refreshing from SurveyCTO."""
    if partner is None:
        import config
        partner = config.PARTNER

    # Clear session state
    if "data" in st.session_state:
        st.session_state["data"] = None
    if "dq_data" in st.session_state:
        st.session_state["dq_data"] = None

    # Clear from shared cache
    store = _get_data_store()
    if partner in store["data"]:
        del store["data"][partner]
