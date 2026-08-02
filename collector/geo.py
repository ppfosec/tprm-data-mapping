"""Resolve job-board location strings to countries.

Boards are inconsistent in a way that matters here: one posting says
"Amsterdam, The Netherlands; Dublin, Ireland", the next says "SF, NYC, SEA, CHI",
and a third says "Hybrid". A posting can name several sites, so this returns a
set, and a posting that names no place at all is reported as unplaceable rather
than quietly dropped -- a board that withholds location is itself a finding.
"""

import re

EEA = {
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia", "Denmark",
    "Estonia", "Finland", "France", "Germany", "Greece", "Hungary", "Iceland",
    "Ireland", "Italy", "Latvia", "Liechtenstein", "Lithuania", "Luxembourg",
    "Malta", "Netherlands", "Norway", "Poland", "Portugal", "Romania",
    "Slovakia", "Slovenia", "Spain", "Sweden",
}

US_STATES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)

US_STATE_NAMES = re.compile(
    r"^(alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|"
    r"georgia|hawaii|idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|"
    r"massachusetts|michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    r"new hampshire|new jersey|new mexico|new york|north carolina|ohio|oklahoma|oregon|"
    r"pennsylvania|rhode island|south carolina|tennessee|texas|utah|vermont|virginia|"
    r"washington|wisconsin)$",
    re.I,
)

ALIASES = [
    (re.compile(r"^(usa|u\.?s\.?a?\.?|united states.*|america)$", re.I), "United States"),
    (re.compile(r"^(uk|gb|u\.k\.|united kingdom.*|england|scotland|wales|northern ireland)$", re.I), "United Kingdom"),
    (re.compile(r"^(the )?netherlands$", re.I), "Netherlands"),
    (re.compile(r"^(uae|united arab emirates)$", re.I), "United Arab Emirates"),
    (re.compile(r"^(korea|south korea|republic of korea)$", re.I), "South Korea"),
    (re.compile(r"^(czechia|czech republic)$", re.I), "Czechia"),
]

COUNTRIES = {
    c.lower(): c
    for c in [
        "Ireland", "Germany", "France", "Spain", "Italy", "Portugal", "Poland", "Sweden",
        "Denmark", "Norway", "Finland", "Belgium", "Switzerland", "Austria", "Greece",
        "Romania", "Bulgaria", "Croatia", "Estonia", "Lithuania", "Latvia", "Luxembourg",
        "Hungary", "Slovakia", "Slovenia", "Iceland", "Malta", "Cyprus", "Israel", "India",
        "Japan", "Singapore", "Australia", "New Zealand", "Brazil", "Mexico", "Argentina",
        "Chile", "Colombia", "Canada", "China", "Taiwan", "Hong Kong", "Turkey", "Nigeria",
        "Kenya", "Egypt", "South Africa", "Saudi Arabia", "Philippines", "Indonesia",
        "Vietnam", "Thailand", "Malaysia", "Ukraine", "Serbia", "Costa Rica", "Uruguay",
    ]
}

CITIES = {
    "london": "United Kingdom", "manchester": "United Kingdom", "edinburgh": "United Kingdom",
    "paris": "France", "lyon": "France", "dublin": "Ireland", "cork": "Ireland",
    "berlin": "Germany", "munich": "Germany", "münchen": "Germany", "hamburg": "Germany",
    "frankfurt": "Germany", "cologne": "Germany",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain",
    "milan": "Italy", "rome": "Italy", "lisbon": "Portugal", "porto": "Portugal",
    "stockholm": "Sweden", "copenhagen": "Denmark", "oslo": "Norway", "helsinki": "Finland",
    "brussels": "Belgium", "zurich": "Switzerland", "zürich": "Switzerland", "geneva": "Switzerland",
    "vienna": "Austria", "warsaw": "Poland", "kraków": "Poland", "krakow": "Poland",
    "prague": "Czechia", "athens": "Greece", "bucharest": "Romania", "sofia": "Bulgaria",
    "budapest": "Hungary", "tel aviv": "Israel", "jerusalem": "Israel", "haifa": "Israel",
    "bengaluru": "India", "bangalore": "India", "mumbai": "India", "delhi": "India",
    "new delhi": "India", "hyderabad": "India", "pune": "India", "chennai": "India",
    "gurugram": "India", "gurgaon": "India", "noida": "India",
    "tokyo": "Japan", "osaka": "Japan", "seoul": "South Korea", "singapore": "Singapore",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia",
    "perth": "Australia", "auckland": "New Zealand",
    "são paulo": "Brazil", "sao paulo": "Brazil", "rio de janeiro": "Brazil",
    "mexico city": "Mexico", "guadalajara": "Mexico", "bogotá": "Colombia", "bogota": "Colombia",
    "buenos aires": "Argentina", "santiago": "Chile", "montevideo": "Uruguay",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "montréal": "Canada",
    "ottawa": "Canada", "waterloo": "Canada",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates", "riyadh": "Saudi Arabia",
    "hong kong": "Hong Kong", "taipei": "Taiwan", "shanghai": "China", "beijing": "China",
    "istanbul": "Turkey", "lagos": "Nigeria", "nairobi": "Kenya", "cairo": "Egypt",
    "cape town": "South Africa", "johannesburg": "South Africa",
    "manila": "Philippines", "jakarta": "Indonesia", "bangkok": "Thailand",
    "kuala lumpur": "Malaysia", "ho chi minh city": "Vietnam", "hanoi": "Vietnam",
    "kyiv": "Ukraine", "belgrade": "Serbia",
    "san francisco": "United States", "sf": "United States", "new york": "United States",
    "nyc": "United States", "seattle": "United States", "sea": "United States",
    "chicago": "United States", "chi": "United States", "austin": "United States",
    "boston": "United States", "denver": "United States", "atlanta": "United States",
    "los angeles": "United States", "washington": "United States", "washington dc": "United States",
    "miami": "United States", "dallas": "United States", "houston": "United States",
    "portland": "United States", "san diego": "United States", "philadelphia": "United States",
    "phoenix": "United States", "detroit": "United States", "nashville": "United States",
    "salt lake city": "United States", "minneapolis": "United States", "raleigh": "United States",
    "san jose": "United States", "palo alto": "United States", "mountain view": "United States",
    "boulder": "United States",
}

MODE_WORDS = re.compile(
    r"\b(remote|hybrid|in[-\s]?office|on[-\s]?site|onsite|distributed|flexible|"
    r"work from home|wfh|or|and|only|based)\b",
    re.I,
)

UNPLACEABLE = "Unplaceable"


def countries_of(name):
    """Every country a single posting touches. Empty set means unplaceable."""
    if not name or not name.strip():
        return set()
    raw = re.sub(r"\(.*?\)", " ", name)
    found = set()
    for frag in re.split(r"[;•|/]|\s&\s", raw):
        found |= _resolve_fragment(frag)
    return found


def _resolve_fragment(frag):
    frag = frag.strip()
    if not frag:
        return set()
    out = set()
    if re.match(r"^u\.?s\.?[\s-]", frag, re.I) or re.search(r"\bus[-\s]remote\b", frag, re.I):
        out.add("United States")

    cleaned = MODE_WORDS.sub(" ", frag)
    cleaned = re.sub(r"[-–—]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return out

    for seg in [s.strip() for s in cleaned.split(",") if s.strip()]:
        c = _resolve_token(seg)
        if c:
            out.add(c)
    if not out:
        c = _resolve_token(cleaned)
        if c:
            out.add(c)
    return out


def _resolve_token(tok):
    t = tok.strip()
    if not t:
        return None
    for rx, name in ALIASES:
        if rx.match(t):
            return name
    if t.lower() in COUNTRIES:
        return COUNTRIES[t.lower()]
    if len(t) == 2 and t.upper() in US_STATES:
        return "United States"
    if US_STATE_NAMES.match(t):
        return "United States"
    return CITIES.get(t.lower())
