"""SiteScout AI - business discovery from OpenStreetMap (Overpass, Nominatim fallback)."""
import time

import httpx

from app import config

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# friendly name -> OSM tag (key, value)
CATEGORIES = {
    "cafe": ("amenity", "cafe"),
    "restaurant": ("amenity", "restaurant"),
    "fast_food": ("amenity", "fast_food"),
    "bakery": ("shop", "bakery"),
    "clothes": ("shop", "clothes"),
    "hairdresser": ("shop", "hairdresser"),
    "beauty": ("shop", "beauty"),
    "gym": ("leisure", "fitness_centre"),
    "dentist": ("amenity", "dentist"),
    "pharmacy": ("amenity", "pharmacy"),
    "car_repair": ("shop", "car_repair"),
    "hotel": ("tourism", "hotel"),
}

HEADERS = {"User-Agent": config.USER_AGENT}


class DiscoveryError(Exception):
    """Raised when a data source cannot be reached. Never means 'no businesses'."""


def find_city(city: str, country: str = ""):
    """Return (display_name, south, west, north, east), None if not found, or raise DiscoveryError."""
    query = f"{city}, {country}".strip(", ")
    try:
        r = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers=HEADERS, timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DiscoveryError(f"Could not look up the city (Nominatim): {exc}") from exc
    if not data:
        return None
    s, n, w, e = (float(x) for x in data[0]["boundingbox"])
    return data[0]["display_name"], s, w, n, e


def build_query(category: str, bbox) -> str:
    key, value = CATEGORIES[category]
    s, w, n, e = bbox
    return (
        f"[out:json][timeout:25];"
        f'(node["{key}"="{value}"]({s},{w},{n},{e});'
        f'way["{key}"="{value}"]({s},{w},{n},{e}););'
        f"out center tags 300;"
    )


def run_overpass(query: str) -> dict:
    """Try each Overpass server in turn. Raise DiscoveryError if all fail."""
    problems = []
    for url in OVERPASS_URLS:
        try:
            r = httpx.post(url, data={"data": query}, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            problems.append(f"{url} -> HTTP {r.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            problems.append(f"{url} -> {type(exc).__name__}")
        time.sleep(1)
    raise DiscoveryError("All Overpass servers failed: " + "; ".join(problems))


def _lead(name, category, country, city, tags, address, osm_ref, source):
    return {
        "name": name,
        "category": category,
        "country": country or None,
        "city": city,
        "phone": tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile"),
        "email": tags.get("email") or tags.get("contact:email"),
        "address": address,
        "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "source": source,
        "source_url": f"https://www.openstreetmap.org/{osm_ref}",
        "osm_ref": osm_ref,
    }


def parse_overpass(data: dict, category: str, city: str, country: str) -> list:
    """Turn raw OSM elements into lead dicts. Only real OSM data, nothing invented."""
    leads = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")]
        address = ", ".join(p for p in parts if p) or None
        osm_ref = f"{el.get('type')}/{el.get('id')}"
        leads.append(_lead(name, category, country, city, tags, address, osm_ref,
                           "OpenStreetMap (Overpass)"))
    return leads


def nominatim_category_search(city: str, country: str, category: str) -> list:
    """Fallback: ask Nominatim for 'category in city'. Max 40 results."""
    key, value = CATEGORIES[category]
    query = f"{category.replace('_', ' ')} in {city}, {country}".strip(", ")
    try:
        r = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 40,
                    "extratags": 1, "addressdetails": 1},
            headers=HEADERS, timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise DiscoveryError(f"Nominatim search failed: {exc}") from exc
    leads, seen = [], set()
    for x in data:
        # keep only results whose OSM category really matches
        if x.get("class") != key or x.get("type") != value:
            continue
        name = x.get("name")
        osm_ref = f"{x.get('osm_type')}/{x.get('osm_id')}"
        if not name or osm_ref in seen:
            continue
        seen.add(osm_ref)
        leads.append(_lead(name, category, country, city, x.get("extratags") or {},
                           x.get("display_name"), osm_ref, "OpenStreetMap (Nominatim)"))
    return leads


def discover(city: str, country: str, category: str):
    """Return (leads, source_name). Raises DiscoveryError if every source is unreachable."""
    if category not in CATEGORIES:
        raise DiscoveryError("Unknown category.")
    found = find_city(city, country)
    if found is None:
        raise DiscoveryError(f"City not found: {city}")
    _, s, w, n, e = found
    time.sleep(1)
    try:
        data = run_overpass(build_query(category, (s, w, n, e)))
        return parse_overpass(data, category, city, country), "Overpass"
    except DiscoveryError as overpass_error:
        time.sleep(1)
        try:
            return nominatim_category_search(city, country, category), "Nominatim"
        except DiscoveryError as nominatim_error:
            raise DiscoveryError(f"{overpass_error} | {nominatim_error}") from nominatim_error
