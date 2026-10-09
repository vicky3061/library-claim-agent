import os

from dotenv import load_dotenv

load_dotenv()  # reads .env into environment variables

# locale (a setting, not hardcoded: proves the second-country requirement)
COUNTRY = os.getenv("COUNTRY", "IN")
CURRENCY = os.getenv("CURRENCY", "INR")

# identification: matches below this confidence go to the review queue
ID_REVIEW_THRESHOLD = 0.90

SQFT_PER_SQM = 10.7639

SHELF_MARKER_CM = 10.0
WALL_MARKER_CM = 18.0

# identification
ID_ACCEPT_THRESHOLD = 0.80   # below this: unidentified, title left blank
ID_REVIEW_THRESHOLD = 0.90   # accepted, but below this: also flagged for review
ID_AMBIGUITY_MARGIN = 0.05   # two different titles this close: ambiguous, refuse to pick

GOOGLE_BOOKS_API_KEY = os.getenv("GOOGLE_BOOKS_API_KEY") or None

SERPAPI_KEY = os.getenv("SERPAPI_KEY") or None
CACHE_DIR = "runs/cache"
MARKETS = {
    "IN": {"amazon_domain": "amazon.in", "currency": "INR"},
    "US": {"amazon_domain": "amazon.com", "currency": "USD"},
}
FALLBACK_MARKET = "US"

# used value and appraisal (stated assumptions, see README)
USED_CONDITION_ASSUMED = "Good: used, complete, normal wear, no major damage"
APPRAISAL_PRICE_LIMIT = {"INR": 5000.0, "USD": 60.0}
APPRAISAL_PUBLISHED_BEFORE = 1960
APPRAISAL_KEYWORDS = ("signed", "autographed", "first edition", "1st edition", "limited edition", "antiquarian")

# vision: tried in order; verified with `python -m tools.probe_models` on 2026-10-09
VISION_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]

# Copy-age evidence (from what is visible on the spine, not the catalogue year of the work)
AGE_CUES = ("blackletter", "cloth_binding", "leather_binding", "gilt_lettering", "heavy_wear")
ANTIQUE_STRONG_CUES = ("blackletter", "leather_binding")  # one of these alone -> appraisal
ANTIQUE_MIN_CUES = 2  # or at least this many cues together
MAX_VOLUME_NUMBER = 30  # "vol. 30017" is a series/catalogue number, not a volume
NOTE_NOT_PRICED = "Not priced in this run (price limit reached); excluded from totals"