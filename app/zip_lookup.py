from typing import Optional, Tuple

# Small demo lookup for common CA zip codes. Falls back to state=California
# (this product is CA-only per the SRS) with county left unknown.
ZIP_COUNTY_LOOKUP = {
    "94103": "San Francisco County",
    "94102": "San Francisco County",
    "90001": "Los Angeles County",
    "90012": "Los Angeles County",
    "92101": "San Diego County",
    "95814": "Sacramento County",
    "94607": "Alameda County",
    "95112": "Santa Clara County",
    "93701": "Fresno County",
    "92701": "Orange County",
}


def derive_state_county(zip_code: str) -> Tuple[str, Optional[str]]:
    county = ZIP_COUNTY_LOOKUP.get(zip_code.strip())
    return "California", county
