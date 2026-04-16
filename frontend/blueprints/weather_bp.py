"""weather_bp.py — Lightweight weather proxy for world clocks.

Uses Open-Meteo (free, no API key) with 30-minute in-memory cache.
"""

import json
import time
import threading
import urllib.request
import urllib.parse
import logging

from flask import Blueprint, jsonify, request

weather_bp = Blueprint('weather', __name__)
logger = logging.getLogger(__name__)

_cache = {}          # {city_lower: {data, fetched_at}}
_cache_lock = threading.Lock()
_CACHE_TTL = 1800    # 30 minutes

# Pre-mapped coordinates for the 28 cities in the frontend timezone pool
_CITY_COORDS = {
    'melbourne': (-37.81, 144.96), 'sydney': (-33.87, 151.21),
    'auckland': (-36.85, 174.76), 'singapore': (1.35, 103.82),
    'delhi': (28.61, 77.21), 'mumbai': (19.08, 72.88),
    'dubai': (25.20, 55.27), 'bangkok': (13.76, 100.50),
    'jakarta': (-6.21, 106.85), 'manila': (14.60, 120.98),
    'hong kong': (22.32, 114.17), 'shanghai': (31.23, 121.47),
    'seoul': (37.57, 126.98), 'tokyo': (35.68, 139.69),
    'london': (51.51, -0.13), 'paris': (48.86, 2.35),
    'istanbul': (41.01, 28.98), 'moscow': (55.76, 37.62),
    'cape town': (-33.93, 18.42), 'new york': (40.71, -74.01),
    'chicago': (41.88, -87.63), 'denver': (39.74, -104.99),
    'los angeles': (34.05, -118.24), 'hawaii': (21.31, -157.86),
    'são paulo': (-23.55, -46.63), 'buenos aires': (-34.60, -58.38),
    'fiji': (-17.77, 177.97), 'utc': (0.0, 0.0),
}

# WMO weather code → short description + emoji-free icon hint
_WMO_DESC = {
    0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Rime fog',
    51: 'Light drizzle', 53: 'Drizzle', 55: 'Heavy drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain',
    71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
    77: 'Snow grains', 80: 'Light showers', 81: 'Showers', 82: 'Heavy showers',
    85: 'Light snow showers', 86: 'Snow showers',
    95: 'Thunderstorm', 96: 'Thunderstorm + hail', 99: 'Heavy thunderstorm',
}


def _fetch_weather(city):
    """Fetch current weather from Open-Meteo. Returns dict or None."""
    city_lower = city.lower().strip()
    coords = _CITY_COORDS.get(city_lower)
    if not coords:
        return None
    lat, lon = coords
    url = (
        f'https://api.open-meteo.com/v1/forecast'
        f'?latitude={lat}&longitude={lon}'
        f'&current_weather=true'
        f'&temperature_unit=celsius'
    )
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Fridays/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        cw = data.get('current_weather', {})
        code = int(cw.get('weathercode', -1))
        return {
            'temperature': cw.get('temperature'),
            'windspeed': cw.get('windspeed'),
            'description': _WMO_DESC.get(code, 'Unknown'),
            'weathercode': code,
            'is_day': bool(cw.get('is_day', 1)),
        }
    except Exception as e:
        logger.debug('Weather fetch failed for %s: %s', city, e)
        return None


def _get_cached(city):
    city_lower = city.lower().strip()
    now = time.time()
    with _cache_lock:
        entry = _cache.get(city_lower)
        if entry and (now - entry['fetched_at']) < _CACHE_TTL:
            return entry['data']
    data = _fetch_weather(city)
    if data is not None:
        with _cache_lock:
            _cache[city_lower] = {'data': data, 'fetched_at': now}
    return data


@weather_bp.route('/api/weather', methods=['GET'])
def get_weather():
    """GET /api/weather?cities=Melbourne,Singapore,..."""
    raw = request.args.get('cities', '')
    cities = [c.strip() for c in raw.split(',') if c.strip()][:10]
    results = {}
    for city in cities:
        data = _get_cached(city)
        if data:
            results[city] = data
    return jsonify(results)
