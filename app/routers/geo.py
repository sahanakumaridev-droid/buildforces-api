import json
import time
import urllib.error
import urllib.parse
import urllib.request
from threading import Lock
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/geo", tags=["geo"])

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ZIPPOPOTAM_URL = "https://api.zippopotam.us/us/{zip}"
USER_AGENT = "BuildforcesOnboarding/1.0 (https://buildforces.com)"

_cache: dict[str, dict[str, Any]] = {}
_lock = Lock()
_last_nominatim_at = 0.0

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
    "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH",
    "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT",
    "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC",
}


def _clean_place(name: str) -> str:
    place = name.strip()
    for suffix in (" County", " Parish", " Borough", " Census Area", " Municipality"):
        if place.endswith(suffix):
            return place[: -len(suffix)]
    return place


def _state_code(state: str, code: str = "") -> str:
    if code and len(code) == 2:
        return code.upper()
    return STATE_ABBR.get(state, "")


def _label(city: str, state: str, code: str = "") -> str:
    abbr = _state_code(state, code)
    place = _clean_place(city)
    return f"{place}, {abbr}" if abbr else f"{place}, {state}"


class ZipLocation(BaseModel):
    zip: str
    city: str
    state: str
    state_code: str
    lat: float
    lon: float
    label: str


def _http_json(url: str, timeout: float = 8.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _pace_nominatim() -> None:
    global _last_nominatim_at
    with _lock:
        wait = 1.05 - (time.monotonic() - _last_nominatim_at)
        if wait > 0:
            time.sleep(wait)
        _last_nominatim_at = time.monotonic()


def _from_nominatim(zip_code: str) -> Optional[ZipLocation]:
    _pace_nominatim()
    query = urllib.parse.urlencode(
        {
            "postalcode": zip_code,
            "country": "US",
            "countrycodes": "us",
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
        }
    )
    try:
        data = _http_json(f"{NOMINATIM_URL}?{query}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(data, list) or not data:
        _pace_nominatim()
        fallback = urllib.parse.urlencode(
            {
                "q": f"{zip_code} USA",
                "countrycodes": "us",
                "format": "json",
                "addressdetails": 1,
                "limit": 1,
            }
        )
        try:
            data = _http_json(f"{NOMINATIM_URL}?{fallback}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
    if not isinstance(data, list) or not data:
        return None

    hit = data[0]
    address = hit.get("address") or {}
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("county")
        or ""
    )
    iso = address.get("ISO3166-2-lvl4") or ""
    iso_code = iso.split("-")[-1] if iso else ""
    state = address.get("state") or ""
    state_code = _state_code(state, iso_code or address.get("state_code") or "")
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not city or not state:
        return None
    city = _clean_place(city)
    return ZipLocation(
        zip=zip_code,
        city=city,
        state=state,
        state_code=state_code,
        lat=lat,
        lon=lon,
        label=_label(city, state, state_code),
    )


def _from_zippopotam(zip_code: str) -> Optional[ZipLocation]:
    try:
        data = _http_json(ZIPPOPOTAM_URL.format(zip=zip_code))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, urllib.error.HTTPError):
        return None
    places = data.get("places") if isinstance(data, dict) else None
    if not places:
        return None
    place = places[0]
    try:
        lat = float(place["latitude"])
        lon = float(place["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    city = _clean_place(place.get("place name") or "")
    state = place.get("state") or ""
    state_code = _state_code(state, place.get("state abbreviation") or "")
    if not city:
        return None
    return ZipLocation(
        zip=zip_code,
        city=city,
        state=state,
        state_code=state_code,
        lat=lat,
        lon=lon,
        label=_label(city, state, state_code),
    )


@router.get("/zip", response_model=ZipLocation)
def lookup_zip(q: str = Query(..., min_length=5, max_length=10)):
    zip_code = "".join(ch for ch in q if ch.isdigit())[:5]
    if len(zip_code) != 5:
        raise HTTPException(status_code=400, detail="Enter a 5-digit U.S. ZIP code.")

    cached = _cache.get(zip_code)
    if cached:
        return cached

    location = _from_zippopotam(zip_code) or _from_nominatim(zip_code)
    if not location:
        raise HTTPException(status_code=404, detail="We couldn't find that ZIP code.")

    payload = location.model_dump()
    _cache[zip_code] = payload
    return payload
