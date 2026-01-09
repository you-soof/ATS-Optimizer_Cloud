"""
Fingrid Open Data API Integration (Fixed)

Fingrid is Finland's transmission system operator.
Their Open Data API provides real-time grid information.

Get API key from: https://data.fingrid.fi/en/instructions

Key datasets:
- Variable 181: Wind power production (MW)
- Variable 74: Total production (MW)
- Variable 177: Grid frequency (Hz)
- Variable 336: Nuclear power production (MW)

Documentation: https://data.fingrid.fi/en/
API Details: https://developer-data.fingrid.fi/api-details
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging
import os
import asyncio
import random
import re

from app.config import Config

try:
    import httpx

    HTTPX_AVAILABLE = True
except Exception:
    httpx = None
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


class FingridAPI:
    """Client for Fingrid Open Data API."""

    # Correct base URL based on Fingrid API documentation
    BASE_URL = "https://data.fingrid.fi/api"

    # Retry/backoff configuration
    MAX_RETRIES = 4
    BACKOFF_FACTOR = 1.0
    JITTER = 0.25

    # Variable IDs for different data types
    VARIABLES = {
        "wind_power": 181,
        "total_production": 74,
        "frequency": 177,
        "nuclear_power": 336,
        "hydro_power": 191,
        "solar_power": 248,
    }

    def __init__(self, api_key: Optional[str] = None):
        # Prefer explicit api_key, then Config, then primary/secondary env vars
        cfg_key = None
        try:
            cfg_key = getattr(Config, "FINGRID_API_KEY", None)
        except Exception:
            cfg_key = None

        self.api_key = (
            api_key
            or cfg_key
            or os.getenv("FINGRID_PRIMARY_API_KEY")
            or os.getenv("FINGRID_SECONDARY_API_KEY")
        )
        if not self.api_key:
            raise RuntimeError(
                "FINGRID API key not configured: set FINGRID_PRIMARY_API_KEY or FINGRID_SECONDARY_API_KEY or FINGRID_API_KEY"
            )
        if not HTTPX_AVAILABLE:
            raise RuntimeError(
                "httpx is required for Fingrid API access but is not installed"
            )

    async def get_grid_status(self) -> Dict:
        """Fetch latest grid metrics (wind %, frequency, stress level, etc.)"""
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "ats-optimizer/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Fetch all values concurrently
                wind_power = await self._get_latest_value(client, headers, "wind_power")
                total_production = await self._get_latest_value(
                    client, headers, "total_production"
                )
                frequency = await self._get_latest_value(client, headers, "frequency")

            wind_percentage = (
                (wind_power / total_production * 100) if total_production > 0 else 0.0
            )

            if 49.9 <= frequency <= 50.1:
                stress_level = "normal"
            elif 49.8 <= frequency <= 50.2:
                stress_level = "warning"
            else:
                stress_level = "critical"

            result = {
                "timestamp": datetime.utcnow(),
                "wind_power_mw": float(wind_power),
                "total_production_mw": float(total_production),
                "wind_percentage": float(wind_percentage),
                "frequency_hz": float(frequency),
                "stress_level": stress_level,
            }

            return result

        except Exception as e:
            logger.error(f"Fingrid API error in get_grid_status: {e}")
            raise

    async def _get_latest_value(
        self, client: httpx.AsyncClient, headers: Dict, variable_name: str
    ) -> float:
        """Get the latest value for a specific variable from Fingrid Open Data.

        Correct endpoint format: /datasets/{datasetId}/data/latest
        """
        variable_id = self.VARIABLES[variable_name]
        # Fixed endpoint path - use /datasets instead of /variable
        url = f"{self.BASE_URL}/datasets/{variable_id}/data/latest"

        resp = await self._request_with_retries(client, url, headers)
        data = resp.json()

        # Fingrid returns data in various formats, handle multiple cases
        if isinstance(data, dict):
            # Try different possible field names
            value = (
                data.get("value")
                or data.get("Value")
                or data.get("data", {}).get("value")
            )
            if value is not None:
                return float(value)
        elif isinstance(data, list) and len(data) > 0:
            # Sometimes returns array with latest value first
            item = data[0]
            value = item.get("value") or item.get("Value")
            if value is not None:
                return float(value)

        raise ValueError(f"Could not extract value from response: {data}")

    async def get_wind_forecast(self, hours: int = 24) -> Dict:
        """Fetch hourly wind power values for the next `hours` hours.

        Uses the correct Fingrid dataset endpoint format.
        """
        headers = {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "ats-optimizer/1.0",
        }

        # Build time range: now -> now + hours
        start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=hours)

        # Format timestamps in ISO format with Z
        start_time = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = end.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                # Fetch wind power data
                wind_data = await self._fetch_dataset(
                    client, headers, "wind_power", start_time, end_time
                )
                # Fetch total production data
                total_data = await self._fetch_dataset(
                    client, headers, "total_production", start_time, end_time
                )

            if not wind_data:
                raise RuntimeError(
                    "No wind forecast data returned from Fingrid data endpoint"
                )

            # Build timestamp to value maps
            wind_map = {item["timestamp"]: item["value"] for item in wind_data}
            total_map = {item["timestamp"]: item["value"] for item in total_data}

            # Use wind timestamps as base
            timestamps = sorted(wind_map.keys())
            wind_power = []
            wind_percentage = []

            # Calculate average total production as fallback
            avg_total = (
                sum(total_map.values()) / max(1, len(total_map))
                if total_map
                else 1000.0
            )

            for ts in timestamps:
                wind_val = wind_map[ts]
                total_val = total_map.get(ts, avg_total)

                wind_power.append(float(wind_val))
                percentage = (wind_val / total_val * 100) if total_val > 0 else 0.0
                wind_percentage.append(float(percentage))

            return {
                "timestamps": timestamps,
                "wind_power_mw": wind_power,
                "wind_percentage": wind_percentage,
            }

        except Exception as e:
            logger.error(f"Fingrid API error in get_wind_forecast: {e}")
            raise

    async def _fetch_dataset(
        self,
        client: httpx.AsyncClient,
        headers: Dict,
        variable_name: str,
        start_time: str,
        end_time: str,
    ) -> List[Dict]:
        """Fetch time series data for a dataset.

        Correct endpoint format: /datasets/{datasetId}/data
        """
        variable_id = self.VARIABLES[variable_name]
        # Fixed endpoint path
        url = f"{self.BASE_URL}/datasets/{variable_id}/data"

        params = {
            "startTime": start_time,
            "endTime": end_time,
            "format": "json",
            # Use a more conservative page size to avoid server issues
            "pageSize": 1000,
        }

        resp = await self._request_with_retries(client, url, headers, params=params)
        data = resp.json()

        results = []

        # Handle different response formats
        data_list = data
        if isinstance(data, dict):
            data_list = data.get("data", []) or data.get("Data", [])

        for item in data_list:
            # Extract timestamp with multiple possible field names
            ts = (
                item.get("startTime")
                or item.get("start_time")
                or item.get("timestamp")
                or item.get("time")
            )
            if not ts:
                continue

            try:
                # Parse timestamp
                if isinstance(ts, str):
                    if ts.endswith("Z"):
                        ts_parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        ts_parsed = datetime.fromisoformat(ts)
                else:
                    ts_parsed = ts
            except Exception as e:
                logger.warning(f"Could not parse timestamp {ts}: {e}")
                continue

            # Extract value
            value = item.get("value") or item.get("Value")
            if value is None:
                continue

            try:
                value = float(value)
            except Exception as e:
                logger.warning(f"Could not parse value {value}: {e}")
                continue

            results.append({"timestamp": ts_parsed, "value": value})

        return results

    async def _request_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict,
        params: Optional[Dict] = None,
    ) -> httpx.Response:
        """Perform GET with retries/backoff on 429 and 5xx errors.

        Honors `Retry-After` header if present or parses a numeric hint from the JSON message.
        """
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = await client.get(url, headers=headers, params=params)

                # Handle explicit rate-limit
                if resp.status_code == 429:
                    # try Retry-After header first
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = int(retry_after)
                        except Exception:
                            # fallback to exponential backoff
                            delay = self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                    else:
                        # try to parse numeric hint from JSON message
                        try:
                            body = resp.json()
                            msg = (
                                body.get("message", "")
                                if isinstance(body, dict)
                                else ""
                            )
                            m = re.search(r"(\d+)", msg)
                            delay = (
                                int(m.group(1))
                                if m
                                else self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                            )
                        except Exception:
                            delay = self.BACKOFF_FACTOR * (2 ** (attempt - 1))

                    jitter = random.random() * self.JITTER
                    wait = delay + jitter
                    logger.warning(
                        "Fingrid rate-limited, attempt %s/%s — sleeping %.2fs",
                        attempt,
                        self.MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # raise for other error statuses
                resp.raise_for_status()
                return resp

            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                # Retry on server errors
                if status and 500 <= status < 600 and attempt < self.MAX_RETRIES:
                    delay = (
                        self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                        + random.random() * self.JITTER
                    )
                    logger.warning(
                        "Fingrid server error %s, attempt %s/%s — sleeping %.2fs",
                        status,
                        attempt,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                # otherwise re-raise
                raise

            except Exception as e:
                if attempt < self.MAX_RETRIES:
                    delay = (
                        self.BACKOFF_FACTOR * (2 ** (attempt - 1))
                        + random.random() * self.JITTER
                    )
                    logger.warning(
                        "Fingrid request error, attempt %s/%s — sleeping %.2fs: %s",
                        attempt,
                        self.MAX_RETRIES,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise


# Singleton instance
fingrid_api = FingridAPI()
