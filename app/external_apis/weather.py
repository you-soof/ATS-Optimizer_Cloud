"""
Open-Meteo Weather API Integration

Open-Meteo provides free weather forecast data without API key required.
Documentation: https://open-meteo.com/en/docs

We fetch:
- Hourly temperature forecast (next 48 hours)
- Solar radiation (for passive heating calculation)
- Wind speed (affects heat pump efficiency)
"""

try:
    import httpx

    HTTPX_AVAILABLE = True
except Exception:
    httpx = None
    HTTPX_AVAILABLE = False
from datetime import datetime, timedelta
from typing import List, Dict
import logging

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except Exception:
    np = None
    NUMPY_AVAILABLE = False
import random
import math

logger = logging.getLogger(__name__)


class WeatherAPI:
    """Client for Open-Meteo weather API"""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    async def get_forecast(
        self, latitude: float, longitude: float, hours: int = 48
    ) -> Dict:
        """
        Get weather forecast for a location

        Args:
            latitude: Location latitude
            longitude: Location longitude
            hours: Number of hours to forecast (max 168)

        Returns:
            Dict with hourly data:
            {
                'timestamps': List[datetime],
                'temperature': List[float],  # °C
                'solar_radiation': List[float],  # W/m²
                'wind_speed': List[float]  # m/s
            }
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": "temperature_2m,shortwave_radiation,windspeed_10m",
            "timezone": "Europe/Helsinki",
            "forecast_days": min(7, (hours + 23) // 24),  # Convert hours to days
        }

        try:
            if not HTTPX_AVAILABLE:
                logger.warning("httpx not available; returning dummy weather forecast")
                return self._get_dummy_forecast(hours)

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

            # Parse response
            hourly = data["hourly"]

            result = {
                "timestamps": [
                    datetime.fromisoformat(ts) for ts in hourly["time"][:hours]
                ],
                "temperature": hourly["temperature_2m"][:hours],
                "solar_radiation": hourly["shortwave_radiation"][:hours],
                "wind_speed": hourly["windspeed_10m"][:hours],
            }

            logger.info(
                f"Fetched weather forecast for ({latitude}, {longitude}): {len(result['timestamps'])} hours"
            )
            return result

        except httpx.HTTPError as e:
            logger.error(f"Weather API error: {e}")
            # Return dummy data for development
            return self._get_dummy_forecast(hours)
        except Exception as e:
            logger.error(f"Unexpected error in weather API: {e}")
            return self._get_dummy_forecast(hours)

    def _get_dummy_forecast(self, hours: int) -> Dict:
        """
        Generate dummy weather data for testing
        Simulates a typical Finnish winter day
        """
        now = datetime.now()

        # Typical winter pattern: coldest at 6 AM, warmest at 2 PM
        temps = []
        solar = []
        wind = []

        for h in range(hours):
            hour_of_day = (now.hour + h) % 24

            # Temperature: -10°C at night, -5°C during day
            base_temp = -7.5
            if NUMPY_AVAILABLE:
                daily_variation = 2.5 * np.cos((hour_of_day - 14) * np.pi / 12)
                temps.append(base_temp + daily_variation)
            else:
                daily_variation = 2.5 * math.cos((hour_of_day - 14) * math.pi / 12)
                temps.append(base_temp + daily_variation)

            # Solar radiation: only during daylight (9 AM - 3 PM in winter)
            if 9 <= hour_of_day <= 15:
                if NUMPY_AVAILABLE:
                    solar.append(150.0 * np.sin((hour_of_day - 9) * np.pi / 7))
                else:
                    solar.append(150.0 * math.sin((hour_of_day - 9) * math.pi / 7))
            else:
                solar.append(0.0)

            # Wind: constant with some variation
            if NUMPY_AVAILABLE:
                wind.append(5.0 + np.random.uniform(-1, 1))
            else:
                wind.append(5.0 + random.uniform(-1, 1))

        return {
            "timestamps": [now + timedelta(hours=h) for h in range(hours)],
            "temperature": temps,
            "solar_radiation": solar,
            "wind_speed": wind,
        }


# Singleton instance
weather_api = WeatherAPI()
