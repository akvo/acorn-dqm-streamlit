"""
Cache utilities for dev mode.
Saves API responses locally to speed up development.
"""

import json
import os
from pathlib import Path
from typing import Optional

CACHE_DIR = Path("data_cache")


def is_dev_mode() -> bool:
    """Check if dev mode is enabled via environment variable."""
    return os.environ.get("DEV_MODE", "").lower() == "true"


def get_cache_path(partner: str, data_type: str) -> Path:
    """Get cache file path for partner's GT or DQ data."""
    return CACHE_DIR / f"{partner}_{data_type}.json"


def save_to_cache(partner: str, data_type: str, json_data: list):
    """Save API response to cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path = get_cache_path(partner, data_type)
    with open(cache_path, 'w') as f:
        json.dump(json_data, f)


def load_from_cache(partner: str, data_type: str) -> Optional[list]:
    """Load cached data if available."""
    cache_path = get_cache_path(partner, data_type)
    if cache_path.exists():
        with open(cache_path, 'r') as f:
            return json.load(f)
    return None


def cache_exists(partner: str, data_type: str) -> bool:
    """Check if cache exists for partner's data."""
    return get_cache_path(partner, data_type).exists()
