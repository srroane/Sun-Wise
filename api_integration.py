from __future__ import annotations

import pandas as pd
import requests
import streamlit as st

# URLs for the three external APIs used in the app
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOLAR_URL = "https://api.forecast.solar/estimate"

# Cache city lookups for 24 hours — coordinates don't change
@st.cache_data(ttl=24 * 3600, show_spinner=False)
def geocode_city(city_name: str) -> dict:
# Request only the top match, in English JSON format
    params = {"name": city_name, "count": 1, "language": "en", "format": "json"}
    response = requests.get(GEOCODING_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
# Raise an error if the city name wasn't recognized
    results = payload.get("results")
    if not results:
        raise ValueError(f"No location found for '{city_name}'.")
# Pull the best match and return just the fields we need
    top = results[0]
    return {
        "name": top.get("name", city_name),
        "country": top.get("country", ""),
        "latitude": float(top["latitude"]),
        "longitude": float(top["longitude"]),
    }

# Cache weather data for 15 minutes — short enough to stay reasonably fresh
@st.cache_data(ttl=15 * 60, show_spinner=False)
def get_weather_forecast(
    latitude: float,
    longitude: float,
    days: int = 7,
) -> pd.DataFrame:
# Request hourly temperature, cloud cover, and solar irradiance
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,cloud_cover,shortwave_radiation",
        "forecast_days": days,
        "timezone": "auto",
    }
    response = requests.get(FORECAST_URL, params=params, timeout=15)
    response.raise_for_status()
    hourly = response.json()["hourly"]

# Build a structured DataFrame — shortwave_radiation is used as a GHI proxy
    weather = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(hourly["time"]),
            "ghi": hourly["shortwave_radiation"],
            "temperature_c": hourly["temperature_2m"],
            "cloud_cover_pct": hourly["cloud_cover"],
        }
    ).set_index("timestamp")

# Fill any gaps with 0 and standardize all columns as float
    return weather.fillna(0.0).astype(float)

# Cache solar estimates for 1 hour — the external API has rate limits
@st.cache_data(ttl=60 * 60, show_spinner=False)
def get_solar_production(
    latitude: float,
    longitude: float,
    declination: float,
    azimuth: float,
    kwp: float,
) -> pd.DataFrame:
# Forecast.Solar uses a path-based REST API — build the URL manually
    url = f"{SOLAR_URL}/{latitude}/{longitude}/{declination}/{azimuth}/{kwp}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
# Extract the daily production values (returned in watt-hours)
    daily_wh = response.json()["result"]["watt_hours_day"]

# Convert Wh to kWh and return as a date-indexed DataFrame
    return pd.DataFrame(
        [
            {"date": pd.to_datetime(day), "production_kwh": wh / 1000.0}
            for day, wh in daily_wh.items()
        ]
    ).set_index("date")
