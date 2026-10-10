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

# Order measured on 10 Oct on one shop frame: 3.6 answered in 19.3 s (39 spines) with thinking LOW;
# 3.8 took 99.5 s with default thinking and its free daily quota ran out; 3.7 / 3.5 returned 503 (busy).
VISION_MODELS = ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.8-flash"]
VISION_THINKING_LEVEL = "LOW"   # None = model default. MINIMAL is rejected by 3.8 (400).
VISION_TIMEOUT_S = 60           # one call longer than this is abandoned and the next model is tried
VISION_WORKERS = 3              # live sweep: frames read in parallel (lower to 1 if per-minute 429s appear)

# Copy-age evidence (from what is visible on the spine, not the catalogue year of the work)
AGE_CUES = ("blackletter", "cloth_binding", "leather_binding", "gilt_lettering", "heavy_wear")
ANTIQUE_STRONG_CUES = ("blackletter", "leather_binding")  # one of these alone -> appraisal
ANTIQUE_MIN_CUES = 2  # or at least this many cues together
MAX_VOLUME_NUMBER = 30  # "vol. 30017" is a series/catalogue number, not a volume
NOTE_NOT_PRICED = "Not priced in this run (price limit reached); excluded from totals"

# Parallel network work (catalogue + pricing are I/O bound). Lower these if a service starts returning 429.
IDENTIFY_WORKERS = 4
PRICE_WORKERS = 8

# Frame quality checks (code, not a model). Calibrate on real frames with tools/quality_report.py.
BLUR_MIN_VAR = 35.0      # variance of Laplacian at 640 px width; below = blurry
GLARE_MAX_FRAC = 0.03     # share of pixels that are near-white and colourless; above = glare
DARK_MAX_MEAN = 60.0      # mean brightness (0-255); below = too dark


# Live sweep: keep a frame only if it is good AND shows something new
KEYFRAME_MIN_CHANGE = 12.0  # mean abs difference (0-255) of 64x48 grey thumbnails vs the last kept frame

# Cost per sweep = measured usage x list price. Fill these from the official pricing pages and write the date.
# Left as None -> the packet reports usage counts and says the cost is unknown (no invented numbers).
VISION_USD_PER_M_INPUT = None     # e.g. Gemini Flash input price per 1M tokens
VISION_USD_PER_M_OUTPUT = None    # output price per 1M tokens
SERPAPI_USD_PER_SEARCH = None     # your plan price / searches per month
PRICE_BASIS = "not set: fill from provider pricing pages (state date)"

TOO_FAST_CHANGE = 60.0         # thumbnail change between two consecutive frames (2 s apart) above this = moving too fast
STEP_CLOSER_UNREADABLE = 0.6   # share of spines in a frame that are partial/unreadable -> ask to step closer
STEP_CLOSER_MIN_SPINES = 3     # only judge frames with at least this many spines


# Cross-frame de-duplication (Layer 9)
DEDUP_MIN_INLIERS = 25   # RANSAC inliers needed to trust that two keyframes overlap
DEDUP_IOU = 0.4          # mapped box overlap needed to call two spines the same book


# Frames whose file name starts with this are for non-book items only (e.g. a sofa next to shelves outside the claim):
# their spines are ignored, so books outside the claim scope are never counted.
ITEMS_ONLY_PREFIX = "items_"
# Live sweep: price each book as soon as it is identified, while the user is still filming, so Finish is fast.
LIVE_PREFETCH_PRICES = True

# Words that mark a detected "item" as one of our own measuring markers, not the policyholder's property
NOT_ITEM_WORDS = ("aruco", "fiducial", "printed marker", "paper marker", "marker tag", "target code")