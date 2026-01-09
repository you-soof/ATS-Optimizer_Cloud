"""
ENTSO-E price provider using spot.utilitarian.io

This client attempts to fetch day-ahead prices from spot.utilitarian.io
and returns a dict with `timestamps` and `prices` (EUR/MWh). If the
remote call fails or the `httpx` package is unavailable, the client
falls back to generating synthetic prices for testing.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import logging

logger = logging.getLogger(__name__)

# Try to import httpx; fall back to dummy behavior if missing
try:
    import httpx

    HTTPX_AVAILABLE = True
except Exception:
    httpx = None
    HTTPX_AVAILABLE = False

# Optional numpy for nicer dummy generation
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except Exception:
    np = None
    NUMPY_AVAILABLE = False

import random
import math


class EntsoeAPI:
    """Client for fetching day-ahead prices from spot.utilitarian.io

    Usage:
        await entsoe_api.get_day_ahead_prices(area="FI", date=some_date, hours=24)

    Returns:
        {"timestamps": List[datetime], "prices": List[float]} (EUR/MWh)
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = base_url or os.getenv(
            "UTILITARIAN_BASE_URL", "https://spot.utilitarian.io"
        )
        self.timeout = timeout

    async def get_day_ahead_prices(
        self, area: str = "FI", date: Optional[datetime] = None, hours: int = 24
    ) -> Dict:
        # If httpx not available, use dummy generator
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not available; returning synthetic day-ahead prices")
            return self._get_dummy_prices(hours)

        # Default to next day (day-ahead)
        if date is None:
            target = (datetime.utcnow() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        else:
            target = date.replace(hour=0, minute=0, second=0, microsecond=0)

        date_str = target.strftime("%Y-%m-%d")

        # Try a set of candidate endpoints/paths that spot.utilitarian.io might expose
        candidate_paths = [
            "/api/v1/spot",
            "/api/v1/prices",
            "/api/v1/price",
            "/prices",
            "/spot",
        ]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for path in candidate_paths:
                url = f"{self.base_url.rstrip('/')}{path}"
                params = {"area": area, "date": date_str}

                try:
                    resp = await client.get(url, params=params)
                except Exception as e:
                    logger.debug(f"Error requesting {url}: {e}")
                    continue

                if resp.status_code != 200:
                    logger.debug(f"Non-200 from {url}: {resp.status_code}")
                    continue

                try:
                    data = resp.json()
                except Exception as e:
                    logger.debug(f"Invalid JSON from {url}: {e}")
                    continue

                # Flexible parsing: look for common keys containing time-series
                timestamps: List[datetime] = []
                prices: List[float] = []

                # Common shapes: {"timestamps": [...], "prices": [...]} or
                # {"data": [{"timestamp":"...","price":...}, ...]} or
                # {"prices": [val,...], "timestamps": [..]}
                if isinstance(data, dict):
                    # Direct keys
                    if "timestamps" in data and "prices" in data:
                        try:
                            timestamps = [
                                self._parse_iso(ts) for ts in data["timestamps"][:hours]
                            ]
                            prices = [float(p) for p in data["prices"][:hours]]
                        except Exception:
                            timestamps, prices = [], []

                    # Data as list of objects
                    elif "data" in data and isinstance(data["data"], list):
                        for item in data["data"][:hours]:
                            try:
                                if isinstance(item, dict) and (
                                    "price" in item or "value" in item
                                ):
                                    ts = (
                                        item.get("timestamp")
                                        or item.get("time")
                                        or item.get("datetime")
                                    )
                                    val = (
                                        item.get("price")
                                        or item.get("value")
                                        or item.get("spot")
                                    )
                                    timestamps.append(self._parse_iso(ts))
                                    prices.append(float(val))
                            except Exception:
                                continue

                    # Nested keys like {"spot_prices": {...}}
                    else:
                        # Try to search recursively for lists of numeric prices
                        # Look for keys that contain 'price' or 'spot'
                        for key, val in data.items():
                            if (
                                key
                                and ("price" in key or "spot" in key)
                                and isinstance(val, list)
                            ):
                                try:
                                    prices = [float(x) for x in val[:hours]]
                                except Exception:
                                    prices = []
                            if (
                                key
                                and ("time" in key or "timestamp" in key)
                                and isinstance(val, list)
                            ):
                                try:
                                    timestamps = [
                                        self._parse_iso(x) for x in val[:hours]
                                    ]
                                except Exception:
                                    timestamps = []

                # If we successfully parsed both, return
                if prices and timestamps and len(prices) == len(timestamps):
                    logger.info(
                        f"Fetched day-ahead prices from {url} for {area} {date_str}"
                    )
                    return {"timestamps": timestamps, "prices": prices}

                # If we have prices but no timestamps, synthesize timestamps starting from target
                if prices and not timestamps:
                    timestamps = [
                        target + timedelta(hours=h) for h in range(len(prices))
                    ]
                    logger.info(
                        f"Fetched day-ahead prices from {url} (timestamps synthesized) for {area} {date_str}"
                    )
                    return {
                        "timestamps": timestamps,
                        "prices": [float(p) for p in prices],
                    }

        # If all attempts failed, fall back to generating dummy prices
        logger.warning(
            "Failed to fetch day-ahead prices from spot.utilitarian.io — falling back to synthetic prices"
        )
        return self._get_dummy_prices(hours, start=target)

    def _get_dummy_prices(self, hours: int, start: Optional[datetime] = None) -> Dict:
        """Generate a synthetic 24-hour price curve (EUR/MWh) for testing."""
        if start is None:
            start = (datetime.utcnow() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

        timestamps = [start + timedelta(hours=h) for h in range(hours)]

        base_price = 60.0
        prices: List[float] = []

        if NUMPY_AVAILABLE:
            hours_arr = np.arange(hours)
            daily_variation = 20.0 * np.sin(hours_arr * 2 * np.pi / 24 - 2.0)
            noise = np.random.normal(0.0, 3.0, size=hours)
            prices = (base_price + daily_variation + noise).tolist()
        else:
            for h in range(hours):
                prices.append(
                    base_price
                    + 20.0 * math.sin((h * 2 * math.pi / 24) - 2.0)
                    + random.gauss(0, 3)
                )

        return {"timestamps": timestamps, "prices": [float(p) for p in prices]}

    def _parse_iso(self, s: Optional[str]) -> datetime:
        """Parse common ISO datetime formats to a datetime object."""
        if not s:
            raise ValueError("Empty timestamp")
        if isinstance(s, (int, float)):
            # assume epoch seconds
            return datetime.fromtimestamp(float(s))
        try:
            # Try fromisoformat (handles YYYY-MM-DDTHH:MM:SS)
            return datetime.fromisoformat(s)
        except Exception:
            # Fallback common formats
            try:
                return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                return datetime.fromtimestamp(float(s))


# Singleton instance
entsoe_api = EntsoeAPI()
